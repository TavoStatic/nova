from __future__ import annotations

import json
import time
from pathlib import Path

from services.runtime_timeline import RUNTIME_TIMELINE_SERVICE


class RuntimeAnalyticsService:
    """Own the restart analytics payload computation.

    Extracted from nova_http shell per shell-thin-slice contract.
    Owner: services/runtime_analytics.py
    Anti-drift: nova_http._runtime_restart_analytics_payload must delegate here.
    """

    def restart_analytics_payload(
        self,
        *,
        boot_history_path: Path,
        now: int | None = None,
    ) -> dict:
        """Build the runtime restart analytics payload from guard boot history."""
        _now = int(now) if now is not None else int(time.time())

        payload: dict = {
            "ok": True,
            "count": 0,
            "success_count": 0,
            "failure_count": 0,
            "recent_restart_count_15m": 0,
            "recent_restart_count_1h": 0,
            "recent_restart_count_24h": 0,
            "consecutive_failures": 0,
            "avg_success_boot_sec": 0.0,
            "latest_outcome": "unknown",
            "latest_reason": "",
            "last_success_ts": 0,
            "last_failure_ts": 0,
            "last_success_age_sec": None,
            "last_failure_age_sec": None,
            "flap_level": "info",
            "flap_summary": "No guard boot history recorded yet.",
            "recent_outcomes": [],
        }

        if not boot_history_path.exists():
            return payload

        try:
            raw = json.loads(boot_history_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                **payload,
                "ok": False,
                "flap_level": "danger",
                "flap_summary": f"Unable to read guard boot history: {exc}",
            }

        entries = [dict(item) for item in list(raw or []) if isinstance(item, dict)]
        if not entries:
            return payload

        _coerce = RUNTIME_TIMELINE_SERVICE.coerce_epoch_seconds
        entries.sort(
            key=lambda item: (_coerce(item.get("ts")) or 0, float(item.get("total_observed_s") or 0.0))
        )
        success_entries = [item for item in entries if bool(item.get("success"))]
        failure_entries = [item for item in entries if not bool(item.get("success"))]
        last_success = next((item for item in reversed(entries) if bool(item.get("success"))), None)
        last_failure = next((item for item in reversed(entries) if not bool(item.get("success"))), None)
        latest = entries[-1]
        latest_outcome = "success" if bool(latest.get("success")) else "failure"
        latest_reason = str(latest.get("reason") or ("running" if bool(latest.get("success")) else "unknown")).strip()

        consecutive_failures = 0
        for item in reversed(entries):
            if bool(item.get("success")):
                break
            consecutive_failures += 1

        def _count_since(window_seconds: int) -> int:
            cutoff = _now - max(1, int(window_seconds))
            return sum(1 for item in entries if (_coerce(item.get("ts")) or 0) >= cutoff)

        success_durations = [
            float(item.get("total_observed_s") or 0.0)
            for item in success_entries
            if float(item.get("total_observed_s") or 0.0) > 0
        ]
        recent_tail = entries[-6:]
        recent_failures = sum(1 for item in recent_tail if not bool(item.get("success")))

        flap_level = "good"
        if consecutive_failures >= 3 or _count_since(900) >= 4 or recent_failures >= 4:
            flap_level = "danger"
        elif consecutive_failures >= 1 or _count_since(3600) >= 3 or recent_failures >= 2:
            flap_level = "warn"

        if flap_level == "danger":
            flap_summary = (
                f"Restart instability detected: {consecutive_failures} consecutive failure(s), "
                f"{_count_since(900)} restart(s) in the last 15m, latest reason={latest_reason or 'unknown'}."
            )
        elif flap_level == "warn":
            flap_summary = (
                f"Runtime restart pressure is elevated: {consecutive_failures} consecutive failure(s) and "
                f"{_count_since(3600)} restart(s) in the last hour."
            )
        else:
            flap_summary = "Guard restart behavior looks stable over the recent boot history."

        return {
            **payload,
            "count": len(entries),
            "success_count": len(success_entries),
            "failure_count": len(failure_entries),
            "recent_restart_count_15m": _count_since(900),
            "recent_restart_count_1h": _count_since(3600),
            "recent_restart_count_24h": _count_since(86400),
            "consecutive_failures": consecutive_failures,
            "avg_success_boot_sec": (
                round(sum(success_durations) / len(success_durations), 1) if success_durations else 0.0
            ),
            "latest_outcome": latest_outcome,
            "latest_reason": latest_reason,
            "last_success_ts": int(_coerce((last_success or {}).get("ts")) or 0),
            "last_failure_ts": int(_coerce((last_failure or {}).get("ts")) or 0),
            "last_success_age_sec": (
                (_now - int(_coerce((last_success or {}).get("ts")) or 0)) if last_success else None
            ),
            "last_failure_age_sec": (
                (_now - int(_coerce((last_failure or {}).get("ts")) or 0)) if last_failure else None
            ),
            "flap_level": flap_level,
            "flap_summary": flap_summary,
            "recent_outcomes": [
                {
                    "ts": int(_coerce(item.get("ts")) or 0),
                    "outcome": "success" if bool(item.get("success")) else "failure",
                    "reason": str(item.get("reason") or ""),
                    "observed_sec": float(item.get("total_observed_s") or 0.0),
                }
                for item in reversed(recent_tail)
            ],
        }


RUNTIME_ANALYTICS_SERVICE = RuntimeAnalyticsService()
