from __future__ import annotations

def looks_like_find_command(text: str) -> bool:
    raw = str(text or "").strip()
    low = raw.lower()
    if not low.startswith("find "):
        return False
    if raw.endswith("?"):
        return False
    if any(mark in raw for mark in (",", ";", ":")):
        return False
    parts = raw.split()
    if len(parts) < 2 or len(parts) > 3:
        return False
    first_arg = str(parts[1] or "").strip().lower()
    if first_arg in {"a", "an", "the", "me", "more", "out"}:
        return False
    return True
