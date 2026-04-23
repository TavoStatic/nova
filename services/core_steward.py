from __future__ import annotations

import time
from typing import Any


def _check_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or "").strip()
    return str(getattr(item, "name", "") or "").strip()


def _check_ok(item: Any) -> bool:
    if isinstance(item, dict):
        return bool(item.get("ok"))
    return bool(getattr(item, "ok", False))


def _check_required(item: Any) -> bool:
    if isinstance(item, dict):
        return bool(item.get("required"))
    return bool(getattr(item, "required", False))


def _queue_item(priority: str, title: str, reason: str, command: str) -> dict[str, str]:
    return {
        "priority": priority,
        "title": title,
        "reason": reason,
        "command": command,
    }


def build_core_steward_payload(
    *,
    preflight_checks: list[Any],
    runtime_health: dict,
    pulse_payload: dict,
    autonomy_maintenance: dict,
    kidney_summary: dict,
) -> dict:
    checks = list(preflight_checks or [])
    required_failed = [item for item in checks if _check_required(item) and not _check_ok(item)]

    heartbeat = dict(runtime_health.get("heartbeat") or {}) if isinstance(runtime_health, dict) else {}
    core_state = dict(runtime_health.get("core_state") or {}) if isinstance(runtime_health, dict) else {}
    ollama = dict(runtime_health.get("ollama") or {}) if isinstance(runtime_health, dict) else {}

    runtime_worker = {}
    if isinstance(autonomy_maintenance, dict) and isinstance(autonomy_maintenance.get("runtime_worker"), dict):
        runtime_worker = dict(autonomy_maintenance.get("runtime_worker") or {})

    fallback_score = float(pulse_payload.get("last_fallback_overuse_score", 0.0) or 0.0) if isinstance(pulse_payload, dict) else 0.0
    approved_updates = int(pulse_payload.get("approved_eligible_previews", 0) or 0) if isinstance(pulse_payload, dict) else 0
    kidney_candidates = int(kidney_summary.get("candidate_count", 0) or 0) if isinstance(kidney_summary, dict) else 0
    kidney_mode = str(kidney_summary.get("mode") or "unknown").strip() if isinstance(kidney_summary, dict) else "unknown"
    worker_status = str(runtime_worker.get("last_cycle_status") or "").strip().lower()
    last_generated_queue_run = dict(autonomy_maintenance.get("last_generated_queue_run") or {}) if isinstance(autonomy_maintenance, dict) else {}
    latest_report_status = str(last_generated_queue_run.get("latest_report_status") or last_generated_queue_run.get("status") or "").strip().lower()
    fallback_penalty_active = fallback_score >= 0.75 and latest_report_status in {"drift", "failed", "error", "blocked"}
    kidney_penalty_active = kidney_candidates > 0 and kidney_mode != "enforce"

    score = 100
    score -= min(35, len(required_failed) * 12)
    if not bool(heartbeat.get("ok")):
        score -= 20
    if not bool(core_state.get("ok")):
        score -= 20
    if not bool(ollama.get("ok")):
        score -= 10
    if fallback_penalty_active:
        if fallback_score >= 0.90:
            score -= 15
        elif fallback_score >= 0.75:
            score -= 10
        elif fallback_score >= 0.50:
            score -= 5
    if kidney_penalty_active:
        if kidney_candidates >= 10:
            score -= 10
        elif kidney_candidates >= 1:
            score -= 5
    if worker_status not in {"running", "ok"}:
        score -= 5
    score = max(0, min(100, score))

    level = "strong"
    if required_failed or not bool(heartbeat.get("ok")) or not bool(core_state.get("ok")):
        level = "repair"
    elif score < 85 or fallback_penalty_active or kidney_penalty_active or worker_status not in {"running", "ok"}:
        level = "watch"

    queue: list[dict[str, str]] = []
    if required_failed:
        queue.append(
            _queue_item(
                "high",
                "Repair preflight gaps",
                f"{len(required_failed)} required doctor checks are failing.",
                "nova doctor --fix",
            )
        )
    if not bool(heartbeat.get("ok")) or not bool(core_state.get("ok")):
        queue.append(
            _queue_item(
                "high",
                "Recover core runtime",
                "Heartbeat or core-state health is degraded.",
                "nova runtime-status",
            )
        )
    if not bool(ollama.get("ok")):
        queue.append(
            _queue_item(
                "high",
                "Repair model runtime",
                "Ollama is not currently healthy.",
                "c:/Nova/.venv/Scripts/python.exe health.py repair",
            )
        )
    if worker_status not in {"running", "ok"}:
        queue.append(
            _queue_item(
                "medium",
                "Restart maintenance worker",
                "Autonomy maintenance is not reporting an active running cycle.",
                "start autonomy maintenance worker",
            )
        )
    if fallback_score >= 0.75:
        queue.append(
            _queue_item(
                "medium",
                "Review fallback training pressure",
                (
                    f"Fallback overuse score is elevated at {fallback_score:.2f}."
                    if fallback_penalty_active
                    else f"Fallback training pressure is elevated at {fallback_score:.2f}, but the latest queue status is {latest_report_status or 'informational'}."
                ),
                "pulse",
            )
        )
    if kidney_candidates > 0:
        queue.append(
            _queue_item(
                "medium",
                "Review cleanup pressure",
                (
                    f"Kidney reported {kidney_candidates} cleanup candidate(s) in {kidney_mode} mode."
                    if kidney_penalty_active
                    else f"Kidney is actively enforcing cleanup and reported {kidney_candidates} candidate(s) this cycle."
                ),
                "kidney dry-run",
            )
        )
    if approved_updates > 0:
        queue.append(
            _queue_item(
                "low",
                "Review validated updates",
                f"{approved_updates} approved eligible preview(s) are ready for apply review.",
                "update now",
            )
        )

    summary_lines = []
    if required_failed:
        summary_lines.append(f"doctor:{len(required_failed)} required check(s) failing")
    if not bool(heartbeat.get("ok")):
        summary_lines.append(f"heartbeat:{heartbeat.get('info') or 'degraded'}")
    if not bool(core_state.get("ok")):
        summary_lines.append(f"core_state:{core_state.get('info') or 'degraded'}")
    if not bool(ollama.get("ok")):
        summary_lines.append(f"ollama:{ollama.get('info') or 'degraded'}")
    if fallback_penalty_active:
        summary_lines.append(f"fallback_pressure:{fallback_score:.2f}")
    if kidney_penalty_active:
        summary_lines.append(f"kidney_candidates:{kidney_candidates}")
    if worker_status not in {"running", "ok"}:
        summary_lines.append(f"maintenance_worker:{worker_status or 'inactive'}")
    if not summary_lines:
        summary_lines.append("core surfaces look stable")

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "score": score,
        "level": level,
        "summary": "; ".join(summary_lines),
        "doctor": {
            "required_failed": [_check_name(item) for item in required_failed],
            "required_failed_count": len(required_failed),
            "checks_total": len(checks),
        },
        "runtime": {
            "heartbeat": heartbeat,
            "core_state": core_state,
            "ollama": ollama,
        },
        "pulse": {
            "autonomy_level": str(pulse_payload.get("autonomy_level") or "unknown") if isinstance(pulse_payload, dict) else "unknown",
            "routing_stable": bool(pulse_payload.get("routing_stable", False)) if isinstance(pulse_payload, dict) else False,
            "fallback_overuse_score": fallback_score,
            "approved_eligible_previews": approved_updates,
        },
        "kidney": {
            "mode": kidney_mode,
            "candidate_count": kidney_candidates,
            "archive_count": int(kidney_summary.get("archive_count", 0) or 0) if isinstance(kidney_summary, dict) else 0,
            "delete_count": int(kidney_summary.get("delete_count", 0) or 0) if isinstance(kidney_summary, dict) else 0,
        },
        "autonomy_maintenance": {
            "worker_status": worker_status or "unknown",
            "interval_sec": int(runtime_worker.get("interval_sec", 0) or 0),
            "last_completed_at": str(runtime_worker.get("last_completed_at") or ""),
        },
        "maintenance_queue": queue,
    }


def build_core_steward_gates(
    *,
    core_steward: dict | None,
    patch_summary: dict | None = None,
    release_status: dict | None = None,
) -> dict[str, dict[str, object]]:
    steward = dict(core_steward or {})
    patch = dict(patch_summary or {})
    release = dict(release_status or {})
    level = str(steward.get("level") or "unknown").strip().lower()
    summary = str(steward.get("summary") or "core steward signal unavailable").strip() or "core steward signal unavailable"

    if level == "strong":
        steward_ready = True
        steward_reason = f"Core Steward is strong: {summary}."
    elif level in {"watch", "repair"}:
        steward_ready = False
        steward_reason = f"Core Steward is {level}: {summary}."
    else:
        steward_ready = False
        steward_reason = f"Core Steward signal is unavailable: {summary}."

    patch_ready = bool(patch.get("enabled", False)) and bool(patch.get("ready_for_validated_apply", False))
    if not steward_ready:
        patch_apply = {"enabled": False, "reason": steward_reason}
        update_now_confirm = {"enabled": False, "reason": steward_reason}
    elif not bool(patch.get("enabled", False)):
        patch_apply = {"enabled": False, "reason": "Patch pipeline is disabled by policy."}
        update_now_confirm = {"enabled": False, "reason": "Patch pipeline is disabled by policy."}
    elif not patch_ready:
        patch_apply = {"enabled": False, "reason": "No approved eligible preview is ready to apply."}
        update_now_confirm = {"enabled": False, "reason": "No approved eligible preview is ready to apply."}
    else:
        patch_apply = {"enabled": True, "reason": "Core Steward is strong and the patch pipeline is ready for validated apply."}
        update_now_confirm = {"enabled": True, "reason": "Core Steward is strong and the pending update is eligible for confirmation."}

    release_ready = bool(release.get("latest_ready_to_ship", False))
    release_note = str(release.get("latest_readiness_note") or release.get("latest_readiness_state") or "release readiness signal unavailable").strip()
    if not steward_ready:
        release_promotion = {"enabled": False, "reason": steward_reason}
    elif not release_ready:
        release_promotion = {"enabled": False, "reason": release_note or "Latest release candidate is not ready to ship."}
    else:
        release_promotion = {"enabled": True, "reason": "Core Steward is strong and the latest release candidate is ready to ship."}

    return {
        "patch_preview_apply": patch_apply,
        "update_now_confirm": update_now_confirm,
        "release_promotion": release_promotion,
    }


def render_core_steward(payload: dict | None = None) -> str:
    data = payload if isinstance(payload, dict) else {}
    doctor = dict(data.get("doctor") or {})
    runtime = dict(data.get("runtime") or {})
    pulse = dict(data.get("pulse") or {})
    kidney = dict(data.get("kidney") or {})
    autonomy = dict(data.get("autonomy_maintenance") or {})
    queue = list(data.get("maintenance_queue") or [])

    lines = [
        f"Core Steward - {data.get('generated_at')}",
        f"Strength score: {int(data.get('score', 0) or 0)}/100",
        f"Level: {str(data.get('level') or 'unknown')}",
        f"Summary: {str(data.get('summary') or 'unknown')}",
        "Surfaces:",
        f"- doctor required failures: {int(doctor.get('required_failed_count', 0) or 0)}",
        f"- heartbeat: {'ok' if (runtime.get('heartbeat') or {}).get('ok') else 'degraded'} ({(runtime.get('heartbeat') or {}).get('info', '')})",
        f"- core state: {'ok' if (runtime.get('core_state') or {}).get('ok') else 'degraded'} ({(runtime.get('core_state') or {}).get('info', '')})",
        f"- ollama: {'ok' if (runtime.get('ollama') or {}).get('ok') else 'degraded'} ({(runtime.get('ollama') or {}).get('info', '')})",
        f"- fallback pressure: {float(pulse.get('fallback_overuse_score', 0.0) or 0.0):.2f}",
        f"- kidney: mode={kidney.get('mode')} candidates={int(kidney.get('candidate_count', 0) or 0)}",
        f"- maintenance worker: {autonomy.get('worker_status')} interval={int(autonomy.get('interval_sec', 0) or 0)}s",
    ]

    if queue:
        lines.append("Maintenance queue:")
        for index, item in enumerate(queue, start=1):
            lines.append(
                f"{index}. [{str(item.get('priority') or 'info').upper()}] {str(item.get('title') or '').strip()}"
            )
            lines.append(f"   reason: {str(item.get('reason') or '').strip()}")
            lines.append(f"   command: {str(item.get('command') or '').strip()}")
    else:
        lines.append("Maintenance queue:")
        lines.append("1. [OK] No immediate maintenance action is recommended.")

    return "\n".join(lines)