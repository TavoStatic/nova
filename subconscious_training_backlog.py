"""Read-only training backlog generation from subconscious route pressure.

This module consumes the existing subconscious snapshot shape and turns repeated
or active route crack patterns into candidate regression tests. It does not
route turns, mutate session state, or create any new controller behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from subconscious_config import SUBCONSCIOUS_CHARTER


_IMMEDIATE_PRIORITY_SIGNALS = set(SUBCONSCIOUS_CHARTER["training_backlog_generation_rules"]["immediate_priority_signals"])
_SIGNAL_TEMPLATES = dict(SUBCONSCIOUS_CHARTER["training_backlog_generation_rules"]["signal_templates"])


@dataclass(slots=True)
class TrainingBacklogItem:
    signal: str
    occurrences: int
    priority: str
    title: str
    suggested_test_name: str
    rationale: str


@dataclass(slots=True)
class TrainingBacklog:
    replan_requested: bool
    active_recent_signals: list[str] = field(default_factory=list)
    record_window: dict[str, int] = field(default_factory=dict)
    candidate_tests: list[TrainingBacklogItem] = field(default_factory=list)
    deferred_signals: list[str] = field(default_factory=list)


def _clean_signal_list(values: Any) -> list[str]:
    cleaned: list[str] = []
    for value in list(values or []):
        signal = str(value or "").strip()
        if signal and signal not in cleaned:
            cleaned.append(signal)
    return cleaned


def _clean_crack_counts(values: Any) -> dict[str, int]:
    cleaned: dict[str, int] = {}
    if not isinstance(values, Mapping):
        return cleaned
    for key, value in values.items():
        signal = str(key or "").strip()
        if not signal:
            continue
        try:
            count = max(0, int(value))
        except Exception:
            continue
        if count > 0:
            cleaned[signal] = count
    return cleaned


def _clean_record_window(values: Any) -> dict[str, int]:
    payload = values if isinstance(values, Mapping) else {}
    try:
        count = max(0, int(payload.get("count", 0) or 0))
    except Exception:
        count = 0
    try:
        cap = max(0, int(payload.get("cap", 0) or 0))
    except Exception:
        cap = 0
    return {"count": count, "cap": cap}


def _priority_for(signal: str, occurrences: int, *, active: bool, replan_requested: bool) -> str:
    if signal in _IMMEDIATE_PRIORITY_SIGNALS and active and replan_requested:
        return "high"
    if occurrences >= 3 or (occurrences >= 2 and active):
        return "high"
    if occurrences >= 2 or (active and replan_requested):
        return "medium"
    return "low"


def build_training_backlog(subconscious_snapshot: Mapping[str, Any]) -> TrainingBacklog:
    active_recent_signals = _clean_signal_list(subconscious_snapshot.get("active_recent_signals"))
    crack_counts = _clean_crack_counts(subconscious_snapshot.get("crack_counts"))
    record_window = _clean_record_window(subconscious_snapshot.get("record_window"))
    replan_requested = bool(subconscious_snapshot.get("replan_requested"))

    candidate_tests: list[TrainingBacklogItem] = []
    deferred_signals: list[str] = []

    ranked_signals = sorted(crack_counts.items(), key=lambda item: (-item[1], item[0]))
    for signal, occurrences in ranked_signals:
        active = signal in active_recent_signals
        if occurrences < 2 and not (replan_requested and active):
            deferred_signals.append(signal)
            continue

        template = _SIGNAL_TEMPLATES.get(
            signal,
            {
                "title": f"Investigate {signal.replace('_', ' ')}",
                "suggested_test_name": f"test_route_pressure_{signal}",
                "rationale": "Repeated subconscious pressure indicates a route seam gap.",
            },
        )
        rationale_parts = [template["rationale"], f"Observed {occurrences} time(s) in recent crack counts."]
        if active:
            rationale_parts.append("The signal is still active in the latest pressure window.")
        if record_window.get("cap", 0) > 0:
            rationale_parts.append(
                f"Snapshot window currently holds {record_window.get('count', 0)} of {record_window.get('cap', 0)} recent pressure records."
            )
        candidate_tests.append(
            TrainingBacklogItem(
                signal=signal,
                occurrences=occurrences,
                priority=_priority_for(signal, occurrences, active=active, replan_requested=replan_requested),
                title=str(template["title"]),
                suggested_test_name=str(template["suggested_test_name"]),
                rationale=" ".join(rationale_parts),
            )
        )

    return TrainingBacklog(
        replan_requested=replan_requested,
        active_recent_signals=list(active_recent_signals),
        record_window=dict(record_window),
        candidate_tests=candidate_tests,
        deferred_signals=deferred_signals,
    )