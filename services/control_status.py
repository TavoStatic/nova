from __future__ import annotations

import time


class ControlStatusService:
    """Own HTTP control-status payload assembly outside the transport layer."""

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
        schedule_tree: list | None = None,
    ) -> dict:
        schedule_rows = list(schedule_tree or [])
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
            "autonomy_maintenance": autonomy_maintenance if isinstance(autonomy_maintenance, dict) else {},
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
            "schedule_tree": schedule_rows,
        }

        # Central plan surface used by the control UI to avoid plan wiring drift.
        payload["plans"] = {
            "schedule_tree": schedule_rows,
            "generated_work_queue": generated_work_queue if isinstance(generated_work_queue, dict) else {},
            "action_readiness": action_readiness if isinstance(action_readiness, dict) else {},
            "patch_action_readiness": patch_action_readiness if isinstance(patch_action_readiness, dict) else {},
        }

        runtime_worker = autonomy_maintenance.get("runtime_worker") if isinstance(autonomy_maintenance, dict) and isinstance(autonomy_maintenance.get("runtime_worker"), dict) else {}
        last_generated_queue_run = autonomy_maintenance.get("last_generated_queue_run") if isinstance(autonomy_maintenance, dict) and isinstance(autonomy_maintenance.get("last_generated_queue_run"), dict) else {}
        payload["runtime_worker_status"] = str(runtime_worker.get("last_cycle_status") or "")
        payload["runtime_worker_interval_sec"] = int(runtime_worker.get("interval_sec", 0) or 0)
        payload["runtime_worker_cycle_count"] = int(runtime_worker.get("cycle_count", 0) or 0)
        payload["runtime_worker_last_completed_at"] = str(runtime_worker.get("last_completed_at") or "")
        payload["last_generated_queue_run_status"] = str(last_generated_queue_run.get("status") or "")
        payload["last_generated_queue_run_file"] = str(last_generated_queue_run.get("selected_file") or "")
        payload["last_generated_queue_run_at"] = str(last_generated_queue_run.get("ts") or "")
        payload["last_generated_queue_report_status"] = str(last_generated_queue_run.get("latest_report_status") or "")

        payload["memory_stats_ok"] = bool(memory_stats.get("ok", False))
        payload["memory_entries_total"] = int(memory_stats.get("total", 0) or 0)
        payload["memory_by_user_count"] = len(memory_stats.get("by_user") or {}) if isinstance(memory_stats.get("by_user"), dict) else 0
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
        last_provider_hit = str(last_record.get("provider_used") or provider_telemetry.get("last_provider_used") or "").strip().lower()
        if last_provider_hit and last_provider_hit not in active_priority:
            last_provider_hit = str(provider_telemetry.get("last_provider_used") or "").strip().lower()
        last_provider_family = str(last_record.get("provider_family") or provider_telemetry.get("last_provider_family") or "").strip().lower()
        if last_provider_family and last_provider_family not in active_priority:
            last_provider_family = str(provider_telemetry.get("last_provider_family") or "").strip().lower()
        payload["last_provider_hit"] = last_provider_hit
        payload["last_provider_family"] = last_provider_family

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