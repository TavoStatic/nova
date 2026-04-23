import unittest

from services import nova_search_endpoint


class TestNovaSearchEndpoint(unittest.TestCase):
    def test_search_endpoint_candidates_include_local_fallbacks(self):
        candidates = nova_search_endpoint.search_endpoint_candidates("http://127.0.0.1:8081/search")

        self.assertEqual(candidates[0], "http://127.0.0.1:8081/search")
        self.assertIn("http://127.0.0.1:8080/search", candidates)
        self.assertIn("http://localhost:8081/search", candidates)

    def test_probe_search_endpoint_auto_repairs_local_fallback(self):
        calls = []

        class _Response:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"results": []}

        def _requests_get(url, **_kwargs):
            calls.append(url)
            if url == "http://127.0.0.1:8081/search":
                raise RuntimeError("connection refused")
            return _Response()

        repaired = []
        probe = nova_search_endpoint.probe_search_endpoint(
            "http://127.0.0.1:8081/search",
            timeout=0.1,
            persist_repair=True,
            get_search_endpoint_fn=lambda: "http://127.0.0.1:8081/search",
            auto_repair_search_endpoint_fn=lambda endpoint: repaired.append(endpoint) or f"repaired:{endpoint}",
            requests_get_fn=_requests_get,
        )

        self.assertTrue(probe.get("ok"))
        self.assertEqual(probe.get("resolved_endpoint"), "http://127.0.0.1:8080/search")
        self.assertTrue(probe.get("repaired"))
        self.assertEqual(repaired, ["http://127.0.0.1:8080/search"])
        self.assertEqual(calls[:2], ["http://127.0.0.1:8081/search", "http://127.0.0.1:8080/search"])


if __name__ == "__main__":
    unittest.main()