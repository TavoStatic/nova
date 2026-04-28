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
    "tool_web_research",
    "tool_web_gather",
    "tool_wikipedia_lookup",
    "tool_stackexchange_search",
    "tool_health",
)

_PLANNED_TOOL_ALIASES = {
    "tool_find": "find",
    "tool_ls": "ls",
    "tool_queue_status": "queue_status",
    "tool_phase2_audit": "phase2_audit",
    "tool_nova_pulse": "pulse",
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
    "tool_web_research": "web_research",
    "tool_web_gather": "web_gather",
    "tool_wikipedia_lookup": "wikipedia_lookup",
    "tool_stackexchange_search": "stackexchange_search",
    "tool_health": "health",
}


def _planned_tool_map(runtime_scope: Mapping[str, Any]) -> dict[str, Callable[..., object]]:
    tool_map: dict[str, Callable[..., object]] = {}
    for runtime_name in _PLANNED_TOOL_NAMES:
        value = runtime_scope.get(runtime_name)
        if not callable(value):
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
