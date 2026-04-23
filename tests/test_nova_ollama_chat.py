import unittest

from services import nova_ollama_chat


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TestNovaOllamaChatService(unittest.TestCase):
    def test_returns_error_when_live_calls_disallowed(self):
        out = nova_ollama_chat.ollama_chat(
            "hello",
            live_ollama_calls_allowed_fn=lambda: False,
            ensure_ollama_fn=lambda: None,
            identity_context_for_prompt_fn=lambda: "",
            language_mix_instruction_fn=lambda _pct: "Language preference:",
            chat_model_fn=lambda: "model",
            requests_post_fn=lambda *args, **kwargs: None,
            ollama_base="http://127.0.0.1:11434",
            ollama_req_timeout=30,
            warn_fn=lambda _msg: None,
            kill_ollama_fn=lambda: None,
            start_ollama_serve_detached_fn=lambda: None,
            sleep_fn=lambda _secs: None,
            env={},
        )

        self.assertEqual(out, "(error: LLM service unavailable)")

    def test_builds_prompt_and_returns_response_content(self):
        captured = {}

        def _post(url, json=None, timeout=None):
            captured["url"] = url
            captured["payload"] = json
            captured["timeout"] = timeout
            return _Response({"message": {"content": "hello back"}})

        out = nova_ollama_chat.ollama_chat(
            "hello",
            retrieved_context="facts",
            language_mix_spanish_pct=20,
            live_ollama_calls_allowed_fn=lambda: True,
            ensure_ollama_fn=lambda: None,
            identity_context_for_prompt_fn=lambda: "assistant_name=Nova",
            language_mix_instruction_fn=lambda pct: f"mix={pct}",
            chat_model_fn=lambda: "gpt-local",
            requests_post_fn=_post,
            ollama_base="http://127.0.0.1:11434",
            ollama_req_timeout=15,
            warn_fn=lambda _msg: None,
            kill_ollama_fn=lambda: None,
            start_ollama_serve_detached_fn=lambda: None,
            sleep_fn=lambda _secs: None,
            env={"CASUAL_MODE": "1"},
        )

        self.assertEqual(out, "hello back")
        self.assertEqual(captured["url"], "http://127.0.0.1:11434/api/chat")
        self.assertEqual(captured["payload"]["model"], "gpt-local")
        self.assertIn("Persistent identity memory", captured["payload"]["messages"][0]["content"])
        self.assertIn("mix=20", captured["payload"]["messages"][0]["content"])
        self.assertIn("Retrieved context", captured["payload"]["messages"][1]["content"])

    def test_retries_once_after_failure(self):
        calls = {"count": 0}
        side_effects = []

        def _post(*_args, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("first failure")
            return _Response({"message": {"content": "retry ok"}})

        out = nova_ollama_chat.ollama_chat(
            "hello",
            live_ollama_calls_allowed_fn=lambda: True,
            ensure_ollama_fn=lambda: None,
            identity_context_for_prompt_fn=lambda: "",
            language_mix_instruction_fn=lambda _pct: "lang",
            chat_model_fn=lambda: "gpt-local",
            requests_post_fn=_post,
            ollama_base="http://127.0.0.1:11434",
            ollama_req_timeout=15,
            warn_fn=lambda msg: side_effects.append(msg),
            kill_ollama_fn=lambda: side_effects.append("kill"),
            start_ollama_serve_detached_fn=lambda: side_effects.append("start"),
            sleep_fn=lambda secs: side_effects.append(f"sleep:{secs}"),
            env={},
        )

        self.assertEqual(out, "retry ok")
        self.assertEqual(calls["count"], 2)
        self.assertIn("kill", side_effects)
        self.assertIn("start", side_effects)


if __name__ == "__main__":
    unittest.main()