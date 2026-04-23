from __future__ import annotations

from typing import Callable, Optional


def is_brief_command_form(text: str, command: str, max_tokens: int) -> bool:
    raw = str(text or "").strip()
    low = raw.lower()
    if not low.startswith(f"{command} "):
        return False
    if raw.endswith("?"):
        return False
    tail = raw[len(command):].strip()
    if not tail:
        return False
    tokens = tail.split()
    if len(tokens) < 1 or len(tokens) + 1 > max_tokens:
        return False
    if any(mark in raw for mark in (",", ";", ":")):
        return False
    return True


def handle_keywords(
    text: str,
    *,
    tool_screen_fn: Callable[[], str],
    tool_camera_fn: Callable[[str], str],
    tool_ls_fn: Callable[[str], str],
    tool_read_fn: Callable[[str], str],
    tool_find_fn: Callable[[str, str], str],
    tool_health_fn: Callable[[], str],
    is_brief_command_form_fn: Callable[[str, str, int], bool],
) -> Optional[tuple[str, str, str]]:
    raw = str(text or "").strip()
    low = raw.lower()

    if low in {"screen", "look at my screen"}:
        return ("tool", "screen", tool_screen_fn())

    if low.startswith("camera"):
        prompt = text[len("camera"):].strip() or "what do you see"
        return ("tool", "camera", tool_camera_fn(prompt))

    if low == "ls" or is_brief_command_form_fn(raw, "ls", max_tokens=2):
        parts = raw.split(maxsplit=1)
        sub = parts[1] if len(parts) > 1 else ""
        return ("tool", "ls", tool_ls_fn(sub))

    if is_brief_command_form_fn(raw, "read", max_tokens=2):
        path = raw.split(maxsplit=1)[1]
        return ("tool", "read", tool_read_fn(path))

    if is_brief_command_form_fn(raw, "find", max_tokens=3):
        parts = raw.split(maxsplit=2)
        keyword = parts[1] if len(parts) > 1 else ""
        folder = parts[2] if len(parts) > 2 else ""
        return ("tool", "find", tool_find_fn(keyword, folder))

    if low in {"health", "status"}:
        return ("tool", "health", tool_health_fn())

    return None
