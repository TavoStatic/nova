import unittest

from services.control_status import CONTROL_STATUS_SERVICE


class TestControlStatusService(unittest.TestCase):
    def test_runtime_supplier_fns_from_scope_collects_http_supplier_contract(self):
        scope = {
            "_probe_searxng": object(),
            "_guard_status_payload": object(),
            "_core_status_payload": object(),
            "_http_status_payload": object(),
            "_runtime_timeline_payload": object(),
            "_subconscious_status_summary": object(),
            "_subconscious_live_summary": object(),
            "_generated_work_queue": object(),
            "_autonomy_maintenance_summary": object(),
            "_load_operator_macros": object(),
            "_load_backend_commands": object(),
            "_memory_events_summary": object(),
            "_tool_events_summary": object(),
            "_action_ledger_summary": object(),
            "_provider_telemetry_payload": object(),
            "_runtime_summary_payload": object(),
            "_runtime_artifacts_payload": object(),
            "_runtime_restart_analytics_payload": object(),
            "_runtime_failure_reasons_payload": object(),
            "_action_readiness_payload": object(),
            "_release_status_payload": object(),
            "_patch_action_readiness_payload": object(),
            "_storage_watch_summary": object(),
            "_runtime_process_note": object(),
            "_heartbeat_age_seconds": object(),
            "_chat_login_enabled": object(),
            "_chat_auth_source": object(),
            "_chat_users": object(),
            "_append_metrics_snapshot": object(),
            "_build_self_check": object(),
            "_control_policy_payload": object(),
            "_metrics_payload": object(),
        }

        payload = CONTROL_STATUS_SERVICE.runtime_supplier_fns_from_scope(scope)

        self.assertIs(payload["probe_searxng"], scope["_probe_searxng"])
        self.assertIs(payload["provider_telemetry_payload"], scope["_provider_telemetry_payload"])
        self.assertIs(payload["metrics_payload"], scope["_metrics_payload"])
        self.assertEqual(len(payload), 32)

    def test_runtime_status_payload_collects_supplier_outputs(self):
        class _Core:
            @staticmethod
            def load_policy():
                return {
                    "memory": {"scope": "private"},
                    "tools_enabled": {"web": True},
                    "web": {
                        "enabled": True,
                        "search_provider": "searxng",
                        "search_api_endpoint": "http://127.0.0.1:8081/search",
                        "allow_domains": ["example.org"],
                    },
                }

            @staticmethod
            def get_search_provider_priority():
                return ["general_web"]

            @staticmethod
            def ollama_api_up():
                return True

            @staticmethod
            def chat_model():
                return "test-model"

            @staticmethod
            def mem_enabled():
                return True

            @staticmethod
            def mem_stats_payload(*, emit_event=False):
                return {"ok": True, "total": 1, "by_user": {"u1": 1}}

            @staticmethod
            def patch_status_payload():
                return {"ok": True, "enabled": True}

            @staticmethod
            def build_pulse_payload():
                return {
                    "generated_at": "now",
                    "autonomy_level": "guarded",
                    "memory_health_status": "ok",
                    "memory_db_total": 756,
                    "memory_scoped_total": 1,
                    "memory_health_issue_count": 0,
                    "memory_events_log_status": "ok",
                    "memory_events_log_bytes": 42,
                    "memory_events_log_invalid_tail_count": 0,
                }

            @staticmethod
            def update_now_pending_payload():
                return {"pending": False}

            @staticmethod
            def runtime_device_location_payload():
                return {"available": False}

        payload = CONTROL_STATUS_SERVICE.runtime_status_payload(
            core_module=_Core(),
            session_turns={"s1": [], "s2": []},
            metrics_totals=(5, 1),
            supplier_fns={
                "probe_searxng": lambda endpoint: (True, f"ok:{endpoint}"),
                "guard_status_payload": lambda: {"running": True, "status": "running"},
                "core_status_payload": lambda: {"running": True, "status": "running", "pid": 123, "heartbeat_age_sec": 1},
                "http_status_payload": lambda: {"running": True, "status": "running", "pid": 456},
                "runtime_timeline_payload": lambda: {"count": 0, "events": []},
                "subconscious_status_summary": lambda: {"ok": True},
                "subconscious_live_summary": lambda: {},
                "generated_work_queue": lambda limit: {"status": "clear", "open_count": 0, "actionable_count": 0, "next_item": {}},
                "autonomy_maintenance_summary": lambda: {},
                "load_operator_macros": lambda limit: [],
                "load_backend_commands": lambda limit: [],
                "memory_events_summary": lambda limit: {"ok": True, "count": 0},
                "tool_events_summary": lambda limit: {"ok": True, "count": 0, "status_counts": {}},
                "action_ledger_summary": lambda limit: {"ok": True, "count": 0},
                "provider_telemetry_payload": lambda **kwargs: {"last_provider_used": "general_web"},
                "runtime_summary_payload": lambda **kwargs: {"guard": kwargs.get("guard")},
                "runtime_artifacts_payload": lambda: {"count": 0, "items": []},
                "runtime_restart_analytics_payload": lambda: {},
                "runtime_failure_reasons_payload": lambda guard, core, webui, timeline: {},
                "action_readiness_payload": lambda guard, core, webui: {},
                "release_status_payload": lambda: {},
                "patch_action_readiness_payload": lambda patch_summary: {"ready": True},
                "storage_watch_summary": lambda: {"status": "ok", "note": "fine", "total_bytes": 128},
                "runtime_process_note": lambda: "note",
                "heartbeat_age_seconds": lambda: 1,
                "chat_login_enabled": lambda: False,
                "chat_auth_source": lambda: "disabled",
                "chat_users": lambda: ["user-a"],
                "append_metrics_snapshot": lambda payload: payload.update({"metrics_snapshot_test": True}),
                "build_self_check": lambda payload, policy, metrics: {"health_score": 97, "pass_ratio": 0.75, "alerts": ["warn"]},
                "control_policy_payload": lambda: {"ok": True},
                "metrics_payload": lambda: {"ok": True},
            },
        )

        self.assertEqual(payload.get("requests_total"), 5)
        self.assertEqual(payload.get("errors_total"), 1)
        self.assertEqual(payload.get("active_http_sessions"), 2)
        self.assertEqual(payload.get("health_score"), 97)
        self.assertEqual(payload.get("self_check_pass_ratio"), 0.75)
        self.assertEqual(payload.get("alerts"), ["warn"])
        self.assertTrue(payload.get("metrics_snapshot_test"))
        self.assertEqual(payload.get("searxng_note"), "ok:http://127.0.0.1:8081/search")
        self.assertEqual(payload.get("memory_health_status"), "ok")
        self.assertEqual(payload.get("memory_db_total"), 756)
        self.assertEqual(payload.get("memory_scoped_total"), 1)
        self.assertEqual(payload.get("memory_events_log_status"), "ok")
        self.assertEqual(payload.get("memory_events_log_bytes"), 42)

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
                "last_autonomy_orchestrator": {
                    "ts": "2026-05-06 12:30:00",
                    "mode": "advisory",
                    "decision": "recommend_action",
                    "action": {"act": "generated_queue_run_next"},
                    "reason": "Generated Work Queue has 1 actionable item.",
                    "ledger_status": "recorded",
                },
                "autonomy_orchestrator_summary": {
                    "count": 4,
                    "recommendation_changes": 1,
                    "recommendation_change_rate": 0.3333,
                    "stable_recommendation": False,
                    "weak_posture_refusal_rate": 1.0,
                },
                "last_patch_cleanup": {
                    "status": "ok",
                    "ts": "2026-04-04 02:08:00",
                    "orphan_rejected_count": 8,
                    "superseded_archived_count": 12,
                    "review_total_before": 14,
                    "review_total_after": 5,
                    "orphaned_before": 4,
                    "orphaned_after": 0,
                    "superseded_before": 20,
                    "superseded_after": 1,
                    "archive_dir": "C:/Nova/updates/previews/archive",
                },
                "last_complete_tree_archive": {
                    "status": "ok",
                    "ts": "2026-04-04 02:07:00",
                    "archived_count": 12,
                    "retained_count": 8,
                },
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
            patch_summary={
                "ok": True,
                "enabled": True,
                "current_revision": 4,
                "previews_total": 12,
                "previews_pending": 9,
                "previews_approved": 3,
                "previews_orphaned": 2,
                "review_previews_total": 5,
                "review_previews_pending_distinct": 3,
                "review_previews_pending_superseded": 4,
                "review_previews_approved_distinct": 2,
                "review_previews_approved_superseded": 1,
                "review_previews_orphaned": 1,
                "review_previews_superseded_total": 5,
                "last_patch_log_line": "ok",
                "previews": [],
            },
            patch_action_readiness={"default_preview": "preview.txt"},
            pulse_payload={
                "generated_at": "now",
                "autonomy_level": "guarded",
                "promoted_total": 2,
                "promoted_delta": 1,
                "memory_health_status": "watch",
                "memory_health_issue_count": 1,
                "memory_db_total": 756,
                "memory_scoped_total": 0,
                "memory_health": {
                    "memory_events_log": {
                        "status": "watch",
                        "byte_count": 99,
                        "invalid_tail_count": 1,
                    },
                },
                "memory_health_issues": [{"code": "learned_facts_orphan_tmp", "detail": "valid tmp without final"}],
            },
            update_now_pending={"pending": False},
            requests_total=7,
            errors_total=1,
        )

        self.assertEqual((payload.get("runtime_timeline") or {}).get("count"), 1)
        self.assertEqual((payload.get("runtime_artifacts") or {}).get("count"), 1)
        self.assertEqual(payload.get("patch_current_revision"), 4)
        self.assertEqual((payload.get("patch_action_readiness") or {}).get("default_preview"), "preview.txt")
        self.assertEqual(payload.get("memory_health_status"), "watch")
        self.assertEqual(payload.get("memory_health_issue_count"), 1)
        self.assertEqual(payload.get("memory_db_total"), 756)
        self.assertEqual(payload.get("memory_scoped_total"), 0)
        self.assertEqual(payload.get("memory_events_log_status"), "watch")
        self.assertEqual(payload.get("memory_events_log_bytes"), 99)
        self.assertEqual(payload.get("memory_events_log_invalid_tail_count"), 1)
        self.assertEqual((payload.get("memory_health_issues") or [{}])[0].get("code"), "learned_facts_orphan_tmp")
        self.assertEqual(payload.get("patch_previews_total"), 12)
        self.assertEqual(payload.get("patch_previews_orphaned"), 2)
        self.assertEqual(payload.get("patch_review_previews_total"), 5)
        self.assertEqual(payload.get("patch_review_previews_pending_distinct"), 3)
        self.assertEqual(payload.get("patch_review_previews_superseded_total"), 5)
        self.assertEqual(payload.get("patch_cleanup_status"), "ok")
        self.assertEqual(payload.get("patch_cleanup_orphan_rejected_count"), 8)
        self.assertEqual(payload.get("patch_cleanup_superseded_archived_count"), 12)
        self.assertEqual(payload.get("patch_cleanup_review_total_before"), 14)
        self.assertEqual(payload.get("patch_cleanup_review_total_after"), 5)
        self.assertEqual(payload.get("complete_tree_archive_status"), "ok")
        self.assertEqual(payload.get("complete_tree_archived_count"), 12)
        self.assertEqual(payload.get("complete_tree_retained_count"), 8)
        self.assertEqual(payload.get("requests_total"), 7)
        self.assertEqual(payload.get("last_provider_hit"), "wikipedia")
        self.assertTrue(payload.get("last_provider_available"))
        self.assertEqual(payload.get("last_provider_note"), "provider_hit_recorded")
        self.assertEqual(payload.get("runtime_worker_status"), "ok")
        self.assertFalse(payload.get("runtime_worker_active"))
        self.assertFalse(payload.get("runtime_worker_stale_identity"))
        self.assertEqual(payload.get("last_generated_queue_run_file"), "demo.json")
        self.assertFalse(payload.get("last_generated_queue_run_stale"))
        self.assertEqual(payload.get("autonomy_orchestrator_decision"), "recommend_action")
        self.assertEqual(payload.get("autonomy_orchestrator_action"), "generated_queue_run_next")
        self.assertEqual(payload.get("autonomy_orchestrator_action_type"), "generated_queue_run_next")
        self.assertTrue(payload.get("autonomy_orchestrator_recommendation_stale"))
        self.assertEqual(payload.get("autonomy_orchestrator_display_decision"), "settled")
        self.assertEqual(payload.get("autonomy_orchestrator_display_action"), "none")
        self.assertIn("Generated Work Queue is clear", payload.get("autonomy_orchestrator_current_note"))
        self.assertEqual(payload.get("autonomy_orchestrator_ledger_status"), "recorded")
        self.assertEqual((payload.get("autonomy_orchestrator") or {}).get("mode"), "advisory")
        self.assertEqual(payload.get("autonomy_orchestrator_count"), 4)
        self.assertEqual(payload.get("autonomy_orchestrator_recommendation_changes"), 1)
        self.assertEqual(payload.get("autonomy_orchestrator_change_rate"), 0.3333)
        self.assertFalse(payload.get("autonomy_orchestrator_stable"))
        self.assertEqual(payload.get("autonomy_orchestrator_weak_refusal_rate"), 1.0)

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
            generated_work_queue={
                "status": "blocked",
                "open_count": 2,
                "actionable_count": 0,
                "blocked_count": 2,
                "blocked_reason_counts": {"parity_drift_locked": 2},
                "blocked_files": ["next_generated.json", "next_generated_2.json"],
                "count": 3,
                "next_item": {"file": "next_generated.json"},
            },
            autonomy_maintenance={
                "runtime_worker": {"last_cycle_status": "running", "interval_sec": 60, "cycle_count": 9},
                "last_regression_status": "FAILED",
                "last_regression_stale": True,
                "last_generated_queue_run": {"status": "failed", "selected_file": "next_generated.json", "latest_report_status": "warning", "ts": "2026-04-04 03:00:00"},
                "last_work_tree_cycle": {"status": "ok"},
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
        )

        self.assertTrue(payload.get("subconscious_ok"))
        self.assertEqual(payload.get("subconscious_label"), "hourly")
        self.assertEqual(payload.get("subconscious_family_count"), 7)
        self.assertEqual(payload.get("generated_work_queue_open_count"), 2)
        self.assertEqual(payload.get("generated_work_queue_next_file"), "next_generated.json")
        self.assertEqual(payload.get("generated_queue_status"), "blocked")
        self.assertEqual(payload.get("last_regression_status"), "FAILED")
        self.assertTrue(payload.get("last_regression_stale"))
        self.assertEqual(payload.get("queue_open_count"), 2)
        self.assertEqual(payload.get("queue_actionable_count"), 0)
        self.assertEqual(payload.get("queue_blocked_count"), 2)
        self.assertEqual(payload.get("queue_blocked_reason_counts"), {"parity_drift_locked": 2})
        self.assertEqual(payload.get("queue_blocked_files"), ["next_generated.json", "next_generated_2.json"])
        self.assertTrue(payload.get("last_generated_queue_run_stale"))
        self.assertEqual(payload.get("work_tree_status"), "ok")
        self.assertEqual(payload.get("backend_command_count"), 1)
        self.assertEqual((payload.get("subconscious_top_priorities") or [])[0].get("seam_label"), "session fact recall route fallthrough")
        self.assertEqual((payload.get("provider_telemetry") or {}).get("last_provider_used"), "general_web")
        self.assertEqual(payload.get("runtime_worker_status"), "running")
        self.assertEqual(payload.get("last_generated_queue_run_status"), "failed")
        self.assertEqual(payload.get("last_generated_queue_report_status"), "warning")
        self.assertEqual((payload.get("autonomy_maintenance") or {}).get("generated_queue_status"), "blocked")
        self.assertEqual((payload.get("autonomy_maintenance") or {}).get("queue_open_count"), 2)
        self.assertEqual((payload.get("autonomy_maintenance") or {}).get("queue_actionable_count"), 0)
        self.assertEqual((payload.get("autonomy_maintenance") or {}).get("queue_blocked_count"), 2)
        self.assertTrue((payload.get("autonomy_maintenance") or {}).get("last_generated_queue_run_stale"))

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
        self.assertFalse(payload.get("last_provider_available"))
        self.assertEqual(payload.get("last_provider_note"), "no_provider_hit_recorded")

    def test_status_payload_treats_nullish_provider_values_as_no_provider_hit(self):
        payload = CONTROL_STATUS_SERVICE.status_payload(
            policy={"memory": {"scope": "private"}},
            provider="searxng",
            endpoint="http://127.0.0.1:8081/search",
            searx_ok=True,
            searx_note="status=200",
            search_provider_priority=["wikipedia", "stackexchange", "general_web"],
            provider_telemetry={"last_provider_used": "null", "last_provider_family": "undefined"},
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
            web_enabled=False,
            allow_domains_count=0,
            process_counting_mode="logical_leaf_processes",
            runtime_process_note="note",
            heartbeat_age_sec=1,
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
            ledger_summary={"ok": True, "count": 1, "last_record": {"provider_used": None, "provider_family": "none"}},
            patch_summary={"ok": True},
            patch_action_readiness={},
            pulse_payload={},
            update_now_pending={},
            requests_total=0,
            errors_total=0,
        )

        self.assertEqual(payload.get("last_provider_hit"), "")
        self.assertEqual(payload.get("last_provider_family"), "")
        self.assertFalse(payload.get("last_provider_available"))
        self.assertEqual(payload.get("last_provider_note"), "no_provider_hit_recorded")

    def test_status_payload_marks_guard_scheduled_maintenance_when_worker_is_not_persistent(self):
        payload = CONTROL_STATUS_SERVICE.status_payload(
            policy={"memory": {"scope": "private"}},
            provider="searxng",
            endpoint="http://127.0.0.1:8081/search",
            searx_ok=True,
            searx_note="status=200",
            search_provider_priority=["wikipedia", "stackexchange", "general_web"],
            provider_telemetry={},
            ollama_api_up=False,
            chat_model="test-model",
            memory_enabled=False,
            subconscious_summary={"ok": True},
            subconscious_live_summary={},
            generated_work_queue={"open_count": 0, "next_item": {}},
            autonomy_maintenance={
                "runtime_worker": {
                    "last_cycle_status": "ok",
                    "active": False,
                    "interval_sec": 300,
                    "cycle_count": 12,
                    "last_completed_at": "2026-04-23 22:18:09",
                }
            },
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
            guard_status={"running": True, "status": "running"},
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
        )

        self.assertTrue(payload.get("maintenance_scheduler_active"))
        self.assertEqual(payload.get("maintenance_scheduler_mode"), "guard_tick")
        self.assertEqual(payload.get("maintenance_scheduler_status"), "guard_scheduled")
        self.assertEqual((payload.get("autonomy_maintenance") or {}).get("maintenance_scheduler_mode"), "guard_tick")

    def test_status_payload_includes_storage_watch_fields_when_provided(self):
        payload = CONTROL_STATUS_SERVICE.status_payload(
            policy={"memory": {"scope": "private"}},
            provider="html",
            endpoint="",
            searx_ok=None,
            searx_note="n/a",
            search_provider_priority=[],
            provider_telemetry={},
            ollama_api_up=False,
            chat_model="test-model",
            memory_enabled=False,
            subconscious_summary={"ok": True},
            subconscious_live_summary={},
            generated_work_queue={},
            autonomy_maintenance={},
            operator_macros=[],
            backend_commands=[],
            memory_scope="private",
            web_enabled=False,
            allow_domains_count=0,
            process_counting_mode="logical_leaf_processes",
            runtime_process_note="",
            heartbeat_age_sec=0,
            active_http_sessions=0,
            chat_login_enabled=False,
            chat_auth_source="disabled",
            chat_users_count=0,
            guard_status={"running": True},
            core_status={"running": True},
            webui_status={"running": True},
            runtime_summary={},
            timeline_payload={},
            runtime_artifacts={},
            runtime_restart_analytics={},
            runtime_failures={},
            live_tracking={},
            action_readiness={},
            release_status={},
            memory_stats={},
            memory_summary={},
            tool_summary={},
            ledger_summary={},
            patch_summary={},
            patch_action_readiness={},
            pulse_payload={},
            update_now_pending={},
            requests_total=0,
            errors_total=0,
            storage_watch_summary={
                "status": "warn",
                "note": "25 kidney cleanup snapshots retained",
                "total_bytes": 12345,
                "patch_snapshot_count": 2,
                "kidney_snapshot_count": 25,
            },
        )

        self.assertEqual(payload.get("storage_watch_status"), "warn")
        self.assertEqual(payload.get("storage_watch_note"), "25 kidney cleanup snapshots retained")
        self.assertEqual(payload.get("storage_watch_total_bytes"), 12345)
        self.assertEqual(payload.get("patch_snapshot_count"), 2)
        self.assertEqual(payload.get("kidney_snapshot_count"), 25)


if __name__ == "__main__":
    unittest.main()
