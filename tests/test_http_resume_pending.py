import unittest
from unittest import mock

import nova_http
import nova_core


class TestHttpResumePending(unittest.TestCase):
    def setUp(self):
        nova_http.SESSION_TURNS.clear()
        self.orig_mem_should_store = nova_core.mem_should_store
        self.orig_mem_add = nova_core.mem_add
        self.orig_build_learning_context = nova_core.build_learning_context
        self.orig_render_chat_context = nova_core._render_chat_context
        self.orig_ollama_chat = nova_core.ollama_chat
        self.orig_sanitize = nova_core.sanitize_llm_reply

        nova_core.mem_should_store = lambda _text: False
        nova_core.mem_add = lambda *args, **kwargs: None
        nova_core.build_learning_context = lambda _text: ""
        nova_core._render_chat_context = lambda _turns: ""
        nova_core.ollama_chat = lambda text, retrieved_context="", **_kwargs: f"LLM:{text}"
        nova_core.sanitize_llm_reply = lambda text, _tool: text

    def tearDown(self):
        nova_core.mem_should_store = self.orig_mem_should_store
        nova_core.mem_add = self.orig_mem_add
        nova_core.build_learning_context = self.orig_build_learning_context
        nova_core._render_chat_context = self.orig_render_chat_context
        nova_core.ollama_chat = self.orig_ollama_chat
        nova_core.sanitize_llm_reply = self.orig_sanitize

    def test_resume_pending_user_turn(self):
        nova_http._append_session_turn("r1", "user", "pending question")

        with mock.patch("nova_http._invalidate_control_status_cache") as invalidate_mock:
            out = nova_http.resume_last_pending_turn("r1")
        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("resumed"))
        self.assertIn("LLM:pending question", out.get("reply", ""))
        invalidate_mock.assert_called_once_with()

        turns = nova_http._get_session_turns("r1")
        self.assertEqual(turns[-1][0], "assistant")

    def test_resume_no_pending_when_last_is_assistant(self):
        nova_http._append_session_turn("r2", "user", "hello")
        nova_http._append_session_turn("r2", "assistant", "hi")

        with mock.patch("nova_http._invalidate_control_status_cache") as invalidate_mock:
            out = nova_http.resume_last_pending_turn("r2")
        self.assertTrue(out.get("ok"))
        self.assertFalse(out.get("resumed"))
        self.assertEqual(out.get("reason"), "no_pending_user_turn")
        invalidate_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
