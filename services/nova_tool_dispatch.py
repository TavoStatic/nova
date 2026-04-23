from __future__ import annotations

from typing import Callable, Optional


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