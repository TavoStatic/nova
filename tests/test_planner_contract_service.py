import unittest
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

    def handle_commands(self, text, session_turns=None, session=None):
        return ""

    def handle_keywords(self, text):
        return None

    def execute_planned_action(self, tool, args):
        self.executed.append((tool, list(args or [])))
        return self._tool_result

    def tool_web_research(self, text):
        return self._tool_result

    def _web_allowlist_message(self, resource):
        return f"Allowlist blocked: {resource}"


class _SessionStub:
    def __init__(self, active_work_tree_id="", active_work_identity=""):
        self.active_work_tree_id = active_work_tree_id
        self.active_work_identity = active_work_identity
        self.last_work_continuity = ""

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
            actions=[{"type": "run_tool", "tool": "web_research", "args": ["student_data"]}],
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
            is_web_preferred_data_query=lambda text: False,
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
            is_web_preferred_data_query=lambda text: False,
        )

        self.assertEqual(reply, "Weather reply")
        self.assertEqual(meta.get("planner_decision"), "run_tool")
        self.assertEqual(meta.get("tool"), "weather_current_location")
        self.assertEqual(meta.get("reply_contract"), "weather_lookup.current_location")
        self.assertEqual(core.executed, [("weather_current_location", [])])

    def test_maybe_handle_planner_sequence_prefers_semantic_intent_over_static_parser(self):
        core = _PlannerCoreStub(
            actions=[{"type": "run_tool", "tool": "web_search", "args": ["surface parse"]}],
            semantic_intent={"tool": "self_status", "args": [], "confidence": 0.94, "reason": "live runtime state"},
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
            is_web_preferred_data_query=lambda text: False,
        )

        self.assertEqual(reply, "Nova Self Status")
        self.assertEqual(meta.get("planner_decision"), "run_tool")
        self.assertEqual(meta.get("tool"), "self_status")
        self.assertEqual(meta.get("reply_contract"), "self_status.current")
        self.assertEqual(core.executed, [("self_status", [])])

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
            is_web_preferred_data_query=lambda text: False,
        )

        self.assertIsNone(outcome)
        self.assertEqual(core.executed, [])

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
                is_web_preferred_data_query=lambda text: False,
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
            is_web_preferred_data_query=lambda text: False,
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
                core=_PlannerCoreStub(),
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
                is_web_preferred_data_query=lambda text: False,
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
                core=_PlannerCoreStub(),
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
                is_web_preferred_data_query=lambda text: False,
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
                core=_PlannerCoreStub(),
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
                is_web_preferred_data_query=lambda text: False,
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
                core=_PlannerCoreStub(),
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
                is_web_preferred_data_query=lambda text: False,
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
                core=_PlannerCoreStub(),
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
                is_web_preferred_data_query=lambda text: False,
            )

        self.assertTrue(str(reply or "").strip())
        self.assertIn("Active work tree:", reply)
        self.assertEqual(meta.get("planner_decision"), "work_tree")

    def test_maybe_handle_planner_sequence_auto_seeds_tree_for_system_prompt(self):
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
            is_web_preferred_data_query=lambda text: False,
            ensure_active_work_tree_fn=lambda _text: ensure_calls.append(_text) or "tree_auto_1",
            work_tree_seed_source="chat",
            work_tree_seed_mode="",
        )

        # Auto-seeding is silent when this turn is not a work-tree request.
        self.assertIsNone(outcome)
        self.assertEqual(ensure_calls, ["inspect runtime worker queue pressure and patch status"])

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
            is_web_preferred_data_query=lambda text: False,
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
                core=_PlannerCoreStub(),
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
                is_web_preferred_data_query=lambda text: False,
            )

        self.assertTrue(str(reply or "").strip())
        self.assertIn("queue_status", reply)
        self.assertEqual(meta.get("planner_decision"), "work_tree")
        self.assertEqual((meta.get("pending_action") or {}).get("work_tree_id"), "tree_1")
        self.assertEqual(session.last_work_continuity, "continuing_existing_work")


if __name__ == "__main__":
    unittest.main()

