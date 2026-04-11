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

    def test_is_web_research_override_request_matches_override_phrase(self):
        self.assertTrue(
            nova_turn_helpers.is_web_research_override_request(
                "all you need is the Web",
                normalize_turn_text_fn=lambda text: text.lower(),
            )
        )

    def test_uses_prior_reference_detects_short_reference(self):
        self.assertTrue(nova_turn_helpers.uses_prior_reference("summarize that"))

    def test_extract_memory_teach_text_strips_prefix_and_filters(self):
        out = nova_turn_helpers.extract_memory_teach_text(
            "think you can remember that PEIMS applies to BISD submissions too",
            memory_should_keep_text_fn=lambda text: (True, "ok"),
        )
        self.assertEqual(out, "PEIMS applies to BISD submissions too")


if __name__ == "__main__":
    unittest.main()