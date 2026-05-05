import unittest

from services import nova_turn_helpers


class TestNovaTurnHelpers(unittest.TestCase):
    def test_retrieval_status_reply_asks_for_target(self):
        self.assertEqual(
            nova_turn_helpers.retrieval_status_reply("retreiving data"),
            "What data do you want me to retrieve?",
        )

    def test_is_location_request_detects_self_location_question(self):
        self.assertTrue(
            nova_turn_helpers.is_location_request(
                "What is your current physical location Nova?",
                normalize_turn_text_fn=lambda text: text.lower(),
            )
        )

    def test_is_location_request_does_not_treat_use_location_as_recall(self):
        self.assertFalse(
            nova_turn_helpers.is_location_request(
                "use your location",
                normalize_turn_text_fn=lambda text: text.lower(),
            )
        )

    def test_location_reply_prefers_live_device_location(self):
        reply = nova_turn_helpers.location_reply(
            runtime_device_location_payload_fn=lambda: {
                "available": True,
                "stale": False,
                "coords_text": "26.19,-97.69",
                "accuracy_m": 12.4,
            },
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
        )

        self.assertIn("My current device location is 26.19,-97.69.", reply)
        self.assertIn("Accuracy about 12m.", reply)

    def test_location_reply_falls_back_to_saved_location(self):
        reply = nova_turn_helpers.location_reply(
            runtime_device_location_payload_fn=lambda: {"available": False, "stale": True},
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
        )

        self.assertEqual(reply, "My location is Brownsville, Texas.")

    def test_location_reply_refreshes_stale_device_location(self):
        calls = {"n": 0}

        def live_payload():
            if calls["n"] == 0:
                return {"available": True, "stale": True, "coords_text": "25.90,-97.50"}
            return {
                "available": True,
                "stale": False,
                "coords_text": "25.90974,-97.50606",
                "accuracy_m": 113,
            }

        def refresh():
            calls["n"] += 1
            return (25.90974, -97.50606)

        reply = nova_turn_helpers.location_reply(
            runtime_device_location_payload_fn=live_payload,
            get_saved_location_text_fn=lambda: "",
            resolve_current_device_coords_fn=refresh,
        )

        self.assertEqual(calls["n"], 1)
        self.assertIn("My current device location is 25.90974,-97.50606.", reply)

    def test_location_reply_reports_stale_device_fix_before_saved_location(self):
        reply = nova_turn_helpers.location_reply(
            runtime_device_location_payload_fn=lambda: {
                "available": True,
                "stale": True,
                "coords_text": "25.90974,-97.50606",
                "accuracy_m": 113,
            },
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
            resolve_current_device_coords_fn=lambda: None,
        )

        self.assertIn("My last device location fix is 25.90974,-97.50606.", reply)
        self.assertIn("stale", reply)

    def test_is_web_research_override_request_matches_override_phrase(self):
        self.assertTrue(
            nova_turn_helpers.is_web_research_override_request(
                "all you need is the Web",
                normalize_turn_text_fn=lambda text: text.lower(),
            )
        )

    def test_is_web_research_override_request_rejects_database_negation(self):
        self.assertFalse(
            nova_turn_helpers.is_web_research_override_request(
                "no database for this one",
                normalize_turn_text_fn=lambda text: text.lower(),
            )
        )

    def test_uses_prior_reference_detects_short_reference(self):
        self.assertTrue(nova_turn_helpers.uses_prior_reference("summarize that"))

    def test_extract_memory_teach_text_strips_prefix_and_filters(self):
        out = nova_turn_helpers.extract_memory_teach_text(
            "think you can remember that student_data applies to BISD submissions too",
            memory_should_keep_text_fn=lambda text: (True, "ok"),
        )
        self.assertEqual(out, "student_data applies to BISD submissions too")


if __name__ == "__main__":
    unittest.main()

