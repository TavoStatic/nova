import unittest

from services.policy_control import POLICY_CONTROL_SERVICE


class TestPolicyControlService(unittest.TestCase):
    def test_memory_scope_set_action_returns_policy_snapshot(self):
        invalidations = []
        ok, msg, extra, detail = POLICY_CONTROL_SERVICE.memory_scope_set_action(
            {"scope": "hybrid"},
            set_memory_scope_fn=lambda scope: f"Memory scope set to {scope}",
            control_policy_payload_fn=lambda: {"memory": {"scope": "hybrid"}},
            invalidate_control_status_cache_fn=lambda: invalidations.append("memory"),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "Memory scope set to hybrid")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("policy") or {}).get("memory", {}).get("scope"), "hybrid")
        self.assertEqual(invalidations, ["memory"])

    def test_search_provider_action_marks_usage_as_failure(self):
        invalidations = []
        ok, msg, extra, detail = POLICY_CONTROL_SERVICE.search_provider_action(
            {"provider": ""},
            set_search_provider_fn=lambda _provider: "Usage: search provider <html|searxng|brave>",
            control_policy_payload_fn=lambda: {"web": {"search_provider": "html"}},
            invalidate_control_status_cache_fn=lambda: invalidations.append("provider"),
        )

        self.assertFalse(ok)
        self.assertEqual(msg, "Usage: search provider <html|searxng|brave>")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("policy") or {}).get("web", {}).get("search_provider"), "html")
        self.assertEqual(invalidations, [])

    def test_search_endpoint_set_action_returns_policy_snapshot(self):
        invalidations = []
        ok, msg, extra, detail = POLICY_CONTROL_SERVICE.search_endpoint_set_action(
            {"endpoint": "http://127.0.0.1:8080/search"},
            set_search_endpoint_fn=lambda endpoint: f"Search endpoint set to {endpoint}.",
            control_policy_payload_fn=lambda: {"web": {"search_api_endpoint": "http://127.0.0.1:8080/search"}},
            invalidate_control_status_cache_fn=lambda: invalidations.append("endpoint"),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "Search endpoint set to http://127.0.0.1:8080/search.")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("policy") or {}).get("web", {}).get("search_api_endpoint"), "http://127.0.0.1:8080/search")
        self.assertEqual(invalidations, ["endpoint"])

    def test_search_provider_priority_action_returns_policy_snapshot(self):
        invalidations = []
        ok, msg, extra, detail = POLICY_CONTROL_SERVICE.search_provider_priority_set_action(
            {"priority": "stackexchange, wikipedia"},
            set_search_provider_priority_fn=lambda value: f"Search provider priority set to {value}.",
            control_policy_payload_fn=lambda: {"web": {"search_provider_priority": ["stackexchange", "wikipedia", "general_web"]}},
            invalidate_control_status_cache_fn=lambda: invalidations.append("priority"),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "Search provider priority set to stackexchange, wikipedia.")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("policy") or {}).get("web", {}).get("search_provider_priority"), ["stackexchange", "wikipedia", "general_web"])
        self.assertEqual(invalidations, ["priority"])

    def test_search_provider_toggle_action_invalidates_status_cache(self):
        invalidations = []

        ok, msg, extra, detail = POLICY_CONTROL_SERVICE.search_provider_toggle_action(
            toggle_search_provider_fn=lambda: "Search provider toggled to searxng.",
            control_policy_payload_fn=lambda: {"web": {"search_provider": "searxng"}},
            invalidate_control_status_cache_fn=lambda: invalidations.append("toggle"),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "Search provider toggled to searxng.")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("policy") or {}).get("web", {}).get("search_provider"), "searxng")
        self.assertEqual(invalidations, ["toggle"])

    def test_search_endpoint_probe_action_returns_probe_payload(self):
        ok, msg, extra, detail = POLICY_CONTROL_SERVICE.search_endpoint_probe_action(
            {"endpoint": "http://127.0.0.1:8080/search"},
            probe_search_endpoint_fn=lambda endpoint: {"ok": True, "endpoint": endpoint, "note": "status=200", "message": "reachable"},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "reachable")
        self.assertEqual(detail, msg)
        self.assertTrue((extra.get("probe") or {}).get("ok"))

    def test_policy_allow_action_passes_domain(self):
        seen = {}

        ok, msg, extra, detail = POLICY_CONTROL_SERVICE.policy_allow_action(
            {"domain": "example.com"},
            policy_allow_domain_fn=lambda domain: seen.update({"domain": domain}) or f"Added allowed domain: {domain}",
        )

        self.assertTrue(ok)
        self.assertEqual(seen.get("domain"), "example.com")
        self.assertEqual(msg, "Added allowed domain: example.com")
        self.assertEqual(detail, msg)
        self.assertEqual(extra, {})


if __name__ == "__main__":
    unittest.main()