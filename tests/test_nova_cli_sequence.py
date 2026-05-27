from services.nova_cli_sequence import apply_sequence_result
from services.nova_cli_sequence import execute_cli_sequence
from services.nova_cli_sequence import normalize_sequence_reply


class _FakeSession:
    def __init__(self):
        self.pending_action = {}
        self.conversation_state = {"kind": "start"}


def test_normalize_sequence_reply_falls_back_when_override_raises():
    assert normalize_sequence_reply(
        "hello",
        ensure_reply_fn=lambda text: f"[{text}]",
    ) == "[hello]"


def test_apply_sequence_result_updates_ledger_and_context():
    session = _FakeSession()
    ledger = {"routing_decision": {"owner": "seed"}}
    turns = []
    sync_calls = []
    trace_calls = []

    def _apply_session_updates(session_state, **_kwargs):
        session_state.pending_action = {"kind": "after"}
        session_state.conversation_state = {"kind": "updated"}

    outcome = apply_sequence_result(
        final="reply",
        meta={
            "planner_decision": "run_tool",
            "tool": "web_research",
            "tool_args": {"args": ["nova"]},
            "tool_result": "grounded output",
            "grounded": True,
            "reply_contract": "test.contract",
            "reply_outcome": {"kind": "ok"},
            "route_evidence": {"final_owner": "planner"},
            "pending_action": {"kind": "weather"},
        },
        pending_action_ledger=ledger,
        merge_route_evidence_fn=lambda routing_decision, meta: {
            **(routing_decision or {}),
            **(meta or {}),
        },
        set_pending_action_fn=lambda value: setattr(session, "pending_action", value),
        session_state=session,
        apply_reply_runtime_effects_fn=lambda **kwargs: {
            "context_updated": True,
            "recent_tool_context": "tool ctx",
            "recent_web_urls": ["https://example.com"],
        },
        apply_reply_session_updates_fn=_apply_session_updates,
        sync_pending_conversation_tracking_fn=lambda: sync_calls.append("sync"),
        trace_fn=lambda *args, **kwargs: trace_calls.append((args, kwargs)),
        emit_cli_reply_outcome_fn=lambda **kwargs: turns.append(("assistant", kwargs["reply_text"])),
        behavior_record_event_fn=lambda *args, **kwargs: None,
        extract_urls_fn=lambda text: [text],
        session_turns=[("user", "nova")],
        recent_tool_context="old",
        recent_web_urls=[],
    )

    assert ledger["planner_decision"] == "run_tool"
    assert ledger["tool"] == "web_research"
    assert ledger["reply_contract"] == "test.contract"
    assert ledger["routing_decision"]["route_evidence"]["final_owner"] == "planner"
    assert session.pending_action == {"kind": "after"}
    assert outcome["conversation_state"] == {"kind": "updated"}
    assert outcome["recent_tool_context"] == "tool ctx"
    assert outcome["recent_web_urls"] == ["https://example.com"]
    assert sync_calls == ["sync"]
    assert turns[-1] == ("assistant", "reply")


def test_execute_cli_sequence_enables_early_planner_and_stops_before_llm():
    captured = {}

    def _fake_execute_reply_sequence(**kwargs):
        captured.update(kwargs)
        return "reply", {"planner_decision": "unhandled"}

    reply, meta = execute_cli_sequence(
        execute_reply_sequence_fn=_fake_execute_reply_sequence,
        text="hello",
        turns=[],
    )

    assert reply == "reply"
    assert meta["planner_decision"] == "unhandled"
    assert captured["stop_before_llm_fallback"] is True
