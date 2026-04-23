"""
ToolRegistryService - Manages tool registry and event logging.

This service encapsulates:
- Tool manifest loading and caching
- Tool invocation event logging (success, failure, denial)
- Tool metadata aggregation
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from tools import ToolRegistry, ToolContext, ToolInvocationError


@dataclass
class ToolInvocationEvent:
    """Represents a single tool invocation event."""
    event: str = "tool_invocation"
    tool: str = ""
    user: str = ""
    session: str = ""
    status: str = ""  # ok, denied, error
    reason: str = ""  # for denied status
    error: str = ""  # for error status
    safe: bool = False
    requires_admin: bool = False
    locality: str = "local"
    mutating: bool = False
    scope: str = "user"
    args: list[str] = field(default_factory=list)
    duration_ms: int = 0
    ts: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "event": self.event,
            "tool": self.tool,
            "user": self.user,
            "session": self.session,
            "status": self.status,
            "safe": self.safe,
            "requires_admin": self.requires_admin,
            "locality": self.locality,
            "mutating": self.mutating,
            "scope": self.scope,
            "args": self.args,
            "ts": self.ts,
        }
        if self.reason:
            result["reason"] = self.reason
        if self.error:
            result["error"] = self.error
        if self.duration_ms:
            result["duration_ms"] = self.duration_ms
        return result


class ToolRegistryService:
    """Service for managing tool registry and execution with event logging."""
    
    def __init__(self, registry: ToolRegistry, manifest_path: Path, events_log_path: Path):
        """
        Initialize the service.
        
        Args:
            registry: The underlying ToolRegistry instance
            manifest_path: Path to TOOL_MANIFEST.json
            events_log_path: Path to tool_events.jsonl for logging invocations
        """
        self.registry = registry
        self.manifest_path = manifest_path
        self.events_log_path = events_log_path
        self._manifest_cache: Optional[dict] = None
    
    def get_manifest(self) -> dict[str, Any]:
        """
        Load and cache the tool manifest.
        
        Returns:
            Tool manifest dictionary
        """
        if self._manifest_cache is not None:
            return self._manifest_cache
        
        if not self.manifest_path.exists():
            self._manifest_cache = {}
            return {}
        
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            self._manifest_cache = data if isinstance(data, dict) else {}
        except Exception:
            self._manifest_cache = {}
        
        return self._manifest_cache
    
    def invalidate_manifest_cache(self) -> None:
        """Invalidate the manifest cache (e.g., after manifest changes)."""
        self._manifest_cache = None
    
    def _append_event(self, event: ToolInvocationEvent) -> None:
        """
        Append a tool invocation event to the log.
        
        Args:
            event: The event to log
        """
        try:
            self.events_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.events_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=True) + "\n")
        except Exception:
            pass  # Silent failure to avoid disrupting tool execution
    
    def run_tool(self, name: str, args: dict[str, Any], context: ToolContext) -> Any:
        """
        Run a tool with policy checking and event logging.
        
        Args:
            name: Tool name
            args: Tool arguments
            context: Tool execution context
            
        Returns:
            Tool result
            
        Raises:
            ToolInvocationError: If tool is unknown, denied by policy, or fails
        """
        tool = self.registry.get(name)
        if not tool:
            raise ToolInvocationError("unknown_tool")
        
        started = time.time()
        ok, reason = tool.check_policy(args, context)
        meta = tool.metadata()
        
        if not ok:
            event = ToolInvocationEvent(
                tool=tool.name,
                user=context.user_id,
                session=context.session_id,
                status="denied",
                reason=reason,
                safe=bool(meta.get("safe")),
                requires_admin=bool(meta.get("requires_admin")),
                locality=str(meta.get("locality") or "local"),
                mutating=bool(meta.get("mutating")),
                scope=str(meta.get("scope") or "user"),
                args=sorted(list((args or {}).keys())),
                ts=int(time.time()),
            )
            self._append_event(event)
            raise ToolInvocationError(reason)
        
        try:
            result = tool.run(args or {}, context)
            event = ToolInvocationEvent(
                tool=tool.name,
                user=context.user_id,
                session=context.session_id,
                status="ok",
                safe=bool(meta.get("safe")),
                requires_admin=bool(meta.get("requires_admin")),
                locality=str(meta.get("locality") or "local"),
                mutating=bool(meta.get("mutating")),
                scope=str(meta.get("scope") or "user"),
                args=sorted(list((args or {}).keys())),
                duration_ms=int((time.time() - started) * 1000),
                ts=int(time.time()),
            )
            self._append_event(event)
            return result
        except Exception as e:
            event = ToolInvocationEvent(
                tool=tool.name,
                user=context.user_id,
                session=context.session_id,
                status="error",
                error=str(e),
                safe=bool(meta.get("safe")),
                requires_admin=bool(meta.get("requires_admin")),
                locality=str(meta.get("locality") or "local"),
                mutating=bool(meta.get("mutating")),
                scope=str(meta.get("scope") or "user"),
                args=sorted(list((args or {}).keys())),
                duration_ms=int((time.time() - started) * 1000),
                ts=int(time.time()),
            )
            self._append_event(event)
            raise
    
    def list_tools(self) -> list[dict[str, Any]]:
        """Get list of all available tools with metadata."""
        return self.registry.list_metadata()
    
    def describe_tools(self) -> str:
        """Get human-readable description of all available tools."""
        return self.registry.describe()
    
    def get_tool(self, name: str):
        """Get a specific tool by name."""
        return self.registry.get(name)
