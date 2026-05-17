from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

from services.nova_runtime_hooks import resolve_runtime_hooks


_EXECUTE_REGISTERED_SUPERVISOR_RULE_HOOKS = {
    "make_conversation_state_fn": "_make_conversation_state",
    "attach_reply_outcome_fn": "_attach_reply_outcome",
    "render_reply_fn": "render_reply",
    "last_assistant_turn_text_fn": "_last_assistant_turn_text",
    "parse_correction_fn": "_parse_correction",
    "extract_authoritative_correction_text_fn": "_extract_authoritative_correction_text",
    "store_supervisor_correction_record_fn": "_store_supervisor_correction_record",
    "learn_from_user_correction_fn": "learn_from_user_correction",
    "classify_correction_outcome_fn": "_classify_correction_outcome",
    "mem_enabled_fn": "mem_enabled",
    "normalize_correction_for_storage_fn": "_normalize_correction_for_storage",
    "teach_store_example_fn": "_teach_store_example",
    "get_active_user_fn": "get_active_user",
    "looks_like_correction_cancel_fn": "_looks_like_correction_cancel",
    "looks_like_pending_replacement_text_fn": "_looks_like_pending_replacement_text",
}

_HANDLE_SUPERVISOR_INTENT_HOOKS = {
    "render_reply_fn": "render_reply",
    "mem_enabled_fn": "mem_enabled",
    "mem_add_fn": "mem_add",
    "classify_store_fact_outcome_fn": "_classify_store_fact_outcome",
    "classify_set_location_outcome_fn": "_classify_set_location_outcome",
    "set_location_text_fn": "set_location_text",
    "make_conversation_state_fn": "_make_conversation_state",
    "parse_correction_fn": "_parse_correction",
    "last_assistant_turn_text_fn": "_last_assistant_turn_text",
    "store_supervisor_correction_record_fn": "_store_supervisor_correction_record",
    "teach_store_example_fn": "_teach_store_example",
    "get_active_user_fn": "get_active_user",
    "classify_correction_outcome_fn": "_classify_correction_outcome",
}

CHAT_SUPERVISOR_INTENTS_RETIRED_FOR_CLI_HTTP = frozenset({
    "capability_inventory",
    "grounded_self_report",
    "retrieval_followup",
    "runtime_identity",
    "weather_lookup",
    "web_research_family",
})


def execute_registered_supervisor_rule(
    rule_result: dict,
    text: str,
    current_state: Optional[dict],
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    input_source: str = "typed",
    allowed_actions: Optional[set[str]] = None,
    make_conversation_state_fn: Callable[..., dict],
    attach_reply_outcome_fn: Callable[[Optional[dict], Optional[dict]], None],
    render_reply_fn: Callable[[Optional[dict]], str],
    last_assistant_turn_text_fn: Callable[[Optional[list[tuple[str, str]]]], str],
    parse_correction_fn: Callable[[str], str],
    extract_authoritative_correction_text_fn: Callable[[str], str],
    store_supervisor_correction_record_fn: Callable[..., None],
    learn_from_user_correction_fn: Callable[[str], tuple[bool, str]],
    classify_correction_outcome_fn: Callable[..., dict[str, object]],
    mem_enabled_fn: Callable[[], bool],
    normalize_correction_for_storage_fn: Callable[[str], str],
    teach_store_example_fn: Callable[..., object],
    get_active_user_fn: Callable[[], Optional[str]],
    looks_like_correction_cancel_fn: Callable[[str], bool],
    looks_like_pending_replacement_text_fn: Callable[[str], bool],
) -> tuple[bool, str, Optional[dict]]:
    action = str((rule_result or {}).get("action") or "").strip().lower()
    if not action:
        return False, "", current_state
    if allowed_actions is not None and action not in allowed_actions:
        return False, "", current_state

    if action == "location_clarify":
        question = str((rule_result or {}).get("clarifying_question") or "").strip()
        if not question:
            question = "Which location do you mean?"
        next_state = (rule_result or {}).get("next_state") if isinstance((rule_result or {}).get("next_state"), dict) else current_state
        return True, question, next_state

    if action == "apply_correction":
        correction_text = str((rule_result or {}).get("user_correction_text") or text).strip()
        pending_target = ""
        pending_followup = isinstance(current_state, dict) and str(current_state.get("kind") or "") == "correction_pending"
        if pending_followup:
            pending_target = str(current_state.get("target") or "").strip()
        last_assistant = pending_target or last_assistant_turn_text_fn(turns)
        parsed = parse_correction_fn(correction_text)
        authoritative = extract_authoritative_correction_text_fn(correction_text)
        correction_value = parsed or authoritative

        store_supervisor_correction_record_fn(
            correction_text,
            input_source=input_source,
            last_assistant=last_assistant,
            parsed_correction=(correction_value or ""),
        )

        if correction_value and last_assistant:
            if mem_enabled_fn():
                corr_store = normalize_correction_for_storage_fn(correction_value)
                teach_store_example_fn(last_assistant, corr_store, user=get_active_user_fn() or None)
            outcome = classify_correction_outcome_fn(
                correction_text=correction_text,
                correction_value=correction_value,
                last_assistant=last_assistant,
                pending_followup=pending_followup,
                replacement_applied=True,
            )
            attach_reply_outcome_fn(rule_result, outcome)
            return True, render_reply_fn(outcome), None

        learned_fact, learned_msg = learn_from_user_correction_fn(correction_text)
        if learned_fact:
            outcome = classify_correction_outcome_fn(
                correction_text=correction_text,
                correction_value=correction_value,
                last_assistant=last_assistant,
                pending_followup=pending_followup,
                learned_fact=True,
                learned_message=learned_msg,
            )
            attach_reply_outcome_fn(rule_result, outcome)
            return True, render_reply_fn(outcome), None

        if pending_followup and looks_like_correction_cancel_fn(correction_text):
            reply_text = "Understood. I canceled that replacement request and did not learn anything from it."
            outcome = {
                "intent": "apply_correction",
                "kind": "correction_cancelled",
                "correction_kind": "cancel_pending_replacement",
                "reply_contract": "correction.cancelled",
                "reply_text": reply_text,
                "state_delta": {},
            }
            attach_reply_outcome_fn(rule_result, outcome)
            return True, reply_text, None

        if pending_followup and not correction_value and looks_like_pending_replacement_text_fn(correction_text):
            if last_assistant:
                if mem_enabled_fn():
                    corr_store = normalize_correction_for_storage_fn(correction_text)
                    teach_store_example_fn(last_assistant, corr_store, user=get_active_user_fn() or None)
                outcome = classify_correction_outcome_fn(
                    correction_text=correction_text,
                    correction_value=correction_text,
                    last_assistant=last_assistant,
                    pending_followup=True,
                    replacement_applied=True,
                )
                attach_reply_outcome_fn(rule_result, outcome)
                return True, render_reply_fn(outcome), None

        if pending_followup and not correction_value and correction_text and "?" not in correction_text:
            reply_text = "I still need the exact replacement wording you want me to use."
            outcome = {
                "intent": "apply_correction",
                "kind": "pending_replacement_reminder",
                "correction_kind": "awaiting_replacement_text",
                "reply_contract": "correction.pending_replacement",
                "reply_text": reply_text,
                "state_delta": {},
            }
            attach_reply_outcome_fn(rule_result, outcome)
            return True, reply_text, current_state

        if last_assistant:
            next_state = make_conversation_state_fn("correction_pending", target=last_assistant)
            outcome = classify_correction_outcome_fn(
                correction_text=correction_text,
                correction_value=correction_value,
                last_assistant=last_assistant,
                pending_followup=pending_followup,
                replacement_pending=True,
            )
            attach_reply_outcome_fn(rule_result, outcome)
            return True, render_reply_fn(outcome), next_state

        outcome = classify_correction_outcome_fn(
            correction_text=correction_text,
            correction_value=correction_value,
            last_assistant=last_assistant,
            pending_followup=pending_followup,
        )
        attach_reply_outcome_fn(rule_result, outcome)
        return True, render_reply_fn(outcome), None

    return False, "", current_state


def execute_registered_supervisor_rule_from_runtime(
    rule_result: dict,
    text: str,
    current_state: Optional[dict],
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    input_source: str = "typed",
    allowed_actions: Optional[set[str]] = None,
    runtime_scope: Optional[Mapping[str, Any]] = None,
    **explicit_hooks,
) -> tuple[bool, str, Optional[dict]]:
    hooks = resolve_runtime_hooks(
        _EXECUTE_REGISTERED_SUPERVISOR_RULE_HOOKS,
        explicit_hooks=explicit_hooks,
        runtime_scope=runtime_scope,
    )
    return execute_registered_supervisor_rule(
        rule_result,
        text,
        current_state,
        turns=turns,
        input_source=input_source,
        allowed_actions=allowed_actions,
        **hooks,
    )


def handle_supervisor_intent(
    intent_result: dict,
    user_text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    input_source: str = "typed",
    entry_point: str = "",
    render_reply_fn: Callable[[Optional[dict]], str],
    mem_enabled_fn: Callable[[], bool],
    mem_add_fn: Callable[[str, str, str], None],
    classify_store_fact_outcome_fn: Callable[..., dict[str, object]],
    classify_set_location_outcome_fn: Callable[[dict, str], dict[str, object]],
    set_location_text_fn: Callable[..., None],
    make_conversation_state_fn: Callable[..., dict],
    parse_correction_fn: Callable[[str], str],
    last_assistant_turn_text_fn: Callable[[Optional[list[tuple[str, str]]]], str],
    store_supervisor_correction_record_fn: Callable[..., None],
    teach_store_example_fn: Callable[..., object],
    get_active_user_fn: Callable[[], Optional[str]],
    classify_correction_outcome_fn: Callable[..., dict[str, object]],
) -> tuple[bool, str, Optional[dict], Optional[dict]]:
    intent = str((intent_result or {}).get("intent") or "").strip().lower()
    if not intent:
        return False, "", None, None
    if intent in CHAT_SUPERVISOR_INTENTS_RETIRED_FOR_CLI_HTTP:
        return False, "", None, None

    normalized_entry_point = str(entry_point or "").strip().lower()
    _ = normalized_entry_point

    if intent == "store_fact":
        fact_text = str((intent_result or {}).get("fact_text") or user_text).strip()
        memory_kind = str((intent_result or {}).get("memory_kind") or "user_fact").strip() or "user_fact"
        storage_performed = False
        if fact_text and mem_enabled_fn():
            try:
                mem_add_fn(memory_kind, input_source, fact_text)
                storage_performed = True
            except Exception:
                storage_performed = False
        outcome = classify_store_fact_outcome_fn(intent_result, user_text, source="intent", storage_performed=storage_performed)
        return True, render_reply_fn(outcome), None, {
            "reply_contract": str(outcome.get("reply_contract") or ""),
            "reply_outcome": outcome,
        }

    if intent == "set_location":
        location_value = str((intent_result or {}).get("location_value") or user_text).strip()
        if location_value:
            try:
                set_location_text_fn(location_value, input_source=input_source)
            except Exception:
                pass
        outcome = classify_set_location_outcome_fn(intent_result, user_text)
        return True, render_reply_fn(outcome), make_conversation_state_fn("location_recall"), {
            "reply_contract": str(outcome.get("reply_contract") or ""),
            "reply_outcome": outcome,
        }

    if intent == "apply_correction":
        correction_text = str((intent_result or {}).get("user_correction_text") or user_text).strip()
        parsed = parse_correction_fn(correction_text)
        last_assistant = last_assistant_turn_text_fn(turns)
        store_supervisor_correction_record_fn(
            correction_text,
            input_source=input_source,
            last_assistant=last_assistant,
            parsed_correction=parsed or "",
        )
        if parsed and last_assistant and mem_enabled_fn():
            teach_store_example_fn(last_assistant, parsed, user=get_active_user_fn() or None)
            outcome = classify_correction_outcome_fn(
                correction_text=correction_text,
                correction_value=parsed,
                last_assistant=last_assistant,
                pending_followup=False,
                replacement_applied=True,
            )
        else:
            outcome = {
                "intent": "apply_correction",
                "kind": "intent_ack",
                "correction_kind": "simple_negation",
                "reply_contract": "correction.intent_ack",
                "correction_text": correction_text,
                "correction_value": str(parsed or "").strip(),
                "learned_message": "",
                "target_text": str(last_assistant or "").strip(),
                "pending_followup": False,
                "state_delta": {},
            }
        return True, render_reply_fn(outcome), None, {
            "reply_contract": str(outcome.get("reply_contract") or ""),
            "reply_outcome": outcome,
        }

    return False, "", None, None


def handle_supervisor_intent_from_runtime(
    intent_result: dict,
    user_text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    input_source: str = "typed",
    entry_point: str = "",
    runtime_scope: Optional[Mapping[str, Any]] = None,
    **explicit_hooks,
) -> tuple[bool, str, Optional[dict], Optional[dict]]:
    hooks = resolve_runtime_hooks(
        _HANDLE_SUPERVISOR_INTENT_HOOKS,
        explicit_hooks=explicit_hooks,
        runtime_scope=runtime_scope,
    )
    return handle_supervisor_intent(
        intent_result,
        user_text,
        turns=turns,
        input_source=input_source,
        entry_point=entry_point,
        **hooks,
    )


def apply_cli_supervisor_intent(
    *,
    intent_rule: dict,
    routed_user_text: str,
    handled_intent: bool,
    intent_msg: str,
    intent_state: Optional[dict],
    intent_effects: Optional[dict],
    pending_action_ledger: Optional[dict],
    ensure_reply_fn: Callable[[str], str],
    emit_supervisor_intent_trace_fn: Callable[..., None],
    set_pending_action_fn: Callable[[Optional[dict]], None],
    set_conversation_state_fn: Callable[[Optional[dict]], None],
    sync_pending_conversation_tracking_fn: Callable[[], None],
    trace_fn: Callable[..., None],
) -> tuple[bool, str]:
    if not handled_intent:
        return False, ""

    intent_name = str((intent_rule or {}).get("intent") or "").strip().lower()
    if intent_name in CHAT_SUPERVISOR_INTENTS_RETIRED_FOR_CLI_HTTP:
        return False, ""
    emit_supervisor_intent_trace_fn(intent_rule, user_text=routed_user_text)
    final = ensure_reply_fn(intent_msg)

    if isinstance(intent_effects, dict) and "pending_action" in intent_effects:
        set_pending_action_fn(intent_effects.get("pending_action"))

    if isinstance(intent_effects, dict) and isinstance(pending_action_ledger, dict):
        pending_action_ledger["reply_contract"] = str(intent_effects.get("reply_contract") or "")
        pending_action_ledger["reply_outcome"] = (
            dict(intent_effects.get("reply_outcome") or {})
            if isinstance(intent_effects.get("reply_outcome"), dict)
            else {}
        )

    if isinstance(intent_state, dict):
        set_conversation_state_fn(intent_state)
        sync_pending_conversation_tracking_fn()

    trace_fn(
        "supervisor_intent",
        "handled",
        str((intent_rule or {}).get("intent") or "intent"),
        rule=str((intent_rule or {}).get("rule_name") or ""),
    )
    return True, final
