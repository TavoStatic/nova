"""Live cognitive workspace and bounded event stream for meta reasoning."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import threading
import time
from typing import Any

from services.nova_runtime_context import RUNTIME_DIR

MAX_COGNITIVE_EVENTS = 128


@dataclass(frozen=True)
class CognitiveEvent:
    event_id: str
    cycle: int
    event_type: str
    subject: str
    content: dict[str, Any] = field(default_factory=dict)
    origin: str = ""
    confidence: float = 0.0
    activation: float = 0.0
    parent_events: tuple[str, ...] = ()
    timestamp: float = 0.0


@dataclass
class CognitiveWorkspace:
    current_focus: str = ""
    active_goal: str = ""
    interpreted_condition: str = ""
    candidate_explanations: list[str] = field(default_factory=list)
    candidate_actions: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    predictions: list[dict[str, Any]] = field(default_factory=list)
    recalled_experiences: list[dict[str, Any]] = field(default_factory=list)
    emotional_equivalents: dict[str, float] = field(default_factory=dict)
    internal_conflicts: list[dict[str, Any]] = field(default_factory=list)
    active_reasoning_strategy: str = ""
    self_model: dict[str, Any] = field(default_factory=dict)
    cycle: int = 0
    updated_at: float = 0.0


_LOCK = threading.RLock()
_WORKSPACE = CognitiveWorkspace()
_EVENTS: list[CognitiveEvent] = []
_EVENT_SEQUENCE = 0


def _state_path() -> Path:
    return Path(RUNTIME_DIR) / "cognitive_workspace.json"


def _event_id(sequence: int) -> str:
    return f"ce_{sequence:08d}"


def _bounded_strings(values: Any, limit: int = 32) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    return [str(value or "").strip()[:240] for value in values[:limit] if str(value or "").strip()]


def _save_unlocked() -> None:
    try:
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "workspace": asdict(_WORKSPACE),
                    "events": [asdict(event) for event in _EVENTS[-MAX_COGNITIVE_EVENTS:]],
                },
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def _load_unlocked() -> None:
    global _EVENT_SEQUENCE
    if _EVENTS or _WORKSPACE.updated_at:
        return
    path = _state_path()
    if not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    workspace = payload.get("workspace") if isinstance(payload, dict) else {}
    if isinstance(workspace, dict):
        for key in asdict(_WORKSPACE):
            if key in workspace:
                setattr(_WORKSPACE, key, workspace[key])
    rows = payload.get("events") if isinstance(payload, dict) else []
    if isinstance(rows, list):
        for row in rows[-MAX_COGNITIVE_EVENTS:]:
            if not isinstance(row, dict):
                continue
            try:
                event = CognitiveEvent(
                    event_id=str(row.get("event_id") or ""),
                    cycle=int(row.get("cycle") or 0),
                    event_type=str(row.get("event_type") or "")[:80],
                    subject=str(row.get("subject") or "")[:160],
                    content=dict(row.get("content") or {}) if isinstance(row.get("content"), dict) else {},
                    origin=str(row.get("origin") or "")[:80],
                    confidence=float(row.get("confidence") or 0.0),
                    activation=float(row.get("activation") or 0.0),
                    parent_events=tuple(str(item) for item in list(row.get("parent_events") or [])),
                    timestamp=float(row.get("timestamp") or 0.0),
                )
            except (TypeError, ValueError):
                continue
            if not event.event_id or not event.event_type or not event.subject:
                continue
            _EVENTS.append(event)
            try:
                _EVENT_SEQUENCE = max(_EVENT_SEQUENCE, int(event.event_id.rsplit("_", 1)[-1]))
            except (ValueError, IndexError):
                pass


def reset() -> None:
    global _EVENT_SEQUENCE
    with _LOCK:
        _WORKSPACE.__dict__.update(asdict(CognitiveWorkspace()))
        _EVENTS.clear()
        _EVENT_SEQUENCE = 0
        try:
            _state_path().unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def update_workspace(**updates: Any) -> CognitiveWorkspace:
    """Merge bounded live cognitive state and persist the current scene."""
    with _LOCK:
        _load_unlocked()
        for key, value in updates.items():
            if not hasattr(_WORKSPACE, key):
                continue
            if key in {"candidate_explanations", "candidate_actions", "unresolved_questions", "assumptions"}:
                value = _bounded_strings(value)
            elif key in {"predictions", "recalled_experiences", "internal_conflicts"}:
                value = list(value)[:32] if isinstance(value, list) else []
            elif key == "emotional_equivalents" or key == "self_model":
                value = dict(value) if isinstance(value, dict) else {}
            elif key in {"cycle"}:
                value = int(value or 0)
            elif key == "updated_at":
                value = float(value or 0.0)
            else:
                value = str(value or "").strip()[:240]
            setattr(_WORKSPACE, key, value)
        _WORKSPACE.updated_at = time.time()
        _save_unlocked()
        return CognitiveWorkspace(**asdict(_WORKSPACE))


def current_workspace() -> CognitiveWorkspace:
    with _LOCK:
        _load_unlocked()
        return CognitiveWorkspace(**asdict(_WORKSPACE))


def record_event(
    *,
    event_type: str,
    subject: str,
    content: dict[str, Any] | None = None,
    origin: str = "",
    confidence: float = 0.0,
    activation: float = 0.0,
    parent_events: list[str] | tuple[str, ...] | None = None,
) -> CognitiveEvent | None:
    """Record a causal cognitive event without allowing it to break runtime work."""
    global _EVENT_SEQUENCE
    event_type = str(event_type or "").strip()[:80]
    subject = str(subject or "").strip()[:160]
    if not event_type or not subject:
        return None
    with _LOCK:
        _load_unlocked()
        _EVENT_SEQUENCE += 1
        event = CognitiveEvent(
            event_id=_event_id(_EVENT_SEQUENCE),
            cycle=int(_WORKSPACE.cycle or 0),
            event_type=event_type,
            subject=subject,
            content=dict(content or {}) if isinstance(content, dict) else {},
            origin=str(origin or "").strip()[:80],
            confidence=max(0.0, min(1.0, float(confidence or 0.0))),
            activation=max(0.0, min(1.0, float(activation or 0.0))),
            parent_events=tuple(str(item).strip() for item in list(parent_events or []) if str(item).strip())[:16],
            timestamp=time.time(),
        )
        _EVENTS.append(event)
        del _EVENTS[:-MAX_COGNITIVE_EVENTS]
        _save_unlocked()
        return event


def recent_events(limit: int = MAX_COGNITIVE_EVENTS) -> list[CognitiveEvent]:
    with _LOCK:
        _load_unlocked()
        return list(_EVENTS[-max(1, min(int(limit or MAX_COGNITIVE_EVENTS), MAX_COGNITIVE_EVENTS)):])


def payload(limit: int = MAX_COGNITIVE_EVENTS) -> dict[str, Any]:
    with _LOCK:
        workspace = current_workspace()
        events = recent_events(limit)
        return {
            "ok": True,
            "workspace": asdict(workspace),
            "event_count": len(events),
            "events": [asdict(event) for event in events],
        }
