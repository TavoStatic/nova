import unittest
from pathlib import Path
from types import SimpleNamespace

from services.runtime_status import RUNTIME_STATUS_SERVICE


class TestRuntimeStatusService(unittest.TestCase):
    def test_action_readiness_payload_explains_runtime_controls(self):
        payload = RUNTIME_STATUS_SERVICE.action_readiness_payload(
            {"running": True, "stop_flag": False, "status": "running"},
            {"running": False, "pid": None, "state_exists": False, "status": "stopped"},
            {"running": True, "status": "running"},
        )

        self.assertFalse((payload.get("guard_start") or {}).get("enabled"))
        self.assertIn("already running", ((payload.get("guard_start") or {}).get("reason") or "").lower())
        self.assertTrue((payload.get("core_restart") or {}).get("enabled"))
        self.assertTrue((payload.get("webui_restart") or {}).get("enabled"))

    def test_runtime_failure_reasons_follow_status_and_timeline(self):
        timeline_payload = {
            "events": [
                {"service": "core", "level": "danger", "title": "Core attempt failed", "detail": "heartbeat_stale"},
                {"service": "guard", "level": "warn", "title": "Guard stop requested", "detail": "Stop file detected by supervisor."},
            ]
        }
        payload = RUNTIME_STATUS_SERVICE.runtime_failure_reasons_payload(
            {"status": "stopping", "running": False},
            {"status": "heartbeat_stale", "running": False},
            {"status": "running", "running": True},
            timeline_payload,
        )

        self.assertEqual(((payload.get("guard") or {}).get("level")), "warn")
        self.assertIn("stop", ((payload.get("guard") or {}).get("detail") or "").lower())
        self.assertEqual(((payload.get("core") or {}).get("level")), "danger")
        self.assertEqual(((payload.get("core") or {}).get("detail")), "heartbeat_stale")
        self.assertEqual(((payload.get("webui") or {}).get("summary")), "Healthy")

    def test_runtime_summary_payload_shapes_guard_core_and_webui(self):
        payload = RUNTIME_STATUS_SERVICE.runtime_summary_payload(
            {"running": True, "status": "running", "pid": 11, "create_time": 1.1, "process_count": 1, "lock_exists": True, "stop_flag": False},
            {"running": False, "status": "heartbeat_stale", "pid": 22, "create_time": 2.2, "process_count": 1, "heartbeat_age_sec": 9, "state_exists": True},
            {"running": True, "status": "running", "pid": 33, "create_time": 3.3, "process_count": 1},
        )

        self.assertEqual(((payload.get("guard") or {}).get("pid")), 11)
        self.assertEqual(((payload.get("core") or {}).get("status")), "heartbeat_stale")
        self.assertEqual(((payload.get("webui") or {}).get("process_count")), 1)

    def test_http_status_payload_reads_current_process_identity(self):
        payload = RUNTIME_STATUS_SERVICE.http_status_payload(
            getpid_fn=lambda: 2468,
            process_fn=lambda pid: SimpleNamespace(create_time=lambda: 321.5),
        )

        self.assertTrue(payload.get("running"))
        self.assertEqual(payload.get("pid"), 2468)
        self.assertEqual(payload.get("create_time"), 321.5)

    def test_guard_status_payload_uses_cached_fallback_without_artifacts(self):
        calls = {"cached": 0, "logical": 0}

        payload = RUNTIME_STATUS_SERVICE.guard_status_payload(
            runtime_dir=Path("c:/tmp/runtime"),
            guard_py=Path("c:/Nova/nova_guard.py"),
            include_fallback_scan=True,
            pid_exists_fn=lambda _pid: False,
            cached_logical_service_processes_fn=lambda *args, **kwargs: calls.__setitem__("cached", calls["cached"] + 1) or [],
            logical_service_processes_fn=lambda *args, **kwargs: calls.__setitem__("logical", calls["logical"] + 1) or [],
            prune_orphaned_guard_artifacts_fn=lambda *_args, **_kwargs: None,
            select_logical_process_fn=lambda *_args, **_kwargs: None,
            process_scan_cache_ttl_seconds=5.0,
        )

        self.assertEqual(payload.get("status"), "stopped")
        self.assertEqual(calls, {"cached": 1, "logical": 0})


if __name__ == "__main__":
    unittest.main()