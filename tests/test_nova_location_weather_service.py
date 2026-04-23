import unittest

from services import nova_location_weather


class TestNovaLocationWeatherService(unittest.TestCase):
    def test_is_saved_location_weather_query_matches_weather_now(self):
        self.assertTrue(
            nova_location_weather.is_saved_location_weather_query(
                "weather now",
                normalize_turn_text_fn=lambda text: text.lower().strip(),
            )
        )

    def test_is_saved_location_weather_query_matches_saved_location_confirmation(self):
        self.assertTrue(
            nova_location_weather.is_saved_location_weather_query(
                "yes please use the saved location",
                normalize_turn_text_fn=lambda text: text.lower().strip(),
            )
        )

    def test_weather_location_label_prefers_saved_location(self):
        label = nova_location_weather.weather_location_label(
            "saved_location",
            "",
            get_saved_location_text_fn=lambda: "Brownsville, Texas",
            coords_from_saved_location_fn=lambda: None,
        )
        self.assertEqual(label, "Brownsville, Texas")

    def test_weather_meta_reply_includes_source_and_location(self):
        reply = nova_location_weather.weather_meta_reply(
            {"source_host": "wttr.in", "location_value": "Brownsville, Texas"}
        )
        self.assertIn("wttr.in", reply)
        self.assertIn("Brownsville, Texas", reply)

    def test_handle_location_conversation_turn_returns_location_recall(self):
        handled, reply, next_state, action = nova_location_weather.handle_location_conversation_turn(
            None,
            "where am i",
            turns=[],
            make_conversation_state_fn=lambda kind, **data: {"kind": kind, **data},
            is_location_name_query_fn=lambda text: False,
            location_name_reply_fn=lambda: "name",
            is_location_recall_query_fn=lambda text: True,
            location_recall_reply_fn=lambda: "Your saved location is Brownsville.",
            looks_like_contextual_followup_fn=lambda text: False,
            is_location_recall_state_fn=lambda state: False,
            looks_like_location_recall_followup_fn=lambda turns, text: False,
        )
        self.assertTrue(handled)
        self.assertEqual(action, "location_recall")
        self.assertEqual(reply, "Your saved location is Brownsville.")
        self.assertEqual(next_state, {"kind": "location_recall"})


if __name__ == "__main__":
    unittest.main()
