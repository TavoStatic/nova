from __future__ import annotations

from typing import Any


_INVALID_PREFIXES = (
    "no matches found.",
    "not a file:",
    "not a folder:",
    "file not found:",
    "not found:",
    "error:",
)

_POLICY_DENIALS = (
    "screen tool disabled by policy.",
    "camera tool disabled by policy.",
    "file tools disabled by policy.",
    "health tool disabled by policy.",
    "patch tool disabled by policy.",
    "forced patch apply is disabled by policy.",
    "web tool disabled by policy.",
    "knowledge pack disabled.",
    "memory is disabled in policy.",
)

_FAILURE_FRAGMENTS = (
    " is restricted to admin-approved execution.",
    " tool failed:",
    "tool error:",
    "llm service unavailable",
    "ollama chat model missing",
    "ollama chat api unavailable",
    "ollama chat failed",
)


def invalid_tool_result(tool_name: str, result: Any) -> tuple[bool, str]:
    """Return whether a tool result is blocked/failed evidence, not usable evidence."""
    if isinstance(result, dict):
        if not bool(result.get("ok", True)):
            return True, str(result.get("error") or result.get("reason") or "unknown error")
        mode = str(result.get("execution_mode") or "").strip().lower()
        if mode == "blocked":
            return True, str(result.get("error") or result.get("reason") or "execution_blocked")
        return False, ""

    text_raw = str(result or "").strip()
    text = text_raw.lower()
    if not text:
        return True, "empty_result"
    if any(text.startswith(prefix) for prefix in _INVALID_PREFIXES):
        return True, text_raw or "invalid_result"
    if text in _POLICY_DENIALS:
        return True, text_raw or "policy_denied"
    short_status = "\n" not in text_raw and len(text_raw) <= 500
    if short_status and any(fragment in text for fragment in _FAILURE_FRAGMENTS):
        return True, text_raw or "tool_failed"
    if text.startswith(f"{str(tool_name or '').strip().lower()} tool failed:"):
        return True, text_raw or "tool_failed"
    return False, ""


def evidence_result_valid(row: dict[str, Any]) -> bool:
    tool_name = str(row.get("tool_name") or "").strip()
    result_text = str(row.get("result_text") or "").strip()
    invalid, _reason = invalid_tool_result(tool_name, result_text)
    return not invalid
