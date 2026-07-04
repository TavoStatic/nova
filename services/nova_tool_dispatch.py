from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

from services.nova_runtime_hooks import resolve_runtime_hooks


_EXECUTE_PLANNED_ACTION_HOOKS = {
    "resolve_current_device_coords_fn": "resolve_current_device_coords",
    "tool_weather_fn": "tool_weather",
    "get_saved_location_text_fn": "get_saved_location_text",
    "coords_from_saved_location_fn": "_coords_from_saved_location",
    "need_confirmed_location_message_fn": "_need_confirmed_location_message",
    "set_location_coords_fn": "set_location_coords",
}

_PLANNED_TOOL_NAMES = (
    "tool_find",
    "tool_ls",
    "tool_queue_status",
    "tool_phase2_audit",
    "tool_nova_pulse",
    "tool_memory_bootstrap_judgment",
    "tool_memory_bootstrap_confirm",
    "tool_memory_identity_bootstrap",
    "tool_memory_hygiene",
    "tool_subconscious_review_judgment",
    "tool_source_root_judgment",
    "tool_pipeline",
    "tool_nova_self_status",
    "tool_core_health_brief",
    "tool_core_thinning",
    "tool_os_capability",
    "tool_release_promotion_judgment",
    "tool_release_validation_run",
    "tool_release_record_validation_outcome",
    "tool_release_rebuild_verify",
    "tool_installer_validation_run",
    "tool_patch_preview_approve",
    "patch_apply",
    "tool_patch_preview_apply",
    "patch_rollback",
    "tool_read",
    "tool_system_check",
    "tool_update_now",
    "tool_update_now_confirm",
    "tool_update_now_cancel",
    "tool_web_search",
    "tool_web_fetch",
    "tool_web_research",
    "tool_web_gather",
    "tool_wikipedia_lookup",
    "tool_stackexchange_search",
    "tool_health",
    "tool_screen",
    "tool_camera",
    "tool_temporal_review",
)

_PLANNED_TOOL_ALIASES = {
    "tool_find": "find",
    "tool_ls": "ls",
    "tool_queue_status": "queue_status",
    "tool_phase2_audit": "phase2_audit",
    "tool_nova_pulse": "pulse",
    "tool_memory_bootstrap_judgment": "memory_bootstrap_judgment",
    "tool_memory_bootstrap_confirm": "memory_bootstrap_confirm",
    "tool_memory_identity_bootstrap": "memory_identity_bootstrap",
    "tool_memory_hygiene": "memory_hygiene",
    "tool_subconscious_review_judgment": "subconscious_review_judgment",
    "tool_source_root_judgment": "source_root_judgment",
    "tool_pipeline": "pipeline",
    "tool_nova_self_status": "self_status",
    "tool_core_health_brief": "core_health",
    "tool_core_thinning": "core_thinning",
    "tool_os_capability": "os_capability",
    "tool_release_promotion_judgment": "release_promotion_judgment",
    "tool_release_validation_run": "release_validation_run",
    "tool_release_record_validation_outcome": "release_record_validation_outcome",
    "tool_release_rebuild_verify": "release_rebuild_verify",
    "tool_installer_validation_run": "installer_validation_run",
    "tool_patch_preview_approve": "patch_preview_approve",
    "patch_apply": "patch_apply",
    "tool_patch_preview_apply": "patch_preview_apply",
    "patch_rollback": "patch_rollback",
    "tool_read": "read",
    "tool_system_check": "system_check",
    "tool_update_now": "update_now",
    "tool_update_now_confirm": "update_now_confirm",
    "tool_update_now_cancel": "update_now_cancel",
    "tool_web_search": "web_search",
    "tool_web_fetch": "web_fetch",
    "tool_web_research": "web_research",
    "tool_web_gather": "web_gather",
    "tool_wikipedia_lookup": "wikipedia_lookup",
    "tool_stackexchange_search": "stackexchange_search",
    "tool_health": "health",
    "tool_screen": "screen",
    "tool_camera": "camera",
    "tool_temporal_review": "temporal_review",
}

_OPTIONAL_PLANNED_TOOL_DEFAULTS = {
    "tool_pipeline": lambda *args: {"ok": False, "error": "Pipeline tool is not available in this runtime scope."},
    "tool_screen": lambda *args: {"ok": False, "error": "Screen tool is not available in this runtime scope."},
    "tool_camera": lambda *args: {"ok": False, "error": "Camera tool is not available in this runtime scope."},
}


def _planned_tool_map(runtime_scope: Mapping[str, Any]) -> dict[str, Callable[..., object]]:
    tool_map: dict[str, Callable[..., object]] = {}
    for runtime_name in _PLANNED_TOOL_NAMES:
        value = runtime_scope.get(runtime_name)
        if not callable(value):
            fallback = _OPTIONAL_PLANNED_TOOL_DEFAULTS.get(runtime_name)
            if callable(fallback):
                tool_map[_PLANNED_TOOL_ALIASES[runtime_name]] = fallback
                continue
            raise TypeError(f"{runtime_name} must be callable")
        tool_map[_PLANNED_TOOL_ALIASES[runtime_name]] = value
    return tool_map


def execute_planned_action(
    tool: str,
    args=None,
    *,
    resolve_current_device_coords_fn: Callable[[], Optional[tuple[float, float]]],
    tool_weather_fn: Callable[[str], str],
    get_saved_location_text_fn: Callable[[], str],
    coords_from_saved_location_fn: Callable[[], Optional[tuple[float, float]]],
    need_confirmed_location_message_fn: Callable[[], str],
    set_location_coords_fn: Callable[[str], str],
    tool_map: dict[str, Callable[..., object]],
) -> object:
    tool_name = str(tool or "").strip()
    tool_args = list(args) if isinstance(args, (list, tuple)) else ([] if args in {None, ""} else [args])

    if tool_name == "weather_current_location":
        current_coords = resolve_current_device_coords_fn()
        if current_coords:
            return str(tool_weather_fn(f"{current_coords[0]},{current_coords[1]}") or "")

        saved_location = str(get_saved_location_text_fn() or "").strip()
        if saved_location:
            return str(tool_weather_fn(saved_location) or "")

        coords = coords_from_saved_location_fn()
        if coords:
            return str(tool_weather_fn(f"{coords[0]},{coords[1]}") or "")

        return need_confirmed_location_message_fn()

    if tool_name == "weather_location":
        location_value = str(tool_args[0] if tool_args else "").strip()
        return str(tool_weather_fn(location_value) or "")

    if tool_name == "location_coords":
        location_value = str(tool_args[0] if tool_args else "").strip()
        if not location_value:
            # No args — return the current device GPS fix
            coords = resolve_current_device_coords_fn()
            if coords:
                return f"Current device location: {coords[0]},{coords[1]}"
            return "Location fix is not available right now. No GPS fix or saved coordinates found."
        return set_location_coords_fn(location_value)

    fn = tool_map.get(tool_name)
    if not fn:
        return {"ok": False, "error": f"Unknown planned tool: {tool_name}"}

    try:
        return fn(*tool_args) if tool_args else fn()
    except Exception as exc:
        return {"ok": False, "error": f"Tool error: {exc}"}


def execute_planned_action_from_runtime(
    tool: str,
    args=None,
    *,
    runtime_scope: Optional[Mapping[str, Any]] = None,
    **explicit_hooks,
) -> object:
    hooks = resolve_runtime_hooks(
        _EXECUTE_PLANNED_ACTION_HOOKS,
        explicit_hooks=explicit_hooks,
        runtime_scope=runtime_scope,
    )
    if "tool_map" in explicit_hooks:
        hooks["tool_map"] = explicit_hooks["tool_map"]
    elif runtime_scope is not None:
        hooks["tool_map"] = _planned_tool_map(runtime_scope)
    else:
        raise TypeError("tool_map is required")
    return execute_planned_action(tool, args, **hooks)
