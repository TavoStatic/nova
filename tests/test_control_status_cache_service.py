import threading
import unittest

from services.control_status_cache import CONTROL_STATUS_CACHE_SERVICE


class TestControlStatusCacheService(unittest.TestCase):
    def test_invalidate_resets_cache(self):
        cache = {"computed_at": 10.0, "payload": {"ok": True}}
        lock = threading.Lock()

        CONTROL_STATUS_CACHE_SERVICE.invalidate(cache, lock=lock)

        self.assertEqual(cache["computed_at"], 0.0)
        self.assertIsNone(cache["payload"])

    def test_cached_payload_reuses_recent_value(self):
        cache = {"computed_at": 5.0, "payload": {"ok": True, "value": 1}}
        lock = threading.Lock()
        calls = []

        result = CONTROL_STATUS_CACHE_SERVICE.cached_payload(
            cache,
            lock=lock,
            max_age_seconds=10.0,
            monotonic_fn=lambda: 10.0,
            compute_payload_fn=lambda: calls.append(True) or {"ok": True, "value": 2},
        )

        self.assertEqual(result, {"ok": True, "value": 1})
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()