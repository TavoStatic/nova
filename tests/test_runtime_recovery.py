import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import nova_guard
import nova_http


class TestRuntimeRecovery(unittest.TestCase):
    def test_guard_status_payload_uses_pid_exists_and_runtime_flags(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            (runtime_dir / "guard.lock").write_text("{}", encoding="utf-8")
            (runtime_dir / "guard.stop").write_text("stop", encoding="utf-8")
            (runtime_dir / "guard_pid.json").write_text(
                json.dumps({"pid": 4321}, ensure_ascii=True),
                encoding="utf-8",
            )

            with mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir), \
                mock.patch("nova_http.psutil.pid_exists", return_value=True) as pid_exists:
                payload = nova_http._guard_status_payload()

            self.assertTrue(payload["running"])
            self.assertEqual(payload["pid"], 4321)
            self.assertTrue(payload["lock_exists"])
            self.assertTrue(payload["stop_flag"])
            pid_exists.assert_called_once_with(4321)

    def test_core_status_payload_treats_fresh_heartbeat_as_running(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            (runtime_dir / "core_state.json").write_text(
                json.dumps({"pid": 9876, "create_time": 12.5}, ensure_ascii=True),
                encoding="utf-8",
            )

            with mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir), \
                mock.patch("nova_http.psutil.pid_exists", return_value=False) as pid_exists, \
                mock.patch("nova_http._heartbeat_age_seconds", return_value=0):
                payload = nova_http._core_status_payload()

            self.assertTrue(payload["running"])
            self.assertEqual(payload["pid"], 9876)
            self.assertEqual(payload["create_time"], 12.5)
            self.assertEqual(payload["heartbeat_age_sec"], 0)
            pid_exists.assert_called_once_with(9876)

    def test_acquire_lock_or_exit_replaces_stale_lock(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            lock_file = runtime_dir / "guard.lock"
            pid_file = runtime_dir / "guard_pid.json"
            lock_file.write_text(
                json.dumps({"pid": 1111, "ts": "old"}, ensure_ascii=True),
                encoding="utf-8",
            )

            with mock.patch.object(nova_guard, "RUNTIME_DIR", runtime_dir), \
                mock.patch.object(nova_guard, "LOCK_FILE", lock_file), \
                mock.patch.object(nova_guard, "GUARD_PID_FILE", pid_file), \
                mock.patch.object(nova_guard, "log", lambda _msg: None), \
                mock.patch.object(nova_guard, "ts", return_value="2026-03-15 17:40:00"), \
                mock.patch("nova_guard.os.getpid", return_value=2222), \
                mock.patch("nova_guard.psutil.pid_exists", return_value=False) as pid_exists:
                nova_guard.acquire_lock_or_exit()

            written_lock = json.loads(lock_file.read_text(encoding="utf-8"))
            written_pid = json.loads(pid_file.read_text(encoding="utf-8"))
            self.assertEqual(written_lock["pid"], 2222)
            self.assertEqual(written_pid["pid"], 2222)
            pid_exists.assert_called_once_with(1111)

    def test_acquire_lock_or_exit_exits_when_live_guard_exists(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            lock_file = runtime_dir / "guard.lock"
            pid_file = runtime_dir / "guard_pid.json"
            lock_file.write_text(
                json.dumps({"pid": 3333, "ts": "old"}, ensure_ascii=True),
                encoding="utf-8",
            )

            with mock.patch.object(nova_guard, "RUNTIME_DIR", runtime_dir), \
                mock.patch.object(nova_guard, "LOCK_FILE", lock_file), \
                mock.patch.object(nova_guard, "GUARD_PID_FILE", pid_file), \
                mock.patch.object(nova_guard, "log", lambda _msg: None), \
                mock.patch("nova_guard.psutil.pid_exists", return_value=True), \
                self.assertRaises(SystemExit) as raised:
                nova_guard.acquire_lock_or_exit()

            self.assertEqual(raised.exception.code, 0)
            self.assertFalse(pid_file.exists())
            retained_lock = json.loads(lock_file.read_text(encoding="utf-8"))
            self.assertEqual(retained_lock["pid"], 3333)

    def test_powershell_webui_status_uses_logical_processes(self):
        script = (Path(__file__).resolve().parent.parent / "nova.ps1").read_text(encoding="utf-8")

        self.assertIn("function Get-NovaHttpLogicalProcesses", script)
        self.assertIn("$leaf = @($all | Where-Object { -not $parentIds.ContainsKey([int]$_.ProcessId) })", script)
        self.assertIn('$procs = Get-NovaHttpLogicalProcesses', script)

    def test_command_center_ui_renders_runtime_process_note(self):
        base = Path(__file__).resolve().parent.parent
        html = (base / "templates" / "control.html").read_text(encoding="utf-8")
        script = (base / "static" / "control.js").read_text(encoding="utf-8")

        self.assertIn('id="runtimeNoteBar"', html)
        self.assertIn("const runtimeNoteBar = document.getElementById('runtimeNoteBar');", script)
        self.assertIn("runtimeNoteBar.textContent = String(latestStatus.runtime_process_note || '');", script)

    def test_command_center_ui_separates_live_sessions_and_test_runs(self):
        base = Path(__file__).resolve().parent.parent
        html = (base / "templates" / "control.html").read_text(encoding="utf-8")
        script = (base / "static" / "control.js").read_text(encoding="utf-8")

        self.assertIn('id="testRunSelect"', html)
        self.assertIn('id="testRunProbeBox"', html)
        self.assertIn('id="testSessionDefinitionSelect"', html)
        self.assertIn('id="testRunDriftGrid"', html)
        self.assertIn("runtime/test_sessions", html)
        self.assertIn("const testRunSelect = document.getElementById('testRunSelect');", script)
        self.assertIn("const testSessionDefinitionSelect = document.getElementById('testSessionDefinitionSelect');", script)
        self.assertIn("getJson('/api/control/test-sessions')", script)
        self.assertIn("bindClick('btnTestRunExecute'", script)
        self.assertIn("bindClick('btnTestRunsRefresh'", script)

    def test_chat_ui_includes_browser_voice_controls(self):
        script = (Path(__file__).resolve().parent.parent / "nova_http.py").read_text(encoding="utf-8")

        self.assertIn('id="btnToggleAudio"', script)
        self.assertIn('id="btnMic"', script)
        self.assertIn("const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition || null;", script)
        self.assertIn("window.speechSynthesis.speak(utterance);", script)


if __name__ == "__main__":
    unittest.main()