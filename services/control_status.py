from __future__ import annotations

import os
import time


class ControlStatusService:
    """Own HTTP control-status payload assembly outside the transport layer."""

    @staticmethod
    def _clean_provider_value(value) -> str:
        text = str(value or "").strip().lower()
        if text in {"none", "null", "undefined", "n/a", "na"}:
            return ""
        return text

    @staticmethod
    def runtime_supplier_fns_from_scope(runtime_scope: dict[str, object]) -> dict[str, object]:
        names = (
            "probe_searxng",
            "guard_status_payload",
            "core_status_payload",
            "http_status_payload",
            "runtime_timeline_payload",
            "subconscious_status_summary",
            "subconscious_live_summary",
            "generated_work_queue",
            "autonomy_maintenance_summary",
            "load_operator_macros",
            "load_backend_commands",
            "memory_events_summary",
            "tool_events_summary",
            "action_ledger_summary",
            "provider_telemetry_payload",
            "runtime_summary_payload",
            "runtime_artifacts_payload",
            "runtime_restart_analytics_payload",
            "runtime_failure_reasons_payload",
            "action_readiness_payload",
            "release_status_payload",
            "patch_action_readiness_payload",
            "storage_watch_summary",
            "runtime_process_note",
            "heartbeat_age_seconds",
            "chat_login_enabled",
            "chat_auth_source",
            "chat_users",
            "append_metrics_snapshot",
            "build_self_check",
            "control_policy_payload",
            "metrics_payload",
        )
        return {
            name: runtime_scope[f"_{name}"]
            for name in names
        }

    def runtime_status_payload(
        self,
        *,
        core_module,
        session_turns,
        metrics_totals: tuple[int, int],
        supplier_fns: dict[str, object] | None = None,
    ) -> dict:
        supplier_fns = dict(supplier_fns or {})
        probe_searxng_fn = supplier_fns["probe_searxng"]
        guard_status_payload_fn = supplier_fns["guard_status_payload"]
        core_status_payload_fn = supplier_fns["core_status_payload"]
        http_status_payload_fn = supplier_fns["http_status_payload"]
        runtime_timeline_payload_fn = supplier_fns["runtime_timeline_payload"]
        subconscious_status_summary_fn = supplier_fns["subconscious_status_summary"]
        subconscious_live_summary_fn = supplier_fns["subconscious_live_summary"]
        generated_work_queue_fn = supplier_fns["generated_work_queue"]
        autonomy_maintenance_summary_fn = supplier_fns["autonomy_maintenance_summary"]
        load_operator_macros_fn = supplier_fns["load_operator_macros"]
        load_backend_commands_fn = supplier_fns["load_backend_commands"]
        memory_events_summary_fn = supplier_fns["memory_events_summary"]
        tool_events_summary_fn = supplier_fns["tool_events_summary"]
        action_ledger_summary_fn = supplier_fns["action_ledger_summary"]
        provider_telemetry_payload_fn = supplier_fns["provider_telemetry_payload"]
        runtime_summary_payload_fn = supplier_fns["runtime_summary_payload"]
        runtime_artifacts_payload_fn = supplier_fns["runtime_artifacts_payload"]
        runtime_restart_analytics_payload_fn = supplier_fns["runtime_restart_analytics_payload"]
        runtime_failure_reasons_payload_fn = supplier_fns["runtime_failure_reasons_payload"]
        action_readiness_payload_fn = supplier_fns["action_readiness_payload"]
        release_status_payload_fn = supplier_fns["release_status_payload"]
        patch_action_readiness_payload_fn = supplier_fns["patch_action_readiness_payload"]
        storage_watch_summary_fn = supplier_fns["storage_watch_summary"]
        runtime_process_note_fn = supplier_fns["runtime_process_note"]
        heartbeat_age_seconds_fn = supplier_fns["heartbeat_age_seconds"]
        chat_login_enabled_fn = supplier_fns["chat_login_enabled"]
        chat_auth_source_fn = supplier_fns["chat_auth_source"]
        chat_users_fn = supplier_fns["chat_users"]
        append_metrics_snapshot_fn = supplier_fns["append_metrics_snapshot"]
        build_self_check_fn = supplier_fns["build_self_check"]
        control_policy_payload_fn = supplier_fns["control_policy_payload"]
        metrics_payload_fn = supplier_fns["metrics_payload"]

        policy = core_module.load_policy()
        web_cfg = policy.get("web") or {}
        provider = str(web_cfg.get("search_provider") or "html").strip().lower()
        endpoint = str(web_cfg.get("search_api_endpoint") or "").strip()

        searx_ok = None
        searx_note = "n/a"
        if provider == "searxng":
            if endpoint:
                searx_ok, searx_note = probe_searxng_fn(endpoint)
            else:
                searx_ok, searx_note = None, "endpoint_missing"

        guard_status = guard_status_payload_fn()
        core_status = core_status_payload_fn()
        webui_status = http_status_payload_fn()
        timeline_payload = runtime_timeline_payload_fn()
        subconscious_summary = subconscious_status_summary_fn()
        subconscious_live_summary = subconscious_live_summary_fn()
        generated_work_queue = generated_work_queue_fn(24)
        autonomy_maintenance = autonomy_maintenance_summary_fn()
        operator_macros = load_operator_macros_fn(24)
        backend_commands = load_backend_commands_fn(40)
        memory_stats = core_module.mem_stats_payload(emit_event=False)
        memory_summary = memory_events_summary_fn(80)
        tool_summary = tool_events_summary_fn(80)
        ledger_summary = action_ledger_summary_fn(80)
        patch_summary = core_module.patch_status_payload()
        pulse_payload = core_module.build_pulse_payload()
        update_now_pending = core_module.update_now_pending_payload()
        requests_total, errors_total = metrics_totals

        payload = self.status_payload(
            policy=policy,
            provider=provider,
            endpoint=endpoint,
            searx_ok=searx_ok,
            searx_note=searx_note,
            search_provider_priority=list(core_module.get_search_provider_priority()),
            provider_telemetry=provider_telemetry_payload_fn(ledger_summary=ledger_summary, tool_summary=tool_summary),
            ollama_api_up=bool(core_module.ollama_api_up()),
            chat_model=core_module.chat_model(),
            memory_enabled=bool(core_module.mem_enabled()),
            subconscious_summary=subconscious_summary,
            subconscious_live_summary=subconscious_live_summary,
            generated_work_queue=generated_work_queue,
            autonomy_maintenance=autonomy_maintenance,
            operator_macros=operator_macros,
            backend_commands=backend_commands,
            memory_scope=str((policy.get("memory") or {}).get("scope") or "private"),
            web_enabled=bool((policy.get("tools_enabled") or {}).get("web")) and bool(web_cfg.get("enabled")),
            allow_domains_count=len(web_cfg.get("allow_domains") or []),
            process_counting_mode="logical_leaf_processes" if os.name == "nt" else "direct_process_state",
            runtime_process_note=runtime_process_note_fn(),
            heartbeat_age_sec=heartbeat_age_seconds_fn(),
            active_http_sessions=len(session_turns),
            chat_login_enabled=bool(chat_login_enabled_fn()),
            chat_auth_source=chat_auth_source_fn(),
            chat_users_count=len(chat_users_fn()),
            guard_status=guard_status,
            core_status=core_status,
            webui_status=webui_status,
            runtime_summary=runtime_summary_payload_fn(guard=guard_status, core=core_status, webui=webui_status),
            timeline_payload=timeline_payload,
            runtime_artifacts=runtime_artifacts_payload_fn(),
            runtime_restart_analytics=runtime_restart_analytics_payload_fn(),
            runtime_failures=runtime_failure_reasons_payload_fn(guard_status, core_status, webui_status, timeline_payload),
            live_tracking=core_module.runtime_device_location_payload(),
            action_readiness=action_readiness_payload_fn(guard_status, core_status, webui_status),
            release_status=release_status_payload_fn(),
            memory_stats=memory_stats,
            memory_summary=memory_summary,
            tool_summary=tool_summary,
            ledger_summary=ledger_summary,
            patch_summary=patch_summary,
            patch_action_readiness=patch_action_readiness_payload_fn(patch_summary),
            pulse_payload=pulse_payload,
            update_now_pending=update_now_pending,
            requests_total=requests_total,
            errors_total=errors_total,
            storage_watch_summary=storage_watch_summary_fn(),
        )
        append_metrics_snapshot_fn(payload)
        self_check = build_self_check_fn(payload, control_policy_payload_fn(), metrics_payload_fn())
        payload["health_score"] = int(self_check.get("health_score", 0))
        payload["self_check_pass_ratio"] = float(self_check.get("pass_ratio", 0.0))
        payload["alerts"] = list(self_check.get("alerts") or [])
        return payload

    @staticmethod
    def status_payload(
        *,
        policy: dict,
        provider: str,
        endpoint: str,
        searx_ok,
        searx_note: str,
        search_provider_priority: list,
        provider_telemetry: dict,
        ollama_api_up: bool,
        chat_model: str,
        memory_enabled: bool,
        subconscious_summary: dict,
        subconscious_live_summary: dict,
        generated_work_queue: dict,
        autonomy_maintenance: dict,
        operator_macros: list,
        backend_commands: list,
        memory_scope: str,
        web_enabled: bool,
        allow_domains_count: int,
        process_counting_mode: str,
        runtime_process_note: str,
        heartbeat_age_sec,
        active_http_sessions: int,
        chat_login_enabled: bool,
        chat_auth_source: str,
        chat_users_count: int,
        guard_status: dict,
        core_status: dict,
        webui_status: dict,
        runtime_summary: dict,
        timeline_payload: dict,
        runtime_artifacts: dict,
        runtime_restart_analytics: dict,
        runtime_failures: dict,
        live_tracking: dict,
        action_readiness: dict,
        release_status: dict,
        memory_stats: dict,
        memory_summary: dict,
        tool_summary: dict,
        ledger_summary: dict,
        patch_summary: dict,
        patch_action_readiness: dict,
        pulse_payload: dict,
        update_now_pending: dict,
        requests_total: int,
        errors_total: int,
        storage_watch_summary: dict | None = None,
    ) -> dict:
        autonomy_payload = autonomy_maintenance.copy() if isinstance(autonomy_maintenance, dict) else {}
        payload = {
            "ok": True,
            "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ollama_api_up": bool(ollama_api_up),
            "chat_model": chat_model,
            "memory_enabled": bool(memory_enabled),
            "subconscious_ok": bool(subconscious_summary.get("ok")),
            "subconscious_generated_at": str(subconscious_summary.get("generated_at") or ""),
            "subconscious_label": str(subconscious_summary.get("label") or ""),
            "subconscious_family_count": int(subconscious_summary.get("family_count", 0) or 0),
            "subconscious_variation_count": int(subconscious_summary.get("variation_count", 0) or 0),
            "subconscious_training_priority_count": int(subconscious_summary.get("training_priority_count", 0) or 0),
            "subconscious_generated_definition_count": int(subconscious_summary.get("generated_definition_count", 0) or 0),
            "subconscious_top_priorities": list(subconscious_summary.get("top_priorities") or []),
            "subconscious_latest_report_path": str(subconscious_summary.get("latest_report_path") or ""),
            "subconscious_live_summary": subconscious_live_summary,
            "generated_work_queue_open_count": int(generated_work_queue.get("open_count", 0) or 0),
            "generated_work_queue_next_file": str((generated_work_queue.get("next_item") or {}).get("file") or ""),
            "autonomy_maintenance": autonomy_payload,
            "operator_macros": operator_macros,
            "backend_commands": backend_commands,
            "backend_command_count": len(backend_commands),
            "memory_scope": memory_scope,
            "web_enabled": bool(web_enabled),
            "search_provider": provider,
            "search_api_endpoint": endpoint,
            "search_provider_priority": list(search_provider_priority or []),
            "provider_telemetry": provider_telemetry if isinstance(provider_telemetry, dict) else {},
            "allow_domains_count": allow_domains_count,
            "process_counting_mode": process_counting_mode,
            "runtime_process_note": runtime_process_note,
            "heartbeat_age_sec": heartbeat_age_sec,
            "active_http_sessions": int(active_http_sessions),
            "chat_login_enabled": bool(chat_login_enabled),
            "chat_auth_source": chat_auth_source,
            "chat_users_count": int(chat_users_count),
            "searxng_ok": searx_ok,
            "searxng_note": searx_note,
            "guard": guard_status,
            "core": core_status,
            "webui": webui_status,
            "runtime_summary": runtime_summary,
            "runtime_timeline": timeline_payload,
            "runtime_artifacts": runtime_artifacts,
            "runtime_restart_analytics": runtime_restart_analytics,
            "runtime_failures": runtime_failures,
            "live_tracking": live_tracking,
            "action_readiness": action_readiness,
            "release_status": release_status,
            "subconscious_summary": subconscious_summary,
            "generated_work_queue": generated_work_queue,
        }

        runtime_worker = autonomy_payload.get("runtime_worker") if isinstance(autonomy_payload.get("runtime_worker"), dict) else {}
        last_generated_queue_run = autonomy_payload.get("last_generated_queue_run") if isinstance(autonomy_payload.get("last_generated_queue_run"), dict) else {}
        last_work_tree_cycle = autonomy_payload.get("last_work_tree_cycle") if isinstance(autonomy_payload.get("last_work_tree_cycle"), dict) else {}
        last_patch_cleanup = autonomy_payload.get("last_patch_cleanup") if isinstance(autonomy_payload.get("last_patch_cleanup"), dict) else {}
        last_complete_tree_archive = autonomy_payload.get("last_complete_tree_archive") if isinstance(autonomy_payload.get("last_complete_tree_archive"), dict) else {}
        last_autonomy_orchestrator = autonomy_payload.get("last_autonomy_orchestrator") if isinstance(autonomy_payload.get("last_autonomy_orchestrator"), dict) else {}
        queue_status = str(generated_work_queue.get("status") or last_generated_queue_run.get("status") or "").strip()
        queue_open_count = int(generated_work_queue.get("open_count", 0) or 0)
        queue_actionable_count = int(generated_work_queue.get("actionable_count", 0) or 0)
        queue_blocked_count = int(generated_work_queue.get("blocked_count", 0) or 0)
        queue_blocked_reason_counts = dict(generated_work_queue.get("blocked_reason_counts") or {}) if isinstance(generated_work_queue.get("blocked_reason_counts"), dict) else {}
        queue_blocked_files = list(generated_work_queue.get("blocked_files") or []) if isinstance(generated_work_queue.get("blocked_files"), list) else []
        if queue_open_count > 0 and queue_blocked_count <= 0 and queue_actionable_count <= 0:
            queue_blocked_count = queue_open_count
        last_generated_queue_run_stale = any(
            (
                str(last_generated_queue_run.get("status") or "").strip() != queue_status,
                int(last_generated_queue_run.get("queue_open_count", 0) or 0) != queue_open_count,
                int(last_generated_queue_run.get("queue_actionable_count", 0) or 0) != queue_actionable_count,
                int(last_generated_queue_run.get("queue_blocked_count", 0) or 0) != queue_blocked_count,
                dict(last_generated_queue_run.get("queue_blocked_reason_counts") or {}) != queue_blocked_reason_counts,
                list(last_generated_queue_run.get("queue_blocked_files") or []) != queue_blocked_files,
            )
        )
        autonomy_payload["runtime_worker"] = runtime_worker
        autonomy_payload["generated_queue_status"] = queue_status
        autonomy_payload["queue_open_count"] = queue_open_count
        autonomy_payload["queue_actionable_count"] = queue_actionable_count
        autonomy_payload["queue_blocked_count"] = queue_blocked_count
        autonomy_payload["queue_blocked_reason_counts"] = queue_blocked_reason_counts
        autonomy_payload["queue_blocked_files"] = queue_blocked_files
        autonomy_payload["last_generated_queue_run_stale"] = last_generated_queue_run_stale
        payload["runtime_worker_status"] = str(runtime_worker.get("last_cycle_status") or "")
        payload["runtime_worker_active"] = bool(runtime_worker.get("active", False))
        payload["runtime_worker_stale_identity"] = bool(runtime_worker.get("stale_identity", False))
        payload["runtime_worker_interval_sec"] = int(runtime_worker.get("interval_sec", 0) or 0)
        payload["runtime_worker_cycle_count"] = int(runtime_worker.get("cycle_count", 0) or 0)
        payload["runtime_worker_last_completed_at"] = str(runtime_worker.get("last_completed_at") or "")
        guard_running = bool((guard_status or {}).get("running"))
        if payload["runtime_worker_active"]:
            maintenance_scheduler_mode = "worker_loop"
            maintenance_scheduler_status = "running"
        elif guard_running:
            maintenance_scheduler_mode = "guard_tick"
            maintenance_scheduler_status = "guard_scheduled"
        else:
            maintenance_scheduler_mode = "inactive"
            maintenance_scheduler_status = "inactive"
        payload["maintenance_scheduler_active"] = bool(payload["runtime_worker_active"] or guard_running)
        payload["maintenance_scheduler_mode"] = maintenance_scheduler_mode
        payload["maintenance_scheduler_status"] = maintenance_scheduler_status
        autonomy_payload["maintenance_scheduler_active"] = payload["maintenance_scheduler_active"]
        autonomy_payload["maintenance_scheduler_mode"] = maintenance_scheduler_mode
        autonomy_payload["maintenance_scheduler_status"] = maintenance_scheduler_status
        autonomy_payload["last_autonomy_orchestrator"] = last_autonomy_orchestrator
        autonomy_orchestrator_action = last_autonomy_orchestrator.get("action") if isinstance(last_autonomy_orchestrator.get("action"), dict) else {}
        autonomy_orchestrator_recommended_action = (
            last_autonomy_orchestrator.get("recommended_action")
            if isinstance(last_autonomy_orchestrator.get("recommended_action"), dict)
            else {}
        )
        autonomy_orchestrator_summary = (
            autonomy_payload.get("autonomy_orchestrator_summary")
            if isinstance(autonomy_payload.get("autonomy_orchestrator_summary"), dict)
            else {}
        )
        payload["autonomy_orchestrator"] = last_autonomy_orchestrator
        payload["autonomy_orchestrator_summary"] = autonomy_orchestrator_summary
        payload["autonomy_orchestrator_ts"] = str(last_autonomy_orchestrator.get("ts") or "")
        payload["autonomy_orchestrator_mode"] = str(last_autonomy_orchestrator.get("mode") or "")
        payload["autonomy_orchestrator_decision"] = str(last_autonomy_orchestrator.get("decision") or "")
        payload["autonomy_orchestrator_decision_type"] = str(last_autonomy_orchestrator.get("decision_type") or "")
        payload["autonomy_orchestrator_confidence"] = float(last_autonomy_orchestrator.get("confidence", 0.0) or 0.0)
        payload["autonomy_orchestrator_recommended_action"] = autonomy_orchestrator_recommended_action
        autonomy_orchestrator_action_text = str(
            autonomy_orchestrator_action.get("act")
            or autonomy_orchestrator_recommended_action.get("action_type")
            or ""
        )
        payload["autonomy_orchestrator_action"] = autonomy_orchestrator_action_text
        payload["autonomy_orchestrator_action_type"] = autonomy_orchestrator_action_text
        payload["autonomy_orchestrator_reason"] = str(last_autonomy_orchestrator.get("reason") or "")
        payload["autonomy_orchestrator_ledger_status"] = str(last_autonomy_orchestrator.get("ledger_status") or "")
        payload["autonomy_orchestrator_rejection_reasons"] = (
            list(last_autonomy_orchestrator.get("rejection_reasons") or [])
            if isinstance(last_autonomy_orchestrator.get("rejection_reasons"), list)
            else []
        )
        stale_recommendation_reasons: list[str] = []
        recommends_action = payload["autonomy_orchestrator_decision"] == "recommend_action" or payload["autonomy_orchestrator_decision_type"] == "RecommendAction"
        if recommends_action:
            if autonomy_orchestrator_action_text == "generated_queue_run_next" and queue_actionable_count <= 0:
                stale_recommendation_reasons.append("generated_queue_no_actionable_items")
            elif autonomy_orchestrator_action_text == "generated_queue_investigate" and queue_blocked_count <= 0:
                stale_recommendation_reasons.append("generated_queue_no_blocked_items")
        stale_recommendation = bool(stale_recommendation_reasons)
        payload["autonomy_orchestrator_recommendation_stale"] = stale_recommendation
        payload["autonomy_orchestrator_stale_reasons"] = stale_recommendation_reasons
        payload["autonomy_orchestrator_display_decision"] = "settled" if stale_recommendation else (payload["autonomy_orchestrator_decision_type"] or payload["autonomy_orchestrator_decision"] or "")
        payload["autonomy_orchestrator_display_action"] = "none" if stale_recommendation else (autonomy_orchestrator_action_text or "none")
        payload["autonomy_orchestrator_current_note"] = (
            "Generated Work Queue is clear; the last queue recommendation has already settled."
            if stale_recommendation and "generated_queue_no_actionable_items" in stale_recommendation_reasons
            else ""
        )
        autonomy_payload["autonomy_orchestrator_recommendation_stale"] = stale_recommendation
        autonomy_payload["autonomy_orchestrator_display_decision"] = payload["autonomy_orchestrator_display_decision"]
        autonomy_payload["autonomy_orchestrator_display_action"] = payload["autonomy_orchestrator_display_action"]
        autonomy_payload["autonomy_orchestrator_current_note"] = payload["autonomy_orchestrator_current_note"]
        payload["autonomy_orchestrator_count"] = int(autonomy_orchestrator_summary.get("count", 0) or 0)
        payload["autonomy_orchestrator_recommendation_changes"] = int(autonomy_orchestrator_summary.get("recommendation_changes", 0) or 0)
        payload["autonomy_orchestrator_change_rate"] = float(autonomy_orchestrator_summary.get("recommendation_change_rate", 0.0) or 0.0)
        payload["autonomy_orchestrator_stable"] = bool(autonomy_orchestrator_summary.get("stable_recommendation", True))
        payload["autonomy_orchestrator_weak_refusal_rate"] = float(autonomy_orchestrator_summary.get("weak_posture_refusal_rate", 0.0) or 0.0)
        payload["last_regression_status"] = str(autonomy_maintenance.get("last_regression_status") or "")
        payload["last_regression_stale"] = bool(autonomy_maintenance.get("last_regression_stale", False))
        payload["last_generated_queue_run_status"] = str(last_generated_queue_run.get("status") or "")
        payload["last_generated_queue_run_file"] = str(last_generated_queue_run.get("selected_file") or "")
        payload["last_generated_queue_run_at"] = str(last_generated_queue_run.get("ts") or "")
        payload["last_generated_queue_report_status"] = str(last_generated_queue_run.get("latest_report_status") or "")
        payload["last_generated_queue_run_stale"] = last_generated_queue_run_stale
        payload["generated_queue_status"] = queue_status
        payload["queue_open_count"] = queue_open_count
        payload["queue_actionable_count"] = queue_actionable_count
        payload["queue_blocked_count"] = queue_blocked_count
        payload["queue_blocked_reason_counts"] = queue_blocked_reason_counts
        payload["queue_blocked_files"] = queue_blocked_files
        payload["work_tree_status"] = str(last_work_tree_cycle.get("status") or "")
        payload["patch_cleanup_status"] = str(last_patch_cleanup.get("status") or "")
        payload["patch_cleanup_at"] = str(last_patch_cleanup.get("ts") or "")
        payload["patch_cleanup_orphan_rejected_count"] = int(last_patch_cleanup.get("orphan_rejected_count", 0) or 0)
        payload["patch_cleanup_superseded_archived_count"] = int(last_patch_cleanup.get("superseded_archived_count", 0) or 0)
        payload["patch_cleanup_review_total_before"] = int(last_patch_cleanup.get("review_total_before", 0) or 0)
        payload["patch_cleanup_review_total_after"] = int(last_patch_cleanup.get("review_total_after", 0) or 0)
        payload["patch_cleanup_orphaned_before"] = int(last_patch_cleanup.get("orphaned_before", 0) or 0)
        payload["patch_cleanup_orphaned_after"] = int(last_patch_cleanup.get("orphaned_after", 0) or 0)
        payload["patch_cleanup_superseded_before"] = int(last_patch_cleanup.get("superseded_before", 0) or 0)
        payload["patch_cleanup_superseded_after"] = int(last_patch_cleanup.get("superseded_after", 0) or 0)
        payload["patch_cleanup_archive_dir"] = str(last_patch_cleanup.get("archive_dir") or "")
        payload["complete_tree_archive_status"] = str(last_complete_tree_archive.get("status") or "")
        payload["complete_tree_archive_at"] = str(last_complete_tree_archive.get("ts") or "")
        payload["complete_tree_archived_count"] = int(last_complete_tree_archive.get("archived_count", 0) or 0)
        payload["complete_tree_retained_count"] = int(last_complete_tree_archive.get("retained_count", 0) or 0)
        storage_watch = storage_watch_summary if isinstance(storage_watch_summary, dict) else {}
        payload["storage_watch_status"] = str(storage_watch.get("status") or "")
        payload["storage_watch_note"] = str(storage_watch.get("note") or "")
        payload["storage_watch_total_bytes"] = int(storage_watch.get("total_bytes", 0) or 0)
        payload["patch_snapshot_count"] = int(storage_watch.get("patch_snapshot_count", 0) or 0)
        payload["kidney_snapshot_count"] = int(storage_watch.get("kidney_snapshot_count", 0) or 0)

        payload["memory_stats_ok"] = bool(memory_stats.get("ok", False))
        payload["memory_entries_total"] = int(memory_stats.get("total", 0) or 0)
        payload["memory_by_user_count"] = len(memory_stats.get("by_user") or {}) if isinstance(memory_stats.get("by_user"), dict) else 0
        pulse_memory_health = pulse_payload.get("memory_health") if isinstance(pulse_payload.get("memory_health"), dict) else {}
        if isinstance(pulse_payload.get("memory_health_issues"), list):
            pulse_memory_issues = list(pulse_payload.get("memory_health_issues") or [])
        elif isinstance(pulse_memory_health.get("issues"), list):
            pulse_memory_issues = list(pulse_memory_health.get("issues") or [])
        else:
            pulse_memory_issues = []
        memory_health_status = str(pulse_payload.get("memory_health_status") or pulse_memory_health.get("status") or "unknown").strip().lower()
        payload["memory_scoped_total"] = int(pulse_payload.get("memory_scoped_total", payload["memory_entries_total"]) or 0)
        payload["memory_db_total"] = int(pulse_payload.get("memory_db_total", payload["memory_entries_total"]) or 0)
        payload["memory_health"] = pulse_memory_health
        payload["memory_health_ok"] = bool(pulse_payload.get("memory_ok", payload["memory_stats_ok"])) and memory_health_status in {"ok", "unknown"}
        payload["memory_health_status"] = memory_health_status
        payload["memory_health_issue_count"] = int(pulse_payload.get("memory_health_issue_count", pulse_memory_health.get("issue_count", 0)) or 0)
        payload["memory_health_issues"] = pulse_memory_issues[:6]
        memory_events_log = pulse_memory_health.get("memory_events_log") if isinstance(pulse_memory_health.get("memory_events_log"), dict) else {}
        payload["memory_events_log_status"] = str(
            pulse_payload.get("memory_events_log_status") or memory_events_log.get("status") or "unknown"
        )
        payload["memory_events_log_invalid_tail_count"] = int(
            pulse_payload.get("memory_events_log_invalid_tail_count", memory_events_log.get("invalid_tail_count", 0)) or 0
        )
        payload["memory_events_log_bytes"] = int(
            pulse_payload.get("memory_events_log_bytes", memory_events_log.get("byte_count", 0)) or 0
        )
        payload["memory_events_ok"] = bool(memory_summary.get("ok", False))
        payload["memory_events_total"] = int(memory_summary.get("count", 0))
        payload["memory_write_count"] = int(memory_summary.get("write_count", 0))
        payload["memory_recall_count"] = int(memory_summary.get("recall_count", 0))
        payload["memory_skipped_count"] = int(memory_summary.get("skipped_count", 0))
        payload["memory_events_avg_latency_ms"] = int(memory_summary.get("avg_latency_ms", 0))
        last_memory = memory_summary.get("last_event") if isinstance(memory_summary.get("last_event"), dict) else {}
        payload["last_memory_action"] = str(last_memory.get("action") or "")
        payload["last_memory_status"] = str(last_memory.get("status") or "")

        payload["tool_events_ok"] = bool(tool_summary.get("ok", False))
        payload["tool_events_total"] = int(tool_summary.get("count", 0))
        status_counts = tool_summary.get("status_counts") if isinstance(tool_summary.get("status_counts"), dict) else {}
        last_tool = tool_summary.get("last_event") if isinstance(tool_summary.get("last_event"), dict) else {}
        payload["tool_events_ok_count"] = int(status_counts.get("ok", 0))
        payload["tool_events_denied_count"] = int(status_counts.get("denied", 0))
        payload["tool_events_error_count"] = int(status_counts.get("error", 0))
        payload["tool_events_success_count"] = int(tool_summary.get("success_count", 0))
        payload["tool_events_failure_count"] = int(tool_summary.get("failure_count", 0))
        payload["tool_events_avg_latency_ms"] = int(tool_summary.get("avg_latency_ms", 0))
        payload["tool_avg_latency_ms_by_tool"] = tool_summary.get("avg_latency_ms_by_tool") or {}
        payload["last_tool_error_summary"] = str(tool_summary.get("last_error_summary") or "")
        payload["last_tool_name"] = str(last_tool.get("tool") or "")
        payload["last_tool_status"] = str(last_tool.get("status") or "")
        payload["last_tool_user"] = str(last_tool.get("user") or "")

        payload["action_ledger_ok"] = bool(ledger_summary.get("ok", False))
        payload["action_ledger_total"] = int(ledger_summary.get("count", 0) or 0)
        last_record = ledger_summary.get("last_record") if isinstance(ledger_summary.get("last_record"), dict) else {}
        payload["last_intent"] = str(last_record.get("intent") or "")
        payload["last_planner_decision"] = str(last_record.get("planner_decision") or "")
        payload["last_action_tool"] = str(last_record.get("tool") or "")
        payload["last_route_summary"] = str(last_record.get("route_summary") or "")
        payload["last_route_grounded"] = bool(last_record.get("grounded")) if last_record else False
        payload["last_route_trace"] = list(last_record.get("route_trace") or []) if isinstance(last_record.get("route_trace"), list) else []
        payload["last_action_final_answer"] = str(last_record.get("final_answer") or "")
        provider_telemetry = payload.get("provider_telemetry") or {}
        active_priority = {
            str(item or "").strip().lower()
            for item in list(payload.get("search_provider_priority") or [])
            if str(item or "").strip()
        }
        telemetry_provider = ControlStatusService._clean_provider_value(provider_telemetry.get("last_provider_used"))
        telemetry_family = ControlStatusService._clean_provider_value(provider_telemetry.get("last_provider_family"))
        last_provider_hit = ControlStatusService._clean_provider_value(last_record.get("provider_used")) or telemetry_provider
        if active_priority and last_provider_hit and last_provider_hit not in active_priority:
            last_provider_hit = telemetry_provider if telemetry_provider in active_priority else ""
        last_provider_family = ControlStatusService._clean_provider_value(last_record.get("provider_family")) or telemetry_family
        if active_priority and last_provider_family and last_provider_family not in active_priority:
            last_provider_family = telemetry_family if telemetry_family in active_priority else ""
        payload["last_provider_hit"] = last_provider_hit
        payload["last_provider_family"] = last_provider_family
        payload["last_provider_available"] = bool(last_provider_hit)
        payload["last_provider_note"] = "provider_hit_recorded" if last_provider_hit else "no_provider_hit_recorded"

        payload["patch_status_ok"] = bool(patch_summary.get("ok", False))
        payload["patch_enabled"] = bool(patch_summary.get("enabled", False))
        payload["patch_strict_manifest"] = bool(patch_summary.get("strict_manifest", False))
        payload["patch_allow_force"] = bool(patch_summary.get("allow_force", False))
        payload["patch_behavioral_check"] = bool(patch_summary.get("behavioral_check", False))
        payload["patch_behavioral_check_timeout_sec"] = int(patch_summary.get("behavioral_check_timeout_sec", 0) or 0)
        payload["patch_tests_available"] = bool(patch_summary.get("tests_available", False))
        payload["patch_pipeline_ready"] = bool(patch_summary.get("pipeline_ready", False))
        payload["patch_ready_for_validated_apply"] = bool(patch_summary.get("ready_for_validated_apply", False))
        payload["patch_current_revision"] = int(patch_summary.get("current_revision", 0) or 0)
        payload["patch_previews_total"] = int(patch_summary.get("previews_total", 0) or 0)
        payload["patch_previews_pending"] = int(patch_summary.get("previews_pending", 0) or 0)
        payload["patch_previews_approved"] = int(patch_summary.get("previews_approved", 0) or 0)
        payload["patch_previews_rejected"] = int(patch_summary.get("previews_rejected", 0) or 0)
        payload["patch_previews_eligible"] = int(patch_summary.get("previews_eligible", 0) or 0)
        payload["patch_previews_approved_eligible"] = int(patch_summary.get("previews_approved_eligible", 0) or 0)
        payload["patch_previews_orphaned"] = int(patch_summary.get("previews_orphaned", 0) or 0)
        payload["patch_review_previews_total"] = int(patch_summary.get("review_previews_total", 0) or 0)
        payload["patch_review_previews_pending_distinct"] = int(patch_summary.get("review_previews_pending_distinct", 0) or 0)
        payload["patch_review_previews_pending_superseded"] = int(patch_summary.get("review_previews_pending_superseded", 0) or 0)
        payload["patch_review_previews_approved_distinct"] = int(patch_summary.get("review_previews_approved_distinct", 0) or 0)
        payload["patch_review_previews_approved_superseded"] = int(patch_summary.get("review_previews_approved_superseded", 0) or 0)
        payload["patch_review_previews_orphaned"] = int(patch_summary.get("review_previews_orphaned", 0) or 0)
        payload["patch_review_previews_superseded_total"] = int(patch_summary.get("review_previews_superseded_total", 0) or 0)
        payload["patch_last_preview_name"] = str(patch_summary.get("last_preview_name") or "")
        payload["patch_last_preview_status"] = str(patch_summary.get("last_preview_status") or "")
        payload["patch_last_preview_decision"] = str(patch_summary.get("last_preview_decision") or "")
        payload["patch_last_log_line"] = str(patch_summary.get("last_patch_log_line") or "")
        payload["patch_previews"] = list(patch_summary.get("previews") or []) if isinstance(patch_summary.get("previews"), list) else []
        payload["patch_action_readiness"] = patch_action_readiness

        payload["pulse"] = pulse_payload
        payload["pulse_summary"] = {
            "generated_at": str(pulse_payload.get("generated_at") or ""),
            "autonomy_level": str(pulse_payload.get("autonomy_level") or "unknown"),
            "promoted_total": int(pulse_payload.get("promoted_total", 0) or 0),
            "promoted_delta": int(pulse_payload.get("promoted_delta", 0) or 0),
            "ready_for_validated_apply": bool(pulse_payload.get("ready_for_validated_apply", False)),
        }
        payload["update_now_pending"] = update_now_pending
        payload["core_running"] = bool(core_status.get("running"))
        payload["core_pid"] = core_status.get("pid")
        payload["core_heartbeat_age_sec"] = core_status.get("heartbeat_age_sec")
        payload["requests_total"] = int(requests_total)
        payload["errors_total"] = int(errors_total)
        return payload


CONTROL_STATUS_SERVICE = ControlStatusService()
