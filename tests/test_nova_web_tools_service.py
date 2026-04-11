import unittest
from pathlib import Path

from services import nova_web_tools
from services.web_research_session import WebResearchSessionStore


class TestNovaWebToolsService(unittest.TestCase):
    def test_tool_web_fetch_surfaces_allowlist_message(self):
        out = nova_web_tools.tool_web_fetch(
            "https://blocked.example.com",
            explain_missing_fn=lambda _tool, _caps: "",
            policy_tools_enabled_fn=lambda: {"web": True},
            web_fetch_fn=lambda _url: {"ok": False, "error": "Domain not allowed: blocked.example.com"},
            web_allowlist_message_fn=lambda url: f"ALLOWLIST:{url}",
        )

        self.assertEqual(out, "ALLOWLIST:https://blocked.example.com")

    def test_tool_web_search_reports_local_backend_unavailable(self):
        def _requests_get(*_args, **_kwargs):
            raise RuntimeError("html fallback unavailable")

        out = nova_web_tools.tool_web_search(
            "district calendar",
            explain_missing_fn=lambda _tool, _caps: "",
            policy_tools_enabled_fn=lambda: {"web": True},
            web_enabled_fn=lambda: True,
            policy_web_fn=lambda: {
                "allow_domains": ["tea.texas.gov"],
                "search_provider": "searxng",
                "search_api_endpoint": "http://127.0.0.1:8080/search",
            },
            host_allowed_fn=lambda _host, _domains: True,
            decode_search_href_fn=lambda href: href,
            probe_search_endpoint_fn=lambda *_args, **_kwargs: {"ok": False, "note": "404 not found"},
            web_allowlist_message_fn=lambda query: f"ALLOWLIST:{query}",
            requests_get_fn=_requests_get,
        )

        self.assertIn("Local web search backend is unavailable", out)
        self.assertIn("127.0.0.1:8080/search", out)

    def test_tool_web_research_continue_uses_cached_session(self):
        session = WebResearchSessionStore()
        session.set_state(
            "district calendar",
            [(9.5, "https://tea.texas.gov/calendar", "Important district calendar details")],
            cursor=0,
        )

        out = nova_web_tools.tool_web_research(
            "",
            continue_mode=True,
            explain_missing_fn=lambda _tool, _caps: "",
            policy_tools_enabled_fn=lambda: {"web": True},
            web_enabled_fn=lambda: True,
            policy_web_fn=lambda: {"allow_domains": ["tea.texas.gov"], "research_max_results": 5},
            tokenize_fn=lambda text: text.split(),
            fetch_sitemap_urls_fn=lambda _domain, _limit: [],
            scan_candidate_urls_for_query_fn=lambda _urls, _tokens, _max_pages, _min_score: [],
            seed_urls_for_domain_fn=lambda _domain, _tokens, _max_seed: [],
            crawl_domain_for_query_fn=lambda _start_url, _tokens, _max_pages, _max_depth: [],
            session_store=session,
        )

        self.assertIn("Web research results (continued) for: district calendar", out)
        self.assertIn("https://tea.texas.gov/calendar", out)
        self.assertIn("End of cached research results.", out)

    def test_tool_web_gather_returns_summary_snippet(self):
        out = nova_web_tools.tool_web_gather(
            "https://tea.texas.gov/example",
            explain_missing_fn=lambda _tool, _caps: "",
            policy_tools_enabled_fn=lambda: {"web": True},
            web_fetch_fn=lambda _url: {
                "ok": True,
                "path": str(Path("c:/Nova/knowledge/web/example.html")),
                "content_type": "text/html",
                "bytes": 1234,
            },
            web_allowlist_message_fn=lambda url: f"ALLOWLIST:{url}",
            extract_text_from_path_fn=lambda _path, _max_chars: "Short summary",
        )

        self.assertIn("Summary snippet:", out)
        self.assertIn("Short summary", out)


if __name__ == "__main__":
    unittest.main()
