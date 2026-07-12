from __future__ import annotations


class PolicyControlService:
    """Own control-action orchestration for policy mutations outside the HTTP layer."""

    @staticmethod
    def policy_allow_action(payload: dict, *, policy_allow_domain_fn) -> tuple[bool, str, dict, str]:
        domain = str(payload.get("domain") or "").strip()
        msg = policy_allow_domain_fn(domain)
        return True, msg, {}, msg

    @staticmethod
    def policy_remove_action(payload: dict, *, policy_remove_domain_fn) -> tuple[bool, str, dict, str]:
        domain = str(payload.get("domain") or "").strip()
        msg = policy_remove_domain_fn(domain)
        return True, msg, {}, msg

    @staticmethod
    def web_mode_action(payload: dict, *, set_web_mode_fn) -> tuple[bool, str, dict, str]:
        mode = str(payload.get("mode") or "").strip()
        msg = set_web_mode_fn(mode)
        return True, msg, {}, msg

    @staticmethod
    def memory_scope_set_action(
        payload: dict,
        *,
        set_memory_scope_fn,
        control_policy_payload_fn,
        invalidate_control_status_cache_fn,
    ) -> tuple[bool, str, dict, str]:
        scope = str(payload.get("scope") or "").strip()
        msg = set_memory_scope_fn(scope)
        ok = not msg.lower().startswith("usage:")
        if ok:
            invalidate_control_status_cache_fn()
        return ok, msg, {"policy": control_policy_payload_fn()}, msg

    @staticmethod
    def mission_settings_action(
        payload: dict,
        *,
        set_mission_settings_fn,
        control_policy_payload_fn,
        invalidate_control_status_cache_fn,
    ) -> tuple[bool, str, dict, str]:
        enabled_value = payload.get("enabled")
        enabled = None
        if isinstance(enabled_value, bool):
            enabled = enabled_value
        elif isinstance(enabled_value, str):
            token = enabled_value.strip().lower()
            if token in {"true", "1", "yes", "on"}:
                enabled = True
            elif token in {"false", "0", "no", "off"}:
                enabled = False

        def _bool_field(name: str) -> bool | None:
            value = payload.get(name)
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                token = value.strip().lower()
                if token in {"true", "1", "yes", "on"}:
                    return True
                if token in {"false", "0", "no", "off"}:
                    return False
            return None

        msg = set_mission_settings_fn(
            enabled=enabled,
            mode=str(payload.get("mode") or "").strip(),
            objective=str(payload.get("objective") or "").strip(),
            release_stale_ready_is_pressure=_bool_field("release_stale_ready_is_pressure"),
            subconscious_triage_is_pressure=_bool_field("subconscious_triage_is_pressure"),
            generated_queue_backlog_is_pressure=_bool_field("generated_queue_backlog_is_pressure"),
        )
        ok = not msg.lower().startswith("usage:")
        if ok:
            invalidate_control_status_cache_fn()
        return ok, msg, {"policy": control_policy_payload_fn()}, msg

    @staticmethod
    def server_side_settings_action(
        payload: dict,
        *,
        set_server_side_settings_fn,
        control_policy_payload_fn,
        invalidate_control_status_cache_fn,
    ) -> tuple[bool, str, dict, str]:
        mode = str(payload.get("mode") or "").strip()
        frontdoor = str(payload.get("frontdoor") or "").strip()
        frontdoor_base_url = payload.get("frontdoor_base_url")
        if frontdoor_base_url is None:
            normalized_base_url = None
        else:
            normalized_base_url = str(frontdoor_base_url).strip()
        docker_enabled_value = payload.get("docker_enabled")
        docker_enabled = None
        if isinstance(docker_enabled_value, bool):
            docker_enabled = docker_enabled_value
        elif isinstance(docker_enabled_value, str):
            token = docker_enabled_value.strip().lower()
            if token in {"true", "1", "yes", "on"}:
                docker_enabled = True
            elif token in {"false", "0", "no", "off"}:
                docker_enabled = False

        msg = set_server_side_settings_fn(
            mode=mode,
            frontdoor=frontdoor,
            frontdoor_base_url=normalized_base_url,
            docker_enabled=docker_enabled,
        )
        ok = not msg.lower().startswith("usage:")
        if ok:
            invalidate_control_status_cache_fn()
        return ok, msg, {"policy": control_policy_payload_fn()}, msg

    @staticmethod
    def search_provider_action(
        payload: dict,
        *,
        set_search_provider_fn,
        control_policy_payload_fn,
        invalidate_control_status_cache_fn,
    ) -> tuple[bool, str, dict, str]:
        provider = str(payload.get("provider") or "").strip()
        msg = set_search_provider_fn(provider)
        ok = not msg.lower().startswith("usage:")
        if ok:
            invalidate_control_status_cache_fn()
        return ok, msg, {"policy": control_policy_payload_fn()}, msg

    @staticmethod
    def search_endpoint_set_action(
        payload: dict,
        *,
        set_search_endpoint_fn,
        control_policy_payload_fn,
        invalidate_control_status_cache_fn,
    ) -> tuple[bool, str, dict, str]:
        endpoint = str(payload.get("endpoint") or "").strip()
        msg = set_search_endpoint_fn(endpoint)
        ok = not msg.lower().startswith("usage:")
        if ok:
            invalidate_control_status_cache_fn()
        return ok, msg, {"policy": control_policy_payload_fn()}, msg

    @staticmethod
    def search_provider_priority_set_action(
        payload: dict,
        *,
        set_search_provider_priority_fn,
        control_policy_payload_fn,
        invalidate_control_status_cache_fn,
    ) -> tuple[bool, str, dict, str]:
        priority = payload.get("priority")
        value = [str(item or "").strip() for item in priority] if isinstance(priority, list) else str(priority or "").strip()
        msg = set_search_provider_priority_fn(value)
        ok = not msg.lower().startswith("usage:")
        if ok:
            invalidate_control_status_cache_fn()
        return ok, msg, {"policy": control_policy_payload_fn()}, msg

    @staticmethod
    def search_endpoint_probe_action(payload: dict, *, probe_search_endpoint_fn) -> tuple[bool, str, dict, str]:
        endpoint = str(payload.get("endpoint") or "").strip()
        probe = probe_search_endpoint_fn(endpoint)
        ok = bool(probe.get("ok"))
        message = str(probe.get("message") or ("search endpoint reachable" if ok else "search endpoint probe failed"))
        return ok, message, {"probe": probe}, message

    @staticmethod
    def search_provider_toggle_action(
        *,
        toggle_search_provider_fn,
        control_policy_payload_fn,
        invalidate_control_status_cache_fn,
    ) -> tuple[bool, str, dict, str]:
        msg = toggle_search_provider_fn()
        invalidate_control_status_cache_fn()
        return True, msg, {"policy": control_policy_payload_fn()}, msg


POLICY_CONTROL_SERVICE = PolicyControlService()