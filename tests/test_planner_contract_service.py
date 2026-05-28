import unittest
import json
from unittest import mock

from services import nova_planner_contract


class _PlannerCoreStub:
    def __init__(self, actions=None, tool_result="", semantic_intent=None, weather_available=True):
        self._actions = list(actions or [])
        self._tool_result = tool_result
        self._semantic_intent = semantic_intent
        self._weather_available = weather_available
        self.last_config = None
        self.executed = []

    def decide_actions(self, text, config=None):
        self.last_config = dict(config or {})
        return list(self._actions)

    def _llm_classify_routing_intent(self, text, turns=None, pending_action=None, return_none_payload=False):
        return self._semantic_intent

    def _weather_current_location_available(self):
        return bool(self._weather_available)

    def make_pending_weather_action(self):
        return {"kind": "weather_lookup", "status": "awaiting_location", "preferred_tool": "weather_location"}

    def execute_planned_action(self, tool, args):
        self.executed.append((tool, list(args or [])))
        return self._tool_result

    def tool_web_research(self, text):
        return self._tool_result

    def _web_allowlist_message(self, resource):
        return f"Allowlist blocked: {resource}"


class _SessionStub:
    def __init__(self, active_work_tree_id="", active_work_identity="", conversation_state=None):
        self.active_work_tree_id = active_work_tree_id
        self.active_work_identity = active_work_identity
        self.last_work_continuity = ""
        self.conversation_state = conversation_state

    def set_last_work_continuity(self, value: str):
        self.last_work_continuity = value

    def set_active_work_identity(self, value: str):
        self.active_work_identity = value


class TestPlannerContractService(unittest.TestCase):
    def test_build_planner_config_carries_turns_pending_and_override(self):
        config = nova_planner_contract.build_planner_config(
            turns=[("user", "hello")],
            pending_action={"tool": "weather"},
            prefer_web_for_data_queries=True,
        )

        self.assertEqual(config["session_turns"], [("user", "hello")])
        self.assertEqual(config["pending_action"], {"tool": "weather"})
        self.assertTrue(config["prefer_web_for_data_queries"])

    def test_maybe_handle_planner_sequence_returns_route_evidence_for_tool_run(self):
        core = _PlannerCoreStub(
            semantic_intent={
                "tool": "web_research",
                "args": ["student_data"],
                "confidence": 0.92,
                "reason": "research goal",
            },
            tool_result="Grounded result",
        )

        reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
            text="research student_data",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=None,
            core=core,
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
        )

        self.assertTrue(str(reply or "").strip())
        self.assertEqual(meta.get("planner_decision"), "run_tool")
        self.assertEqual((meta.get("route_evidence") or {}).get("final_owner"), "action_planner")
        self.assertEqual((meta.get("route_evidence") or {}).get("planner_tool"), "web_research")
        self.assertIn("timing", meta)
        self.assertGreaterEqual((meta.get("timing") or {}).get("planner_time", -1), 0)
        self.assertGreaterEqual((meta.get("timing") or {}).get("tool_selection_time", -1), 0)
        self.assertGreaterEqual((meta.get("timing") or {}).get("tool_time", -1), 0)

    def test_maybe_handle_planner_sequence_uses_semantic_tool_intent(self):
        core = _PlannerCoreStub(
            actions=[],
            semantic_intent={"tool": "weather_current_location", "args": [], "confidence": 0.91, "reason": "weather goal"},
            tool_result="Weather reply",
            weather_available=True,
        )

        reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
            text="should I bring a jacket today?",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=None,
            core=core,
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
        )

        self.assertEqual(reply, "Weather reply")
        self.assertEqual(meta.get("planner_decision"), "run_tool")
        self.assertEqual(meta.get("tool"), "weather_current_location")
        self.assertEqual(meta.get("reply_contract"), "weather_lookup.current_location")
        self.assertEqual(core.executed, [("weather_current_location", [])])

    def test_maybe_handle_planner_sequence_prefers_semantic_intent_over_static_parser(self):
        core = _PlannerCoreStub(
            actions=[{"type": "run_tool", "tool": "web_search", "args": ["surface parse"]}],
            semantic_intent={
                "tool": "self_status",
                "args": [],
                "confidence": 0.94,
                "reason": "live runtime state",
                "answer_target": "nova_live_state",
                "evidence_need": "live_self_status",
            },
            tool_result="Nova Self Status",
            weather_available=True,
        )

        reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
            text="tell me what is going on inside Nova",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=None,
            core=core,
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
        )

        self.assertEqual(reply, "")
        self.assertEqual(meta.get("planner_decision"), "tool_evidence_for_fallback")
        self.assertEqual(meta.get("tool"), "self_status")
        self.assertEqual(meta.get("reply_contract"), "self_status.current")
        self.assertTrue(meta.get("defer_to_fallback"))
        self.assertEqual(meta.get("tool_result"), "Nova Self Status")
        self.assertEqual(core.executed, [("self_status", [])])

    def test_maybe_handle_planner_sequence_allows_semantic_non_self_tool_with_empty_turn_acts(self):
        core = _PlannerCoreStub(
            actions=[],
            semantic_intent={"tool": "weather_current_location", "args": [], "confidence": 0.91, "reason": "weather intent"},
            tool_result="Weather from current location",
            weather_available=True,
        )

        reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
            text="weather now",
            turns=[],
            pending_action=None,
            turn_acts=[],
            prefer_web_for_data_queries=False,
            session=None,
            core=core,
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
        )

        self.assertEqual(reply, "Weather from current location")
        self.assertEqual(meta.get("tool"), "weather_current_location")
        self.assertEqual(meta.get("reply_contract"), "weather_lookup.current_location")

    def test_maybe_handle_planner_sequence_contracts_system_check_tool(self):
        core = _PlannerCoreStub(
            semantic_intent={"tool": "system_check", "args": [], "confidence": 0.88, "reason": "verify runtime checks"},
            tool_result="System check: OK",
        )

        reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
            text="can you prove that from your internals?",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=None,
            core=core,
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
        )

        self.assertEqual(reply, "System check: OK")
        self.assertEqual(meta.get("reply_contract"), "system_check.current")
        self.assertEqual(core.executed, [("system_check", [])])

    def test_maybe_handle_planner_sequence_renders_system_check_json_by_contract(self):
        payload = {
            "profile": "runtime",
            "heartbeat": {"ok": True, "info": "age=0s", "required": True},
            "core_state": {"ok": True, "info": "pid=123", "required": True},
            "ollama": {"ok": False, "info": "chat_model_missing", "required": True},
            "ok": False,
        }
        core = _PlannerCoreStub(
            semantic_intent={"tool": "system_check", "args": [], "confidence": 0.88, "reason": "verify runtime checks"},
            tool_result=json.dumps(payload),
        )

        reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
            text="can you prove that from your internals?",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=None,
            core=core,
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
        )

        self.assertIn("System check: needs attention.", reply)
        self.assertIn("- heartbeat: ok (age=0s)", reply)
        self.assertIn("- ollama: attention (chat_model_missing)", reply)
        self.assertIn("Needs attention: ollama.", reply)
        self.assertFalse(reply.strip().startswith("{"))
        self.assertEqual(meta.get("reply_contract"), "system_check.current")
        evidence = (meta.get("reply_outcome") or {}).get("evidence") or {}
        self.assertFalse(evidence.get("ok"))
        self.assertEqual(evidence.get("profile"), "runtime")

    def test_maybe_handle_planner_sequence_does_not_fallback_to_static_parser_after_semantic_none(self):
        core = _PlannerCoreStub(
            actions=[{"type": "run_tool", "tool": "web_search", "args": ["surface parse"]}],
            semantic_intent={"tool": "none", "args": [], "confidence": 0.81, "reason": "conversation"},
            tool_result="should not run",
        )

        outcome = nova_planner_contract.maybe_handle_planner_sequence(
            text="tell me why your last answer was odd",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=None,
            core=core,
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
        )

        self.assertIsNone(outcome)
        self.assertEqual(core.executed, [])

    def test_maybe_handle_planner_sequence_blocks_low_confidence_no_arg_tool_payload(self):
        observed = []
        core = _PlannerCoreStub(
            semantic_intent={"tool": "system_check", "args": [], "confidence": 0.31, "reason": "weak numeric signal"},
            tool_result="System check: OK",
        )

        outcome = nova_planner_contract.maybe_handle_planner_sequence(
            text="verify the runtime checks",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=None,
            core=core,
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
            semantic_tool_observer_fn=lambda payload: observed.append(payload),
        )

        self.assertIsNone(outcome)
        self.assertEqual(core.executed, [])
        self.assertEqual(observed[-1].get("status"), "weak_tool_route")
        self.assertEqual((observed[-1].get("intent") or {}).get("tool"), "none")
        self.assertEqual((observed[-1].get("intent") or {}).get("answer_target"), "current_conversation")

    def test_maybe_handle_planner_sequence_does_not_run_no_confidence_status_route(self):
        observed = []
        core = _PlannerCoreStub(
            actions=[{"type": "run_tool", "tool": "web_search", "args": ["surface parse"]}],
            semantic_intent={"tool": "self_status", "args": [], "confidence": 0.0, "reason": ""},
            tool_result="LIVE STATUS",
        )

        outcome = nova_planner_contract.maybe_handle_planner_sequence(
            text="hello",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=None,
            core=core,
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
            semantic_tool_observer_fn=lambda payload: observed.append(payload),
        )

        self.assertIsNone(outcome)
        self.assertEqual(core.executed, [])
        self.assertEqual(observed[-1].get("status"), "weak_tool_route")
        self.assertEqual((observed[-1].get("intent") or {}).get("tool"), "none")
        self.assertEqual((observed[-1].get("intent") or {}).get("answer_target"), "current_conversation")

    def test_maybe_handle_planner_sequence_routes_live_status_from_structured_pair_without_numeric_confidence(self):
        core = _PlannerCoreStub(
            semantic_intent={
                "tool": "self_status",
                "args": [],
                "confidence": 0.0,
                "reason": "",
                "answer_target": "nova_live_state",
                "evidence_need": "live_self_status",
            },
            tool_result="Nova Self Status",
        )

        reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
            text="what is troubling you today?",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=None,
            core=core,
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
        )

        self.assertEqual(reply, "")
        self.assertEqual(meta.get("planner_decision"), "tool_evidence_for_fallback")
        self.assertEqual(meta.get("tool"), "self_status")
        self.assertEqual(meta.get("reply_contract"), "self_status.current")
        self.assertTrue(meta.get("defer_to_fallback"))
        self.assertEqual(meta.get("tool_result"), "Nova Self Status")
        self.assertEqual(core.executed, [("self_status", [])])

    def test_maybe_handle_planner_sequence_blocks_status_tool_without_live_status_contract(self):
        observed = []
        core = _PlannerCoreStub(
            semantic_intent={
                "tool": "self_status",
                "args": [],
                "confidence": 0.95,
                "reason": "bare status tool is not enough",
                "answer_target": "current_conversation",
                "evidence_need": "conversation",
            },
            tool_result="Nova Self Status",
        )

        outcome = nova_planner_contract.maybe_handle_planner_sequence(
            text="ordinary conversation turn",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=None,
            core=core,
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
            semantic_tool_observer_fn=lambda payload: observed.append(payload),
        )

        self.assertIsNone(outcome)
        self.assertEqual(core.executed, [])
        self.assertEqual(observed[-1].get("status"), "weak_tool_route")

    def test_maybe_handle_planner_sequence_does_not_rerun_no_arg_tool_when_evidence_is_available(self):
        core = _PlannerCoreStub(
            semantic_intent={
                "tool": "self_status",
                "args": [],
                "confidence": 0.0,
                "answer_target": "nova_live_state",
                "evidence_need": "live_self_status",
            },
            tool_result="Nova Self Status",
        )
        session = _SessionStub(
            conversation_state={
                "kind": "last_tool_evidence",
                "tool": "self_status",
                "tool_result": "Previous Nova Self Status",
            }
        )
        traces = []
        observed = []

        outcome = nova_planner_contract.maybe_handle_planner_sequence(
            text="explain the status you just gave",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=session,
            core=core,
            trace=lambda *args, **kwargs: traces.append((args, kwargs)),
            normalize_reply=lambda text: text,
            semantic_tool_observer_fn=lambda payload: observed.append(payload),
        )

        self.assertIsNone(outcome)
        self.assertEqual(core.executed, [])
        self.assertTrue(any(args[:2] == ("action_planner", "prior_tool_evidence_present") for args, _kwargs in traces))
        self.assertEqual(observed[-1].get("status"), "prior_tool_evidence_present")
        self.assertEqual((observed[-1].get("intent") or {}).get("answer_target"), "current_conversation")
        self.assertEqual((observed[-1].get("intent") or {}).get("evidence_need"), "conversation")

    def test_maybe_handle_planner_sequence_routes_semantic_work_tree_status(self):
        core = _PlannerCoreStub(
            actions=[],
            semantic_intent={"tool": "work_tree_status", "args": [], "confidence": 0.89, "reason": "work plan status"},
        )

        with mock.patch("work_tree.format_tree_snapshot", return_value="Active work tree: Repair tree (active)."):
            reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
                text="show me the current work plan state",
                turns=[],
                pending_action=None,
                prefer_web_for_data_queries=False,
                session=_SessionStub(active_work_tree_id="tree_1"),
                core=core,
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
            )

        self.assertIn("Active work tree:", reply)
        self.assertEqual(meta.get("planner_decision"), "work_tree")
        self.assertEqual((meta.get("route_evidence") or {}).get("planner_action"), "inspect")

    def test_maybe_handle_planner_sequence_sets_pending_weather_when_location_missing(self):
        core = _PlannerCoreStub(
            actions=[],
            semantic_intent={"tool": "weather_current_location", "args": [], "confidence": 0.91},
            weather_available=False,
        )

        reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
            text="should I bring a jacket today?",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=None,
            core=core,
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
        )

        self.assertIn("What location", reply)
        self.assertEqual(meta.get("planner_decision"), "ask_clarify")
        self.assertEqual((meta.get("pending_action") or {}).get("kind"), "weather_lookup")
        self.assertEqual(core.executed, [])

    def test_merge_route_evidence_updates_routing_decision(self):
        merged = nova_planner_contract.merge_route_evidence(
            {"entry_point": "http"},
            {"route_evidence": {"final_owner": "action_planner", "planner_action": "run_tool"}},
        )

        self.assertEqual(merged.get("entry_point"), "http")
        self.assertEqual(merged.get("final_owner"), "action_planner")
        self.assertEqual(merged.get("planner_action"), "run_tool")

    def test_maybe_handle_planner_sequence_returns_work_tree_step_for_active_tree(self):
        with mock.patch("work_tree.next_autonomous_step", return_value={
            "action": "execute",
            "branch_id": "branch_1",
            "branch_title": "Root: Repair",
            "recommended_tool": "web_search",
            "required_tools": ["web_search"],
            "allowed_tools": ["web_search"],
        }):
            reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
                text="what next",
                turns=[],
                pending_action=None,
                prefer_web_for_data_queries=False,
                session=_SessionStub(active_work_tree_id="tree_1"),
                core=_PlannerCoreStub(semantic_intent={"tool": "work_tree_next", "args": [], "confidence": 0.9}),
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
            )

        self.assertTrue(str(reply or "").strip())
        self.assertIn("Root: Repair", reply)
        self.assertIn("web_search", reply)
        self.assertEqual(meta.get("planner_decision"), "work_tree")
        self.assertEqual((meta.get("route_evidence") or {}).get("final_owner"), "work_tree")
        self.assertEqual((meta.get("route_evidence") or {}).get("planner_action"), "execute")

    def test_maybe_handle_planner_sequence_returns_work_tree_wait_reply(self):
        with mock.patch("work_tree.next_autonomous_step", return_value={
            "action": "wait_for_tools",
            "branch_id": "branch_1",
            "missing_tools": ["web_fetch"],
        }):
            reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
                text="continue",
                turns=[],
                pending_action=None,
                prefer_web_for_data_queries=False,
                session=_SessionStub(active_work_tree_id="tree_1"),
                core=_PlannerCoreStub(semantic_intent={"tool": "work_tree_next", "args": [], "confidence": 0.9}),
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
            )

        self.assertTrue(str(reply or "").strip())
        self.assertIn("waiting for tools", reply)
        self.assertIn("web_fetch", reply)
        self.assertEqual(meta.get("planner_decision"), "work_tree")

    def test_maybe_handle_planner_sequence_executes_work_tree_on_continue(self):
        with mock.patch("work_tree.execute_autonomous_step", return_value={
            "action": "executed",
            "branch_id": "branch_1",
            "branch_title": "Root: Repair",
            "task_id": "task_1",
            "task_title": "search student_data",
            "tool": "web_search",
            "tool_args": ["search student_data"],
            "tool_result": "search results",
        }):
            reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
                text="continue",
                turns=[],
                pending_action=None,
                prefer_web_for_data_queries=False,
                session=_SessionStub(active_work_tree_id="tree_1"),
                core=_PlannerCoreStub(semantic_intent={"tool": "work_tree_execute", "args": [], "confidence": 0.9}),
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
            )

        self.assertTrue(str(reply or "").strip())
        self.assertEqual(meta.get("planner_decision"), "work_tree")
        self.assertEqual((meta.get("route_evidence") or {}).get("planner_action"), "executed")

    def test_maybe_handle_planner_sequence_creates_work_tree_when_requested(self):
        with mock.patch("work_tree.format_tree_snapshot", return_value="Active work tree: Chat: inspect runtime (active)."):
            reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
                text="start a work tree for inspect runtime",
                turns=[],
                pending_action=None,
                prefer_web_for_data_queries=False,
                session=_SessionStub(active_work_tree_id=""),
                core=_PlannerCoreStub(semantic_intent={"tool": "work_tree_create", "args": ["inspect runtime"], "confidence": 0.9}),
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
                ensure_active_work_tree_fn=lambda _text: "tree_1",
            )

        self.assertTrue(str(reply or "").strip())
        self.assertIn("Active work tree:", reply)
        self.assertEqual(meta.get("planner_decision"), "work_tree")
        self.assertEqual((meta.get("tool_args") or {}).get("tree_id"), "tree_1")

    def test_maybe_handle_planner_sequence_formats_tree_inspection(self):
        with mock.patch("work_tree.format_tree_snapshot", return_value="Active work tree: Repair tree (active)."):
            reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
                text="show active work tree",
                turns=[],
                pending_action=None,
                prefer_web_for_data_queries=False,
                session=_SessionStub(active_work_tree_id="tree_1"),
                core=_PlannerCoreStub(semantic_intent={"tool": "work_tree_status", "args": [], "confidence": 0.9}),
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
            )

        self.assertTrue(str(reply or "").strip())
        self.assertIn("Active work tree:", reply)
        self.assertEqual(meta.get("planner_decision"), "work_tree")

    def test_maybe_handle_planner_sequence_does_not_auto_seed_from_message_content(self):
        ensure_calls = []

        outcome = nova_planner_contract.maybe_handle_planner_sequence(
            text="inspect runtime worker queue pressure and patch status",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=_SessionStub(active_work_tree_id=""),
            core=_PlannerCoreStub(actions=[]),
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
            ensure_active_work_tree_fn=lambda _text: ensure_calls.append(_text) or "tree_auto_1",
            work_tree_seed_source="chat",
            work_tree_seed_mode="",
        )

        self.assertIsNone(outcome)
        self.assertEqual(ensure_calls, [])

    def test_maybe_handle_planner_sequence_does_not_auto_seed_for_content_prompt(self):
        ensure_calls = []

        outcome = nova_planner_contract.maybe_handle_planner_sequence(
            text="collect student_data attendance guidance and summarize district action items",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=_SessionStub(active_work_tree_id=""),
            core=_PlannerCoreStub(actions=[]),
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
            ensure_active_work_tree_fn=lambda _text: ensure_calls.append(_text) or "tree_should_not_seed",
            work_tree_seed_source="chat",
            work_tree_seed_mode="",
        )

        self.assertIsNone(outcome)
        self.assertEqual(ensure_calls, [])

    def test_maybe_handle_planner_sequence_continues_active_identity_without_continue_keyword(self):
        with mock.patch("work_tree.next_autonomous_step", return_value={
            "action": "execute",
            "branch_id": "branch_1",
            "branch_title": "Step 1: inspect runtime queue pressure",
            "recommended_tool": "queue_status",
            "required_tools": ["queue_status"],
            "allowed_tools": ["queue_status"],
        }):
            session = _SessionStub(
                active_work_tree_id="tree_1",
                active_work_identity="work:guard-pressure-queue-runtime|terms:guard|pressure|queue|runtime",
            )
            reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
                text="also check runtime queue pressure trends",
                turns=[],
                pending_action=None,
                prefer_web_for_data_queries=False,
                session=session,
                core=_PlannerCoreStub(semantic_intent={"tool": "work_tree_next", "args": [], "confidence": 0.9}),
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
            )

        self.assertTrue(str(reply or "").strip())
        self.assertIn("queue_status", reply)
        self.assertEqual(meta.get("planner_decision"), "work_tree")
        self.assertEqual((meta.get("pending_action") or {}).get("work_tree_id"), "tree_1")
        self.assertEqual(session.last_work_continuity, "continuing_existing_work")


if __name__ == "__main__":
    unittest.main()

