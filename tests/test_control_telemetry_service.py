import json
import tempfile
import threading
import unittest
from pathlib import Path

from services.control_telemetry import ControlTelemetryService


class TestControlTelemetryService(unittest.TestCase):
    def test_action_ledger_summary_aggregates_recent_records(self):
        service = ControlTelemetryService(list_capabilities_fn=lambda: {})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.json").write_text(
                json.dumps(
                    {
                        "planner_decision": "deterministic",
                        "tool": "none",
                        "grounded": True,
                        "intent": "chat",
                        "route_trace": ["a"],
                        "final_answer": "ok",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            (root / "b.json").write_text(
                json.dumps(
                    {
                        "planner_decision": "run_tool",
                        "tool": "queue_status",
                        "grounded": False,
                        "intent": "tool",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            payload = service.action_ledger_summary(root, lambda record: f"route:{record.get('planner_decision')}", limit=10)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["decision_counts"].get("deterministic"), 1)
        self.assertEqual(payload["tool_counts"].get("queue_status"), 1)
        self.assertEqual(payload["route_counts"].get("route:run_tool"), 1)

    def test_tool_events_summary_computes_latency_and_statuses(self):
        service = ControlTelemetryService(list_capabilities_fn=lambda: {})
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "tool_events.jsonl"
            log_path.write_text(
                "\n".join(
                    [
                        json.dumps({"tool": "filesystem", "status": "ok", "duration_ms": 50, "user": "u", "ts": 1}),
                        json.dumps({"tool": "vision", "status": "error", "error": "boom", "duration_ms": 100, "user": "u", "ts": 2}),
                    ]
                ),
                encoding="utf-8",
            )

            payload = service.tool_events_summary(log_path, limit=10)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["success_count"], 1)
        self.assertEqual(payload["failure_count"], 1)
        self.assertEqual(payload["avg_latency_ms"], 75)
        self.assertEqual(payload["avg_latency_ms_by_tool"].get("filesystem"), 50)
        self.assertIn("vision", payload["last_error_summary"])

    def test_memory_events_summary_counts_actions(self):
        service = ControlTelemetryService(list_capabilities_fn=lambda: {})
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "memory_events.jsonl"
            log_path.write_text(
                "\n".join(
                    [
                        json.dumps({"action": "add", "status": "ok", "duration_ms": 20, "user": "u", "ts": 1}),
                        json.dumps({"action": "recall", "status": "skipped", "duration_ms": 30, "user": "u", "ts": 2}),
                    ]
                ),
                encoding="utf-8",
            )

            payload = service.memory_events_summary(log_path, limit=10)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["write_count"], 1)
        self.assertEqual(payload["recall_count"], 1)
        self.assertEqual(payload["skipped_count"], 1)
        self.assertEqual(payload["avg_latency_ms"], 25)

    def test_build_self_check_flags_missing_allow_domains(self):
        service = ControlTelemetryService(list_capabilities_fn=lambda: {"a": 1, "b": 2})
        status = {
            "ok": True,
            "ollama_api_up": True,
            "guard": {},
            "heartbeat_age_sec": 5,
            "tool_events_ok": True,
            "patch_status_ok": True,
            "patch_enabled": False,
            "patch_strict_manifest": True,
            "patch_behavioral_check": True,
            "patch_tests_available": True,
        }
        policy = {"ok": True, "tools_enabled": {"web": True}, "web": {"enabled": True, "allow_domains": []}}
        metrics = {"ok": True, "points": []}

        payload = service.build_self_check(status, policy, metrics)

        self.assertGreaterEqual(payload["health_score"], 0)
        self.assertIn("web_enabled_without_allow_domains", payload["alerts"])
        self.assertTrue(any(item.get("name") == "capability_registry" for item in payload.get("checks")))

    def test_metrics_helpers_append_and_read_payload(self):
        series = []
        lock = threading.Lock()
        ControlTelemetryService.append_metrics_snapshot(
            {"heartbeat_age_sec": 5, "ollama_api_up": True, "searxng_ok": False},
            metrics_lock=lock,
            http_requests_total=7,
            http_errors_total=2,
            metrics_series=series,
            metrics_max_points=4,
            now_fn=lambda: 123,
        )

        payload = ControlTelemetryService.metrics_payload(
            metrics_lock=lock,
            http_requests_total=7,
            http_errors_total=2,
            metrics_series=series,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["requests_total"], 7)
        self.assertEqual(payload["errors_total"], 2)
        self.assertEqual(payload["points"][0]["ts"], 123)

    def test_tail_log_action_rejects_unknown_names(self):
        events = []
        ok, msg, extra = ControlTelemetryService.tail_log_action(
            {"name": "unknown.log"},
            log_dir=Path("."),
            tail_file_fn=lambda path: "",
            record_control_action_event_fn=lambda action, result, detail, payload: events.append((action, result, detail)),
        )

        self.assertFalse(ok)
        self.assertEqual(msg, "invalid_log_name")
        self.assertEqual(extra, {})
        self.assertEqual(events, [("tail_log", "fail", "invalid_log_name")])

    def test_export_ledger_summary_action_writes_json(self):
        service = ControlTelemetryService(list_capabilities_fn=lambda: {})
        events = []
        with tempfile.TemporaryDirectory() as td:
            ok, msg, extra = service.export_ledger_summary_action(
                {"limit": 2},
                export_dir=Path(td),
                action_ledger_summary_fn=lambda limit=60: {"ok": True, "count": limit},
                record_control_action_event_fn=lambda action, result, detail, payload: events.append((action, result, detail)),
                strftime_fn=lambda fmt: "20260330_120000",
            )

            self.assertTrue(ok)
            self.assertEqual(msg, "action_ledger_export_ok")
            written = Path(extra["path"])
            self.assertTrue(written.exists())
            self.assertEqual(json.loads(written.read_text(encoding="utf-8"))["count"], 2)
            self.assertEqual(events, [("export_ledger_summary", "ok", "action_ledger_export_ok")])


if __name__ == "__main__":
    unittest.main()