from __future__ import annotations

from typing import Any, Mapping


class NovaHttpBackpackControlService:
    """Bind backpack control service to the HTTP runtime (same pattern as pipelines)."""

    @staticmethod
    def _runtime_value(runtime_scope: Mapping[str, Any], name: str) -> Any:
        return runtime_scope[name]

    @classmethod
    def payload_from_runtime(
        cls,
        runtime_scope: Mapping[str, Any],
        *,
        selected_backpack_id: str = "",
        role: str = "account_admin",
    ) -> dict[str, Any]:
        from services.control_backpacks import CONTROL_BACKPACKS_SERVICE

        return CONTROL_BACKPACKS_SERVICE.payload(
            selected_backpack_id=selected_backpack_id,
            role=role,
        )

    @classmethod
    def handle_action_from_runtime(
        cls,
        action: str,
        payload: dict,
        runtime_scope: Mapping[str, Any],
    ) -> tuple[bool, str, dict]:
        from services.control_backpacks import CONTROL_BACKPACKS_SERVICE

        return CONTROL_BACKPACKS_SERVICE.handle_action(action, payload or {})


HTTP_BACKPACK_CONTROL_SERVICE = NovaHttpBackpackControlService()
