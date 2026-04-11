from __future__ import annotations

import json
from pathlib import Path


def _seam_label(value: str) -> str:
    words = [part for part in str(value or "").split("_") if part]
    return " ".join(words)


class SubconsciousControlService:
    """Build subconscious control-room summaries outside the HTTP layer."""

    @staticmethod
    def latest_report(runs_root: Path) -> dict:
        latest_path = Path(runs_root) / "latest.json"
        if not latest_path.exists():
            return {}
        try:
            payload = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def status_summary(latest: dict, definitions: list[dict], latest_report_path: Path) -> dict:
        report = dict(latest or {}) if isinstance(latest, dict) else {}
        totals = report.get("totals") if isinstance(report.get("totals"), dict) else {}
        top_priorities: list[dict] = []
        for family in list(report.get("families") or []):
            if not isinstance(family, dict):
                continue
            for item in list(family.get("training_priorities") or []):
                if not isinstance(item, dict):
                    continue
                top_priorities.append(
                    {
                        "seam": str(item.get("seam") or family.get("target_seam") or "").strip(),
                        "seam_label": _seam_label(str(item.get("seam") or family.get("target_seam") or "").strip()),
                        "signal": str(item.get("signal") or "").strip(),
                        "urgency": str(item.get("urgency") or "").strip(),
                        "suggested_test_name": str(item.get("suggested_test_name") or "").strip(),
                        "robustness": float(item.get("robustness", 0.0) or 0.0),
                    }
                )
        top_priorities.sort(
            key=lambda item: (
                {"high": 0, "medium": 1, "low": 2, "deferred": 3}.get(item.get("urgency"), 4),
                -float(item.get("robustness", 0.0) or 0.0),
                str(item.get("signal") or ""),
            )
        )
        generated_defs = [item for item in list(definitions or []) if str(item.get("origin") or "") == "generated"]
        return {
            "ok": bool(report),
            "generated_at": str(report.get("generated_at") or ""),
            "label": str(report.get("label") or ""),
            "family_count": int(totals.get("family_count", 0) or 0),
            "variation_count": int(totals.get("variation_count", 0) or 0),
            "training_priority_count": int(totals.get("training_priority_count", 0) or 0),
            "generated_definition_count": len(generated_defs),
            "latest_report_path": str(Path(latest_report_path)),
            "top_priorities": top_priorities[:5],
        }

    @staticmethod
    def live_summary(
        *,
        limit: int,
        pressure_config: dict,
        session_turns_items: list[tuple[str, list[tuple[str, str]]]],
        session_owner_lookup,
        session_state_peek_fn,
        get_snapshot_fn,
    ) -> dict:
        tracked_sessions: list[dict] = []
        active_reason_counts: dict[str, int] = {}

        for session_id, turns in reversed(list(session_turns_items or [])):
            session = session_state_peek_fn(session_id)
            if session is None:
                continue
            snapshot = get_snapshot_fn(session)
            record_window = snapshot.get("record_window") if isinstance(snapshot.get("record_window"), dict) else {}
            if int(record_window.get("count", 0) or 0) <= 0:
                continue
            reasons = [dict(item) for item in list(snapshot.get("replan_reasons") or []) if isinstance(item, dict)]
            for item in reasons:
                signal = str(item.get("signal") or "").strip()
                if signal:
                    active_reason_counts[signal] = int(active_reason_counts.get(signal, 0)) + 1
            last_user = ""
            for role, text in reversed(list(turns or [])):
                if role == "user":
                    last_user = str(text or "").strip()[:120]
                    break
            tracked_sessions.append(
                {
                    "session_id": str(session_id or "").strip(),
                    "owner": str(session_owner_lookup.get(session_id) or "").strip() if hasattr(session_owner_lookup, "get") else "",
                    "turn_count": len(list(turns or [])),
                    "active_subject": session.active_subject() if hasattr(session, "active_subject") else "",
                    "replan_requested": bool(snapshot.get("replan_requested")),
                    "replan_reasons": reasons,
                    "active_recent_signals": list(snapshot.get("active_recent_signals") or []),
                    "weak_signal_window_counts": dict(snapshot.get("weak_signal_window_counts") or {}),
                    "last_user": last_user,
                    "record_window": {
                        "count": int(record_window.get("count", 0) or 0),
                        "cap": int(record_window.get("cap", pressure_config.get("recent_pressure_window_cap", 0)) or 0),
                    },
                }
            )

        tracked_sessions.sort(
            key=lambda item: (
                0 if item.get("replan_requested") else 1,
                -len(list(item.get("replan_reasons") or [])),
                -int(((item.get("record_window") or {}).get("count", 0) or 0)),
                str(item.get("session_id") or ""),
            )
        )
        limited_sessions = tracked_sessions[: max(1, int(limit))]
        return {
            "tracked_session_count": len(tracked_sessions),
            "replan_session_count": sum(1 for item in tracked_sessions if item.get("replan_requested")),
            "pressure_config": dict(pressure_config or {}),
            "active_reason_counts": active_reason_counts,
            "sessions": limited_sessions,
        }


SUBCONSCIOUS_CONTROL_SERVICE = SubconsciousControlService()