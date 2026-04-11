import unittest

from services.memory_routing import MemoryRoutingService


class TestMemoryRoutingService(unittest.TestCase):
    def setUp(self):
        self.service = MemoryRoutingService()

    def test_preference_query_is_allowed(self):
        plan = self.service.plan_durable_recall("what colors does the user like favorite color preference")

        self.assertTrue(plan.allow)
        self.assertEqual(plan.lane, "durable_user")
        self.assertEqual(plan.purpose, "user_preferences")

    def test_generic_query_is_blocked(self):
        plan = self.service.plan_durable_recall("tell me a joke about weather")

        self.assertFalse(plan.allow)
        self.assertEqual(plan.reason, "not_memory_seeking")

    def test_session_priority_blocks_general_context(self):
        plan = self.service.plan_durable_recall(
            "what do you know about this",
            conversation_state={"kind": "retrieval"},
        )

        self.assertFalse(plan.allow)
        self.assertEqual(plan.reason, "session_priority")

    def test_identity_fallback_overrides_session_priority(self):
        plan = self.service.plan_durable_recall(
            "nova name origin story creator gus",
            conversation_state={"kind": "retrieval"},
        )

        self.assertTrue(plan.allow)
        self.assertEqual(plan.purpose, "identity_fallback")
        self.assertEqual(plan.reason, "purpose_override")

    def test_recent_learning_summary_overrides_session_priority(self):
        plan = self.service.plan_durable_recall(
            "what have you learned from me",
            purpose="recent_learning_summary",
            conversation_state={"kind": "retrieval"},
        )

        self.assertTrue(plan.allow)
        self.assertEqual(plan.purpose, "recent_learning_summary")
        self.assertEqual(plan.reason, "purpose_override")


if __name__ == "__main__":
    unittest.main()