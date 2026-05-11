from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Optional

from services.test_session_definitions import count_definition_files


def _count_definition_files(root: Path) -> int:
    return count_definition_files(root)


def _promotion_audit_summary(
    *,
    promotion_audit_log: Path,
    generated_definitions_dir: Path,
    promoted_definitions_dir: Path,
    pending_review_dir: Path,
    quarantine_dir: Path,
) -> dict:
    latest_by_file = {}
    if promotion_audit_log.exists():
        try:
            with promotion_audit_log.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(row, dict):
                        continue
                    file_name = str(row.get("file") or "").strip()
                    if not file_name:
                        continue
                    latest_by_file[file_name] = row
        except Exception:
            latest_by_file = {}

    status_counts = {}
    latest_ts = ""
    for row in latest_by_file.values():
        status = str(row.get("status") or "unknown").strip() or "unknown"
        status_counts[status] = int(status_counts.get(status, 0) or 0) + 1
        row_ts = str(row.get("ts") or "").strip()
        if row_ts > latest_ts:
            latest_ts = row_ts

    return {
        "generated_total": _count_definition_files(generated_definitions_dir),
        "promoted_total": _count_definition_files(promoted_definitions_dir),
        "pending_review_total": _count_definition_files(pending_review_dir),
        "quarantine_total": _count_definition_files(quarantine_dir),
        "latest_audited_files": len(latest_by_file),
        "latest_audit_ts": latest_ts,
        "status_counts": status_counts,
    }


def _parse_log_timestamp(ts_text: str) -> float:
    try:
        return time.mktime(time.strptime(str(ts_text or "").strip(), "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return 0.0


def _patch_activity_summary(
    *,
    patch_log: Path,
    read_patch_log_tail_line_fn: Callable[[], str],
    window_hours: int = 24,
) -> dict:
    summary = {
        "apply_count": 0,
        "apply_ok_count": 0,
        "rollback_count": 0,
        "behavior_fail_count": 0,
        "last_line": read_patch_log_tail_line_fn(),
    }
    if not patch_log.exists():
        return summary

    window_seconds = max(1, int(window_hours or 24)) * 3600
    cutoff = time.time() - window_seconds
    try:
        with patch_log.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or "|" not in line:
                    continue
                ts_text, event = line.split("|", 1)
                event = event.strip()
                event_ts = _parse_log_timestamp(ts_text)
                if event_ts and event_ts < cutoff:
                    continue
                if event.startswith("APPLY_OK"):
                    summary["apply_ok_count"] += 1
                elif event.startswith("APPLY "):
                    summary["apply_count"] += 1
                elif event.startswith("ROLLBACK"):
                    summary["rollback_count"] += 1
                elif event.startswith("BEHAVIOR_FAIL"):
                    summary["behavior_fail_count"] += 1
    except Exception:
        return summary
    return summary


def _pulse_level(ollama_up: bool, routing_stable: bool, fallback_score: float, rollback_count: int) -> str:
    if not ollama_up:
        return "deterministic-only"
    if not routing_stable or fallback_score >= 0.9 or rollback_count > 0:
        return "guarded"
    return "operational"


def _pulse_mood(ollama_up: bool, routing_stable: bool, promoted_delta: int, fallback_score: float, rollback_count: int) -> str:
    if not ollama_up:
        return "LLM link is down, so I am holding to deterministic paths only."
    if rollback_count > 0 or fallback_score >= 0.9:
        return "Stable, but I am watching rollback pressure and fallback drift closely."
    if not routing_stable:
        return "Routing is unsettled, so I am staying conservative."
    if promoted_delta > 0:
        return "Learning is moving forward cleanly."
    return "Quiet and steady."


def build_pulse_payload(
    *,
    promotion_audit_log: Path,
    generated_definitions_dir: Path,
    promoted_definitions_dir: Path,
    pending_review_dir: Path,
    quarantine_dir: Path,
    behavior_metrics_file: Path,
    autonomy_maintenance_file: Path,
    pulse_snapshot_file: Path,
    patch_log: Path,
    load_json_file_fn: Callable[[Path, Any], Any],
    patch_status_payload_fn: Callable[[], dict],
    read_patch_log_tail_line_fn: Callable[[], str],
    ollama_api_up_fn: Callable[[], bool],
    mem_stats_payload_fn: Callable[..., dict],
    kidney_summary_fn: Callable[[], dict],
    safety_policy_fn: Callable[[], dict],
    latest_approved_update_zip_fn: Callable[[Optional[dict]], Optional[Path]],
    generated_work_queue_fn: Optional[Callable[[int], dict]] = None,
    memory_health_payload_fn: Optional[Callable[[], dict]] = None,
) -> dict:
    audit = _promotion_audit_summary(
        promotion_audit_log=promotion_audit_log,
        generated_definitions_dir=generated_definitions_dir,
        promoted_definitions_dir=promoted_definitions_dir,
        pending_review_dir=pending_review_dir,
        quarantine_dir=quarantine_dir,
    )
    behavior = load_json_file_fn(behavior_metrics_file, {})
    autonomy = load_json_file_fn(autonomy_maintenance_file, {})
    prior = load_json_file_fn(pulse_snapshot_file, {})
    patch = patch_status_payload_fn()
    patch_activity = _patch_activity_summary(
        patch_log=patch_log,
        read_patch_log_tail_line_fn=read_patch_log_tail_line_fn,
        window_hours=24,
    )
    ollama_up = bool(ollama_api_up_fn())
    routing_stable = bool(behavior.get("routing_stable", False))
    legacy_fallback_score = float(autonomy.get("last_fallback_overuse_score") or 0.0)
    raw_fallback_score = float(autonomy.get("last_raw_fallback_overuse_score", legacy_fallback_score) or 0.0)
    stored_active_fallback_score = float(
        autonomy.get("last_active_fallback_overuse_score", legacy_fallback_score) or 0.0
    )
    stored_fallback_pressure_active = bool(autonomy.get("last_fallback_pressure_active"))
    last_generated_queue_run = autonomy.get("last_generated_queue_run") if isinstance(autonomy.get("last_generated_queue_run"), dict) else {}
    latest_queue_status = str(last_generated_queue_run.get("status") or "").strip().lower()
    latest_queue_report_status = str(last_generated_queue_run.get("latest_report_status") or "").strip().lower()
    live_queue = {}
    if generated_work_queue_fn is not None:
        try:
            maybe_queue = generated_work_queue_fn(24)
            live_queue = maybe_queue if isinstance(maybe_queue, dict) else {}
        except Exception:
            live_queue = {}
    if live_queue:
        latest_queue_status = str(live_queue.get("status") or latest_queue_status).strip().lower()
        if int(live_queue.get("drift_count", 0) or 0) > 0:
            latest_queue_report_status = "drift"
        elif int(live_queue.get("warning_count", 0) or 0) > 0:
            latest_queue_report_status = "warning"
        elif int(live_queue.get("never_run_count", 0) or 0) > 0:
            latest_queue_report_status = "never_run"
        elif int(live_queue.get("green_count", 0) or 0) >= int(live_queue.get("count", 0) or 0) and int(live_queue.get("count", 0) or 0) > 0:
            latest_queue_report_status = "green"
    live_fallback_pressure_active = raw_fallback_score >= 0.75 and latest_queue_report_status in {"drift", "failed", "error", "blocked"}
    fallback_pressure_active = (
        stored_active_fallback_score >= 0.75 and stored_fallback_pressure_active
    ) or live_fallback_pressure_active
    if fallback_pressure_active:
        active_fallback_score = max(stored_active_fallback_score, raw_fallback_score if live_fallback_pressure_active else 0.0)
    else:
        active_fallback_score = 0.0
    promoted_total = int(audit.get("promoted_total", 0) or 0)
    prior_promoted_total = int(prior.get("promoted_total", 0) or 0)
    promoted_delta = promoted_total - prior_promoted_total if prior_promoted_total else 0
    approved_update_zip = latest_approved_update_zip_fn(patch)

    memory_payload = mem_stats_payload_fn(emit_event=False)
    memory_health = {}
    if memory_health_payload_fn is not None:
        try:
            maybe_health = memory_health_payload_fn()
            memory_health = maybe_health if isinstance(maybe_health, dict) else {}
        except Exception as exc:
            memory_health = {
                "ok": False,
                "status": "failure",
                "issue_count": 1,
                "issues": [
                    {
                        "severity": "failure",
                        "code": "memory_health_failed",
                        "detail": str(exc)[:260],
                    }
                ],
            }
    kidney_summary = kidney_summary_fn()
    safety_cfg = safety_policy_fn()
    memory_stats_ok = bool(memory_payload.get("ok", False))
    memory_health_ok = bool(memory_health.get("ok", True)) if memory_health else True
    memory_db = memory_health.get("memory_db") if isinstance(memory_health.get("memory_db"), dict) else {}
    memory_events_log = memory_health.get("memory_events_log") if isinstance(memory_health.get("memory_events_log"), dict) else {}
    memory_scoped_total = int(memory_payload.get("total", 0) or 0) if memory_payload.get("ok") else 0

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "promoted_total": promoted_total,
        "promoted_delta": max(0, int(promoted_delta)),
        "generated_total": int(audit.get("generated_total", 0) or 0),
        "pending_review_total": int(audit.get("pending_review_total", 0) or 0),
        "quarantine_total": int(audit.get("quarantine_total", 0) or 0),
        "latest_audited_files": int(audit.get("latest_audited_files", 0) or 0),
        "latest_audit_ts": str(audit.get("latest_audit_ts") or "unknown"),
        "audit_status_counts": dict(audit.get("status_counts") or {}),
        "routing_stable": routing_stable,
        "tool_route_count": int(behavior.get("tool_route", 0) or 0),
        "llm_fallback_count": int(behavior.get("llm_fallback", 0) or 0),
        "last_reflection_at": str(behavior.get("last_reflection_at") or "unknown"),
        "last_fallback_overuse_score": active_fallback_score,
        "raw_fallback_overuse_score": raw_fallback_score,
        "active_fallback_overuse_score": active_fallback_score,
        "fallback_pressure_active": fallback_pressure_active,
        "last_generated_queue_status": latest_queue_status,
        "last_generated_queue_report_status": latest_queue_report_status,
        "last_regression_status": str(autonomy.get("last_regression_status") or "unknown"),
        "last_regression_stale": bool(autonomy.get("last_regression_stale", False)),
        "patch_revision": int(patch.get("current_revision", 0) or 0),
        "approved_eligible_previews": int(patch.get("previews_approved_eligible", 0) or 0),
        "ready_for_validated_apply": bool(patch.get("ready_for_validated_apply", False)),
        "patch_activity": patch_activity,
        "patch_last_line": str(patch.get("last_patch_log_line") or patch_activity.get("last_line") or "none"),
        "ollama_up": ollama_up,
        "memory_ok": memory_stats_ok and memory_health_ok,
        "memory_stats_ok": memory_stats_ok,
        "memory_total": memory_scoped_total,
        "memory_scoped_total": memory_scoped_total,
        "memory_db_total": int(memory_db.get("total", memory_scoped_total) or 0),
        "memory_health": memory_health,
        "memory_health_status": str(memory_health.get("status") or ("ok" if memory_health_ok else "failure")) if memory_health else "unknown",
        "memory_health_issue_count": int(memory_health.get("issue_count", 0) or 0) if memory_health else 0,
        "memory_health_issues": list(memory_health.get("issues") or [])[:6] if isinstance(memory_health.get("issues"), list) else [],
        "memory_events_log_status": str(memory_events_log.get("status") or "unknown"),
        "memory_events_log_invalid_tail_count": int(memory_events_log.get("invalid_tail_count", 0) or 0),
        "memory_events_log_bytes": int(memory_events_log.get("byte_count", 0) or 0),
        "kidney_mode": str(kidney_summary.get("mode") or "unknown"),
        "kidney_candidates": int(kidney_summary.get("candidate_count", 0) or 0),
        "kidney_archive_count": int(kidney_summary.get("archive_count", 0) or 0),
        "kidney_delete_count": int(kidney_summary.get("delete_count", 0) or 0),
        "safety_enabled": bool(safety_cfg.get("enabled", True)) if isinstance(safety_cfg, dict) else True,
        "safety_mode": str(safety_cfg.get("mode") or "unknown") if isinstance(safety_cfg, dict) else "unknown",
        "update_zip_path": str(approved_update_zip) if approved_update_zip is not None else "",
    }
    payload["autonomy_level"] = _pulse_level(
        payload["ollama_up"],
        payload["routing_stable"],
        payload["active_fallback_overuse_score"],
        int((payload.get("patch_activity") or {}).get("rollback_count", 0) or 0),
    )
    payload["mood"] = _pulse_mood(
        payload["ollama_up"],
        payload["routing_stable"],
        payload["promoted_delta"],
        payload["active_fallback_overuse_score"],
        int((payload.get("patch_activity") or {}).get("rollback_count", 0) or 0),
    )
    return payload


def write_pulse_snapshot(payload: dict, *, pulse_snapshot_file: Path) -> None:
    snapshot = {
        "generated_at": str(payload.get("generated_at") or ""),
        "promoted_total": int(payload.get("promoted_total", 0) or 0),
        "patch_revision": int(payload.get("patch_revision", 0) or 0),
        "llm_fallback_count": int(payload.get("llm_fallback_count", 0) or 0),
        "tool_route_count": int(payload.get("tool_route_count", 0) or 0),
    }
    try:
        pulse_snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        pulse_snapshot_file.write_text(json.dumps(snapshot, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception:
        return


def render_nova_pulse(payload: Optional[dict] = None, *, build_pulse_payload_fn: Optional[Callable[[], dict]] = None) -> str:
    data = payload if isinstance(payload, dict) else (build_pulse_payload_fn() if build_pulse_payload_fn else {})
    patch_activity = data.get("patch_activity") if isinstance(data.get("patch_activity"), dict) else {}
    status_counts = data.get("audit_status_counts") if isinstance(data.get("audit_status_counts"), dict) else {}
    audit_status_text = ", ".join(f"{name}={status_counts[name]}" for name in sorted(status_counts)) if status_counts else "none"

    lines = [
        f"Nova Pulse - {data.get('generated_at')}",
        "Core evolution:",
        f"- promoted definitions: {int(data.get('promoted_total', 0) or 0)} (+{int(data.get('promoted_delta', 0) or 0)} since last pulse)",
        f"- generated definitions: {int(data.get('generated_total', 0) or 0)}",
        f"- pending review: {int(data.get('pending_review_total', 0) or 0)}",
        f"- quarantine: {int(data.get('quarantine_total', 0) or 0)}",
        f"- latest audited files: {int(data.get('latest_audited_files', 0) or 0)} at {data.get('latest_audit_ts')}",
        f"- audit statuses: {audit_status_text}",
        "Updates:",
        f"- patch revision: {int(data.get('patch_revision', 0) or 0)}",
        f"- ready for validated apply: {'yes' if data.get('ready_for_validated_apply') else 'no'}",
        f"- approved eligible previews: {int(data.get('approved_eligible_previews', 0) or 0)}",
        f"- patch activity last 24h: applies={int(patch_activity.get('apply_count', 0) or 0)}, apply_ok={int(patch_activity.get('apply_ok_count', 0) or 0)}, rollbacks={int(patch_activity.get('rollback_count', 0) or 0)}, behavior_failures={int(patch_activity.get('behavior_fail_count', 0) or 0)}",
        f"- patch log tail: {data.get('patch_last_line')}",
        "Support systems:",
        f"- Ollama API: {'online' if data.get('ollama_up') else 'offline'}",
        f"- memory: {'ok' if data.get('memory_ok') else 'watch'} (scope_total={int(data.get('memory_scoped_total', data.get('memory_total', 0)) or 0)}, db_total={int(data.get('memory_db_total', data.get('memory_total', 0)) or 0)}, health={data.get('memory_health_status') or 'unknown'}, events={data.get('memory_events_log_status') or 'unknown'})",
        f"- kidney: mode={data.get('kidney_mode')} candidates={int(data.get('kidney_candidates', 0) or 0)} archive={int(data.get('kidney_archive_count', 0) or 0)} delete={int(data.get('kidney_delete_count', 0) or 0)}",
        f"- safety envelope: enabled={bool(data.get('safety_enabled'))} mode={data.get('safety_mode')}",
        "Autonomy:",
        f"- level: {data.get('autonomy_level')}",
        f"- routing stable: {'yes' if data.get('routing_stable') else 'no'}",
        f"- tool routes vs llm fallbacks: {int(data.get('tool_route_count', 0) or 0)} / {int(data.get('llm_fallback_count', 0) or 0)}",
        f"- active fallback pressure score: {float(data.get('active_fallback_overuse_score', data.get('last_fallback_overuse_score', 0.0)) or 0.0):.2f}",
        f"- last regression status: {data.get('last_regression_status')}",
        f"- last reflection: {data.get('last_reflection_at')}",
        "Assessment:",
        f"- {data.get('mood')}",
    ]
    raw_fallback_score = float(data.get("raw_fallback_overuse_score", data.get("last_fallback_overuse_score", 0.0)) or 0.0)
    active_fallback_score = float(data.get("active_fallback_overuse_score", data.get("last_fallback_overuse_score", 0.0)) or 0.0)
    if raw_fallback_score >= 0.75 and raw_fallback_score > active_fallback_score:
        queue_status = str(data.get("last_generated_queue_report_status") or data.get("last_generated_queue_status") or "informational")
        lines.append(f"- fallback robustness history: {raw_fallback_score:.2f} (not active; queue report is {queue_status})")
    memory_issues = list(data.get("memory_health_issues") or [])
    if memory_issues:
        rendered_issues = []
        for item in memory_issues[:3]:
            if isinstance(item, dict):
                code = str(item.get("code") or "memory_health_issue")
                detail = str(item.get("detail") or "").strip()
                rendered_issues.append(f"{code}: {detail}" if detail else code)
        if rendered_issues:
            lines.append(f"- memory watch: {'; '.join(rendered_issues)}")
    update_zip_path = str(data.get("update_zip_path") or "").strip()
    if update_zip_path:
        lines.append('Type "update now" if you want me to apply the latest approved validated update.')
    else:
        lines.append("No approved validated update is queued right now.")
    return "\n".join(lines)


def tool_nova_pulse(
    *,
    build_pulse_payload_fn: Callable[[], dict],
    write_pulse_snapshot_fn: Callable[[dict], None],
    render_nova_pulse_fn: Callable[[dict], str],
) -> str:
    payload = build_pulse_payload_fn()
    write_pulse_snapshot_fn(payload)
    return render_nova_pulse_fn(payload)
