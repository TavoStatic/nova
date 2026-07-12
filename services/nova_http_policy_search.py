from __future__ import annotations

from typing import Any, Callable, Mapping

from services.policy_control import POLICY_CONTROL_SERVICE


class NovaHttpPolicySearchService:
    """Bind policy and search control actions to the HTTP runtime dependencies."""

    @staticmethod
    def _runtime_value(runtime_scope: Mapping[str, Any], name: str) -> Any:
        return runtime_scope[name]

    @classmethod
    def action_hooks_from_runtime(cls, runtime_scope: Mapping[str, Any]) -> dict[str, Callable[..., Any]]:
        service = runtime_scope.get("POLICY_CONTROL_SERVICE", POLICY_CONTROL_SERVICE)
        core = cls._runtime_value(runtime_scope, "nova_core")
        control_policy_payload_fn = cls._runtime_value(runtime_scope, "_control_policy_payload")
        invalidate_control_status_cache_fn = cls._runtime_value(runtime_scope, "_invalidate_control_status_cache")

        def _probe(endpoint: str) -> dict:
            return core.probe_search_endpoint(str(endpoint or core.get_search_endpoint() or "").strip())

        return {
            "policy_allow_action_fn": lambda payload: service.policy_allow_action(
                payload,
                policy_allow_domain_fn=core.policy_allow_domain,
            ),
            "policy_remove_action_fn": lambda payload: service.policy_remove_action(
                payload,
                policy_remove_domain_fn=core.policy_remove_domain,
            ),
            "web_mode_action_fn": lambda payload: service.web_mode_action(
                payload,
                set_web_mode_fn=core.set_web_mode,
            ),
            "memory_scope_set_action_fn": lambda payload: service.memory_scope_set_action(
                payload,
                set_memory_scope_fn=core.set_memory_scope,
                control_policy_payload_fn=control_policy_payload_fn,
                invalidate_control_status_cache_fn=invalidate_control_status_cache_fn,
            ),
            "server_side_settings_action_fn": lambda payload: service.server_side_settings_action(
                payload,
                set_server_side_settings_fn=core.set_server_side_settings,
                control_policy_payload_fn=control_policy_payload_fn,
                invalidate_control_status_cache_fn=invalidate_control_status_cache_fn,
            ),
            "mission_settings_action_fn": lambda payload: service.mission_settings_action(
                payload,
                set_mission_settings_fn=core.set_mission_settings,
                control_policy_payload_fn=control_policy_payload_fn,
                invalidate_control_status_cache_fn=invalidate_control_status_cache_fn,
            ),
            "search_provider_action_fn": lambda payload: service.search_provider_action(
                payload,
                set_search_provider_fn=core.set_search_provider,
                control_policy_payload_fn=control_policy_payload_fn,
                invalidate_control_status_cache_fn=invalidate_control_status_cache_fn,
            ),
            "search_provider_toggle_action_fn": lambda _payload: service.search_provider_toggle_action(
                toggle_search_provider_fn=core.toggle_search_provider,
                control_policy_payload_fn=control_policy_payload_fn,
                invalidate_control_status_cache_fn=invalidate_control_status_cache_fn,
            ),
            "search_endpoint_set_action_fn": lambda payload: service.search_endpoint_set_action(
                payload,
                set_search_endpoint_fn=core.set_search_endpoint,
                control_policy_payload_fn=control_policy_payload_fn,
                invalidate_control_status_cache_fn=invalidate_control_status_cache_fn,
            ),
            "search_provider_priority_set_action_fn": lambda payload: service.search_provider_priority_set_action(
                payload,
                set_search_provider_priority_fn=core.set_search_provider_priority,
                control_policy_payload_fn=control_policy_payload_fn,
                invalidate_control_status_cache_fn=invalidate_control_status_cache_fn,
            ),
            "search_endpoint_probe_action_fn": lambda payload: service.search_endpoint_probe_action(
                payload,
                probe_search_endpoint_fn=_probe,
            ),
        }


HTTP_POLICY_SEARCH_SERVICE = NovaHttpPolicySearchService()
