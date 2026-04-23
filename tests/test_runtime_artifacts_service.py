import json
import tempfile
import unittest
from pathlib import Path

from services.runtime_artifacts import RUNTIME_ARTIFACTS_SERVICE


class TestRuntimeArtifactsService(unittest.TestCase):
    def test_payload_summarizes_runtime_files(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            log_dir = Path(td) / "logs"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)

            (runtime_dir / "core_state.json").write_text(json.dumps({"pid": 321, "create_time": 99.1}), encoding="utf-8")
            (runtime_dir / "core.heartbeat").write_text("", encoding="utf-8")
            (runtime_dir / "guard.lock").write_text(json.dumps({"pid": 654, "command": {"script": "nova_guard.py"}}), encoding="utf-8")
            (runtime_dir / "guard_boot_history.json").write_text(json.dumps([
                {"ts": 1710000100, "success": True, "reason": "running", "total_observed_s": 4.2, "boot_timeout_seconds": 12.0}
            ]), encoding="utf-8")
            (runtime_dir / "control_action_audit.jsonl").write_text(
                json.dumps({"ts": 1710000101, "action": "guard_status", "result": "ok", "detail": "status_refreshed"}) + "\n",
                encoding="utf-8",
            )
            (log_dir / "guard.log").write_text("2024-03-09 16:00:08 | [GUARD] Core pid=123 reached RUNNING state\n", encoding="utf-8")

            definitions = RUNTIME_ARTIFACTS_SERVICE.artifact_definitions(
                runtime_dir=runtime_dir,
                guard_boot_history_path=runtime_dir / "guard_boot_history.json",
                control_audit_log=runtime_dir / "control_action_audit.jsonl",
                guard_log_path=log_dir / "guard.log",
            )

            payload = RUNTIME_ARTIFACTS_SERVICE.payload(
                definitions,
                artifact_summary_fn=lambda name, path: RUNTIME_ARTIFACTS_SERVICE.artifact_summary(
                    name,
                    path,
                    safe_json_file_fn=lambda current_path: json.loads(Path(current_path).read_text(encoding="utf-8")) if Path(current_path).exists() else None,
                    tail_file_fn=lambda current_path, max_lines=120: "\n".join(Path(current_path).read_text(encoding="utf-8").splitlines()[-max_lines:]),
                    safe_tail_lines_fn=lambda current_path, max_lines=120: Path(current_path).read_text(encoding="utf-8").splitlines()[-max_lines:],
                    file_age_seconds_fn=lambda current_path: 0,
                    json_module=json,
                ),
                artifact_status_fn=lambda name, path: RUNTIME_ARTIFACTS_SERVICE.artifact_status(name, path, file_age_seconds_fn=lambda current_path: 0),
                file_age_seconds_fn=lambda current_path: 0,
            )

        items = {item.get("name"): item for item in (payload.get("items") or [])}
        self.assertEqual(payload.get("count"), 7)
        self.assertEqual((items.get("core_state.json") or {}).get("status"), "present")
        self.assertIn("pid=321", (items.get("core_state.json") or {}).get("summary", ""))
        self.assertEqual((items.get("core.heartbeat") or {}).get("status"), "running")
        self.assertIn("last_action=guard_status", (items.get("control_action_audit.jsonl") or {}).get("summary", ""))
        self.assertIn("Core pid=123 reached RUNNING state", (items.get("guard.log") or {}).get("summary", ""))


if __name__ == "__main__":
    unittest.main()