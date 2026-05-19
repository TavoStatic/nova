import unittest

from services import nova_ollama_chat


class _Response:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _HTTPError(Exception):
    def __init__(self, response):
        super().__init__(getattr(response, "text", ""))
        self.response = response


class _FailingResponse(_Response):
    def raise_for_status(self):
        raise _HTTPError(self)


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
        self.assertEqual(captured["payload"]["keep_alive"], "10m")
        system_msg = captured["payload"]["messages"][0]["content"]
        self.assertIn("local AI runtime", system_msg)
        self.assertIn("Conversation is one interface", system_msg)
        self.assertNotIn("conversational assistant", system_msg)
        self.assertIn("Persistent identity memory", system_msg)
        self.assertIn("mix=20", system_msg)
        self.assertIn("model-only chat call cannot write memory or run tools", system_msg)
        self.assertNotIn("[TOOL:web_fetch]", system_msg)
        self.assertNotIn("[TOOL:patch_apply]", system_msg)
        self.assertIn("Retrieved context", captured["payload"]["messages"][1]["content"])

    def test_assist_prompt_omits_tool_citation_examples(self):
        captured = {}

        def _post(_url, json=None, timeout=None):
            captured["payload"] = json
            return _Response({"message": {"content": "ok"}})

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
            warn_fn=lambda _msg: None,
            kill_ollama_fn=lambda: None,
            start_ollama_serve_detached_fn=lambda: None,
            sleep_fn=lambda _secs: None,
            env={"CASUAL_MODE": "0"},
        )

        self.assertEqual(out, "ok")
        system_msg = captured["payload"]["messages"][0]["content"]
        self.assertIn("model-only chat call cannot write memory or run tools", system_msg)
        self.assertNotIn("[TOOL:web_fetch]", system_msg)
        self.assertNotIn("[TOOL:patch_apply]", system_msg)

    def test_chat_failure_does_not_restart_or_retry(self):
        calls = {"count": 0}
        side_effects = []

        def _post(*_args, **_kwargs):
            calls["count"] += 1
            raise RuntimeError("first failure")

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

        self.assertEqual(out, "(error: Ollama chat failed: first failure)")
        self.assertEqual(calls["count"], 1)
        self.assertIn("error: Ollama chat failed: first failure", side_effects)
        self.assertNotIn("kill", side_effects)
        self.assertNotIn("start", side_effects)
        self.assertNotIn("sleep:2", side_effects)

    def test_chat_route_404_reports_api_contract_without_restart(self):
        side_effects = []

        def _post(*_args, **_kwargs):
            return _FailingResponse(
                {"error": "not found"},
                status_code=404,
                text='{"error":"not found"}',
            )

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

        self.assertEqual(out, "(error: Ollama chat API unavailable: /api/chat returned 404)")
        self.assertIn("error: Ollama chat API unavailable: /api/chat returned 404", side_effects)
        self.assertNotIn("kill", side_effects)
        self.assertNotIn("start", side_effects)
        self.assertNotIn("sleep:2", side_effects)

    def test_missing_model_does_not_restart_ollama(self):
        side_effects = []

        def _post(*_args, **_kwargs):
            return _FailingResponse(
                {"error": "model 'missing-model' not found"},
                status_code=404,
                text='{"error":"model \'missing-model\' not found"}',
            )

        out = nova_ollama_chat.ollama_chat(
            "hello",
            live_ollama_calls_allowed_fn=lambda: True,
            ensure_ollama_fn=lambda: None,
            identity_context_for_prompt_fn=lambda: "",
            language_mix_instruction_fn=lambda _pct: "lang",
            chat_model_fn=lambda: "missing-model",
            requests_post_fn=_post,
            ollama_base="http://127.0.0.1:11434",
            ollama_req_timeout=15,
            warn_fn=lambda msg: side_effects.append(msg),
            kill_ollama_fn=lambda: side_effects.append("kill"),
            start_ollama_serve_detached_fn=lambda: side_effects.append("start"),
            sleep_fn=lambda secs: side_effects.append(f"sleep:{secs}"),
            env={},
        )

        self.assertEqual(out, "(error: Ollama chat model missing: missing-model)")
        self.assertNotIn("kill", side_effects)
        self.assertNotIn("start", side_effects)


if __name__ == "__main__":
    unittest.main()
