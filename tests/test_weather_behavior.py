import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import nova_core


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TestWeatherBehavior(unittest.TestCase):
    def setUp(self):
        self.orig_policy_path = nova_core.POLICY_PATH
        self.orig_statefile = nova_core.DEFAULT_STATEFILE
        self.orig_device_location_file = nova_core.DEVICE_LOCATION_FILE
        self.orig_windows_device_resolver = nova_core._resolve_windows_device_coords
        self.orig_mem_add = nova_core.mem_add
        self.orig_mem_audit = nova_core.mem_audit
        self.orig_requests_get = nova_core.requests.get
        self.tmp = tempfile.TemporaryDirectory()
        self.policy_path = Path(self.tmp.name) / "policy.json"
        self.state_path = Path(self.tmp.name) / "core_state.json"
        self.device_location_path = Path(self.tmp.name) / "device_location.json"
        nova_core.DEFAULT_STATEFILE = self.state_path
        nova_core.DEVICE_LOCATION_FILE = self.device_location_path
        nova_core._resolve_windows_device_coords = lambda *args, **kwargs: None
        nova_core.mem_add = lambda *args, **kwargs: None
        nova_core.mem_audit = lambda _query: json.dumps({"results": []})

    def tearDown(self):
        nova_core.POLICY_PATH = self.orig_policy_path
        nova_core.DEFAULT_STATEFILE = self.orig_statefile
        nova_core.DEVICE_LOCATION_FILE = self.orig_device_location_file
        nova_core._resolve_windows_device_coords = self.orig_windows_device_resolver
        nova_core.mem_add = self.orig_mem_add
        nova_core.mem_audit = self.orig_mem_audit
        nova_core.requests.get = self.orig_requests_get
        self.tmp.cleanup()

    def _write_policy(self, allow_domains):
        self.policy_path.write_text(
            json.dumps(
                {
                    "allowed_root": "C:/Nova",
                    "tools_enabled": {"web": True},
                    "web": {"enabled": True, "allow_domains": allow_domains, "max_bytes": 1000},
                }
            ),
            encoding="utf-8",
        )
        nova_core.POLICY_PATH = self.policy_path

    def _write_policy_with_style(self, allow_domains, style):
        self.policy_path.write_text(
            json.dumps(
                {
                    "allowed_root": "C:/Nova",
                    "tools_enabled": {"web": True},
                    "web": {
                        "enabled": True,
                        "allow_domains": allow_domains,
                        "max_bytes": 1000,
                        "weather_response_style": style,
                    },
                }
            ),
            encoding="utf-8",
        )
        nova_core.POLICY_PATH = self.policy_path

    def test_weather_unavailable_without_structured_source(self):
        self._write_policy(["weather.com"])
        out = nova_core.tool_weather("mcallen tx")
        self.assertIn("reliable structured weather source", out)
        self.assertIn("policy allow api.weather.gov", out)

    def test_weather_nws_success(self):
        self._write_policy(["api.weather.gov"])

        calls = {"n": 0}

        def fake_get(url, headers=None, timeout=0):
            calls["n"] += 1
            if "api.weather.gov/points/" in url:
                return _FakeResponse(
                    {
                        "properties": {
                            "forecast": "https://api.weather.gov/gridpoints/BRO/64,48/forecast"
                        }
                    }
                )
            self.assertIn("/forecast", url)
            return _FakeResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "name": "Tonight",
                                "temperature": 74,
                                "temperatureUnit": "F",
                                "shortForecast": "Mostly Clear",
                                "windSpeed": "10 mph",
                                "windDirection": "SE",
                            }
                        ]
                    }
                }
            )

        nova_core.requests.get = fake_get
        out = nova_core.tool_weather("brownsville")
        self.assertIn("Brownsville, TX:", out)
        self.assertIn("Tonight: 74", out)
        self.assertIn("[source: api.weather.gov]", out)
        self.assertEqual(calls["n"], 2)

    def test_weather_formatter_deduplicates_prefixes(self):
        out = nova_core._format_weather_output("Brownsville, TX", "Forecast for Brownsville, TX: Tomorrow: Sunny. [source: api.weather.gov]")
        self.assertEqual(out.lower().count("forecast for"), 0)
        self.assertEqual(out.lower().count("brownsville, tx"), 1)

    def test_weather_tool_style_outputs_single_tool_prefix(self):
        self._write_policy_with_style(["api.weather.gov"], "tool")

        def fake_get(url, headers=None, timeout=0):
            if "api.weather.gov/points/" in url:
                return _FakeResponse({"properties": {"forecast": "https://api.weather.gov/gridpoints/BRO/64,48/forecast"}})
            return _FakeResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "name": "Tomorrow",
                                "temperature": 86,
                                "temperatureUnit": "F",
                                "shortForecast": "Partly cloudy",
                                "windSpeed": "8 mph",
                                "windDirection": "SE",
                            }
                        ]
                    }
                }
            )

        nova_core.requests.get = fake_get
        out = nova_core.tool_weather("brownsville")
        self.assertTrue(out.startswith("Forecast for "))
        self.assertEqual(out.lower().count("forecast for"), 1)

    def test_weather_current_location_requires_coords(self):
        self._write_policy(["api.weather.gov"])
        out = nova_core.handle_commands("weather current location")
        self.assertIn("need a confirmed location or coordinates", out)

    def test_sanitize_blocks_ungrounded_weather_fetch_claim(self):
        self._write_policy(["weather.com"])
        out = nova_core.sanitize_llm_reply("I fetched the weather data but didn't display it directly.", tool_context="")
        self.assertIn("reliable structured weather source", out)

    def test_sanitize_blocks_fake_weather_action_promise(self):
        out = nova_core.sanitize_llm_reply("I'll try to find out the weather for our location. Let me check...", tool_context="")
        self.assertIn("haven't actually run the weather tool", out)
        self.assertIn("our current location", out)

    def test_location_coords_command_saves_state(self):
        out = nova_core.handle_commands("location coords 25.9017,-97.4975")
        self.assertIn("Saved current location coordinates", out)

        st = nova_core.read_core_state(self.state_path)
        self.assertIn("location_coords", st)
        self.assertAlmostEqual(float(st["location_coords"]["lat"]), 25.9017)
        self.assertAlmostEqual(float(st["location_coords"]["lon"]), -97.4975)

    def test_weather_current_location_uses_saved_coords(self):
        self._write_policy(["api.weather.gov"])
        nova_core.handle_commands("location coords 25.9017,-97.4975")

        calls = {"n": 0}

        def fake_get(url, headers=None, timeout=0):
            calls["n"] += 1
            if "api.weather.gov/points/" in url:
                return _FakeResponse({"properties": {"forecast": "https://api.weather.gov/gridpoints/BRO/64,48/forecast"}})
            return _FakeResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "name": "Tonight",
                                "temperature": 74,
                                "temperatureUnit": "F",
                                "shortForecast": "Mostly Clear",
                                "windSpeed": "10 mph",
                                "windDirection": "SE",
                            }
                        ]
                    }
                }
            )

        nova_core.requests.get = fake_get
        out = nova_core.handle_commands("weather current location")
        self.assertIn("25.9017,-97.4975:", out)
        self.assertIn("[source: api.weather.gov]", out)
        self.assertEqual(calls["n"], 2)

    def test_weather_current_location_uses_live_runtime_location(self):
        self._write_policy(["api.weather.gov"])
        ok, msg, live = nova_core.set_runtime_device_location({
            "lat": 30.2672,
            "lon": -97.7431,
            "accuracy_m": 18,
            "source": "browser_watch",
            "permission_state": "granted",
            "captured_ts": time.time(),
        })
        self.assertTrue(ok)
        self.assertEqual(msg, "device_location_updated")
        self.assertTrue(live.get("available"))

        calls = {"n": 0}

        def fake_get(url, headers=None, timeout=0):
            calls["n"] += 1
            if "api.weather.gov/points/" in url:
                self.assertIn("30.2672,-97.7431", url)
                return _FakeResponse({"properties": {"forecast": "https://api.weather.gov/gridpoints/EWX/156,97/forecast"}})
            return _FakeResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "name": "Tonight",
                                "temperature": 78,
                                "temperatureUnit": "F",
                                "shortForecast": "Mostly Clear",
                                "windSpeed": "7 mph",
                                "windDirection": "S",
                            }
                        ]
                    }
                }
            )

        nova_core.requests.get = fake_get
        out = nova_core.handle_commands("weather current location")
        self.assertIn("30.2672,-97.7431:", out)
        self.assertIn("[source: api.weather.gov]", out)
        self.assertEqual(calls["n"], 2)

    def test_resolve_current_device_coords_uses_windows_fallback_and_persists_snapshot(self):
        nova_core._resolve_windows_device_coords = lambda *args, **kwargs: {
            "lat": 47.6062,
            "lon": -122.3321,
            "accuracy_m": 21,
            "source": "windows_geolocator",
            "permission_state": "granted",
            "captured_ts": time.time(),
        }

        coords = nova_core.resolve_current_device_coords()

        self.assertEqual(coords, (47.6062, -122.3321))
        live = nova_core.runtime_device_location_payload()
        self.assertTrue(live.get("available"))
        self.assertEqual(live.get("source"), "windows_geolocator")

    def test_runtime_device_location_payload_reports_backend_provider_status(self):
        with mock.patch("nova_core.os.name", "nt"), mock.patch("nova_core.importlib.util.find_spec", return_value=object()):
            live = nova_core.runtime_device_location_payload()

        provider = live.get("backend_provider") or {}
        self.assertTrue(provider.get("available"))
        self.assertTrue(provider.get("winsdk_installed"))
        self.assertEqual(provider.get("name"), "windows_geolocator")

    def test_natural_weather_phrase_routes_deterministically(self):
        self._write_policy(["api.weather.gov"])
        out = nova_core.handle_commands("nova give me the weather")
        self.assertIn("need a confirmed location or coordinates", out)
        self.assertIn("My location is", out)

    def test_natural_weather_phrase_uses_saved_location_text(self):
        self._write_policy(["api.weather.gov"])
        nova_core.set_location_text("Brownsville TX")

        def fake_get(url, headers=None, timeout=0):
            if "api.weather.gov/points/" in url:
                return _FakeResponse({"properties": {"forecast": "https://api.weather.gov/gridpoints/BRO/64,48/forecast"}})
            return _FakeResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "name": "Tonight",
                                "temperature": 74,
                                "temperatureUnit": "F",
                                "shortForecast": "Mostly Clear",
                                "windSpeed": "10 mph",
                                "windDirection": "SE",
                            }
                        ]
                    }
                }
            )

        nova_core.requests.get = fake_get
        out = nova_core.handle_commands("can you give me the current weather in your location ?")
        self.assertIn("Brownsville, TX:", out)
        self.assertIn("[source: api.weather.gov]", out)

    def test_use_physical_location_routes_to_brownsville(self):
        self._write_policy(["api.weather.gov"])
        nova_core.set_location_text("Brownsville TX")

        calls = {"n": 0}

        def fake_get(url, headers=None, timeout=0):
            calls["n"] += 1
            if "api.weather.gov/points/" in url:
                return _FakeResponse({"properties": {"forecast": "https://api.weather.gov/gridpoints/BRO/64,48/forecast"}})
            return _FakeResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "name": "Tonight",
                                "temperature": 74,
                                "temperatureUnit": "F",
                                "shortForecast": "Mostly Clear",
                                "windSpeed": "10 mph",
                                "windDirection": "SE",
                            }
                        ]
                    }
                }
            )

        nova_core.requests.get = fake_get
        out = nova_core.handle_commands("use your physical location")
        self.assertIn("Brownsville, TX:", out)
        self.assertIn("[source: api.weather.gov]", out)
        self.assertEqual(calls["n"], 2)

    def test_use_your_location_nova_routes_to_brownsville(self):
        self._write_policy(["api.weather.gov"])
        nova_core.set_location_text("Brownsville TX")

        def fake_get(url, headers=None, timeout=0):
            if "api.weather.gov/points/" in url:
                return _FakeResponse({"properties": {"forecast": "https://api.weather.gov/gridpoints/BRO/64,48/forecast"}})
            return _FakeResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "name": "Tonight",
                                "temperature": 74,
                                "temperatureUnit": "F",
                                "shortForecast": "Mostly Clear",
                                "windSpeed": "10 mph",
                                "windDirection": "SE",
                            }
                        ]
                    }
                }
            )

        nova_core.requests.get = fake_get
        out = nova_core.handle_commands("use your location nova")
        self.assertIn("Brownsville, TX:", out)
        self.assertIn("[source: api.weather.gov]", out)

    def test_weather_for_current_physical_locaiton_typo_routes_to_brownsville(self):
        self._write_policy(["api.weather.gov"])
        nova_core.set_location_text("Brownsville TX")

        def fake_get(url, headers=None, timeout=0):
            if "api.weather.gov/points/" in url:
                return _FakeResponse({"properties": {"forecast": "https://api.weather.gov/gridpoints/BRO/64,48/forecast"}})
            return _FakeResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "name": "Tonight",
                                "temperature": 74,
                                "temperatureUnit": "F",
                                "shortForecast": "Mostly Clear",
                                "windSpeed": "10 mph",
                                "windDirection": "SE",
                            }
                        ]
                    }
                }
            )

        nova_core.requests.get = fake_get
        out = nova_core.handle_commands("Give me the weather for your current physical locaiton nova")
        self.assertIn("Brownsville, TX:", out)
        self.assertIn("[source: api.weather.gov]", out)


class TestLlmRoutingIntentClassifier(unittest.TestCase):
    """Validates _llm_classify_routing_intent — the non-keyword routing path.

    Every input here deliberately contains NO trigger keyword (no 'weather',
    no 'forecast').  If these tests fail, we have domesticated the test suite
    back to keyword triggers.
    """

    def setUp(self):
        self.orig_post = nova_core.requests.post
        self.orig_location = nova_core.get_saved_location_text

    def tearDown(self):
        nova_core.requests.post = self.orig_post
        nova_core.get_saved_location_text = self.orig_location

    def _mock_llm_label(self, label: str):
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {"content": label}}

        nova_core.requests.post = lambda *a, **kw: _Resp()

    def test_jacket_question_classifies_as_weather(self):
        """'should I bring a jacket?' — no keyword, LLM must classify it."""
        self._mock_llm_label("weather_lookup")
        nova_core.get_saved_location_text = lambda: ""
        with mock.patch.dict("os.environ", {"NOVA_ALLOW_LIVE_OLLAMA_TESTS": "1"}, clear=False):
            result = nova_core._llm_classify_routing_intent("should I bring a jacket today?")
        self.assertIsNotNone(result)
        self.assertEqual(result.get("intent"), "weather_lookup")
        self.assertEqual(result.get("weather_mode"), "clarify")

    def test_umbrella_question_with_saved_location(self):
        """'do I need an umbrella?' with saved location → current_location mode."""
        self._mock_llm_label("weather_lookup")
        nova_core.get_saved_location_text = lambda: "Brownsville TX"
        with mock.patch.dict("os.environ", {"NOVA_ALLOW_LIVE_OLLAMA_TESTS": "1"}, clear=False):
            result = nova_core._llm_classify_routing_intent("do I need an umbrella?")
        self.assertIsNotNone(result)
        self.assertEqual(result.get("intent"), "weather_lookup")
        self.assertEqual(result.get("weather_mode"), "current_location")
        self.assertEqual(result.get("location_value"), "Brownsville TX")

    def test_hot_outside_question_with_saved_location(self):
        """'how hot is it outside?' — implicit outdoor conditions, no keyword."""
        self._mock_llm_label("weather_lookup")
        nova_core.get_saved_location_text = lambda: "McAllen TX"
        with mock.patch.dict("os.environ", {"NOVA_ALLOW_LIVE_OLLAMA_TESTS": "1"}, clear=False):
            result = nova_core._llm_classify_routing_intent("how hot is it outside right now?")
        self.assertIsNotNone(result)
        self.assertEqual(result.get("weather_mode"), "current_location")
        self.assertEqual(result.get("location_value"), "McAllen TX")

    def test_general_chat_returns_none(self):
        """LLM says general_chat → no route returned (falls through to LLM chat)."""
        self._mock_llm_label("general_chat")
        nova_core.get_saved_location_text = lambda: ""
        with mock.patch.dict("os.environ", {"NOVA_ALLOW_LIVE_OLLAMA_TESTS": "1"}, clear=False):
            result = nova_core._llm_classify_routing_intent("tell me something interesting about the moon")
        self.assertIsNone(result)

    def test_ollama_failure_returns_none(self):
        """If Ollama is unreachable, routing falls through gracefully — no crash."""
        def _fail(*a, **kw):
            raise ConnectionError("ollama down")
        nova_core.requests.post = _fail
        with mock.patch.dict("os.environ", {"NOVA_ALLOW_LIVE_OLLAMA_TESTS": "1"}, clear=False):
            result = nova_core._llm_classify_routing_intent("is it going to rain this afternoon?")
        self.assertIsNone(result)

    def test_empty_text_returns_none(self):
        result = nova_core._llm_classify_routing_intent("")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
