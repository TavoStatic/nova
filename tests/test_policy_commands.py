import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import nova_core


class TestPolicyCommands(unittest.TestCase):
    def setUp(self):
        self.orig_policy_path = nova_core.POLICY_PATH
        self.orig_policy_audit_log = nova_core.POLICY_AUDIT_LOG
        self.tmp = tempfile.TemporaryDirectory()
        self.policy_path = Path(self.tmp.name) / "policy.json"
        self.audit_path = Path(self.tmp.name) / "policy_changes.jsonl"
        self.policy_path.write_text(
            json.dumps(
                {
                    "allowed_root": "C:/Nova",
                    "web": {
                        "enabled": True,
                        "allow_domains": ["tea.texas.gov"],
                        "max_bytes": 1000,
                    },
                    "tools_enabled": {"web": True},
                }
            ),
            encoding="utf-8",
        )
        nova_core.POLICY_PATH = self.policy_path
        nova_core.POLICY_AUDIT_LOG = self.audit_path

    def tearDown(self):
        nova_core.POLICY_PATH = self.orig_policy_path
        nova_core.POLICY_AUDIT_LOG = self.orig_policy_audit_log
        self.tmp.cleanup()

    def test_typo_domains_command_is_context_aware(self):
        out = nova_core.handle_commands("list the domanins")
        self.assertIn('It looks like you meant "domains".', out)
        self.assertIn("tea.texas.gov", out)

    def test_policy_allow_adds_domain(self):
        out = nova_core.handle_commands("policy allow https://weather.com")
        self.assertIn("Added allowed domain: weather.com", out)

        saved = json.loads(self.policy_path.read_text(encoding="utf-8"))
        domains = (saved.get("web") or {}).get("allow_domains") or []
        self.assertIn("weather.com", domains)

    def test_policy_allow_duplicate_domain(self):
        first = nova_core.handle_commands("policy allow weather.com")
        self.assertIn("Added allowed domain: weather.com", first)

        second = nova_core.handle_commands("policy allow weather.com")
        self.assertIn("Domain already allowed: weather.com", second)

    def test_policy_allow_writes_audit_log(self):
        nova_core.handle_commands("policy allow weather.com")
        self.assertTrue(self.audit_path.exists())
        lines = [ln for ln in self.audit_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertGreaterEqual(len(lines), 1)
        last = json.loads(lines[-1])
        self.assertEqual(last.get("action"), "allow_domain")
        self.assertEqual(last.get("target"), "weather.com")
        self.assertEqual(last.get("result"), "success")

    def test_policy_remove_domain(self):
        out = nova_core.handle_commands("policy remove tea.texas.gov")
        self.assertIn("Removed allowed domain: tea.texas.gov", out)

        saved = json.loads(self.policy_path.read_text(encoding="utf-8"))
        domains = (saved.get("web") or {}).get("allow_domains") or []
        self.assertNotIn("tea.texas.gov", domains)

    def test_policy_remove_not_found(self):
        out = nova_core.handle_commands("policy remove weather.com")
        self.assertIn("Domain not found in allowlist: weather.com", out)

    def test_policy_audit_command(self):
        nova_core.handle_commands("policy allow weather.com")
        out = nova_core.handle_commands("policy audit 5")
        self.assertIn("Recent policy changes", out)
        self.assertIn("action=allow_domain", out)

    def test_web_mode_max_updates_policy(self):
        out = nova_core.handle_commands("web mode max")
        self.assertIn("Web research mode set to max", out)

        saved = json.loads(self.policy_path.read_text(encoding="utf-8"))
        web = saved.get("web") or {}
        self.assertEqual(web.get("research_max_depth"), 2)
        self.assertEqual(web.get("research_pages_per_domain"), 25)

    def test_web_mode_status(self):
        out = nova_core.handle_commands("web mode")
        self.assertIn("Current web research limits", out)
        self.assertIn("research_max_depth", out)

    def test_probe_search_endpoint_auto_detects_local_fallback_port(self):
        class _Response:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"results": []}

        with mock.patch("nova_core.requests.get", side_effect=[RuntimeError("connection refused"), _Response()]):
            probe = nova_core.probe_search_endpoint("http://127.0.0.1:8081/search", timeout=0.1, persist_repair=True)

        self.assertTrue(probe.get("ok"))
        self.assertTrue(probe.get("auto_detected"))
        self.assertTrue(probe.get("repaired"))
        self.assertEqual(probe.get("resolved_endpoint"), "http://127.0.0.1:8080/search")
        self.assertIn("auto-detected=http://127.0.0.1:8080/search", str(probe.get("note") or ""))

        saved = json.loads(self.policy_path.read_text(encoding="utf-8"))
        self.assertEqual((saved.get("web") or {}).get("search_api_endpoint"), "http://127.0.0.1:8080/search")

    def test_probe_search_endpoint_failure_reports_configured_endpoint_and_checked_candidates(self):
        with mock.patch(
            "nova_core.requests.get",
            side_effect=[
                RuntimeError("configured refused"),
                RuntimeError("localhost refused"),
                RuntimeError("fallback refused"),
                RuntimeError("localhost fallback refused"),
            ],
        ):
            probe = nova_core.probe_search_endpoint("http://127.0.0.1:8080/search", timeout=0.1, persist_repair=True)

        self.assertFalse(probe.get("ok"))
        self.assertEqual(probe.get("endpoint"), "http://127.0.0.1:8080/search")
        self.assertIn("configured_failed=error:configured refused", str(probe.get("note") or ""))
        self.assertIn("http://127.0.0.1:8080/search => error:configured refused", str(probe.get("note") or ""))
        self.assertEqual(len(probe.get("candidate_errors") or []), 4)

    def test_wikipedia_lookup_returns_summary_and_related_pages(self):
        class _Response:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        search_payload = {
            "query": {
                "search": [
                    {"title": "Ada Lovelace"},
                    {"title": "Analytical Engine"},
                ]
            }
        }
        summary_payload = {
            "title": "Ada Lovelace",
            "extract": "Ada Lovelace was an English mathematician.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Ada_Lovelace"}},
        }

        with mock.patch("nova_core.requests.get", side_effect=[_Response(search_payload), _Response(summary_payload)]):
            out = nova_core.tool_wikipedia_lookup("Ada Lovelace")

        self.assertIn("Wikipedia summary for: Ada Lovelace", out)
        self.assertIn("https://en.wikipedia.org/wiki/Ada_Lovelace", out)
        self.assertIn("Analytical Engine", out)

    def test_stackexchange_search_returns_ranked_results(self):
        class _Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "items": [
                        {
                            "title": "FastAPI OAuth invalid_grant error",
                            "link": "https://stackoverflow.com/questions/123",
                            "score": 8,
                            "answer_count": 2,
                            "is_answered": True,
                            "tags": ["python", "fastapi", "oauth-2.0"],
                        }
                    ]
                }

        with mock.patch("nova_core.requests.get", return_value=_Response()):
            out = nova_core.tool_stackexchange_search("fastapi oauth invalid_grant")

        self.assertIn("StackExchange results for: fastapi oauth invalid_grant", out)
        self.assertIn("stackoverflow.com/questions/123", out)

    def test_load_policy_sets_safety_envelope_defaults(self):
        loaded = nova_core.load_policy()

        envelope = loaded.get("safety_envelope") or {}
        self.assertTrue(envelope.get("enabled"))
        self.assertEqual(envelope.get("mode"), "observe")
        self.assertEqual(envelope.get("human_veto_first_n"), 3)

        kidney_cfg = loaded.get("kidney") or {}
        self.assertTrue(kidney_cfg.get("enabled"))
        self.assertEqual(kidney_cfg.get("mode"), "observe")
        self.assertEqual(kidney_cfg.get("definition_max_age_days"), 7)


if __name__ == "__main__":
    unittest.main()
