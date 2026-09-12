"""Type-casting and string normalization utilities for Nova services.

Consolidates defensive JSON/type-casting helpers (_as_dict, _as_list, _as_int,
_as_float, _as_bool, _as_bool_or_none, _text) across services into a single,
well-tested utility module.
"""

from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    """Convert value to a dict, or return empty dict if invalid."""
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    """Convert value to a list, or return empty list if invalid."""
    return list(value) if isinstance(value, list) else []


def _as_int(value: Any, default: int = 0) -> int:
    """Convert value to int, returning default on failure."""
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    """Convert value to float, returning default on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    """Convert value to boolean, with support for truthy string literals."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "ok", "ready", "running", "active"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _as_bool_or_none(value: Any) -> bool | None:
    """Convert value to boolean or None if ambiguous/missing."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "ok", "running", "active", "healthy"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _text(value: Any, limit: int | None = None, default: str = "") -> str:
    """Normalize value to a clean stripped string with optional character limit."""
    if value is None:
        return default
    rendered = str(value).strip()
    if not rendered and default:
        rendered = default
    if limit is not None and limit >= 0:
        return rendered[:limit]
    return rendered
