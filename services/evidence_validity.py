from __future__ import annotations

import json
from typing import Any

from services.tool_execution_contracts import ADMIN_APPROVED_EXECUTION_SUFFIX
from services.tool_identity import STRUCTURED_JUDGMENT_TOOLS


_INVALID_PREFIXES = (
    "[fail]",
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
    ADMIN_APPROVED_EXECUTION_SUFFIX,
    " tool failed:",
    "tool error:",
    "llm service unavailable",
    "ollama chat model missing",
    "ollama chat api unavailable",
    "ollama chat failed",
)

def _is_structured_judgment_result(tool_name: str, result: dict[str, Any]) -> bool:
    tool = str(tool_name or "").strip()
    if tool not in STRUCTURED_JUDGMENT_TOOLS:
        return False
    return bool(str(result.get("schema") or "").strip() and str(result.get("verdict") or "").strip())


def _parse_structured_tool_result(text_raw: str) -> dict[str, Any] | None:
    stripped = str(text_raw or "").strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        return None
    if len(stripped) > 4000:
        return None
    try:
        payload = json.loads(stripped)
    except Exception:
        return None
    if not isinstance(payload, dict) or "ok" not in payload:
        return None
    return payload


def invalid_tool_result(tool_name: str, result: Any) -> tuple[bool, str]:
    """Return whether a tool result is blocked/failed evidence, not usable evidence."""
    if isinstance(result, dict):
        if _is_structured_judgment_result(tool_name, result):
            return False, ""
        if not bool(result.get("ok", True)):
            return True, str(result.get("error") or result.get("reason") or "unknown error")
        mode = str(result.get("execution_mode") or "").strip().lower()
        if mode == "blocked":
            return True, str(result.get("error") or result.get("reason") or "execution_blocked")
        return False, ""

    text_raw = str(result or "").strip()
    parsed = _parse_structured_tool_result(text_raw)
    if parsed is not None:
        return invalid_tool_result(tool_name, parsed)
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
