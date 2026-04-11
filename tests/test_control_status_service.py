import unittest

from services.control_status import CONTROL_STATUS_SERVICE


class TestControlStatusService(unittest.TestCase):
    def test_status_payload_includes_runtime_timeline_and_patch_fields(self):
        payload = CONTROL_STATUS_SERVICE.status_payload(
            policy={"memory": {"scope": "private"}},
            provider="html",
            endpoint="",
            searx_ok=None,
            searx_note="n/a",
            search_provider_priority=["wikipedia", "stackexchange", "general_web"],
            provider_telemetry={"last_provider_used": "wikipedia", "hits_last_window": {"wikipedia": 2}},
            ollama_api_up=False,
            chat_model="test-model",
            memory_enabled=False,
            subconscious_summary={"ok": True},
            subconscious_live_summary={"tracked_session_count": 0},
            generated_work_queue={"open_count": 0, "next_item": {}},
            autonomy_maintenance={
                "runtime_worker": {"last_cycle_status": "ok", "interval_sec": 300, "cycle_count": 4, "last_completed_at": "2026-04-04 02:10:00"},
                "last_generated_queue_run": {"status": "ok", "selected_file": "demo.json", "ts": "2026-04-04 02:09:00", "latest_report_status": "green"},
            },
            operator_macros=[],
            backend_commands=[],
            memory_scope="private",
            web_enabled=False,
            allow_domains_count=0,
            process_counting_mode="logical_leaf_processes",
            runtime_process_note="note",
            heartbeat_age_sec=1,
            active_http_sessions=0,
            chat_login_enabled=False,
            chat_auth_source="disabled",
            chat_users_count=0,
            guard_status={"status": "running"},
            core_status={"status": "running", "running": True, "pid": 123, "heartbeat_age_sec": 1},
            webui_status={"status": "running", "pid": 456},
            runtime_summary={"guard": {"status": "running"}},
            timeline_payload={"count": 1, "events": [{"title": "Guard online"}]},
            runtime_artifacts={"count": 1, "items": [{"name": "core_state.json"}]},
            runtime_restart_analytics={"flap_level": "warn"},
            runtime_failures={"guard": {"summary": "Healthy"}},
            live_tracking={"available": False},
            action_readiness={"guard_start": {"enabled": True}},
            release_status={"latest_state": "promoted-pass"},
            memory_stats={"ok": True, "total": 0, "by_user": {}},
            memory_summary={"ok": True, "count": 0},
            tool_summary={"ok": True, "count": 0, "status_counts": {}},
            ledger_summary={"ok": True, "count": 0},
            patch_summary={"ok": True, "enabled": True, "current_revision": 4, "previews_total": 1, "last_patch_log_line": "ok", "previews": []},
            patch_action_readiness={"default_preview": "preview.txt"},
            pulse_payload={"generated_at": "now", "autonomy_level": "guarded", "promoted_total": 2, "promoted_delta": 1},
            update_now_pending={"pending": False},
            requests_total=7,
            errors_total=1,
        )

        self.assertEqual((payload.get("runtime_timeline") or {}).get("count"), 1)
        self.assertEqual((payload.get("runtime_artifacts") or {}).get("count"), 1)
        self.assertEqual(payload.get("patch_current_revision"), 4)
        self.assertEqual((payload.get("patch_action_readiness") or {}).get("default_preview"), "preview.txt")
        self.assertEqual(payload.get("requests_total"), 7)
        self.assertEqual(payload.get("last_provider_hit"), "wikipedia")
        self.assertEqual(payload.get("runtime_worker_status"), "ok")
        self.assertEqual(payload.get("last_generated_queue_run_file"), "demo.json")
        self.assertIn("plans", payload)
        self.assertEqual((payload.get("plans") or {}).get("schedule_tree"), [])

    def test_status_payload_includes_subconscious_and_queue_fields(self):
        payload = CONTROL_STATUS_SERVICE.status_payload(
            policy={"memory": {"scope": "private"}},
            provider="html",
            endpoint="",
            searx_ok=None,
            searx_note="n/a",
            search_provider_priority=["wikipedia", "stackexchange", "general_web"],
            provider_telemetry={"last_provider_used": "general_web", "hits_last_window": {"general_web": 1}},
            ollama_api_up=False,
            chat_model="test-model",
            memory_enabled=False,
            subconscious_summary={
                "ok": True,
                "label": "hourly",
                "family_count": 7,
                "generated_definition_count": 6,
                "top_priorities": [{"signal": "fallback_overuse", "seam": "session_fact_recall_route_fallthrough", "seam_label": "session fact recall route fallthrough"}],
            },
            subconscious_live_summary={"pressure_config": {"weak_signal_thresholds": {"route_unclear": 3}}},
            generated_work_queue={"open_count": 2, "count": 3, "next_item": {"file": "next_generated.json"}},
            autonomy_maintenance={
                "runtime_worker": {"last_cycle_status": "running", "interval_sec": 60, "cycle_count": 9},
                "last_generated_queue_run": {"status": "failed", "selected_file": "next_generated.json", "latest_report_status": "warning", "ts": "2026-04-04 03:00:00"},
            },
            operator_macros=[{"macro_id": "inspect"}],
            backend_commands=[{"command_id": "regression"}],
            memory_scope="private",
            web_enabled=False,
            allow_domains_count=0,
            process_counting_mode="logical_leaf_processes",
            runtime_process_note="note",
            heartbeat_age_sec=None,
            active_http_sessions=0,
            chat_login_enabled=False,
            chat_auth_source="disabled",
            chat_users_count=0,
            guard_status={},
            core_status={},
            webui_status={},
            runtime_summary={},
            timeline_payload={"count": 0, "events": []},
            runtime_artifacts={"count": 0, "items": []},
            runtime_restart_analytics={},
            runtime_failures={},
            live_tracking={},
            action_readiness={},
            release_status={},
            memory_stats={"ok": True, "total": 0, "by_user": {}},
            memory_summary={"ok": True, "count": 0},
            tool_summary={"ok": True, "count": 0, "status_counts": {}},
            ledger_summary={"ok": True, "count": 0},
            patch_summary={"ok": True},
            patch_action_readiness={},
            pulse_payload={},
            update_now_pending={},
            requests_total=0,
            errors_total=0,
            schedule_tree=[{"name": "core_heartbeat", "label": "Core Heartbeat"}],
        )

        self.assertTrue(payload.get("subconscious_ok"))
        self.assertEqual(payload.get("subconscious_label"), "hourly")
        self.assertEqual(payload.get("subconscious_family_count"), 7)
        self.assertEqual(payload.get("generated_work_queue_open_count"), 2)
        self.assertEqual(payload.get("generated_work_queue_next_file"), "next_generated.json")
        self.assertEqual(payload.get("backend_command_count"), 1)
        self.assertEqual((payload.get("subconscious_top_priorities") or [])[0].get("seam_label"), "session fact recall route fallthrough")
        self.assertEqual((payload.get("provider_telemetry") or {}).get("last_provider_used"), "general_web")
        self.assertEqual(payload.get("runtime_worker_status"), "running")
        self.assertEqual(payload.get("last_generated_queue_run_status"), "failed")
        self.assertEqual(payload.get("last_generated_queue_report_status"), "warning")
        self.assertEqual((payload.get("schedule_tree") or [])[0].get("name"), "core_heartbeat")
        self.assertEqual(((payload.get("plans") or {}).get("schedule_tree") or [])[0].get("label"), "Core Heartbeat")

    def test_status_payload_ignores_legacy_last_provider_when_priority_removed(self):
        payload = CONTROL_STATUS_SERVICE.status_payload(
            policy={"memory": {"scope": "private"}},
            provider="searxng",
            endpoint="http://127.0.0.1:8081/search",
            searx_ok=True,
            searx_note="status=200",
            search_provider_priority=["wikipedia", "stackexchange", "general_web"],
            provider_telemetry={"last_provider_used": "", "last_provider_family": "", "hits_last_window": {"stackexchange": 1}},
            ollama_api_up=False,
            chat_model="test-model",
            memory_enabled=False,
            subconscious_summary={"ok": True},
            subconscious_live_summary={},
            generated_work_queue={"open_count": 0, "next_item": {}},
            autonomy_maintenance={},
            operator_macros=[],
            backend_commands=[],
            memory_scope="private",
            web_enabled=True,
            allow_domains_count=0,
            process_counting_mode="logical_leaf_processes",
            runtime_process_note="note",
            heartbeat_age_sec=None,
            active_http_sessions=0,
            chat_login_enabled=False,
            chat_auth_source="disabled",
            chat_users_count=0,
            guard_status={},
            core_status={},
            webui_status={},
            runtime_summary={},
            timeline_payload={"count": 0, "events": []},
            runtime_artifacts={"count": 0, "items": []},
            runtime_restart_analytics={},
            runtime_failures={},
            live_tracking={},
            action_readiness={},
            release_status={},
            memory_stats={"ok": True, "total": 0, "by_user": {}},
            memory_summary={"ok": True, "count": 0},
            tool_summary={"ok": True, "count": 0, "status_counts": {}},
            ledger_summary={"ok": True, "count": 1, "last_record": {"provider_used": "github", "provider_family": "github"}},
            patch_summary={"ok": True},
            patch_action_readiness={},
            pulse_payload={},
            update_now_pending={},
            requests_total=0,
            errors_total=0,
        )

        self.assertEqual(payload.get("last_provider_hit"), "")
        self.assertEqual(payload.get("last_provider_family"), "")


if __name__ == "__main__":
    unittest.main()