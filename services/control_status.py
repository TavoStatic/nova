from __future__ import annotations

import os
import time
from pathlib import Path

from services.data_pipeline_registry import list_pipeline_summaries
from services.edfi.core_readiness import read_edfi_core_readiness
from services.edfi.profile_evidence import build_capability_profile_evidence
from services.frontdoor_cli_parity import FRONTDOOR_CLI_PARITY_SERVICE
from services.nova_grounded_self_report import GROUNDED_SELF_REPORT_SERVICE
from services.regression_lanes import SOURCE_PROFILE_LANES
from services.regression_profile_inventory import build_regression_profile_inventory_payload
from services.nova_root_inventory import build_source_root_inventory_payload
from services.nova_wiring_inventory import build_root_closure_inventory_payload
from services.nova_wiring_inventory import build_self_repair_closure_inventory_payload
from services.nova_wiring_inventory import build_source_wiring_probe_payload
from services.nova_wiring_inventory import build_wiring_inventory_payload
from services.nova_wiring_inventory import wiring_surface_ids
from services.sock_service import get_sock_status_keys
from services.capabilities_gap_detector import enhance_status_with_capability_gaps
from services.layer_maturity_policy import enrich_status_with_layer_maturity
from services.control_status_surfaces import CONTROL_STATUS_SURFACES_SERVICE
from services.work_tree_pressure_snapshot import build_work_tree_pressure_snapshot

ROOT = Path(__file__).resolve().parents[1]


class ControlStatusService:
    """Own HTTP control-status payload assembly outside the transport layer."""

    @staticmethod
    def _clean_provider_value(value) -> str:
        text = str(value or "").strip().lower()
        if text in {"none", "null", "undefined", "n/a", "na"}:
            return ""
        return text

    @staticmethod
    def _os_capability_control_payload(summary: dict | None, operator_outbox: dict | None = None) -> dict:
        raw = dict(summary or {}) if isinstance(summary, dict) else {}
        outbox = dict(operator_outbox or {}) if isinstance(operator_outbox, dict) else {}
        open_notice_keys: set[tuple[str, str]] = set()
        open_notices = [
            item
            for item in list(outbox.get("open_events") or [])
            if isinstance(item, dict)
        ]
        latest_open = outbox.get("latest_open") if isinstance(outbox.get("latest_open"), dict) else {}
        if latest_open:
            open_notices.append(dict(latest_open))
        for notice in open_notices:
            if str(notice.get("source") or "").strip() != "os_capability":
                continue
            payload = notice.get("payload") if isinstance(notice.get("payload"), dict) else {}
            capability = str(payload.get("capability") or "").strip()
            reason = str(payload.get("blocked_reason") or "").strip().lower()
            if capability and reason:
                open_notice_keys.add((capability, reason))
        rows = [
            dict(item)
            for item in list(raw.get("rows") or [])
            if isinstance(item, dict)
        ]
        status_counts = dict(raw.get("status_counts") or {}) if isinstance(raw.get("status_counts"), dict) else {}
        reason_counts = dict(raw.get("reason_counts") or {}) if isinstance(raw.get("reason_counts"), dict) else {}
        latest_by_capability: dict[str, dict] = {}
        for row in rows:
            capability = str(row.get("capability") or "").strip() or "unknown"
            latest_by_capability[capability] = row
        current_issue_rows: list[dict] = []
        historic_issue_rows: list[dict] = []
        now_epoch = time.time()
        active_age_sec = 6 * 60 * 60
        for row in latest_by_capability.values():
            status_text = str(row.get("status") or "").strip().lower()
            if status_text != "success" or bool(row.get("operator_outbox")):
                capability = str(row.get("capability") or "").strip() or "unknown"
                reason_text = str(row.get("reason") or "").strip().lower()
                ts_epoch = float(row.get("ts_epoch", 0) or 0)
                age_sec = max(0.0, now_epoch - ts_epoch) if ts_epoch > 0 else 0.0
                row = dict(row)
                row["age_sec"] = int(age_sec) if ts_epoch > 0 else None
                if (capability, reason_text) in open_notice_keys or age_sec <= active_age_sec:
                    current_issue_rows.append(row)
                else:
                    historic_issue_rows.append(row)
        current_issue_rows.sort(key=lambda item: float(item.get("ts_epoch", 0) or 0))
        last_row = dict(raw.get("last_row") or {}) if isinstance(raw.get("last_row"), dict) else (rows[-1] if rows else {})
        last_issue = current_issue_rows[-1] if current_issue_rows else {}
        current_status_counts: dict[str, int] = {}
        current_reason_counts: dict[str, int] = {}
        for row in current_issue_rows:
            status_text = str(row.get("status") or "").strip().lower()
            reason_text = str(row.get("reason") or "").strip().lower()
            if status_text:
                current_status_counts[status_text] = current_status_counts.get(status_text, 0) + 1
            if reason_text:
                current_reason_counts[reason_text] = current_reason_counts.get(reason_text, 0) + 1
        current_blocked_count = int(current_status_counts.get("blocked", 0) or 0)
        current_timeout_count = int(current_status_counts.get("timeout", 0) or 0)
        current_failure_count = sum(
            int(current_status_counts.get(status, 0) or 0)
            for status in ("failed", "error", "timeout")
        )
        current_operator_outbox_count = sum(1 for row in current_issue_rows if bool(row.get("operator_outbox")))
        readable_ok = bool(raw.get("ok", True))
        return {
            "ok": bool(readable_ok and not current_issue_rows),
            "readable_ok": readable_ok,
            "count": int(raw.get("count", len(rows)) or 0),
            "ledger_path": str(raw.get("path") or raw.get("ledger_path") or "runtime/os_capability_ledger.jsonl"),
            "status_counts": status_counts,
            "reason_counts": reason_counts,
            "current_issue_count": len(current_issue_rows),
            "current_status_counts": current_status_counts,
            "current_reason_counts": current_reason_counts,
            "current_blocked_count": current_blocked_count,
            "current_failure_count": current_failure_count,
            "current_timeout_count": current_timeout_count,
            "current_operator_outbox_count": current_operator_outbox_count,
            "current_issue_rows": current_issue_rows[-12:],
            "historic_issue_count": len(historic_issue_rows),
            "historic_issue_rows": historic_issue_rows[-12:],
            "last_row": last_row,
            "last_issue": last_issue,
        }

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
            "work_trees_payload",
            "work_tree_pressure_payload",
            "operator_outbox_summary",
            "load_operator_macros",
            "load_backend_commands",
            "memory_events_summary",
            "tool_events_summary",
            "action_ledger_summary",
            "os_capability_ledger_summary",
            "provider_telemetry_payload",
            "runtime_summary_payload",
            "runtime_artifacts_payload",
            "validation_artifact_truth_payload",
            "runtime_restart_analytics_payload",
            "runtime_failure_reasons_payload",
            "port_ownership_payload",
            "action_readiness_payload",
            "release_status_payload",
            "installer_status_payload",
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
        lightweight: bool = False,
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
        work_trees_payload_fn = supplier_fns["work_trees_payload"]
        operator_outbox_summary_fn = supplier_fns["operator_outbox_summary"]
        load_operator_macros_fn = supplier_fns["load_operator_macros"]
        load_backend_commands_fn = supplier_fns["load_backend_commands"]
        memory_events_summary_fn = supplier_fns["memory_events_summary"]
        tool_events_summary_fn = supplier_fns["tool_events_summary"]
        action_ledger_summary_fn = supplier_fns["action_ledger_summary"]
        os_capability_ledger_summary_fn = supplier_fns.get(
            "os_capability_ledger_summary",
            lambda limit: {
                "ok": True,
                "count": 0,
                "status_counts": {},
                "reason_counts": {},
                "last_row": {},
                "rows": [],
            },
        )
        provider_telemetry_payload_fn = supplier_fns["provider_telemetry_payload"]
        runtime_summary_payload_fn = supplier_fns["runtime_summary_payload"]
        runtime_artifacts_payload_fn = supplier_fns["runtime_artifacts_payload"]
        validation_artifact_truth_payload_fn = supplier_fns["validation_artifact_truth_payload"]
        runtime_restart_analytics_payload_fn = supplier_fns["runtime_restart_analytics_payload"]
        runtime_failure_reasons_payload_fn = supplier_fns["runtime_failure_reasons_payload"]
        port_ownership_payload_fn = supplier_fns["port_ownership_payload"]
        action_readiness_payload_fn = supplier_fns["action_readiness_payload"]
        release_status_payload_fn = supplier_fns["release_status_payload"]
        installer_status_payload_fn = supplier_fns.get("installer_status_payload", lambda: {})
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
        work_trees_payload = work_trees_payload_fn(32)
        operator_outbox_summary = operator_outbox_summary_fn(20)
        operator_macros = load_operator_macros_fn(24)
        backend_commands = load_backend_commands_fn(40)
        frontdoor_surfaces = FRONTDOOR_CLI_PARITY_SERVICE.build_surfaces(
            root=ROOT,
            backend_commands=backend_commands,
        )
        backend_commands = list(frontdoor_surfaces.get("backend_commands") or backend_commands)
        memory_stats = core_module.mem_stats_payload(emit_event=False)
        memory_summary = memory_events_summary_fn(80)
        tool_summary = tool_events_summary_fn(80)
        ledger_summary = action_ledger_summary_fn(80)
        os_capability_summary = os_capability_ledger_summary_fn(80)
        patch_summary = core_module.patch_status_payload()
        pulse_payload = core_module.build_pulse_payload()
        update_now_pending = core_module.update_now_pending_payload()
        try:
            data_pipelines = {
                "ok": True,
                "pipelines": list_pipeline_summaries(),
                "error": "",
            }
        except Exception as exc:
            data_pipelines = {
                "ok": False,
                "pipelines": [],
                "error": str(exc),
            }
        try:
            edfi_capability_profile = build_capability_profile_evidence()
        except Exception as exc:
            edfi_capability_profile = {
                "ok": False,
                "status": "failure",
                "present": False,
                "issue_count": 1,
                "issues": [{
                    "code": "edfi_profile_evidence_unreadable",
                    "severity": "failure",
                    "detail": str(exc),
                }],
                "profile_evidence_path": "runtime/edfi/profiles/district-main.json",
            }
        try:
            edfi_core_readiness = read_edfi_core_readiness("district-main")
        except Exception as exc:
            edfi_core_readiness = {
                "ready": False,
                "milestone": "",
                "connection_id": "district-main",
                "issues": [{"code": "edfi_core_readiness_unreadable", "detail": str(exc)}],
            }
        requests_total, errors_total = metrics_totals
        if hasattr(core_module, "ollama_health_payload"):
            ollama_health = core_module.ollama_health_payload()
        else:
            ollama_health = {"ok": bool(core_module.ollama_api_up()), "status": "legacy_probe", "info": ""}
        voice_status_payload_fn = getattr(core_module, "voice_status_payload", None)
        voice_status = voice_status_payload_fn() if callable(voice_status_payload_fn) else {}
        vision_status_payload_fn = getattr(core_module, "vision_status_payload", None)
        vision_status = {}
        if callable(vision_status_payload_fn):
            try:
                vision_status = vision_status_payload_fn(policy=policy, ollama_health=ollama_health)
            except TypeError:
                vision_status = vision_status_payload_fn()

        payload = self.status_payload(
            policy=policy,
            provider=provider,
            endpoint=endpoint,
            searx_ok=searx_ok,
            searx_note=searx_note,
            search_provider_priority=list(core_module.get_search_provider_priority()),
            provider_telemetry=provider_telemetry_payload_fn(ledger_summary=ledger_summary, tool_summary=tool_summary),
            ollama_api_up=bool(ollama_health.get("server_ok", ollama_health.get("ok"))),
            ollama_health=ollama_health,
            voice_status=voice_status,
            vision_status=vision_status,
            chat_model=core_module.chat_model(),
            memory_enabled=bool(core_module.mem_enabled()),
            subconscious_summary=subconscious_summary,
            subconscious_live_summary=subconscious_live_summary,
            generated_work_queue=generated_work_queue,
            autonomy_maintenance=autonomy_maintenance,
            work_trees_payload=work_trees_payload,
            operator_outbox=operator_outbox_summary,
            operator_macros=operator_macros,
            backend_commands=backend_commands,
            frontdoor_cli_status=str(frontdoor_surfaces.get("frontdoor_cli_status") or ""),
            cli_http_parity=(
                dict(frontdoor_surfaces.get("cli_http_parity") or {})
                if isinstance(frontdoor_surfaces.get("cli_http_parity"), dict)
                else {}
            ),
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
            validation_artifact_truth=validation_artifact_truth_payload_fn(),
            runtime_restart_analytics=runtime_restart_analytics_payload_fn(),
            runtime_failures=runtime_failure_reasons_payload_fn(guard_status, core_status, webui_status, timeline_payload),
            port_ownership=port_ownership_payload_fn(),
            live_tracking=core_module.runtime_device_location_payload(),
            action_readiness=action_readiness_payload_fn(guard_status, core_status, webui_status),
            release_status=release_status_payload_fn(),
            installer_status=installer_status_payload_fn(),
            memory_stats=memory_stats,
            memory_summary=memory_summary,
            tool_summary=tool_summary,
            ledger_summary=ledger_summary,
            os_capability_summary=os_capability_summary,
            patch_summary=patch_summary,
            patch_action_readiness=patch_action_readiness_payload_fn(patch_summary),
            pulse_payload=pulse_payload,
            update_now_pending=update_now_pending,
            data_pipelines=data_pipelines,
            edfi_capability_profile=edfi_capability_profile,
            edfi_core_readiness=edfi_core_readiness,
            requests_total=requests_total,
            errors_total=errors_total,
            storage_watch_summary=storage_watch_summary_fn(),
        )
        if not lightweight:
            append_metrics_snapshot_fn(payload)
        self_check = build_self_check_fn(payload, control_policy_payload_fn(), metrics_payload_fn())
        payload["health_score"] = int(self_check.get("health_score", 0))
        payload["self_check_pass_ratio"] = float(self_check.get("pass_ratio", 0.0))
        payload["alerts"] = list(self_check.get("alerts") or [])
        if not lightweight:
            report_payload = GROUNDED_SELF_REPORT_SERVICE.build_payload(payload, work_trees_payload)
            operator_attention = GROUNDED_SELF_REPORT_SERVICE.build_operator_attention(report_payload)
            payload["operator_attention"] = operator_attention
            payload["operator_attention_active"] = bool(operator_attention.get("active"))
            payload["operator_attention_level"] = str(operator_attention.get("level") or "")
            payload["operator_attention_message"] = str(operator_attention.get("message") or "")
        return payload

    def runtime_signal_ingestion_surfaces_payload(
        self,
        *,
        core_module,
        session_turns,
        metrics_totals: tuple[int, int],
        supplier_fns: dict[str, object] | None = None,
    ) -> dict:
        supplier_fns = dict(supplier_fns or {})
        guard_status_payload_fn = supplier_fns["guard_status_payload"]
        core_status_payload_fn = supplier_fns["core_status_payload"]
        http_status_payload_fn = supplier_fns["http_status_payload"]
        generated_work_queue_fn = supplier_fns["generated_work_queue"]
        autonomy_maintenance_summary_fn = supplier_fns["autonomy_maintenance_summary"]
        work_tree_pressure_payload_fn = supplier_fns.get("work_tree_pressure_payload", lambda: {})
        operator_outbox_summary_fn = supplier_fns["operator_outbox_summary"]
        validation_artifact_truth_payload_fn = supplier_fns["validation_artifact_truth_payload"]
        release_status_payload_fn = supplier_fns["release_status_payload"]
        runtime_summary_payload_fn = supplier_fns["runtime_summary_payload"]
        heartbeat_age_seconds_fn = supplier_fns["heartbeat_age_seconds"]

        policy = core_module.load_policy()
        web_cfg = policy.get("web") if isinstance(policy.get("web"), dict) else {}
        generated_work_queue = generated_work_queue_fn(8)
        autonomy_maintenance = autonomy_maintenance_summary_fn()
        autonomy_payload = dict(autonomy_maintenance or {}) if isinstance(autonomy_maintenance, dict) else {}
        operator_outbox = operator_outbox_summary_fn(8)
        validation_truth = validation_artifact_truth_payload_fn()
        release_status = release_status_payload_fn()
        guard_status = guard_status_payload_fn()
        core_status = core_status_payload_fn()
        webui_status = http_status_payload_fn()
        runtime_summary = runtime_summary_payload_fn(guard=guard_status, core=core_status, webui=webui_status)
        work_tree_pressure = work_tree_pressure_payload_fn()
        pulse_payload = core_module.build_pulse_payload()
        memory_health = pulse_payload.get("memory_health") if isinstance(pulse_payload.get("memory_health"), dict) else {}
        requests_total, errors_total = metrics_totals

        generated_queue_snapshot_has_truth = any(
            key in generated_work_queue
            for key in ("status", "open_count", "actionable_count", "blocked_count")
        )
        last_generated_queue_run = (
            autonomy_payload.get("last_generated_queue_run")
            if isinstance(autonomy_payload.get("last_generated_queue_run"), dict)
            else {}
        )
        queue_status = str(
            generated_work_queue.get("status")
            or autonomy_payload.get("generated_queue_status")
            or last_generated_queue_run.get("status")
            or ""
        ).strip()
        queue_open_count = int(
            (
                generated_work_queue.get("open_count")
                if generated_queue_snapshot_has_truth
                else autonomy_payload.get("queue_open_count", last_generated_queue_run.get("queue_open_count", 0))
            )
            or 0
        )
        queue_actionable_count = int(
            (
                generated_work_queue.get("actionable_count")
                if generated_queue_snapshot_has_truth
                else autonomy_payload.get("queue_actionable_count", last_generated_queue_run.get("queue_actionable_count", 0))
            )
            or 0
        )
        queue_blocked_count = int(
            (
                generated_work_queue.get("blocked_count")
                if generated_queue_snapshot_has_truth
                else autonomy_payload.get("queue_blocked_count", last_generated_queue_run.get("queue_blocked_count", 0))
            )
            or 0
        )
        if queue_open_count > 0 and queue_blocked_count <= 0 and queue_actionable_count <= 0:
            queue_blocked_count = queue_open_count
        queue_blocked_reason_counts = (
            dict(generated_work_queue.get("blocked_reason_counts") or {})
            if generated_queue_snapshot_has_truth and isinstance(generated_work_queue.get("blocked_reason_counts"), dict)
            else (
                dict(autonomy_payload.get("queue_blocked_reason_counts") or {})
                if isinstance(autonomy_payload.get("queue_blocked_reason_counts"), dict)
                else {}
            )
        )
        queue_blocked_files = (
            list(generated_work_queue.get("blocked_files") or [])
            if generated_queue_snapshot_has_truth and isinstance(generated_work_queue.get("blocked_files"), list)
            else (
                list(autonomy_payload.get("queue_blocked_files") or [])
                if isinstance(autonomy_payload.get("queue_blocked_files"), list)
                else []
            )
        )

        last_autonomy_orchestrator = (
            autonomy_payload.get("last_autonomy_orchestrator")
            if isinstance(autonomy_payload.get("last_autonomy_orchestrator"), dict)
            else {}
        )
        last_nova_mission = (
            autonomy_payload.get("last_nova_mission")
            if isinstance(autonomy_payload.get("last_nova_mission"), dict)
            else (
                last_autonomy_orchestrator.get("mission_snapshot")
                if isinstance(last_autonomy_orchestrator.get("mission_snapshot"), dict)
                else {}
            )
        )
        core_thinning_sync = (
            dict(autonomy_payload.get("last_core_thinning_sync") or {})
            if isinstance(autonomy_payload.get("last_core_thinning_sync"), dict)
            else {}
        )
        runtime_worker = autonomy_payload.get("runtime_worker") if isinstance(autonomy_payload.get("runtime_worker"), dict) else {}
        guard_running = bool((guard_status or {}).get("running"))
        if bool(runtime_worker.get("active", False)):
            maintenance_scheduler_mode = "worker_loop"
            maintenance_scheduler_status = "running"
        elif guard_running:
            maintenance_scheduler_mode = "guard_tick"
            maintenance_scheduler_status = "guard_scheduled"
        else:
            maintenance_scheduler_mode = "inactive"
            maintenance_scheduler_status = "inactive"

        validation_truth_payload = dict(validation_truth or {}) if isinstance(validation_truth, dict) else {}
        operator_outbox_payload = dict(operator_outbox or {}) if isinstance(operator_outbox, dict) else {}
        work_tree_payload = dict(work_tree_pressure or {}) if isinstance(work_tree_pressure, dict) else {}
        payload = {
            "ok": True,
            "status_kind": "signal_ingestion_surfaces",
            "guard": guard_status,
            "core": core_status,
            "webui": webui_status,
            "guard_status": guard_status,
            "core_status": core_status,
            "webui_status": webui_status,
            "runtime_summary": runtime_summary,
            "heartbeat_age_sec": heartbeat_age_seconds_fn(),
            "web_enabled": bool((policy.get("tools_enabled") or {}).get("web")) and bool(web_cfg.get("enabled")),
            "search_provider": str(web_cfg.get("search_provider") or "html"),
            "search_api_endpoint": str(web_cfg.get("search_api_endpoint") or ""),
            "search_provider_priority": list(core_module.get_search_provider_priority()),
            "active_http_sessions": len(session_turns),
            "requests_total": int(requests_total),
            "errors_total": int(errors_total),
            "generated_work_queue": generated_work_queue,
            "generated_queue_status": queue_status,
            "queue_open_count": queue_open_count,
            "queue_actionable_count": queue_actionable_count,
            "queue_blocked_count": queue_blocked_count,
            "queue_blocked_reason_counts": queue_blocked_reason_counts,
            "queue_blocked_files": queue_blocked_files,
            "autonomy_maintenance": autonomy_payload,
            "operator_outbox": operator_outbox_payload,
            "operator_outbox_open_count": int(operator_outbox_payload.get("open_count", 0) or 0),
            "operator_outbox_actionable_open_count": int(
                operator_outbox_payload.get("operator_actionable_open_count", operator_outbox_payload.get("open_count", 0))
                or 0
            ),
            "operator_outbox_actionable_latest_open_id": str(
                operator_outbox_payload.get("operator_actionable_latest_open_id") or ""
            ),
            "operator_outbox_latest_open_id": str((operator_outbox_payload.get("latest_open") or {}).get("id") or ""),
            "runtime_worker_status": str(runtime_worker.get("last_cycle_status") or ""),
            "runtime_worker_active": bool(runtime_worker.get("active", False)),
            "runtime_worker_stale_identity": bool(runtime_worker.get("stale_identity", False)),
            "maintenance_scheduler_active": bool(runtime_worker.get("active", False) or guard_running),
            "maintenance_scheduler_mode": maintenance_scheduler_mode,
            "maintenance_scheduler_status": maintenance_scheduler_status,
            "autonomy_orchestrator": last_autonomy_orchestrator,
            "autonomy_orchestrator_summary": (
                autonomy_payload.get("autonomy_orchestrator_summary")
                if isinstance(autonomy_payload.get("autonomy_orchestrator_summary"), dict)
                else {}
            ),
            "nova_mission": dict(last_nova_mission),
            "nova_mission_status": str(last_nova_mission.get("status") or ""),
            "nova_mission_action": str(last_nova_mission.get("action") or ""),
            "nova_mission_green_cycle": bool(last_nova_mission.get("green_cycle", False)),
            "nova_mission_headline": str(last_nova_mission.get("headline") or ""),
            "nova_mission_truth_ready": bool(last_nova_mission.get("truth_ready", False)),
            "nova_mission_truth_blockers": (
                list(last_nova_mission.get("truth_blockers") or [])
                if isinstance(last_nova_mission.get("truth_blockers"), list)
                else []
            ),
            "nova_mission_owner_verdicts": (
                list(last_nova_mission.get("owner_verdicts") or [])
                if isinstance(last_nova_mission.get("owner_verdicts"), list)
                else []
            ),
            "nova_mission_owner_blockers": (
                list(last_nova_mission.get("owner_blockers") or [])
                if isinstance(last_nova_mission.get("owner_blockers"), list)
                else []
            ),
            "nova_mission_green_blockers": (
                list(last_nova_mission.get("green_blockers") or [])
                if isinstance(last_nova_mission.get("green_blockers"), list)
                else []
            ),
            "nova_mission_blocking_owner_count": int(last_nova_mission.get("blocking_owner_count", 0) or 0),
            "nova_mission_core_gate_source": str(last_nova_mission.get("core_gate_source") or ""),
            "nova_mission_history": (
                list(autonomy_payload.get("nova_mission_history") or [])
                if isinstance(autonomy_payload.get("nova_mission_history"), list)
                else []
            ),
            "nova_mission_sustained_watch": bool(autonomy_payload.get("nova_mission_sustained_watch", False)),
            "nova_mission_watch_streak": int(autonomy_payload.get("nova_mission_watch_streak", 0) or 0),
            "core_thinning_sync": core_thinning_sync,
            "core_thinning_sync_status": str(core_thinning_sync.get("status") or ""),
            "core_thinning_sync_at": str(core_thinning_sync.get("ts") or ""),
            "core_thinning_order_count": int(core_thinning_sync.get("order_count", 0) or 0),
            "core_thinning_added_count": int(core_thinning_sync.get("added_count", 0) or 0),
            "core_thinning_resolved_count": int(core_thinning_sync.get("resolved_count", 0) or 0),
            "core_thinning_tree_id": str(core_thinning_sync.get("tree_id") or ""),
            "last_regression_status": str(autonomy_payload.get("last_regression_status") or ""),
            "last_regression_stale": bool(autonomy_payload.get("last_regression_stale", False)),
            "validation_artifact_truth": validation_truth_payload,
            "validation_artifact_truth_ok": bool(validation_truth_payload.get("ok", True)),
            "validation_artifact_truth_status": str(validation_truth_payload.get("status") or ""),
            "validation_artifact_failure_count": int(
                validation_truth_payload.get("current_window_failure_count", validation_truth_payload.get("failure_count", 0))
                or 0
            ),
            "validation_artifact_llm_unavailable_count": int(
                validation_truth_payload.get(
                    "current_window_llm_unavailable_count",
                    validation_truth_payload.get("llm_unavailable_count", 0),
                )
                or 0
            ),
            "validation_artifact_hidden_by_green_regression": bool(
                validation_truth_payload.get("hidden_by_green_regression", False)
            ),
            "validation_artifact_latest_failure": (
                dict(validation_truth_payload.get("latest_failure") or {})
                if isinstance(validation_truth_payload.get("latest_failure"), dict)
                else {}
            ),
            "release_status": release_status,
            "memory_health": memory_health,
            "memory_health_status": str(
                pulse_payload.get("memory_health_status")
                or memory_health.get("status")
                or ("ok" if pulse_payload.get("memory_ok") else "")
            ),
            "pulse": pulse_payload,
            "pulse_summary": {
                "generated_at": str(pulse_payload.get("generated_at") or ""),
                "autonomy_level": str(pulse_payload.get("autonomy_level") or "unknown"),
                "ready_for_validated_apply": bool(pulse_payload.get("ready_for_validated_apply", False)),
            },
            "work_tree_truth": work_tree_payload,
            "work_tree_truth_status": str(work_tree_payload.get("status") or ""),
            "work_tree_tree_count": int(work_tree_payload.get("tree_count", 0) or 0),
            "work_tree_active_tree_count": int(work_tree_payload.get("active_tree_count", 0) or 0),
            "work_tree_branch_count": int(work_tree_payload.get("branch_count", 0) or 0),
            "work_tree_open_task_count": int(work_tree_payload.get("open_task_count", 0) or 0),
            "work_tree_blocked_branch_count": int(work_tree_payload.get("blocked_branch_count", 0) or 0),
            "work_tree_operator_hold_branch_count": int(work_tree_payload.get("operator_hold_branch_count", 0) or 0),
            "work_tree_self_repair_blocked_branch_count": int(
                work_tree_payload.get("self_repair_blocked_branch_count", 0) or 0
            ),
            "work_tree_self_repair_observing_branch_count": int(
                work_tree_payload.get("self_repair_observing_branch_count", 0) or 0
            ),
            "work_tree_pending_branch_count": int(work_tree_payload.get("pending_count", 0) or 0),
            "work_tree_working_branch_count": int(work_tree_payload.get("working_count", 0) or 0),
            "work_tree_complete_branch_count": int(work_tree_payload.get("complete_count", 0) or 0),
            "work_tree_observing_branch_count": int(work_tree_payload.get("observing_branch_count", 0) or 0),
            "work_tree_blocked_observing_branch_count": int(work_tree_payload.get("blocked_observing_count", 0) or 0),
            "work_tree_latent_root_signal_count": int(work_tree_payload.get("latent_root_signal_count", 0) or 0),
            "work_tree_release_stale_ready_count": int(work_tree_payload.get("release_stale_ready_count", 0) or 0),
        }
        return CONTROL_STATUS_SURFACES_SERVICE.build_surfaces_payload(payload)

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
        frontdoor_cli_status: str = "",
        cli_http_parity: dict | None = None,
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
        os_capability_summary: dict | None = None,
        validation_artifact_truth: dict | None = None,
        storage_watch_summary: dict | None = None,
        work_trees_payload: dict | None = None,
        operator_outbox: dict | None = None,
        ollama_health: dict | None = None,
        voice_status: dict | None = None,
        vision_status: dict | None = None,
        port_ownership: dict | None = None,
        data_pipelines: dict | None = None,
        edfi_capability_profile: dict | None = None,
        edfi_core_readiness: dict | None = None,
        installer_status: dict | None = None,
    ) -> dict:
        autonomy_payload = autonomy_maintenance.copy() if isinstance(autonomy_maintenance, dict) else {}
        ollama_health_payload = dict(ollama_health or {}) if isinstance(ollama_health, dict) else {}
        port_ownership_payload = dict(port_ownership or {}) if isinstance(port_ownership, dict) else {}
        validation_truth_payload = (
            dict(validation_artifact_truth)
            if isinstance(validation_artifact_truth, dict)
            else {"ok": True, "status": "not_supplied"}
        )
        operator_outbox_payload = dict(operator_outbox or {}) if isinstance(operator_outbox, dict) else {}
        voice_status_payload = dict(voice_status or {}) if isinstance(voice_status, dict) else {}
        vision_status_payload = dict(vision_status or {}) if isinstance(vision_status, dict) else {}
        data_pipeline_payload = dict(data_pipelines or {}) if isinstance(data_pipelines, dict) else {"ok": True, "pipelines": []}
        edfi_profile_payload = (
            dict(edfi_capability_profile or {})
            if isinstance(edfi_capability_profile, dict)
            else {"ok": False, "status": "missing", "present": False, "issue_count": 0, "issues": []}
        )
        edfi_core_readiness_payload = (
            dict(edfi_core_readiness or {})
            if isinstance(edfi_core_readiness, dict)
            else {"ready": False, "milestone": "", "connection_id": "district-main", "issues": []}
        )
        installer_status_payload = dict(installer_status or {}) if isinstance(installer_status, dict) else {}
        os_capability_payload = ControlStatusService._os_capability_control_payload(
            os_capability_summary,
            operator_outbox_payload,
        )
        data_pipeline_rows = [
            dict(item)
            for item in list(data_pipeline_payload.get("pipelines") or [])
            if isinstance(item, dict)
        ]
        voice_runtime_requested = bool(
            voice_status_payload.get("requested", voice_status_payload.get("voice_ready", False))
        )
        voice_runtime_ok = bool(voice_status_payload.get("ok", not voice_runtime_requested))
        vision_runtime_requested = bool(vision_status_payload.get("requested", False))
        vision_runtime_ok = bool(vision_status_payload.get("ok", not vision_runtime_requested))
        payload = {
            "ok": True,
            "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "health_score": 0,
            "self_check_pass_ratio": 0.0,
            "ollama_api_up": bool(ollama_api_up),
            "ollama_server_ok": bool(ollama_health_payload.get("server_ok", bool(ollama_api_up))),
            "ollama_chat_ready": bool(ollama_health_payload.get("ok", bool(ollama_api_up))),
            "ollama_health": ollama_health_payload,
            "ollama_health_status": str(ollama_health_payload.get("status") or ""),
            "ollama_health_info": str(ollama_health_payload.get("info") or ""),
            "ollama_tags_ok": bool(ollama_health_payload.get("tags_ok", bool(ollama_api_up))),
            "ollama_chat_route_ok": bool(ollama_health_payload.get("chat_route_ok", bool(ollama_api_up))),
            "ollama_version": str(ollama_health_payload.get("version") or ""),
            "ollama_version_ok": bool(ollama_health_payload.get("version_ok", False)),
            "ollama_version_status": int(ollama_health_payload.get("version_status", 0) or 0),
            "ollama_api_contract_status": str(ollama_health_payload.get("api_contract_status") or ""),
            "ollama_configured_model": str(ollama_health_payload.get("chat_model") or chat_model or ""),
            "ollama_model_available": bool(ollama_health_payload.get("model_available", bool(ollama_api_up))),
            "ollama_model_status": str(ollama_health_payload.get("model_status") or ""),
            "ollama_available_models": list(ollama_health_payload.get("available_models") or []),
            "voice_status": voice_status_payload,
            "voice_runtime_status": str(voice_status_payload.get("status") or ""),
            "voice_runtime_requested": voice_runtime_requested,
            "voice_runtime_ok": voice_runtime_ok,
            "voice_import_error": str(voice_status_payload.get("import_error") or ""),
            "voice_sounddevice_loaded": bool(
                voice_status_payload.get("sounddevice_loaded", voice_status_payload.get("sounddevice_available", False))
            ),
            "voice_wav_loaded": bool(voice_status_payload.get("wav_loaded", voice_status_payload.get("wav_available", False))),
            "voice_whisper_loaded": bool(
                voice_status_payload.get("whisper_loaded", voice_status_payload.get("whisper_available", False))
            ),
            "vision_status": vision_status_payload,
            "vision_runtime_status": str(vision_status_payload.get("status") or ""),
            "vision_runtime_requested": vision_runtime_requested,
            "vision_runtime_ok": vision_runtime_ok,
            "vision_missing_modules": list(vision_status_payload.get("missing_modules") or []),
            "vision_screen_requested": bool(vision_status_payload.get("screen_requested", False)),
            "vision_camera_requested": bool(vision_status_payload.get("camera_requested", False)),
            "vision_model": str(vision_status_payload.get("vision_model") or ""),
            "vision_model_available": bool(vision_status_payload.get("vision_model_available", True)),
            "vision_note": str(vision_status_payload.get("note") or ""),
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
            "operator_outbox": operator_outbox_payload,
            "operator_outbox_open_count": int(operator_outbox_payload.get("open_count", 0) or 0),
            "operator_outbox_actionable_open_count": int(
                operator_outbox_payload.get("operator_actionable_open_count", operator_outbox_payload.get("open_count", 0))
                or 0
            ),
            "operator_outbox_actionable_latest_open_id": str(
                operator_outbox_payload.get("operator_actionable_latest_open_id") or ""
            ),
            "operator_outbox_latest_id": str(operator_outbox_payload.get("latest_id") or ""),
            "operator_outbox_latest_open_id": str((operator_outbox_payload.get("latest_open") or {}).get("id") or ""),
            "operator_outbox_status_counts": (
                dict(operator_outbox_payload.get("status_counts") or {})
                if isinstance(operator_outbox_payload.get("status_counts"), dict)
                else {}
            ),
            "operator_macros": operator_macros,
            "backend_commands": backend_commands,
            "backend_command_count": len(backend_commands),
            "frontdoor_cli_status": str(frontdoor_cli_status or ""),
            "cli_http_parity": (
                dict(cli_http_parity or {}) if isinstance(cli_http_parity, dict) else {}
            ),
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
            "validation_artifact_truth": validation_truth_payload,
            "validation_artifact_truth_ok": bool(validation_truth_payload.get("ok", True)),
            "validation_artifact_truth_status": str(validation_truth_payload.get("status") or ""),
            "validation_artifact_action_count": int(validation_truth_payload.get("action_count", 0) or 0),
            "validation_artifact_inspected_count": int(validation_truth_payload.get("inspected_count", 0) or 0),
            "validation_artifact_failure_count": int(
                validation_truth_payload.get(
                    "current_window_failure_count",
                    validation_truth_payload.get("failure_count", 0),
                )
                or 0
            ),
            "validation_artifact_llm_unavailable_count": int(
                validation_truth_payload.get(
                    "current_window_llm_unavailable_count",
                    validation_truth_payload.get("llm_unavailable_count", 0),
                )
                or 0
            ),
            "validation_artifact_hidden_by_green_regression": bool(
                validation_truth_payload.get("hidden_by_green_regression", False)
            ),
            "validation_artifact_latest_failure": (
                dict(validation_truth_payload.get("latest_failure") or {})
                if isinstance(validation_truth_payload.get("latest_failure"), dict)
                else {}
            ),
            "runtime_restart_analytics": runtime_restart_analytics,
            "runtime_failures": runtime_failures,
            "port_ownership": port_ownership_payload,
            "port_ownership_status": str(port_ownership_payload.get("status") or ""),
            "port_ownership_issue_count": int(port_ownership_payload.get("issue_count", 0) or 0),
            "live_tracking": live_tracking,
            "action_readiness": action_readiness,
            "release_status": release_status,
            "installer_release_status": installer_status_payload,
            "installer_status": str(installer_status_payload.get("latest_readiness_state") or ""),
            "installer_packaging_status": str(installer_status_payload.get("latest_readiness_state") or ""),
            "subconscious_summary": subconscious_summary,
            "generated_work_queue": generated_work_queue,
            "data_pipelines": data_pipeline_payload,
            "data_pipeline_registry_ok": bool(data_pipeline_payload.get("ok", True)),
            "data_pipeline_registry_error": str(data_pipeline_payload.get("error") or ""),
            "data_pipeline_count": len(data_pipeline_rows),
            "data_pipeline_ids": [
                str(item.get("pipeline_id") or "").strip()
                for item in data_pipeline_rows
                if str(item.get("pipeline_id") or "").strip()
            ],
            "edfi_capability_profile": edfi_profile_payload,
            "edfi_capability_profile_ok": bool(edfi_profile_payload.get("ok")),
            "edfi_capability_profile_status": str(edfi_profile_payload.get("status") or ""),
            "edfi_capability_profile_present": bool(edfi_profile_payload.get("present")),
            "edfi_capability_profile_connection_id": str(edfi_profile_payload.get("connection_id") or ""),
            "edfi_capability_profile_resource_count": int(edfi_profile_payload.get("resource_count") or 0),
            "edfi_capability_profile_discovered_at": int(edfi_profile_payload.get("discovered_at") or 0),
            "edfi_capability_profile_auth_ok": bool(edfi_profile_payload.get("auth_ok")),
            "edfi_capability_profile_issue_count": int(edfi_profile_payload.get("issue_count") or 0),
            "edfi_capability_profile_path": str(
                edfi_profile_payload.get("profile_evidence_path")
                or edfi_profile_payload.get("profile_path")
                or ""
            ),
            "edfi_core_readiness": dict(edfi_core_readiness_payload),
            "edfi_core_ready": bool(edfi_core_readiness_payload.get("ready", False)),
            "edfi_core_milestone": str(edfi_core_readiness_payload.get("milestone") or ""),
        }

        runtime_worker = autonomy_payload.get("runtime_worker") if isinstance(autonomy_payload.get("runtime_worker"), dict) else {}
        last_generated_queue_run = autonomy_payload.get("last_generated_queue_run") if isinstance(autonomy_payload.get("last_generated_queue_run"), dict) else {}
        last_work_tree_cycle = autonomy_payload.get("last_work_tree_cycle") if isinstance(autonomy_payload.get("last_work_tree_cycle"), dict) else {}
        last_patch_cleanup = autonomy_payload.get("last_patch_cleanup") if isinstance(autonomy_payload.get("last_patch_cleanup"), dict) else {}
        last_complete_tree_archive = autonomy_payload.get("last_complete_tree_archive") if isinstance(autonomy_payload.get("last_complete_tree_archive"), dict) else {}
        last_autonomy_orchestrator = autonomy_payload.get("last_autonomy_orchestrator") if isinstance(autonomy_payload.get("last_autonomy_orchestrator"), dict) else {}
        generated_queue_snapshot_has_truth = any(
            key in generated_work_queue
            for key in ("status", "open_count", "actionable_count", "blocked_count")
        )
        queue_status = str(
            generated_work_queue.get("status")
            or autonomy_payload.get("generated_queue_status")
            or last_generated_queue_run.get("status")
            or ""
        ).strip()
        queue_open_count = int(
            (
                generated_work_queue.get("open_count")
                if generated_queue_snapshot_has_truth
                else autonomy_payload.get("queue_open_count", last_generated_queue_run.get("queue_open_count", 0))
            )
            or 0
        )
        queue_actionable_count = int(
            (
                generated_work_queue.get("actionable_count")
                if generated_queue_snapshot_has_truth
                else autonomy_payload.get("queue_actionable_count", last_generated_queue_run.get("queue_actionable_count", 0))
            )
            or 0
        )
        queue_blocked_count = int(
            (
                generated_work_queue.get("blocked_count")
                if generated_queue_snapshot_has_truth
                else autonomy_payload.get("queue_blocked_count", last_generated_queue_run.get("queue_blocked_count", 0))
            )
            or 0
        )
        queue_blocked_reason_counts = (
            dict(generated_work_queue.get("blocked_reason_counts") or {})
            if generated_queue_snapshot_has_truth and isinstance(generated_work_queue.get("blocked_reason_counts"), dict)
            else (
                dict(autonomy_payload.get("queue_blocked_reason_counts") or {})
                if isinstance(autonomy_payload.get("queue_blocked_reason_counts"), dict)
                else {}
            )
        )
        queue_blocked_files = (
            list(generated_work_queue.get("blocked_files") or [])
            if generated_queue_snapshot_has_truth and isinstance(generated_work_queue.get("blocked_files"), list)
            else (
                list(autonomy_payload.get("queue_blocked_files") or [])
                if isinstance(autonomy_payload.get("queue_blocked_files"), list)
                else []
            )
        )
        if queue_open_count > 0 and queue_blocked_count <= 0 and queue_actionable_count <= 0:
            queue_blocked_count = queue_open_count
        if generated_queue_snapshot_has_truth and not str(generated_work_queue.get("status") or "").strip():
            if queue_open_count <= 0:
                queue_status = "clear"
            elif queue_actionable_count > 0:
                queue_status = "actionable"
            elif queue_blocked_count > 0:
                queue_status = "blocked"
            else:
                queue_status = "open"
        last_queue_run_status = str(last_generated_queue_run.get("status") or "").strip().lower()
        last_queue_run_status_mismatch = bool(
            last_queue_run_status
            and last_queue_run_status not in {"ok", "success"}
            and last_queue_run_status != queue_status.strip().lower()
        )
        last_generated_queue_run_stale = any(
            (
                last_queue_run_status_mismatch,
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
        payload["maintenance_cycle_process_active"] = bool(runtime_worker.get("cycle_process_active", False))
        payload["maintenance_cycle_process_count"] = int(runtime_worker.get("cycle_process_count", 0) or 0)
        payload["maintenance_cycle_process_pids"] = list(runtime_worker.get("cycle_process_pids") or [])
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
        last_nova_mission = (
            autonomy_maintenance.get("last_nova_mission")
            if isinstance(autonomy_maintenance.get("last_nova_mission"), dict)
            else (
                last_autonomy_orchestrator.get("mission_snapshot")
                if isinstance(last_autonomy_orchestrator.get("mission_snapshot"), dict)
                else {}
            )
        )
        payload["nova_mission"] = dict(last_nova_mission)
        payload["nova_mission_status"] = str(last_nova_mission.get("status") or "")
        payload["nova_mission_action"] = str(last_nova_mission.get("action") or "")
        payload["nova_mission_green_cycle"] = bool(last_nova_mission.get("green_cycle", False))
        payload["nova_mission_headline"] = str(last_nova_mission.get("headline") or "")
        payload["nova_mission_truth_ready"] = bool(last_nova_mission.get("truth_ready", False))
        payload["nova_mission_truth_blockers"] = (
            list(last_nova_mission.get("truth_blockers") or [])
            if isinstance(last_nova_mission.get("truth_blockers"), list)
            else []
        )
        payload["nova_mission_owner_verdicts"] = (
            list(last_nova_mission.get("owner_verdicts") or [])
            if isinstance(last_nova_mission.get("owner_verdicts"), list)
            else []
        )
        payload["nova_mission_owner_blockers"] = (
            list(last_nova_mission.get("owner_blockers") or [])
            if isinstance(last_nova_mission.get("owner_blockers"), list)
            else []
        )
        payload["nova_mission_green_blockers"] = (
            list(last_nova_mission.get("green_blockers") or [])
            if isinstance(last_nova_mission.get("green_blockers"), list)
            else []
        )
        payload["nova_mission_blocking_owner_count"] = int(last_nova_mission.get("blocking_owner_count", 0) or 0)
        payload["nova_mission_core_gate_source"] = str(last_nova_mission.get("core_gate_source") or "")
        payload["nova_mission_history"] = (
            list(autonomy_maintenance.get("nova_mission_history") or [])
            if isinstance(autonomy_maintenance.get("nova_mission_history"), list)
            else []
        )
        payload["nova_mission_sustained_watch"] = bool(autonomy_maintenance.get("nova_mission_sustained_watch", False))
        payload["nova_mission_watch_streak"] = int(autonomy_maintenance.get("nova_mission_watch_streak", 0) or 0)
        core_thinning_sync = (
            dict(autonomy_maintenance.get("last_core_thinning_sync") or {})
            if isinstance(autonomy_maintenance.get("last_core_thinning_sync"), dict)
            else {}
        )
        payload["core_thinning_sync"] = core_thinning_sync
        payload["core_thinning_sync_status"] = str(core_thinning_sync.get("status") or "")
        payload["core_thinning_sync_at"] = str(core_thinning_sync.get("ts") or "")
        payload["core_thinning_order_count"] = int(core_thinning_sync.get("order_count", 0) or 0)
        payload["core_thinning_added_count"] = int(core_thinning_sync.get("added_count", 0) or 0)
        payload["core_thinning_resolved_count"] = int(core_thinning_sync.get("resolved_count", 0) or 0)
        payload["core_thinning_tree_id"] = str(core_thinning_sync.get("tree_id") or "")
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
        work_trees = work_trees_payload if isinstance(work_trees_payload, dict) else {}
        work_tree_pressure = build_work_tree_pressure_snapshot(work_trees)
        work_tree_truth_status = str(work_tree_pressure.get("status") or "")
        work_tree_branch_count = int(work_tree_pressure.get("branch_count", 0) or 0)
        work_tree_open_task_count = int(work_tree_pressure.get("open_task_count", 0) or 0)
        work_tree_blocked_count = int(work_tree_pressure.get("blocked_branch_count", 0) or 0)
        work_tree_pending_count = int(work_tree_pressure.get("pending_count", 0) or 0)
        work_tree_working_count = int(work_tree_pressure.get("working_count", 0) or 0)
        work_tree_complete_count = int(work_tree_pressure.get("complete_count", 0) or 0)
        observing_count = int(work_tree_pressure.get("observing_branch_count", 0) or 0)
        latent_root_signal_count = int(work_tree_pressure.get("latent_root_signal_count", 0) or 0)
        operator_hold_count = int(work_tree_pressure.get("operator_hold_branch_count", 0) or 0)
        self_repair_blocked_count = int(work_tree_pressure.get("self_repair_blocked_branch_count", 0) or 0)
        self_repair_observing_count = int(work_tree_pressure.get("self_repair_observing_branch_count", 0) or 0)
        payload["work_tree_truth_status"] = work_tree_truth_status
        payload["work_tree_tree_count"] = int(work_tree_pressure.get("tree_count", 0) or 0)
        payload["work_tree_active_tree_count"] = int(work_tree_pressure.get("active_tree_count", 0) or 0)
        payload["work_tree_branch_count"] = work_tree_branch_count
        payload["work_tree_open_task_count"] = work_tree_open_task_count
        payload["work_tree_blocked_branch_count"] = work_tree_blocked_count
        payload["work_tree_operator_hold_branch_count"] = operator_hold_count
        payload["work_tree_self_repair_blocked_branch_count"] = self_repair_blocked_count
        payload["work_tree_self_repair_observing_branch_count"] = self_repair_observing_count
        payload["work_tree_pending_branch_count"] = work_tree_pending_count
        payload["work_tree_working_branch_count"] = work_tree_working_count
        payload["work_tree_complete_branch_count"] = work_tree_complete_count
        payload["work_tree_observing_branch_count"] = observing_count
        payload["work_tree_latent_root_signal_count"] = latent_root_signal_count
        payload["work_tree_truth"] = {
            "status": work_tree_truth_status,
            "tree_count": payload["work_tree_tree_count"],
            "active_tree_count": payload["work_tree_active_tree_count"],
            "branch_count": work_tree_branch_count,
            "open_task_count": work_tree_open_task_count,
            "blocked_branch_count": work_tree_blocked_count,
            "operator_hold_branch_count": operator_hold_count,
            "self_repair_blocked_branch_count": self_repair_blocked_count,
            "self_repair_observing_branch_count": self_repair_observing_count,
            "observing_branch_count": observing_count,
            "latent_root_signal_count": latent_root_signal_count,
        }
        autonomy_payload["work_tree_truth_status"] = work_tree_truth_status
        autonomy_payload["work_tree_blocked_branch_count"] = work_tree_blocked_count
        autonomy_payload["work_tree_observing_branch_count"] = observing_count
        autonomy_payload["work_tree_latent_root_signal_count"] = latent_root_signal_count
        autonomy_payload["work_tree_operator_hold_branch_count"] = operator_hold_count
        autonomy_payload["work_tree_self_repair_blocked_branch_count"] = self_repair_blocked_count
        autonomy_payload["work_tree_self_repair_observing_branch_count"] = self_repair_observing_count
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
        payload["storage_watch_watched_total_bytes"] = int(storage_watch.get("watched_total_bytes", 0) or 0)
        payload["runtime_storage_total_bytes"] = int(storage_watch.get("runtime_total_bytes", 0) or 0)
        payload["runtime_storage_file_count"] = int(storage_watch.get("runtime_file_count", 0) or 0)
        payload["patch_snapshot_count"] = int(storage_watch.get("patch_snapshot_count", 0) or 0)
        payload["kidney_snapshot_count"] = int(storage_watch.get("kidney_snapshot_count", 0) or 0)
        payload["release_validation_extract_count"] = int(storage_watch.get("release_validation_extract_count", 0) or 0)
        payload["release_validation_extract_bytes"] = int(storage_watch.get("release_validation_extract_bytes", 0) or 0)
        payload["release_stage_count"] = int(storage_watch.get("release_stage_count", 0) or 0)
        payload["release_stage_bytes"] = int(storage_watch.get("release_stage_bytes", 0) or 0)
        payload["release_zip_count"] = int(storage_watch.get("release_zip_count", 0) or 0)
        payload["release_zip_bytes"] = int(storage_watch.get("release_zip_bytes", 0) or 0)

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
        payload["last_tool_error_ts"] = int(tool_summary.get("last_error_ts", 0) or 0)
        last_tool_error_age = tool_summary.get("last_error_age_sec")
        payload["last_tool_error_age_sec"] = int(last_tool_error_age) if isinstance(last_tool_error_age, (int, float)) else None
        payload["last_tool_error_stale"] = bool(tool_summary.get("last_error_stale", False))
        payload["last_tool_name"] = str(last_tool.get("tool") or "")
        payload["last_tool_status"] = str(last_tool.get("status") or "")
        payload["last_tool_user"] = str(last_tool.get("user") or "")

        last_os_capability = os_capability_payload.get("last_row") if isinstance(os_capability_payload.get("last_row"), dict) else {}
        last_os_capability_issue = (
            os_capability_payload.get("last_issue")
            if isinstance(os_capability_payload.get("last_issue"), dict)
            else {}
        )
        payload["os_capability_ledger"] = os_capability_payload
        payload["os_capability_ledger_ok"] = bool(os_capability_payload.get("ok", False))
        payload["os_capability_ledger_readable_ok"] = bool(os_capability_payload.get("readable_ok", False))
        payload["os_capability_ledger_total"] = int(os_capability_payload.get("count", 0) or 0)
        payload["os_capability_ledger_current_issue_count"] = int(os_capability_payload.get("current_issue_count", 0) or 0)
        payload["os_capability_ledger_current_blocked_count"] = int(os_capability_payload.get("current_blocked_count", 0) or 0)
        payload["os_capability_ledger_current_failure_count"] = int(os_capability_payload.get("current_failure_count", 0) or 0)
        payload["os_capability_ledger_current_timeout_count"] = int(os_capability_payload.get("current_timeout_count", 0) or 0)
        payload["os_capability_ledger_current_operator_outbox_count"] = int(
            os_capability_payload.get("current_operator_outbox_count", 0) or 0
        )
        payload["os_capability_ledger_path"] = str(os_capability_payload.get("ledger_path") or "")
        payload["last_os_capability_name"] = str(last_os_capability.get("capability") or "")
        payload["last_os_capability_status"] = str(last_os_capability.get("status") or "")
        payload["last_os_capability_reason"] = str(last_os_capability.get("reason") or "")
        payload["last_os_capability_issue"] = dict(last_os_capability_issue)
        payload["last_os_capability_issue_name"] = str(last_os_capability_issue.get("capability") or "")
        payload["last_os_capability_issue_status"] = str(last_os_capability_issue.get("status") or "")
        payload["last_os_capability_issue_reason"] = str(last_os_capability_issue.get("reason") or "")

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
        test_profile_inventory = build_regression_profile_inventory_payload(test_lanes=SOURCE_PROFILE_LANES)
        payload["test_profile_inventory"] = test_profile_inventory
        payload["test_profile_inventory_ok"] = bool(test_profile_inventory.get("ok", False))
        payload["test_profile_profile_gap_count"] = int(test_profile_inventory.get("profile_gap_count", 0) or 0)
        payload["test_profile_profile_drift_count"] = int(test_profile_inventory.get("profile_drift_count", 0) or 0)
        payload["test_profile_profile_attention_count"] = int(test_profile_inventory.get("profile_attention_count", 0) or 0)
        payload["test_profile_curated_target_count"] = int(test_profile_inventory.get("curated_target_count", 0) or 0)
        payload["test_profile_curated_test_file_count"] = int(test_profile_inventory.get("curated_test_file_count", 0) or 0)
        payload["test_profile_root_test_file_count"] = int(test_profile_inventory.get("root_test_file_count", 0) or 0)
        payload["test_profile_all_test_file_count"] = int(test_profile_inventory.get("all_test_file_count", 0) or 0)
        payload["test_profile_source_observed_count"] = int(
            test_profile_inventory.get("source_observed_count", test_profile_inventory.get("outside_curated_count", 0)) or 0
        )
        payload["test_profile_outside_curated_count"] = int(test_profile_inventory.get("outside_curated_count", 0) or 0)
        payload["test_profile_install_profile_inactive_count"] = int(test_profile_inventory.get("install_profile_inactive_count", 0) or 0)
        payload["test_profile_install_profile_optional_inactive_count"] = int(
            test_profile_inventory.get("install_profile_optional_inactive_count", 0) or 0
        )
        payload["test_profile_unclassified_count"] = int(test_profile_inventory.get("unclassified_count", 0) or 0)
        source_root_inventory = build_source_root_inventory_payload(wiring_surface_ids=wiring_surface_ids())
        payload["source_root_inventory"] = source_root_inventory
        payload["source_root_inventory_ok"] = bool(source_root_inventory.get("ok", False))
        payload["source_root_inventory_root_count"] = int(source_root_inventory.get("root_count", 0) or 0)
        payload["source_root_inventory_gap_count"] = int(source_root_inventory.get("gap_count", 0) or 0)
        payload["source_root_inventory_unwired_roots"] = list(source_root_inventory.get("unwired_roots") or [])
        payload["source_root_inventory_missing_evidence_roots"] = list(
            source_root_inventory.get("missing_evidence_roots") or []
        )
        payload["source_root_inventory_source_file_count"] = int(source_root_inventory.get("source_file_count", 0) or 0)
        payload["source_root_inventory_unclassified_source_file_count"] = int(
            source_root_inventory.get("unclassified_source_file_count", 0) or 0
        )
        payload["source_root_inventory_unclassified_source_files"] = list(
            source_root_inventory.get("unclassified_source_files") or []
        )
        source_wiring_probe = build_source_wiring_probe_payload()
        payload["source_wiring_probe"] = source_wiring_probe
        payload["source_wiring_probe_ok"] = bool(source_wiring_probe.get("ok", False))
        payload["source_wiring_probe_gap_count"] = int(source_wiring_probe.get("gap_count", 0) or 0)
        payload["source_wiring_probe_missing_signal_sources"] = list(
            source_wiring_probe.get("missing_signal_sources") or []
        )
        payload["source_wiring_probe_missing_planned_tools"] = list(
            source_wiring_probe.get("missing_planned_tools") or []
        )
        payload["source_wiring_probe_missing_advisory_actions"] = list(
            source_wiring_probe.get("missing_advisory_actions") or []
        )
        payload["source_wiring_probe_planned_tools_without_execution"] = list(
            source_wiring_probe.get("planned_tools_without_execution") or []
        )
        payload["source_wiring_probe_advisory_actions_without_execution"] = list(
            source_wiring_probe.get("advisory_actions_without_execution") or []
        )
        payload["source_wiring_probe_missing_required_evidence_paths"] = list(
            source_wiring_probe.get("missing_required_evidence_paths") or []
        )
        payload["source_wiring_probe_missing_required_judgment_paths"] = list(
            source_wiring_probe.get("missing_required_judgment_paths") or []
        )
        payload["source_wiring_probe_missing_required_closure_paths"] = list(
            source_wiring_probe.get("missing_required_closure_paths") or []
        )
        payload["source_wiring_probe_missing_required_operator_outbox_paths"] = list(
            source_wiring_probe.get("missing_required_operator_outbox_paths") or []
        )
        payload["source_wiring_probe_missing_required_owned_root_routes"] = list(
            source_wiring_probe.get("missing_required_owned_root_routes") or []
        )
        try:
            payload = enhance_status_with_capability_gaps(payload)
            payload = enrich_status_with_layer_maturity(payload, policy=policy)
        except Exception:
            payload.setdefault("capability_gap_count", 0)
            payload.setdefault("capability_gaps", [])
            payload.setdefault("capabilities_gap_summary", {})
            payload.setdefault("layer_maturity", {})
            payload.setdefault("suppress_capability_gap_signals", True)
        root_closure_seed = {
            **payload,
            "root_closure_inventory": {},
            "root_closure_inventory_ok": True,
            "root_closure_inventory_gap_count": 0,
            "self_repair_closure_inventory": {},
            "self_repair_closure_inventory_ok": True,
            "self_repair_closure_inventory_gap_count": 0,
        }
        root_closure_inventory = build_root_closure_inventory_payload(
            root_closure_seed,
            signal_sources=source_wiring_probe.get("signal_sources", []),
            planned_tools=source_wiring_probe.get("planned_tools", []),
            advisory_actions=source_wiring_probe.get("advisory_actions", []),
        )
        payload["root_closure_inventory"] = root_closure_inventory
        payload["root_closure_inventory_ok"] = bool(root_closure_inventory.get("ok", False))
        payload["root_closure_inventory_gap_count"] = int(root_closure_inventory.get("gap_count", 0) or 0)
        payload["root_closure_inventory_gap_roots"] = list(root_closure_inventory.get("gap_roots") or [])
        try:
            payload = enrich_status_with_layer_maturity(payload, policy=policy)
        except Exception:
            payload.setdefault("layer_maturity", {})
        self_repair_closure_inventory = build_self_repair_closure_inventory_payload(
            root_closure_seed,
            signal_sources=source_wiring_probe.get("signal_sources", []),
            planned_tools=source_wiring_probe.get("planned_tools", []),
            advisory_actions=source_wiring_probe.get("advisory_actions", []),
            executable_tools=source_wiring_probe.get("executable_tools", []),
            executable_actions=source_wiring_probe.get("executable_actions", []),
            evidence_paths=source_wiring_probe.get("evidence_paths", []),
            judgment_paths=source_wiring_probe.get("judgment_paths", []),
            closure_paths=source_wiring_probe.get("closure_paths", []),
            operator_outbox_paths=source_wiring_probe.get("operator_outbox_paths", []),
            owned_root_routes=source_wiring_probe.get("owned_root_routes", []),
        )
        payload["self_repair_closure_inventory"] = self_repair_closure_inventory
        payload["self_repair_closure_inventory_ok"] = bool(self_repair_closure_inventory.get("ok", False))
        payload["self_repair_closure_inventory_gap_count"] = int(
            self_repair_closure_inventory.get("gap_count", 0) or 0
        )
        payload["self_repair_closure_inventory_gap_roots"] = list(
            self_repair_closure_inventory.get("gap_roots") or []
        )
        payload["self_repair_closure_source_contract_ready_count"] = int(
            self_repair_closure_inventory.get("source_contract_ready_count", 0) or 0
        )
        payload["self_repair_closure_depth_counts"] = dict(self_repair_closure_inventory.get("depth_counts") or {})
        last_temporal_feed = (
            autonomy_payload.get("last_temporal_feed")
            if isinstance(autonomy_payload.get("last_temporal_feed"), dict)
            else {}
        )
        payload["temporal_enabled"] = bool(last_temporal_feed.get("enabled", False))
        payload["temporal_feed_status"] = str(last_temporal_feed.get("status") or "")
        payload["temporal_feed_last_run_at"] = str(last_temporal_feed.get("ran_at") or "")
        payload["temporal_feed_event_count"] = int(last_temporal_feed.get("event_count", 0) or 0)
        payload["temporal_feed_surfaced_count"] = int(last_temporal_feed.get("surfaced_count", 0) or 0)
        payload["temporal_pressure_count"] = int(last_temporal_feed.get("pressure_count", 0) or 0)
        try:
            payload.update(get_sock_status_keys())
        except Exception:
            payload.setdefault("sock_hardware_profile", {})
            payload.setdefault("sock_recommendation", {})
            payload.setdefault("sock_policy_diff", {})
        wiring_inventory = build_wiring_inventory_payload(payload)
        payload["wiring_inventory"] = wiring_inventory
        payload["wiring_inventory_ok"] = bool(wiring_inventory.get("ok", False))
        payload["wiring_inventory_gap_count"] = int(wiring_inventory.get("gap_count", 0) or 0)
        return payload


CONTROL_STATUS_SERVICE = ControlStatusService()
