from __future__ import annotations
from contextlib import closing
from contextlib import contextmanager
import json
import os
import sqlite3
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator
import uuid
from work_tree_contracts import WorkTree, Branch, Task, TreeStatus, BranchStatus, TaskStatus, ToolStatus


_TREES: dict[str, WorkTree] = {}
_BRANCHES: dict[str, Branch] = {}
_TASKS: dict[str, Task] = {}
_SCORES: dict[str, float] = {}
_DB_PATH = Path(__file__).resolve().parent / "runtime" / "_internal" / "work_tree.db"
_DB_REQUESTED_PATH = _DB_PATH
_DB_CONNECT_TARGET: str = str(_DB_PATH)
_DB_CONNECT_USE_URI = False
_DB_MEMORY_ANCHORS: dict[str, sqlite3.Connection] = {}
_DB_GUARD_LOG = Path(__file__).resolve().parent / "runtime" / "work_tree_db_guard.log"
_DB_SCHEMA_VERSION = 3
_DB_RETRY_ATTEMPTS = 4
_DB_RETRY_SLEEP_SEC = 0.15
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
        "generated_queue_run",
        "patch_preview_approve",
        "patch_preview_apply",
        "patch_apply",
        "patch_rollback",
        "camera",
        "screen",
        "update_now",
        "update_now_confirm",
        "update_now_cancel",
    )
)


DecisionCallback = Callable[[str, list[dict]], dict | None]


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


def _json_object_dict(value: str | None) -> dict[str, object]:
    loaded = _json_load(value, {})
    if not isinstance(loaded, dict):
        return {}
    out: dict[str, object] = {}
    for key, item in loaded.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        out[key_text] = item
    return out


def _append_db_guard(event: str, detail: str) -> None:
    try:
        _DB_GUARD_LOG.parent.mkdir(parents=True, exist_ok=True)
        line = f"{_dt(_now())} | {event} | {detail}\n"
        with _DB_GUARD_LOG.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception:
        pass


def _db_journal_path() -> Path:
    return _DB_PATH.with_name(f"{_DB_PATH.name}-journal")


def _memory_db_target(db_path: Path) -> str:
    slug = str(db_path).replace("\\", "_").replace("/", "_").replace(":", "_")
    return f"file:work_tree_{slug}?mode=memory&cache=shared"


def _memory_fallback_disk_path(db_path: Path, unique: bool = False) -> Path:
    fallback_root = Path(__file__).resolve().parent / "runtime" / "_internal" / "work_tree_fallback"
    fallback_root.mkdir(parents=True, exist_ok=True)
    safe_name = db_path.name or f"work_tree_{uuid.uuid4().hex[:8]}.sqlite3"
    if unique:
        stem = Path(safe_name).stem
        suffix = Path(safe_name).suffix or ".sqlite3"
        safe_name = f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"
    return fallback_root / safe_name


def _sync_memory_db_to_disk() -> None:
    global _DB_PATH
    target = str(_DB_CONNECT_TARGET or "")
    if not _DB_CONNECT_USE_URI or not target.startswith("file:"):
        return
    anchor = _DB_MEMORY_ANCHORS.get(target)
    if anchor is None:
        return
    for sync_attempt in range(2):
        try:
            _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            journal_path = _db_journal_path()
            if _DB_PATH.exists() and _DB_PATH.stat().st_size == 0:
                try:
                    _DB_PATH.unlink()
                except Exception:
                    pass
            if journal_path.exists():
                try:
                    journal_path.unlink()
                except Exception:
                    pass
            with closing(sqlite3.connect(_DB_PATH)) as disk_connection:
                anchor.backup(disk_connection)
            return
        except Exception as exc:
            _append_db_guard("memory_sync_failed", f"path={_DB_PATH} err={exc}")
            if sync_attempt == 0:
                _DB_PATH = _memory_fallback_disk_path(_DB_REQUESTED_PATH, unique=True)
                _append_db_guard("memory_sync_retry_path", f"path={_DB_PATH}")
                continue
            break


def _activate_memory_db_fallback(requested_path: Path | None = None) -> None:
    global _DB_PATH
    global _DB_CONNECT_TARGET
    global _DB_CONNECT_USE_URI
    source_path = Path(requested_path or _DB_REQUESTED_PATH or _DB_PATH)
    _DB_PATH = _memory_fallback_disk_path(source_path)
    target = _memory_db_target(source_path)
    anchor = _DB_MEMORY_ANCHORS.get(target)
    if anchor is None:
        anchor = sqlite3.connect(target, uri=True, isolation_level=None, timeout=30.0)
        anchor.row_factory = sqlite3.Row
        anchor.execute("PRAGMA foreign_keys = ON")
        try:
            anchor.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        _DB_MEMORY_ANCHORS[target] = anchor
    _DB_CONNECT_TARGET = target
    _DB_CONNECT_USE_URI = True
    _append_db_guard("memory_fallback_enabled", f"requested={source_path} mirror={_DB_PATH} target={target}")


def _guard_db_header(stage: str) -> None:
    if not _DB_PATH.exists():
        return
    try:
        data = _DB_PATH.read_bytes()
    except Exception as exc:
        _append_db_guard("read_failed", f"stage={stage} err={exc}")
        return
    if not data:
        _append_db_guard("empty_file", f"stage={stage}")
        return
    if not data.startswith(b"SQLite format 3\x00"):
        header_hex = " ".join(f"{b:02X}" for b in data[:32])
        has_bom = data.startswith(b"\xEF\xBB\xBF")
        _append_db_guard(
            "invalid_header",
            f"stage={stage} size={len(data)} has_bom={has_bom} header={header_hex}",
        )


_DB_ACCESS_LOG = Path(__file__).resolve().parent / "runtime" / "work_tree_access.log"


def _log_db_access() -> None:
    try:
        _DB_ACCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _DB_ACCESS_LOG.open("a", encoding="utf-8") as f:
            f.write(f"\n=== ACCESS {time.time()} PID={os.getpid()} ===\n")
            f.write("".join(traceback.format_stack(limit=6)))
    except Exception:
        pass


def _is_retryable_db_error(exc: Exception) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    text = str(exc or "").strip().lower()
    return any(
        token in text
        for token in (
            "database is locked",
            "database table is locked",
            "disk i/o error",
            "database is busy",
        )
    )


def _attempt_db_recovery(exc: Exception) -> bool:
    if not _is_retryable_db_error(exc):
        return False
    journal_path = _db_journal_path()
    if not journal_path.exists():
        return False
    try:
        stamp = _now().strftime("%Y%m%d_%H%M%S")
        recovered = journal_path.with_name(f"{journal_path.name}.stale_{stamp}")
        journal_path.replace(recovered)
        _append_db_guard("journal_quarantined", f"src={journal_path} dst={recovered} err={exc}")
        return True
    except Exception as recovery_exc:
        _append_db_guard("journal_quarantine_failed", f"path={journal_path} err={recovery_exc}")
        return False


def _db_connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _log_db_access()
    _guard_db_header("before_connect")
    connection = sqlite3.connect(_DB_CONNECT_TARGET, isolation_level=None, timeout=30.0, uri=_DB_CONNECT_USE_URI)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute("PRAGMA busy_timeout = 5000")
    except Exception as exc:
        _append_db_guard("pragma_busy_timeout_failed", str(exc))
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
    except Exception as exc:
        _append_db_guard("pragma_wal_failed", str(exc))
        if _attempt_db_recovery(exc):
            try:
                connection.close()
            except Exception:
                pass
            connection = sqlite3.connect(_DB_PATH, isolation_level=None, timeout=30.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            try:
                connection.execute("PRAGMA busy_timeout = 5000")
            except Exception as retry_exc:
                _append_db_guard("pragma_busy_timeout_failed_after_recovery", str(retry_exc))
    return connection


@contextmanager
def _db_transaction() -> Iterator[sqlite3.Connection]:
    connection = None
    for attempt in range(1, _DB_RETRY_ATTEMPTS + 1):
        try:
            connection = _db_connect()
            connection.execute("BEGIN IMMEDIATE")
        except Exception as exc:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
                connection = None
            if _is_retryable_db_error(exc) and attempt < _DB_RETRY_ATTEMPTS:
                _append_db_guard("retryable_db_error", f"attempt={attempt} err={exc}")
                _attempt_db_recovery(exc)
                time.sleep(_DB_RETRY_SLEEP_SEC * attempt)
                continue
            raise
        else:
            break
    else:
        raise RuntimeError("work_tree_db_transaction_exhausted")

    try:
        yield connection
        connection.commit()
        _sync_memory_db_to_disk()
    except Exception:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        raise
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


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
            notes TEXT,
            source_type TEXT,
            source_key TEXT,
            source_payload_json TEXT,
            work_class TEXT,
            actionability TEXT,
            resolution_state TEXT,
            last_seen_at TEXT,
            evidence_count INTEGER NOT NULL DEFAULT 0
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
            depends_on_json TEXT NOT NULL,
            meta_json TEXT NOT NULL DEFAULT '{}'
        );
        """
    )

    branch_columns = {
        str(row[1]).strip().lower()
        for row in connection.execute("PRAGMA table_info(work_tree_branches)")
    }

    def _ensure_branch_column(name: str, sql_type: str) -> None:
        if name.lower() in branch_columns:
            return
        connection.execute(f"ALTER TABLE work_tree_branches ADD COLUMN {name} {sql_type}")
        branch_columns.add(name.lower())

    _ensure_branch_column("source_type", "TEXT")
    _ensure_branch_column("source_key", "TEXT")
    _ensure_branch_column("source_payload_json", "TEXT")
    _ensure_branch_column("work_class", "TEXT")
    _ensure_branch_column("actionability", "TEXT")
    _ensure_branch_column("resolution_state", "TEXT")
    _ensure_branch_column("last_seen_at", "TEXT")
    _ensure_branch_column("evidence_count", "INTEGER NOT NULL DEFAULT 0")

    task_columns = {
        str(row[1]).strip().lower()
        for row in connection.execute("PRAGMA table_info(work_tree_tasks)")
    }
    if "meta_json" not in task_columns:
        connection.execute("ALTER TABLE work_tree_tasks ADD COLUMN meta_json TEXT NOT NULL DEFAULT '{}'" )

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
                    source_type=str(row["source_type"]) if row["source_type"] is not None else None,
                    source_key=str(row["source_key"]) if row["source_key"] is not None else None,
                    source_payload=_json_object_dict(row["source_payload_json"]),
                    work_class=str(row["work_class"]) if row["work_class"] is not None else None,
                    actionability=str(row["actionability"]) if row["actionability"] is not None else None,
                    resolution_state=str(row["resolution_state"]) if row["resolution_state"] is not None else None,
                    last_seen_at=_parse_dt(str(row["last_seen_at"])) if row["last_seen_at"] is not None else None,
                    evidence_count=int(row["evidence_count"] if row["evidence_count"] is not None else 0),
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
                    meta=_json_object_dict(row["meta_json"]),
                )
            except Exception:
                continue
            _TASKS[task.task_id] = task


def reload_persisted_state() -> bool:
    try:
        _load_persisted_state()
        return True
    except Exception as exc:
        _append_db_guard("reload_failed", str(exc))
        return False


def _set_db_path(db_path: str | Path) -> None:
    global _DB_PATH
    global _DB_REQUESTED_PATH
    global _DB_CONNECT_TARGET
    global _DB_CONNECT_USE_URI
    _DB_REQUESTED_PATH = Path(db_path)
    _DB_PATH = _DB_REQUESTED_PATH
    _DB_CONNECT_TARGET = str(_DB_PATH)
    _DB_CONNECT_USE_URI = False
    try:
        _ensure_db()
    except sqlite3.OperationalError as exc:
        if not _is_retryable_db_error(exc):
            raise
        _activate_memory_db_fallback(_DB_REQUESTED_PATH)
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
            required_tools_json, allowed_tools_json, preferred_tool, tool_state_json, notes,
            source_type, source_key, source_payload_json, work_class, actionability,
            resolution_state, last_seen_at, evidence_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            branch.source_type,
            branch.source_key,
            _json_dump(branch.source_payload),
            branch.work_class,
            branch.actionability,
            branch.resolution_state,
            _dt(branch.last_seen_at) if branch.last_seen_at is not None else None,
            int(branch.evidence_count),
        ),
    )


def _save_task_record(connection: sqlite3.Connection, task: Task) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO work_tree_tasks (
            task_id, branch_id, title, status, created_at, updated_at, priority, score, depends_on_json, meta_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            _json_dump(task.meta),
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
    if preferred and branch.tool_state.get(preferred, ToolStatus.READY) == ToolStatus.READY:
        return preferred
    declared = _branch_declared_tools(branch)
    for tool_name in declared:
        if branch.tool_state.get(tool_name, ToolStatus.READY) == ToolStatus.READY:
            return tool_name
    if preferred:
        return preferred
    for tool_name in declared:
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


def _refresh_branch_state(branch: Branch) -> bool:
    tasks = _branch_tasks(branch.branch_id)
    open_tasks = [task for task in tasks if task.status not in (TaskStatus.COMPLETE, TaskStatus.DROPPED)]
    active_tasks = [task for task in open_tasks if task.status == TaskStatus.ACTIVE]
    was_active = branch.status == BranchStatus.ACTIVE
    can_preserve_active = was_active and all(state == ToolStatus.READY for state in branch.tool_state.values())
    previous_open_stem_count = int(branch.open_stem_count)
    previous_blocked_by = list(branch.blocked_by)
    previous_status = branch.status
    previous_score = float(branch.score)
    branch.open_stem_count = len(open_tasks)
    branch.blocked_by = _blocked_dependencies(branch)
    if branch.status == BranchStatus.ARCHIVED:
        branch.score = recompute_branch_score(branch)
        _SCORES[branch.branch_id] = branch.score
        return (
            previous_open_stem_count != branch.open_stem_count
            or previous_blocked_by != branch.blocked_by
            or previous_status != branch.status
            or abs(previous_score - float(branch.score)) > 1e-9
        )
    if branch.blocked_by:
        branch.status = BranchStatus.BLOCKED
    elif branch.open_stem_count == 0:
        branch.status = BranchStatus.COMPLETE
    elif active_tasks or can_preserve_active:
        branch.status = BranchStatus.ACTIVE
    else:
        branch.status = BranchStatus.READY
    branch.score = recompute_branch_score(branch)
    _SCORES[branch.branch_id] = branch.score
    return (
        previous_open_stem_count != branch.open_stem_count
        or previous_blocked_by != branch.blocked_by
        or previous_status != branch.status
        or abs(previous_score - float(branch.score)) > 1e-9
    )


def _refresh_tree_state(tree_id: str, persist: bool = False) -> bool:
    tree = _TREES.get(tree_id)
    if tree is None:
        return False
    previous_status = tree.status
    branch_dirty = False
    branches = _tree_branches(tree_id)
    for branch in branches:
        branch_dirty = _refresh_branch_state(branch) or branch_dirty
    if tree.status != TreeStatus.ARCHIVED:
        tree.status = TreeStatus.COMPLETE if is_tree_complete(tree_id) else TreeStatus.ACTIVE
    dirty = branch_dirty or tree.status != previous_status
    if dirty:
        tree.updated_at = _now()
    if persist and dirty:
        _persist_tree_state(tree_id)
    return dirty


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


def create_task(branch_id: str, title: str, meta: dict[str, object] | None = None) -> Task:
    now = _now()
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    return Task(
        task_id=task_id,
        branch_id=branch_id,
        title=title,
        status=TaskStatus.OPEN,
        created_at=now,
        updated_at=now,
        meta=dict(meta or {}),
    )


def get_tree(tree_id: str) -> WorkTree | None:
    return _TREES.get(tree_id)


def list_trees() -> list[WorkTree]:
    return list(_TREES.values())


def get_branch(branch_id: str) -> Branch | None:
    return _BRANCHES.get(branch_id)


def list_tree_branches(tree_id: str) -> list[Branch]:
    return _tree_branches(tree_id)


def list_branch_tasks(branch_id: str) -> list[Task]:
    return _branch_tasks(branch_id)


def list_tree_tasks(tree_id: str) -> list[Task]:
    tasks = [task for task in _TASKS.values() if get_branch(task.branch_id) and str(get_branch(task.branch_id).tree_id) == str(tree_id)]
    tasks.sort(key=lambda task: (task.created_at, task.task_id))
    return tasks


def list_visual_trees(limit: int | None = None) -> list[dict]:
    reload_persisted_state()
    max_items = None if limit is None else max(1, int(limit))
    ranked_payloads: list[tuple[tuple[object, ...], dict]] = []
    for tree in _TREES.values():
        if tree.status == TreeStatus.ARCHIVED:
            continue
        payload = get_visual_tree_data(tree.tree_id)
        if payload is None:
            continue
        counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
        branch_counts = counts.get("branches") if isinstance(counts.get("branches"), dict) else {}
        branch_total = sum(int(value or 0) for value in branch_counts.values())
        node_count = len(list(payload.get("nodes") or []))
        open_tasks = int(counts.get("open_tasks") or 0)
        active_branch = bool(str(payload.get("active_branch_id") or "").strip())
        has_next_step = isinstance(payload.get("next_step"), dict) and bool(payload.get("next_step"))
        has_renderable_content = bool(branch_total or node_count or open_tasks or active_branch or has_next_step)
        ranked_payloads.append((
            (
                0 if active_branch or tree.status == TreeStatus.ACTIVE else 1,
                0 if has_renderable_content else 1,
                -open_tasks,
                -branch_total,
                -node_count,
                -tree.updated_at.timestamp(),
                str(tree.title or "").lower(),
            ),
            payload,
        ))
    ranked_payloads.sort(key=lambda item: item[0])
    payloads: list[dict] = []
    for _, payload in ranked_payloads:
        payloads.append(payload)
        if max_items is not None and len(payloads) >= max_items:
            break
    return payloads


def save_tree(tree: WorkTree) -> None:
    _TREES[tree.tree_id] = tree
    _ensure_db()
    with _db_transaction() as connection:
        _save_tree_record(connection, tree)


def archive_tree(tree_id: str, reason: str | None = None) -> bool:
    tree = get_tree(tree_id)
    if tree is None:
        return False
    now = _now()
    reason_text = str(reason or "").strip()
    dirty = False
    for branch in _tree_branches(tree_id):
        if branch.status != BranchStatus.ARCHIVED:
            branch.status = BranchStatus.ARCHIVED
            dirty = True
        if reason_text:
            existing_notes = str(branch.notes or "").strip()
            if reason_text not in existing_notes:
                branch.notes = f"{existing_notes}\n{reason_text}".strip() if existing_notes else reason_text
                dirty = True
        if str(branch.resolution_state or "").strip().lower() != "archived":
            branch.resolution_state = "archived"
            dirty = True
        branch.last_seen_at = now
        branch.updated_at = now
        branch.open_stem_count = 0
        branch.blocked_by = []
        branch.score = recompute_branch_score(branch)
        _SCORES[branch.branch_id] = branch.score
        for task in _branch_tasks(branch.branch_id):
            if task.status in {TaskStatus.COMPLETE, TaskStatus.DROPPED}:
                continue
            task.status = TaskStatus.DROPPED
            task.updated_at = now
            dirty = True
    meta = dict(tree.meta or {}) if isinstance(tree.meta, dict) else {}
    if reason_text:
        if str(meta.get("archive_reason") or "").strip() != reason_text:
            meta["archive_reason"] = reason_text
            dirty = True
    archived_at = _dt(now)
    if str(meta.get("archived_at") or "").strip() != archived_at:
        meta["archived_at"] = archived_at
        dirty = True
    if tree.status != TreeStatus.ARCHIVED:
        tree.status = TreeStatus.ARCHIVED
        dirty = True
    tree.meta = meta
    tree.updated_at = now
    _persist_tree_state(tree_id)
    return dirty


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

    _refresh_tree_state(tree_id, persist=False)
    candidates: list[Branch] = []
    for branch in _tree_branches(tree_id):
        if is_branch_ready(branch.branch_id) and branch.open_stem_count > 0:
            candidates.append(branch)

    if not candidates:
        previous_status = tree.status
        tree.status = TreeStatus.COMPLETE if is_tree_complete(tree_id) else TreeStatus.ACTIVE
        if tree.status != previous_status:
            tree.updated_at = _now()
            _persist_tree_state(tree_id)
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
    _persist_tree_state(tree_id)
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


def add_task_to_branch(branch_id: str, title: str, meta: dict[str, object] | None = None) -> Task:
    branch = _BRANCHES.get(branch_id)
    if branch is None:
        raise ValueError(f"Branch {branch_id} not found")
    task = create_task(branch_id, title, meta=meta)
    _TASKS[task.task_id] = task
    branch.updated_at = task.updated_at
    _refresh_tree_state(branch.tree_id, persist=True)
    return task


def touch_branch(branch_id: str) -> None:
    branch = _BRANCHES.get(branch_id)
    if branch is None:
        raise ValueError(f"Branch {branch_id} not found")
    branch.updated_at = _now()
    _refresh_tree_state(branch.tree_id, persist=True)


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
    _refresh_tree_state(branch.tree_id, persist=False)
    _persist_tree_state(branch.tree_id)


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


def set_tree_policy(tree_id: str, allowed_tools: list[str] | None = None, require_explicit_allow: bool = True) -> None:
    set_tree_execution_policy(
        tree_id,
        allowed_tools=allowed_tools,
        require_explicit_allow=require_explicit_allow,
    )


def is_tooling_ready(branch_id: str) -> bool:
    branch = _BRANCHES.get(branch_id)
    if branch is None:
        return False
    if not branch.required_tools:
        return True
    for tool in branch.required_tools:
        state = branch.tool_state.get(tool, ToolStatus.READY)
        if state == ToolStatus.BLOCKED:
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


def _extract_read_path_from_task_title(title: str) -> str:
    raw = str(title or "").strip()
    if not raw:
        return ""
    # Common pattern: "read <path> <section/details>"
    normalized = raw.replace("\\", "/")
    tokens = [token.strip(" ,;:.\"'()[]{}") for token in normalized.split() if token.strip()]
    for token in tokens:
        candidate = token
        if "/" in candidate:
            candidate = candidate.split("/")[-1]
        if "." not in candidate:
            continue
        resolved = (Path(__file__).resolve().parent / candidate).resolve()
        if resolved.exists() and resolved.is_file():
            return candidate
    return ""


def _extract_ls_path_from_task_title(title: str) -> str:
    raw = str(title or "").strip()
    if not raw:
        return ""
    normalized = raw.lower()
    if " log" in f" {normalized}" or "logs" in normalized:
        runtime_dir = Path(__file__).resolve().parent / "runtime"
        if runtime_dir.exists() and runtime_dir.is_dir():
            return "runtime"
    if "runtime" in normalized:
        runtime_dir = Path(__file__).resolve().parent / "runtime"
        if runtime_dir.exists() and runtime_dir.is_dir():
            return "runtime"
    return ""


def _extract_test_symbol_from_task_title(title: str) -> str:
    raw = str(title or "").strip()
    if not raw:
        return ""
    normalized = raw.replace("\\", "/")
    tokens = [token.strip(" ,;:.\"'()[]{}") for token in normalized.split() if token.strip()]
    for token in tokens:
        candidate = str(token or "").strip()
        if not candidate:
            continue
        if candidate.lower().startswith("test_"):
            return candidate
    return ""


def _extract_find_keyword_from_task_title(title: str) -> str:
    test_symbol = _extract_test_symbol_from_task_title(title)
    if test_symbol:
        return test_symbol
    raw = str(title or "").strip()
    if not raw:
        return ""
    normalized = raw.replace("\\", "/")
    tokens = [token.strip(" ,;:.\"'()[]{}") for token in normalized.split() if token.strip()]
    for token in tokens:
        candidate = str(token or "").strip()
        if not candidate:
            continue
        low = candidate.lower()
        if low in {"inspect", "run", "or", "and", "confirm", "whether", "verify", "the", "is", "still", "active", "in"}:
            continue
        if low in {"work-tree", "work_tree", "worktree"}:
            return "work_tree"
        if "_" in candidate or "-" in candidate:
            return candidate.replace("-", "_")
    for token in tokens:
        low = str(token or "").strip().lower()
        if low in {"metadata", "evidence", "counter", "branch", "symbol", "reference"}:
            return low
    return ""


def _extract_patch_preview_name(task: Task) -> str:
    task_meta = dict(task.meta or {}) if isinstance(task.meta, dict) else {}
    for key in ("patch_preview", "preview", "preview_name"):
        value = str(task_meta.get(key) or "").strip()
        if value:
            return value
    raw = str(task.title or "").strip()
    if not raw:
        return ""
    tokens = [token.strip(" ,;:.\"'()[]{}") for token in raw.split() if token.strip()]
    for token in tokens:
        candidate = str(token or "").strip()
        if candidate.lower().startswith("preview") and candidate.lower().endswith(".txt"):
            return candidate
    return ""


def _extract_generated_session_file(task: Task) -> str:
    task_meta = dict(task.meta or {}) if isinstance(task.meta, dict) else {}
    for key in ("session_file", "generated_session_file", "file"):
        value = str(task_meta.get(key) or "").strip()
        if value:
            return value
    raw = str(task.title or "").strip()
    if not raw:
        return ""
    tokens = [token.strip(" ,;:.\"'()[]{}") for token in raw.split() if token.strip()]
    for token in tokens:
        candidate = str(token or "").strip()
        if candidate.lower().endswith(".json"):
            return candidate
    return ""


def _tool_args_for_task(tool_name: str, task: Task) -> list[str]:
    task_meta = dict(task.meta or {}) if isinstance(task.meta, dict) else {}
    target_meta = task_meta.get("target") if isinstance(task_meta.get("target"), dict) else None
    title = str(task.title or "").strip()
    if target_meta is not None:
        return [
            _json_dump(
                {
                    "task_id": task.task_id,
                    "task_title": task.title,
                    "target": dict(target_meta),
                    "scope": str(task_meta.get("scope") or ""),
                    "verification": dict(task_meta.get("verification") or {}) if isinstance(task_meta.get("verification"), dict) else {},
                }
            )
        ]
    if tool_name in {"patch_preview_apply", "patch_preview_approve"}:
        preview_name = _extract_patch_preview_name(task)
        if preview_name:
            return [preview_name]
    if tool_name == "generated_queue_run":
        session_file = _extract_generated_session_file(task)
        if session_file:
            return [session_file]
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
    if tool_name == "ls":
        resolved_dir = _extract_ls_path_from_task_title(title)
        if resolved_dir:
            return [resolved_dir]
    if tool_name == "find":
        find_keyword = _extract_find_keyword_from_task_title(title)
        if find_keyword:
            return [find_keyword]
    if tool_name == "read":
        resolved_path = _extract_read_path_from_task_title(title)
        if resolved_path:
            return [resolved_path]
    return [title] if title else []


def _scoped_task_target(task: Task) -> dict[str, object]:
    if not isinstance(task.meta, dict):
        return {}
    target = task.meta.get("target")
    return dict(target) if isinstance(target, dict) else {}


def _is_scoped_stabilization_task(task: Task) -> bool:
    if not isinstance(task.meta, dict):
        return False
    return bool(_scoped_task_target(task))


def _scoped_target_valid(task: Task) -> tuple[bool, str]:
    target = _scoped_task_target(task)
    if not target:
        return False, "missing_target"
    file_name = str(target.get("file") or "").strip()
    function_name = str(target.get("function") or "").strip()
    block_name = str(target.get("block") or "").strip()
    start_line = target.get("start_line")
    end_line = target.get("end_line")
    if not file_name or not function_name or not block_name:
        return False, "missing_target_fields"
    if not isinstance(start_line, int) or not isinstance(end_line, int):
        return False, "invalid_target_lines"
    if start_line <= 0 or end_line < start_line:
        return False, "invalid_target_range"
    if str(task.meta.get("scope") or "").strip().lower() != "single_block_only":
        return False, "invalid_scope"
    return True, ""


def _is_invalid_tool_result(tool_name: str, result: object) -> tuple[bool, str]:
    """Detect no-op results that should not be marked as completed work."""
    if isinstance(result, dict):
        if not bool(result.get("ok", True)):
            return True, str(result.get("error") or "unknown error")
        return False, ""
    text = str(result or "").strip().lower()
    if not text:
        return True, "empty_result"
    invalid_prefixes = (
        "not a file:",
        "not a folder:",
        "file not found:",
        "not found:",
        "error:",
    )
    if any(text.startswith(prefix) for prefix in invalid_prefixes):
        return True, str(result or "invalid_result")
    return False, ""


def _restore_task_after_failed_execution(task: Task, branch: Branch) -> None:
    now = _now()
    task.status = TaskStatus.OPEN
    task.updated_at = now
    branch.updated_at = now


def _ordered_tool_suggestions_from_text(text: str) -> list[str]:
    low = str(text or "").strip().lower()
    if not low:
        return []
    suggestions: list[str] = []

    def _push(tool_name: str) -> None:
        if tool_name and tool_name in _KNOWN_TOOL_NAMES and tool_name not in suggestions:
            suggestions.append(tool_name)

    if "test_" in low:
        _push("find")
        _push("read")
    if any(token in low for token in ("metadata", "symbol reference", "missing symbol", "evidence counter", "branch metadata")):
        _push("find")
        _push("read")
    if any(token in low for token in ("health", "heartbeat", "pulse", "runtime", "diagnose", "status", "check")):
        _push("system_check")
        _push("health")
        _push("pulse")
    if any(token in low for token in ("queue", "backlog", "pending", "generated")):
        _push("queue_status")
    if any(token in low for token in ("generated session", "session drift", "parity drift", "generated queue")):
        _push("generated_queue_run")
    if any(token in low for token in ("rollback", "revert", "undo patch")):
        _push("patch_rollback")
    if "approve pending preview" in low or low.startswith("approve preview"):
        _push("patch_preview_approve")
    if "preview" in low and any(token in low for token in ("apply", "approved", "eligible")):
        _push("patch_preview_apply")
    if any(token in low for token in ("patch", "fix", "apply", "diff", "regression")):
        _push("patch_apply")
    if any(token in low for token in ("update", "upgrade", "install")):
        _push("update_now")
    if any(token in low for token in ("read", "inspect", "file", "log", "snapshot", "report")):
        _push("read")
    if any(token in low for token in ("list", "directory", "folder", "tree")):
        _push("ls")
    if any(token in low for token in ("find", "search file", "locate")):
        _push("find")
    if any(token in low for token in ("web", "research", "wikipedia", "stack", "sources")):
        _push("web_research")
        _push("web_search")
        _push("web_fetch")
    return suggestions


def assign_branch_tool_from_text(branch_id: str, task_text: str = "") -> str:
    branch = _BRANCHES.get(branch_id)
    if branch is None:
        return ""
    tree = _TREES.get(branch.tree_id)
    allowed = _tree_allowed_tools(tree)
    if not allowed:
        return ""

    merged_text = f"{branch.title} {str(task_text or '').strip()}".strip()
    suggestions = _ordered_tool_suggestions_from_text(merged_text)
    selected = next((tool for tool in suggestions if tool in allowed), "")
    if not selected:
        selected = str(allowed[0] or "").strip() if allowed else ""
    if not selected:
        return ""

    set_branch_tools(
        branch.branch_id,
        allowed_tools=[selected],
        preferred_tool=selected,
    )
    return selected


def _rebalance_branch_tool_for_task(branch: Branch, task: Task | None) -> str:
    if branch is None or task is None:
        return ""
    tree = _TREES.get(branch.tree_id)
    if tree is None:
        return ""
    # Preserve explicit branch tool declarations when a ready candidate already exists.
    if _branch_candidate_tool(branch):
        return ""
    allowed = _tree_allowed_tools(tree)
    if not allowed:
        return ""
    suggestions = _ordered_tool_suggestions_from_text(f"{branch.title} {str(task.title or '').strip()}".strip())
    selected = next((tool for tool in suggestions if tool in allowed), "")
    if not selected:
        return ""
    current = str(branch.preferred_tool or "").strip()
    if current == selected and list(branch.allowed_tools or []) == [selected]:
        return selected
    if selected == "find" and "read" in suggestions:
        branch.tool_state["read"] = ToolStatus.FAILED
    set_branch_tools(
        branch.branch_id,
        allowed_tools=[selected],
        preferred_tool=selected,
    )
    return selected


def list_autonomous_options(tree_id: str) -> list[dict]:
    tree = get_tree(tree_id)
    if tree is None:
        return []
    options: list[dict] = []
    for branch in _tree_branches(tree_id):
        if _next_open_task(branch.branch_id) is None:
            continue
        if not is_branch_ready(branch.branch_id):
            continue
        if not is_tooling_ready(branch.branch_id):
            continue
        recommended_tool = _branch_candidate_tool(branch)
        if not recommended_tool:
            continue
        allowed, _ = _tool_governance_status(tree, branch, recommended_tool)
        if not allowed:
            continue
        options.append(
            {
                "branch_id": branch.branch_id,
                "branch_title": branch.title,
                "recommended_tool": recommended_tool,
                "required_tools": list(branch.required_tools),
                "allowed_tools": list(branch.allowed_tools),
            }
        )
    return options


def _preview_next_open_branch(tree_id: str) -> Branch | None:
    tree = get_tree(tree_id)
    if tree is None:
        return None

    _refresh_tree_state(tree_id, persist=False)
    candidates: list[Branch] = []
    for branch in _tree_branches(tree_id):
        if is_branch_ready(branch.branch_id) and branch.open_stem_count > 0:
            candidates.append(branch)

    if not candidates:
        return None

    candidates.sort(
        key=lambda branch: (
            branch.depth,
            -branch.score,
            branch.created_at,
            branch.branch_id,
        )
    )
    return candidates[0]


def _preview_recommended_tool(tree: WorkTree | None, branch: Branch, task: Task | None) -> tuple[str, list[str], str]:
    recommended_tool = _branch_candidate_tool(branch)
    if recommended_tool:
        allowed, reason = _tool_governance_status(tree, branch, recommended_tool)
        return recommended_tool, list(branch.allowed_tools), "" if allowed else reason

    if task is None:
        return "", list(branch.allowed_tools), ""

    tree_allowed = _tree_allowed_tools(tree)
    suggestions = _ordered_tool_suggestions_from_text(f"{branch.title} {str(task.title or '').strip()}".strip())
    selected = next((tool for tool in suggestions if tool in tree_allowed), "")
    if not selected:
        return "", list(branch.allowed_tools), ""
    return selected, [selected], ""


def _preview_next_autonomous_step(tree_id: str) -> dict | None:
    tree = get_tree(tree_id)
    if tree is None:
        return None

    branch = _preview_next_open_branch(tree_id)
    if branch is None:
        return None

    if not is_tooling_ready(branch.branch_id):
        return {
            "action": "wait_for_tools",
            "branch_id": branch.branch_id,
            "missing_tools": [tool for tool in branch.required_tools if branch.tool_state.get(tool) != ToolStatus.READY],
        }

    current_task = _next_open_task(branch.branch_id)
    recommended_tool, allowed_tools, governance_reason = _preview_recommended_tool(tree, branch, current_task)
    if not recommended_tool:
        return {
            "action": "missing_tool_assignment",
            "branch_id": branch.branch_id,
            "branch_title": branch.title,
            "task_id": str(current_task.task_id) if current_task is not None else "",
            "branch_declared_tools": _branch_declared_tools(branch),
            "suggested_tools": _tree_allowed_tools(tree),
        }

    if governance_reason:
        return {
            "action": "governance_blocked",
            "branch_id": branch.branch_id,
            "branch_title": branch.title,
            "recommended_tool": recommended_tool,
            "reason": governance_reason,
            "branch_declared_tools": _branch_declared_tools(branch),
            "tree_allowed_tools": _tree_allowed_tools(tree),
        }

    return {
        "action": "execute",
        "branch_id": branch.branch_id,
        "branch_title": branch.title,
        "recommended_tool": recommended_tool,
        "required_tools": branch.required_tools,
        "allowed_tools": allowed_tools,
        "task_target": _scoped_task_target(current_task) if current_task is not None else {},
    }


def next_autonomous_step(tree_id: str, decide_next_step_fn: DecisionCallback | None = None) -> dict | None:
    tree = get_tree(tree_id)
    if tree is None:
        return None
    if decide_next_step_fn is not None:
        options = list_autonomous_options(tree_id)
        if options:
            try:
                decision = decide_next_step_fn(tree_id, options)
            except Exception as exc:
                return {"action": "decision_error", "error": str(exc)}
            if isinstance(decision, dict):
                selected_branch_id = str(decision.get("branch_id") or "").strip()
                selected_tool = str(decision.get("recommended_tool") or decision.get("tool") or "").strip()
                selected = next((opt for opt in options if str(opt.get("branch_id") or "") == selected_branch_id), None)
                if selected is None:
                    return {
                        "action": "invalid_decision",
                        "reason": "unknown_branch",
                        "branch_id": selected_branch_id,
                    }
                if selected_tool and selected_tool != str(selected.get("recommended_tool") or ""):
                    return {
                        "action": "invalid_decision",
                        "reason": "tool_mismatch",
                        "branch_id": selected_branch_id,
                        "recommended_tool": selected_tool,
                    }
                return {
                    "action": "execute",
                    "branch_id": str(selected.get("branch_id") or ""),
                    "branch_title": str(selected.get("branch_title") or ""),
                    "recommended_tool": str(selected.get("recommended_tool") or ""),
                    "required_tools": list(selected.get("required_tools") or []),
                    "allowed_tools": list(selected.get("allowed_tools") or []),
                }
    branch = next_open_branch(tree_id)
    if branch is None:
        return None
    if not is_tooling_ready(branch.branch_id):
        return {"action": "wait_for_tools", "branch_id": branch.branch_id, "missing_tools": [t for t in branch.required_tools if branch.tool_state.get(t) != ToolStatus.READY]}
    current_task = _next_open_task(branch.branch_id)
    if current_task is not None:
        _rebalance_branch_tool_for_task(branch, current_task)
    recommended_tool = _branch_candidate_tool(branch)
    if not recommended_tool:
        if current_task is not None:
            assigned_tool = assign_branch_tool_from_text(branch.branch_id, current_task.title)
            if assigned_tool:
                recommended_tool = _branch_candidate_tool(branch)
        if recommended_tool:
            allowed, reason = _tool_governance_status(tree, branch, recommended_tool)
            if not allowed:
                return _governance_payload(tree, branch, recommended_tool, reason)
            return {
                "action": "execute",
                "branch_id": branch.branch_id,
                "branch_title": branch.title,
                "recommended_tool": recommended_tool,
                "required_tools": branch.required_tools,
                "allowed_tools": branch.allowed_tools,
                "task_target": _scoped_task_target(current_task) if current_task is not None else {},
            }
        return {
            "action": "missing_tool_assignment",
            "branch_id": branch.branch_id,
            "branch_title": branch.title,
            "task_id": str(current_task.task_id) if current_task is not None else "",
            "branch_declared_tools": _branch_declared_tools(branch),
            "suggested_tools": _tree_allowed_tools(tree),
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
        "allowed_tools": branch.allowed_tools,
        "task_target": _scoped_task_target(current_task) if current_task is not None else {},
    }


def execute_autonomous_step(
    tree_id: str,
    execute_planned_action_fn: Callable[[str, list[str] | None], object],
    decide_next_step_fn: DecisionCallback | None = None,
) -> dict | None:
    step = next_autonomous_step(tree_id, decide_next_step_fn=decide_next_step_fn)
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

    if _is_scoped_stabilization_task(task):
        target_ok, target_reason = _scoped_target_valid(task)
        if not target_ok:
            return {
                "action": "scope_blocked",
                "branch_id": branch_id,
                "branch_title": branch.title,
                "task_id": task.task_id,
                "task_title": task.title,
                "reason": target_reason,
                "task_target": _scoped_task_target(task),
            }

    now = _now()
    task.status = TaskStatus.ACTIVE
    task.updated_at = now
    branch.updated_at = now
    branch.tool_state[tool_name] = ToolStatus.RUNNING
    _persist_tree_state(tree_id)

    tool_args = _tool_args_for_task(tool_name, task)
    result = execute_planned_action_fn(tool_name, tool_args)

    if _is_scoped_stabilization_task(task):
        target_meta = _scoped_task_target(task)
        if not isinstance(result, dict):
            branch.tool_state[tool_name] = ToolStatus.FAILED
            _restore_task_after_failed_execution(task, branch)
            _persist_tree_state(tree_id)
            return {
                "action": "verification_failed",
                "branch_id": branch_id,
                "branch_title": branch.title,
                "task_id": task.task_id,
                "task_title": task.title,
                "tool": tool_name,
                "tool_args": tool_args,
                "reason": "verification_result_required",
                "task_target": target_meta,
            }
        if not bool(result.get("scope_ok")):
            branch.tool_state[tool_name] = ToolStatus.FAILED
            _restore_task_after_failed_execution(task, branch)
            _persist_tree_state(tree_id)
            return {
                "action": "scope_blocked",
                "branch_id": branch_id,
                "branch_title": branch.title,
                "task_id": task.task_id,
                "task_title": task.title,
                "tool": tool_name,
                "tool_args": tool_args,
                "reason": str(result.get("reason") or "scope_expanded"),
                "task_target": target_meta,
            }
        if not bool(result.get("ok", False)):
            branch.tool_state[tool_name] = ToolStatus.FAILED
            _restore_task_after_failed_execution(task, branch)
            _persist_tree_state(tree_id)
            return {
                "action": "execution_failed",
                "branch_id": branch_id,
                "branch_title": branch.title,
                "task_id": task.task_id,
                "task_title": task.title,
                "tool": tool_name,
                "tool_args": tool_args,
                "reason": str(result.get("reason") or result.get("error") or "execution_failed"),
                "task_target": target_meta,
            }
        if not bool(result.get("verified", False)):
            branch.tool_state[tool_name] = ToolStatus.FAILED
            _restore_task_after_failed_execution(task, branch)
            _persist_tree_state(tree_id)
            return {
                "action": "verification_failed",
                "branch_id": branch_id,
                "branch_title": branch.title,
                "task_id": task.task_id,
                "task_title": task.title,
                "tool": tool_name,
                "tool_args": tool_args,
                "reason": str(result.get("reason") or "verification_failed"),
                "task_target": target_meta,
            }

    invalid_result, invalid_reason = _is_invalid_tool_result(tool_name, result)
    if invalid_result:
        branch.tool_state[tool_name] = ToolStatus.FAILED
        _restore_task_after_failed_execution(task, branch)
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
        "task_target": _scoped_task_target(task),
    }


def run_autonomous_loop(
    tree_id: str,
    max_steps: int = 100,
    execute_planned_action_fn: Callable[[str, list[str] | None], object] | None = None,
    decide_next_step_fn: DecisionCallback | None = None,
) -> list[dict]:
    history: list[dict] = []
    limit = max(1, int(max_steps or 0))
    for _ in range(limit):
        if execute_planned_action_fn is not None:
            step = execute_autonomous_step(tree_id, execute_planned_action_fn, decide_next_step_fn=decide_next_step_fn)
        else:
            step = next_autonomous_step(tree_id, decide_next_step_fn=decide_next_step_fn)
        if step is None:
            break
        action = str(step.get("action") or "").strip()
        history.append(dict(step))
        if execute_planned_action_fn is not None:
            if action != "executed":
                break
            if is_tree_complete(tree_id):
                break
            continue
        # No executor callback means planning-only mode; never mutate task state.
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
    task_counts: dict[str, int] = {status.value: 0 for status in TaskStatus}
    for branch in branches:
        branch_tasks = [t for t in _TASKS.values() if t.branch_id == branch.branch_id]
        tasks_open = sum(1 for t in branch_tasks if t.status not in (TaskStatus.COMPLETE, TaskStatus.DROPPED))
        for task in branch_tasks:
            task_counts[task.status.value] = task_counts.get(task.status.value, 0) + 1
        current_task = _next_open_task(branch.branch_id)
        display_tool = str(branch.preferred_tool or "").strip()
        if current_task is not None:
            suggestions = _ordered_tool_suggestions_from_text(f"{branch.title} {str(current_task.title or '').strip()}".strip())
            display_tool = next((tool for tool in suggestions if tool in _tree_allowed_tools(tree)), display_tool)
        nodes.append({
            "id": branch.branch_id,
            "title": branch.title,
            "status": branch.status.value,
            "parent_id": branch.parent_branch_id,
            "depth": branch.depth,
            "tasks_open": tasks_open,
            "tasks_total": len(branch_tasks),
            "preferred_tool": display_tool,
            "required_tools": list(branch.required_tools),
            "allowed_tools": list(branch.allowed_tools),
            "blocked_by": list(branch.blocked_by),
            "depends_on": list(branch.depends_on),
            "source_type": str(branch.source_type or ""),
            "source_key": str(branch.source_key or ""),
            "source_payload": dict(branch.source_payload or {}),
            "work_class": str(branch.work_class or ""),
            "actionability": str(branch.actionability or ""),
            "resolution_state": str(branch.resolution_state or ""),
            "last_seen_at": _dt(branch.last_seen_at) if branch.last_seen_at is not None else "",
            "evidence_count": int(branch.evidence_count or 0),
            "notes": str(branch.notes or ""),
            "current_task": {
                "task_id": current_task.task_id,
                "title": current_task.title,
                "status": current_task.status.value,
            } if current_task is not None else None,
        })
        for dep_id in branch.depends_on:
            dependency_edges.append({"from": dep_id, "to": branch.branch_id})
    tree_meta = dict(tree.meta or {}) if isinstance(tree.meta, dict) else {}
    active_branch = next((branch for branch in branches if branch.status == BranchStatus.ACTIVE), None)
    next_step = _preview_next_autonomous_step(tree_id)
    branch_counts: dict[str, int] = {status.value: 0 for status in BranchStatus}
    for branch in branches:
        branch_counts[branch.status.value] = branch_counts.get(branch.status.value, 0) + 1
    return {
        "tree_id": tree.tree_id,
        "title": tree.title,
        "status": tree.status.value,
        "root_branch_id": tree.root_branch_id,
        "updated_at": _dt(tree.updated_at),
        "kind": str(tree_meta.get("kind") or ""),
        "source": str(tree_meta.get("source") or ""),
        "work_identity_key": str(tree_meta.get("work_identity_key") or ""),
        "work_identity_label": str(tree_meta.get("work_identity_label") or ""),
        "counts": {
            "branches": branch_counts,
            "tasks": task_counts,
            "open_tasks": sum(
                1 for task in _TASKS.values()
                if _BRANCHES.get(task.branch_id) is not None
                and _BRANCHES[task.branch_id].tree_id == tree_id
                and task.status not in (TaskStatus.COMPLETE, TaskStatus.DROPPED)
            ),
        },
        "active_branch_id": active_branch.branch_id if active_branch is not None else "",
        "active_branch_title": active_branch.title if active_branch is not None else "",
        "next_step": dict(next_step) if isinstance(next_step, dict) else None,
        "nodes": nodes,
        "dependency_edges": dependency_edges,
    }


def inspect_tree(tree_id: str) -> dict | None:
    tree = get_tree(tree_id)
    if tree is None:
        return None
    _refresh_tree_state(tree_id, persist=False)
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
        display_tool = str(branch.preferred_tool or "").strip()
        display_allowed_tools = list(branch.allowed_tools)
        if current_task is not None:
            suggestions = _ordered_tool_suggestions_from_text(f"{branch.title} {str(current_task.title or '').strip()}".strip())
            selected_tool = next((tool for tool in suggestions if tool in _tree_allowed_tools(tree)), "")
            if selected_tool:
                display_tool = selected_tool
                display_allowed_tools = [selected_tool]
        return {
            "branch_id": branch.branch_id,
            "title": branch.title,
            "status": branch.status.value,
            "depends_on": list(branch.depends_on),
            "blocked_by": list(branch.blocked_by),
            "required_tools": list(branch.required_tools),
            "allowed_tools": display_allowed_tools,
            "preferred_tool": display_tool,
            "open_stem_count": int(branch.open_stem_count),
            "source_type": str(branch.source_type or ""),
            "source_key": str(branch.source_key or ""),
            "source_payload": dict(branch.source_payload or {}),
            "work_class": str(branch.work_class or ""),
            "actionability": str(branch.actionability or ""),
            "resolution_state": str(branch.resolution_state or ""),
            "last_seen_at": _dt(branch.last_seen_at) if branch.last_seen_at is not None else "",
            "evidence_count": int(branch.evidence_count or 0),
            "notes": str(branch.notes or ""),
            "current_task": {
                "task_id": current_task.task_id,
                "title": current_task.title,
                "status": current_task.status.value,
            } if current_task is not None else None,
        }

    active_branch = next((branch for branch in branches if branch.status == BranchStatus.ACTIVE), None)
    ready_branches = [_branch_summary(branch) for branch in branches if branch.status in {BranchStatus.READY, BranchStatus.ACTIVE}]
    blocked_branches = [_branch_summary(branch) for branch in branches if branch.status == BranchStatus.BLOCKED]
    step = _preview_next_autonomous_step(tree_id)
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


try:
    _ensure_db()
    _load_persisted_state()
except Exception as exc:
    _append_db_guard("startup_load_failed", str(exc))
    _clear_in_memory()
