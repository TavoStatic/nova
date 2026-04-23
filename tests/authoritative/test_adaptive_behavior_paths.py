import unittest
from unittest import mock

from services import nova_planner_contract


class _PlannerCoreStub:
    def __init__(self):
        self.calls = []

    def decide_actions(self, text, config=None):
        self.calls.append((text, dict(config or {})))
        return []

    def make_pending_weather_action(self):
        return {"tool": "weather", "awaiting": "location"}

    def handle_commands(self, text, session_turns=None, session=None):
        return ""

    def handle_keywords(self, text):
        return None

    def execute_planned_action(self, tool, args):
        return ""


class _SessionStub:
    def __init__(self, active_work_tree_id="", active_work_identity=""):
        self.active_work_tree_id = active_work_tree_id
        self.active_work_identity = active_work_identity
        self.last_work_continuity = ""

    def set_last_work_continuity(self, value: str):
        self.last_work_continuity = value

    def set_active_work_identity(self, value: str):
        self.active_work_identity = value

    def set_active_work_tree_id(self, value: str):
        self.active_work_tree_id = value


class TestAdaptiveBehaviorPaths(unittest.TestCase):
    def test_related_work_variations_keep_work_tree_route_consistent(self):
        session = _SessionStub(
            active_work_tree_id="tree_1",
            active_work_identity="work:guard-pressure-queue-runtime|terms:guard|pressure|queue|runtime",
        )
        core = _PlannerCoreStub()
        step = {
            "action": "execute",
            "branch_id": "branch_1",
            "branch_title": "Inspect runtime queue pressure",
            "recommended_tool": "queue_status",
            "required_tools": ["queue_status"],
            "allowed_tools": ["queue_status"],
        }
        with mock.patch("work_tree.next_autonomous_step", return_value=step):
            first_reply, first_meta = nova_planner_contract.maybe_handle_planner_sequence(
                text="also inspect runtime queue pressure",
                turns=[],
                pending_action=None,
                prefer_web_for_data_queries=False,
                session=session,
                core=core,
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
                is_web_preferred_data_query=lambda text: False,
            )
            second_reply, second_meta = nova_planner_contract.maybe_handle_planner_sequence(
                text="check runtime queue pressure trends too",
                turns=[],
                pending_action=first_meta.get("pending_action"),
                prefer_web_for_data_queries=False,
                session=session,
                core=core,
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
                is_web_preferred_data_query=lambda text: False,
            )

        self.assertTrue(str(first_reply or "").strip())
        self.assertTrue(str(second_reply or "").strip())
        self.assertEqual(first_meta.get("planner_decision"), "work_tree")
        self.assertEqual(second_meta.get("planner_decision"), "work_tree")
        self.assertEqual((first_meta.get("pending_action") or {}).get("work_tree_id"), "tree_1")
        self.assertEqual((second_meta.get("pending_action") or {}).get("work_tree_id"), "tree_1")
        self.assertEqual((first_meta.get("pending_action") or {}).get("work_identity_key"), session.active_work_identity)
        self.assertEqual((second_meta.get("pending_action") or {}).get("work_identity_key"), session.active_work_identity)
        self.assertEqual(session.last_work_continuity, "continuing_existing_work")

    def test_active_work_identity_is_reused_after_first_adaptive_match(self):
        session = _SessionStub(active_work_tree_id="tree_1", active_work_identity="")
        core = _PlannerCoreStub()
        step = {
            "action": "execute",
            "branch_id": "branch_1",
            "branch_title": "Inspect runtime queue pressure",
            "recommended_tool": "queue_status",
        }
        with mock.patch("work_tree.next_autonomous_step", return_value=step):
            _reply, first_meta = nova_planner_contract.maybe_handle_planner_sequence(
                text="continue work on runtime queue pressure",
                turns=[],
                pending_action=None,
                prefer_web_for_data_queries=False,
                session=session,
                core=core,
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
                is_web_preferred_data_query=lambda text: False,
            )
            _reply2, second_meta = nova_planner_contract.maybe_handle_planner_sequence(
                text="also review queue pressure spikes",
                turns=[],
                pending_action=first_meta.get("pending_action"),
                prefer_web_for_data_queries=False,
                session=session,
                core=core,
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
                is_web_preferred_data_query=lambda text: False,
            )

        self.assertTrue(session.active_work_identity)
        self.assertEqual((first_meta.get("pending_action") or {}).get("work_identity_key"), session.active_work_identity)
        self.assertEqual((second_meta.get("pending_action") or {}).get("work_identity_key"), session.active_work_identity)

    def test_related_prompt_continues_while_unrelated_prompt_does_not_force_work_path(self):
        session = _SessionStub(
            active_work_tree_id="tree_1",
            active_work_identity="work:guard-pressure-queue-runtime|terms:guard|pressure|queue|runtime",
        )
        core = _PlannerCoreStub()
        step = {
            "action": "execute",
            "branch_id": "branch_1",
            "branch_title": "Inspect runtime queue pressure",
            "recommended_tool": "queue_status",
        }
        with mock.patch("work_tree.next_autonomous_step", return_value=step):
            related = nova_planner_contract.maybe_handle_planner_sequence(
                text="also inspect queue pressure spikes",
                turns=[],
                pending_action=None,
                prefer_web_for_data_queries=False,
                session=session,
                core=core,
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
                is_web_preferred_data_query=lambda text: False,
            )
            unrelated = nova_planner_contract.maybe_handle_planner_sequence(
                text="tell me about PEIMS deadlines",
                turns=[],
                pending_action=None,
                prefer_web_for_data_queries=False,
                session=session,
                core=core,
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
                is_web_preferred_data_query=lambda text: False,
            )

        self.assertIsNotNone(related)
        self.assertEqual((related[1].get("route_evidence") or {}).get("final_owner"), "work_tree")
        self.assertIsNone(unrelated)