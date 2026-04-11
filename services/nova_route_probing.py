from __future__ import annotations

from typing import Callable, Optional


def evaluate_deterministic_route_viability(
    user_text: str,
    session: object,
    recent_turns: list[tuple[str, str]],
    *,
    pending_action: Optional[dict] = None,
    evaluate_rules_fn: Callable[..., dict],
    supervisor_result_has_route_fn: Callable[[Optional[dict]], bool],
    planner_decide_turn_fn: Optional[Callable[..., list[dict]]] = None,
) -> dict:
    intent_result = evaluate_rules_fn(
        user_text,
        manager=session,
        turns=recent_turns,
        phase="intent",
        entry_point="probe",
    )
    handle_result = evaluate_rules_fn(
        user_text,
        manager=session,
        turns=recent_turns,
        phase="handle",
        entry_point="probe",
    )

    owned_result = intent_result if supervisor_result_has_route_fn(intent_result) else handle_result
    if supervisor_result_has_route_fn(owned_result):
        notes = [
            note
            for note in [
                f"explicit supervisor rule: {str(owned_result.get('rule_name') or '').strip()}",
                f"intent: {str(owned_result.get('intent') or '').strip()}" if str(owned_result.get("intent") or "").strip() else "",
                f"action: {str(owned_result.get('action') or '').strip()}" if str(owned_result.get("action") or "").strip() else "",
            ]
            if note
        ]
        return {
            "viable": True,
            "fit_notes": notes,
            "comparison_strength": "clear",
            "owner_kind": "supervisor",
            "intent_result": intent_result,
            "handle_result": handle_result,
            "owned_result": owned_result,
        }

    if planner_decide_turn_fn is None:
        return {
            "viable": False,
            "fit_notes": [],
            "comparison_strength": "weak",
            "owner_kind": "",
            "intent_result": intent_result,
            "handle_result": handle_result,
            "owned_result": {},
        }

    planner_actions = planner_decide_turn_fn(
        user_text,
        config={
            "session_turns": list(recent_turns or []),
            "pending_action": dict(pending_action) if isinstance(pending_action, dict) else None,
        },
    )
    first_action = planner_actions[0] if isinstance(planner_actions, list) and planner_actions else {}
    action_type = str(first_action.get("type") or "").strip()
    tool_name = str(first_action.get("tool") or "").strip()

    if action_type == "route_keyword":
        return {
            "viable": True,
            "fit_notes": ["planner keyword route is deterministic", "keyword route keeps follow-up handling out of fallback"],
            "comparison_strength": "clear",
            "owner_kind": "planner_keyword",
            "intent_result": intent_result,
            "handle_result": handle_result,
            "owned_result": {"action": "route_keyword", "rule_name": "planner_keyword"},
        }

    if action_type == "run_tool" and tool_name in {"patch_apply", "patch_rollback"}:
        return {
            "viable": True,
            "fit_notes": ["planner direct-tool route is deterministic", "patch apply should not be treated as generic fallback"],
            "comparison_strength": "clear",
            "owner_kind": "planner_direct_tool",
            "intent_result": intent_result,
            "handle_result": handle_result,
            "owned_result": {"action": tool_name, "rule_name": "planner_direct_tool", "intent": tool_name},
        }

    if action_type == "route_command":
        normalized_text = str(user_text or "").strip().lower()
        if normalized_text.startswith("patch ") or normalized_text == "patch rollback":
            return {
                "viable": True,
                "fit_notes": ["planner command route is deterministic", "patch command should not be treated as generic fallback"],
                "comparison_strength": "clear",
                "owner_kind": "planner_command",
                "intent_result": intent_result,
                "handle_result": handle_result,
                "owned_result": {"action": "route_command", "rule_name": "planner_command", "intent": "patch_command"},
            }

    return {
        "viable": False,
        "fit_notes": [],
        "comparison_strength": "weak",
        "owner_kind": "",
        "intent_result": intent_result,
        "handle_result": handle_result,
        "owned_result": {},
    }


def build_probe_turn_routes(user_text: str, deterministic: dict, fulfillment: dict) -> dict:
    supervisor_owned = deterministic.get("owned_result") if isinstance(deterministic.get("owned_result"), dict) else {}
    supervisor_viable = bool(deterministic.get("viable"))

    generic_fallback_viable = True
    generic_notes = ["generic fallback remains available if no explicit owner or useful fulfillment comparison exists"]
    comparison_strength = "clear"
    if supervisor_viable and fulfillment.get("viable"):
        comparison_strength = "weak"
        generic_notes.append("multiple routes are viable; no route should claim ownership in probe mode")
    elif not supervisor_viable and not fulfillment.get("viable"):
        comparison_strength = str(fulfillment.get("comparison_strength") or "weak")
        generic_notes.append("fallback is the likely route because explicit ownership and fulfillment both look weak")

    return {
        "user_text": text if (text := str(user_text or "").strip()) else "",
        "comparison_strength": comparison_strength,
        "routes": {
            "supervisor_owned": {
                "viable": supervisor_viable,
                "fit_notes": list(deterministic.get("fit_notes") or []),
            },
            "fulfillment_applicable": {
                "viable": bool(fulfillment.get("viable")),
                "fit_notes": list(fulfillment.get("fit_notes") or []),
            },
            "generic_fallback": {
                "viable": generic_fallback_viable,
                "fit_notes": generic_notes,
            },
        },
    }