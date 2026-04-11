from __future__ import annotations
from contextlib import closing
from contextlib import contextmanager
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator
import uuid
from work_tree_contracts import WorkTree, Branch, Task, TreeStatus, BranchStatus, TaskStatus, ToolStatus


_TREES: dict[str, WorkTree] = {}
_BRANCHES: dict[str, Branch] = {}
_TASKS: dict[str, Task] = {}
_SCORES: dict[str, float] = {}
_DB_PATH = Path(__file__).resolve().parent / "runtime" / "work_tree.sqlite3"
_DB_SCHEMA_VERSION = 1
_DEFAULT_TREE_ALLOWED_TOOLS = (
    "web_fetch",
    "web_search",
    "web_research",
    "web_gather",
    "wikipedia_lookup",
    "stackexchange_search",
    "read",
    "ls",
    "find",
    "health",
    "system_check",
    "queue_status",
    "phase2_audit",
    "pulse",
    "weather_current_location",
    "weather_location",
    "location_coords",
)
_KNOWN_TOOL_NAMES = frozenset(
    _DEFAULT_TREE_ALLOWED_TOOLS
    + (
        "patch_apply",
        "patch_rollback",
        "camera",
        "screen",
        "update_now",
        "update_now_confirm",
        "update_now_cancel",
    )
)


def _now() -> datetime:
    return datetime.now()


def _dt(value: datetime) -> str:
    return value.isoformat()


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(str(value or "").strip())


def _json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=True)


def _json_load(value: str | None, default):
    if not value:
        return default
    try:
        loaded = json.loads(value)
    except Exception:
        return default
    return loaded


def _json_list(value: str | None) -> list[str]:
    loaded = _json_load(value, [])
    if not isinstance(loaded, list):
        return []
    return [str(item).strip() for item in loaded if str(item).strip()]


def _json_dict(value: str | None) -> dict[str, str]:
    loaded = _json_load(value, {})
    if not isinstance(loaded, dict):
        return {}
    return {str(key).strip(): str(item).strip() for key, item in loaded.items() if str(key).strip()}


def _db_connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(_DB_PATH, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


@contextmanager
def _db_transaction() -> Iterator[sqlite3.Connection]:
    with closing(_db_connect()) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _apply_schema_migrations(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version >= _DB_SCHEMA_VERSION:
        return
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS work_trees (
            tree_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            root_branch_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            meta_json TEXT
        );

        CREATE TABLE IF NOT EXISTS work_tree_branches (
            branch_id TEXT PRIMARY KEY,
            tree_id TEXT NOT NULL,
            parent_branch_id TEXT,
            title TEXT NOT NULL,
            bucket TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            priority INTEGER NOT NULL,
            score REAL NOT NULL,
            depth INTEGER NOT NULL,
            depends_on_json TEXT NOT NULL,
            blocked_by_json TEXT NOT NULL,
            children_json TEXT NOT NULL,
            open_stem_count INTEGER NOT NULL,
            required_tools_json TEXT NOT NULL,
            allowed_tools_json TEXT NOT NULL,
            preferred_tool TEXT,
            tool_state_json TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS work_tree_tasks (
            task_id TEXT PRIMARY KEY,
            branch_id TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            priority INTEGER NOT NULL,
            score REAL NOT NULL,
            depends_on_json TEXT NOT NULL
        );
        """
    )
    connection.execute(f"PRAGMA user_version = {_DB_SCHEMA_VERSION}")


def _ensure_db() -> None:
    with _db_transaction() as connection:
        _apply_schema_migrations(connection)


def _clear_in_memory() -> None:
    _TREES.clear()
    _BRANCHES.clear()
    _TASKS.clear()
    _SCORES.clear()


def _load_persisted_state() -> None:
    _clear_in_memory()
    if not _DB_PATH.exists():
        return
    _ensure_db()
    with closing(_db_connect()) as connection:
        for row in connection.execute("SELECT * FROM work_trees"):
            try:
                tree = WorkTree(
                    tree_id=str(row["tree_id"]),
                    title=str(row["title"]),
                    status=TreeStatus(str(row["status"])),
                    root_branch_id=str(row["root_branch_id"]),
                    created_at=_parse_dt(str(row["created_at"])),
                    updated_at=_parse_dt(str(row["updated_at"])),
                    meta=_json_load(row["meta_json"], None),
                )
            except Exception:
                continue
            _TREES[tree.tree_id] = tree
        for row in connection.execute("SELECT * FROM work_tree_branches"):
            try:
                tool_state_data = _json_dict(row["tool_state_json"])
                branch = Branch(
                    branch_id=str(row["branch_id"]),
                    tree_id=str(row["tree_id"]),
                    parent_branch_id=str(row["parent_branch_id"]) if row["parent_branch_id"] is not None else None,
                    title=str(row["title"]),
                    bucket=str(row["bucket"]),
                    status=BranchStatus(str(row["status"])),
                    created_at=_parse_dt(str(row["created_at"])),
                    updated_at=_parse_dt(str(row["updated_at"])),
                    priority=int(row["priority"]),
                    score=float(row["score"]),
                    depth=int(row["depth"]),
                    depends_on=_json_list(row["depends_on_json"]),
                    blocked_by=_json_list(row["blocked_by_json"]),
                    children=_json_list(row["children_json"]),
                    open_stem_count=int(row["open_stem_count"]),
                    required_tools=_json_list(row["required_tools_json"]),
                    allowed_tools=_json_list(row["allowed_tools_json"]),
                    preferred_tool=str(row["preferred_tool"]) if row["preferred_tool"] is not None else None,
                    tool_state={key: ToolStatus(value) for key, value in tool_state_data.items()},
                    notes=str(row["notes"]) if row["notes"] is not None else None,
                )
            except Exception:
                continue
            _BRANCHES[branch.branch_id] = branch
            _SCORES[branch.branch_id] = branch.score
        for row in connection.execute("SELECT * FROM work_tree_tasks"):
            try:
                task = Task(
                    task_id=str(row["task_id"]),
                    branch_id=str(row["branch_id"]),
                    title=str(row["title"]),
                    status=TaskStatus(str(row["status"])),
                    created_at=_parse_dt(str(row["created_at"])),
                    updated_at=_parse_dt(str(row["updated_at"])),
                    priority=int(row["priority"]),
                    score=float(row["score"]),
                    depends_on=_json_list(row["depends_on_json"]),
                )
            except Exception:
                continue
            _TASKS[task.task_id] = task


def _set_db_path(db_path: str | Path) -> None:
    global _DB_PATH
    _DB_PATH = Path(db_path)
    _ensure_db()
    _load_persisted_state()


def _save_tree_record(connection: sqlite3.Connection, tree: WorkTree) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO work_trees (
            tree_id, title, status, root_branch_id, created_at, updated_at, meta_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tree.tree_id,
            tree.title,
            tree.status.value,
            tree.root_branch_id,
            _dt(tree.created_at),
            _dt(tree.updated_at),
            _json_dump(tree.meta),
        ),
    )


def _save_branch_record(connection: sqlite3.Connection, branch: Branch) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO work_tree_branches (
            branch_id, tree_id, parent_branch_id, title, bucket, status, created_at, updated_at,
            priority, score, depth, depends_on_json, blocked_by_json, children_json, open_stem_count,
            required_tools_json, allowed_tools_json, preferred_tool, tool_state_json, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            branch.branch_id,
            branch.tree_id,
            branch.parent_branch_id,
            branch.title,
            branch.bucket,
            branch.status.value,
            _dt(branch.created_at),
            _dt(branch.updated_at),
            branch.priority,
            branch.score,
            branch.depth,
            _json_dump(branch.depends_on),
            _json_dump(branch.blocked_by),
            _json_dump(branch.children),
            branch.open_stem_count,
            _json_dump(branch.required_tools),
            _json_dump(branch.allowed_tools),
            branch.preferred_tool,
            _json_dump({key: value.value for key, value in branch.tool_state.items()}),
            branch.notes,
        ),
    )


def _save_task_record(connection: sqlite3.Connection, task: Task) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO work_tree_tasks (
            task_id, branch_id, title, status, created_at, updated_at, priority, score, depends_on_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task.task_id,
            task.branch_id,
            task.title,
            task.status.value,
            _dt(task.created_at),
            _dt(task.updated_at),
            task.priority,
            task.score,
            _json_dump(task.depends_on),
        ),
    )


def _persist_tree_state(tree_id: str) -> None:
    tree = _TREES.get(tree_id)
    if tree is None:
        return
    branches = _tree_branches(tree_id)
    branch_ids = [branch.branch_id for branch in branches]
    with _db_transaction() as connection:
        connection.execute("DELETE FROM work_tree_tasks WHERE branch_id IN (SELECT branch_id FROM work_tree_branches WHERE tree_id = ?)", (tree_id,))
        connection.execute("DELETE FROM work_tree_branches WHERE tree_id = ?", (tree_id,))
        _save_tree_record(connection, tree)
        for branch in branches:
            _save_branch_record(connection, branch)
        for task in sorted(_TASKS.values(), key=lambda item: (item.created_at, item.task_id)):
            if task.branch_id in branch_ids:
                _save_task_record(connection, task)


def _branch_tasks(branch_id: str) -> list[Task]:
    tasks = [task for task in _TASKS.values() if task.branch_id == branch_id]
    tasks.sort(key=lambda task: (task.created_at, task.task_id))
    return tasks


def _tree_branches(tree_id: str) -> list[Branch]:
    branches = [branch for branch in _BRANCHES.values() if branch.tree_id == tree_id]
    branches.sort(key=lambda branch: (branch.depth, branch.created_at, branch.branch_id))
    return branches


def _normalize_tool_names(value: list[str] | tuple[str, ...] | None) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in list(value or []):
        tool_name = str(item or "").strip()
        if not tool_name or tool_name in seen:
            continue
        seen.add(tool_name)
        ordered.append(tool_name)
    return ordered


def _tree_policy(tree: WorkTree | None) -> dict[str, object]:
    if tree is None or not isinstance(tree.meta, dict):
        return {}
    policy = tree.meta.get("execution_policy")
    return dict(policy) if isinstance(policy, dict) else {}


def _tree_allowed_tools(tree: WorkTree | None) -> list[str]:
    policy = _tree_policy(tree)
    allowed = _normalize_tool_names(policy.get("allowed_tools") if isinstance(policy.get("allowed_tools"), list) else None)
    return allowed or list(_DEFAULT_TREE_ALLOWED_TOOLS)


def _tree_requires_explicit_allow(tree: WorkTree | None) -> bool:
    policy = _tree_policy(tree)
    return bool(policy.get("require_explicit_allow", True))


def _branch_declared_tools(branch: Branch) -> list[str]:
    return _normalize_tool_names(list(branch.required_tools) + list(branch.allowed_tools))


def _branch_candidate_tool(branch: Branch) -> str:
    preferred = str(branch.preferred_tool or "").strip()
    if preferred:
        return preferred
    for tool_name in _branch_declared_tools(branch):
        if tool_name:
            return tool_name
    return ""


def _tool_governance_status(tree: WorkTree | None, branch: Branch, tool_name: str) -> tuple[bool, str]:
    selected_tool = str(tool_name or "").strip()
    if not selected_tool:
        return False, "no_tool_selected"
    if selected_tool not in _KNOWN_TOOL_NAMES:
        return False, "unknown_tool"
    declared = _branch_declared_tools(branch)
    if declared:
        if selected_tool not in declared:
            return False, "branch_tool_not_declared"
    elif _tree_requires_explicit_allow(tree):
        return False, "branch_tool_not_declared"
    if selected_tool not in _tree_allowed_tools(tree):
        return False, "tree_policy_blocked"
    return True, ""


def _governance_payload(tree: WorkTree | None, branch: Branch, tool_name: str, reason: str) -> dict:
    branch.tool_state[tool_name] = ToolStatus.BLOCKED if tool_name else ToolStatus.BLOCKED
    branch.updated_at = _now()
    _persist_tree_state(branch.tree_id)
    return {
        "action": "governance_blocked",
        "branch_id": branch.branch_id,
        "branch_title": branch.title,
        "recommended_tool": tool_name,
        "reason": reason,
        "branch_declared_tools": _branch_declared_tools(branch),
        "tree_allowed_tools": _tree_allowed_tools(tree),
    }


def _blocked_dependencies(branch: Branch) -> list[str]:
    blocked: list[str] = []
    for dependency_id in branch.depends_on:
        dependency = _BRANCHES.get(dependency_id)
        if dependency is None or dependency.status != BranchStatus.COMPLETE:
            blocked.append(dependency_id)
    blocked.sort()
    return blocked


def _branch_ancestor_ids(branch_id: str) -> list[str]:
    ancestors: list[str] = []
    current = _BRANCHES.get(branch_id)
    seen: set[str] = set()
    while current is not None and current.parent_branch_id is not None:
        parent_id = current.parent_branch_id
        if parent_id in seen:
            break
        seen.add(parent_id)
        ancestors.append(parent_id)
        current = _BRANCHES.get(parent_id)
    return ancestors


def _refresh_branch_state(branch: Branch) -> None:
    tasks = _branch_tasks(branch.branch_id)
    open_tasks = [task for task in tasks if task.status not in (TaskStatus.COMPLETE, TaskStatus.DROPPED)]
    active_tasks = [task for task in open_tasks if task.status == TaskStatus.ACTIVE]
    branch.open_stem_count = len(open_tasks)
    branch.blocked_by = _blocked_dependencies(branch)
    if branch.status == BranchStatus.ARCHIVED:
        branch.score = recompute_branch_score(branch)
        _SCORES[branch.branch_id] = branch.score
        return
    if branch.blocked_by:
        branch.status = BranchStatus.BLOCKED
    elif branch.open_stem_count == 0:
        branch.status = BranchStatus.COMPLETE
    elif active_tasks:
        branch.status = BranchStatus.ACTIVE
    else:
        branch.status = BranchStatus.READY
    branch.score = recompute_branch_score(branch)
    _SCORES[branch.branch_id] = branch.score


def _refresh_tree_state(tree_id: str, persist: bool = False) -> None:
    tree = _TREES.get(tree_id)
    if tree is None:
        return
    branches = _tree_branches(tree_id)
    for branch in branches:
        _refresh_branch_state(branch)
    tree.status = TreeStatus.COMPLETE if is_tree_complete(tree_id) else TreeStatus.ACTIVE
    tree.updated_at = _now()
    if persist:
        _persist_tree_state(tree_id)


def create_tree(title: str, meta: dict[str, object] | None = None) -> WorkTree:
    now = _now()
    tree_id = f"tree_{uuid.uuid4().hex[:8]}"
    root_branch_id = f"branch_{uuid.uuid4().hex[:8]}"
    return WorkTree(
        tree_id=tree_id,
        title=title,
        status=TreeStatus.ACTIVE,
        root_branch_id=root_branch_id,
        created_at=now,
        updated_at=now,
        meta=meta
    )


def create_branch(tree_id: str, title: str, bucket: str, parent_branch_id: str | None = None) -> Branch:
    now = _now()
    branch_id = f"branch_{uuid.uuid4().hex[:8]}"
    depth = 0
    if parent_branch_id is not None:
        parent = _BRANCHES.get(parent_branch_id)
        if parent is not None:
            depth = parent.depth + 1
    return Branch(
        branch_id=branch_id,
        tree_id=tree_id,
        parent_branch_id=parent_branch_id,
        title=title,
        bucket=bucket,
        status=BranchStatus.READY,
        created_at=now,
        updated_at=now,
        depth=depth
    )


def create_task(branch_id: str, title: str) -> Task:
    now = _now()
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    return Task(
        task_id=task_id,
        branch_id=branch_id,
        title=title,
        status=TaskStatus.OPEN,
        created_at=now,
        updated_at=now
    )


def get_tree(tree_id: str) -> WorkTree | None:
    return _TREES.get(tree_id)


def save_tree(tree: WorkTree) -> None:
    _TREES[tree.tree_id] = tree
    _ensure_db()
    with _db_transaction() as connection:
        _save_tree_record(connection, tree)


def add_branch_to_tree(tree_id: str, title: str, bucket: str, parent_branch_id: str | None = None) -> Branch:
    tree = get_tree(tree_id)
    if tree is None:
        raise ValueError(f"Tree {tree_id} not found")
    if parent_branch_id is not None:
        parent = _BRANCHES.get(parent_branch_id)
        if parent is None:
            raise ValueError(f"Parent branch {parent_branch_id} not found")
        if parent.tree_id != tree_id:
            raise ValueError("Parent branch must stay within the same tree")
    branch = create_branch(tree_id, title, bucket, parent_branch_id)
    _BRANCHES[branch.branch_id] = branch
    if parent_branch_id is not None:
        parent = _BRANCHES.get(parent_branch_id)
        if parent is not None and branch.branch_id not in parent.children:
            parent.children.append(branch.branch_id)
            parent.updated_at = branch.updated_at
    branch.score = recompute_branch_score(branch)
    _SCORES[branch.branch_id] = branch.score
    tree.updated_at = branch.updated_at
    save_tree(tree)
    _persist_tree_state(tree_id)
    return branch


def mark_task_complete(task_id: str) -> None:
    task = _TASKS.get(task_id)
    if task is None:
        raise ValueError(f"Task {task_id} not found")

    if task.status in (TaskStatus.COMPLETE, TaskStatus.DROPPED):
        return

    now = _now()
    task.status = TaskStatus.COMPLETE
    task.updated_at = now

    branch = _BRANCHES.get(task.branch_id)
    if branch is None:
        return
    branch.updated_at = now
    _refresh_tree_state(branch.tree_id, persist=True)


def next_open_branch(tree_id: str) -> Branch | None:
    tree = get_tree(tree_id)
    if tree is None:
        return None

    _refresh_tree_state(tree_id, persist=True)
    candidates: list[Branch] = []
    for branch in _tree_branches(tree_id):
        if is_branch_ready(branch.branch_id) and branch.open_stem_count > 0:
            candidates.append(branch)

    if not candidates:
        tree.status = TreeStatus.COMPLETE if is_tree_complete(tree_id) else TreeStatus.ACTIVE
        tree.updated_at = _now()
        return None

    candidates.sort(
        key=lambda branch: (
            branch.depth,
            -branch.score,
            branch.created_at,
            branch.branch_id,
        )
    )
    selected = candidates[0]
    now = _now()
    for branch in _tree_branches(tree_id):
        if branch.branch_id == selected.branch_id:
            branch.status = BranchStatus.ACTIVE
            branch.updated_at = now
            continue
        if branch.status == BranchStatus.ACTIVE:
            branch.status = BranchStatus.READY if branch.open_stem_count > 0 and not branch.blocked_by else branch.status
            branch.updated_at = now
    tree.status = TreeStatus.ACTIVE
    tree.updated_at = now
    return selected


def initialize_tree(title: str, meta: dict[str, object] | None = None) -> WorkTree:
    tree_meta = dict(meta or {})
    if not isinstance(tree_meta.get("execution_policy"), dict):
        tree_meta["execution_policy"] = {
            "allowed_tools": list(_DEFAULT_TREE_ALLOWED_TOOLS),
            "require_explicit_allow": True,
        }
    tree = create_tree(title, tree_meta)
    root_branch = Branch(
        branch_id=tree.root_branch_id,
        tree_id=tree.tree_id,
        parent_branch_id=None,
        title=f"Root: {title}",
        bucket="root",
        status=BranchStatus.READY,
        created_at=tree.created_at,
        updated_at=tree.updated_at,
    )
    _BRANCHES[root_branch.branch_id] = root_branch
    root_branch.score = recompute_branch_score(root_branch)
    _SCORES[root_branch.branch_id] = root_branch.score
    save_tree(tree)
    _persist_tree_state(tree.tree_id)
    return tree


def add_task_to_branch(branch_id: str, title: str) -> Task:
    branch = _BRANCHES.get(branch_id)
    if branch is None:
        raise ValueError(f"Branch {branch_id} not found")
    task = create_task(branch_id, title)
    _TASKS[task.task_id] = task
    branch.updated_at = task.updated_at
    _refresh_tree_state(branch.tree_id, persist=True)
    return task


def recompute_branch_score(branch: Branch) -> float:
    base = branch.priority * 0.6 + branch.open_stem_count * 10
    base -= branch.depth * 2
    base -= len(branch.depends_on) * 5
    base -= len(branch.blocked_by) * 15
    if branch.status == BranchStatus.BLOCKED:
        base -= 20
    if branch.status == BranchStatus.COMPLETE:
        base = 0.0
    return max(0.0, min(100.0, base))


def is_tree_complete(tree_id: str) -> bool:
    tree = get_tree(tree_id)
    if tree is None:
        return False

    for branch in _tree_branches(tree_id):
        if branch.status == BranchStatus.ARCHIVED:
            continue
        if branch.status == BranchStatus.BLOCKED:
            return False
        if branch.open_stem_count > 0:
            return False
    return True


def add_dependency(branch_id: str, depends_on_branch_id: str) -> None:
    branch = _BRANCHES.get(branch_id)
    depends_on_branch = _BRANCHES.get(depends_on_branch_id)
    if branch is None:
        raise ValueError(f"Branch {branch_id} not found")
    if depends_on_branch is None:
        raise ValueError(f"Branch {depends_on_branch_id} not found")
    if branch.tree_id != depends_on_branch.tree_id:
        raise ValueError("Dependencies must stay within the same tree")
    if branch.branch_id == depends_on_branch_id:
        raise ValueError("Branch cannot depend on itself")
    if branch.branch_id in _branch_ancestor_ids(depends_on_branch_id):
        raise ValueError("Dependency would create a cycle")
    if depends_on_branch_id not in branch.depends_on:
        branch.depends_on.append(depends_on_branch_id)
    branch.updated_at = _now()
    _refresh_tree_state(branch.tree_id, persist=True)


def is_branch_ready(branch_id: str) -> bool:
    branch = _BRANCHES.get(branch_id)
    if branch is None:
        return False
    if branch.status in (BranchStatus.COMPLETE, BranchStatus.ARCHIVED):
        return False
    return not _blocked_dependencies(branch)


def set_branch_tools(branch_id: str, required_tools: list[str] | None = None, allowed_tools: list[str] | None = None, preferred_tool: str | None = None) -> None:
    branch = _BRANCHES.get(branch_id)
    if branch is None:
        raise ValueError(f"Branch {branch_id} not found")
    tree = _TREES.get(branch.tree_id)
    next_required = _normalize_tool_names(required_tools) if required_tools is not None else _normalize_tool_names(branch.required_tools)
    next_allowed = _normalize_tool_names(allowed_tools) if allowed_tools is not None else _normalize_tool_names(branch.allowed_tools)
    next_preferred = str(preferred_tool).strip() if preferred_tool is not None else str(branch.preferred_tool or "").strip()
    declared = _normalize_tool_names(next_required + next_allowed + ([next_preferred] if next_preferred else []))
    unknown = [tool_name for tool_name in declared if tool_name not in _KNOWN_TOOL_NAMES]
    if unknown:
        raise ValueError(f"Unknown tool(s): {', '.join(unknown)}")
    if next_allowed and any(tool_name not in next_allowed for tool_name in next_required):
        raise ValueError("Required tools must be included in allowed tools")
    if next_preferred and declared and next_preferred not in declared:
        raise ValueError("Preferred tool must be declared on the branch")
    if next_preferred and not declared and _tree_requires_explicit_allow(tree):
        raise ValueError("Preferred tool must be declared on the branch")
    if required_tools is not None:
        branch.required_tools = next_required
    if allowed_tools is not None:
        branch.allowed_tools = next_allowed
    if preferred_tool is not None:
        branch.preferred_tool = next_preferred or None
    for tool in _normalize_tool_names(list(branch.required_tools) + list(branch.allowed_tools) + ([branch.preferred_tool] if branch.preferred_tool else [])):
        if tool not in branch.tool_state:
            branch.tool_state[tool] = ToolStatus.READY
    branch.updated_at = _now()
    _refresh_tree_state(branch.tree_id, persist=True)


def set_tree_execution_policy(tree_id: str, allowed_tools: list[str] | None = None, require_explicit_allow: bool = True) -> None:
    tree = _TREES.get(tree_id)
    if tree is None:
        raise ValueError(f"Tree {tree_id} not found")
    normalized_allowed = _normalize_tool_names(allowed_tools) if allowed_tools is not None else _tree_allowed_tools(tree)
    unknown = [tool_name for tool_name in normalized_allowed if tool_name not in _KNOWN_TOOL_NAMES]
    if unknown:
        raise ValueError(f"Unknown tool(s): {', '.join(unknown)}")
    meta = dict(tree.meta or {})
    meta["execution_policy"] = {
        "allowed_tools": normalized_allowed,
        "require_explicit_allow": bool(require_explicit_allow),
    }
    tree.meta = meta
    tree.updated_at = _now()
    _persist_tree_state(tree_id)


def is_tooling_ready(branch_id: str) -> bool:
    branch = _BRANCHES.get(branch_id)
    if branch is None:
        return False
    if not branch.required_tools:
        return True
    for tool in branch.required_tools:
        state = branch.tool_state.get(tool, ToolStatus.BLOCKED)
        if state != ToolStatus.READY:
            return False
    return True


def _next_open_task(branch_id: str) -> Task | None:
    tasks = _branch_tasks(branch_id)
    return next(
        (
            task
            for task in tasks
            if task.status not in (TaskStatus.COMPLETE, TaskStatus.DROPPED)
        ),
        None,
    )


def _tool_args_for_task(tool_name: str, task: Task) -> list[str]:
    no_arg_tools = {
        "camera",
        "health",
        "phase2_audit",
        "pulse",
        "queue_status",
        "screen",
        "system_check",
        "update_now",
        "update_now_cancel",
        "weather_current_location",
    }
    if tool_name in no_arg_tools:
        return []
    title = str(task.title or "").strip()
    return [title] if title else []


def _is_invalid_tool_result(tool_name: str, result: object) -> tuple[bool, str]:
    """Detect no-op results that should not be marked as completed work."""
    if isinstance(result, dict):
        if not bool(result.get("ok", True)):
            return True, str(result.get("error") or "unknown error")
        return False, ""
    if tool_name not in {"read", "ls", "find"}:
        return False, ""
    text = str(result or "").strip().lower()
    if not text:
        return True, "empty_result"
    invalid_prefixes = (
        "not a file:",
        "file not found:",
        "not found:",
        "error:",
    )
    if any(text.startswith(prefix) for prefix in invalid_prefixes):
        return True, str(result or "invalid_result")
    return False, ""


def next_autonomous_step(tree_id: str) -> dict | None:
    tree = get_tree(tree_id)
    if tree is None:
        return None
    branch = next_open_branch(tree_id)
    if branch is None:
        return None
    if not is_tooling_ready(branch.branch_id):
        return {"action": "wait_for_tools", "branch_id": branch.branch_id, "missing_tools": [t for t in branch.required_tools if branch.tool_state.get(t) != ToolStatus.READY]}
    recommended_tool = _branch_candidate_tool(branch)
    if not recommended_tool:
        return {
            "action": "no_tool_selected",
            "branch_id": branch.branch_id,
            "branch_title": branch.title,
            "branch_declared_tools": _branch_declared_tools(branch),
        }
    allowed, reason = _tool_governance_status(tree, branch, recommended_tool)
    if not allowed:
        return _governance_payload(tree, branch, recommended_tool, reason)
    return {
        "action": "execute",
        "branch_id": branch.branch_id,
        "branch_title": branch.title,
        "recommended_tool": recommended_tool,
        "required_tools": branch.required_tools,
        "allowed_tools": branch.allowed_tools
    }


def execute_autonomous_step(tree_id: str, execute_planned_action_fn: Callable[[str, list[str] | None], object]) -> dict | None:
    step = next_autonomous_step(tree_id)
    if step is None:
        return None
    if str(step.get("action") or "") != "execute":
        return step

    branch_id = str(step.get("branch_id") or "").strip()
    branch = _BRANCHES.get(branch_id)
    if branch is None:
        return {"action": "missing_branch", "branch_id": branch_id}

    task = _next_open_task(branch_id)
    if task is None:
        _refresh_tree_state(tree_id, persist=True)
        return {"action": "no_open_task", "branch_id": branch_id, "branch_title": branch.title}

    tool_name = str(step.get("recommended_tool") or "").strip()
    if not tool_name:
        return {
            "action": "no_tool_selected",
            "branch_id": branch_id,
            "branch_title": branch.title,
            "task_id": task.task_id,
            "task_title": task.title,
        }

    now = _now()
    task.status = TaskStatus.ACTIVE
    task.updated_at = now
    branch.updated_at = now
    branch.tool_state[tool_name] = ToolStatus.RUNNING
    _persist_tree_state(tree_id)

    tool_args = _tool_args_for_task(tool_name, task)
    result = execute_planned_action_fn(tool_name, tool_args)

    invalid_result, invalid_reason = _is_invalid_tool_result(tool_name, result)
    if invalid_result:
        branch.tool_state[tool_name] = ToolStatus.FAILED
        branch.updated_at = _now()
        _persist_tree_state(tree_id)
        return {
            "action": "tool_failed",
            "branch_id": branch_id,
            "branch_title": branch.title,
            "task_id": task.task_id,
            "task_title": task.title,
            "tool": tool_name,
            "tool_args": tool_args,
            "error": invalid_reason or "unknown error",
        }

    branch.tool_state[tool_name] = ToolStatus.READY
    branch.updated_at = _now()
    mark_task_complete(task.task_id)
    return {
        "action": "executed",
        "branch_id": branch_id,
        "branch_title": branch.title,
        "task_id": task.task_id,
        "task_title": task.title,
        "tool": tool_name,
        "tool_args": tool_args,
        "tool_result": result,
    }


def run_autonomous_loop(tree_id: str, max_steps: int = 100, execute_planned_action_fn: Callable[[str, list[str] | None], object] | None = None) -> list[dict]:
    history: list[dict] = []
    limit = max(1, int(max_steps or 0))
    for _ in range(limit):
        if execute_planned_action_fn is not None:
            step = execute_autonomous_step(tree_id, execute_planned_action_fn)
        else:
            step = next_autonomous_step(tree_id)
        if step is None:
            break
        action = str(step.get("action") or "").strip()
        if execute_planned_action_fn is None and action == "no_tool_selected":
            local_step = dict(step)
            local_step["action"] = "execute"
            history.append(local_step)
        else:
            history.append(dict(step))
        if execute_planned_action_fn is not None:
            if action != "executed":
                break
            if is_tree_complete(tree_id):
                break
            continue
        if action not in {"execute", "no_tool_selected"}:
            break
        branch_id = str(step.get("branch_id") or "").strip()
        next_task = _next_open_task(branch_id)
        if next_task is None:
            _refresh_tree_state(tree_id)
            continue
        if next_task.status != TaskStatus.ACTIVE:
            next_task.status = TaskStatus.ACTIVE
            next_task.updated_at = _now()
        mark_task_complete(next_task.task_id)
        if is_tree_complete(tree_id):
            break
    return history


def get_visual_tree_data(tree_id: str) -> dict | None:
    """Return a lightweight node/edge structure suitable for GUI tree rendering."""
    tree = get_tree(tree_id)
    if tree is None:
        return None
    _refresh_tree_state(tree_id, persist=False)
    branches = _tree_branches(tree_id)
    dependency_edges: list[dict] = []
    nodes: list[dict] = []
    for branch in branches:
        branch_tasks = [t for t in _TASKS.values() if t.branch_id == branch.branch_id]
        tasks_open = sum(1 for t in branch_tasks if t.status not in (TaskStatus.COMPLETE, TaskStatus.DROPPED))
        nodes.append({
            "id": branch.branch_id,
            "title": branch.title,
            "status": branch.status.value,
            "parent_id": branch.parent_branch_id,
            "depth": branch.depth,
            "tasks_open": tasks_open,
            "tasks_total": len(branch_tasks),
            "preferred_tool": branch.preferred_tool or "",
            "required_tools": list(branch.required_tools),
            "allowed_tools": list(branch.allowed_tools),
            "blocked_by": list(branch.blocked_by),
            "depends_on": list(branch.depends_on),
        })
        for dep_id in branch.depends_on:
            dependency_edges.append({"from": dep_id, "to": branch.branch_id})
    tree_meta = dict(tree.meta or {}) if isinstance(tree.meta, dict) else {}
    return {
        "tree_id": tree.tree_id,
        "title": tree.title,
        "status": tree.status.value,
        "root_branch_id": tree.root_branch_id,
        "updated_at": _dt(tree.updated_at),
        "kind": str(tree_meta.get("kind") or ""),
        "source": str(tree_meta.get("source") or ""),
        "nodes": nodes,
        "dependency_edges": dependency_edges,
    }


def inspect_tree(tree_id: str) -> dict | None:
    tree = get_tree(tree_id)
    if tree is None:
        return None
    _refresh_tree_state(tree_id, persist=True)
    branches = _tree_branches(tree_id)
    tasks = [task for task in _TASKS.values() if _BRANCHES.get(task.branch_id, Branch("", "", None, "", "", BranchStatus.ARCHIVED, _now(), _now())).tree_id == tree_id]
    tasks.sort(key=lambda task: (task.created_at, task.task_id))
    branch_counts: dict[str, int] = {status.value: 0 for status in BranchStatus}
    task_counts: dict[str, int] = {status.value: 0 for status in TaskStatus}
    for branch in branches:
        branch_counts[branch.status.value] = branch_counts.get(branch.status.value, 0) + 1
    for task in tasks:
        task_counts[task.status.value] = task_counts.get(task.status.value, 0) + 1

    def _branch_summary(branch: Branch) -> dict:
        current_task = _next_open_task(branch.branch_id)
        return {
            "branch_id": branch.branch_id,
            "title": branch.title,
            "status": branch.status.value,
            "depends_on": list(branch.depends_on),
            "blocked_by": list(branch.blocked_by),
            "required_tools": list(branch.required_tools),
            "allowed_tools": list(branch.allowed_tools),
            "preferred_tool": branch.preferred_tool,
            "open_stem_count": int(branch.open_stem_count),
            "current_task": {
                "task_id": current_task.task_id,
                "title": current_task.title,
                "status": current_task.status.value,
            } if current_task is not None else None,
        }

    active_branch = next((branch for branch in branches if branch.status == BranchStatus.ACTIVE), None)
    ready_branches = [_branch_summary(branch) for branch in branches if branch.status in {BranchStatus.READY, BranchStatus.ACTIVE}]
    blocked_branches = [_branch_summary(branch) for branch in branches if branch.status == BranchStatus.BLOCKED]
    step = next_autonomous_step(tree_id)
    return {
        "tree_id": tree.tree_id,
        "title": tree.title,
        "status": tree.status.value,
        "root_branch_id": tree.root_branch_id,
        "created_at": _dt(tree.created_at),
        "updated_at": _dt(tree.updated_at),
        "counts": {
            "branches": branch_counts,
            "tasks": task_counts,
            "open_tasks": sum(1 for task in tasks if task.status not in {TaskStatus.COMPLETE, TaskStatus.DROPPED}),
            "total_tasks": len(tasks),
        },
        "active_branch": _branch_summary(active_branch) if active_branch is not None else None,
        "ready_branches": ready_branches,
        "blocked_branches": blocked_branches,
        "next_step": step,
        "policy": {
            "allowed_tools": _tree_allowed_tools(tree),
            "require_explicit_allow": _tree_requires_explicit_allow(tree),
        },
    }


def active_tree_session_summary(tree_id: str) -> dict | None:
    snapshot = inspect_tree(tree_id)
    if snapshot is None:
        return None
    next_step = snapshot.get("next_step") if isinstance(snapshot.get("next_step"), dict) else {}
    active_branch = snapshot.get("active_branch") if isinstance(snapshot.get("active_branch"), dict) else {}
    counts = snapshot.get("counts") if isinstance(snapshot.get("counts"), dict) else {}
    return {
        "tree_id": snapshot.get("tree_id"),
        "title": snapshot.get("title"),
        "status": snapshot.get("status"),
        "open_tasks": int(counts.get("open_tasks") or 0),
        "next_action": str(next_step.get("action") or ""),
        "next_branch_title": str(next_step.get("branch_title") or next_step.get("branch_id") or ""),
        "active_branch_title": str(active_branch.get("title") or ""),
        "blocked_branch_count": len(list(snapshot.get("blocked_branches") or [])),
    }


def format_tree_snapshot(tree_id: str) -> str:
    snapshot = inspect_tree(tree_id)
    if snapshot is None:
        return "The active work tree could not be found."
    counts = snapshot.get("counts") if isinstance(snapshot.get("counts"), dict) else {}
    branch_counts = counts.get("branches") if isinstance(counts.get("branches"), dict) else {}
    next_step = snapshot.get("next_step") if isinstance(snapshot.get("next_step"), dict) else {}
    active_branch = snapshot.get("active_branch") if isinstance(snapshot.get("active_branch"), dict) else {}
    blocked_branches = [item for item in list(snapshot.get("blocked_branches") or []) if isinstance(item, dict)]
    lines = [
        f"Active work tree: {snapshot.get('title') or snapshot.get('tree_id')} ({snapshot.get('status')}).",
        f"Tasks open: {int(counts.get('open_tasks') or 0)} of {int(counts.get('total_tasks') or 0)}. Ready branches: {int(branch_counts.get(BranchStatus.READY.value, 0) or 0)}. Blocked branches: {len(blocked_branches)}.",
    ]
    if active_branch:
        current_task = active_branch.get("current_task") if isinstance(active_branch.get("current_task"), dict) else {}
        current_task_title = str(current_task.get("title") or "").strip()
        if current_task_title:
            lines.append(f"Active branch: {active_branch.get('title')} on task {current_task_title}.")
        else:
            lines.append(f"Active branch: {active_branch.get('title')}.")
    action = str(next_step.get("action") or "").strip()
    if action == "execute":
        lines.append(
            f"Next step: {next_step.get('branch_title') or next_step.get('branch_id')}. Recommended tool: {next_step.get('recommended_tool') or 'none'}."
        )
    elif action == "wait_for_tools":
        missing = ", ".join(str(item).strip() for item in list(next_step.get("missing_tools") or []) if str(item).strip()) or "required tools"
        lines.append(f"Next step is waiting for tools: {missing}.")
    elif action == "governance_blocked":
        lines.append(
            f"Next step is governance-blocked on {next_step.get('branch_title') or next_step.get('branch_id')}: {next_step.get('recommended_tool') or 'tool'} ({next_step.get('reason') or 'blocked'})."
        )
    elif action == "no_tool_selected":
        lines.append(f"Next step has no governed tool selected for {next_step.get('branch_title') or next_step.get('branch_id')}.")
    if blocked_branches:
        blocked_titles = ", ".join(str(item.get("title") or item.get("branch_id") or "").strip() for item in blocked_branches[:3] if str(item.get("title") or item.get("branch_id") or "").strip())
        if blocked_titles:
            lines.append(f"Blocked branches: {blocked_titles}.")
    policy = snapshot.get("policy") if isinstance(snapshot.get("policy"), dict) else {}
    allowed_tools = [str(item).strip() for item in list(policy.get("allowed_tools") or []) if str(item).strip()]
    if allowed_tools:
        preview = ", ".join(allowed_tools[:5])
        if len(allowed_tools) > 5:
            preview = f"{preview}, ..."
        lines.append(f"Tree policy allows: {preview}.")
    return " ".join(line for line in lines if str(line).strip())


_ensure_db()
_load_persisted_state()