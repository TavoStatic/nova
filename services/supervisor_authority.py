from __future__ import annotations

from typing import Any, Callable, Optional

from services.supervisor_patterns import normalize_text as _normalize_text


EXPLICIT_INTENT_OWNERSHIP_RULES: frozenset[str] = frozenset()


EXPLICIT_HANDLE_OWNERSHIP_RULES: frozenset[str] = frozenset({
    "identity_location_guard",
})


def default_rule_handlers() -> dict[str, Callable[..., dict[str, Any]]]:
    try:
        from services.supervisor_rules import DEFAULT_RULE_HANDLERS
        return dict(DEFAULT_RULE_HANDLERS)
    except ImportError:
        return {}


def result_is_explicitly_owned(rule_name: str, result: dict[str, Any], *, phase: str) -> bool:
    if not bool(result.get("handled")):
        return False
    if bool(result.get("required_safety_intercept")) or bool(result.get("required_policy_intercept")):
        return True
    if str(result.get("ownership") or "").strip().lower() == "explicit":
        return True

    normalized_rule_name = str(rule_name or "").strip()
    normalized_phase = str(phase or "handle").strip().lower()
    if normalized_phase == "intent":
        return normalized_rule_name in EXPLICIT_INTENT_OWNERSHIP_RULES
    if normalized_phase == "handle":
        return normalized_rule_name in EXPLICIT_HANDLE_OWNERSHIP_RULES
    return False


def register_rule(
    rules: list[dict[str, Any]],
    name: str,
    rule: Callable[..., dict[str, Any]],
    *,
    priority: int = 100,
    phases: tuple[str, ...] = ("handle",),
) -> list[dict[str, Any]]:
    updated_rules = [item for item in rules if str(item.get("name") or "") != str(name or "")]
    updated_rules.append({
        "name": str(name or "").strip(),
        "rule": rule,
        "priority": int(priority),
        "phases": tuple(str(phase or "handle").strip().lower() for phase in phases if str(phase or "").strip()),
    })
    updated_rules.sort(key=lambda item: (int(item.get("priority", 100)), str(item.get("name") or "")))
    return updated_rules


def evaluate_rules(
    rules: list[dict[str, Any]],
    user_text: str,
    *,
    manager: Any = None,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    normalized_user_text = str(user_text or "")
    normalized_manager = {} if manager is None else manager
    normalized_turns = list(turns or [])
    normalized_phase = str(phase or "handle").strip().lower() or "handle"
    normalized_entry_point = str(entry_point or "").strip().lower()
    low = _normalize_text(normalized_user_text)
    turn = len(normalized_turns)
    candidates: list[dict[str, Any]] = []
    for item in rules:
        phases = tuple(item.get("phases") or ())
        if normalized_phase not in phases:
            continue
        rule_name = str(item.get("name") or "")
        try:
            result = item["rule"](
                normalized_user_text,
                low,
                normalized_manager,
                turn,
                turns=list(normalized_turns),
                phase=normalized_phase,
                entry_point=normalized_entry_point,
            )
        except Exception as exc:
            result = {"handled": False, "rule_error": str(exc)}
        if not isinstance(result, dict):
            continue
        explicitly_owned = result_is_explicitly_owned(rule_name, result, phase=normalized_phase)
        candidate = {
            "rule_name": rule_name,
            "priority": int(item.get("priority", 100)),
            "handled": bool(result.get("handled")) and explicitly_owned,
        }
        action = str(result.get("action") or "").strip()
        if action:
            candidate["action"] = action
        intent = str(result.get("intent") or "").strip()
        if intent:
            candidate["intent"] = intent
        if bool(result.get("handled")) and not explicitly_owned:
            candidate["ownership_declined"] = True
        if str(result.get("rewrite_text") or "").strip():
            candidate["rewrite"] = True
        if isinstance(result.get("state_update"), dict):
            candidate["state_update"] = True
        rule_error = str(result.get("rule_error") or "").strip()
        if rule_error:
            candidate["rule_error"] = rule_error[:160]
        candidates.append(candidate)
        if explicitly_owned or str(result.get("rewrite_text") or "").strip() or isinstance(result.get("state_update"), dict):
            payload = dict(result)
            payload["phase"] = normalized_phase
            payload["candidates"] = list(candidates)
            if str(payload.get("rule_name") or "").strip():
                payload["matched_rule_name"] = str(payload.get("rule_name") or "").strip()
            payload["rule_name"] = rule_name
            payload["priority"] = int(item.get("priority", 100))
            if not explicitly_owned:
                payload["handled"] = False
            return payload
    return {"handled": False, "phase": normalized_phase, "candidates": candidates}
