import unittest

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


if __name__ == "__main__":
    unittest.main()