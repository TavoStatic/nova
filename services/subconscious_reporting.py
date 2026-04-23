from __future__ import annotations

from typing import Optional


def _summary_value(payload: object, key: str) -> object:
    if isinstance(payload, dict):
        return payload.get(key)
    return getattr(payload, key, None)


def _seam_label(target_seam: str) -> str:
    words = [part for part in str(target_seam or "").split("_") if part]
    return " ".join(words)


def build_training_backlog_summary(snapshot: dict) -> Optional[dict]:
    if not isinstance(snapshot, dict):
        return None
    try:
        from subconscious_training_backlog import build_training_backlog
    except Exception:
        return None

    backlog = build_training_backlog(snapshot)
    candidate_tests = list(getattr(backlog, "candidate_tests", []) or [])
    if not candidate_tests:
        return None

    return {
        "replan_requested": bool(getattr(backlog, "replan_requested", False)),
        "candidate_tests": [
            {
                "signal": str(getattr(item, "signal", "") or "").strip(),
                "occurrences": max(0, int(getattr(item, "occurrences", 0) or 0)),
                "priority": str(getattr(item, "priority", "") or "").strip().lower() or "low",
                "suggested_test_name": str(getattr(item, "suggested_test_name", "") or "").strip(),
                "rationale": str(getattr(item, "rationale", "") or "").strip(),
            }
            for item in candidate_tests
            if str(getattr(item, "signal", "") or "").strip()
        ],
    }


def build_robust_weakness_summary(family_summary: object) -> Optional[dict]:
    if family_summary is None:
        return None

    target_seam = str(_summary_value(family_summary, "target_seam") or "").strip()

    def _extract_items(name: str) -> list[dict]:
        values = _summary_value(family_summary, name)
        items = []
        for item in list(values or []):
            payload = dict(item) if isinstance(item, dict) else None
            if payload is None:
                continue
            cleaned = {
                "signal": str(payload.get("signal") or "").strip(),
                "classification": str(payload.get("classification") or "").strip(),
                "robustness_score": round(float(payload.get("robustness_score", 0.0) or 0.0), 4),
            }
            if str(payload.get("suggested_test_name") or "").strip():
                cleaned["suggested_test_name"] = str(payload.get("suggested_test_name") or "").strip()
            if cleaned["signal"]:
                items.append(cleaned)
        return items

    quiet_control_verdict = _summary_value(family_summary, "quiet_control_verdict")
    quiet_control_payload = dict(quiet_control_verdict) if isinstance(quiet_control_verdict, dict) else {}

    robust_signals = _extract_items("robust_signals")
    script_specific_signals = _extract_items("script_specific_signals")
    robust_backlog_candidates = _extract_items("robust_backlog_candidates")

    if not robust_signals and not script_specific_signals and not robust_backlog_candidates and not quiet_control_payload:
        return None

    summary = {
        "target_seam": target_seam,
        "seam_label": _seam_label(target_seam),
        "robust_signals": robust_signals,
        "script_specific_signals": script_specific_signals,
        "robust_backlog_candidates": robust_backlog_candidates,
        "quiet_control_verdict": {
            "quiet_control": bool(quiet_control_payload.get("quiet_control", False)),
            "status": str(quiet_control_payload.get("status") or "").strip(),
        },
    }
    if target_seam.startswith("session_fact_recall"):
        summary["ownership_focus"] = "session_fact_recall"
    if str(quiet_control_payload.get("reason") or "").strip():
        summary["quiet_control_verdict"]["reason"] = str(quiet_control_payload.get("reason") or "").strip()
    return summary