"""
Session state management service.
Consolidates fulfillment state and subconscious state handling.
"""
from dataclasses import dataclass, field
from typing import Optional

from subconscious_route_probe import analyze_route_pressure


@dataclass(slots=True)
class SubconsciousState:
    """Subconscious state tracking for session."""
    replan_requested: bool = False
    crack_counts: dict[str, int] = field(default_factory=dict)
    recent_pressure_records: list[object] = field(default_factory=list)
    weak_signal_window_counts: dict[str, int] = field(default_factory=dict)
    replan_reasons: list[dict[str, object]] = field(default_factory=list)


class SessionStateService:
    """Manage session fulfillment and subconscious state."""

    @staticmethod
    def _recent_signal_counts(records: list[object]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in list(records or []):
            for signal in list(getattr(record, "signals", []) or []):
                cleaned = str(signal or "").strip()
                if cleaned:
                    counts[cleaned] = int(counts.get(cleaned, 0)) + 1
        return counts

    @staticmethod
    def _weak_signal_thresholds(subconscious_charter: dict, weak_crack_signals: set[str]) -> dict[str, int]:
        crack_rules = subconscious_charter.get("crack_accumulation_rules") or {}
        default_threshold = max(1, int(crack_rules.get("weak_crack_repeat_threshold", 2) or 2))
        configured = crack_rules.get("weak_crack_repeat_thresholds") if isinstance(crack_rules.get("weak_crack_repeat_thresholds"), dict) else {}
        thresholds: dict[str, int] = {}
        for signal in sorted(weak_crack_signals):
            try:
                thresholds[signal] = max(1, int(configured.get(signal, default_threshold) or default_threshold))
            except Exception:
                thresholds[signal] = default_threshold
        return thresholds

    @staticmethod
    def get_subconscious_pressure_config(subconscious_charter: dict, max_pressure_records: int) -> dict:
        signal_rules = subconscious_charter.get("signal_handling_rules") or {}
        weak_crack_signals = {
            str(signal).strip()
            for signal in list(signal_rules.get("weak_crack_signals") or [])
            if str(signal).strip()
        }
        crack_rules = subconscious_charter.get("crack_accumulation_rules") or {}
        return {
            "recent_pressure_window_cap": max(1, int(max_pressure_records or 1)),
            "weak_crack_repeat_threshold": max(1, int(crack_rules.get("weak_crack_repeat_threshold", 2) or 2)),
            "weak_signal_thresholds": SessionStateService._weak_signal_thresholds(
                subconscious_charter,
                weak_crack_signals,
            ),
        }

    @staticmethod
    def get_fulfillment_state(session: object) -> Optional[dict]:
        """Get fulfillment state from session."""
        state = getattr(session, "fulfillment_state", None)
        return state if isinstance(state, dict) else None

    @staticmethod
    def set_fulfillment_state(session: object, state: Optional[dict]) -> None:
        """Set fulfillment state on session."""
        try:
            setattr(session, "fulfillment_state", state if isinstance(state, dict) else None)
        except Exception:
            pass

    @staticmethod
    def get_subconscious_state(session: object) -> Optional[SubconsciousState]:
        """Get subconscious state from session."""
        state = getattr(session, "subconscious_state", None)
        return state if isinstance(state, SubconsciousState) else None

    @staticmethod
    def set_subconscious_state(session: object, state: Optional[SubconsciousState]) -> None:
        """Set subconscious state on session."""
        try:
            setattr(session, "subconscious_state", state if isinstance(state, SubconsciousState) else None)
        except Exception:
            pass

    @staticmethod
    def get_subconscious_snapshot(session: object, subconscious_charter: dict, max_pressure_records: int) -> dict:
        """Build snapshot of subconscious state for inspection/monitoring."""
        state = SessionStateService.get_subconscious_state(session)
        if state is None:
            return {
                "replan_requested": False,
                "replan_reasons": [],
                "active_recent_signals": [],
                "crack_counts": {},
                "weak_signal_window_counts": {},
                "recent_pressure_records": [],
                "record_window": {"count": 0, "cap": max_pressure_records},
            }

        recent_records = list(state.recent_pressure_records or [])
        recent_summaries = []
        active_recent_signals: list[str] = []
        for record in recent_records[-3:]:
            signals = [str(signal).strip() for signal in list(getattr(record, "signals", []) or []) if str(signal).strip()]
            for signal in signals:
                if signal not in active_recent_signals:
                    active_recent_signals.append(signal)
            recent_summaries.append(
                {
                    "chosen_route": str(getattr(record, "chosen_route", "") or "") or None,
                    "comparison_strength": str(getattr(record, "comparison_strength", "") or "").strip().lower() or "weak",
                    "signals": list(signals),
                    "weak_spots": [
                        str(item).strip()
                        for item in list(getattr(record, "weak_spots", []) or [])
                        if str(item).strip()
                    ],
                }
            )

        return {
            "replan_requested": bool(state.replan_requested),
            "replan_reasons": [dict(item) for item in list(state.replan_reasons or []) if isinstance(item, dict)],
            "active_recent_signals": active_recent_signals,
            "crack_counts": {str(key): int(value) for key, value in dict(state.crack_counts or {}).items()},
            "weak_signal_window_counts": {str(key): int(value) for key, value in dict(state.weak_signal_window_counts or {}).items()},
            "recent_pressure_records": recent_summaries,
            "record_window": {
                "count": len(recent_records),
                "cap": max_pressure_records,
            },
        }

    @staticmethod
    def update_subconscious_state(
        session: object,
        probe_result: dict,
        subconscious_charter: dict,
        max_pressure_records: int,
        *,
        chosen_route: Optional[str] = None,
    ) -> Optional[SubconsciousState]:
        """Update subconscious state with new probe result."""
        if not isinstance(probe_result, dict):
            return None

        existing_state = SessionStateService.get_subconscious_state(session)
        state = existing_state if existing_state else SubconsciousState()
        record = analyze_route_pressure(probe_result, chosen_route=chosen_route)

        for signal in list(record.signals or []):
            cleaned = str(signal or "").strip()
            if cleaned:
                state.crack_counts[cleaned] = int(state.crack_counts.get(cleaned, 0)) + 1

        state.recent_pressure_records.append(record)
        if len(state.recent_pressure_records) > max_pressure_records:
            state.recent_pressure_records = state.recent_pressure_records[-max_pressure_records:]

        immediate_signals = set(subconscious_charter["signal_handling_rules"]["replan_immediate_signals"])
        weak_crack_signals = set(subconscious_charter["signal_handling_rules"]["weak_crack_signals"])
        recent_signal_counts = SessionStateService._recent_signal_counts(state.recent_pressure_records)
        weak_signal_thresholds = SessionStateService._weak_signal_thresholds(subconscious_charter, weak_crack_signals)
        state.weak_signal_window_counts = {
            signal: int(recent_signal_counts.get(signal, 0))
            for signal in sorted(weak_crack_signals)
            if int(recent_signal_counts.get(signal, 0)) > 0
        }

        immediate_reasons = [
            {
                "kind": "immediate_signal",
                "signal": signal,
            }
            for signal in list(record.signals or [])
            if signal in immediate_signals
        ]
        weak_reasons = [
            {
                "kind": "weak_signal_threshold",
                "signal": signal,
                "window_count": int(recent_signal_counts.get(signal, 0)),
                "threshold": int(weak_signal_thresholds.get(signal, 1)),
            }
            for signal in sorted(weak_crack_signals)
            if int(recent_signal_counts.get(signal, 0)) >= int(weak_signal_thresholds.get(signal, 1))
        ]

        state.replan_reasons = immediate_reasons + weak_reasons
        state.replan_requested = bool(state.replan_reasons)

        SessionStateService.set_subconscious_state(session, state)
        return state
