"""Bounded observer over Nova's existing causal boundaries.

Not a second planner, self-model, or mission. Records what a gate, executor,
evidence step, or commit actually did. Meta is one interrupt-driven pass over
a rolling window. Control effects land on the solution trail, not a new store.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

META_MAX_OBSERVATIONS = 64
REPEAT_UNCHANGED_THRESHOLD = 3  # Deprecated: use policy.json observation_spine.repeat_unchanged_threshold

NO_META_INTERVENTION = "NO_META_INTERVENTION"
REPEATED_UNCHANGED_PATH = "REPEATED_UNCHANGED_PATH"
PICKUP_PATH_GAP = "PICKUP_PATH_GAP"
COMPETING_INTERPRETATIONS = "COMPETING_INTERPRETATIONS"
SELF_PREDICTION_MISS = "SELF_PREDICTION_MISS"

CONTINUE = "continue"
STOP_REPEATED_PATH = "stop_repeated_path"
ALTER_EXISTING_SELECTION = "alter_existing_selection"
REVISE_EXISTING_SELECTION = "revise_existing_selection"


@dataclass(frozen=True)
class Observation:
    seq: int
    source: str
    operation: str
    subject: str
    input_ref: str | None
    outcome: str
    output_ref: str | None
    reason_code: str | None
    monotonic_ns: int


@dataclass(frozen=True)
class CognitiveEvent:
    """Derived cognitive-context event backed by one boundary observation."""
    event_id: str
    cycle: int
    event_type: str
    subject: str
    content: dict[str, Any]
    origin: str
    confidence: float
    activation: float
    parent_events: list[str]
    monotonic_ns: int


@dataclass(frozen=True)
class DynamicSelfModel:
    """Evidence-backed model of Nova's current operational condition."""
    identity: str
    observed_capabilities: list[str]
    active_constraints: list[str]
    current_internal_condition: dict[str, Any]
    predicted_future_states: list[str]
    source_observation_seqs: list[int]


@dataclass(frozen=True)
class InternalPosition:
    """A competing operational interpretation before selection collapses it."""
    proposition: str
    supporting_evidence: list[int]
    opposing_evidence: list[int]
    confidence: float
    persistence: int
    status: str
    action_implications: list[str]


@dataclass(frozen=True)
class MetaResult:
    finding_code: str
    effect: str
    subject: str
    input_ref: str | None
    required_state_change: tuple[str, ...] = ()


_LOCK = threading.Lock()
_SEQ = 0
_BUFFER: list[Observation] = []


def _persist_path() -> Path:
    from services.nova_runtime_context import RUNTIME_DIR

    return Path(RUNTIME_DIR) / "observation_spine.json"


def _clear_persist() -> None:
    try:
        path = _persist_path()
        if path.is_file():
            path.unlink()
    except Exception:
        pass


def _load_persist_unlocked() -> None:
    """Caller holds _LOCK. Restore the rolling window across --once processes."""
    global _SEQ
    if _BUFFER:
        return
    path = _persist_path()
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    rows = data.get("observations") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return
    loaded: list[Observation] = []
    max_seq = 0
    for item in rows[-META_MAX_OBSERVATIONS:]:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        operation = str(item.get("operation") or "").strip()
        subject = str(item.get("subject") or "").strip()
        if not source or not operation or not subject:
            continue
        seq = int(item.get("seq") or 0)
        max_seq = max(max_seq, seq)
        loaded.append(
            Observation(
                seq=seq,
                source=source[:80],
                operation=operation[:80],
                subject=subject[:160],
                input_ref=str(item.get("input_ref") or "").strip()[:160] or None,
                outcome=str(item.get("outcome") or "unknown").strip()[:80] or "unknown",
                output_ref=str(item.get("output_ref") or "").strip()[:160] or None,
                reason_code=str(item.get("reason_code") or "").strip()[:120] or None,
                monotonic_ns=int(item.get("monotonic_ns") or 0),
            )
        )
    if not loaded:
        return
    _BUFFER.extend(loaded)
    _SEQ = max(_SEQ, max_seq)


def _save_persist_unlocked() -> None:
    try:
        path = _persist_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "observations": [asdict(row) for row in _BUFFER[-META_MAX_OBSERVATIONS:]],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass


def reset_observations() -> None:
    """Test helper. Live cycles keep the rolling window."""
    global _SEQ
    with _LOCK:
        _SEQ = 0
        _BUFFER.clear()
    _clear_persist()


def reset_memory_only() -> None:
    """Test helper: simulate a new --once process without wiping disk."""
    global _SEQ
    with _LOCK:
        _SEQ = 0
        _BUFFER.clear()


def recent_observations(*, limit: int = META_MAX_OBSERVATIONS) -> list[Observation]:
    cap = max(1, min(int(limit or META_MAX_OBSERVATIONS), META_MAX_OBSERVATIONS))
    with _LOCK:
        _load_persist_unlocked()
        return list(_BUFFER[-cap:])


def trailing_mill_skip_loop(*, threshold: int | None = None) -> bool:
    """True while the last mill cycles of the work-tree lane were skips.

    Spine may still report loop after mill already ran. Control uses the
    trailing mill observations so a mill run changes the next cycle.
    """
    need = int(threshold) if threshold is not None else _get_repeat_threshold()
    need = max(1, need)
    rows = [
        row
        for row in recent_observations()
        if row.source == "mill"
        and row.operation == "invoke"
        and row.subject == "active_work_tree_cycle"
    ]
    if len(rows) < need:
        return False
    return all(str(row.outcome or "").strip().lower() == "skipped" for row in rows[-need:])


FINDING_LABELS = {
    NO_META_INTERVENTION: "Watching — no interrupt",
    REPEATED_UNCHANGED_PATH: "Same path repeated unchanged",
    PICKUP_PATH_GAP: "Planner pick was not admitted by the matching gate",
    COMPETING_INTERPRETATIONS: "Competing next-step offers before collapse",
    SELF_PREDICTION_MISS: "Invoked path did not match the selected pick",
}

EFFECT_LABELS = {
    CONTINUE: "Continue",
    STOP_REPEATED_PATH: "Stop this path until the controlling ref changes",
    ALTER_EXISTING_SELECTION: "Alter the current selection",
    REVISE_EXISTING_SELECTION: "Revise the current selection",
}


def _count_attr(rows: list[Observation], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(getattr(row, attr, None) or "").strip() or "(none)"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _row_dict(row: Observation | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return asdict(row)


def _cognitive_event_type(row: Observation) -> str:
    if row.source == "pickup" and row.operation == "offer":
        return "candidate_action_activated"
    if row.operation == "select_next_action" and row.outcome == "selected":
        return "action_selected"
    if row.source in {"execution_gate", "mission_gate"} and row.outcome in {"blocked", "denied"}:
        return "constraint_detected"
    if row.source == "executor" and row.operation == "invoke":
        return "action_invoked"
    if row.outcome in {"failed", "error"}:
        return "prediction_failed"
    return f"{row.operation}_observed"


def _cognitive_events(rows: list[Observation]) -> list[CognitiveEvent]:
    events: list[CognitiveEvent] = []
    for row in rows:
        event_id = f"observation-{row.seq}"
        parent = [events[-1].event_id] if events else []
        events.append(
            CognitiveEvent(
                event_id=event_id,
                cycle=row.seq,
                event_type=_cognitive_event_type(row),
                subject=row.subject,
                content={
                    "source": row.source,
                    "operation": row.operation,
                    "outcome": row.outcome,
                    "input_ref": row.input_ref,
                    "output_ref": row.output_ref,
                    "reason_code": row.reason_code,
                },
                origin="observation_spine",
                confidence=1.0,
                activation=1.0,
                parent_events=parent,
                monotonic_ns=row.monotonic_ns,
            )
        )
    return events


def _self_questions(rows: list[Observation], finding: MetaResult) -> list[str]:
    questions: list[str] = []
    if finding.finding_code == REPEATED_UNCHANGED_PATH:
        questions.append("What changed since the last attempt on this path?")
    elif finding.finding_code == PICKUP_PATH_GAP:
        questions.append("Why was this action selected when its execution gate did not admit it?")
    elif finding.finding_code == COMPETING_INTERPRETATIONS:
        questions.append("Which evidence would discriminate between the competing next-step offers?")
    elif finding.finding_code == SELF_PREDICTION_MISS:
        questions.append("What did the invoked path reveal about the previous selection prediction?")
    if rows and rows[-1].outcome in {"failed", "blocked", "denied", "error"}:
        questions.append("Which assumption or constraint caused the latest action not to advance the work?")
    return questions[:3]


def _dynamic_self_model(rows: list[Observation], finding: MetaResult, questions: list[str]) -> DynamicSelfModel:
    capabilities = sorted({row.subject for row in rows if row.source in {"pickup", "planner", "executor"}})
    constraints = sorted({row.reason_code for row in rows if row.reason_code})
    condition = {
        "observation_count": len(rows),
        "meta_finding": finding.finding_code,
        "meta_effect": finding.effect,
        "active_question_count": len(questions),
        "runtime_observed": bool(rows),
    }
    predictions: list[str] = []
    if finding.finding_code == REPEATED_UNCHANGED_PATH:
        predictions.append("The same path should remain ineligible until its controlling reference changes.")
    elif finding.finding_code == SELF_PREDICTION_MISS:
        predictions.append("The next selection should be revised before another invocation.")
    elif finding.finding_code == PICKUP_PATH_GAP:
        predictions.append("The selected action should not be invoked until the matching gate admits it.")
    return DynamicSelfModel(
        identity="Nova operational self-model",
        observed_capabilities=capabilities[:32],
        active_constraints=constraints[:32],
        current_internal_condition=condition,
        predicted_future_states=predictions,
        source_observation_seqs=[row.seq for row in rows],
    )


def _internal_positions(rows: list[Observation], finding: MetaResult) -> list[InternalPosition]:
    offers = [
        row
        for row in rows
        if row.source == "pickup" and row.operation == "offer" and row.outcome == "offered"
    ]
    if len({(row.subject, row.input_ref or "") for row in offers}) < 2:
        return []
    last_offer_seq = max(row.seq for row in offers)
    later = [row for row in rows if row.seq > last_offer_seq]
    selected = next(
        (row for row in later if row.operation == "select_next_action" and row.outcome == "selected"),
        None,
    )
    invoked = next(
        (row for row in later if row.source == "executor" and row.operation == "invoke"),
        None,
    )
    positions: list[InternalPosition] = []
    offer_groups: dict[tuple[str, str], list[Observation]] = {}
    for row in offers:
        offer_groups.setdefault((row.subject, row.input_ref or ""), []).append(row)
    for key, group in offer_groups.items():
        row = group[-1]
        matching_selection = selected is not None and (selected.subject, selected.input_ref or "") == key
        matching_invoke = invoked is not None and (invoked.subject, invoked.input_ref or "") == key
        supporting = [item.seq for item in group]
        opposing: list[int] = []
        confidence = 0.5
        status = "competing"
        if selected is not None:
            if matching_selection:
                supporting.append(selected.seq)
                confidence = 0.75
                status = "favored"
            else:
                opposing.append(selected.seq)
                confidence = 0.25
                status = "deprioritized"
        if invoked is not None and matching_invoke:
            supporting.append(invoked.seq)
            confidence = min(0.95, confidence + 0.15)
            status = "supported"
        elif invoked is not None and not matching_invoke:
            opposing.append(invoked.seq)
        positions.append(
            InternalPosition(
                proposition=f"The next productive action may be {row.subject} for {row.input_ref or 'the current work' }.",
                supporting_evidence=supporting,
                opposing_evidence=opposing,
                confidence=confidence,
                persistence=len(supporting),
                status=status,
                action_implications=[f"test:{row.subject}"],
            )
        )
    return positions[:8]


def build_observation_spine_payload() -> dict[str, Any]:
    """Operator-facing snapshot of the live observation window and current finding."""
    try:
        rows = recent_observations()
        finding = meta_check(rows)
    except Exception as exc:
        return {
            "ok": False,
            "status": "unavailable",
            "error": str(exc)[:160],
            "window_count": 0,
            "window_cap": META_MAX_OBSERVATIONS,
            "finding_code": NO_META_INTERVENTION,
            "finding_label": FINDING_LABELS[NO_META_INTERVENTION],
            "effect": CONTINUE,
            "effect_label": EFFECT_LABELS[CONTINUE],
            "subject": "",
            "input_ref": None,
            "required_state_change": [],
            "intervening": False,
            "source_counts": {},
            "operation_counts": {},
            "subject_counts": {},
            "last_select": None,
            "last_invoke": None,
            "last_gate": None,
            "observations": [],
        }

    last_select = None
    last_invoke = None
    last_gate = None
    for row in rows:
        if row.operation == "select_next_action":
            last_select = row
        if row.operation == "invoke":
            last_invoke = row
        if row.source in {"execution_gate", "mission_gate"}:
            last_gate = row

    intervening = bool(rows) and finding.finding_code != NO_META_INTERVENTION
    if not rows:
        status = "empty"
    elif intervening:
        status = "intervening"
    else:
        status = "watching"

    events = _cognitive_events(rows)
    questions = _self_questions(rows, finding)
    self_model = _dynamic_self_model(rows, finding, questions)
    positions = _internal_positions(rows, finding)
    return {
        "ok": True,
        "status": status,
        "window_count": len(rows),
        "window_cap": META_MAX_OBSERVATIONS,
        "first_seq": int(rows[0].seq) if rows else 0,
        "last_seq": int(rows[-1].seq) if rows else 0,
        "finding_code": finding.finding_code,
        "finding_label": FINDING_LABELS.get(finding.finding_code, finding.finding_code),
        "effect": finding.effect,
        "effect_label": EFFECT_LABELS.get(finding.effect, finding.effect),
        "subject": finding.subject,
        "input_ref": finding.input_ref,
        "required_state_change": list(finding.required_state_change or ()),
        "intervening": intervening,
        "source_counts": _count_attr(rows, "source"),
        "operation_counts": _count_attr(rows, "operation"),
        "subject_counts": _count_attr(rows, "subject"),
        "last_select": _row_dict(last_select),
        "last_invoke": _row_dict(last_invoke),
        "last_gate": _row_dict(last_gate),
        "observations": [_row_dict(row) for row in rows],
        "cognitive_events": [asdict(event) for event in events],
        "self_questions": questions,
        "self_model": asdict(self_model),
        "internal_positions": [asdict(position) for position in positions],
    }


def observe(
    *,
    source: str,
    operation: str,
    subject: str,
    outcome: str,
    input_ref: str | None = None,
    output_ref: str | None = None,
    reason_code: str | None = None,
) -> Observation | None:
    """Record one raw boundary event. Never raises into the object loop."""
    try:
        global _SEQ
        source_key = str(source or "").strip()[:80]
        operation_key = str(operation or "").strip()[:80]
        subject_key = str(subject or "").strip()[:160]
        if not source_key or not operation_key or not subject_key:
            return None
        row = Observation(
            seq=0,
            source=source_key,
            operation=operation_key,
            subject=subject_key,
            input_ref=_clip(input_ref, 160),
            outcome=str(outcome or "").strip()[:80] or "unknown",
            output_ref=_clip(output_ref, 160),
            reason_code=_clip(reason_code, 120),
            monotonic_ns=time.monotonic_ns(),
        )
        with _LOCK:
            _load_persist_unlocked()
            _SEQ += 1
            row = Observation(
                seq=_SEQ,
                source=row.source,
                operation=row.operation,
                subject=row.subject,
                input_ref=row.input_ref,
                outcome=row.outcome,
                output_ref=row.output_ref,
                reason_code=row.reason_code,
                monotonic_ns=row.monotonic_ns,
            )
            _BUFFER.append(row)
            if len(_BUFFER) > META_MAX_OBSERVATIONS:
                del _BUFFER[:-META_MAX_OBSERVATIONS]
            _save_persist_unlocked()
        return row
    except Exception:
        return None


def observe_quietly(**kwargs: Any) -> None:
    observe(**kwargs)


def _get_repeat_threshold() -> int:
    """Load repeat threshold from policy.json, fall back to hardcoded default."""
    try:
        import json
        from pathlib import Path
        policy_file = Path(__file__).parent.parent / "policy.json"
        if policy_file.exists():
            policy = json.loads(policy_file.read_text())
            return int(policy.get("observation_spine", {}).get("repeat_unchanged_threshold", REPEAT_UNCHANGED_THRESHOLD))
    except Exception:
        pass
    return REPEAT_UNCHANGED_THRESHOLD


def meta_check(window: list[Observation] | None = None) -> MetaResult:
    """One bounded pass. Topology only. No LLM."""
    rows = list(window if window is not None else recent_observations())
    if not rows:
        return MetaResult(NO_META_INTERVENTION, CONTINUE, "", None)

    pickup = _pickup_path_gap(rows)
    if pickup is not None:
        return pickup

    predicted = _self_prediction(rows)
    if predicted is not None:
        return predicted

    competing = _competing_interpretations(rows)
    if competing is not None:
        return competing

    repeated = _repeated_unchanged_path(rows)
    if repeated is not None:
        return repeated

    return MetaResult(NO_META_INTERVENTION, CONTINUE, "", None)


def apply_self_prediction_miss_to_trail(
    *,
    branch_id: str,
    tool_name: str,
    task_title: str = "",
    input_ref: str | None = None,
    predicted_subject: str = "",
    predicted_ref: str | None = None,
) -> dict[str, Any]:
    """Invoke did not match the predicted pick. Make that invoked path ineligible for now."""
    try:
        import work_tree
        from services.solution_trail import (
            JUDGMENT_REDUNDANT,
            append_attempt_judgment,
        )
    except Exception as exc:
        return {"ok": False, "reason": f"trail_unavailable:{exc}"}

    clean_id = str(branch_id or "").strip()
    tool = str(tool_name or "").strip().lower()
    if not clean_id or not tool:
        return {"ok": False, "reason": "missing_path"}

    # Use per-branch lock to prevent race condition when multiple --once cycles apply effects
    try:
        with work_tree._acquire_branch_lock(clean_id):
            branch = work_tree.get_branch(clean_id)
            if branch is None:
                return {"ok": False, "reason": "branch_missing"}

            payload = dict(branch.source_payload or {}) if isinstance(getattr(branch, "source_payload", None), dict) else {}
            controlling = str(input_ref or "").strip()
            predicted = str(predicted_subject or "").strip()
            predicted_input = str(predicted_ref or "").strip()
            if controlling:
                payload["observation_input_ref"] = controlling[:160]
            record = {
                "judgment": JUDGMENT_REDUNDANT,
                "reason": "self_prediction_miss",
                "tool": tool,
                "task_title": str(task_title or "")[:200],
                "target_markers": [],
                "do_not_retry_while": (
                    [{"type": "same_input_ref", "value": controlling}] if controlling else []
                ),
                "retry_when": (
                    [{"type": "invoke_matches_selection", "subject": predicted, "input_ref": predicted_input}]
                    if predicted
                    else []
                ),
                "conditions": {"input_ref": controlling, "predicted_subject": predicted},
                "source": "observation_spine",
            }
            branch.source_payload = append_attempt_judgment(payload, record)
            try:
                work_tree.touch_branch(clean_id)
            except Exception:
                pass
    except Exception as exc:
        return {"ok": False, "reason": f"lock_failed:{exc}"}
    
    return {
        "ok": True,
        "finding_code": SELF_PREDICTION_MISS,
        "tool": tool,
        "predicted_subject": predicted,
    }


def apply_repeated_path_to_trail(
    *,
    branch_id: str,
    tool_name: str,
    task_title: str = "",
    input_ref: str | None = None,
) -> dict[str, Any]:
    """Make the existing trail path ineligible until the controlling ref changes."""
    try:
        import work_tree
        from services.solution_trail import (
            JUDGMENT_REDUNDANT,
            append_attempt_judgment,
        )
    except Exception as exc:
        return {"ok": False, "reason": f"trail_unavailable:{exc}"}

    clean_id = str(branch_id or "").strip()
    tool = str(tool_name or "").strip().lower()
    if not clean_id or not tool:
        return {"ok": False, "reason": "missing_path"}

    # Use per-branch lock to prevent race condition when multiple --once cycles apply effects
    try:
        with work_tree._acquire_branch_lock(clean_id):
            branch = work_tree.get_branch(clean_id)
            if branch is None:
                return {"ok": False, "reason": "branch_missing"}

            payload = dict(branch.source_payload or {}) if isinstance(getattr(branch, "source_payload", None), dict) else {}
            controlling = str(input_ref or "").strip()
            if controlling:
                payload["observation_input_ref"] = controlling[:160]
            record = {
                "judgment": JUDGMENT_REDUNDANT,
                "reason": "repeated_unchanged_path",
                "tool": tool,
                "task_title": str(task_title or "")[:200],
                "target_markers": [],
                "do_not_retry_while": (
                    [{"type": "same_input_ref", "value": controlling}] if controlling else []
                ),
                "retry_when": (
                    [{"type": "input_ref_changed", "from": controlling}] if controlling else []
                ),
                "conditions": {"input_ref": controlling},
                "source": "observation_spine",
            }
            branch.source_payload = append_attempt_judgment(payload, record)
            try:
                work_tree.touch_branch(clean_id)
            except Exception:
                pass
    except Exception as exc:
        return {"ok": False, "reason": f"lock_failed:{exc}"}
    
    return {"ok": True, "finding_code": REPEATED_UNCHANGED_PATH, "tool": tool}


def _clip(value: Any, limit: int) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[: max(1, int(limit or 80))]


def _path_key(row: Observation) -> tuple[str, str, str, str | None]:
    """Key for loop detection: (source, operation, subject, input_ref).
    
    IMPORTANT: Keep input_ref as-is (don't collapse None to ""). This allows:
    - Distinguishing "action called with no ref" (None) from "called with different refs"
    - Detecting real loops where same subject is invoked with identical ref
    - NOT falsely detecting loops when the ref varies (which indicates different contexts)
    """
    return (row.source, row.operation, row.subject, row.input_ref)


def _repeated_unchanged_path(rows: list[Observation]) -> MetaResult | None:
    """Detect when the exact same action (source, operation, subject, input_ref) repeats.
    
    Only trips when ALL four components are identical. This prevents:
    - False positives on legitimate variation (different input_ref means different context)
    - Missing genuine loops (same subject, same input_ref = same context = loop)
    """
    threshold = _get_repeat_threshold()
    counts: dict[tuple[str, str, str, str | None], int] = {}
    last: Observation | None = None
    for row in rows:
        if row.operation not in {"invoke", "select_next_action"}:
            continue
        key = _path_key(row)
        counts[key] = counts.get(key, 0) + 1
        if counts[key] >= threshold:
            last = row
    if last is None:
        return None
    return MetaResult(
        finding_code=REPEATED_UNCHANGED_PATH,
        effect=STOP_REPEATED_PATH,
        subject=last.subject,
        input_ref=last.input_ref,
        required_state_change=("input_ref_changed",),
    )


def _self_prediction(rows: list[Observation]) -> MetaResult | None:
    """Score whether the collapsed pick was the invoke that ran."""
    last_select = None
    for row in rows:
        if row.source == "pickup" and row.operation == "select_next_action" and row.outcome == "selected":
            last_select = row
        if (
            last_select is not None
            and row.source == "executor"
            and row.operation == "invoke"
            and row.seq > last_select.seq
        ):
            selected = (last_select.subject, last_select.input_ref or "")
            invoked = (row.subject, row.input_ref or "")
            if selected == invoked:
                return None
            return MetaResult(
                finding_code=SELF_PREDICTION_MISS,
                effect=REVISE_EXISTING_SELECTION,
                subject=last_select.subject,
                input_ref=last_select.input_ref,
                required_state_change=("invoke_matches_selection",),
            )
    return None


def _competing_interpretations(rows: list[Observation]) -> MetaResult | None:
    """Two pickup offers disagree about what next is. See them before sort collapses."""
    offers = [
        row
        for row in rows
        if row.source == "pickup" and row.operation == "offer" and row.outcome == "offered"
    ]
    keys = {(row.subject, row.input_ref or "") for row in offers}
    if len(keys) < 2:
        return None
    last_offer_seq = max(row.seq for row in offers)
    for row in rows:
        if row.seq <= last_offer_seq:
            continue
        if row.operation == "select_next_action" and row.outcome == "selected":
            return None
        if row.source == "executor" and row.operation == "invoke":
            return None
    last = offers[-1]
    return MetaResult(
        finding_code=COMPETING_INTERPRETATIONS,
        effect=ALTER_EXISTING_SELECTION,
        subject=last.subject,
        input_ref=last.input_ref,
        required_state_change=("selection_collapsed",),
    )


def _pickup_path_gap(rows: list[Observation]) -> MetaResult | None:
    """Planner selected an action the matching gate never admitted."""
    selected: dict[str, Observation] = {}
    for row in rows:
        if row.source == "planner" and row.operation == "select_next_action" and row.outcome == "selected":
            selected[row.subject] = row
    if not selected:
        return None
    for subject, plan in selected.items():
        admitted = False
        denied = False
        for row in rows:
            if row.seq < plan.seq:
                continue
            if row.subject != subject:
                continue
            if row.source in {"execution_gate", "mission_gate"} and row.operation in {"evaluate", "admit_action"}:
                if row.outcome in {"allowed", "admitted"}:
                    admitted = True
                if row.outcome in {"blocked", "denied", "deferred"}:
                    denied = True
        if denied and not admitted:
            return MetaResult(
                finding_code=PICKUP_PATH_GAP,
                effect=STOP_REPEATED_PATH,
                subject=subject,
                input_ref=plan.input_ref,
                required_state_change=("gate_outcome_changed",),
            )
    return None
