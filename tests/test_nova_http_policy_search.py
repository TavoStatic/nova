import unittest

from services.nova_http_policy_search import HTTP_POLICY_SEARCH_SERVICE
from services.policy_control import POLICY_CONTROL_SERVICE


class _Core:
    def __init__(self):
        self.calls = []
        self.endpoint = "http://current/search"

    def policy_allow_domain(self, domain):
        self.calls.append(("allow", domain))
        return f"allowed:{domain}"

    def policy_remove_domain(self, domain):
        self.calls.append(("remove", domain))
        return f"removed:{domain}"

    def set_web_mode(self, mode):
        self.calls.append(("web_mode", mode))
        return f"mode:{mode}"

    def set_memory_scope(self, scope):
        self.calls.append(("memory_scope", scope))
        return f"memory:{scope}"

    def set_search_provider(self, provider):
        self.calls.append(("provider", provider))
        return f"provider:{provider}"

    def toggle_search_provider(self):
        self.calls.append(("toggle",))
        return "provider:toggled"

    def set_search_endpoint(self, endpoint):
        self.calls.append(("endpoint", endpoint))
        return f"endpoint:{endpoint}"

    def set_search_provider_priority(self, priority):
        self.calls.append(("priority", priority))
        return f"priority:{priority}"

    def get_search_endpoint(self):
        self.calls.append(("get_endpoint",))
        return self.endpoint

    def probe_search_endpoint(self, endpoint):
        self.calls.append(("probe", endpoint))
        return {"ok": True, "endpoint": endpoint, "message": f"reachable:{endpoint}"}


class TestNovaHttpPolicySearchService(unittest.TestCase):
    def _scope(self, core: _Core, invalidations: list[str] | None = None):
        invalidations = invalidations if invalidations is not None else []
        return {
            "POLICY_CONTROL_SERVICE": POLICY_CONTROL_SERVICE,
            "nova_core": core,
            "_control_policy_payload": lambda: {"web": {"search_provider": "html"}},
            "_invalidate_control_status_cache": lambda: invalidations.append("status"),
        }

    def test_policy_hooks_bind_core_policy_actions(self):
        core = _Core()
        hooks = HTTP_POLICY_SEARCH_SERVICE.action_hooks_from_runtime(self._scope(core))

        ok, msg, extra, detail = hooks["policy_allow_action_fn"]({"domain": "example.com"})

        self.assertTrue(ok)
        self.assertEqual(msg, "allowed:example.com")
        self.assertEqual(detail, msg)
        self.assertEqual(extra, {})
        self.assertEqual(core.calls, [("allow", "example.com")])

    def test_search_provider_hook_returns_policy_snapshot_and_invalidates_cache(self):
        core = _Core()
        invalidations = []
        hooks = HTTP_POLICY_SEARCH_SERVICE.action_hooks_from_runtime(self._scope(core, invalidations))

        ok, msg, extra, detail = hooks["search_provider_action_fn"]({"provider": "html"})

        self.assertTrue(ok)
        self.assertEqual(msg, "provider:html")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("policy") or {}).get("web", {}).get("search_provider"), "html")
        self.assertEqual(invalidations, ["status"])
        self.assertEqual(core.calls, [("provider", "html")])

    def test_memory_scope_hook_returns_policy_snapshot_and_invalidates_cache(self):
        core = _Core()
        invalidations = []
        hooks = HTTP_POLICY_SEARCH_SERVICE.action_hooks_from_runtime(self._scope(core, invalidations))

        ok, msg, extra, detail = hooks["memory_scope_set_action_fn"]({"scope": "hybrid"})

        self.assertTrue(ok)
        self.assertEqual(msg, "memory:hybrid")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("policy") or {}).get("web", {}).get("search_provider"), "html")
        self.assertEqual(invalidations, ["status"])
        self.assertEqual(core.calls, [("memory_scope", "hybrid")])

    def test_probe_hook_uses_current_endpoint_when_payload_is_empty(self):
        core = _Core()
        hooks = HTTP_POLICY_SEARCH_SERVICE.action_hooks_from_runtime(self._scope(core))

        ok, msg, extra, detail = hooks["search_endpoint_probe_action_fn"]({})

        self.assertTrue(ok)
        self.assertEqual(msg, "reachable:http://current/search")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("probe") or {}).get("endpoint"), "http://current/search")
        self.assertEqual(core.calls, [("get_endpoint",), ("probe", "http://current/search")])

    def test_toggle_hook_ignores_payload_and_invalidates_cache(self):
        core = _Core()
        invalidations = []
        hooks = HTTP_POLICY_SEARCH_SERVICE.action_hooks_from_runtime(self._scope(core, invalidations))

        ok, msg, extra, detail = hooks["search_provider_toggle_action_fn"]({"unused": True})

        self.assertTrue(ok)
        self.assertEqual(msg, "provider:toggled")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("policy") or {}).get("web", {}).get("search_provider"), "html")
        self.assertEqual(invalidations, ["status"])
        self.assertEqual(core.calls, [("toggle",)])


if __name__ == "__main__":
    unittest.main()
