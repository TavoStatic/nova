import os
import unittest
from unittest import mock

import nova_core


class TestOllamaTestGuard(unittest.TestCase):
    def test_llm_classify_routing_intent_is_blocked_under_unittest_by_default(self):
        with mock.patch.object(nova_core.sys, "argv", ["python", "-m", "unittest", "discover"]), \
             mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch("nova_core.requests.post") as post_mock:
            reply = nova_core._llm_classify_routing_intent("should I bring a jacket?")
            self.assertIsNone(reply)
            post_mock.assert_not_called()

    def test_llm_classify_routing_intent_can_be_opted_in_under_unittest(self):
        class _Resp:
            def raise_for_status(self):
                return None

            @staticmethod
            def json():
                return {"message": {"content": "weather_lookup"}}

        with mock.patch.object(nova_core.sys, "argv", ["python", "-m", "unittest", "discover"]), \
             mock.patch.dict(os.environ, {"NOVA_ALLOW_LIVE_OLLAMA_TESTS": "1"}, clear=False), \
             mock.patch("nova_core.requests.post", return_value=_Resp()) as post_mock, \
             mock.patch("nova_core.get_saved_location_text", return_value="Austin, TX"):
            reply = nova_core._llm_classify_routing_intent("should I bring a jacket?")
            self.assertEqual((reply or {}).get("tool"), "weather_current_location")
            post_mock.assert_called_once()

    def test_ollama_api_up_is_blocked_under_unittest_by_default(self):
        with mock.patch.object(nova_core.sys, "argv", ["python", "-m", "unittest", "discover"]), \
             mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch("nova_core.requests.get") as get_mock:
            self.assertFalse(nova_core.ollama_api_up())
            get_mock.assert_not_called()

    def test_ollama_chat_is_blocked_under_unittest_by_default(self):
        with mock.patch.object(nova_core.sys, "argv", ["python", "-m", "unittest", "discover"]), \
             mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch("nova_core.requests.post") as post_mock:
            reply = nova_core.ollama_chat("hello")
            self.assertEqual(reply, "(error: LLM service unavailable)")
            post_mock.assert_not_called()

    def test_ollama_chat_is_blocked_under_regression_runner_test_mode(self):
        with mock.patch.object(nova_core.sys, "argv", ["scripts/run_regression.py", "behavior"]), \
             mock.patch.dict(os.environ, {"NOVA_TEST_RUNNER": "1"}, clear=False), \
             mock.patch("nova_core.requests.post") as post_mock:
            reply = nova_core.ollama_chat("hello")
            self.assertEqual(reply, "(error: LLM service unavailable)")
            post_mock.assert_not_called()

    def test_ollama_api_up_can_be_opted_in_for_unittest(self):
        class _Resp:
            def __init__(self, status_code, payload=None):
                self.status_code = status_code
                self._payload = payload if payload is not None else {}

            def json(self):
                return self._payload

        def fake_get(url, **_kwargs):
            if str(url).endswith("/api/version"):
                return _Resp(200, {"version": "0.23.3"})
            if str(url).endswith("/api/tags"):
                return _Resp(200, {"models": [{"name": "llama3.2:3b"}]})
            return _Resp(404)

        with mock.patch.object(nova_core.sys, "argv", ["python", "-m", "unittest", "discover"]), \
             mock.patch.dict(os.environ, {"NOVA_ALLOW_LIVE_OLLAMA_TESTS": "1"}, clear=False), \
             mock.patch("nova_core.requests.get", side_effect=fake_get) as get_mock, \
             mock.patch("nova_core.requests.post", return_value=_Resp(400)) as post_mock:
            self.assertTrue(nova_core.ollama_api_up())
            self.assertEqual(get_mock.call_count, 2)
            self.assertEqual(get_mock.call_args_list[0].args[0], f"{nova_core.OLLAMA_BASE}/api/version")
            self.assertEqual(get_mock.call_args_list[1].args[0], f"{nova_core.OLLAMA_BASE}/api/tags")
            post_mock.assert_called_once()

    def test_ensure_ollama_does_not_restart_when_only_model_contract_is_unready(self):
        with mock.patch.object(nova_core, "_live_ollama_calls_allowed", return_value=True), \
             mock.patch.object(nova_core, "tcp_listening", return_value=True), \
             mock.patch.object(nova_core, "ollama_server_up", return_value=True), \
             mock.patch("nova_core.start_ollama_serve_detached") as start_mock, \
             mock.patch("nova_core.kill_ollama") as kill_mock:
            nova_core.ensure_ollama()
            start_mock.assert_not_called()
            kill_mock.assert_not_called()

    def test_ensure_ollama_boot_does_not_restart_when_only_model_contract_is_unready(self):
        with mock.patch.object(nova_core, "_live_ollama_calls_allowed", return_value=True), \
             mock.patch.object(nova_core, "tcp_listening", return_value=True), \
             mock.patch.object(nova_core, "ollama_server_up", return_value=True), \
             mock.patch("nova_core.start_ollama_serve_detached") as start_mock, \
             mock.patch("nova_core.kill_ollama") as kill_mock:
            self.assertTrue(nova_core.ensure_ollama_boot())
            start_mock.assert_not_called()
            kill_mock.assert_not_called()

    def test_ensure_ollama_does_not_restart_when_api_contract_is_unready(self):
        with mock.patch.object(nova_core, "_live_ollama_calls_allowed", return_value=True), \
             mock.patch.object(nova_core, "tcp_listening", return_value=True), \
             mock.patch.object(nova_core, "ollama_server_up", return_value=False), \
             mock.patch("nova_core.start_ollama_serve_detached") as start_mock, \
             mock.patch("nova_core.kill_ollama") as kill_mock:
            self.assertFalse(nova_core.ensure_ollama())
            start_mock.assert_not_called()
            kill_mock.assert_not_called()

    def test_ensure_ollama_boot_does_not_restart_when_api_contract_is_unready(self):
        with mock.patch.object(nova_core, "_live_ollama_calls_allowed", return_value=True), \
             mock.patch.object(nova_core, "tcp_listening", return_value=True), \
             mock.patch.object(nova_core, "ollama_server_up", return_value=False), \
             mock.patch.object(nova_core, "OLLAMA_BOOT_RETRIES", 1), \
             mock.patch("nova_core.time.sleep") as sleep_mock, \
             mock.patch("nova_core.start_ollama_serve_detached") as start_mock, \
             mock.patch("nova_core.kill_ollama") as kill_mock:
            self.assertFalse(nova_core.ensure_ollama_boot())
            sleep_mock.assert_called_once_with(1)
            start_mock.assert_not_called()
            kill_mock.assert_not_called()

    def test_ensure_ollama_boot_does_not_start_process_under_unittest_by_default(self):
        with mock.patch.object(nova_core.sys, "argv", ["python", "-m", "unittest", "discover"]), \
             mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch("nova_core.start_ollama_serve_detached") as start_mock, \
             mock.patch("nova_core.kill_ollama") as kill_mock:
            self.assertFalse(nova_core.ensure_ollama_boot())
            start_mock.assert_not_called()
            kill_mock.assert_not_called()

    def test_warm_ollama_chat_model_is_blocked_under_unittest_by_default(self):
        with mock.patch.object(nova_core.sys, "argv", ["python", "-m", "unittest", "discover"]), \
             mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch("nova_core.requests.post") as post_mock:
            self.assertFalse(nova_core.warm_ollama_chat_model(reason="test"))
            post_mock.assert_not_called()

    def test_warm_ollama_chat_model_posts_bounded_probe_when_allowed(self):
        captured = {}

        class _Resp:
            def raise_for_status(self):
                return None

        def _post(url, json=None, timeout=None):
            captured["url"] = url
            captured["payload"] = json
            captured["timeout"] = timeout
            return _Resp()

        with mock.patch.object(nova_core, "_live_ollama_calls_allowed", return_value=True), \
             mock.patch.object(nova_core, "ollama_server_up", return_value=True), \
             mock.patch.object(nova_core, "chat_model", return_value="llama3.2:3b"), \
             mock.patch("nova_core.requests.post", side_effect=_post), \
             mock.patch("nova_core.ok") as ok_mock:
            self.assertTrue(nova_core.warm_ollama_chat_model(reason="http_startup"))
            self.assertEqual(captured["url"], f"{nova_core.OLLAMA_BASE}/api/chat")
            self.assertEqual(captured["payload"]["model"], "llama3.2:3b")
            self.assertEqual(captured["payload"]["keep_alive"], "10m")
            self.assertEqual(captured["payload"]["options"]["num_predict"], 1)
            self.assertEqual(captured["timeout"], nova_core.OLLAMA_WARM_TIMEOUT)
            ok_mock.assert_called_once()

    def test_ensure_ollama_does_not_start_process_under_unittest_by_default(self):
        with mock.patch.object(nova_core.sys, "argv", ["python", "-m", "unittest", "discover"]), \
             mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch("nova_core.start_ollama_serve_detached") as start_mock, \
             mock.patch("nova_core.kill_ollama") as kill_mock:
            nova_core.ensure_ollama()
            start_mock.assert_not_called()
            kill_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
