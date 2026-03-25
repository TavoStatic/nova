import tempfile
import unittest
import json
import os
from contextlib import ExitStack
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
            mock.patch("nova_http.nova_core.patch_status_payload", return_value={"ok": True, "enabled": True, "strict_manifest": True, "allow_force": False, "behavioral_check": True, "behavioral_check_timeout_sec": 600, "tests_available": True, "pipeline_ready": True, "current_revision": 4, "previews_total": 1, "previews_pending": 1, "previews_approved": 0, "previews_rejected": 0, "previews_eligible": 1, "previews_approved_eligible": 0, "last_preview_name": "preview.txt", "last_preview_status": "eligible", "last_preview_decision": "pending", "last_patch_log_line": "APPLY_OK files=1", "ready_for_validated_apply": False}), \
            mock.patch("nova_http._chat_login_enabled", return_value=False), \
            mock.patch("nova_http._chat_auth_source", return_value="disabled"), \
            mock.patch("nova_http._chat_users", return_value={}), \
            mock.patch("nova_http._memory_events_summary", return_value={"ok": True, "count": 0}), \
            mock.patch("nova_http._tool_events_summary", return_value={"ok": True, "count": 0}), \
            mock.patch("nova_http._action_ledger_summary", return_value={"ok": True, "count": 0}), \
            mock.patch("nova_http._guard_status_payload", return_value={"running": False, "status": "boot_timeout", "process_count": 0, "lock_exists": True, "stop_flag": False}), \
            mock.patch("nova_http._core_status_payload", return_value={"running": False, "status": "heartbeat_stale", "pid": None, "heartbeat_age_sec": 12, "process_count": 0, "state_exists": True}), \
            mock.patch("nova_http._http_status_payload", return_value={"running": True, "status": "running", "pid": 456, "process_count": 1}), \
            mock.patch("nova_http._append_metrics_snapshot", return_value=None), \
            mock.patch("nova_http._build_self_check", return_value={"health_score": 100, "pass_ratio": 1.0, "alerts": []}), \
            mock.patch("nova_http.os.name", "nt"):
            payload = nova_http._control_status_payload()

        self.assertEqual(payload.get("process_counting_mode"), "logical_leaf_processes")
        self.assertIn("logical service state", payload.get("runtime_process_note", ""))
        self.assertEqual((payload.get("webui") or {}).get("pid"), 456)
        self.assertIn("runtime_summary", payload)
        self.assertEqual((((payload.get("runtime_summary") or {}).get("guard") or {}).get("status")), "boot_timeout")
        self.assertEqual((((payload.get("runtime_summary") or {}).get("core") or {}).get("status")), "heartbeat_stale")

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
            mock.patch("nova_http.nova_core.patch_status_payload", return_value={
                "ok": True,
                "enabled": True,
                "strict_manifest": True,
                "allow_force": False,
                "behavioral_check": True,
                "behavioral_check_timeout_sec": 600,
                "tests_available": True,
                "pipeline_ready": True,
                "current_revision": 6,
                "previews_total": 3,
                "previews_pending": 2,
                "previews_approved": 1,
                "previews_rejected": 0,
                "previews_eligible": 1,
                "previews_approved_eligible": 1,
                "last_preview_name": "preview_1.txt",
                "last_preview_status": "eligible",
                "last_preview_decision": "approved",
                "last_patch_log_line": "BEHAVIOR_OK OK",
                "ready_for_validated_apply": True,
            }), \
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
            mock.patch("nova_http._guard_status_payload", return_value={"running": True, "status": "starting", "process_count": 1, "lock_exists": True, "stop_flag": False}), \
            mock.patch("nova_http._core_status_payload", return_value={"running": True, "status": "heartbeat_only", "pid": 123, "heartbeat_age_sec": 2, "process_count": 1, "state_exists": True}), \
            mock.patch("nova_http._http_status_payload", return_value={"running": True, "status": "running", "pid": 654, "process_count": 1}), \
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
        self.assertTrue(payload.get("patch_status_ok"))
        self.assertTrue(payload.get("patch_pipeline_ready"))
        self.assertEqual(payload.get("patch_current_revision"), 6)
        self.assertEqual(payload.get("patch_previews_pending"), 2)
        self.assertEqual(payload.get("patch_last_preview_status"), "eligible")
        self.assertTrue(payload.get("patch_ready_for_validated_apply"))
        self.assertEqual(payload.get("last_planner_decision"), "run_tool")
        self.assertEqual(payload.get("last_route_summary"), "planner>tool")
        self.assertTrue(payload.get("last_route_grounded"))
        self.assertEqual((payload.get("webui") or {}).get("pid"), 654)
        self.assertEqual(((payload.get("runtime_summary") or {}).get("core") or {}).get("pid"), 123)
        self.assertEqual(((payload.get("runtime_summary") or {}).get("guard") or {}).get("status"), "starting")
        self.assertEqual(((payload.get("runtime_summary") or {}).get("core") or {}).get("status"), "heartbeat_only")
        self.assertEqual(payload.get("health_score"), 92)
        self.assertEqual(payload.get("self_check_pass_ratio"), 0.8)
        self.assertEqual(payload.get("alerts"), ["tool latency elevated"])

    def test_runtime_timeline_payload_combines_operator_guard_and_boot_events(self):
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

            with mock.patch.object(nova_http, "CONTROL_AUDIT_LOG", control_log), \
                mock.patch.object(nova_http, "GUARD_LOG_PATH", guard_log), \
                mock.patch.object(nova_http, "GUARD_BOOT_HISTORY_PATH", boot_history):
                payload = nova_http._runtime_timeline_payload(limit=10)

        events = payload.get("events") or []
        self.assertGreaterEqual(payload.get("count"), 4)
        self.assertEqual(events[0].get("title"), "Core reached running state")
        self.assertTrue(any(item.get("source") == "operator" and item.get("title") == "Guard Start" for item in events))
        self.assertTrue(any(item.get("title") == "Operator Prompt [MACRO]" and item.get("operator_source") == "cli" and item.get("operator_macro") == "inspect-runtime" for item in events))
        self.assertTrue(any(item.get("service") == "patch" and item.get("level") == "danger" for item in events))
        self.assertTrue(any(item.get("title") == "Boot observation failed" for item in events))

    def test_runtime_artifacts_payload_summarizes_runtime_files(self):
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

            with mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir), \
                mock.patch.object(nova_http, "CONTROL_AUDIT_LOG", runtime_dir / "control_action_audit.jsonl"), \
                mock.patch.object(nova_http, "GUARD_BOOT_HISTORY_PATH", runtime_dir / "guard_boot_history.json"), \
                mock.patch.object(nova_http, "GUARD_LOG_PATH", log_dir / "guard.log"):
                payload = nova_http._runtime_artifacts_payload()

        items = {item.get("name"): item for item in (payload.get("items") or [])}
        self.assertEqual(payload.get("count"), 7)
        self.assertEqual((items.get("core_state.json") or {}).get("status"), "present")
        self.assertIn("pid=321", (items.get("core_state.json") or {}).get("summary", ""))
        self.assertEqual((items.get("core.heartbeat") or {}).get("status"), "running")
        self.assertIn("last_action=guard_status", (items.get("control_action_audit.jsonl") or {}).get("summary", ""))
        self.assertIn("Core pid=123 reached RUNNING state", (items.get("guard.log") or {}).get("summary", ""))

    def test_runtime_artifact_detail_payload_returns_full_detail(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            log_dir = Path(td) / "logs"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)

            guard_log = log_dir / "guard.log"
            guard_log.write_text(
                "2024-03-09 16:00:08 | [GUARD] Core pid=123 reached RUNNING state\n",
                encoding="utf-8",
            )

            with mock.patch.object(nova_http, "GUARD_LOG_PATH", guard_log):
                payload = nova_http._runtime_artifact_detail_payload("guard.log", max_lines=20)

        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("service"), "guard")
        self.assertTrue(str(payload.get("path") or "").endswith("guard.log"))
        self.assertIn("RUNNING state", payload.get("content", ""))

    def test_runtime_restart_analytics_payload_detects_flapping(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            boot_history = runtime_dir / "guard_boot_history.json"
            boot_history.write_text(
                json.dumps([
                    {"ts": 1710000000, "success": False, "reason": "boot_timeout", "total_observed_s": 12.0},
                    {"ts": 1710000300, "success": False, "reason": "heartbeat_stale", "total_observed_s": 10.0},
                    {"ts": 1710000600, "success": False, "reason": "boot_timeout", "total_observed_s": 11.0},
                ]),
                encoding="utf-8",
            )

            with mock.patch.object(nova_http, "GUARD_BOOT_HISTORY_PATH", boot_history), \
                mock.patch("nova_http.time.time", return_value=1710000700):
                payload = nova_http._runtime_restart_analytics_payload()

        self.assertEqual(payload.get("flap_level"), "danger")
        self.assertEqual(payload.get("consecutive_failures"), 3)
        self.assertEqual(payload.get("recent_restart_count_15m"), 3)
        self.assertIn("instability", str(payload.get("flap_summary") or "").lower())

    def test_runtime_failure_reasons_follow_status_and_timeline(self):
        timeline_payload = {
            "events": [
                {"service": "core", "level": "danger", "title": "Core attempt failed", "detail": "heartbeat_stale"},
                {"service": "guard", "level": "warn", "title": "Guard stop requested", "detail": "Stop file detected by supervisor."},
            ]
        }
        payload = nova_http._runtime_failure_reasons_payload(
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

    def test_action_readiness_payload_explains_runtime_controls(self):
        payload = nova_http._action_readiness_payload(
            {"running": True, "stop_flag": False, "status": "running"},
            {"running": False, "pid": None, "state_exists": False, "status": "stopped"},
            {"running": True, "status": "running"},
        )

        self.assertFalse((payload.get("guard_start") or {}).get("enabled"))
        self.assertIn("already running", ((payload.get("guard_start") or {}).get("reason") or "").lower())
        self.assertTrue((payload.get("core_restart") or {}).get("enabled"))
        self.assertTrue((payload.get("webui_restart") or {}).get("enabled"))

    def test_patch_action_readiness_payload_explains_preview_controls(self):
        payload = nova_http._patch_action_readiness_payload({
            "enabled": True,
            "strict_manifest": True,
            "behavioral_check": True,
            "tests_available": True,
            "last_preview_name": "preview_a.txt",
            "previews": [
                {"name": "preview_a.txt", "status": "eligible", "decision": "approved"},
                {"name": "preview_b.txt", "status": "rejected: non-forward revision", "decision": "pending"},
            ],
        })

        approved = ((payload.get("by_preview") or {}).get("preview_a.txt") or {})
        blocked = ((payload.get("by_preview") or {}).get("preview_b.txt") or {})
        self.assertEqual(payload.get("default_preview"), "preview_a.txt")
        self.assertTrue(((approved.get("apply") or {}).get("enabled")))
        self.assertFalse(((blocked.get("apply") or {}).get("enabled")))
        self.assertIn("not eligible", ((blocked.get("apply") or {}).get("reason") or "").lower())

    def test_control_status_payload_includes_runtime_timeline(self):
        policy = {
            "tools_enabled": {"web": False},
            "memory": {"enabled": False, "scope": "private"},
            "web": {"enabled": False, "search_provider": "html", "search_api_endpoint": "", "allow_domains": []},
        }
        timeline_payload = {"count": 1, "events": [{"ts": 1710000000, "title": "Guard online", "level": "good", "source": "guard", "service": "guard", "detail": "Deterministic supervisor loop active."}]}
        artifact_payload = {"count": 1, "items": [{"name": "core_state.json", "status": "present"}]}
        failure_payload = {"guard": {"summary": "Healthy"}, "core": {"summary": "Healthy"}, "webui": {"summary": "Healthy"}}
        readiness_payload = {"guard_start": {"enabled": True, "reason": "ok"}}
        restart_analytics_payload = {"count": 2, "flap_level": "warn", "flap_summary": "Restart pressure elevated."}
        patch_action_readiness = {"default_preview": "preview.txt", "by_preview": {"preview.txt": {"apply": {"enabled": False, "reason": "Preview must be approved before apply."}}}}
        with ExitStack() as stack:
            stack.enter_context(mock.patch("nova_http.nova_core.load_policy", return_value=policy))
            stack.enter_context(mock.patch("nova_http.nova_core.ollama_api_up", return_value=False))
            stack.enter_context(mock.patch("nova_http.nova_core.chat_model", return_value="test-model"))
            stack.enter_context(mock.patch("nova_http.nova_core.mem_enabled", return_value=False))
            stack.enter_context(mock.patch("nova_http.nova_core.mem_stats_payload", return_value={"ok": True, "total": 0, "by_user": {}}))
            stack.enter_context(mock.patch("nova_http.nova_core.patch_status_payload", return_value={"ok": True, "enabled": True, "strict_manifest": True, "allow_force": False, "behavioral_check": True, "behavioral_check_timeout_sec": 600, "tests_available": True, "pipeline_ready": True, "current_revision": 4, "previews_total": 0, "previews_pending": 0, "previews_approved": 0, "previews_rejected": 0, "previews_eligible": 0, "previews_approved_eligible": 0, "last_preview_name": "", "last_preview_status": "", "last_preview_decision": "", "last_patch_log_line": "", "ready_for_validated_apply": False}))
            stack.enter_context(mock.patch("nova_http._chat_login_enabled", return_value=False))
            stack.enter_context(mock.patch("nova_http._chat_auth_source", return_value="disabled"))
            stack.enter_context(mock.patch("nova_http._chat_users", return_value={}))
            stack.enter_context(mock.patch("nova_http._memory_events_summary", return_value={"ok": True, "count": 0}))
            stack.enter_context(mock.patch("nova_http._tool_events_summary", return_value={"ok": True, "count": 0}))
            stack.enter_context(mock.patch("nova_http._action_ledger_summary", return_value={"ok": True, "count": 0}))
            stack.enter_context(mock.patch("nova_http._guard_status_payload", return_value={"running": True, "status": "running", "process_count": 1, "lock_exists": True, "stop_flag": False}))
            stack.enter_context(mock.patch("nova_http._core_status_payload", return_value={"running": True, "status": "running", "pid": 123, "heartbeat_age_sec": 1, "process_count": 1, "state_exists": True}))
            stack.enter_context(mock.patch("nova_http._http_status_payload", return_value={"running": True, "status": "running", "pid": 456, "process_count": 1}))
            stack.enter_context(mock.patch("nova_http._runtime_timeline_payload", return_value=timeline_payload))
            stack.enter_context(mock.patch("nova_http._runtime_artifacts_payload", return_value=artifact_payload))
            stack.enter_context(mock.patch("nova_http._runtime_restart_analytics_payload", return_value=restart_analytics_payload))
            stack.enter_context(mock.patch("nova_http._runtime_failure_reasons_payload", return_value=failure_payload))
            stack.enter_context(mock.patch("nova_http._action_readiness_payload", return_value=readiness_payload))
            stack.enter_context(mock.patch("nova_http._patch_action_readiness_payload", return_value=patch_action_readiness))
            stack.enter_context(mock.patch("nova_http._append_metrics_snapshot", return_value=None))
            stack.enter_context(mock.patch("nova_http._build_self_check", return_value={"health_score": 100, "pass_ratio": 1.0, "alerts": []}))
            payload = nova_http._control_status_payload()

        self.assertEqual((payload.get("runtime_timeline") or {}).get("count"), 1)
        self.assertEqual((((payload.get("runtime_timeline") or {}).get("events") or [])[0]).get("title"), "Guard online")
        self.assertEqual((payload.get("runtime_artifacts") or {}).get("count"), 1)
        self.assertEqual((payload.get("runtime_restart_analytics") or {}).get("flap_level"), "warn")
        self.assertEqual((((payload.get("runtime_failures") or {}).get("guard") or {}).get("summary")), "Healthy")
        self.assertTrue(((payload.get("action_readiness") or {}).get("guard_start") or {}).get("enabled"))
        self.assertEqual((payload.get("patch_action_readiness") or {}).get("default_preview"), "preview.txt")

    def test_control_self_check_alerts_when_patch_behavioral_gate_disabled(self):
        status_payload = {
            "ok": True,
            "ollama_api_up": True,
            "guard": {},
            "tool_events_ok": True,
            "patch_status_ok": True,
            "patch_enabled": True,
            "patch_strict_manifest": True,
            "patch_behavioral_check": False,
            "patch_tests_available": True,
        }
        policy_payload = {"ok": True, "tools_enabled": {"web": False}, "web": {"enabled": False, "allow_domains": []}}
        metrics_payload = {"ok": True, "points": []}

        with mock.patch("nova_http.capabilities_mod.list_capabilities", return_value={}):
            payload = nova_http._build_self_check(status_payload, policy_payload, metrics_payload)

        self.assertIn("patch_behavioral_check_disabled", payload.get("alerts", []))
        failed = {item["name"] for item in payload.get("checks", []) if not item.get("ok")}
        self.assertIn("patch_behavioral_gate", failed)

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

    def test_control_action_patch_preview_list_returns_previews_and_patch_status(self):
        previews = [{"name": "preview_a.txt", "status": "eligible", "decision": "pending"}]
        patch_payload = {"ok": True, "previews_total": 1}

        with mock.patch("nova_http.nova_core.patch_preview_summaries", return_value=previews) as previews_mock, \
            mock.patch("nova_http.nova_core.patch_status_payload", return_value=patch_payload) as patch_mock, \
            mock.patch("nova_http._patch_action_readiness_payload", return_value={"default_preview": "preview_a.txt"}):
            ok, msg, extra = nova_http._control_action("patch_preview_list", {})

        self.assertTrue(ok)
        self.assertEqual(msg, "patch_preview_list_ok")
        self.assertEqual(extra.get("previews"), previews)
        self.assertEqual(extra.get("patch"), patch_payload)
        self.assertEqual((extra.get("patch_action_readiness") or {}).get("default_preview"), "preview_a.txt")
        previews_mock.assert_called_once_with(40)
        patch_mock.assert_called_once_with()

    def test_control_action_runtime_artifact_show(self):
        artifact_payload = {"ok": True, "name": "guard.log", "content": "guard detail"}
        with mock.patch("nova_http._runtime_artifact_detail_payload", return_value=artifact_payload) as detail_mock:
            ok, msg, extra = nova_http._control_action("runtime_artifact_show", {"artifact": "guard.log", "lines": 50})

        self.assertTrue(ok)
        self.assertEqual(msg, "runtime_artifact_show_ok")
        self.assertEqual((extra.get("artifact") or {}).get("name"), "guard.log")
        detail_mock.assert_called_once_with("guard.log", max_lines=50)

    def test_control_action_patch_preview_show_returns_preview_text(self):
        previews = [{"name": "preview_a.txt", "status": "eligible", "decision": "pending"}]
        patch_payload = {"ok": True, "previews_total": 1}

        with mock.patch("nova_http.nova_core.show_preview", return_value="Patch Preview\nStatus: eligible") as show_mock, \
            mock.patch("nova_http.nova_core.patch_preview_summaries", return_value=previews), \
            mock.patch("nova_http.nova_core.patch_status_payload", return_value=patch_payload):
            ok, msg, extra = nova_http._control_action("patch_preview_show", {"preview": "preview_a.txt"})

        self.assertTrue(ok)
        self.assertEqual(msg, "patch_preview_show_ok")
        self.assertEqual(extra.get("preview"), "preview_a.txt")
        self.assertIn("Status: eligible", extra.get("text", ""))
        show_mock.assert_called_once_with("preview_a.txt")

    def test_control_action_patch_preview_approve_records_decision(self):
        previews = [{"name": "preview_a.txt", "status": "eligible", "decision": "approved"}]
        patch_payload = {"ok": True, "previews_total": 1, "last_preview_decision": "approved"}

        with mock.patch("nova_http.nova_core.approve_preview", return_value="Approved.") as approve_mock, \
            mock.patch("nova_http.nova_core.patch_preview_summaries", return_value=previews), \
            mock.patch("nova_http.nova_core.patch_status_payload", return_value=patch_payload):
            ok, msg, extra = nova_http._control_action("patch_preview_approve", {"preview": "preview_a.txt", "note": "safe to promote"})

        self.assertTrue(ok)
        self.assertEqual(msg, "patch_preview_approve_ok")
        self.assertEqual(extra.get("text"), "Approved.")
        approve_mock.assert_called_once_with("preview_a.txt", note="safe to promote")

    def test_control_action_patch_preview_reject_records_decision(self):
        previews = [{"name": "preview_a.txt", "status": "eligible", "decision": "rejected"}]
        patch_payload = {"ok": True, "previews_total": 1, "last_preview_decision": "rejected"}

        with mock.patch("nova_http.nova_core.reject_preview", return_value="Rejected.") as reject_mock, \
            mock.patch("nova_http.nova_core.patch_preview_summaries", return_value=previews), \
            mock.patch("nova_http.nova_core.patch_status_payload", return_value=patch_payload):
            ok, msg, extra = nova_http._control_action("patch_preview_reject", {"preview": "preview_a.txt", "note": "needs revision"})

        self.assertTrue(ok)
        self.assertEqual(msg, "patch_preview_reject_ok")
        self.assertEqual(extra.get("text"), "Rejected.")
        reject_mock.assert_called_once_with("preview_a.txt", note="needs revision")

    def test_control_action_patch_preview_apply_runs_patch_apply_for_approved_eligible_preview(self):
        previews = [{"name": "preview_a.txt", "path": "C:/Nova/updates/previews/preview_a.txt", "status": "eligible", "decision": "approved"}]
        patch_payload = {"ok": True, "previews_total": 1, "last_preview_decision": "approved"}

        with mock.patch("nova_http.nova_core.patch_preview_summaries", return_value=previews), \
            mock.patch("nova_http.nova_core.patch_status_payload", return_value=patch_payload), \
            mock.patch("nova_http.nova_core.show_preview", return_value="Patch Preview\nZip: teach_proposal_1.zip\nStatus: eligible") as show_mock, \
            mock.patch("nova_http.nova_core.patch_apply", return_value="Patch applied: 1 file(s). Compile check OK. Behavioral check OK (OK). Snapshot: snap.zip. Revision: 1.") as apply_mock, \
            mock.patch("pathlib.Path.exists", return_value=True):
            ok, msg, extra = nova_http._control_action("patch_preview_apply", {"preview": "preview_a.txt"})

        self.assertTrue(ok)
        self.assertEqual(msg, "patch_preview_apply_ok")
        self.assertIn("Patch applied", extra.get("text", ""))
        self.assertTrue(str(extra.get("zip", "")).endswith("teach_proposal_1.zip"))
        show_mock.assert_called_once_with("preview_a.txt")
        apply_mock.assert_called_once()

    def test_control_action_patch_preview_apply_blocks_pending_preview(self):
        previews = [{"name": "preview_a.txt", "path": "C:/Nova/updates/previews/preview_a.txt", "status": "eligible", "decision": "pending"}]
        patch_payload = {"ok": True, "previews_total": 1, "last_preview_decision": "pending"}

        with mock.patch("nova_http.nova_core.patch_preview_summaries", return_value=previews), \
            mock.patch("nova_http.nova_core.patch_status_payload", return_value=patch_payload), \
            mock.patch("nova_http.nova_core.patch_apply") as apply_mock:
            ok, msg, extra = nova_http._control_action("patch_preview_apply", {"preview": "preview_a.txt"})

        self.assertFalse(ok)
        self.assertEqual(msg, "patch_preview_not_approved")
        self.assertIn("must be approved", extra.get("text", ""))
        apply_mock.assert_not_called()

    def test_control_action_patch_preview_apply_blocks_noneligible_preview(self):
        previews = [{"name": "preview_a.txt", "path": "C:/Nova/updates/previews/preview_a.txt", "status": "rejected: non-forward revision", "decision": "approved"}]
        patch_payload = {"ok": True, "previews_total": 1, "last_preview_decision": "approved"}

        with mock.patch("nova_http.nova_core.patch_preview_summaries", return_value=previews), \
            mock.patch("nova_http.nova_core.patch_status_payload", return_value=patch_payload), \
            mock.patch("nova_http.nova_core.patch_apply") as apply_mock:
            ok, msg, extra = nova_http._control_action("patch_preview_apply", {"preview": "preview_a.txt"})

        self.assertFalse(ok)
        self.assertEqual(msg, "patch_preview_not_eligible")
        self.assertIn("not eligible", extra.get("text", ""))
        apply_mock.assert_not_called()

    def test_control_html_smoke_keeps_core_endpoints_and_tabs(self):
        html = nova_http.CONTROL_HTML
        script = (nova_http.STATIC_DIR / "control.js").read_text(encoding="utf-8")

        self.assertIn("/api/control/status", script)
        self.assertIn("/api/control/action", script)
        self.assertIn("/api/control/test-sessions", script)
        self.assertIn("renderPatchReadiness", script)
        self.assertIn("patchSummaryGrid", script)
        self.assertIn("btnPatchPreviewApprove", script)
        self.assertIn("btnPatchPreviewApply", script)
        self.assertIn("patchPreviewSelect", script)
        self.assertIn("patchPreviewBox", script)
        self.assertIn("runtimeBadgeClassForStatus", script)
        self.assertIn("runtime-summary-grid", script)
        self.assertIn("runtime-badge-button", script)
        self.assertIn("showRuntimeInspect", script)
        self.assertIn("renderRuntimeTimeline", script)
        self.assertIn("renderRuntimeFailures", script)
        self.assertIn("renderRuntimeArtifacts", script)
        self.assertIn("renderArtifactDetail", script)
        self.assertIn("renderRestartAnalytics", script)
        self.assertIn("renderActionReadiness", script)
        self.assertIn("renderPatchActionReadiness", script)
        self.assertIn("runtimeTimelineClass", script)
        self.assertIn("String(text == null ? '' : text)", script)
        self.assertIn("NYO System Control", html)
        self.assertIn("Not Your Ordinary AI System", html)
        self.assertIn("Overview", html)
        self.assertIn("Tools", html)
        self.assertIn("Sessions", html)
        self.assertIn("Logs", html)
        self.assertIn("Parity Test Runs", html)
        self.assertIn("Patch Readiness", html)
        self.assertIn("Runtime Timeline", html)
        self.assertIn("Failure Reasons", html)
        self.assertIn("Runtime Artifacts", html)
        self.assertIn("Artifact Drill-Down", html)
        self.assertIn("Restart Analytics", html)
        self.assertIn("Action Readiness", html)
        self.assertIn("Patch Action Readiness", html)
        self.assertIn("Runtime Summary", html)
        self.assertIn("Badge Legend", html)
        self.assertIn("Heartbeat Only", html)
        self.assertIn("Raw Runtime Fields", html)
        self.assertIn('id="patchStatusBadge"', html)
        self.assertIn('id="patchSummaryGrid"', html)
        self.assertIn('id="patchPreviewSelect"', html)
        self.assertIn('id="btnPatchPreviewShow"', html)
        self.assertIn('id="btnPatchPreviewApply"', html)
        self.assertIn('id="patchPreviewBox"', html)
        self.assertIn('id="btnGuardRestart"', html)
        self.assertIn('id="btnCoreStart"', html)
        self.assertIn('id="btnCoreStop"', html)
        self.assertIn('id="btnCoreRestart"', html)
        self.assertIn('id="btnWebuiRestart"', html)
        self.assertIn('id="runtimeTimeline"', html)
        self.assertIn('id="runtimeFailures"', html)
        self.assertIn('id="runtimeArtifacts"', html)
        self.assertIn('id="artifactDetailMeta"', html)
        self.assertIn('id="artifactDetailBox"', html)
        self.assertIn('id="restartAnalytics"', html)
        self.assertIn('id="runtimeActionReadiness"', html)
        self.assertIn('id="patchActionReadiness"', html)
        self.assertIn('id="runtimeLegend"', html)
        self.assertIn('id="runtimeRawBox"', html)
        self.assertIn('id="guardRawBox"', html)

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
            runtime_dir = base / "runtime"
            sessions_dir = base / "tests" / "sessions"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            sessions_dir.mkdir(parents=True, exist_ok=True)
            (sessions_dir / "gus_profile_test.json").write_text(
                json.dumps({"name": "Gus profile test", "messages": ["one", "two"]}, ensure_ascii=True),
                encoding="utf-8",
            )

            with mock.patch.object(nova_http, "BASE_DIR", base), \
                mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir):
                definitions = nova_http._available_test_session_definitions(10)

        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0].get("file"), "gus_profile_test.json")
        self.assertEqual(definitions[0].get("name"), "Gus profile test")
        self.assertEqual(definitions[0].get("message_count"), 2)

    def test_available_test_session_definitions_merges_generated_sessions_and_skips_manifests(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            runtime_dir = base / "runtime"
            saved_dir = base / "tests" / "sessions"
            generated_dir = runtime_dir / "test_sessions" / "generated_definitions"
            saved_dir.mkdir(parents=True, exist_ok=True)
            generated_dir.mkdir(parents=True, exist_ok=True)
            (saved_dir / "saved_session.json").write_text(
                json.dumps({"name": "Saved session", "messages": ["one"]}, ensure_ascii=True),
                encoding="utf-8",
            )
            (generated_dir / "generated_session.json").write_text(
                json.dumps({"name": "Generated session", "messages": ["one", "two"]}, ensure_ascii=True),
                encoding="utf-8",
            )
            (generated_dir / "latest_manifest.json").write_text(
                json.dumps({"definition_count": 1, "files": ["generated_session.json"]}, ensure_ascii=True),
                encoding="utf-8",
            )

            with mock.patch.object(nova_http, "BASE_DIR", base), \
                mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir):
                definitions = nova_http._available_test_session_definitions(10)

        self.assertEqual(len(definitions), 2)
        origin_by_file = {item.get("file"): item.get("origin") for item in definitions}
        self.assertEqual(origin_by_file.get("saved_session.json"), "saved")
        self.assertEqual(origin_by_file.get("generated_session.json"), "generated")
        self.assertNotIn("latest_manifest.json", origin_by_file)

    def test_control_status_payload_includes_subconscious_summary(self):
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
            mock.patch("nova_http.nova_core.patch_status_payload", return_value={"ok": True}), \
            mock.patch("nova_http._chat_login_enabled", return_value=False), \
            mock.patch("nova_http._chat_auth_source", return_value="disabled"), \
            mock.patch("nova_http._chat_users", return_value={}), \
            mock.patch("nova_http._memory_events_summary", return_value={"ok": True, "count": 0}), \
            mock.patch("nova_http._tool_events_summary", return_value={"ok": True, "count": 0}), \
            mock.patch("nova_http._action_ledger_summary", return_value={"ok": True, "count": 0}), \
            mock.patch("nova_http._guard_status_payload", return_value={"running": False, "status": "stopped", "process_count": 0, "lock_exists": False, "stop_flag": False}), \
            mock.patch("nova_http._core_status_payload", return_value={"running": False, "status": "stopped", "pid": None, "heartbeat_age_sec": None, "process_count": 0, "state_exists": True}), \
            mock.patch("nova_http._http_status_payload", return_value={"running": True, "status": "running", "pid": 456, "process_count": 1}), \
            mock.patch("nova_http._append_metrics_snapshot", return_value=None), \
            mock.patch("nova_http._build_self_check", return_value={"health_score": 100, "pass_ratio": 1.0, "alerts": []}), \
            mock.patch("nova_http._generated_work_queue", return_value={
                "count": 3,
                "open_count": 2,
                "green_count": 1,
                "warning_count": 0,
                "drift_count": 1,
                "never_run_count": 1,
                "next_item": {"file": "next_generated.json", "latest_status": "drift", "open": True},
                "items": [{"file": "next_generated.json", "latest_status": "drift", "open": True}],
            }), \
            mock.patch("nova_http._subconscious_status_summary", return_value={
                "ok": True,
                "generated_at": "2026-03-24 10:17:01",
                "label": "hourly",
                "family_count": 7,
                "variation_count": 26,
                "training_priority_count": 8,
                "generated_definition_count": 6,
                "latest_report_path": "runtime/subconscious_runs/latest.json",
                "top_priorities": [{"signal": "fallback_overuse", "urgency": "high", "seam": "route_selection", "suggested_test_name": "route_selection_fallback_overuse", "robustness": 1.0}],
            }):
            payload = nova_http._control_status_payload()

        self.assertTrue(payload.get("subconscious_ok"))
        self.assertEqual(payload.get("subconscious_label"), "hourly")
        self.assertEqual(payload.get("subconscious_family_count"), 7)
        self.assertEqual(payload.get("subconscious_generated_definition_count"), 6)
        self.assertEqual(len(payload.get("subconscious_top_priorities") or []), 1)
        self.assertEqual(payload.get("generated_work_queue_open_count"), 2)
        self.assertEqual(payload.get("generated_work_queue_next_file"), "next_generated.json")
        self.assertEqual((payload.get("generated_work_queue") or {}).get("count"), 3)
        self.assertEqual((payload.get("subconscious_summary") or {}).get("training_priority_count"), 8)

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

    def test_control_action_operator_prompt_routes_through_process_chat(self):
        summary = {
            "session_id": "operator-abc123",
            "owner": "operator",
            "turn_count": 2,
            "last_user": "inspect the runtime",
            "last_assistant": "Runtime looks healthy.",
        }

        with mock.patch("nova_http._assert_session_owner", return_value=(True, "owner_bound")) as owner_mock, \
            mock.patch("nova_http.process_chat", return_value="Runtime looks healthy.") as chat_mock, \
            mock.patch("nova_http._session_summaries", return_value=[summary]):
            ok, msg, extra = nova_http._control_action("operator_prompt", {"message": "inspect the runtime", "session_id": "operator-abc123"})

        self.assertTrue(ok)
        self.assertEqual(msg, "operator_prompt_ok")
        self.assertEqual(extra.get("session_id"), "operator-abc123")
        self.assertEqual(extra.get("reply"), "Runtime looks healthy.")
        self.assertEqual((extra.get("session") or {}).get("turn_count"), 2)
        owner_mock.assert_called_once_with("operator-abc123", "operator", allow_bind=True)
        chat_mock.assert_called_once_with("operator-abc123", "inspect the runtime", user_id="operator")

    def test_control_action_operator_prompt_uses_saved_macro(self):
        summary = {
            "session_id": "operator-abc123",
            "owner": "operator",
            "turn_count": 2,
        }

        with mock.patch("nova_http._resolve_operator_macro", return_value={"macro_id": "inspect-runtime", "prompt": "Inspect the runtime thoroughly."}), \
            mock.patch("nova_http._assert_session_owner", return_value=(True, "owner_bound")), \
            mock.patch("nova_http.process_chat", return_value="Runtime looks healthy.") as chat_mock, \
            mock.patch("nova_http._session_summaries", return_value=[summary]):
            ok, msg, extra = nova_http._control_action("operator_prompt", {"macro": "inspect-runtime", "session_id": "operator-abc123", "message": "focus on restart pressure"})

        self.assertTrue(ok)
        self.assertEqual(msg, "operator_prompt_ok")
        self.assertEqual((extra.get("macro") or {}).get("macro_id"), "inspect-runtime")
        chat_mock.assert_called_once_with(
            "operator-abc123",
            "Inspect the runtime thoroughly.\n\nOperator note: focus on restart pressure",
            user_id="operator",
        )

    def test_control_action_operator_prompt_renders_macro_placeholders(self):
        summary = {
            "session_id": "operator-abc123",
            "owner": "operator",
            "turn_count": 2,
        }

        macro = {
            "macro_id": "inspect-runtime",
            "prompt_template": "Inspect {focus_area} with a {detail_level} report.",
            "placeholders": [
                {"name": "focus_area", "required": True},
                {"name": "detail_level", "default": "concise"},
            ],
        }

        with mock.patch("nova_http._resolve_operator_macro", return_value=macro), \
            mock.patch("nova_http._assert_session_owner", return_value=(True, "owner_bound")), \
            mock.patch("nova_http.process_chat", return_value="Runtime looks healthy.") as chat_mock, \
            mock.patch("nova_http._session_summaries", return_value=[summary]):
            ok, msg, extra = nova_http._control_action(
                "operator_prompt",
                {
                    "macro": "inspect-runtime",
                    "session_id": "operator-abc123",
                    "source": "cli",
                    "message": "include restart pressure",
                    "macro_values": {"focus_area": "restart pressure"},
                },
            )

        self.assertTrue(ok)
        self.assertEqual(msg, "operator_prompt_ok")
        self.assertEqual(extra.get("resolved_macro_values"), {"focus_area": "restart pressure", "detail_level": "concise"})
        chat_mock.assert_called_once_with(
            "operator-abc123",
            "Inspect restart pressure with a concise report.\n\nOperator note: include restart pressure",
            user_id="operator",
        )

    def test_control_action_operator_prompt_requires_required_macro_placeholder(self):
        macro = {
            "macro_id": "inspect-runtime",
            "prompt_template": "Inspect {focus_area}.",
            "placeholders": [
                {"name": "focus_area", "required": True},
            ],
        }

        with mock.patch("nova_http._resolve_operator_macro", return_value=macro):
            ok, msg, extra = nova_http._control_action(
                "operator_prompt",
                {"macro": "inspect-runtime", "session_id": "operator-abc123", "source": "cli"},
            )

        self.assertFalse(ok)
        self.assertEqual(msg, "operator_macro_placeholder_required:focus_area")
        self.assertEqual((extra.get("macro") or {}).get("macro_id"), "inspect-runtime")
        self.assertEqual(extra.get("resolved_macro_values"), {})

    def test_control_action_operator_prompt_requires_message(self):
        ok, msg, extra = nova_http._control_action("operator_prompt", {"session_id": "operator-abc123"})

        self.assertFalse(ok)
        self.assertEqual(msg, "operator_message_required")
        self.assertEqual(extra, {})

    def test_control_action_generated_pack_run_executes_generated_definitions(self):
        definitions = [
            {"file": "generated_a.json", "name": "Generated A", "origin": "generated"},
            {"file": "generated_b.json", "name": "Generated B", "origin": "generated"},
            {"file": "saved.json", "name": "Saved", "origin": "saved"},
        ]
        reports = [{"run_id": "generated_b_20260324_110000", "status": "green"}]

        def run_side_effect(session_file):
            return True, f"test_session_run_completed:{session_file}", {"latest_report": {"run_id": session_file + "_report"}}

        with mock.patch("nova_http._available_test_session_definitions", return_value=definitions), \
            mock.patch("nova_http._run_test_session_definition", side_effect=run_side_effect) as run_mock, \
            mock.patch("nova_http._test_session_report_summaries", return_value=reports):
            ok, msg, extra = nova_http._control_action("generated_pack_run", {"limit": 2})

        self.assertTrue(ok)
        self.assertEqual(msg, "generated_test_sessions_run_recent_completed:2")
        self.assertEqual(extra.get("count"), 2)
        self.assertEqual(extra.get("mode"), "recent")
        self.assertEqual(len(extra.get("results") or []), 2)
        self.assertEqual(extra.get("latest_report"), reports[0])
        self.assertEqual(run_mock.call_count, 2)

    def test_control_action_generated_pack_run_priority_prefers_highest_priority(self):
        definitions = [
            {"file": "low.json", "name": "Low", "origin": "generated", "training_priorities": [{"urgency": "low", "robustness": 0.4}]},
            {"file": "high.json", "name": "High", "origin": "generated", "training_priorities": [{"urgency": "high", "robustness": 0.9}]},
            {"file": "medium.json", "name": "Medium", "origin": "generated", "training_priorities": [{"urgency": "medium", "robustness": 0.8}]},
        ]

        with mock.patch("nova_http._available_test_session_definitions", return_value=definitions), \
            mock.patch("nova_http._test_session_report_summaries", return_value=[]), \
            mock.patch("nova_http._run_test_session_definition", return_value=(True, "ok", {"latest_report": {}})) as run_mock:
            ok, msg, extra = nova_http._control_action("generated_pack_run", {"limit": 2, "mode": "priority"})

        self.assertTrue(ok)
        self.assertEqual(msg, "generated_test_sessions_run_priority_completed:2")
        self.assertEqual(extra.get("mode"), "priority")
        self.assertEqual([item.get("file") for item in (extra.get("results") or [])], ["high.json", "medium.json"])
        self.assertEqual([call.args[0] for call in run_mock.call_args_list], ["high.json", "medium.json"])

    def test_generated_work_queue_prefers_open_priority_items(self):
        definitions = [
            {"file": "low_green.json", "name": "Low green", "origin": "generated", "training_priorities": [{"urgency": "low", "robustness": 0.2}]},
            {"file": "high_drift.json", "name": "High drift", "origin": "generated", "training_priorities": [{"urgency": "high", "robustness": 0.9}]},
            {"file": "medium_new.json", "name": "Medium new", "origin": "generated", "training_priorities": [{"urgency": "medium", "robustness": 0.7}]},
        ]
        reports = [
            {"run_id": "high_drift_1", "session_path": "c:/Nova/runtime/test_sessions/generated_definitions/high_drift.json", "status": "drift", "comparison": {"diff_count": 1}, "report_path": "c:/Nova/runtime/test_sessions/high_drift/result.json"},
            {"run_id": "low_green_1", "session_path": "c:/Nova/runtime/test_sessions/generated_definitions/low_green.json", "status": "green", "comparison": {"diff_count": 0}, "report_path": "c:/Nova/runtime/test_sessions/low_green/result.json"},
        ]

        with mock.patch("nova_http._available_test_session_definitions", return_value=definitions), \
            mock.patch("nova_http._test_session_report_summaries", return_value=reports):
            queue = nova_http._generated_work_queue(10)

        self.assertEqual(queue.get("open_count"), 2)
        self.assertEqual((queue.get("next_item") or {}).get("file"), "high_drift.json")
        self.assertEqual([item.get("file") for item in (queue.get("items") or [])][:3], ["high_drift.json", "medium_new.json", "low_green.json"])

    def test_control_action_generated_queue_run_next_executes_selected_item(self):
        queue_before = {
            "count": 2,
            "open_count": 1,
            "next_item": {"file": "high_drift.json", "latest_status": "drift", "open": True},
            "items": [{"file": "high_drift.json", "latest_status": "drift", "open": True}],
        }
        queue_after = {
            "count": 2,
            "open_count": 0,
            "next_item": {},
            "items": [{"file": "high_drift.json", "latest_status": "green", "open": False}],
        }
        latest_report = {"run_id": "high_drift_2", "status": "green"}

        with mock.patch("nova_http._generated_work_queue", side_effect=[queue_before, queue_after]), \
            mock.patch("nova_http._run_test_session_definition", return_value=(True, "test_session_run_completed:high_drift.json", {"latest_report": latest_report, "reports": [latest_report], "definitions": []})) as run_mock:
            ok, msg, extra = nova_http._control_action("generated_queue_run_next", {})

        self.assertTrue(ok)
        self.assertEqual(msg, "generated_work_queue_next_ok:high_drift.json")
        self.assertEqual((extra.get("selected") or {}).get("file"), "high_drift.json")
        self.assertEqual(extra.get("latest_report"), latest_report)
        self.assertEqual((extra.get("work_queue") or {}).get("open_count"), 0)
        run_mock.assert_called_once_with("high_drift.json")

    def test_control_action_generated_queue_investigate_routes_to_operator_prompt(self):
        queue_payload = {
            "count": 2,
            "open_count": 1,
            "next_item": {
                "file": "high_drift.json",
                "family_id": "repeated-weak-pressure-family",
                "variation_id": "ambiguous_clarification",
                "latest_status": "drift",
                "open": True,
                "opportunity_reason": "parity_drift",
                "highest_priority": {"signal": "route_fit_weak", "urgency": "high", "seam": "subconscious_pressure_backlog_generation", "robustness": 0.97},
                "latest_comparison": {"diffs": [{"turn": 1, "issues": {"assistant": {}}}]},
            },
            "items": [],
        }
        summary = {
            "session_id": "operator-generated-queue",
            "owner": "operator",
            "turn_count": 2,
        }
        macro = {"macro_id": "subconscious-review", "prompt": "Review the latest subconscious run and recommend what to run next."}

        with mock.patch("nova_http._generated_work_queue", side_effect=[queue_payload, queue_payload]), \
            mock.patch("nova_http._resolve_operator_macro", return_value=macro), \
            mock.patch("nova_http._assert_session_owner", return_value=(True, "owner_bound")), \
            mock.patch("nova_http.process_chat", return_value="Investigated queue item.") as chat_mock, \
            mock.patch("nova_http._session_summaries", return_value=[summary]):
            ok, msg, extra = nova_http._control_action("generated_queue_investigate", {})

        self.assertTrue(ok)
        self.assertEqual(msg, "generated_work_queue_investigation_started")
        self.assertEqual((extra.get("selected") or {}).get("file"), "high_drift.json")
        self.assertEqual((extra.get("macro") or {}).get("macro_id"), "subconscious-review")
        self.assertEqual(extra.get("session_id"), "operator-generated-queue")
        self.assertEqual(extra.get("reply"), "Investigated queue item.")
        sent_message = chat_mock.call_args.args[1]
        self.assertIn("high_drift.json", sent_message)
        self.assertIn("route_fit_weak", sent_message)
        self.assertIn("turn 1: assistant", sent_message)

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

    def test_control_action_core_stop(self):
        with mock.patch("nova_http._stop_core_owned_process", return_value=(True, "core_stop_requested:123")) as stop_mock, \
            mock.patch("nova_http._guard_status_payload", return_value={"running": True, "status": "running"}), \
            mock.patch("nova_http._core_status_payload", return_value={"running": False, "status": "stopped"}):
            ok, msg, extra = nova_http._control_action("core_stop", {})

        self.assertTrue(ok)
        self.assertIn("core_stop_requested", msg)
        self.assertIn("core", extra)
        stop_mock.assert_called_once_with()

    def test_control_action_guard_restart(self):
        with mock.patch("nova_http._restart_guard", return_value=(True, "guard_restart_requested:guard_stop_requested")) as restart_mock, \
            mock.patch("nova_http._guard_status_payload", return_value={"running": False, "status": "stopped"}), \
            mock.patch("nova_http._core_status_payload", return_value={"running": False, "status": "stopped"}):
            ok, msg, extra = nova_http._control_action("guard_restart", {})

        self.assertTrue(ok)
        self.assertIn("guard_restart_requested", msg)
        self.assertIn("guard", extra)
        restart_mock.assert_called_once_with()

    def test_control_action_webui_restart(self):
        with mock.patch("nova_http._restart_webui", return_value=(True, "webui_restart_requested")) as restart_mock, \
            mock.patch("nova_http._http_status_payload", return_value={"running": True, "status": "running", "pid": 321, "process_count": 1}):
            ok, msg, extra = nova_http._control_action("webui_restart", {})

        self.assertTrue(ok)
        self.assertEqual(msg, "webui_restart_requested")
        self.assertEqual((extra.get("webui") or {}).get("pid"), 321)
        restart_mock.assert_called_once_with()

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
