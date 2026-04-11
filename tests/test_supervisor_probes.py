import unittest

from services import supervisor_probes


class TestSupervisorProbes(unittest.TestCase):
    def test_normalize_decision_captures_turn_acts_and_defaults(self):
        result = supervisor_probes.normalize_decision(
            "HTTP",
            "s1",
            {"active_subject": "retrieval:web", "continuation_used": True, "overrides_active": ["a"]},
            {
                "user_input": "tell me about the first one",
                "routing_decision": {"turn_acts": ["followup", " retrieval "]},
                "planner_decision": "conversation_followup",
            },
            normalize_text_fn=lambda text: str(text).strip().lower(),
        )

        self.assertEqual(result.get("entry_point"), "http")
        self.assertEqual(result.get("active_subject"), "retrieval:web")
        self.assertEqual(result.get("turn_acts"), ["followup", "retrieval"])
        self.assertEqual(result.get("overrides_active"), ["a"])

    def test_build_suggestions_emits_repeated_issue_hint(self):
        context = {
            "recent_reflections": [
                {"probe_results": ["RED: pending_action_leak - one"]},
                {"probe_results": ["RED: pending_action_leak - two"]},
            ]
        }
        findings = [{"name": "pending_action_leak", "status": "red", "message": "three"}]

        suggestions = supervisor_probes.build_suggestions(context, findings)

        self.assertEqual(len(suggestions), 1)
        self.assertIn("pending_action_leak", suggestions[0])


if __name__ == "__main__":
    unittest.main()