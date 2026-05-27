import json
import time
import unittest

from services import nova_location_weather


class TestNovaLocationWeatherService(unittest.TestCase):
    def test_saved_location_text_reads_core_state_only(self):
        location = nova_location_weather.get_saved_location_text(
            read_core_state_fn=lambda _path: {"location_text": "  Brownsville,   Texas  "},
            default_statefile="state.json",
        )

        self.assertEqual(location, "Brownsville, Texas")

    def test_saved_location_text_does_not_read_memory_audit_rows(self):
        location = nova_location_weather.get_saved_location_text(
            read_core_state_fn=lambda _path: {},
            default_statefile="state.json",
        )

        self.assertEqual(location, "")

    def test_coords_from_saved_location_reads_structured_core_state(self):
        coords = nova_location_weather.coords_from_saved_location(
            read_core_state_fn=lambda _path: {"location_coords": {"lat": 25.90974, "lon": -97.50606}},
            default_statefile="state.json",
        )

        self.assertEqual(coords, (25.90974, -97.50606))

    def test_parse_lat_lon_accepts_bare_coordinates_with_accuracy_suffix(self):
        coords = nova_location_weather.parse_lat_lon("25.90974,-97.50606 | 113m accuracy")

        self.assertEqual(coords, (25.90974, -97.50606))

    def test_live_device_location_summary_prefers_fresh_payload(self):
        summary = nova_location_weather.live_device_location_summary(
            runtime_device_location_payload_fn=lambda: {
                "available": True,
                "stale": False,
                "lat": 25.90974,
                "lon": -97.50606,
                "coords_text": "25.90974,-97.50606",
                "accuracy_m": 113,
                "source": "windows_geolocator",
            }
        )

        self.assertEqual(summary.get("coords_text"), "25.90974,-97.50606")
        self.assertEqual(summary.get("accuracy_m"), 113.0)
        self.assertEqual(summary.get("label"), "Brownsville, TX")

    def test_live_device_location_summary_refreshes_stale_payload_before_use(self):
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
            }

        def refresh():
            calls["n"] += 1
            return (25.90974, -97.50606)

        summary = nova_location_weather.live_device_location_summary(
            runtime_device_location_payload_fn=live_payload,
            resolve_current_device_coords_fn=refresh,
        )

        self.assertEqual(calls["n"], 1)
        self.assertEqual(summary.get("label"), "Brownsville, TX")

    def test_device_location_status_payload_marks_stale_by_age(self):
        payload = nova_location_weather.device_location_status_payload(
            {
                "lat": 25.90974,
                "lon": -97.50606,
                "captured_ts": time.time() - 600,
                "accuracy_m": 113,
                "source": "browser_watch",
            },
            max_age_sec=300,
            runtime_device_backend_provider_fn=lambda: {"name": "test_provider"},
        )

        self.assertTrue(payload.get("available"))
        self.assertEqual(payload.get("status"), "stale")
        self.assertTrue(payload.get("stale"))

    def test_format_weather_output_uses_structured_label_and_summary(self):
        reply = nova_location_weather.format_weather_output(
            "brownsville",
            "Forecast for Brownsville: Sunny, 90F. [source: api.weather.gov]",
            weather_response_style_fn=lambda: "concise",
        )

        self.assertEqual(reply, "Brownsville, TX: Sunny, 90F. [source: api.weather.gov]")

    def test_tool_weather_uses_api_weather_coords_and_formatter(self):
        calls = []

        reply = nova_location_weather.tool_weather(
            "78521",
            policy_tools_enabled_fn=lambda: {"web": True},
            web_enabled_fn=lambda: True,
            weather_source_host_fn=lambda: "api.weather.gov",
            weather_unavailable_message_fn=lambda: "missing weather source",
            coords_for_location_hint_fn=lambda location: nova_location_weather.coords_for_location_hint(location),
            need_confirmed_location_message_fn=lambda: "need coordinates",
            get_weather_for_location_fn=lambda lat, lon: calls.append((lat, lon)) or "Sunny. [source: api.weather.gov]",
            format_weather_output_fn=lambda label, summary: f"{label}: {summary}",
        )

        self.assertEqual(calls, [(nova_location_weather.BROWNSVILLE_LAT, nova_location_weather.BROWNSVILLE_LON)])
        self.assertEqual(reply, "78521: Sunny. [source: api.weather.gov]")

    def test_runtime_device_location_payload_reports_error_for_bad_json(self):
        class BadFile:
            def exists(self):
                return True

            def read_text(self, encoding="utf-8"):
                return "{"

        payload = nova_location_weather.runtime_device_location_payload(
            device_location_file=BadFile(),
            device_location_status_payload_fn=lambda snapshot, max_age_sec: {"available": bool(snapshot)},
            runtime_device_backend_provider_fn=lambda: {"name": "test_provider"},
        )

        self.assertFalse(payload.get("available"))
        self.assertEqual(payload.get("status"), "error")


if __name__ == "__main__":
    unittest.main()
