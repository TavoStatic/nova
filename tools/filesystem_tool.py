from __future__ import annotations

import os
from pathlib import Path

from agent import load_allowed_root

from .base_tool import NovaTool, ToolContext, ToolInvocationError


class FileSystemTool(NovaTool):
    name = "filesystem"
    description = "Basic filesystem operations inside Nova's allowed root"
    category = "filesystem"
    safe = True
    requires_admin = False
    locality = "local"
    mutating = False
    scope = "user"

    def check_policy(self, args: dict, context: ToolContext) -> tuple[bool, str]:
        ok, reason = super().check_policy(args, context)
        if not ok:
            return ok, reason
        tools = (context.policy.get("tools_enabled") or {}) if isinstance(context.policy, dict) else {}
        if not bool(tools.get("files", False)):
            return False, "files_tool_disabled"
        return True, ""

    def _allowed_root(self, context: ToolContext) -> Path:
        raw = (context.allowed_root or "").strip()
        if raw:
            return Path(raw).resolve()
        return load_allowed_root().resolve()

    def _safe_path(self, user_path: str, context: ToolContext) -> Path:
        root = self._allowed_root(context)
        p = Path(user_path or "")
        if not p.is_absolute():
            p = (root / p)
        p = p.resolve()
        try:
            p.relative_to(root)
        except Exception as e:
            raise ToolInvocationError(f"Denied: path is outside allowed root: {root}") from e
        return p

    def _cmd_ls(self, args: dict, context: ToolContext) -> str:
        target = self._allowed_root(context)
        if args.get("path"):
            target = self._safe_path(str(args.get("path") or ""), context)
        if not target.exists() or not target.is_dir():
            raise ToolInvocationError(f"Not a folder: {target}")
        lines = []
        for p in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
            kind = "DIR " if p.is_dir() else "FILE"
            lines.append(f"{kind}  {p.name}")
        return "\n".join(lines)

    def _cmd_read(self, args: dict, context: ToolContext) -> str:
        path = str(args.get("path") or "").strip()
        if not path:
            raise ToolInvocationError("path_required")
        target = self._safe_path(path, context)
        if not target.exists() or not target.is_file():
            raise ToolInvocationError(f"Not a file: {target}")
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            raise ToolInvocationError(f"Failed to read: {target}: {e}") from e

    def _cmd_find(self, args: dict, context: ToolContext) -> str:
        keyword = str(args.get("keyword") or "").strip().lower()
        if not keyword:
            raise ToolInvocationError("keyword_required")
        start = self._allowed_root(context)
        if args.get("path"):
            start = self._safe_path(str(args.get("path") or ""), context)
        if not start.exists() or not start.is_dir():
            raise ToolInvocationError(f"Not a folder: {start}")
        exts = {".txt", ".md", ".log", ".json", ".xml", ".csv", ".ini", ".conf", ".php", ".js", ".ts", ".css", ".html", ".htm", ".py", ".sql"}
        hits = []
        for root, _dirs, files in os.walk(start):
            for name in files:
                p = Path(root) / name
                if p.suffix.lower() not in exts:
                    continue
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if keyword in content.lower():
                    hits.append(str(p))
        return "No matches found." if not hits else "\n".join(hits[:200])

    def run(self, args: dict, context: ToolContext) -> str:
        action = str(args.get("action") or "").strip().lower()
        if action == "ls":
            return self._cmd_ls(args, context)
        if action == "read":
            return self._cmd_read(args, context)
        if action == "find":
            return self._cmd_find(args, context)
        raise ToolInvocationError("unknown_filesystem_action")