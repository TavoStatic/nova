import unittest

from services import supervisor_intent_rules


class TestSupervisorIntentRules(unittest.TestCase):
    def test_name_origin_rule_returns_query_kind(self):
        result = supervisor_intent_rules.name_origin_rule(
            "Why are you called Nova?",
            "why are you called nova",
            None,
            1,
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "name_origin")
        self.assertEqual(result.get("name_origin_query_kind"), "why_called")

    def test_developer_profile_rule_handles_creator_and_profile(self):
        creator = supervisor_intent_rules.developer_profile_rule(
            "Is Gus your creator?",
            "is gus your creator",
            None,
            1,
        )
        profile = supervisor_intent_rules.developer_profile_rule(
            "Tell me about your developer",
            "tell me about your developer",
            None,
            1,
        )

        self.assertEqual(creator.get("intent"), "creator_identity")
        self.assertEqual(profile.get("intent"), "developer_profile")

    def test_session_summary_rule_returns_session_scope(self):
        result = supervisor_intent_rules.session_summary_rule(
            "What happened?",
            "what happened",
            None,
            1,
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("intent"), "session_summary")
        self.assertEqual(result.get("target"), "current_session_only")