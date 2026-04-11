from __future__ import annotations

from typing import Callable, Optional


def consume_conversation_followup(
    state: Optional[dict],
    text: str,
    *,
    input_source: str = "typed",
    turns: Optional[list[tuple[str, str]]] = None,
    evaluate_rules_fn: Callable[..., dict],
    execute_registered_supervisor_rule_fn: Callable[..., tuple[bool, str, Optional[dict]]],
    is_retrieval_meta_question_fn: Callable[[str], bool],
    retrieval_meta_reply_fn: Callable[[dict], str],
    looks_like_retrieval_followup_fn: Callable[[str], bool],
    retrieval_followup_reply_fn: Callable[[dict, str], tuple[str, Optional[dict]]],
    is_queue_status_reason_followup_fn: Callable[[str], bool],
    queue_status_reason_reply_fn: Callable[[dict], str],
    is_queue_status_report_followup_fn: Callable[[str], bool],
    queue_status_report_reply_fn: Callable[[dict], str],
    is_queue_status_seam_followup_fn: Callable[[str], bool],
    queue_status_seam_reply_fn: Callable[[dict], str],
    handle_location_conversation_turn_fn: Callable[..., tuple[bool, str, Optional[dict], str]],
    is_weather_meta_followup_fn: Callable[[str], bool],
    weather_meta_reply_fn: Callable[[dict], str],
    is_weather_status_followup_fn: Callable[[str], bool],
    weather_status_reply_fn: Callable[[dict], str],
    normalize_turn_text_fn: Callable[[str], str],
    numeric_reference_guess_reply_fn: Callable[[str], str],
    numeric_reference_binding_reply_fn: Callable[[str, str], str],
    make_conversation_state_fn: Callable[..., dict],
    extract_work_role_parts_fn: Callable[[str], list[str]],
    store_developer_role_facts_fn: Callable[..., tuple[bool, str]],
    strip_confirmation_prefix_fn: Callable[[str], str],
    looks_like_profile_followup_fn: Callable[[str], bool],
    developer_identity_followup_reply_fn: Callable[..., str],
    non_retrieval_resource_meta_reply_fn: Callable[[], str],
    is_developer_location_request_fn: Callable[..., bool],
    developer_location_reply_fn: Callable[[], str],
    identity_name_followup_reply_fn: Callable[[str], str],
    identity_profile_followup_reply_fn: Callable[..., str],
) -> tuple[bool, str, Optional[dict]]:
    if not isinstance(state, dict):
        return False, "", state

    rule_result = evaluate_rules_fn(text, manager=state, turns=turns, phase="handle")
    handled_rule, rule_reply, rule_state = execute_registered_supervisor_rule_fn(
        rule_result,
        text,
        state,
        turns=turns,
        input_source=input_source,
    )
    if handled_rule:
        return True, rule_reply, rule_state

    kind = str(state.get("kind") or "")
    if kind == "retrieval":
        if is_retrieval_meta_question_fn(text):
            return True, retrieval_meta_reply_fn(state), state
        if looks_like_retrieval_followup_fn(text):
            reply, next_state = retrieval_followup_reply_fn(state, text)
            return True, reply, next_state
        return False, "", state

    if kind == "queue_status":
        if is_queue_status_reason_followup_fn(text):
            return True, queue_status_reason_reply_fn(state), state
        if is_queue_status_report_followup_fn(text):
            return True, queue_status_report_reply_fn(state), state
        if is_queue_status_seam_followup_fn(text):
            return True, queue_status_seam_reply_fn(state), state
        return False, "", state

    if kind == "location_recall":
        handled_location, location_reply, location_state, _location_intent = handle_location_conversation_turn_fn(
            state,
            text,
            turns=turns,
        )
        if handled_location:
            return True, location_reply, location_state
        return False, "", state

    if kind == "weather_result":
        if is_weather_meta_followup_fn(text):
            return True, weather_meta_reply_fn(state), state
        if is_weather_status_followup_fn(text):
            return True, weather_status_reply_fn(state), state
        return False, "", state

    if kind == "numeric_reference_clarify":
        value = str(state.get("value") or "").strip()
        normalized = normalize_turn_text_fn(text)
        raw = str(text or "").strip()
        if not raw:
            return False, "", state
        if raw == value or "?" in raw or any(phrase in normalized for phrase in ("what do you think", "what is it", "what do you guess", "guess")):
            return True, numeric_reference_guess_reply_fn(value), state
        referent = raw.rstrip(".!? ")
        if not referent:
            return False, "", state
        return True, numeric_reference_binding_reply_fn(value, referent), make_conversation_state_fn("numeric_reference", value=value, referent=referent)

    if kind == "numeric_reference":
        value = str(state.get("value") or "").strip()
        referent = str(state.get("referent") or "").strip()
        raw = str(text or "").strip()
        if raw == value and referent:
            return True, numeric_reference_binding_reply_fn(value, referent), state
        return False, "", state

    if kind == "developer_role_guess":
        if "?" in (text or ""):
            return False, "", None
        roles = extract_work_role_parts_fn(text)
        learned, learned_text = store_developer_role_facts_fn(roles, input_source=input_source)
        if learned:
            return True, "Understood. I learned: " + learned_text + ".", None
        if strip_confirmation_prefix_fn(text):
            return True, "I still need the actual role or job title to store, not just a confirmation.", state
        return False, "", state

    if kind == "developer_identity":
        low = normalize_turn_text_fn(text)
        if "my name" in low or ("name" in low and any(token in low for token in ("tell me more", "more about", "go on", "continue"))):
            return True, developer_identity_followup_reply_fn(turns=turns, name_focus=True), state
        if looks_like_profile_followup_fn(text):
            return True, developer_identity_followup_reply_fn(turns=turns, name_focus=False), state
        return False, "", state

    if kind == "identity_profile":
        low = normalize_turn_text_fn(text)
        if is_retrieval_meta_question_fn(text):
            return True, non_retrieval_resource_meta_reply_fn(), state
        if str(state.get("subject") or "") == "developer":
            if is_developer_location_request_fn(text, state=state, turns=turns):
                return True, developer_location_reply_fn(), state
        if "my name" in low or "name" in low and any(token in low for token in ("tell me more", "more about", "go on", "continue")):
            subject = str(state.get("subject") or "self")
            return True, identity_name_followup_reply_fn(subject), state
        if looks_like_profile_followup_fn(text):
            subject = str(state.get("subject") or "self")
            return True, identity_profile_followup_reply_fn(subject, turns=turns), state
        return False, "", state

    return False, "", state