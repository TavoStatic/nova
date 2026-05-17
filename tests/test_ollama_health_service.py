import unittest

from services.ollama_health import build_ollama_health_payload


class _Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class TestOllamaHealthService(unittest.TestCase):
    def test_requires_tags_and_chat_route(self):
        payload = build_ollama_health_payload(
            requests_get_fn=lambda *_args, **_kwargs: _Response(200),
            requests_post_fn=lambda *_args, **_kwargs: _Response(400),
            ollama_base="http://127.0.0.1:11434",
            timeout=1,
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["server_ok"])
        self.assertTrue(payload["tags_ok"])
        self.assertTrue(payload["chat_route_ok"])
        self.assertEqual(payload["status"], "ok")

    def test_configured_chat_model_must_exist_in_tags(self):
        payload = build_ollama_health_payload(
            requests_get_fn=lambda *_args, **_kwargs: _Response(
                200,
                {"models": [{"name": "llama3.2:3b"}, {"model": "qwen2.5vl:7b"}]},
            ),
            requests_post_fn=lambda *_args, **_kwargs: _Response(400),
            ollama_base="http://127.0.0.1:11434",
            chat_model="llama3.1:8b",
            timeout=1,
        )

        self.assertFalse(payload["ok"])
        self.assertTrue(payload["server_ok"])
        self.assertTrue(payload["tags_ok"])
        self.assertTrue(payload["chat_route_ok"])
        self.assertFalse(payload["model_available"])
        self.assertEqual(payload["model_status"], "missing")
        self.assertEqual(payload["status"], "chat_model_missing")
        self.assertEqual(payload["available_models"], ["llama3.2:3b", "qwen2.5vl:7b"])

    def test_configured_chat_model_available_is_ok(self):
        payload = build_ollama_health_payload(
            requests_get_fn=lambda *_args, **_kwargs: _Response(
                200,
                {"models": [{"name": "llama3.2:3b"}]},
            ),
            requests_post_fn=lambda *_args, **_kwargs: _Response(400),
            ollama_base="http://127.0.0.1:11434",
            chat_model="llama3.2:3b",
            timeout=1,
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["server_ok"])
        self.assertTrue(payload["model_available"])
        self.assertEqual(payload["model_status"], "available")
        self.assertEqual(payload["status"], "ok")

    def test_surfaces_ollama_server_version_and_api_contract(self):
        def fake_get(url, **_kwargs):
            if str(url).endswith("/api/version"):
                return _Response(200, {"version": "0.23.3"})
            return _Response(200, {"models": [{"name": "llama3.2:3b"}]})

        payload = build_ollama_health_payload(
            requests_get_fn=fake_get,
            requests_post_fn=lambda *_args, **_kwargs: _Response(400),
            ollama_base="http://127.0.0.1:11434",
            chat_model="llama3.2:3b",
            timeout=1,
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["version_ok"])
        self.assertEqual(payload["version"], "0.23.3")
        self.assertEqual(payload["api_contract_status"], "chat_api_ready")
        self.assertIn("version=0.23.3", payload["info"])

    def test_tags_green_chat_404_is_not_ok(self):
        payload = build_ollama_health_payload(
            requests_get_fn=lambda *_args, **_kwargs: _Response(200),
            requests_post_fn=lambda *_args, **_kwargs: _Response(404),
            ollama_base="http://127.0.0.1:11434",
            timeout=1,
        )

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["server_ok"])
        self.assertTrue(payload["tags_ok"])
        self.assertFalse(payload["chat_route_ok"])
        self.assertEqual(payload["status"], "chat_route_unreachable")
        self.assertEqual(payload["api_contract_status"], "chat_api_missing_or_incompatible")

    def test_live_call_guard_blocks_without_network(self):
        calls = []

        payload = build_ollama_health_payload(
            requests_get_fn=lambda *_args, **_kwargs: calls.append("get"),
            requests_post_fn=lambda *_args, **_kwargs: calls.append("post"),
            ollama_base="http://127.0.0.1:11434",
            timeout=1,
            live_calls_allowed=False,
        )

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["server_ok"])
        self.assertEqual(payload["status"], "blocked_by_test_guard")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
