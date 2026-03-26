import inspect
import unittest

import memory
import nova_core
from conversation_manager import ConversationSession
from planner_decision import decide_turn


class TestRegressionContracts(unittest.TestCase):
    def test_memory_api_supports_scope_contract(self):
        add_params = inspect.signature(memory.add_memory).parameters
        recall_params = inspect.signature(memory.recall).parameters
        recall_explain_params = inspect.signature(memory.recall_explain).parameters
        stats_params = inspect.signature(memory.stats).parameters

        self.assertIn("scope", add_params)
        self.assertIn("scope", recall_params)
        self.assertIn("scope", recall_explain_params)
        self.assertIn("scope", stats_params)
        self.assertIn("user", stats_params)

    def test_queue_status_phrase_routes_to_direct_tool(self):
        actions = decide_turn("what should you work on next", config={})
        self.assertTrue(actions)
        self.assertEqual(actions[0].get("type"), "run_tool")
        self.assertEqual(actions[0].get("tool"), "queue_status")

    def test_pending_correction_target_tracks_conversation_state(self):
        session = ConversationSession()
        session.apply_state_update({"kind": "correction_pending", "target": "Old incorrect answer"})
        self.assertEqual(session.pending_correction_target, "Old incorrect answer")

        session.apply_state_update({"kind": "retrieval", "subject": "web_research"})
        self.assertEqual(session.pending_correction_target, "")

    def test_creator_hard_answer_contains_canonical_name(self):
        reply = nova_core.hard_answer("who made you?") or ""
        self.assertIn("my creator is gustavo uribe", reply.lower())


if __name__ == "__main__":
    unittest.main()
