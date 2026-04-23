from services.nova_supervisor_flow import apply_cli_supervisor_intent


def test_apply_cli_supervisor_intent_marks_weather_clarify():
    ledger = {}
    events = []
    states = []

    handled, final = apply_cli_supervisor_intent(
        intent_rule={"intent": "weather_lookup", "weather_mode": "clarify", "rule_name": "weather_rule"},
        routed_user_text="weather here",
        handled_intent=True,
        intent_msg="Which location should I use?",
        intent_state={"kind": "location_recall"},
        intent_effects={"reply_contract": "weather.clarify", "reply_outcome": {"intent": "weather_lookup"}},
        pending_action_ledger=ledger,
        ensure_reply_fn=lambda text: text,
        emit_supervisor_intent_trace_fn=lambda *args, **kwargs: None,
        set_pending_action_fn=lambda value: None,
        set_conversation_state_fn=lambda value: states.append(value),
        sync_pending_conversation_tracking_fn=lambda: events.append(("sync", None)),
        trace_fn=lambda *args, **kwargs: events.append((args, kwargs)),
    )

    assert handled is True
    assert final == "Which location should I use?"
    assert ledger["planner_decision"] == "ask_clarify"
    assert ledger["grounded"] is False
    assert ledger["reply_contract"] == "weather.clarify"
    assert ledger["reply_outcome"] == {"intent": "weather_lookup"}
    assert states[-1] == {"kind": "location_recall"}


def test_apply_cli_supervisor_intent_marks_web_research_tool():
    ledger = {"reply_outcome": {"tool_name": "web_research", "query": "nova status"}}

    handled, final = apply_cli_supervisor_intent(
        intent_rule={"intent": "web_research_family", "rule_name": "research_rule"},
        routed_user_text="research nova status",
        handled_intent=True,
        intent_msg="Research results",
        intent_state=None,
        intent_effects={"reply_contract": "research.reply", "reply_outcome": {"tool_name": "web_research", "query": "nova status"}},
        pending_action_ledger=ledger,
        ensure_reply_fn=lambda text: text,
        emit_supervisor_intent_trace_fn=lambda *args, **kwargs: None,
        set_pending_action_fn=lambda value: None,
        set_conversation_state_fn=lambda value: None,
        sync_pending_conversation_tracking_fn=lambda: None,
        trace_fn=lambda *args, **kwargs: None,
    )

    assert handled is True
    assert final == "Research results"
    assert ledger["planner_decision"] == "run_tool"
    assert ledger["tool"] == "web_research"
    assert ledger["tool_args"] == {"args": ["nova status"]}
    assert ledger["grounded"] is True
