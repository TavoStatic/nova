import unittest
from pathlib import Path
from unittest import mock

from services import nova_web_tools
from services.web_research_session import WebResearchSessionStore


class _FakeResponse:
    def __init__(self, *, text="", headers=None, status_code=200):
        self.text = text
        self.headers = headers or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


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

    def test_tool_web_research_stops_after_enough_hits(self):
        session = WebResearchSessionStore()
        visited_domains: list[str] = []

        out = nova_web_tools.tool_web_research(
            "state-data",
            continue_mode=False,
            explain_missing_fn=lambda _tool, _caps: "",
            policy_tools_enabled_fn=lambda: {"web": True},
            web_enabled_fn=lambda: True,
            policy_web_fn=lambda: {
                "allow_domains": ["tea.texas.gov", "txschools.gov", "region1.net"],
                "research_domains_limit": 3,
                "research_max_results": 2,
                "research_domain_timeout_sec": 3.0,
            },
            tokenize_fn=lambda text: text.split(),
            fetch_sitemap_urls_fn=lambda domain, _limit: visited_domains.append(domain) or [f"https://{domain}/sitemap.xml"],
            scan_candidate_urls_for_query_fn=lambda urls, _tokens, _max_pages, _min_score: [
                (9.5, "https://tea.texas.gov/reports-and-data", "state education data overview"),
                (8.9, "https://tea.texas.gov/reports-and-data/data", "state education data data submission"),
            ]
            if "tea.texas.gov" in urls[0]
            else [],
            seed_urls_for_domain_fn=lambda _domain, _tokens, _max_seed: [],
            crawl_domain_for_query_fn=lambda _start_url, _tokens, _max_pages, _max_depth: [],
            session_store=session,
        )

        self.assertEqual(visited_domains, [])
        self.assertIn("Web research results (allowlisted crawl) for: state-data", out)
        self.assertIn("https://tea.texas.gov/reports-and-data", out)

    def test_tool_web_research_uses_query_first_direct_fetch_before_sitemap(self):
        session = WebResearchSessionStore()

        def _scan(urls, _tokens, _max_pages, _min_score):
            self.assertTrue(any("reports-and-data/data-submission/state-data" in url for url in urls))
            return [(9.9, "https://tea.texas.gov/reports-and-data/data-submission/state-data", "state education data data submission guidance")]

        out = nova_web_tools.tool_web_research(
            "state-data",
            continue_mode=False,
            explain_missing_fn=lambda _tool, _caps: "",
            policy_tools_enabled_fn=lambda: {"web": True},
            web_enabled_fn=lambda: True,
            policy_web_fn=lambda: {
                "allow_domains": ["tea.texas.gov", "txschools.gov"],
                "research_domains_limit": 2,
                "research_max_results": 8,
                "research_domain_timeout_sec": 5.0,
            },
            tokenize_fn=lambda text: text.split(),
            fetch_sitemap_urls_fn=lambda _domain, _limit: self.fail("sitemap fallback should not run when query-first fetch finds relevant content"),
            scan_candidate_urls_for_query_fn=_scan,
            seed_urls_for_domain_fn=lambda _domain, _tokens, _max_seed: self.fail("crawl seeding should not run when query-first fetch succeeds"),
            crawl_domain_for_query_fn=lambda _start_url, _tokens, _max_pages, _max_depth: self.fail("crawl should not run when query-first fetch succeeds"),
            session_store=session,
        )

        self.assertIn("https://tea.texas.gov/reports-and-data/data-submission/state-data", out)

    def test_tool_web_research_falls_back_to_crawl_after_query_first_miss(self):
        session = WebResearchSessionStore()
        stages: list[str] = []

        def _scan(urls, _tokens, _max_pages, _min_score):
            if any("reports-and-data/data-submission/state-data" in url for url in urls):
                stages.append("query_first")
                return []
            stages.append("sitemap_scan")
            return []

        out = nova_web_tools.tool_web_research(
            "state-data",
            continue_mode=False,
            explain_missing_fn=lambda _tool, _caps: "",
            policy_tools_enabled_fn=lambda: {"web": True},
            web_enabled_fn=lambda: True,
            policy_web_fn=lambda: {
                "allow_domains": ["tea.texas.gov"],
                "research_domains_limit": 1,
                "research_max_results": 8,
                "research_domain_timeout_sec": 5.0,
            },
            tokenize_fn=lambda text: text.split(),
            fetch_sitemap_urls_fn=lambda _domain, _limit: stages.append("sitemap_fetch") or ["https://tea.texas.gov/fallback"],
            scan_candidate_urls_for_query_fn=_scan,
            seed_urls_for_domain_fn=lambda _domain, _tokens, _max_seed: stages.append("seed") or ["https://tea.texas.gov/reports-and-data/data-submission/state-data"],
            crawl_domain_for_query_fn=lambda _start_url, _tokens, _max_pages, _max_depth: stages.append("crawl") or [(9.7, "https://tea.texas.gov/reports-and-data/data-submission/state-data", "state education data fallback result")],
            session_store=session,
        )

        self.assertEqual(stages[:4], ["query_first", "sitemap_fetch", "sitemap_scan", "seed"])
        self.assertIn("crawl", stages)
        self.assertIn("https://tea.texas.gov/reports-and-data/data-submission/state-data", out)

    def test_tool_web_research_skips_seeds_after_domain_timeout(self):
        session = WebResearchSessionStore()
        seeds_called = False

        with mock.patch("services.nova_web_tools.time.perf_counter", side_effect=[0.0, 1.2]):
            out = nova_web_tools.tool_web_research(
                "state-data",
                continue_mode=False,
                explain_missing_fn=lambda _tool, _caps: "",
                policy_tools_enabled_fn=lambda: {"web": True},
                web_enabled_fn=lambda: True,
                policy_web_fn=lambda: {
                    "allow_domains": ["tea.texas.gov"],
                    "research_domains_limit": 1,
                    "research_max_results": 8,
                    "research_domain_timeout_sec": 1.0,
                },
                tokenize_fn=lambda text: text.split(),
                fetch_sitemap_urls_fn=lambda _domain, _limit: ["https://tea.texas.gov/sitemap.xml"],
                scan_candidate_urls_for_query_fn=lambda _urls, _tokens, _max_pages, _min_score: [
                    (9.5, "https://tea.texas.gov/reports-and-data", "state education data overview"),
                ],
                seed_urls_for_domain_fn=lambda _domain, _tokens, _max_seed: self.fail("seed stage should be skipped after timeout"),
                crawl_domain_for_query_fn=lambda _start_url, _tokens, _max_pages, _max_depth: [],
                session_store=session,
            )

        self.assertFalse(seeds_called)
        self.assertIn("https://tea.texas.gov/reports-and-data", out)

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

    def test_build_grounded_answer_formats_strong_sources_and_filters_weak_ones(self):
        out = nova_web_tools.build_grounded_answer(
            "state education data attendance reporting rules Texas TEA",
            max_sources=3,
            tool_web_research_fn=lambda _query: "\n".join(
                [
                    "https://tea.texas.gov/reports-and-data/data-submission/state-data",
                    "https://txschools.gov/attendance",
                    "https://example.org/cookies",
                ]
            ),
            tool_web_gather_fn=lambda url: {
                "https://tea.texas.gov/reports-and-data/data-submission/state-data": "Summary snippet: TEA explains state education data attendance submission requirements.",
                "https://txschools.gov/attendance": "Summary snippet: TXSchools documents attendance coding windows.",
                "https://example.org/cookies": "Summary snippet: You need to enable JavaScript and accept our cookie policy.",
            }[url],
        )

        self.assertIn("I found sourced information from allowlisted references:", out)
        self.assertIn("- TEA explains state education data attendance submission requirements.", out)
        self.assertIn("- TXSchools documents attendance coding windows.", out)
        self.assertIn("[source: tea.texas.gov]", out)
        self.assertIn("[source: txschools.gov]", out)
        self.assertNotIn("cookie policy", out.lower())
        self.assertNotIn("example.org", out.lower())

    def test_scan_candidate_urls_for_query_keeps_html_and_non_html_hits(self):
        responses = {
            "https://tea.texas.gov/reports-and-data/guide": _FakeResponse(
                text="<html><body>state education data calendar submission guide</body></html>",
                headers={"Content-Type": "text/html"},
            ),
            "https://tea.texas.gov/files/state-data-calendar.pdf": _FakeResponse(
                text="",
                headers={"Content-Type": "application/pdf"},
            ),
        }

        hits = nova_web_tools.scan_candidate_urls_for_query(
            list(responses.keys()),
            ["state-data", "calendar"],
            max_pages=5,
            min_score=3.0,
            requests_get_fn=lambda url, **_kwargs: responses[url],
            expand_research_terms_fn=lambda tokens: tokens,
            extract_text_from_html_content_fn=lambda text, _max_chars: "state education data calendar submission guide",
            score_research_hit_fn=lambda url, text, _terms, primary_tokens=None: 8.0 if ("state-data" in url or "state education data" in text) else 0.0,
        )

        self.assertEqual(len(hits), 2)
        by_url = {url: snippet for _score, url, snippet in hits}
        self.assertIn("https://tea.texas.gov/reports-and-data/guide", by_url)
        self.assertIn("https://tea.texas.gov/files/state-data-calendar.pdf", by_url)
        self.assertNotIn("Non-HTML source", by_url["https://tea.texas.gov/reports-and-data/guide"])
        self.assertIn("Non-HTML source", by_url["https://tea.texas.gov/files/state-data-calendar.pdf"])

    def test_fetch_sitemap_urls_follows_nested_sitemaps_and_filters_host(self):
        responses = {
            "https://tea.texas.gov/sitemap.xml": _FakeResponse(
                text="""
                <sitemapindex>
                  <sitemap><loc>https://tea.texas.gov/section.xml</loc></sitemap>
                  <url><loc>https://tea.texas.gov/direct-page</loc></url>
                </sitemapindex>
                """
            ),
            "https://tea.texas.gov/sitemap_index.xml": _FakeResponse(text="", status_code=404),
            "https://tea.texas.gov/section.xml": _FakeResponse(
                text="""
                <urlset>
                  <url><loc>https://tea.texas.gov/reports-and-data/page</loc></url>
                  <url><loc>https://example.com/outside</loc></url>
                </urlset>
                """
            ),
        }

        urls = nova_web_tools.fetch_sitemap_urls(
            "tea.texas.gov",
            limit=10,
            requests_get_fn=lambda url, **_kwargs: responses[url],
            host_allowed_fn=lambda host, allow_domains: host.endswith(allow_domains[0]),
        )

        self.assertEqual(
            urls,
            [
                "https://tea.texas.gov/direct-page",
                "https://tea.texas.gov/reports-and-data/page",
            ],
        )


if __name__ == "__main__":
    unittest.main()
