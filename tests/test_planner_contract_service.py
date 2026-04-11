import unittest
from unittest import mock

from services import nova_planner_contract


class _PlannerCoreStub:
    def __init__(self, actions=None, tool_result=""):
        self._actions = list(actions or [])
        self._tool_result = tool_result
        self.last_config = None

    def decide_actions(self, text, config=None):
        self.last_config = dict(config or {})
        return list(self._actions)

    def make_pending_weather_action(self):
        return {"tool": "weather", "awaiting": "location"}

    def handle_commands(self, text, session_turns=None, session=None):
        return ""

    def handle_keywords(self, text):
        return None

    def execute_planned_action(self, tool, args):
        return self._tool_result

    def tool_web_research(self, text):
        return self._tool_result

    def _web_allowlist_message(self, resource):
        return f"Allowlist blocked: {resource}"


class _SessionStub:
    def __init__(self, active_work_tree_id=""):
        self.active_work_tree_id = active_work_tree_id


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
            actions=[{"type": "run_tool", "tool": "web_research", "args": ["peims"]}],
            tool_result="Grounded result",
        )

        reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
            text="research peims",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=None,
            core=core,
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
            is_web_preferred_data_query=lambda text: False,
        )

        self.assertEqual(reply, "Grounded result")
        self.assertEqual(meta.get("planner_decision"), "run_tool")
        self.assertEqual((meta.get("route_evidence") or {}).get("final_owner"), "action_planner")
        self.assertEqual((meta.get("route_evidence") or {}).get("planner_tool"), "web_research")

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

        self.assertEqual(reply, "Next work tree step: Root: Repair. Recommended tool: web_search.")
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

        self.assertEqual(reply, "The next work tree branch is waiting for tools: web_fetch.")
        self.assertEqual(meta.get("planner_decision"), "work_tree")

    def test_maybe_handle_planner_sequence_executes_work_tree_on_continue(self):
        with mock.patch("work_tree.execute_autonomous_step", return_value={
            "action": "executed",
            "branch_id": "branch_1",
            "branch_title": "Root: Repair",
            "task_id": "task_1",
            "task_title": "search peims",
            "tool": "web_search",
            "tool_args": ["search peims"],
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

        self.assertEqual(reply, "search results")
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

        self.assertEqual(reply, "Active work tree: Chat: inspect runtime (active).")
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

        self.assertEqual(reply, "Active work tree: Repair tree (active).")
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
            text="collect peims attendance guidance and summarize district action items",
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


if __name__ == "__main__":
    unittest.main()