import json
import os
import tempfile
import unittest
from pathlib import Path

import nova_core


class _FakeResp:
    def __init__(self, text="", payload=None):
        self.text = text
        self._payload = payload if payload is not None else {}
        self._raise_error = None

    def with_error(self, error):
        self._raise_error = error
        return self

    def raise_for_status(self):
        if self._raise_error is not None:
            raise self._raise_error
        return None

    def json(self):
        return self._payload


class TestWebSearchAPI(unittest.TestCase):
    def setUp(self):
        self.orig_policy_path = nova_core.POLICY_PATH
        self.orig_requests_get = nova_core.requests.get
        self.orig_env = os.environ.get("BRAVE_SEARCH_API_KEY")

        self.tmp = tempfile.TemporaryDirectory()
        self.policy_path = Path(self.tmp.name) / "policy.json"

    def tearDown(self):
        nova_core.POLICY_PATH = self.orig_policy_path
        nova_core.requests.get = self.orig_requests_get
        if self.orig_env is None:
            os.environ.pop("BRAVE_SEARCH_API_KEY", None)
        else:
            os.environ["BRAVE_SEARCH_API_KEY"] = self.orig_env
        self.tmp.cleanup()

    def _write_policy(self, provider="brave"):
        self.policy_path.write_text(
            json.dumps(
                {
                    "allowed_root": "C:/Nova",
                    "tools_enabled": {"web": True},
                    "web": {
                        "enabled": True,
                        "allow_domains": ["example.com"],
                        "search_provider": provider,
                        "search_api_key_env": "BRAVE_SEARCH_API_KEY",
                    },
                }
            ),
            encoding="utf-8",
        )
        nova_core.POLICY_PATH = self.policy_path

    def test_web_search_uses_api_provider_when_configured(self):
        self._write_policy(provider="brave")
        os.environ["BRAVE_SEARCH_API_KEY"] = "test-key"

        def fake_get(url, params=None, headers=None, timeout=0):
            if "api.search.brave.com" in url:
                return _FakeResp(
                    payload={
                        "web": {
                            "results": [
                                {"title": "Example A", "url": "https://example.com/a"},
                                {"title": "Blocked", "url": "https://notallowed.com/x"},
                            ]
                        }
                    }
                )
            return _FakeResp(text="")

        nova_core.requests.get = fake_get
        out = nova_core.tool_web_search("test query")
        self.assertIn("provider=api", out)
        self.assertIn("Example A", out)
        self.assertIn("https://example.com/a", out)
        self.assertNotIn("notallowed.com", out)

    def test_web_search_falls_back_to_html_when_api_key_missing(self):
        self._write_policy(provider="brave")
        os.environ.pop("BRAVE_SEARCH_API_KEY", None)

        def fake_get(url, params=None, headers=None, timeout=0):
            if "duckduckgo.com/html" in url:
                return _FakeResp(text='<a class="result__a" href="https://example.com/b">B</a>')
            return _FakeResp(text="")

        nova_core.requests.get = fake_get
        out = nova_core.tool_web_search("test query")
        self.assertIn("provider=html", out)
        self.assertIn("https://example.com/b", out)

    def test_web_search_uses_searxng_provider(self):
        self._write_policy(provider="searxng")

        def fake_get(url, params=None, headers=None, timeout=0):
            if "search" in url and params and params.get("format") == "json":
                return _FakeResp(
                    payload={
                        "results": [
                            {"title": "Example S", "url": "https://example.com/s"},
                            {"title": "Blocked", "url": "https://blocked.com/no"},
                        ]
                    }
                )
            return _FakeResp(text="")

        nova_core.requests.get = fake_get
        out = nova_core.tool_web_search("test query")
        self.assertIn("provider=api:searxng", out)
        self.assertIn("Example S", out)
        self.assertIn("https://example.com/s", out)
        self.assertNotIn("blocked.com", out)

    def test_web_search_404_returns_actionable_message(self):
        self._write_policy(provider="searxng")

        class _Err(Exception):
            pass

        def fake_get(url, params=None, headers=None, timeout=0):
            if "search" in url and params and params.get("format") == "json":
                return _FakeResp().with_error(_Err("404 Client Error: Not Found for url: http://127.0.0.1:8080/search"))
            if "duckduckgo.com/html" in url:
                return _FakeResp(text="")
            return _FakeResp(text="")

        nova_core.requests.get = fake_get
        out = nova_core.tool_web_search("test query")
        self.assertIn("local web search backend is unavailable", out.lower())
        self.assertIn("docker", out.lower())
        self.assertIn("127.0.0.1:8080/search", out)
        self.assertIn("web research <query>", out)
        self.assertIn("web <url>", out)

    def test_web_search_connection_refused_returns_local_backend_message(self):
        self._write_policy(provider="searxng")

        class _Err(Exception):
            pass

        def fake_get(url, params=None, headers=None, timeout=0):
            if "search" in url and params and params.get("format") == "json":
                return _FakeResp().with_error(_Err("HTTPConnectionPool(host='127.0.0.1', port=8080): Max retries exceeded with url: /search?q=test (Caused by NewConnectionError: Failed to establish a new connection: [WinError 10061] No connection could be made because the target machine actively refused it)"))
            if "duckduckgo.com/html" in url:
                return _FakeResp(text="")
            return _FakeResp(text="")

        nova_core.requests.get = fake_get
        out = nova_core.tool_web_search("test query")
        self.assertIn("local web search backend is unavailable", out.lower())
        self.assertIn("docker", out.lower())


if __name__ == "__main__":
    unittest.main()
