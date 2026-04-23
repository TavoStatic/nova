import json
import tempfile
import unittest
from pathlib import Path

from services.policy_manager import PolicyManager


class TestPolicyManager(unittest.TestCase):
    def _make_manager(self, base: Path) -> PolicyManager:
        policy_path = base / "policy.json"
        audit_path = base / "policy_changes.jsonl"
        policy_path.write_text("{}\n", encoding="utf-8")
        return PolicyManager(policy_path, audit_path, base)

    def test_load_policy_applies_expected_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            manager = self._make_manager(Path(td))

            policy = manager.load_policy()

            self.assertIn("models", policy)
            self.assertIn("memory", policy)
            self.assertIn("web", policy)
            self.assertIn("patch", policy)
            self.assertEqual(policy["memory"].get("scope"), "private")

    def test_allow_and_remove_domain_mutates_policy(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            manager = self._make_manager(base)

            add_msg = manager.allow_domain("https://example.com", user="tester")
            self.assertIn("Added allowed domain: example.com", add_msg)

            saved = json.loads((base / "policy.json").read_text(encoding="utf-8"))
            self.assertIn("example.com", saved.get("web", {}).get("allow_domains", []))

            remove_msg = manager.remove_domain("example.com", user="tester")
            self.assertIn("Removed allowed domain: example.com", remove_msg)

            saved2 = json.loads((base / "policy.json").read_text(encoding="utf-8"))
            self.assertNotIn("example.com", saved2.get("web", {}).get("allow_domains", []))

    def test_audit_returns_recent_entries(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            manager = self._make_manager(base)

            manager.record_change("allow_domain", "example.com", "success", "added", user="tester")
            text = manager.audit(limit=5)

            self.assertIn("Recent policy changes", text)
            self.assertIn("allow_domain", text)
            self.assertIn("example.com", text)

    def test_set_memory_scope_updates_policy(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            manager = self._make_manager(base)

            msg = manager.set_memory_scope("hybrid", user="tester")
            self.assertIn("Memory scope set to hybrid", msg)

            saved = json.loads((base / "policy.json").read_text(encoding="utf-8"))
            self.assertEqual(saved.get("memory", {}).get("scope"), "hybrid")

    def test_set_search_provider_enables_web(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            manager = self._make_manager(base)

            msg = manager.set_search_provider("searxng", user="tester")
            self.assertIn("Search provider set to searxng and web enabled", msg)

            saved = json.loads((base / "policy.json").read_text(encoding="utf-8"))
            self.assertEqual(saved.get("web", {}).get("search_provider"), "searxng")
            self.assertTrue(bool(saved.get("web", {}).get("enabled")))
            self.assertTrue(bool(saved.get("tools_enabled", {}).get("web")))

    def test_set_search_provider_accepts_brave(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            manager = self._make_manager(base)

            msg = manager.set_search_provider("brave", user="tester")
            self.assertIn("Search provider set to brave and web enabled", msg)

            saved = json.loads((base / "policy.json").read_text(encoding="utf-8"))
            self.assertEqual(saved.get("web", {}).get("search_provider"), "brave")
            self.assertTrue(bool(saved.get("web", {}).get("enabled")))

    def test_set_search_provider_priority_updates_policy(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            manager = self._make_manager(base)

            msg = manager.set_search_provider_priority("stackexchange, wikipedia", user="tester")
            self.assertIn("Search provider priority set to stackexchange, wikipedia, general_web.", msg)

            saved = json.loads((base / "policy.json").read_text(encoding="utf-8"))
            self.assertEqual(saved.get("web", {}).get("search_provider_priority"), ["stackexchange", "wikipedia", "general_web"])

    def test_auto_repair_search_endpoint_updates_policy(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            manager = self._make_manager(base)
            manager.set_search_endpoint("http://127.0.0.1:8081/search", user="tester")

            msg = manager.auto_repair_search_endpoint("http://127.0.0.1:8080/search", user="tester")

            self.assertIn("Search endpoint auto-repaired to http://127.0.0.1:8080/search.", msg)
            saved = json.loads((base / "policy.json").read_text(encoding="utf-8"))
            self.assertEqual(saved.get("web", {}).get("search_api_endpoint"), "http://127.0.0.1:8080/search")

    def test_set_search_endpoint_normalizes_and_updates_policy(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            manager = self._make_manager(base)

            msg = manager.set_search_endpoint("127.0.0.1:8080/search", user="tester")
            self.assertIn("Search endpoint set to http://127.0.0.1:8080/search.", msg)

            saved = json.loads((base / "policy.json").read_text(encoding="utf-8"))
            self.assertEqual(saved.get("web", {}).get("search_api_endpoint"), "http://127.0.0.1:8080/search")
            self.assertTrue(bool(saved.get("web", {}).get("enabled")))

    def test_set_web_mode_max_updates_research_limits(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            manager = self._make_manager(base)

            msg = manager.set_web_mode("max", user="tester")
            self.assertIn("Web research mode set to max", msg)

            saved = json.loads((base / "policy.json").read_text(encoding="utf-8"))
            web = saved.get("web", {})
            self.assertEqual(web.get("research_max_depth"), 2)
            self.assertEqual(web.get("research_pages_per_domain"), 25)


if __name__ == "__main__":
    unittest.main()
