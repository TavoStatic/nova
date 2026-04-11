import json
import tempfile
import time
import unittest
from pathlib import Path

from services.runtime_timeline import RUNTIME_TIMELINE_SERVICE


class TestRuntimeTimelineService(unittest.TestCase):
    def test_payload_combines_operator_guard_and_boot_events(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            log_dir = Path(td) / "logs"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)

            control_log = runtime_dir / "control_action_audit.jsonl"
            control_log.write_text(
                "\n".join([
                    json.dumps({"ts": 1710000000, "action": "guard_start", "result": "ok", "detail": "guard_start_requested"}),
                    json.dumps({"ts": 1710000003, "action": "operator_prompt", "result": "ok", "detail": "operator_prompt_ok:operator-abc123", "safe_fields": {"source": "cli", "macro": "inspect-runtime", "operator_mode": "macro"}}),
                    json.dumps({"ts": 1710000005, "action": "patch_preview_apply", "result": "fail", "detail": "patch_preview_not_eligible:preview.txt"}),
                ]),
                encoding="utf-8",
            )

            guard_log = log_dir / "guard.log"
            guard_log.write_text(
                "\n".join([
                    "2024-03-09 16:00:06 | [GUARD] Core attempt failed: heartbeat_stale",
                    "2024-03-09 16:00:07 | [GUARD] Restart wait 5s after failure: heartbeat_stale",
                    "2024-03-09 16:00:08 | [GUARD] Core pid=123 reached RUNNING state",
                ]),
                encoding="utf-8",
            )

            boot_history = runtime_dir / "guard_boot_history.json"
            boot_history.write_text(
                json.dumps([
                    {"ts": 1710000004, "success": False, "reason": "boot_timeout", "total_observed_s": 12.5, "boot_timeout_seconds": 12.0},
                ]),
                encoding="utf-8",
            )

            payload = RUNTIME_TIMELINE_SERVICE.payload(
                limit=10,
                control_audit_log=control_log,
                guard_log_path=guard_log,
                boot_history_path=boot_history,
                safe_tail_lines_fn=lambda path, max_lines: path.read_text(encoding="utf-8").splitlines()[-max_lines:],
                time_module=time,
            )

        events = payload.get("events") or []
        self.assertGreaterEqual(payload.get("count"), 4)
        self.assertEqual(events[0].get("title"), "Core reached running state")
        self.assertTrue(any(item.get("source") == "operator" and item.get("title") == "Guard Start" for item in events))
        self.assertTrue(any(item.get("title") == "Operator Prompt [MACRO]" and item.get("operator_source") == "cli" and item.get("operator_macro") == "inspect-runtime" for item in events))
        self.assertTrue(any(item.get("service") == "patch" and item.get("level") == "danger" for item in events))
        self.assertTrue(any(item.get("title") == "Boot observation failed" for item in events))


if __name__ == "__main__":
    unittest.main()