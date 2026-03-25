from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ToolInvocationError(RuntimeError):
    pass


@dataclass
class ToolContext:
    user_id: str = ""
    session_id: str = ""
    policy: dict[str, Any] = field(default_factory=dict)
    allowed_root: str = ""
    is_admin: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "policy": self.policy,
            "allowed_root": self.allowed_root,
            "is_admin": self.is_admin,
            "extra": dict(self.extra),
        }


class NovaTool:
    name = "base"
    description = "Base tool"
    category = "general"
    safe = True
    requires_admin = False
    locality = "local"
    mutating = False
    scope = "user"

    def check_policy(self, args: dict[str, Any], context: ToolContext) -> tuple[bool, str]:
        if self.requires_admin and not bool(context.is_admin):
            return False, "admin_required"
        return True, ""

    def run(self, args: dict[str, Any], context: ToolContext) -> Any:
        raise NotImplementedError()

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "safe": bool(self.safe),
            "requires_admin": bool(self.requires_admin),
            "locality": str(self.locality or "local"),
            "mutating": bool(self.mutating),
            "read_only": not bool(self.mutating),
            "scope": str(self.scope or "user"),
        }
