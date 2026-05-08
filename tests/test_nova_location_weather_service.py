import unittest
import json

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

    def test_saved_location_text_ignores_test_memory_rows(self):
        payload = {
            "results": [
                {
                    "kind": "test",
                    "source": "unittest",
                    "preview": "integration-test-memory: bravo-98765",
                },
                {
                    "kind": "profile",
                    "source": "typed",
                    "preview": "location: Brownsville, Texas",
                },
            ]
        }

        location = nova_location_weather.get_saved_location_text(
            read_core_state_fn=lambda _path: {},
            default_statefile="state.json",
            normalize_location_preview_fn=lambda value: value.replace("location:", "").strip(),
            mem_audit_fn=lambda _query: json.dumps(payload),
        )

        self.assertEqual(location, "Brownsville, Texas")

    def test_saved_location_text_does_not_return_only_test_fixture(self):
        payload = {
            "results": [
                {
                    "kind": "test",
                    "source": "unittest",
                    "preview": "integration-test-memory: bravo-98765",
                }
            ]
        }

        location = nova_location_weather.get_saved_location_text(
            read_core_state_fn=lambda _path: {},
            default_statefile="state.json",
            normalize_location_preview_fn=lambda value: value.strip(),
            mem_audit_fn=lambda _query: json.dumps(payload),
        )

        self.assertEqual(location, "")

    def test_saved_location_text_does_not_return_json_teach_blob(self):
        payload = {
            "results": [
                {
                    "kind": "teach",
                    "source": "user_teach",
                    "preview": '{"orig": "I should not have claimed Notepad was opened", "corr": "Sorry."}',
                }
            ]
        }

        location = nova_location_weather.get_saved_location_text(
            read_core_state_fn=lambda _path: {},
            default_statefile="state.json",
            normalize_location_preview_fn=lambda value: value.strip(),
            mem_audit_fn=lambda _query: json.dumps(payload),
        )

        self.assertEqual(location, "")

    def test_weather_meta_reply_includes_source_and_location(self):
        reply = nova_location_weather.weather_meta_reply(
            {"source_host": "wttr.in", "location_value": "Brownsville, Texas"}
        )
        self.assertIn("wttr.in", reply)
        self.assertIn("Brownsville, Texas", reply)

    def test_extract_location_fact_accepts_bare_coordinates_with_accuracy(self):
        fact = nova_location_weather.extract_location_fact(
            "25.90974,-97.50606 | 113m accuracy",
            normalize_location_preview_fn=lambda value: value.strip(),
        )

        self.assertEqual(fact, "25.90974,-97.50606")

    def test_location_name_reply_prefers_live_device_location_label(self):
        reply = nova_location_weather.location_name_reply(
            get_saved_location_text_fn=lambda: "",
            runtime_device_location_payload_fn=lambda: {
                "available": True,
                "stale": False,
                "lat": 25.90974,
                "lon": -97.50606,
                "coords_text": "25.90974,-97.50606",
                "accuracy_m": 113,
                "source": "windows_geolocator",
            },
        )

        self.assertEqual(reply, "That location is Brownsville, TX.")

    def test_location_recall_reply_prefers_live_device_location(self):
        reply = nova_location_weather.location_recall_reply(
            get_saved_location_text_fn=lambda: "",
            runtime_device_location_payload_fn=lambda: {
                "available": True,
                "stale": False,
                "lat": 25.90974,
                "lon": -97.50606,
                "coords_text": "25.90974,-97.50606",
                "accuracy_m": 113,
                "source": "windows_geolocator",
            },
        )

        self.assertIn("Your current device location is 25.90974,-97.50606.", reply)
        self.assertIn("Accuracy about 113m.", reply)
        self.assertIn("near Brownsville, TX", reply)

    def test_location_name_reply_refreshes_stale_live_device_location(self):
        calls = {"n": 0}

        def live_payload():
            if calls["n"] == 0:
                return {"available": True, "stale": True, "lat": 25.90974, "lon": -97.50606}
            return {
                "available": True,
                "stale": False,
                "lat": 25.90974,
                "lon": -97.50606,
                "coords_text": "25.90974,-97.50606",
                "accuracy_m": 113,
            }

        def refresh():
            calls["n"] += 1
            return (25.90974, -97.50606)

        reply = nova_location_weather.location_name_reply(
            get_saved_location_text_fn=lambda: "",
            runtime_device_location_payload_fn=live_payload,
            resolve_current_device_coords_fn=refresh,
        )

        self.assertEqual(calls["n"], 1)
        self.assertEqual(reply, "That location is Brownsville, TX.")

    def test_location_name_reply_uses_stale_device_location_with_warning(self):
        reply = nova_location_weather.location_name_reply(
            get_saved_location_text_fn=lambda: "",
            runtime_device_location_payload_fn=lambda: {
                "available": True,
                "stale": True,
                "lat": 25.90974,
                "lon": -97.50606,
                "coords_text": "25.90974,-97.50606",
            },
            resolve_current_device_coords_fn=lambda: None,
        )

        self.assertEqual(reply, "That last device location is near Brownsville, TX.")


if __name__ == "__main__":
    unittest.main()
