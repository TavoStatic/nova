"""
Authoritative behavior tests — web tool routing.

Tests that web tool functions behave correctly when policy allows/blocks them
and when dependency tools are missing.
Does NOT inspect source code or depend on internal function names.
"""
from __future__ import annotations

import unittest

from services.nova_web_tools import tool_web_fetch, tool_web_search, tool_wikipedia_lookup


def _no_missing(tool: str, required: list[str]) -> str:
    return ""


def _missing(tool: str, required: list[str]) -> str:
    return f"Missing required tools: {required}"


def _policy_web_enabled() -> dict:
    return {"web": True}


def _policy_web_disabled() -> dict:
    return {"web": False}


class TestWebFetchRouting(unittest.TestCase):

    def test_web_fetch_blocked_when_web_policy_disabled(self):
        reply = tool_web_fetch(
            "https://example.com",
            explain_missing_fn=_no_missing,
            policy_tools_enabled_fn=_policy_web_disabled,
            web_fetch_fn=lambda url: {"ok": True, "path": "/tmp/x", "content_type": "text/html", "bytes": 100},
            web_allowlist_message_fn=lambda url: "not allowed",
        )
        self.assertIn("disabled", reply.lower())

    def test_web_fetch_blocked_when_tool_missing(self):
        reply = tool_web_fetch(
            "https://example.com",
            explain_missing_fn=_missing,
            policy_tools_enabled_fn=_policy_web_enabled,
            web_fetch_fn=lambda url: {"ok": True, "path": "/tmp/x", "content_type": "text/html", "bytes": 100},
            web_allowlist_message_fn=lambda url: "not allowed",
        )
        self.assertIn("Missing", reply)

    def test_web_fetch_returns_ok_when_allowed(self):
        reply = tool_web_fetch(
            "https://example.com",
            explain_missing_fn=_no_missing,
            policy_tools_enabled_fn=_policy_web_enabled,
            web_fetch_fn=lambda url: {"ok": True, "path": "/tmp/result.html", "content_type": "text/html", "bytes": 512},
            web_allowlist_message_fn=lambda url: "not allowed",
        )
        self.assertIn("[OK]", reply)

    def test_web_fetch_returns_allowlist_message_on_not_allowed_error(self):
        reply = tool_web_fetch(
            "https://blocked.example.com",
            explain_missing_fn=_no_missing,
            policy_tools_enabled_fn=_policy_web_enabled,
            web_fetch_fn=lambda url: {"ok": False, "error": "url not allowed"},
            web_allowlist_message_fn=lambda url: f"domain {url} is not on the allowlist",
        )
        self.assertIn("not on the allowlist", reply)

    def test_web_fetch_returns_fail_on_generic_error(self):
        reply = tool_web_fetch(
            "https://example.com",
            explain_missing_fn=_no_missing,
            policy_tools_enabled_fn=_policy_web_enabled,
            web_fetch_fn=lambda url: {"ok": False, "error": "connection refused"},
            web_allowlist_message_fn=lambda url: "not allowed",
        )
        self.assertIn("[FAIL]", reply)


class TestWebSearchRouting(unittest.TestCase):

    def test_web_search_blocked_when_policy_disabled(self):
        reply = tool_web_search(
            "texas attendance",
            explain_missing_fn=_no_missing,
            policy_tools_enabled_fn=_policy_web_disabled,
            web_enabled_fn=lambda: True,
            policy_web_fn=lambda: {"allow_domains": ["example.com"]},
            host_allowed_fn=lambda url, domains: True,
            decode_search_href_fn=lambda href: href,
            probe_search_endpoint_fn=lambda *a, **kw: {"ok": True, "results": []},
            web_allowlist_message_fn=lambda url: "not allowed",
            requests_get_fn=lambda *a, **kw: None,
        )
        self.assertIn("disabled", reply.lower())

    def test_web_search_blocked_when_missing_tool(self):
        reply = tool_web_search(
            "texas attendance",
            explain_missing_fn=_missing,
            policy_tools_enabled_fn=_policy_web_enabled,
            web_enabled_fn=lambda: True,
            policy_web_fn=lambda: {"allow_domains": ["example.com"]},
            host_allowed_fn=lambda url, domains: True,
            decode_search_href_fn=lambda href: href,
            probe_search_endpoint_fn=lambda *a, **kw: {"ok": True, "results": []},
            web_allowlist_message_fn=lambda url: "not allowed",
            requests_get_fn=lambda *a, **kw: None,
        )
        self.assertIn("Missing", reply)

    def test_web_search_no_allow_domains_returns_unavailable(self):
        # When allow_domains is empty, web search is unavailable regardless of other policy
        reply = tool_web_search(
            "texas attendance",
            explain_missing_fn=_no_missing,
            policy_tools_enabled_fn=_policy_web_enabled,
            web_enabled_fn=lambda: True,
            policy_web_fn=lambda: {},
            host_allowed_fn=lambda url, domains: True,
            decode_search_href_fn=lambda href: href,
            probe_search_endpoint_fn=lambda *a, **kw: {"ok": True, "results": []},
            web_allowlist_message_fn=lambda url: "not allowed",
            requests_get_fn=lambda *a, **kw: None,
        )
        self.assertIn("unavailable", reply.lower())


class TestWikipediaRoutingBlocking(unittest.TestCase):

    def test_wikipedia_blocked_when_policy_disabled(self):
        reply = tool_wikipedia_lookup(
            "Python language",
            explain_missing_fn=_no_missing,
            policy_tools_enabled_fn=_policy_web_disabled,
            web_enabled_fn=lambda: True,
            requests_get_fn=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not be called")),
        )
        self.assertIn("disabled", reply.lower())

    def test_wikipedia_blocked_when_web_fn_disabled(self):
        reply = tool_wikipedia_lookup(
            "Python language",
            explain_missing_fn=_no_missing,
            policy_tools_enabled_fn=_policy_web_enabled,
            web_enabled_fn=lambda: False,
            requests_get_fn=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not be called")),
        )
        self.assertIn("disabled", reply.lower())

    def test_wikipedia_empty_query_returns_usage(self):
        reply = tool_wikipedia_lookup(
            "",
            explain_missing_fn=_no_missing,
            policy_tools_enabled_fn=_policy_web_enabled,
            web_enabled_fn=lambda: True,
            requests_get_fn=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not be called")),
        )
        self.assertIn("Usage", reply)


if __name__ == "__main__":
    unittest.main()
