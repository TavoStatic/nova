import inspect
import unittest
from pathlib import Path

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

    def test_system_check_phrase_routes_to_direct_tool(self):
        actions = decide_turn("run system checks", config={})
        self.assertTrue(actions)
        self.assertEqual(actions[0].get("type"), "run_tool")
        self.assertEqual(actions[0].get("tool"), "system_check")

    def test_phase2_audit_phrase_routes_to_direct_tool(self):
        actions = decide_turn("phase 2 status", config={})
        self.assertTrue(actions)
        self.assertEqual(actions[0].get("type"), "run_tool")
        self.assertEqual(actions[0].get("tool"), "phase2_audit")

    def test_pulse_phrase_routes_to_direct_tool(self):
        actions = decide_turn("nova pulse", config={})
        self.assertTrue(actions)
        self.assertEqual(actions[0].get("type"), "run_tool")
        self.assertEqual(actions[0].get("tool"), "pulse")

    def test_update_now_confirm_phrase_routes_to_direct_tool(self):
        actions = decide_turn("update now confirm abc12345", config={})
        self.assertTrue(actions)
        self.assertEqual(actions[0].get("type"), "run_tool")
        self.assertEqual(actions[0].get("tool"), "update_now_confirm")
        self.assertEqual(actions[0].get("args"), ["abc12345"])

    def test_update_now_cancel_phrase_routes_to_direct_tool(self):
        actions = decide_turn("update now cancel", config={})
        self.assertTrue(actions)
        self.assertEqual(actions[0].get("type"), "run_tool")
        self.assertEqual(actions[0].get("tool"), "update_now_cancel")

    def test_pending_correction_target_tracks_conversation_state(self):
        session = ConversationSession()
        session.apply_state_update({"kind": "correction_pending", "target": "Old incorrect answer"})
        self.assertEqual(session.pending_correction_target, "Old incorrect answer")

        session.apply_state_update({"kind": "retrieval", "subject": "web_research"})
        self.assertEqual(session.pending_correction_target, "")

    def test_creator_hard_answer_contains_canonical_name(self):
        reply = nova_core.hard_answer("who made you?") or ""
        self.assertIn("my creator is gustavo uribe", reply.lower())

    def test_control_template_uses_current_branding(self):
        template = (Path(__file__).resolve().parents[1] / "templates" / "control.html").read_text(encoding="utf-8").lower()
        self.assertIn("nyo ai systems", template)
        self.assertNotIn("nyo system\n", template)

    def test_smoke_workflow_uses_ci_safe_contract(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "smoke_e2e.yml").read_text(encoding="utf-8").lower()
        self.assertIn("actions/checkout@v6", workflow)
        self.assertIn("actions/setup-python@v6", workflow)
        self.assertIn("pip install requests psutil", workflow)
        self.assertNotIn("pip install -r requirements.txt", workflow)


if __name__ == "__main__":
    unittest.main()
