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

    def test_llm_classify_routing_intent_can_be_opted_in_for_unittest(self):
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
            self.assertEqual((reply or {}).get("intent"), "weather_lookup")
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

    def test_ollama_api_up_can_be_opted_in_for_unittest(self):
        class _Resp:
            status_code = 200

        with mock.patch.object(nova_core.sys, "argv", ["python", "-m", "unittest", "discover"]), \
             mock.patch.dict(os.environ, {"NOVA_ALLOW_LIVE_OLLAMA_TESTS": "1"}, clear=False), \
             mock.patch("nova_core.requests.get", return_value=_Resp()) as get_mock:
            self.assertTrue(nova_core.ollama_api_up())
            get_mock.assert_called_once()

    def test_ensure_ollama_boot_does_not_start_process_under_unittest_by_default(self):
        with mock.patch.object(nova_core.sys, "argv", ["python", "-m", "unittest", "discover"]), \
             mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch("nova_core.start_ollama_serve_detached") as start_mock, \
             mock.patch("nova_core.kill_ollama") as kill_mock:
            self.assertFalse(nova_core.ensure_ollama_boot())
            start_mock.assert_not_called()
            kill_mock.assert_not_called()

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