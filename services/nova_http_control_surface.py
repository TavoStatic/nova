from __future__ import annotations

import os
from typing import Any, Mapping


class NovaHttpControlSurfaceService:
    """Own remaining HTTP control status/policy/action surface outside the transport shell."""

    @staticmethod
    def _runtime_value(runtime_scope: Mapping[str, Any], name: str) -> Any:
        return runtime_scope[name]

    @classmethod
    def runtime_process_note(cls) -> str:
        if os.name == "nt":
            return (
                "Windows note: the operator console reports logical service state. "
                "Launcher and child interpreter pairs can appear as duplicate python processes, "
                "but nova_http reporting collapses them to the leaf service process."
            )
        return "Process counts reflect the active service process state."

    @classmethod
    def control_status_payload_from_runtime(cls, runtime_scope: Mapping[str, Any]) -> dict:
        metrics_lock = cls._runtime_value(runtime_scope, "_METRICS_LOCK")
        with metrics_lock:
            requests_total = cls._runtime_value(runtime_scope, "_HTTP_REQUESTS_TOTAL")
            errors_total = cls._runtime_value(runtime_scope, "_HTTP_ERRORS_TOTAL")
        control_status_service = cls._runtime_value(runtime_scope, "CONTROL_STATUS_SERVICE")
        return control_status_service.runtime_status_payload(
            core_module=cls._runtime_value(runtime_scope, "nova_core"),
            session_turns=cls._runtime_value(runtime_scope, "SESSION_TURNS"),
            metrics_totals=(requests_total, errors_total),
            supplier_fns=cls._runtime_value(runtime_scope, "_control_status_suppliers")(),
        )

    @classmethod
    def control_status_surfaces_payload_from_runtime(cls, runtime_scope: Mapping[str, Any]) -> dict:
        metrics_lock = cls._runtime_value(runtime_scope, "_METRICS_LOCK")
        with metrics_lock:
            requests_total = cls._runtime_value(runtime_scope, "_HTTP_REQUESTS_TOTAL")
            errors_total = cls._runtime_value(runtime_scope, "_HTTP_ERRORS_TOTAL")
        control_status_service = cls._runtime_value(runtime_scope, "CONTROL_STATUS_SERVICE")
        return control_status_service.runtime_signal_ingestion_surfaces_payload(
            core_module=cls._runtime_value(runtime_scope, "nova_core"),
            session_turns=cls._runtime_value(runtime_scope, "SESSION_TURNS"),
            metrics_totals=(requests_total, errors_total),
            supplier_fns=cls._runtime_value(runtime_scope, "_control_status_suppliers")(),
        )

    @classmethod
    def control_policy_payload_from_runtime(cls, runtime_scope: Mapping[str, Any]) -> dict:
        nova_core = cls._runtime_value(runtime_scope, "nova_core")
        chat_auth_payload_fn = cls._runtime_value(runtime_scope, "_chat_auth_payload")
        policy = nova_core.load_policy()
        return {
            "ok": True,
            "tools_enabled": policy.get("tools_enabled") or {},
            "models": policy.get("models") or {},
            "memory": policy.get("memory") or {},
            "web": policy.get("web") or {},
            "server_side": policy.get("server_side") or {},
            "chat_auth": chat_auth_payload_fn(),
        }

    @classmethod
    def control_action_from_runtime(
        cls,
        action: str,
        payload: dict,
        runtime_scope: Mapping[str, Any],
    ) -> tuple[bool, str, dict]:
        # Temporal calendar actions stay direct — they do not go through the
        # dispatcher ladder (which requires a signature change).
        if action == "temporal_events_list":
            ok, msg, extra, _ = cls._runtime_value(runtime_scope, "_temporal_events_list_action")(payload)
            return ok, msg, extra
        if action == "temporal_event_save":
            ok, msg, extra, _ = cls._runtime_value(runtime_scope, "_temporal_event_save_action")(payload)
            return ok, msg, extra
        if action == "temporal_event_delete":
            ok, msg, extra, _ = cls._runtime_value(runtime_scope, "_temporal_event_delete_action")(payload)
            return ok, msg, extra

        control_hooks = {
            **cls._runtime_value(runtime_scope, "HTTP_PIPELINE_CONTROL_SERVICE").action_hooks_from_runtime(runtime_scope),
            **cls._runtime_value(runtime_scope, "HTTP_GENERATED_WORK_SERVICE").action_hooks_from_runtime(runtime_scope),
            **cls._runtime_value(runtime_scope, "HTTP_POLICY_SEARCH_SERVICE").action_hooks_from_runtime(runtime_scope),
        }
        nova_core = cls._runtime_value(runtime_scope, "nova_core")
        return cls._runtime_value(runtime_scope, "NOVA_CONTROL_ACTION_DISPATCHER").dispatch_control_action_from_runtime(
            action,
            payload,
            patch_control_service=cls._runtime_value(runtime_scope, "PATCH_CONTROL_SERVICE"),
            updates_dir=nova_core.UPDATES_DIR,
            runtime_scope=runtime_scope,
            explicit_hooks=control_hooks,
        )


HTTP_CONTROL_SURFACE_SERVICE = NovaHttpControlSurfaceService()
