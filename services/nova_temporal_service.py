from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _normalize_signal(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        number = float(value)
    except Exception:
        return 0.0
    if number > 1.0:
        number /= 100.0
    return _clamp(number)


def _serialize_dt(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        return value.isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    # Normalize compact ICS format YYYYMMDDTHHmmss[Z] → ISO with separators
    if len(text) >= 15 and "T" in text and "-" not in text[:8]:
        date_part, time_part = text.split("T", 1)
        if len(date_part) == 8 and date_part.isdigit():
            date_iso = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
            t = time_part.rstrip("Z")
            if len(t) >= 6:
                time_iso = f"{t[:2]}:{t[2:4]}:{t[4:6]}"
                tz_iso = "+00:00" if time_part.endswith("Z") else ""
                text = f"{date_iso}T{time_iso}{tz_iso}"
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _confidence_to_score(label: str) -> float:
    normalized = (label or "").strip().lower()
    if normalized in {"confirmed", "certain", "definite"}:
        return 1.0
    if normalized in {"tentative", "possible", "maybe"}:
        return 0.4
    if normalized in {"cancelled", "cancelled?", "declined"}:
        return 0.0
    return 0.6


@dataclass(frozen=True)
class TemporalEvent:
    source: str
    title: str
    start: datetime | None = None
    end: datetime | None = None
    timezone: str = ""
    confidence: str = "tentative"
    importance: float = 0.0
    dependency_risk: float = 0.0
    stale_evidence: float = 0.0
    operator_context: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, source: str = "ics") -> "TemporalEvent":
        data = dict(payload or {})
        return cls(
            source=str(data.get("source") or source or "ics"),
            title=str(data.get("title") or data.get("summary") or "Untitled event").strip(),
            start=_parse_datetime(data.get("start") or data.get("dtstart")),
            end=_parse_datetime(data.get("end") or data.get("dtend")),
            timezone=str(data.get("timezone") or data.get("tzid") or "").strip(),
            confidence=str(data.get("confidence") or data.get("status") or "tentative").strip(),
            importance=_normalize_signal(data.get("importance")),
            dependency_risk=_normalize_signal(data.get("dependency_risk")),
            stale_evidence=_normalize_signal(data.get("stale_evidence")),
            operator_context=_normalize_signal(data.get("operator_context")),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "start": _serialize_dt(self.start),
            "end": _serialize_dt(self.end),
            "timezone": self.timezone,
            "confidence": self.confidence,
            "importance": round(_clamp(self.importance), 4),
            "dependency_risk": round(_clamp(self.dependency_risk), 4),
            "stale_evidence": round(_clamp(self.stale_evidence), 4),
            "operator_context": round(_clamp(self.operator_context), 4),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TemporalPressure:
    event: TemporalEvent
    days_until_start: float | None
    proximity_band: str
    proximity_score: float
    importance_score: float
    dependency_risk_score: float
    stale_evidence_score: float
    operator_context_score: float
    confidence_score: float
    final_score: float
    output_path: str
    recommended_action: str
    explanation: str
    signals: dict[str, float] = field(default_factory=dict)

    @staticmethod
    def _proximity_band_and_score(days_until_start: float | None) -> tuple[str, float]:
        if days_until_start is None:
            return "background awareness", 0.10
        if days_until_start < 0:
            return "overdue", 1.00
        if days_until_start <= 1:
            return "immediate", 0.95
        if days_until_start <= 3:
            return "priority work-tree pressure", 0.82
        if days_until_start <= 7:
            return "active preparation", 0.65
        if days_until_start <= 14:
            return "planning visible", 0.45
        if days_until_start <= 30:
            return "quiet tracking", 0.25
        return "background awareness", 0.10

    @staticmethod
    def _choose_output_path(final_score: float, proximity_band: str) -> tuple[str, str]:
        if proximity_band in {"overdue", "immediate", "priority work-tree pressure"} or final_score >= 75.0:
            return "work_tree", "surface_to_work_tree"
        if proximity_band in {"active preparation", "planning visible"} or final_score >= 45.0:
            return "outbox", "route_to_operator_outbox"
        return "scheduled_job", "keep_silent_scheduled_job"

    @classmethod
    def from_event(cls, event: TemporalEvent, *, now: datetime | None = None) -> "TemporalPressure":
        anchor = now or _utc_now()
        start = event.start
        days_until_start: float | None = None
        if start is not None:
            try:
                current = anchor
                if current.tzinfo is None and start.tzinfo is not None:
                    current = current.replace(tzinfo=start.tzinfo)
                if current.tzinfo is not None and start.tzinfo is None:
                    start = start.replace(tzinfo=current.tzinfo)
                delta = start - current
                days_until_start = delta.total_seconds() / 86400.0
            except Exception:
                days_until_start = None

        proximity_band, proximity_score = cls._proximity_band_and_score(days_until_start)
        importance_score = _clamp(event.importance)
        dependency_risk_score = _clamp(event.dependency_risk)
        stale_evidence_score = _clamp(event.stale_evidence)
        operator_context_score = _clamp(event.operator_context)
        confidence_score = _clamp(_confidence_to_score(event.confidence))

        weighted = (
            proximity_score * 0.40
            + importance_score * 0.20
            + dependency_risk_score * 0.15
            + stale_evidence_score * 0.15
            + operator_context_score * 0.10
        )
        weighted = weighted * (0.80 + (confidence_score * 0.20))
        final_score = round(_clamp(weighted) * 100.0, 1)
        output_path, recommended_action = cls._choose_output_path(final_score, proximity_band)
        explanation = (
            f"{event.title}: {proximity_band} ({final_score:.1f}/100)"
            if event.title
            else f"{proximity_band} ({final_score:.1f}/100)"
        )

        return cls(
            event=event,
            days_until_start=days_until_start,
            proximity_band=proximity_band,
            proximity_score=round(proximity_score, 4),
            importance_score=round(importance_score, 4),
            dependency_risk_score=round(dependency_risk_score, 4),
            stale_evidence_score=round(stale_evidence_score, 4),
            operator_context_score=round(operator_context_score, 4),
            confidence_score=round(confidence_score, 4),
            final_score=final_score,
            output_path=output_path,
            recommended_action=recommended_action,
            explanation=explanation,
            signals={
                "proximity_score": round(proximity_score, 4),
                "importance_score": round(importance_score, 4),
                "dependency_risk_score": round(dependency_risk_score, 4),
                "stale_evidence_score": round(stale_evidence_score, 4),
                "operator_context_score": round(operator_context_score, 4),
                "confidence_score": round(confidence_score, 4),
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.to_dict(),
            "days_until_start": self.days_until_start,
            "proximity_band": self.proximity_band,
            "proximity_score": self.proximity_score,
            "importance_score": self.importance_score,
            "dependency_risk_score": self.dependency_risk_score,
            "stale_evidence_score": self.stale_evidence_score,
            "operator_context_score": self.operator_context_score,
            "confidence_score": self.confidence_score,
            "final_score": self.final_score,
            "output_path": self.output_path,
            "recommended_action": self.recommended_action,
            "explanation": self.explanation,
            "signals": dict(self.signals),
        }


class NovaTemporalService:
    """Nova-specific time reasoning: convert events into action pressure."""

    def __init__(self, *, work_tree_threshold: float = 75.0, outbox_threshold: float = 45.0) -> None:
        self.work_tree_threshold = float(work_tree_threshold)
        self.outbox_threshold = float(outbox_threshold)

    def assess(self, event: TemporalEvent, *, now: datetime | None = None) -> TemporalPressure:
        pressure = TemporalPressure.from_event(event, now=now)
        if pressure.final_score >= self.work_tree_threshold:
            return pressure
        if pressure.final_score >= self.outbox_threshold and pressure.output_path == "scheduled_job":
            return dataclasses.replace(
                pressure,
                output_path="outbox",
                recommended_action="route_to_operator_outbox",
                explanation=f"{pressure.explanation} -> operator review",
            )
        return pressure

    def assess_many(self, events: list[TemporalEvent], *, now: datetime | None = None) -> list[TemporalPressure]:
        return [self.assess(event, now=now) for event in list(events or [])]

    def route_pressure(self, pressure: TemporalPressure) -> dict[str, Any]:
        if pressure.output_path == "work_tree":
            return self.build_work_tree_item(pressure)
        if pressure.output_path == "outbox":
            return self.build_outbox_message(pressure)
        return self.build_silent_job(pressure)

    def build_work_tree_item(self, pressure: TemporalPressure) -> dict[str, Any]:
        event = pressure.event
        return {
            "kind": "work_tree",
            "title": event.title,
            "source": event.source,
            "due_at": _serialize_dt(event.start),
            "score": pressure.final_score,
            "pressure": pressure.to_dict(),
            "recommended_tool": "temporal_review",
            "reason": pressure.explanation,
        }

    def build_outbox_message(self, pressure: TemporalPressure) -> dict[str, Any]:
        event = pressure.event
        return {
            "kind": "operator_outbox",
            "title": event.title,
            "source": event.source,
            "due_at": _serialize_dt(event.start),
            "score": pressure.final_score,
            "pressure": pressure.to_dict(),
            "message": pressure.explanation,
        }

    def build_silent_job(self, pressure: TemporalPressure) -> dict[str, Any]:
        event = pressure.event
        return {
            "kind": "scheduled_job",
            "title": event.title,
            "source": event.source,
            "run_at": _serialize_dt(event.start),
            "score": pressure.final_score,
            "pressure": pressure.to_dict(),
            "message": pressure.explanation,
        }


def build_temporal_pressure(event_like: dict[str, Any] | TemporalEvent, *, now: datetime | None = None) -> TemporalPressure:
    event = event_like if isinstance(event_like, TemporalEvent) else TemporalEvent.from_payload(dict(event_like or {}))
    return TemporalPressure.from_event(event, now=now)
