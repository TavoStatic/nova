import unittest
from pathlib import Path

from conversation_manager import ConversationSession
from supervisor import Supervisor


class TestSupervisorOwnershipGate(unittest.TestCase):
    def test_supervisor_does_not_claim_smalltalk_intent(self):
        result = Supervisor().evaluate_rules("how are you doing today ?", phase="intent")

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "smalltalk")

    def test_supervisor_does_not_claim_open_ended_name_origin_query(self):
        result = Supervisor().evaluate_rules("why are you called Nova?", phase="intent")

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "name_origin")

    def test_supervisor_does_not_claim_open_ended_developer_profile_query(self):
        result = Supervisor().evaluate_rules("who is gus ?", phase="intent")

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "developer_profile")

    def test_supervisor_does_not_claim_session_summary_pattern(self):
        result = Supervisor().evaluate_rules("what happened", phase="intent")

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("rule_name"), "session_summary")

    def test_supervisor_still_claims_explicit_weather_request(self):
        result = Supervisor().evaluate_rules("check the weather if you can please..", phase="intent")

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("rule_name"), "weather_lookup")

    def test_supervisor_still_claims_low_ambiguity_pending_action_continuation(self):
        session = ConversationSession()
        session.set_pending_action(
            {
                "kind": "weather_lookup",
                "status": "awaiting_location",
                "saved_location_available": True,
                "preferred_tool": "weather_current_location",
            }
        )

        result = Supervisor().evaluate_rules("go ahead", manager=session, phase="intent")

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("rule_name"), "weather_lookup")

    def test_supervisor_still_claims_retrieval_followup(self):
        session = ConversationSession()
        session.set_retrieval_state(
            {
                "kind": "retrieval",
                "subject": "web_research",
                "query": "PEIMS attendance",
                "result_count": 2,
                "urls": ["https://tea.texas.gov/a", "https://tea.texas.gov/b"],
            }
        )

        result = Supervisor().evaluate_rules("tell me about the first one", manager=session, phase="handle")

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("rule_name"), "retrieval_followup")

    def test_cli_loop_does_not_own_location_trigger_lists(self):
        source = (Path(__file__).resolve().parents[1] / "services" / "nova_cli_loop.py").read_text(encoding="utf-8")

        self.assertNotIn("loc_triggers", source)
        self.assertNotIn("expand_triggers", source)

    def test_followup_dispatch_does_not_own_location_conversation_fallback(self):
        source = (Path(__file__).resolve().parents[1] / "services" / "nova_followup_dispatch.py").read_text(encoding="utf-8")

        self.assertNotIn("handle_location_conversation_turn", source)

    def test_cli_loop_does_not_own_pending_weather_followup_fallback(self):
        source = (Path(__file__).resolve().parents[1] / "services" / "nova_cli_loop.py").read_text(encoding="utf-8")

        self.assertNotIn("apply_pending_weather_followup_fallback", source)

    def test_http_chat_flow_does_not_reown_shared_turn_outcomes(self):
        source = (Path(__file__).resolve().parents[1] / "http_chat_flow.py").read_text(encoding="utf-8")

        self.assertIn("from services.nova_turn_outcomes import apply_fast_smalltalk", source)
        shared_outcomes = [
            "apply_fast_smalltalk",
            "apply_identity_binding_learning",
            "apply_numeric_clarify_outcome",
            "apply_mixed_turn_clarify",
            "apply_web_research_override",
            "apply_supervisor_bypass_safe_fallback",
            "apply_developer_profile_learning",
            "apply_self_profile_learning",
            "apply_location_store_outcome",
            "apply_saved_location_weather_outcome",
            "apply_declarative_store_outcome",
            "apply_developer_guess_outcome",
            "apply_developer_location_outcome",
        ]
        for outcome_name in shared_outcomes:
            self.assertNotIn(f"def {outcome_name}(", source)

    def test_cli_loop_uses_shared_numeric_and_mixed_clarify_outcomes(self):
        source = (Path(__file__).resolve().parents[1] / "services" / "nova_cli_loop.py").read_text(encoding="utf-8")

        self.assertIn("from services.nova_turn_outcomes import apply_numeric_clarify_outcome", source)
        self.assertIn("from services.nova_turn_outcomes import apply_mixed_turn_clarify", source)
        self.assertNotIn("if \"mixed\" in turn_acts", source)
        self.assertNotIn("core._should_clarify_unlabeled_numeric_turn(", source)

    def test_cli_loop_uses_shared_web_override_outcome(self):
        source = (Path(__file__).resolve().parents[1] / "services" / "nova_cli_loop.py").read_text(encoding="utf-8")

        self.assertIn("from services.nova_turn_outcomes import apply_web_research_override", source)
        self.assertNotIn("core._is_web_research_override_request(", source)

    def test_cli_loop_uses_shared_supervisor_bypass_outcome(self):
        source = (Path(__file__).resolve().parents[1] / "services" / "nova_cli_loop.py").read_text(encoding="utf-8")

        self.assertIn("from services.nova_turn_outcomes import apply_supervisor_bypass_safe_fallback", source)
        self.assertNotIn("safe_reply, safe_kind", source)
        self.assertNotIn("core._open_probe_reply(", source)


if __name__ == "__main__":
    unittest.main()
