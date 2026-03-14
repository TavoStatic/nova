import unittest

import nova_http
import nova_core


class TestHttpIdentityChat(unittest.TestCase):
    def setUp(self):
        nova_http.SESSION_TURNS.clear()
        self.orig_remember_name_origin = nova_core.remember_name_origin
        self.orig_get_name_origin_story = nova_core.get_name_origin_story
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
        nova_core.ollama_chat = lambda text, retrieved_context="": f"LLM:{text}"
        nova_core.sanitize_llm_reply = lambda text, _tool: text

    def tearDown(self):
        nova_core.remember_name_origin = self.orig_remember_name_origin
        nova_core.get_name_origin_story = self.orig_get_name_origin_story
        nova_core.mem_should_store = self.orig_mem_should_store
        nova_core.mem_add = self.orig_mem_add
        nova_core.build_learning_context = self.orig_build_learning_context
        nova_core._render_chat_context = self.orig_render_chat_context
        nova_core.ollama_chat = self.orig_ollama_chat
        nova_core.sanitize_llm_reply = self.orig_sanitize

    def test_remember_this_stores_name_origin(self):
        calls = []

        def fake_store(text: str) -> str:
            calls.append(text)
            return "Stored. I will remember this as the story behind my name."

        nova_core.remember_name_origin = fake_store

        out = nova_http.process_chat(
            "s1",
            "Here is the story behind your name. remember this nova... Nova was named by Gus.",
        )
        self.assertIn("Stored.", out)
        self.assertEqual(len(calls), 1)

    def test_last_question_reply_uses_session_history(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: ""

        out1 = nova_http.process_chat("s2", "do you have any rules")
        self.assertIn("I follow strict operating rules", out1)

        out2 = nova_http.process_chat("s2", "what was my last question ?")
        self.assertIn("do you have any rules", out2.lower())

    def test_name_origin_question_prefers_saved_story(self):
        nova_core.remember_name_origin = lambda _text: "Stored"
        nova_core.get_name_origin_story = lambda: "My creator Gus named me Nova to symbolize light and discovery."

        out = nova_http.process_chat("s3", "so do you now know where your name comes from ?")
        self.assertIn("creator gus", out.lower())


if __name__ == "__main__":
    unittest.main()
