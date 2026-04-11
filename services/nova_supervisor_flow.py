from __future__ import annotations

from typing import Callable, Optional


def execute_registered_supervisor_rule(
    rule_result: dict,
    text: str,
    current_state: Optional[dict],
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    input_source: str = "typed",
    allowed_actions: Optional[set[str]] = None,
    remember_name_origin_fn: Callable[[str], str],
    make_conversation_state_fn: Callable[..., dict],
    location_reply_fn: Callable[[], str],
    is_location_name_query_fn: Callable[[str], bool],
    location_name_reply_fn: Callable[[], str],
    location_recall_reply_fn: Callable[[], str],
    classify_weather_lookup_outcome_fn: Callable[[dict], dict[str, object]],
    attach_reply_outcome_fn: Callable[[Optional[dict], Optional[dict]], None],
    execute_planned_action_fn: Callable[..., object],
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
    execute_retrieval_followup_outcome_fn: Callable[[dict, str], tuple[str, Optional[dict], dict[str, object]]],
    execute_identity_history_outcome_fn: Callable[..., tuple[str, Optional[dict], dict[str, object]]],
    open_probe_reply_fn: Callable[[str, Optional[list[tuple[str, str]]]], tuple[str, str]],
    last_question_recall_reply_fn: Callable[[str, Optional[list[tuple[str, str]]]], tuple[str, str]],
    session_fact_recall_reply_fn: Callable[[dict], tuple[str, str]],
    rules_reply_fn: Callable[[], str],
    developer_location_reply_fn: Callable[[], str],
    developer_identity_followup_reply_fn: Callable[..., str],
    identity_profile_followup_reply_fn: Callable[[str], str],
) -> tuple[bool, str, Optional[dict]]:
    action = str((rule_result or {}).get("action") or "").strip().lower()
    if not action:
        return False, "", current_state
    if allowed_actions is not None and action not in allowed_actions:
        return False, "", current_state

    if action == "name_origin_store":
        store_text = str((rule_result or {}).get("store_text") or text).strip()
        if not store_text:
            return False, "", current_state
        return True, remember_name_origin_fn(store_text), current_state

    if action == "self_location":
        next_state = (rule_result or {}).get("next_state") if isinstance((rule_result or {}).get("next_state"), dict) else make_conversation_state_fn("location_recall")
        return True, location_reply_fn(), next_state

    if action == "location_recall":
        next_state = (rule_result or {}).get("next_state") if isinstance((rule_result or {}).get("next_state"), dict) else make_conversation_state_fn("location_recall")
        if is_location_name_query_fn(text):
            return True, location_name_reply_fn(), next_state
        return True, location_recall_reply_fn(), next_state

    if action == "location_name":
        next_state = current_state if isinstance(current_state, dict) else make_conversation_state_fn("location_recall")
        return True, location_name_reply_fn(), next_state

    if action == "weather_current_location":
        next_state = (rule_result or {}).get("next_state")
        if not isinstance(next_state, dict):
            next_state = make_conversation_state_fn("location_recall")
        outcome = classify_weather_lookup_outcome_fn({"weather_mode": "current_location", "next_state": next_state})
        attach_reply_outcome_fn(rule_result, outcome)
        tool_result = execute_planned_action_fn("weather_current_location")
        return True, render_reply_fn({**outcome, "tool_result": str(tool_result or "")}), next_state

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

        if correction_value and last_assistant and mem_enabled_fn():
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
            if last_assistant and mem_enabled_fn():
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

    if action == "retrieval_followup":
        if not isinstance(current_state, dict) or str(current_state.get("kind") or "") != "retrieval":
            return False, "", current_state
        reply, next_state, outcome = execute_retrieval_followup_outcome_fn(current_state, text)
        attach_reply_outcome_fn(rule_result, outcome)
        return True, reply, next_state

    if action == "identity_history_family":
        reply, next_state, outcome = execute_identity_history_outcome_fn(rule_result, current_state, text, turns=turns)
        attach_reply_outcome_fn(rule_result, outcome)
        return True, reply, next_state

    if action == "open_probe_family":
        reply_text, outcome_kind = open_probe_reply_fn(text, turns=turns)
        outcome = {
            "intent": "open_probe_family",
            "kind": outcome_kind,
            "reply_contract": f"open_probe.{outcome_kind}",
            "reply_text": reply_text,
            "state_delta": {},
        }
        attach_reply_outcome_fn(rule_result, outcome)
        return True, reply_text, current_state

    if action == "last_question_recall":
        reply_text, outcome_kind = last_question_recall_reply_fn(text, turns=turns)
        outcome = {
            "intent": "last_question_recall",
            "kind": outcome_kind,
            "reply_contract": f"last_question.{outcome_kind}",
            "reply_text": reply_text,
            "state_delta": {},
        }
        attach_reply_outcome_fn(rule_result, outcome)
        return True, reply_text, current_state

    if action == "session_fact_recall":
        reply_text, outcome_kind = session_fact_recall_reply_fn(rule_result)
        outcome = {
            "intent": "session_fact_recall",
            "kind": outcome_kind,
            "reply_contract": f"session_fact.{outcome_kind}",
            "reply_text": reply_text,
            "state_delta": {},
        }
        attach_reply_outcome_fn(rule_result, outcome)
        return True, reply_text, current_state

    if action == "rules_list":
        outcome = {
            "intent": "rules_list",
            "kind": "list",
            "reply_contract": "rules.list",
            "reply_text": rules_reply_fn(),
            "state_delta": {},
        }
        attach_reply_outcome_fn(rule_result, outcome)
        return True, str(outcome.get("reply_text") or ""), current_state

    if action == "developer_location":
        next_state = current_state if isinstance(current_state, dict) else make_conversation_state_fn("identity_profile", subject="developer")
        return True, developer_location_reply_fn(), next_state

    if action == "developer_identity_followup":
        next_state = current_state if isinstance(current_state, dict) else make_conversation_state_fn("developer_identity", subject="developer")
        return True, developer_identity_followup_reply_fn(turns=turns, name_focus=bool((rule_result or {}).get("name_focus", False))), next_state

    if action == "identity_profile_followup":
        subject = str((rule_result or {}).get("subject") or "self").strip() or "self"
        next_state = current_state if isinstance(current_state, dict) else make_conversation_state_fn("identity_profile", subject=subject)
        return True, identity_profile_followup_reply_fn(subject, turns=turns), next_state

    return False, "", current_state


def handle_supervisor_intent(
    intent_result: dict,
    user_text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    input_source: str = "typed",
    entry_point: str = "",
    classify_web_research_outcome_fn: Callable[..., dict[str, object]],
    execute_planned_action_fn: Callable[..., object],
    make_retrieval_conversation_state_fn: Callable[..., dict],
    render_reply_fn: Callable[[Optional[dict]], str],
    mem_enabled_fn: Callable[[], bool],
    mem_add_fn: Callable[[str, str, str], None],
    classify_store_fact_outcome_fn: Callable[..., dict[str, object]],
    classify_set_location_outcome_fn: Callable[[dict, str], dict[str, object]],
    weather_current_location_available_fn: Callable[[], bool],
    classify_weather_lookup_outcome_fn: Callable[[dict], dict[str, object]],
    execute_weather_lookup_outcome_fn: Callable[[dict[str, object]], tuple[str, Optional[dict], dict[str, object]]],
    set_location_text_fn: Callable[..., None],
    make_conversation_state_fn: Callable[..., dict],
    parse_correction_fn: Callable[[str], str],
    last_assistant_turn_text_fn: Callable[[Optional[list[tuple[str, str]]]], str],
    store_supervisor_correction_record_fn: Callable[..., None],
    teach_store_example_fn: Callable[..., object],
    get_active_user_fn: Callable[[], Optional[str]],
    classify_correction_outcome_fn: Callable[..., dict[str, object]],
    quick_smalltalk_reply_fn: Callable[..., str],
    describe_capabilities_fn: Callable[[], str],
    policy_web_fn: Callable[[], dict],
    assistant_name_reply_fn: Callable[[str], str],
    self_identity_web_challenge_reply_fn: Callable[[], str],
    classify_name_origin_outcome_fn: Callable[[dict], dict[str, object]],
    developer_full_name_reply_fn: Callable[[], str],
    hard_answer_fn: Callable[[str], str],
    developer_profile_reply_fn: Callable[..., str],
    session_recap_reply_fn: Callable[[list[tuple[str, str]], str], str],
) -> tuple[bool, str, Optional[dict], Optional[dict]]:
    intent = str((intent_result or {}).get("intent") or "").strip().lower()
    if not intent:
        return False, "", None, None

    normalized_entry_point = str(entry_point or "").strip().lower()
    _ = normalized_entry_point

    if intent == "web_research_family":
        outcome = classify_web_research_outcome_fn(intent_result, user_text, turns=turns)
        tool_name = str(outcome.get("tool_name") or "web_research").strip().lower() or "web_research"
        query = str(outcome.get("query") or "").strip()
        tool_args = [query] if query else []
        tool_result = execute_planned_action_fn(tool_name, tool_args)
        outcome["tool_result"] = str(tool_result or "")
        next_state = make_retrieval_conversation_state_fn(tool_name, query, outcome["tool_result"])
        return True, render_reply_fn(outcome), next_state, {
            "reply_contract": str(outcome.get("reply_contract") or ""),
            "reply_outcome": outcome,
        }

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

    if intent == "weather_lookup":
        weather_mode = str((intent_result or {}).get("weather_mode") or "clarify").strip().lower() or "clarify"
        if weather_mode == "clarify" and weather_current_location_available_fn():
            intent_result = dict(intent_result or {})
            intent_result["weather_mode"] = "current_location"
        outcome = classify_weather_lookup_outcome_fn(intent_result)
        reply_text, next_state, reply_outcome = execute_weather_lookup_outcome_fn(outcome)
        return True, reply_text, next_state, {
            "reply_contract": str(reply_outcome.get("reply_contract") or ""),
            "reply_outcome": reply_outcome,
            "pending_action": reply_outcome.get("pending_action"),
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

    if intent == "smalltalk":
        reply = quick_smalltalk_reply_fn(user_text, active_user=get_active_user_fn())
        if reply:
            return True, reply, None, None
        return False, "", None, None

    if intent == "capability_query":
        return True, describe_capabilities_fn(), None, None

    if intent == "policy_domain_query":
        web = policy_web_fn()
        domains = list(web.get("allow_domains") or [])
        enabled = bool(web.get("enabled", False))
        lines = [f"Policy web access enabled: {enabled}"]
        if domains:
            lines.append("Allowed domains: " + ", ".join(domains))
        else:
            lines.append("Allowed domains: none configured")
        return True, "\n".join(lines), None, None

    if intent == "assistant_name":
        return True, assistant_name_reply_fn(user_text), None, None

    if intent == "self_identity_web_challenge":
        return True, self_identity_web_challenge_reply_fn(), None, None

    if intent == "name_origin":
        outcome = classify_name_origin_outcome_fn(intent_result)
        return True, render_reply_fn(outcome), None, {
            "reply_contract": str(outcome.get("reply_contract") or ""),
            "reply_outcome": outcome,
        }

    if intent == "developer_full_name":
        return True, developer_full_name_reply_fn(), make_conversation_state_fn("identity_profile", subject="developer"), None

    if intent == "creator_identity":
        creator_reply = hard_answer_fn(user_text) or developer_profile_reply_fn(turns=turns, user_text=user_text)
        return True, creator_reply, make_conversation_state_fn("identity_profile", subject="developer"), None

    if intent == "developer_profile":
        return True, developer_profile_reply_fn(turns=turns, user_text=user_text), make_conversation_state_fn("identity_profile", subject="developer"), None

    if intent == "session_summary":
        return True, session_recap_reply_fn(list(turns or []), user_text), None, None

    return False, "", None, None