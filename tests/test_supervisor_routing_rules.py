import unittest

from conversation_manager import ConversationSession
from supervisor import Supervisor
from services import supervisor_routing_rules


class TestSupervisorRoutingRules(unittest.TestCase):
    def test_extract_store_fact_payload_accepts_colon_form(self):
        payload = supervisor_routing_rules.extract_store_fact_payload(
            "Remember this: the deployment window is Friday night.",
            "remember this: the deployment window is friday night.",
        )

        self.assertEqual(payload.get("fact_text"), "the deployment window is Friday night")
        self.assertEqual(payload.get("memory_kind"), "user_fact")

    def test_set_location_rule_extracts_zip_payload(self):
        result = supervisor_routing_rules.set_location_rule(
            "My zip is 78504",
            "my zip is 78504",
            None,
            1,
            phase="intent",
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "set_location")
        self.assertEqual(result.get("location_kind"), "zip")
        self.assertEqual(result.get("location_ack_kind"), "fact_only")

    def test_web_research_family_selects_stackexchange_for_debug_query(self):
        result = supervisor_routing_rules.web_research_family_rule(
            "research fastapi oauth error online",
            "research fastapi oauth error online",
            None,
            1,
            phase="intent",
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("tool_name"), "stackexchange_search")

    def test_web_research_family_rejects_bare_research_prompt(self):
        result = supervisor_routing_rules.web_research_family_rule(
            "research PEIMS attendance",
            "research peims attendance",
            None,
            1,
            phase="intent",
        )

        self.assertFalse(result.get("handled"))

    def test_search_provider_keeps_generic_explain_prompt_off_wikipedia(self):
        tool = supervisor_routing_rules.search_provider_tool_for_query(
            "Explain photosynthesis briefly.",
            "Explain photosynthesis briefly.",
            "search",
        )

        self.assertEqual(tool, "web_research")

    def test_search_provider_keeps_location_label_prompt_off_wikipedia(self):
        tool = supervisor_routing_rules.search_provider_tool_for_query(
            "what is the name of the city",
            "what is the name of the city",
            "search",
        )

        self.assertEqual(tool, "web_research")

    def test_location_recall_context_handles_city_name_label_intent(self):
        supervisor = Supervisor()
        session = ConversationSession()
        session.set_conversation_state({"kind": "location_recall"})

        result = supervisor.evaluate_rules(
            "what is the name of the city",
            manager=session,
            phase="handle",
        )

        self.assertEqual(result.get("rule_name"), "location_recall")
        self.assertEqual(result.get("action"), "location_name")
        self.assertTrue(result.get("handled"))
        self.assertFalse(result.get("continuation", False))

    def test_location_name_rule_clarifies_without_location_context(self):
        supervisor = Supervisor()

        result = supervisor.evaluate_rules(
            "what is the name of the city",
            manager=ConversationSession(),
            phase="handle",
        )

        self.assertEqual(result.get("rule_name"), "location_name")
        self.assertEqual(result.get("action"), "location_clarify")
        self.assertTrue(result.get("handled"))
        self.assertIn("Which location", result.get("clarifying_question", ""))

    def test_location_name_rule_claims_prior_reference(self):
        supervisor = Supervisor()

        result = supervisor.evaluate_rules(
            "what is the name of that location",
            manager=ConversationSession(),
            phase="handle",
        )

        self.assertEqual(result.get("rule_name"), "location_name")
        self.assertEqual(result.get("action"), "location_name")
        self.assertTrue(result.get("handled"))


if __name__ == "__main__":
    unittest.main()
