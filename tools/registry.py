from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .base_tool import NovaTool, ToolContext, ToolInvocationError
from .filesystem_tool import FileSystemTool
from .patch_tool import PatchTool
from .research_tool import ResearchTool
from .system_tool import SystemTool
from .vision_tool import VisionTool


BASE_DIR = Path(__file__).resolve().parent.parent
TOOL_MANIFEST_PATH = BASE_DIR / "TOOL_MANIFEST.json"
TOOL_EVENTS_PATH = BASE_DIR / "runtime" / "tool_events.jsonl"


def _load_manifest() -> dict[str, Any]:
    if not TOOL_MANIFEST_PATH.exists():
        return {}
    try:
        data = json.loads(TOOL_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _append_tool_event(payload: dict[str, Any]) -> None:
    try:
        TOOL_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TOOL_EVENTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


class ToolRegistry:
    def __init__(self, tools: list[NovaTool]):
        self._tools = {tool.name: tool for tool in tools}
        self._manifest = _load_manifest()

    def get(self, name: str) -> NovaTool | None:
        return self._tools.get(str(name or "").strip())

    def list_metadata(self) -> list[dict[str, Any]]:
        manifest_tools = self._manifest.get("tools") if isinstance(self._manifest.get("tools"), list) else []
        manifest_by_name = {str(item.get("name") or "").strip(): item for item in manifest_tools if isinstance(item, dict)}
        out = []
        for name in sorted(self._tools.keys()):
            tool = self._tools[name]
            meta = tool.metadata()
            manifest = manifest_by_name.get(name, {})
            if manifest:
                meta["manifest"] = manifest
            out.append(meta)
        return out

    def describe(self) -> str:
        lines = ["Available Nova tools:"]
        for meta in self.list_metadata():
            flags = []
            if meta.get("safe"):
                flags.append("safe")
            if meta.get("requires_admin"):
                flags.append("admin")
            flags.append(str(meta.get("locality") or "local"))
            flags.append("mutating" if meta.get("mutating") else "read-only")
            flags.append(str(meta.get("scope") or "user"))
            flag_text = f" [{' '.join(flags)}]" if flags else ""
            lines.append(f"- {meta['name']}: {meta['description']}{flag_text}")
        return "\n".join(lines)

    def run_tool(self, name: str, args: dict[str, Any], context: ToolContext) -> Any:
        tool = self.get(name)
        if not tool:
            raise ToolInvocationError("unknown_tool")

        started = time.time()
        ok, reason = tool.check_policy(args, context)
        meta = tool.metadata()
        if not ok:
            payload = {
                "event": "tool_invocation",
                "tool": tool.name,
                "user": context.user_id,
                "session": context.session_id,
                "status": "denied",
                "reason": reason,
                "safe": bool(meta.get("safe")),
                "requires_admin": bool(meta.get("requires_admin")),
                "locality": str(meta.get("locality") or "local"),
                "mutating": bool(meta.get("mutating")),
                "scope": str(meta.get("scope") or "user"),
                "args": sorted(list((args or {}).keys())),
                "ts": int(time.time()),
            }
            _append_tool_event(payload)
            raise ToolInvocationError(reason)

        try:
            result = tool.run(args or {}, context)
            payload = {
                "event": "tool_invocation",
                "tool": tool.name,
                "user": context.user_id,
                "session": context.session_id,
                "status": "ok",
                "safe": bool(meta.get("safe")),
                "requires_admin": bool(meta.get("requires_admin")),
                "locality": str(meta.get("locality") or "local"),
                "mutating": bool(meta.get("mutating")),
                "scope": str(meta.get("scope") or "user"),
                "args": sorted(list((args or {}).keys())),
                "duration_ms": int((time.time() - started) * 1000),
                "ts": int(time.time()),
            }
            _append_tool_event(payload)
            return result
        except Exception as e:
            payload = {
                "event": "tool_invocation",
                "tool": tool.name,
                "user": context.user_id,
                "session": context.session_id,
                "status": "error",
                "error": str(e),
                "safe": bool(meta.get("safe")),
                "requires_admin": bool(meta.get("requires_admin")),
                "locality": str(meta.get("locality") or "local"),
                "mutating": bool(meta.get("mutating")),
                "scope": str(meta.get("scope") or "user"),
                "args": sorted(list((args or {}).keys())),
                "duration_ms": int((time.time() - started) * 1000),
                "ts": int(time.time()),
            }
            _append_tool_event(payload)
            raise


def build_default_registry() -> ToolRegistry:
    return ToolRegistry([
        FileSystemTool(),
        PatchTool(),
        VisionTool(),
        ResearchTool(),
        SystemTool(),
    ])
