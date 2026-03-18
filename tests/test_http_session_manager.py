import tempfile
import unittest
import json
import os
from pathlib import Path
from unittest import mock

import nova_http
import nova_core


class TestHttpSessionManager(unittest.TestCase):
    def setUp(self):
        self.orig_store = nova_http.SESSION_STORE_PATH
        self.orig_turns = dict(nova_http.SESSION_TURNS)
        self.orig_runtime = nova_http.RUNTIME_DIR
        self.orig_venv_py = nova_http.VENV_PY
        self.orig_core_py = nova_http.CORE_PY
        self.orig_dev_mode = os.environ.get("NOVA_DEV_MODE")
        self.orig_policy_path = nova_core.POLICY_PATH
        self.orig_policy_audit = nova_core.POLICY_AUDIT_LOG
        self.orig_env_json = os.environ.get("NOVA_CHAT_USERS_JSON")
        self.orig_env_user = os.environ.get("NOVA_CHAT_USER")
        self.orig_env_pass = os.environ.get("NOVA_CHAT_PASS")
        os.environ.pop("NOVA_CHAT_USERS_JSON", None)
        os.environ.pop("NOVA_CHAT_USER", None)
        os.environ.pop("NOVA_CHAT_PASS", None)

    def tearDown(self):
        nova_http.SESSION_STORE_PATH = self.orig_store
        nova_http.RUNTIME_DIR = self.orig_runtime
        nova_http.VENV_PY = self.orig_venv_py
        nova_http.CORE_PY = self.orig_core_py
        nova_core.POLICY_PATH = self.orig_policy_path
        nova_core.POLICY_AUDIT_LOG = self.orig_policy_audit
        if self.orig_dev_mode is None:
            os.environ.pop("NOVA_DEV_MODE", None)
        else:
            os.environ["NOVA_DEV_MODE"] = self.orig_dev_mode
        if self.orig_env_json is None:
            os.environ.pop("NOVA_CHAT_USERS_JSON", None)
        else:
            os.environ["NOVA_CHAT_USERS_JSON"] = self.orig_env_json
        if self.orig_env_user is None:
            os.environ.pop("NOVA_CHAT_USER", None)
        else:
            os.environ["NOVA_CHAT_USER"] = self.orig_env_user
        if self.orig_env_pass is None:
            os.environ.pop("NOVA_CHAT_PASS", None)
        else:
            os.environ["NOVA_CHAT_PASS"] = self.orig_env_pass
        nova_http.SESSION_TURNS.clear()
        nova_http.SESSION_TURNS.update(self.orig_turns)

    def test_dev_mode_toggle_helper(self):
        os.environ.pop("NOVA_DEV_MODE", None)
        self.assertFalse(nova_http._dev_mode_enabled())

        os.environ["NOVA_DEV_MODE"] = "1"
        self.assertTrue(nova_http._dev_mode_enabled())

        os.environ["NOVA_DEV_MODE"] = "true"
        self.assertTrue(nova_http._dev_mode_enabled())

        os.environ["NOVA_DEV_MODE"] = "off"
        self.assertFalse(nova_http._dev_mode_enabled())

    def test_session_summaries_and_delete(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "http_chat_sessions.json"
            nova_http.SESSION_STORE_PATH = store
            nova_http.SESSION_TURNS.clear()

            nova_http._append_session_turn("sA", "user", "hello")
            nova_http._append_session_turn("sA", "assistant", "hi")
            nova_http._append_session_turn("sB", "user", "what is status")

            summary = nova_http._session_summaries(10)
            ids = [x.get("session_id") for x in summary]
            self.assertIn("sA", ids)
            self.assertIn("sB", ids)

            ok, msg = nova_http._delete_session("sA")
            self.assertTrue(ok)
            self.assertIn(msg, {"session_deleted", "session_not_found"})
            self.assertEqual(nova_http._get_session_turns("sA"), [])

    def test_control_action_session_delete_returns_updated_sessions(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "http_chat_sessions.json"
            nova_http.SESSION_STORE_PATH = store
            nova_http.SESSION_TURNS.clear()

            nova_http._append_session_turn("sA", "user", "hello")
            nova_http._append_session_turn("sA", "assistant", "hi")
            nova_http._append_session_turn("sB", "user", "keep me")

            ok, msg, extra = nova_http._control_action("session_delete", {"session_id": "sA"})

        self.assertTrue(ok)
        self.assertEqual(msg, "session_deleted")
        self.assertEqual(nova_http._get_session_turns("sA"), [])
        sessions = extra.get("sessions") or []
        self.assertTrue(any(item.get("session_id") == "sB" for item in sessions))
        self.assertFalse(any(item.get("session_id") == "sA" for item in sessions))

    def test_control_self_check_payload(self):
        payload = nova_http._control_self_check_payload()
        self.assertIn("checks", payload)
        self.assertIn("summary", payload)
        self.assertIn("health_score", payload)
        self.assertIn("pass_ratio", payload)
        self.assertTrue(isinstance(payload.get("checks"), list))

    def test_control_status_payload_includes_runtime_process_note(self):
        policy = {
            "tools_enabled": {"web": False},
            "memory": {"enabled": False, "scope": "private"},
            "web": {"enabled": False, "search_provider": "html", "search_api_endpoint": "", "allow_domains": []},
        }
        with mock.patch("nova_http.nova_core.load_policy", return_value=policy), \
            mock.patch("nova_http.nova_core.ollama_api_up", return_value=False), \
            mock.patch("nova_http.nova_core.chat_model", return_value="test-model"), \
            mock.patch("nova_http.nova_core.mem_enabled", return_value=False), \
            mock.patch("nova_http.nova_core.mem_stats_payload", return_value={"ok": True, "total": 0, "by_user": {}}), \
            mock.patch("nova_http._chat_login_enabled", return_value=False), \
            mock.patch("nova_http._chat_auth_source", return_value="disabled"), \
            mock.patch("nova_http._chat_users", return_value={}), \
            mock.patch("nova_http._memory_events_summary", return_value={"ok": True, "count": 0}), \
            mock.patch("nova_http._tool_events_summary", return_value={"ok": True, "count": 0}), \
            mock.patch("nova_http._action_ledger_summary", return_value={"ok": True, "count": 0}), \
            mock.patch("nova_http._guard_status_payload", return_value={"running": False}), \
            mock.patch("nova_http._core_status_payload", return_value={"running": False, "pid": None, "heartbeat_age_sec": None}), \
            mock.patch("nova_http._append_metrics_snapshot", return_value=None), \
            mock.patch("nova_http._build_self_check", return_value={"health_score": 100, "pass_ratio": 1.0, "alerts": []}), \
            mock.patch("nova_http.os.name", "nt"):
            payload = nova_http._control_status_payload()

        self.assertEqual(payload.get("process_counting_mode"), "logical_leaf_processes")
        self.assertIn("logical service state", payload.get("runtime_process_note", ""))

    def test_control_status_payload_surfaces_control_telemetry_fields(self):
        nova_http.SESSION_TURNS.clear()
        nova_http.SESSION_TURNS["control-smoke"] = [("user", "hello")]
        policy = {
            "tools_enabled": {"web": True},
            "memory": {"enabled": True, "scope": "hybrid"},
            "web": {
                "enabled": True,
                "search_provider": "html",
                "search_api_endpoint": "",
                "allow_domains": ["tea.texas.gov"],
            },
        }
        with mock.patch("nova_http.nova_core.load_policy", return_value=policy), \
            mock.patch("nova_http.nova_core.ollama_api_up", return_value=True), \
            mock.patch("nova_http.nova_core.chat_model", return_value="test-model"), \
            mock.patch("nova_http.nova_core.mem_enabled", return_value=True), \
            mock.patch("nova_http.nova_core.mem_stats_payload", return_value={"ok": True, "total": 7, "by_user": {"gus": 7}}), \
            mock.patch("nova_http._chat_login_enabled", return_value=True), \
            mock.patch("nova_http._chat_auth_source", return_value="managed_file"), \
            mock.patch("nova_http._chat_users", return_value={"gus": {"password_hash": "x"}}), \
            mock.patch("nova_http._memory_events_summary", return_value={
                "ok": True,
                "count": 4,
                "write_count": 2,
                "recall_count": 1,
                "skipped_count": 1,
                "avg_latency_ms": 18,
                "last_event": {"action": "add", "status": "ok"},
            }), \
            mock.patch("nova_http._tool_events_summary", return_value={
                "ok": True,
                "count": 5,
                "status_counts": {"ok": 4, "denied": 1, "error": 0},
                "success_count": 4,
                "failure_count": 0,
                "avg_latency_ms": 91,
                "avg_latency_ms_by_tool": {"web_research": 91},
                "last_error_summary": "",
                "last_event": {"tool": "web_research", "status": "ok", "user": "gus"},
            }), \
            mock.patch("nova_http._action_ledger_summary", return_value={
                "ok": True,
                "count": 3,
                "last_record": {
                    "planner_decision": "run_tool",
                    "route_summary": "planner>tool",
                    "grounded": True,
                },
            }), \
            mock.patch("nova_http._guard_status_payload", return_value={"running": True}), \
            mock.patch("nova_http._core_status_payload", return_value={"running": True, "pid": 123, "heartbeat_age_sec": 2}), \
            mock.patch("nova_http._append_metrics_snapshot", return_value=None), \
            mock.patch("nova_http._build_self_check", return_value={"health_score": 92, "pass_ratio": 0.8, "alerts": ["tool latency elevated"]}):
            payload = nova_http._control_status_payload()

        self.assertEqual(payload.get("active_http_sessions"), 1)
        self.assertEqual(payload.get("memory_scope"), "hybrid")
        self.assertEqual(payload.get("memory_entries_total"), 7)
        self.assertEqual(payload.get("last_memory_action"), "add")
        self.assertEqual(payload.get("tool_events_total"), 5)
        self.assertEqual(payload.get("last_tool_name"), "web_research")
        self.assertEqual(payload.get("action_ledger_total"), 3)
        self.assertEqual(payload.get("last_planner_decision"), "run_tool")
        self.assertEqual(payload.get("last_route_summary"), "planner>tool")
        self.assertTrue(payload.get("last_route_grounded"))
        self.assertEqual(payload.get("health_score"), 92)
        self.assertEqual(payload.get("self_check_pass_ratio"), 0.8)
        self.assertEqual(payload.get("alerts"), ["tool latency elevated"])

    def test_control_action_refresh_status_returns_status_snapshot(self):
        with mock.patch("nova_http._control_status_payload", return_value={"ok": True, "health_score": 99}) as status_mock:
            ok, msg, extra = nova_http._control_action("refresh_status", {"source": "smoke"})

        self.assertTrue(ok)
        self.assertEqual(msg, "status_refreshed")
        self.assertEqual(extra.get("health_score"), 99)
        status_mock.assert_called_once_with()

    def test_control_action_self_check_uses_current_status_policy_and_metrics(self):
        status_payload = {"ok": True, "health_score": 88}
        policy_payload = {"ok": True, "memory": {"scope": "hybrid"}}
        metrics_payload = {"ok": True, "points": [{"ts": 1}]}
        self_check_payload = {"ok": True, "summary": "self_check: 4/4 checks passed", "health_score": 100}

        with mock.patch("nova_http._control_status_payload", return_value=status_payload) as status_mock, \
            mock.patch("nova_http._control_policy_payload", return_value=policy_payload) as policy_mock, \
            mock.patch("nova_http._metrics_payload", return_value=metrics_payload) as metrics_mock, \
            mock.patch("nova_http._build_self_check", return_value=self_check_payload) as check_mock:
            ok, msg, extra = nova_http._control_action("self_check", {})

        self.assertTrue(ok)
        self.assertEqual(msg, "self_check: 4/4 checks passed")
        self.assertEqual(extra, self_check_payload)
        status_mock.assert_called_once_with()
        policy_mock.assert_called_once_with()
        metrics_mock.assert_called_once_with()
        check_mock.assert_called_once_with(status_payload, policy_payload, metrics_payload)

    def test_control_html_smoke_keeps_core_endpoints_and_tabs(self):
        html = nova_http.CONTROL_HTML
        script = (nova_http.STATIC_DIR / "control.js").read_text(encoding="utf-8")

        self.assertIn("/api/control/status", script)
        self.assertIn("/api/control/action", script)
        self.assertIn("/api/control/test-sessions", script)
        self.assertIn("NYO System Control", html)
        self.assertIn("Not Your Ordinary AI System", html)
        self.assertIn("Overview", html)
        self.assertIn("Tools", html)
        self.assertIn("Sessions", html)
        self.assertIn("Logs", html)
        self.assertIn("Parity Test Runs", html)

    def test_test_session_report_summaries_surface_runner_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            nova_http.RUNTIME_DIR = Path(td)
            run_dir = nova_http.RUNTIME_DIR / "test_sessions" / "mixed_thread_parity_20260317_194849"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "result.json").write_text(
                json.dumps({
                    "session": {
                        "name": "Mixed thread context switch parity",
                        "path": "C:/Nova/tests/sessions/mixed_thread_parity.json",
                        "messages": ["a", "b", "c"],
                    },
                    "comparison": {
                        "turn_count_match": True,
                        "cli_turns": 3,
                        "http_turns": 3,
                        "diffs": [],
                        "cli_flagged_probes": [{"turn": 2, "lines": ["YELLOW: continuation_drop"]}],
                        "http_flagged_probes": [{"turn": 2, "lines": ["YELLOW: continuation_drop"]}],
                    },
                    "cli": {"artifacts": {"mode_dir": "C:/Nova/runtime/test_sessions/run/cli"}},
                    "http": {"artifacts": {"mode_dir": "C:/Nova/runtime/test_sessions/run/http"}},
                    "generated_at": "2026-03-17 19:49:41",
                }, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )

            reports = nova_http._test_session_report_summaries(10)

        self.assertEqual(len(reports), 1)
        report = reports[0]
        self.assertEqual(report.get("run_id"), "mixed_thread_parity_20260317_194849")
        self.assertEqual(report.get("session_name"), "Mixed thread context switch parity")
        self.assertEqual(report.get("message_count"), 3)
        self.assertEqual(report.get("status"), "warning")
        self.assertEqual(report.get("comparison", {}).get("diff_count"), 0)
        self.assertEqual(report.get("comparison", {}).get("flagged_probe_count"), 2)

    def test_available_test_session_definitions_reads_saved_sessions(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions_dir = base / "tests" / "sessions"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            (sessions_dir / "gus_profile_test.json").write_text(
                json.dumps({"name": "Gus profile test", "messages": ["one", "two"]}, ensure_ascii=True),
                encoding="utf-8",
            )

            with mock.patch.object(nova_http, "BASE_DIR", base):
                definitions = nova_http._available_test_session_definitions(10)

        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0].get("file"), "gus_profile_test.json")
        self.assertEqual(definitions[0].get("name"), "Gus profile test")
        self.assertEqual(definitions[0].get("message_count"), 2)

    def test_control_action_test_session_run_executes_runner(self):
        latest_report = {"run_id": "gus_profile_test_20260317_200000", "status": "green"}
        definitions = [{"file": "gus_profile_test.json", "name": "Gus profile test", "message_count": 2}]
        completed = mock.Mock(returncode=0, stdout="Saved full report to runtime/test_sessions/...", stderr="")

        with mock.patch.object(nova_http, "VENV_PY", Path("c:/Nova/.venv/Scripts/python.exe")), \
            mock.patch.object(nova_http, "TEST_SESSION_RUNNER_PY", Path("c:/Nova/scripts/run_test_session.py")), \
            mock.patch("pathlib.Path.exists", return_value=True), \
            mock.patch("nova_http._available_test_session_definitions", return_value=definitions), \
            mock.patch("nova_http._test_session_report_summaries", return_value=[latest_report]), \
            mock.patch("nova_http.subprocess.run", return_value=completed) as run_mock:
            ok, msg, extra = nova_http._control_action("test_session_run", {"session_file": "gus_profile_test.json"})

        self.assertTrue(ok)
        self.assertIn("test_session_run_completed", msg)
        self.assertEqual(extra.get("latest_report"), latest_report)
        self.assertEqual(extra.get("definitions"), definitions)
        run_mock.assert_called_once()

    def test_export_capabilities_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            nova_http.RUNTIME_DIR = Path(td)
            ok, msg, extra = nova_http._export_capabilities_snapshot()
            self.assertTrue(ok)
            self.assertIn("capabilities_export_ok", msg)
            self.assertIn("filename", extra)
            p = Path(extra.get("path"))
            self.assertTrue(p.exists())
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertTrue(isinstance(data, dict))

    def test_control_action_export_ledger_and_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            nova_http.RUNTIME_DIR = Path(td)
            nova_core_action_dir = Path(td) / "actions"
            nova_core_action_dir.mkdir(parents=True, exist_ok=True)

            # Seed one action ledger item for summary export.
            (nova_core_action_dir / "a.json").write_text(
                json.dumps({
                    "planner_decision": "run_tool",
                    "tool": "weather",
                    "grounded": True,
                    "route_trace": [
                        {"stage": "input", "outcome": "received"},
                        {"stage": "command", "outcome": "matched"},
                    ],
                }, ensure_ascii=True),
                encoding="utf-8",
            )

            # Patch core action ledger path for this test scope.
            import nova_core
            orig_action_dir = nova_core.ACTION_LEDGER_DIR
            try:
                nova_core.ACTION_LEDGER_DIR = nova_core_action_dir

                ok1, msg1, extra1 = nova_http._control_action("export_ledger_summary", {"limit": 10})
                self.assertTrue(ok1)
                self.assertIn("export_ok", msg1)
                self.assertTrue(Path(extra1.get("path", "")).exists())
                self.assertIn("route_summary", extra1.get("summary", {}).get("last_record", {}))

                ok2, msg2, extra2 = nova_http._control_action("export_diagnostics_bundle", {})
                self.assertTrue(ok2)
                self.assertIn("diagnostics_bundle_exported", msg2)
                self.assertTrue(Path(extra2.get("path", "")).exists())
            finally:
                nova_core.ACTION_LEDGER_DIR = orig_action_dir

    def test_control_action_nova_start(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            nova_http.CORE_PY = base / "nova_core.py"
            nova_http.RUNTIME_DIR = base / "runtime"
            nova_http.CORE_PY.write_text("print('nova core')\n", encoding="utf-8")
            nova_http.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

            with mock.patch("nova_http._start_guard", return_value=(True, "guard_start_requested")) as start_guard_mock:
                ok, msg, extra = nova_http._control_action("nova_start", {})

            self.assertTrue(ok)
            self.assertIn("nova_core", msg)
            self.assertIn("core", extra)
            self.assertTrue(start_guard_mock.called)

    def test_start_guard_clears_stale_stop_flag(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            nova_http.VENV_PY = base / ".venv" / "Scripts" / "python.exe"
            nova_http.GUARD_PY = base / "nova_guard.py"
            nova_http.RUNTIME_DIR = base / "runtime"
            nova_http.VENV_PY.parent.mkdir(parents=True, exist_ok=True)
            nova_http.VENV_PY.write_text("", encoding="utf-8")
            nova_http.GUARD_PY.write_text("print('guard')\n", encoding="utf-8")
            nova_http.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            stop_file = nova_http.RUNTIME_DIR / "guard.stop"
            stop_file.write_text("stale", encoding="utf-8")

            with mock.patch("nova_http.subprocess.Popen"):
                ok, msg = nova_http._start_guard()

            self.assertTrue(ok)
            self.assertIn("guard_", msg)
            self.assertFalse(stop_file.exists())

    def test_control_action_chat_user_management_uses_managed_file(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            nova_http.RUNTIME_DIR = base

            ok_add, msg_add, extra_add = nova_http._control_action("chat_user_upsert", {"username": "Alice Smith", "password": "secret"})

            self.assertTrue(ok_add)
            self.assertIn("chat_user_saved", msg_add)
            self.assertEqual(extra_add.get("chat_auth", {}).get("source"), "managed_file")
            self.assertIn("AliceSmith", extra_add.get("chat_auth", {}).get("users", []))
            data = json.loads((base / "chat_users.json").read_text(encoding="utf-8"))
            self.assertIn("AliceSmith", data)
            self.assertNotIn("secret", json.dumps(data))

            ok_del, msg_del, extra_del = nova_http._control_action("chat_user_delete", {"username": "AliceSmith"})

            self.assertTrue(ok_del)
            self.assertIn("chat_user_deleted", msg_del)
            self.assertEqual(extra_del.get("chat_auth", {}).get("users", []), [])

    def test_control_action_memory_scope_set_updates_policy(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            policy_path = base / "policy.json"
            policy_path.write_text(json.dumps({
                "tools_enabled": {"web": True},
                "models": {"chat": "llama3.1:8b"},
                "memory": {"enabled": True, "scope": "private"},
                "web": {"enabled": True, "allow_domains": []},
            }, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
            nova_core.POLICY_PATH = policy_path
            nova_core.POLICY_AUDIT_LOG = base / "policy_changes.jsonl"

            ok, msg, extra = nova_http._control_action("memory_scope_set", {"scope": "hybrid"})

            self.assertTrue(ok)
            self.assertIn("Memory scope set to hybrid", msg)
            self.assertEqual(extra.get("policy", {}).get("memory", {}).get("scope"), "hybrid")
            saved = json.loads(policy_path.read_text(encoding="utf-8"))
            self.assertEqual(saved.get("memory", {}).get("scope"), "hybrid")


if __name__ == "__main__":
    unittest.main()
