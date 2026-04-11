import unittest

from services.control_actions import CONTROL_ACTIONS_SERVICE


class TestControlActionsService(unittest.TestCase):
    def test_refresh_status_action_returns_status_snapshot(self):
        ok, msg, extra, detail = CONTROL_ACTIONS_SERVICE.refresh_status_action(
            control_status_payload_fn=lambda: {"ok": True, "health_score": 99},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "status_refreshed")
        self.assertEqual(detail, msg)
        self.assertEqual(extra.get("health_score"), 99)

    def test_device_location_update_invalidates_cache_on_success(self):
        calls = []
        ok, msg, extra, detail = CONTROL_ACTIONS_SERVICE.device_location_update_action(
            {"lat": 30.2, "lon": -97.7},
            set_runtime_device_location_fn=lambda payload: (True, "device_location_updated", {"available": True, "source": "browser_watch"}),
            invalidate_control_status_cache_fn=lambda: calls.append("invalidated"),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "device_location_updated")
        self.assertEqual(detail, msg)
        self.assertEqual(calls, ["invalidated"])
        self.assertTrue((extra.get("live_tracking") or {}).get("available"))

    def test_self_check_action_uses_summary_as_message(self):
        ok, msg, extra, detail = CONTROL_ACTIONS_SERVICE.self_check_action(
            control_self_check_payload_fn=lambda: {"ok": True, "summary": "self_check: 4/4 checks passed", "health_score": 100},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "self_check: 4/4 checks passed")
        self.assertEqual(detail, msg)
        self.assertEqual(extra.get("health_score"), 100)


if __name__ == "__main__":
    unittest.main()