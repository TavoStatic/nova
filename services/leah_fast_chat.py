from __future__ import annotations

from typing import Any


def leah_fast_chat_enabled(policy: dict[str, Any] | None, *, input_source: str) -> bool:
    if str(input_source or "").strip().lower() != "http":
        return False
    layers = (policy or {}).get("layers") if isinstance((policy or {}).get("layers"), dict) else {}
    leah = layers.get("leah") if isinstance(layers.get("leah"), dict) else {}
    return bool(leah.get("fast_chat"))


def load_leah_fast_chat_from_core(core) -> bool:
    try:
        load_policy = getattr(core, "load_policy", None)
        if not callable(load_policy):
            return False
        return leah_fast_chat_enabled(load_policy(), input_source="http")
    except Exception:
        return False