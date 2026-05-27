import unittest

from services.nova_reply_runtime import apply_reply_runtime_effects


class TestNovaReplyRuntime(unittest.TestCase):
    def test_run_tool_records_tool_route_and_updates_recent_context(self):
        events = []

        payload = apply_reply_runtime_effects(
            planner_decision="run_tool",
            tool="queue_status",
            tool_result="Standing work queue\nhttps://tea.texas.gov/a",
            behavior_record_event_fn=events.append,
            extract_urls_fn=lambda text: ["https://tea.texas.gov/a"] if "https://tea.texas.gov/a" in text else [],
        )

        self.assertEqual(events, ["tool_route"])
        self.assertTrue(payload.get("context_updated"))
        self.assertIn("Standing work queue", str(payload.get("recent_tool_context") or ""))
        self.assertEqual(payload.get("recent_web_urls"), ["https://tea.texas.gov/a"])

    def test_conversation_followup_does_not_infer_context_from_reply_text(self):
        events = []

        payload = apply_reply_runtime_effects(
            planner_decision="conversation_followup",
            tool="",
            tool_result="",
            final_reply="Gathered: https://tea.texas.gov/a",
            active_state={"kind": "retrieval", "subject": "student_data"},
            behavior_record_event_fn=events.append,
            extract_urls_fn=lambda text: ["https://tea.texas.gov/a"] if "https://tea.texas.gov/a" in text else [],
        )

        self.assertEqual(events, [])
        self.assertFalse(payload.get("context_updated"))
        self.assertEqual(payload.get("recent_web_urls"), [])

    def test_deterministic_reply_records_hit_without_identity_conflict_hook(self):
        events = []

        payload = apply_reply_runtime_effects(
            planner_decision="deterministic",
            tool="hard_answer",
            tool_result="My name is Nova.",
            behavior_record_event_fn=events.append,
            extract_urls_fn=lambda _text: [],
        )

        self.assertEqual(events, ["deterministic_hit"])
        self.assertFalse(payload.get("context_updated"))
        self.assertNotIn("identity_conflict", payload)

    def test_llm_fallback_records_fallback_without_context_update(self):
        events = []

        payload = apply_reply_runtime_effects(
            planner_decision="llm_fallback",
            tool="",
            tool_result="",
            final_reply="fallback reply",
            behavior_record_event_fn=events.append,
            extract_urls_fn=lambda _text: [],
        )

        self.assertEqual(events, ["llm_fallback"])
        self.assertFalse(payload.get("context_updated"))


if __name__ == "__main__":
    unittest.main()

