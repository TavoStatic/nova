from __future__ import annotations

from typing import Callable, Optional


def classify_name_origin_outcome(
    intent_result: dict,
    *,
    get_learned_fact_fn: Callable[[str, str], str],
    get_name_origin_story_fn: Callable[[], str],
) -> dict[str, object]:
    payload = intent_result if isinstance(intent_result, dict) else {}
    query_kind = str(payload.get("name_origin_query_kind") or "source_recall").strip().lower() or "source_recall"
    assistant_name = str(get_learned_fact_fn("assistant_name", "Nova") or "Nova").strip() or "Nova"
    developer_name = str(get_learned_fact_fn("developer_name", "Gustavo Uribe") or "Gustavo Uribe").strip() or "Gustavo Uribe"
    developer_nickname = str(get_learned_fact_fn("developer_nickname", "Gus") or developer_name).strip() or developer_name
    story = str(get_name_origin_story_fn() or "").strip()
    if story:
        if query_kind == "why_called":
            low_story = story.lower()
            if "was given its name" in low_story and "creator" in low_story:
                reply_text = story
            else:
                reply_text = f"{assistant_name} was given its name by its creator, {developer_nickname}. {story}"
        else:
            reply_text = story
        contract = "name_origin.full_story" if query_kind == "full_story" else "name_origin.story_known"
        outcome_kind = "full_story" if query_kind == "full_story" else "story_known"
    else:
        if query_kind == "full_story":
            reply_text = "I do not have a saved full name-origin story yet. You can teach me with: remember this ..."
        else:
            reply_text = "I do not have a saved name-origin story yet. You can teach me with: remember this ..."
        contract = "name_origin.story_missing"
        outcome_kind = "story_missing"
    return {
        "intent": "name_origin",
        "kind": outcome_kind,
        "query_kind": query_kind,
        "reply_contract": contract,
        "reply_text": reply_text,
        "story_known": bool(story),
        "story_text": story,
        "state_delta": {},
    }


def execute_identity_history_outcome(
    rule_result: dict,
    current_state: Optional[dict],
    text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    normalize_turn_text_fn: Callable[[str], str],
    speaker_matches_developer_fn: Callable[[], bool],
    make_conversation_state_fn: Callable[..., dict],
    hard_answer_fn: Callable[[str], str],
    developer_profile_reply_fn: Callable[..., str],
    developer_identity_followup_reply_fn: Callable[..., str],
    identity_name_followup_reply_fn: Callable[[str], str],
    identity_profile_followup_reply_fn: Callable[..., str],
    classify_name_origin_outcome_fn: Callable[[dict], dict[str, object]],
    render_reply_fn: Callable[[Optional[dict]], str],
) -> tuple[str, Optional[dict], dict[str, object]]:
    payload = rule_result if isinstance(rule_result, dict) else {}
    outcome_kind = str(payload.get("identity_history_kind") or "history_recall").strip().lower() or "history_recall"
    subject = str(payload.get("subject") or (current_state or {}).get("subject") or "developer").strip() or "developer"
    state_kind = str((current_state or {}).get("kind") or "").strip()
    normalized_text = normalize_turn_text_fn(text)

    if isinstance(current_state, dict):
        next_state = current_state
    elif subject == "developer" and speaker_matches_developer_fn():
        next_state = make_conversation_state_fn("developer_identity", subject="developer")
    else:
        next_state = make_conversation_state_fn("identity_profile", subject=subject)

    if outcome_kind == "creator_question":
        reply_text = hard_answer_fn(text) or developer_profile_reply_fn(turns=turns, user_text=text)
        next_state = make_conversation_state_fn("identity_profile", subject="developer")
        subject = "developer"
    elif outcome_kind == "name_origin":
        if state_kind == "developer_identity" or (subject == "developer" and speaker_matches_developer_fn()):
            reply_text = developer_identity_followup_reply_fn(turns=turns, name_focus=True)
            next_state = make_conversation_state_fn("developer_identity", subject="developer")
            subject = "developer"
        elif state_kind == "identity_profile":
            reply_text = identity_name_followup_reply_fn(subject)
        else:
            name_origin_outcome = classify_name_origin_outcome_fn(
                {"name_origin_query_kind": str(payload.get("name_origin_query_kind") or "source_recall")}
            )
            reply_text = render_reply_fn(name_origin_outcome)
    else:
        build_history_prompt = any(
            phrase in normalized_text
            for phrase in (
                "how did he develop you",
                "how did he developed you",
                "how did he build you",
                "how was he able to develop you",
            )
        )
        if build_history_prompt:
            reply_text = developer_profile_reply_fn(turns=turns, user_text=text)
            next_state = make_conversation_state_fn("identity_profile", subject="developer")
            subject = "developer"
        elif state_kind == "developer_identity" or (subject == "developer" and speaker_matches_developer_fn()):
            reply_text = developer_identity_followup_reply_fn(turns=turns, name_focus=False)
            next_state = make_conversation_state_fn("developer_identity", subject="developer")
            subject = "developer"
        else:
            reply_text = identity_profile_followup_reply_fn(subject, turns=turns)

    outcome = {
        "intent": "identity_history_family",
        "kind": outcome_kind,
        "reply_contract": f"identity_history.{outcome_kind}",
        "reply_text": str(reply_text or "").strip(),
        "subject": subject,
        "state_delta": dict(next_state or {}) if isinstance(next_state, dict) else {},
    }
    return outcome["reply_text"], next_state, outcome