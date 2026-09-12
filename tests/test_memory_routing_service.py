import unittest

from services.memory_routing import MemoryRoutingService


class TestMemoryRoutingService(unittest.TestCase):
    def setUp(self):
        self.service = MemoryRoutingService()

    def test_preference_query_is_allowed(self):
        plan = self.service.plan_durable_recall(
            "operator requested durable recall",
            purpose="user_preferences",
        )

        self.assertTrue(plan.allow)
        self.assertEqual(plan.lane, "durable_user")
        self.assertEqual(plan.purpose, "user_preferences")

    def test_generic_query_is_blocked(self):
        plan = self.service.plan_durable_recall("tell me a joke about weather")

        self.assertFalse(plan.allow)
        self.assertEqual(plan.reason, "not_memory_seeking")

    def test_general_context_still_blocks_non_memory_queries(self):
        plan = self.service.plan_durable_recall(
            "tell me a joke about weather",
            purpose="general_context",
        )

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
            "operator requested durable recall",
            purpose="identity_fallback",
            conversation_state={"kind": "retrieval"},
        )

        self.assertTrue(plan.allow)
        self.assertEqual(plan.purpose, "identity_fallback")
        self.assertEqual(plan.reason, "purpose_override")

    def test_infer_purpose_maps_query_cues(self):
        self.assertEqual(
            self.service.infer_purpose("what have you learned from me lately"),
            "recent_learning_summary",
        )
        self.assertEqual(
            self.service.infer_purpose("what is my favorite color"),
            "user_preferences",
        )
        self.assertEqual(
            self.service.infer_purpose("who built you"),
            "developer_profile",
        )
        self.assertEqual(
            self.service.infer_purpose("recall what I said earlier"),
            "explicit_recall",
        )
        self.assertEqual(
            self.service.infer_purpose("what did I tell you about the orchard lot code"),
            "explicit_recall",
        )
        self.assertEqual(
            self.service.infer_purpose("we discussed this last time"),
            "explicit_recall",
        )

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
