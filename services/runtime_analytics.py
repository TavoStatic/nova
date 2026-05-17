from __future__ import annotations

import json
import re
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
        guard_log_path: Path | None = None,
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
            "pressure_restart_count_15m": 0,
            "pressure_restart_count_1h": 0,
            "pressure_restart_count_24h": 0,
            "planned_restart_count_1h": 0,
            "restart_origin_gap_count_1h": 0,
            "restart_origin_active_gap_count_1h": 0,
            "restart_origin_legacy_gap_count_1h": 0,
            "restart_pressure_active": False,
            "restart_provenance_status": "unknown",
            "restart_provenance_summary": "No guard boot history recorded yet.",
            "latest_restart_origin": "unknown",
            "latest_restart_action": "unknown",
            "latest_restart_cause_reason": "",
            "latest_restart_planned": False,
            "heartbeat_stale_restart_count_15m": 0,
            "heartbeat_stale_restart_count_1h": 0,
            "heartbeat_stale_restart_count_24h": 0,
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

        def _failure_events_from_guard_log(path: Path | None) -> list[dict]:
            if path is None or not Path(path).exists():
                return []
            events: list[dict] = []
            try:
                lines = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                return []
            for line in lines:
                match = re.match(
                    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| .*Core attempt failed:\s*(.+?)\s*$",
                    str(line or "").strip(),
                )
                if not match:
                    continue
                stamp_text, reason = match.groups()
                try:
                    ts_value = int(time.mktime(time.strptime(stamp_text, "%Y-%m-%d %H:%M:%S")))
                except Exception:
                    continue
                events.append({"ts": ts_value, "reason": str(reason or "").strip()})
            return events

        failure_events = _failure_events_from_guard_log(guard_log_path)

        def _entry_origin(item: dict) -> str:
            return str(item.get("restart_origin") or "").strip().lower()

        def _entry_action(item: dict) -> str:
            action = str(item.get("restart_action") or item.get("start_reason") or "").strip().lower()
            start_reason = str(item.get("start_reason") or "").strip().lower()
            if action == "guard_stop" and start_reason == "initial_start" and bool(item.get("success")):
                return "guard_restart_after_stop"
            return action

        def _entry_planned(item: dict) -> bool:
            if isinstance(item.get("planned_restart"), bool):
                return bool(item.get("planned_restart"))
            intent = item.get("restart_intent") if isinstance(item.get("restart_intent"), dict) else {}
            if isinstance(intent.get("planned"), bool):
                return bool(intent.get("planned"))
            return False

        def _entry_provenance_complete(item: dict) -> bool:
            if isinstance(item.get("provenance_complete"), bool):
                return bool(item.get("provenance_complete"))
            if _entry_planned(item):
                return True
            origin = _entry_origin(item)
            if origin in {"guard_supervisor"}:
                return True
            return False

        def _entry_restart_cause_reason(item: dict) -> str:
            explicit = str(
                item.get("restart_cause_reason")
                or item.get("restart_failure_reason")
                or item.get("previous_failure_reason")
                or ""
            ).strip()
            if explicit:
                return explicit
            if _entry_origin(item) != "guard_supervisor" and _entry_action(item) != "supervised_restart":
                return ""
            entry_ts = int(_coerce(item.get("ts")) or 0)
            if entry_ts <= 0:
                return ""
            candidates = [
                event
                for event in failure_events
                if 0 < int(event.get("ts") or 0) <= entry_ts and (entry_ts - int(event.get("ts") or 0)) <= 1800
            ]
            if not candidates:
                return ""
            return str(candidates[-1].get("reason") or "").strip()

        def _entry_is_pressure(item: dict) -> bool:
            if not bool(item.get("success")):
                return True
            if _entry_planned(item):
                return False
            origin = _entry_origin(item)
            action = _entry_action(item)
            if origin == "guard_supervisor" or action == "supervised_restart":
                return True
            return False

        consecutive_failures = 0
        for item in reversed(entries):
            if bool(item.get("success")):
                break
            consecutive_failures += 1

        def _count_since(window_seconds: int) -> int:
            cutoff = _now - max(1, int(window_seconds))
            return sum(1 for item in entries if (_coerce(item.get("ts")) or 0) >= cutoff)

        def _count_matching_since(window_seconds: int, predicate) -> int:
            cutoff = _now - max(1, int(window_seconds))
            return sum(
                1
                for item in entries
                if (_coerce(item.get("ts")) or 0) >= cutoff and predicate(item)
            )

        success_durations = [
            float(item.get("total_observed_s") or 0.0)
            for item in success_entries
            if float(item.get("total_observed_s") or 0.0) > 0
        ]
        recent_tail = entries[-6:]
        recent_failures = sum(1 for item in recent_tail if not bool(item.get("success")))
        pressure_count_15m = _count_matching_since(900, _entry_is_pressure)
        pressure_count_1h = _count_matching_since(3600, _entry_is_pressure)
        pressure_count_24h = _count_matching_since(86400, _entry_is_pressure)
        heartbeat_stale_count_15m = _count_matching_since(
            900,
            lambda item: _entry_restart_cause_reason(item) == "heartbeat_stale",
        )
        heartbeat_stale_count_1h = _count_matching_since(
            3600,
            lambda item: _entry_restart_cause_reason(item) == "heartbeat_stale",
        )
        heartbeat_stale_count_24h = _count_matching_since(
            86400,
            lambda item: _entry_restart_cause_reason(item) == "heartbeat_stale",
        )
        planned_count_1h = _count_matching_since(3600, _entry_planned)
        one_hour_cutoff = _now - 3600
        recent_1h_entries = [item for item in entries if (_coerce(item.get("ts")) or 0) >= one_hour_cutoff]
        provenance_gap_entries_1h = [item for item in recent_1h_entries if not _entry_provenance_complete(item)]
        complete_provenance_entries_1h = [item for item in recent_1h_entries if _entry_provenance_complete(item)]
        last_complete_provenance_ts = max(
            [int(_coerce(item.get("ts")) or 0) for item in complete_provenance_entries_1h] or [0]
        )
        provenance_gap_count_1h = len(provenance_gap_entries_1h)
        active_provenance_gap_count_1h = sum(
            1
            for item in provenance_gap_entries_1h
            if last_complete_provenance_ts <= 0 or int(_coerce(item.get("ts")) or 0) > last_complete_provenance_ts
        )
        legacy_provenance_gap_count_1h = max(0, provenance_gap_count_1h - active_provenance_gap_count_1h)

        flap_level = "good"
        if consecutive_failures >= 3 or pressure_count_15m >= 4 or heartbeat_stale_count_15m >= 3 or recent_failures >= 4:
            flap_level = "danger"
        elif consecutive_failures >= 1 or pressure_count_1h >= 3 or heartbeat_stale_count_1h >= 2 or recent_failures >= 2:
            flap_level = "warn"

        if flap_level == "danger":
            flap_summary = (
                f"Restart instability detected: {consecutive_failures} consecutive failure(s), "
                f"{pressure_count_15m} pressure restart(s) in the last 15m, "
                f"{heartbeat_stale_count_15m} heartbeat-stale restart(s) in the last 15m, "
                f"latest reason={latest_reason or 'unknown'}."
            )
        elif flap_level == "warn":
            if heartbeat_stale_count_1h >= 2:
                flap_summary = (
                    f"Runtime heartbeat restart pressure is elevated: {heartbeat_stale_count_1h} heartbeat-stale "
                    f"supervised restart(s) and {pressure_count_1h} pressure restart(s) in the last hour."
                )
            else:
                flap_summary = (
                    f"Runtime restart pressure is elevated: {consecutive_failures} consecutive failure(s) and "
                    f"{pressure_count_1h} pressure restart(s) in the last hour."
                )
        elif active_provenance_gap_count_1h > 0:
            flap_summary = (
                f"No failure-driven restart pressure is active; {active_provenance_gap_count_1h} recent boot(s) "
                "are missing restart provenance."
            )
        elif legacy_provenance_gap_count_1h > 0:
            flap_summary = (
                "No failure-driven restart pressure is active; current boot provenance is attributed, "
                f"with {legacy_provenance_gap_count_1h} older boot(s) still missing provenance in the one-hour window."
            )
        else:
            flap_summary = "Guard restart behavior looks stable over the recent boot history."

        latest_origin = _entry_origin(latest) or "unknown"
        latest_action = _entry_action(latest) or "unknown"
        latest_cause = _entry_restart_cause_reason(latest)
        if active_provenance_gap_count_1h > 0:
            restart_provenance_status = "incomplete"
            restart_provenance_summary = f"{active_provenance_gap_count_1h} recent boot(s) are missing restart origin."
        elif legacy_provenance_gap_count_1h > 0:
            restart_provenance_status = "legacy_incomplete"
            restart_provenance_summary = (
                f"{legacy_provenance_gap_count_1h} older boot(s) in the one-hour window predate current provenance attribution."
            )
        else:
            restart_provenance_status = "complete"
            restart_provenance_summary = "Recent restart origins are attributed."

        return {
            **payload,
            "count": len(entries),
            "success_count": len(success_entries),
            "failure_count": len(failure_entries),
            "recent_restart_count_15m": _count_since(900),
            "recent_restart_count_1h": _count_since(3600),
            "recent_restart_count_24h": _count_since(86400),
            "pressure_restart_count_15m": pressure_count_15m,
            "pressure_restart_count_1h": pressure_count_1h,
            "pressure_restart_count_24h": pressure_count_24h,
            "planned_restart_count_1h": planned_count_1h,
            "restart_origin_gap_count_1h": provenance_gap_count_1h,
            "restart_origin_active_gap_count_1h": active_provenance_gap_count_1h,
            "restart_origin_legacy_gap_count_1h": legacy_provenance_gap_count_1h,
            "restart_pressure_active": flap_level in {"warn", "danger"},
            "restart_provenance_status": restart_provenance_status,
            "restart_provenance_summary": restart_provenance_summary,
            "latest_restart_origin": latest_origin,
            "latest_restart_action": latest_action,
            "latest_restart_cause_reason": latest_cause,
            "latest_restart_planned": _entry_planned(latest),
            "heartbeat_stale_restart_count_15m": heartbeat_stale_count_15m,
            "heartbeat_stale_restart_count_1h": heartbeat_stale_count_1h,
            "heartbeat_stale_restart_count_24h": heartbeat_stale_count_24h,
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
                    "origin": _entry_origin(item) or "unknown",
                    "action": _entry_action(item) or "unknown",
                    "restart_cause_reason": _entry_restart_cause_reason(item),
                    "planned": _entry_planned(item),
                    "provenance_complete": _entry_provenance_complete(item),
                    "observed_sec": float(item.get("total_observed_s") or 0.0),
                }
                for item in reversed(recent_tail)
            ],
        }


RUNTIME_ANALYTICS_SERVICE = RuntimeAnalyticsService()
