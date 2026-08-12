import inspect
import unittest
from pathlib import Path

import memory
import nova_core
from conversation_manager import ConversationSession
from planner_decision import decide_turn
from services.nova_action_ledger import _FINALIZE_ACTION_LEDGER_RECORD_HOOKS
from services.nova_tool_dispatch import _PLANNED_TOOL_NAMES


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

    def test_static_planner_does_not_claim_phrase_routes(self):
        samples = [
            "what should you work on next",
            "check queue status",
            "run system checks",
            "phase 2 status",
            "nova pulse",
            "update now confirm abc12345",
            "update now cancel",
        ]
        for text in samples:
            with self.subTest(text=text):
                self.assertEqual(decide_turn(text, config={}), [])

    def test_pending_correction_target_tracks_conversation_state(self):
        session = ConversationSession()
        session.apply_state_update({"kind": "correction_pending", "target": "Old incorrect answer"})
        self.assertEqual(session.pending_correction_target, "Old incorrect answer")

        session.apply_state_update({"kind": "retrieval", "subject": "web_research"})
        self.assertEqual(session.pending_correction_target, "")

    def test_core_thinning_keeps_runtime_public_adapters(self):
        required_public_adapters = [
            "clear_runtime_device_location",
            "execute_planned_action",
            "policy_allow_domain",
            "policy_audit",
            "policy_remove_domain",
            "set_location_coords",
            "set_runtime_device_location",
            "set_web_mode",
            "speak_chunked",
            "update_now_pending_payload",
            "web_mode_status",
            "write_action_ledger_record",
        ]
        for adapter_name in required_public_adapters:
            self.assertTrue(callable(getattr(nova_core, adapter_name, None)), adapter_name)

        for tool_name in _PLANNED_TOOL_NAMES:
            self.assertTrue(callable(getattr(nova_core, tool_name, None)), tool_name)

        for runtime_name in _FINALIZE_ACTION_LEDGER_RECORD_HOOKS.values():
            self.assertTrue(callable(getattr(nova_core, runtime_name, None)), runtime_name)

    def test_control_template_uses_current_branding(self):
        template = (Path(__file__).resolve().parents[1] / "templates" / "control.html").read_text(encoding="utf-8").lower()
        self.assertIn("nova by sg intelligence", template)
        self.assertNotIn("nyo system", template)

    def test_smoke_workflow_uses_ci_safe_contract(self):
        workflow_path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "smoke_e2e.yml"
        if not workflow_path.exists():
            self.skipTest("source-control workflow is intentionally excluded from release packages")
        workflow = workflow_path.read_text(encoding="utf-8").lower()
        self.assertIn("actions/checkout@v6", workflow)
        self.assertIn("actions/setup-python@v6", workflow)
        self.assertIn("pip install requests psutil", workflow)
        self.assertNotIn("pip install -r requirements.txt", workflow)


if __name__ == "__main__":
    unittest.main()
