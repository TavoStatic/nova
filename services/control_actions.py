from __future__ import annotations


class ControlActionsService:
    """Own small control-action orchestration helpers outside the HTTP transport layer."""

    @staticmethod
    def refresh_status_action(*, control_status_payload_fn) -> tuple[bool, str, dict, str]:
        msg = "status_refreshed"
        return True, msg, control_status_payload_fn(), msg

    @staticmethod
    def device_location_update_action(
        payload: dict,
        *,
        set_runtime_device_location_fn,
        invalidate_control_status_cache_fn,
    ) -> tuple[bool, str, dict, str]:
        ok, msg, live_tracking = set_runtime_device_location_fn(payload)
        if ok:
            invalidate_control_status_cache_fn()
        return ok, msg, {"live_tracking": live_tracking}, msg

    @staticmethod
    def device_location_clear_action(
        *,
        clear_runtime_device_location_fn,
        invalidate_control_status_cache_fn,
    ) -> tuple[bool, str, dict, str]:
        live_tracking = clear_runtime_device_location_fn()
        invalidate_control_status_cache_fn()
        msg = "device_location_cleared"
        return True, msg, {"live_tracking": live_tracking}, msg

    @staticmethod
    def self_check_action(*, control_self_check_payload_fn) -> tuple[bool, str, dict, str]:
        data = control_self_check_payload_fn()
        ok = bool(data.get("ok"))
        msg = str(data.get("summary") or "self_check_completed")
        return ok, msg, data, msg


CONTROL_ACTIONS_SERVICE = ControlActionsService()