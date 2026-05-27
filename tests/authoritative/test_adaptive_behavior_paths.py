import unittest
from unittest import mock

from services import nova_planner_contract


class _PlannerCoreStub:
    def __init__(self, semantic_intent=None):
        self.semantic_intent = semantic_intent or {"tool": "none", "args": [], "confidence": 0.9}

    def _llm_classify_routing_intent(self, text, turns=None, pending_action=None, return_none_payload=False):
        return dict(self.semantic_intent)

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
    def test_semantic_work_tree_intent_continues_active_tree(self):
        session = _SessionStub(
            active_work_tree_id="tree_1",
            active_work_identity="work:guard-pressure-queue-runtime|terms:guard|pressure|queue|runtime",
        )
        core = _PlannerCoreStub({"tool": "work_tree_next", "args": [], "confidence": 0.9})
        step = {
            "action": "execute",
            "branch_id": "branch_1",
            "branch_title": "Inspect runtime queue pressure",
            "recommended_tool": "queue_status",
            "required_tools": ["queue_status"],
            "allowed_tools": ["queue_status"],
        }

        with mock.patch("work_tree.next_autonomous_step", return_value=step):
            reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
                text="operator asks to continue active work",
                turns=[],
                pending_action=None,
                prefer_web_for_data_queries=False,
                session=session,
                core=core,
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
            )

        self.assertTrue(str(reply or "").strip())
        self.assertEqual(meta.get("planner_decision"), "work_tree")
        self.assertEqual((meta.get("pending_action") or {}).get("work_tree_id"), "tree_1")
        self.assertEqual((meta.get("pending_action") or {}).get("work_identity_key"), session.active_work_identity)
        self.assertEqual(session.last_work_continuity, "continuing_existing_work")

    def test_semantic_none_does_not_continue_active_tree_from_text_alone(self):
        session = _SessionStub(
            active_work_tree_id="tree_1",
            active_work_identity="work:guard-pressure-queue-runtime|terms:guard|pressure|queue|runtime",
        )
        outcome = nova_planner_contract.maybe_handle_planner_sequence(
            text="also inspect queue pressure spikes",
            turns=[],
            pending_action=None,
            prefer_web_for_data_queries=False,
            session=session,
            core=_PlannerCoreStub({"tool": "none", "args": [], "confidence": 0.9}),
            trace=lambda *args, **kwargs: None,
            normalize_reply=lambda text: text,
        )

        self.assertIsNone(outcome)

    def test_semantic_work_tree_intent_sets_identity_when_missing(self):
        session = _SessionStub(active_work_tree_id="tree_1", active_work_identity="")
        core = _PlannerCoreStub({"tool": "work_tree_next", "args": ["runtime queue pressure"], "confidence": 0.9})
        step = {
            "action": "execute",
            "branch_id": "branch_1",
            "branch_title": "Inspect runtime queue pressure",
            "recommended_tool": "queue_status",
        }

        with mock.patch("work_tree.next_autonomous_step", return_value=step):
            _reply, meta = nova_planner_contract.maybe_handle_planner_sequence(
                text="operator asks to continue active work",
                turns=[],
                pending_action=None,
                prefer_web_for_data_queries=False,
                session=session,
                core=core,
                trace=lambda *args, **kwargs: None,
                normalize_reply=lambda text: text,
            )

        self.assertTrue(session.active_work_identity)
        self.assertEqual((meta.get("pending_action") or {}).get("work_identity_key"), session.active_work_identity)


if __name__ == "__main__":
    unittest.main()
