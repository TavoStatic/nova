from __future__ import annotations

import json
import re
from typing import Optional

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore[assignment]

_OLLAMA_BASE = "http://127.0.0.1:11434"

# Tools that are valid for system-internal work trees.
# Must be a strict subset of work_tree._KNOWN_TOOL_NAMES.
_SYSTEM_TOOL_NAMES = frozenset({
    "health",
    "system_check",
    "queue_status",
    "phase2_audit",
    "pulse",
    "read",
    "ls",
    "find",
    "patch_apply",
    "patch_rollback",
    "update_now",
})

_EXPLICIT_WORK_TREE_PHRASES = (
    "start a work tree",
    "create a work tree",
    "make a work tree",
    "open a work tree",
    "use a work tree",
    "track this in a work tree",
    "put this in a work tree",
    "create work tree",
    "start work tree",
    "build work tree",
    "work tree for",
)

_SYSTEM_NERVOUS_SYSTEM_CUES = (
    "runtime",
    "health",
    "system status",
    "heartbeat",
    "pulse",
    "queue",
    "backlog",
    "generated work",
    "subconscious",
    "pressure",
    "drift",
    "parity",
    "seam",
    "regression",
    "patch",
    "release",
    "assessment",
    "operator",
    "guard",
    "worker",
    "maintenance",
)

_CONTENT_ORIENTED_CUES = (
    "news",
    "wikipedia",
    "research",
    "attendance guidance",
    "district action items",
    "summarize ",
    "collect ",
    "write a blog",
)

_DECOMPOSE_SYSTEM = (
    "You are a system maintenance task decomposition engine for a local AI runtime called Nova. "
    "Nova's work tree is used ONLY for internal system health and maintenance tasks — "
    "NOT for user content research, web searches, or external data gathering. "
    "Break the given system maintenance task into 2 to 4 sequential steps. "
    "Each step is a concise action phrase of at most 60 characters describing a system check or repair action. "
    "For each step choose the single best tool from: "
    "health, system_check, pulse, queue_status, read, ls, patch_apply, patch_rollback, update_now. "
    "Reply ONLY with a JSON array — no markdown, no prose, no code fences. "
    'Example: [{"title":"check runtime pulse","tool":"pulse"},{"title":"verify Ollama model availability","tool":"health"}]'
)


class WorkTreeSeedingService:
    """Own initial work-tree branch seeding outside HTTP transport glue."""

    @staticmethod
    def _llm_decompose(task_text: str, *, nova_core_module=None) -> Optional[list[dict]]:
        """Ask Ollama to decompose *task_text* into step dicts {title, tool}.

        Returns a list of 2-4 dicts on success, or None so callers fall back to
        the rule-based splitter.
        """
        if _requests is None:
            return None
        try:
            model: str = "llama3"
            if nova_core_module is not None:
                try:
                    model = nova_core_module.chat_model()
                except Exception:
                    pass

            payload = {
                "model": model,
                "stream": False,
                "options": {"temperature": 0.05, "top_p": 0.9},
                "messages": [
                    {"role": "system", "content": _DECOMPOSE_SYSTEM},
                    {"role": "user", "content": f'Task: "{task_text[:400]}"'},
                ],
            }
            r = _requests.post(
                f"{_OLLAMA_BASE}/api/chat",
                json=payload,
                timeout=12.0,
            )
            r.raise_for_status()
            raw = r.json().get("message", {}).get("content", "").strip()
            # Strip any accidental markdown fences
            raw = re.sub(r"^```[a-z]*\s*", "", raw).rstrip("`").strip()
            steps = json.loads(raw)
            if not isinstance(steps, list):
                return None
            validated: list[dict] = []
            for item in steps:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                # Reject non-system tools silently — the seeding layer will
                # infer the correct system tool from the step text instead.
                raw_tool = str(item.get("tool") or "").strip().lower()
                tool = raw_tool if raw_tool in _SYSTEM_TOOL_NAMES else ""
                if not title:
                    continue
                if len(title) > 80:
                    title = title[:77].rstrip() + "..."
                validated.append({"title": title, "tool": tool})
            if len(validated) < 2:
                return None
            return validated[:4]
        except Exception:
            return None

    @staticmethod
    def looks_like_explicit_work_tree_request(message: str) -> bool:
        low = str(message or "").strip().lower()
        return any(phrase in low for phrase in _EXPLICIT_WORK_TREE_PHRASES)

    @staticmethod
    def _looks_like_content_oriented_prompt(message: str) -> bool:
        low = str(message or "").strip().lower()
        if not low:
            return False
        return any(cue in low for cue in _CONTENT_ORIENTED_CUES)

    @staticmethod
    def _looks_like_system_nervous_system_prompt(message: str) -> bool:
        low = str(message or "").strip().lower()
        if not low:
            return False
        return any(cue in low for cue in _SYSTEM_NERVOUS_SYSTEM_CUES)

    @staticmethod
    def should_seed_system_work_tree(*, message: str, source: str = "", operator_mode: str = "") -> bool:
        """Shared activation rule for auto-seeding system work trees.

        Rules:
        1) explicit work-tree request always seeds
        2) clear content prompts do not seed
        3) internal maintenance cues seed
        4) operator macro / CLI flows default to seed unless content-oriented
        """
        if WorkTreeSeedingService.looks_like_explicit_work_tree_request(message):
            return True
        if WorkTreeSeedingService._looks_like_content_oriented_prompt(message):
            return False
        if WorkTreeSeedingService._looks_like_system_nervous_system_prompt(message):
            return True
        normalized_source = str(source or "").strip().lower()
        normalized_mode = str(operator_mode or "").strip().lower()
        if normalized_mode == "macro" or normalized_source == "cli":
            return True
        return False

    @staticmethod
    def _split_steps(message: str, *, limit: int = 4) -> list[str]:
        text = str(message or "").strip()
        if not text:
            return []
        normalized = re.sub(r"\s+", " ", text)
        parts = [
            re.sub(r"^[\-\*\d\.\)\s]+", "", item).strip(" .;:-")
            for item in re.split(r"(?:\n+|;|\s+and\s+then\s+|\s+then\s+|\s*->\s*)", normalized, flags=re.I)
        ]
        parts = [item for item in parts if len(item) >= 3]
        if not parts:
            return []
        deduped: list[str] = []
        seen: set[str] = set()
        for item in parts:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= max(1, int(limit)):
                break
        return deduped

    @staticmethod
    def _infer_tool(step_text: str) -> str:
        low = str(step_text or "").strip().lower()
        if not low:
            return "health"
        if any(token in low for token in ("pulse", "beat", "heartbeat")):
            return "pulse"
        if any(token in low for token in ("patch", "apply patch", "rollback")):
            return "patch_apply"
        if any(token in low for token in ("update", "install update")):
            return "update_now"
        if any(token in low for token in ("queue", "backlog", "pending", "generated", "work queue")):
            return "queue_status"
        if any(token in low for token in ("list files", "directory", "folder", "list dir", "ls ")):
            return "ls"
        if any(token in low for token in ("read", "inspect file", "open file", "scan", "log", "snapshot", "report")):
            return "read"
        if any(token in low for token in ("phase2", "audit", "safety envelope")):
            return "phase2_audit"
        if any(token in low for token in ("system", "runtime", "status", "check", "verify", "validate", "diagnose")):
            return "system_check"
        return "health"

    @staticmethod
    def _allowed_tools(preferred_tool: str) -> list[str]:
        tool = str(preferred_tool or "").strip().lower()
        if tool in {"read", "ls", "find"}:
            return ["read", "ls", "find"]
        if tool in {"pulse"}:
            return ["pulse", "health", "system_check"]
        if tool in {"queue_status"}:
            return ["queue_status", "system_check", "health"]
        if tool in {"patch_apply", "patch_rollback"}:
            return ["patch_apply", "patch_rollback"]
        if tool in {"update_now"}:
            return ["update_now", "patch_apply"]
        if tool in {"phase2_audit"}:
            return ["phase2_audit", "system_check"]
        # Default: general system health tools
        return ["health", "system_check", "pulse", "queue_status"]

    @staticmethod
    def _step_branch_title(index: int, step_text: str) -> str:
        compact = re.sub(r"\s+", " ", str(step_text or "").strip())
        if len(compact) > 58:
            compact = compact[:55].rstrip() + "..."
        return f"Step {index + 1}: {compact}" if compact else f"Step {index + 1}"

    def create_seeded_tree(self, *, work_tree_module, title_seed: str, source: str, user_id: str = "", nova_core_module=None) -> str:
        title_text = str(title_seed or "").strip() or "work tree task"
        title = title_text if len(title_text) <= 80 else title_text[:77].rstrip() + "..."
        source_label = str(source or "chat").strip().capitalize() or "Chat"

        tree = work_tree_module.initialize_tree(
            f"{source_label}: {title}",
            {"source": str(source or "chat"), "user_id": str(user_id or ""), "kind": "system"},
        )
        root_branch = work_tree_module._BRANCHES.get(tree.root_branch_id)
        if root_branch is None:
            return tree.tree_id

        # Try LLM decomposition first; fall back to rule-based splitter
        llm_steps = self._llm_decompose(title_text, nova_core_module=nova_core_module)

        previous_branch_id: str | None = None
        if llm_steps:
            for index, item in enumerate(llm_steps):
                step_text = item["title"]
                child = work_tree_module.add_branch_to_tree(
                    tree.tree_id,
                    self._step_branch_title(index, step_text),
                    "planned",
                    root_branch.branch_id,
                )
                work_tree_module.add_task_to_branch(child.branch_id, step_text)
                # Use LLM-provided tool only if it's a known system tool;
                # otherwise fall back to keyword inference.
                llm_tool = str(item.get("tool") or "").strip().lower()
                tool = llm_tool if llm_tool in _SYSTEM_TOOL_NAMES else self._infer_tool(step_text)
                work_tree_module.set_branch_tools(
                    child.branch_id,
                    allowed_tools=self._allowed_tools(tool),
                    preferred_tool=tool,
                )
                if previous_branch_id:
                    work_tree_module.add_dependency(child.branch_id, previous_branch_id)
                previous_branch_id = child.branch_id
        else:
            steps = self._split_steps(title_text)
            if not steps:
                steps = [title_text]

            for index, step_text in enumerate(steps):
                child = work_tree_module.add_branch_to_tree(
                    tree.tree_id,
                    self._step_branch_title(index, step_text),
                    "planned",
                    root_branch.branch_id,
                )
                work_tree_module.add_task_to_branch(child.branch_id, step_text)
                preferred = self._infer_tool(step_text)
                work_tree_module.set_branch_tools(
                    child.branch_id,
                    allowed_tools=self._allowed_tools(preferred),
                    preferred_tool=preferred,
                )
                if previous_branch_id:
                    work_tree_module.add_dependency(child.branch_id, previous_branch_id)
                previous_branch_id = child.branch_id

        return tree.tree_id


WORK_TREE_SEEDING_SERVICE = WorkTreeSeedingService()
