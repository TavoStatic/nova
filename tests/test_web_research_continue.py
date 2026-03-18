import json
import tempfile
import unittest
from pathlib import Path

import nova_core


class TestWebResearchContinue(unittest.TestCase):
    def setUp(self):
        self.orig_policy_path = nova_core.POLICY_PATH
        self.orig_fetch_sitemap = nova_core._fetch_sitemap_urls
        self.orig_scan_candidates = nova_core._scan_candidate_urls_for_query
        self.orig_seed_urls = nova_core._seed_urls_for_domain
        self.orig_crawl = nova_core._crawl_domain_for_query

        self.tmp = tempfile.TemporaryDirectory()
        self.policy_path = Path(self.tmp.name) / "policy.json"
        self.policy_path.write_text(
            json.dumps(
                {
                    "allowed_root": "C:/Nova",
                    "tools_enabled": {"web": True},
                    "web": {
                        "enabled": True,
                        "allow_domains": ["example.com"],
                        "research_domains_limit": 1,
                        "research_pages_per_domain": 2,
                        "research_scan_pages_per_domain": 2,
                        "research_max_depth": 1,
                        "research_seeds_per_domain": 2,
                        "research_max_results": 2,
                        "research_min_score": 0.0,
                    },
                }
            ),
            encoding="utf-8",
        )
        nova_core.POLICY_PATH = self.policy_path

        # Reset session cache for deterministic tests.
        nova_core.WEB_RESEARCH_LAST_QUERY = ""
        nova_core.WEB_RESEARCH_LAST_RESULTS = []
        nova_core.WEB_RESEARCH_CURSOR = 0

        hits = [
            (9.0, "https://example.com/a", "A"),
            (8.0, "https://example.com/b", "B"),
            (7.0, "https://example.com/c", "C"),
            (6.0, "https://example.com/d", "D"),
        ]

        nova_core._fetch_sitemap_urls = lambda d, limit=0: ["https://example.com/a"]
        nova_core._scan_candidate_urls_for_query = lambda urls, toks, max_pages=0, min_score=0.0: hits[:2]
        nova_core._seed_urls_for_domain = lambda d, toks, max_seed=0: ["https://example.com/"]
        nova_core._crawl_domain_for_query = lambda start, toks, max_pages=0, max_depth=0: hits[2:]

    def tearDown(self):
        nova_core.POLICY_PATH = self.orig_policy_path
        nova_core._fetch_sitemap_urls = self.orig_fetch_sitemap
        nova_core._scan_candidate_urls_for_query = self.orig_scan_candidates
        nova_core._seed_urls_for_domain = self.orig_seed_urls
        nova_core._crawl_domain_for_query = self.orig_crawl
        self.tmp.cleanup()

    def test_web_research_then_continue_paginates(self):
        first = nova_core.tool_web_research("test query")
        self.assertIn("1. [9.0] https://example.com/a", first)
        self.assertIn("2. [8.0] https://example.com/b", first)
        self.assertIn("web continue", first)

        second = nova_core.tool_web_research("", continue_mode=True)
        self.assertIn("3. [7.0] https://example.com/c", second)
        self.assertIn("4. [6.0] https://example.com/d", second)

    def test_continue_without_session(self):
        nova_core.WEB_RESEARCH_LAST_RESULTS = []
        out = nova_core.tool_web_research("", continue_mode=True)
        self.assertIn("No active web research session", out)


if __name__ == "__main__":
    unittest.main()
