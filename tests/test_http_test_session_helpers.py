import unittest

import http_test_session_helpers


class TestHttpTestSessionHelpers(unittest.TestCase):
    def test_generated_queue_operator_note_includes_core_fields(self):
        note = http_test_session_helpers.generated_queue_operator_note(
            {
                "file": "demo.json",
                "family_id": "family-a",
                "variation_id": "variant-1",
                "latest_status": "open",
                "opportunity_reason": "drift",
                "latest_report_path": "runtime/report.json",
                "highest_priority": {"signal": "reply drift", "urgency": "high", "seam": "routing", "robustness": 0.25},
                "latest_comparison": {"diffs": [{"turn": 2, "issues": {"reply": True, "route": True}}]},
            }
        )
        self.assertIn("demo.json", note)
        self.assertIn("Latest report path", note)
        self.assertIn("turn 2", note)

    def test_investigate_generated_work_queue_item_success(self):
        def generated_work_queue(_limit):
            return {
                "items": [{"file": "demo.json", "family_id": "f1", "variation_id": "v1", "latest_status": "open"}],
                "next_item": {"file": "demo.json", "family_id": "f1", "variation_id": "v1", "latest_status": "open"},
            }

        ok, msg, extra = http_test_session_helpers.investigate_generated_work_queue_item(
            session_file="",
            session_id="",
            user_id="operator",
            generated_work_queue=generated_work_queue,
            resolve_operator_macro=lambda _name: None,
            render_operator_macro_prompt=lambda macro, payload, note: (True, note, {}),
            normalize_user_id=lambda value: str(value).strip().lower(),
            assert_session_owner=lambda sid, uid: (True, "owner_bound"),
            process_chat=lambda sid, message, user_id="": f"reply:{sid}:{user_id}:{bool(message)}",
            session_summaries=lambda _limit: [{"session_id": "operator-generated-queue", "turn_count": 1}],
        )
        self.assertTrue(ok)
        self.assertEqual(msg, "generated_work_queue_investigation_started")
        self.assertEqual(extra.get("session_id"), "operator-generated-queue")
        self.assertIn("reply:", str(extra.get("reply") or ""))

    def test_investigate_generated_work_queue_item_no_open_item(self):
        ok, msg, extra = http_test_session_helpers.investigate_generated_work_queue_item(
            session_file="",
            session_id="",
            user_id="operator",
            generated_work_queue=lambda _limit: {"items": [], "next_item": {}},
            resolve_operator_macro=lambda _name: None,
            render_operator_macro_prompt=lambda macro, payload, note: (True, note, {}),
            normalize_user_id=lambda value: str(value).strip().lower(),
            assert_session_owner=lambda sid, uid: (True, "ok"),
            process_chat=lambda sid, message, user_id="": "reply",
            session_summaries=lambda _limit: [],
        )
        self.assertFalse(ok)
        self.assertEqual(msg, "generated_work_queue_investigation_no_open_item")
        self.assertIn("work_queue", extra)


if __name__ == "__main__":
    unittest.main()
