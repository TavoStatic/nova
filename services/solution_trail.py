"""Solution trail: attempt journal → judgment → next productive move.

No parallel avenue DB. Judgments live on the finding (branch.source_payload),
bounded. Trail next-move skips sequence stems already satisfied *or* still
suppressed by an active reactivation contract.

Attempt classes (v1 core):
  proven      — advanced at least one required marker
  redundant   — no advance; target marker already held
  premature   — tool targets a marker whose prerequisites are not held

Rule:
  Do not suppress permanently unless unconditional. Suppress while the
  conditions responsible for failure remain unchanged (reactivation contract).
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

ATTEMPT_JUDGMENTS_KEY = "attempt_judgments"
MAX_ATTEMPT_JUDGMENTS = 24

JUDGMENT_PROVEN = "proven"
JUDGMENT_REDUNDANT = "redundant"
JUDGMENT_PREMATURE = "premature"
JUDGMENT_REFUSED = "refused"

_SUPPRESSING = frozenset({JUDGMENT_REDUNDANT, JUDGMENT_PREMATURE, JUDGMENT_REFUSED})
REFUSE_SOURCE = "signal_reconcile"
PRESSURE_INHERITED = "inherited_attempt"
PRESSURE_EMPTY_CLAIM = "empty_claim"


def _empty_memory_kind() -> dict[str, Any]:
    return {
        "kind": "",
        "controlling": False,
        "reason": "",
        "retry_when": [],
        "pressure": {},
        "source": "",
    }


def _refuse_pressure(prior: dict[str, Any]) -> dict[str, Any]:
    """Cost of the refuse lesson. Inherit a prior attempt; never evidence_count."""
    row = _as_dict(prior)
    inherited_from = _text(row.get("attempt_id"), 40)
    if inherited_from:
        return {
            "event": PRESSURE_INHERITED,
            "invoke": False,
            "inherited_from": inherited_from,
            "inherited_judgment": _text(row.get("judgment"), 40),
            "inherited_reason": _text(row.get("reason"), 120),
            "inherited_at": _text(row.get("at"), 40),
        }
    return {
        "event": PRESSURE_EMPTY_CLAIM,
        "invoke": False,
        "inherited_from": "",
        "inherited_judgment": "",
        "inherited_reason": "",
        "inherited_at": "",
        "note": PRESSURE_EMPTY_CLAIM,
    }


def derive_branch_memory_kind(
    branch: Any,
    *,
    has_open_stem: bool = False,
    active_source_keys: set[str] | None = None,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Current instruction kind from trail. Derived, never stored on the branch.

    Pickup and the visual payload must call this with the same world
    (stem + active source keys). Controlling refuse is the pickup skip.
    """
    payload = dict(getattr(branch, "source_payload", None) or {}) if isinstance(getattr(branch, "source_payload", None), dict) else {}
    source_key = str(getattr(branch, "source_key", "") or payload.get("source_key") or "").strip()
    rows = [dict(r) for r in list(payload.get(ATTEMPT_JUDGMENTS_KEY) or []) if isinstance(r, dict)]
    if not rows:
        return _empty_memory_kind()
    holding_progress = dict(progress or {})
    released: dict[str, Any] | None = None
    for row in reversed(rows):
        klass = _text(row.get("judgment"), 40).lower()
        if klass not in {JUDGMENT_REFUSED, JUDGMENT_REDUNDANT, JUDGMENT_PREMATURE, JUDGMENT_PROVEN}:
            continue
        suppressing = klass in _SUPPRESSING and judgment_still_suppresses(
            row,
            progress=holding_progress,
            branch_payload=payload,
            has_open_stem=has_open_stem,
            active_source_keys=active_source_keys,
            source_key=source_key,
        )
        info = {
            "kind": klass,
            "controlling": bool(suppressing),
            "reason": _text(row.get("reason"), 120),
            "retry_when": [dict(c) for c in list(row.get("retry_when") or []) if isinstance(c, dict)],
            "pressure": dict(row.get("pressure") or {}) if isinstance(row.get("pressure"), dict) else {},
            "source": _text(row.get("source"), 80),
        }
        if suppressing or klass == JUDGMENT_PROVEN:
            return info
        if released is None:
            released = info
    return released or _empty_memory_kind()


def mill_judgment_signal(kind: Any = None) -> dict[str, Any]:
    """SOCK handoff packet from derived trail kind. Never names a model.

    Derived, not stored. Mill class + pressure only.
    """
    row = _as_dict(kind)
    pressure = _as_dict(row.get("pressure"))
    klass = _text(row.get("kind") or row.get("class"), 40).lower()
    if klass not in {JUDGMENT_REFUSED, JUDGMENT_REDUNDANT, JUDGMENT_PREMATURE, JUDGMENT_PROVEN}:
        klass = ""
    invoke_raw = pressure.get("invoke")
    return {
        "class": klass,
        "controlling": bool(row.get("controlling")),
        "pressure_event": _text(pressure.get("event"), 40).lower(),
        "invoke": True if invoke_raw is None else bool(invoke_raw),
        "reason": _text(row.get("reason"), 120),
        "source": _text(row.get("source"), 80),
    }


def trail_world_holds(branch: Any, *, has_open_stem: bool | None = None) -> dict[str, Any] | None:
    """Paid trail / refuse is world evidence. Controlling redundant or refused holds."""
    stem = bool(has_open_stem)
    if has_open_stem is None:
        try:
            import work_tree

            stem = work_tree._next_open_task(str(getattr(branch, "branch_id", "") or "")) is not None
        except Exception:
            stem = False
    kind = derive_branch_memory_kind(branch, has_open_stem=stem, progress={})
    signal = mill_judgment_signal(kind)
    if bool(signal.get("controlling")) and str(signal.get("class") or "") in {JUDGMENT_REDUNDANT, JUDGMENT_REFUSED}:
        return signal
    return None


def record_world_hold_on_branch(
    branch_id: str,
    *,
    tool_name: str = "",
    task_title: str = "",
    reason: str = "skip_until_world_changes",
    input_ref: str = "",
    source: str = "mill_sip",
) -> dict[str, Any]:
    """Sip/skip is world evidence. Controlling redundant until the ref changes."""
    import work_tree

    clean_id = str(branch_id or "").strip()
    if not clean_id:
        return {"ok": False, "reason": "missing_path"}
    branch = work_tree.get_branch(clean_id)
    if branch is None:
        return {"ok": False, "reason": "branch_missing"}
    payload = dict(branch.source_payload or {}) if isinstance(branch.source_payload, dict) else {}
    controlling = _text(input_ref, 160) or _text(payload.get("observation_input_ref"), 160)
    package = _package_identity(payload)
    if controlling:
        payload["observation_input_ref"] = controlling
    record = {
        "judgment": JUDGMENT_REDUNDANT,
        "reason": _text(reason, 120) or "skip_until_world_changes",
        "tool": _norm_tool(tool_name),
        "task_title": _text(task_title, 200),
        "target_markers": [],
        "do_not_retry_while": (
            [{"type": "same_input_ref", "value": controlling}]
            if controlling
            else ([{"type": "same_package_identity", "value": package}] if package else [])
        ),
        "retry_when": (
            [{"type": "input_ref_changed", "from": controlling}]
            if controlling
            else ([{"type": "package_identity_changed", "from": package}] if package else [])
        ),
        "conditions": {"input_ref": controlling, "package_identity": package},
        "source": _text(source, 80) or "mill_sip",
    }
    branch.source_payload = append_attempt_judgment(payload, record)
    try:
        work_tree.touch_branch(clean_id)
    except Exception:
        pass
    return {"ok": True, "judgment": record}


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _norm_tool(value: Any) -> str:
    return _text(value, 120).lower()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _holding_map(progress: dict[str, Any] | None) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for row in list(_as_dict(progress).get("markers") or []):
        if not isinstance(row, dict):
            continue
        mid = _text(row.get("id") or row.get("marker_id"), 80)
        if mid:
            out[mid] = bool(row.get("counts") or row.get("achieved"))
    return out


def _markers_for_tool(tool: str, *, work_class: str, source_type: str) -> list[Any]:
    tool_key = _norm_tool(tool)
    if not tool_key:
        return []
    try:
        from services.work_tree_task_progress import get_ladder

        ladder = get_ladder(work_class=work_class, source_type=source_type)
    except Exception:
        return []
    hits = []
    for marker in ladder.markers:
        tools = {_norm_tool(t) for t in list(marker.tools) + list(marker.verify_tools)}
        if tool_key in tools:
            hits.append(marker)
    return hits


def _package_identity(payload: dict[str, Any]) -> str:
    name = _text(payload.get("latest_artifact_name"), 200)
    path = _text(payload.get("latest_artifact_path"), 300)
    verified = _text(payload.get("latest_verified_at"), 80)
    version = _text(payload.get("latest_version"), 80)
    return "|".join(part for part in (name or path, version, verified) if part)


def classify_attempt(
    *,
    tool_name: str,
    task_title: str = "",
    progress_before: dict[str, Any] | None,
    progress_after: dict[str, Any] | None,
    work_class: str = "",
    source_type: str = "",
    branch_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify one tool attempt (proven | redundant | premature)."""
    tool = _norm_tool(tool_name)
    before = _holding_map(progress_before)
    after = _holding_map(progress_after)
    targets = _markers_for_tool(tool, work_class=work_class, source_type=source_type)
    target_ids = [m.marker_id for m in targets]
    payload = _as_dict(branch_payload)

    newly = [mid for mid, held in after.items() if held and not before.get(mid)]
    advanced_targets = [mid for mid in newly if mid in target_ids] if target_ids else newly

    if advanced_targets:
        return {
            "judgment": JUDGMENT_PROVEN,
            "reason": f"advanced_markers:{','.join(advanced_targets)}",
            "target_markers": target_ids or advanced_targets,
            "do_not_retry_while": [],
            "retry_when": [],
            "conditions": {
                "package_identity": _package_identity(payload),
                "readiness_state": _text(payload.get("latest_readiness_state"), 80),
            },
        }

    # Premature: tool aims at a marker whose prerequisites are not held.
    missing_for: list[tuple[str, list[str]]] = []
    for marker in targets:
        missing = [req for req in marker.requires_markers if not after.get(req)]
        if missing:
            missing_for.append((marker.marker_id, missing))
    if missing_for:
        # Contract: do not retry while any required marker remains false.
        do_not: list[dict[str, str]] = []
        retry: list[dict[str, str]] = []
        for _mid, missing in missing_for:
            for req in missing:
                do_not.append({"type": "marker_false", "marker_id": req})
                retry.append({"type": "marker_true", "marker_id": req})
        # Dedupe
        seen: set[str] = set()
        clean_do: list[dict[str, str]] = []
        clean_retry: list[dict[str, str]] = []
        for row in do_not:
            key = f"{row['type']}:{row['marker_id']}"
            if key in seen:
                continue
            seen.add(key)
            clean_do.append(row)
        seen.clear()
        for row in retry:
            key = f"{row['type']}:{row['marker_id']}"
            if key in seen:
                continue
            seen.add(key)
            clean_retry.append(row)
        reason_bits = [f"{mid}<-{','.join(miss)}" for mid, miss in missing_for]
        return {
            "judgment": JUDGMENT_PREMATURE,
            "reason": f"prerequisites_missing:{';'.join(reason_bits)}",
            "target_markers": [mid for mid, _ in missing_for],
            "do_not_retry_while": clean_do,
            "retry_when": clean_retry,
            "conditions": {
                "package_identity": _package_identity(payload),
                "readiness_state": _text(payload.get("latest_readiness_state"), 80),
            },
        }

    # Redundant: no advance; at least one target marker already held (or nothing to move).
    already = [mid for mid in target_ids if before.get(mid) or after.get(mid)]
    return {
        "judgment": JUDGMENT_REDUNDANT,
        "reason": (
            f"no_marker_advance_targets_held:{','.join(already)}"
            if already
            else "no_marker_advance"
        ),
        "target_markers": target_ids or already,
        "do_not_retry_while": (
            [{"type": "marker_true", "marker_id": mid} for mid in already]
            if already
            else [{"type": "same_package_identity", "value": _package_identity(payload)}]
        ),
        "retry_when": (
            [{"type": "marker_false", "marker_id": mid} for mid in already]
            if already
            else [{"type": "package_identity_changed", "from": _package_identity(payload)}]
        ),
        "conditions": {
            "package_identity": _package_identity(payload),
            "readiness_state": _text(payload.get("latest_readiness_state"), 80),
        },
    }


def _clause_holds(
    clause: dict[str, Any],
    *,
    holding: dict[str, bool],
    package_identity: str,
    input_ref: str = "",
    has_open_stem: bool = False,
    active_source_keys: set[str] | None = None,
    source_key: str = "",
) -> bool:
    kind = _text(clause.get("type"), 80).lower()
    if kind == "marker_true":
        return bool(holding.get(_text(clause.get("marker_id"), 80)))
    if kind == "marker_false":
        mid = _text(clause.get("marker_id"), 80)
        return not bool(holding.get(mid))
    if kind == "same_package_identity":
        return package_identity == _text(clause.get("value"), 400) and bool(package_identity)
    if kind == "package_identity_changed":
        prior = _text(clause.get("from"), 400)
        return bool(prior) and package_identity != prior
    if kind == "same_input_ref":
        stored = _text(clause.get("value"), 160)
        current = _text(input_ref, 160)
        return bool(stored) and (not current or current == stored)
    if kind == "input_ref_changed":
        prior = _text(clause.get("from"), 160)
        current = _text(input_ref, 160)
        return bool(prior) and bool(current) and current != prior
    if kind == "invoke_matches_selection":
        # Selection is revised elsewhere. This clause never self-releases a miss.
        return False
    if kind == "has_open_stem":
        return bool(has_open_stem)
    if kind == "no_open_stem":
        return not bool(has_open_stem)
    if kind == "source_key_in_active_set":
        key = _text(source_key or clause.get("value"), 400)
        active = {str(item or "").strip() for item in set(active_source_keys or set()) if str(item or "").strip()}
        return bool(key) and key in active
    return False


def judgment_still_suppresses(
    judgment: dict[str, Any],
    *,
    progress: dict[str, Any] | None,
    branch_payload: dict[str, Any] | None = None,
    has_open_stem: bool = False,
    active_source_keys: set[str] | None = None,
    source_key: str = "",
) -> bool:
    """True while reactivation contract has not fired."""
    row = _as_dict(judgment)
    klass = _text(row.get("judgment"), 40).lower()
    if klass not in _SUPPRESSING:
        return False
    holding = _holding_map(progress)
    package_identity = _package_identity(_as_dict(branch_payload))
    input_ref = _text(_as_dict(branch_payload).get("observation_input_ref"), 160)
    clause_kwargs = {
        "holding": holding,
        "package_identity": package_identity,
        "input_ref": input_ref,
        "has_open_stem": bool(has_open_stem),
        "active_source_keys": active_source_keys,
        "source_key": source_key or _text(_as_dict(branch_payload).get("source_key"), 400),
    }
    # Prefer explicit retry_when: suppress until ALL retry clauses hold.
    retry_when = [dict(c) for c in list(row.get("retry_when") or []) if isinstance(c, dict)]
    if retry_when:
        return not all(_clause_holds(c, **clause_kwargs) for c in retry_when)
    # Fallback: suppress while any do_not_retry_while holds.
    blockers = [dict(c) for c in list(row.get("do_not_retry_while") or []) if isinstance(c, dict)]
    if blockers:
        return any(_clause_holds(c, **clause_kwargs) for c in blockers)
    # Redundant/refused with empty contract: suppress only if still no work needed (conservative).
    return klass in {JUDGMENT_REDUNDANT, JUDGMENT_REFUSED}


def action_suppressed_by_trail(
    *,
    tool_name: str = "",
    task_title: str = "",
    judgments: list[dict[str, Any]] | None = None,
    progress: dict[str, Any] | None = None,
    branch_payload: dict[str, Any] | None = None,
    has_open_stem: bool = False,
    active_source_keys: set[str] | None = None,
    source_key: str = "",
) -> dict[str, Any] | None:
    """Return the active suppressing judgment for this tool/title, if any.
    
    Prunes expired judgments (whose retry_when conditions hold) before checking,
    so feedback closure works: when a condition changes, suppression lifts.
    """
    tool = _norm_tool(tool_name)
    title = _text(task_title, 200).lower()
    if not tool and not title:
        return None
    
    # Prune expired judgments before checking
    rows = [dict(r) for r in list(judgments or []) if isinstance(r, dict)]
    rows = _prune_expired_judgments(
        rows,
        progress=progress,
        branch_payload=branch_payload,
        has_open_stem=has_open_stem,
        active_source_keys=active_source_keys,
        source_key=source_key,
    )
    
    for row in reversed(rows):
        j_tool = _norm_tool(row.get("tool"))
        j_title = _text(row.get("task_title"), 200).lower()
        if tool and j_tool:
            if tool != j_tool:
                continue
            if title and j_title and title != j_title:
                continue
        elif title and j_title:
            if title != j_title:
                continue
        else:
            continue
        if not judgment_still_suppresses(
            row,
            progress=progress,
            branch_payload=branch_payload,
            has_open_stem=has_open_stem,
            active_source_keys=active_source_keys,
            source_key=source_key,
        ):
            continue
        return row
    return None


def tool_targets_already_held(
    tool_name: str,
    *,
    progress: dict[str, Any] | None,
    work_class: str = "",
    source_type: str = "",
) -> bool:
    """True when every ladder marker this tool can hit is already counting.

    Sequence next-move uses this to skip obsolete stems (e.g. more `read` after
    package_identified + drift_understood) without waiting for that exact title
    to have been completed once.
    """
    tool = _norm_tool(tool_name)
    if not tool:
        return False
    targets = _markers_for_tool(tool, work_class=work_class, source_type=source_type)
    if not targets:
        return False
    holding = _holding_map(progress)
    return all(bool(holding.get(marker.marker_id)) for marker in targets)


def sequence_item_should_skip_for_trail(
    *,
    tool_name: str = "",
    task_title: str = "",
    progress: dict[str, Any] | None = None,
    judgments: list[dict[str, Any]] | None = None,
    branch_payload: dict[str, Any] | None = None,
    work_class: str = "",
    source_type: str = "",
) -> dict[str, Any] | None:
    """Why a sequence stem should be skipped now (suppress or markers already held)."""
    tool = _norm_tool(tool_name)
    suppressed = action_suppressed_by_trail(
        tool_name=tool,
        task_title=task_title,
        judgments=judgments,
        progress=progress,
        branch_payload=branch_payload,
    )
    if suppressed is not None:
        return {
            "reason": "trail_suppressed",
            "judgment": suppressed,
            "tool": tool,
        }
    if tool_targets_already_held(
        tool,
        progress=progress,
        work_class=work_class,
        source_type=source_type,
    ):
        return {
            "reason": "markers_already_held",
            "tool": tool,
            "judgment": None,
        }
    return None


def _prune_expired_judgments(
    rows: list[dict[str, Any]],
    *,
    progress: dict[str, Any] | None = None,
    branch_payload: dict[str, Any] | None = None,
    has_open_stem: bool = False,
    active_source_keys: set[str] | None = None,
    source_key: str = "",
) -> list[dict[str, Any]]:
    """Remove judgments whose retry_when conditions have been satisfied.
    
    This closes the feedback loop: when a condition changes (e.g., input_ref),
    the suppression is lifted automatically rather than accumulating forever.
    """
    if not rows:
        return rows
    
    kept = []
    for row in rows:
        # Check if this suppressing judgment is still active
        if not judgment_still_suppresses(
            row,
            progress=progress,
            branch_payload=branch_payload,
            has_open_stem=has_open_stem,
            active_source_keys=active_source_keys,
            source_key=source_key,
        ):
            # Condition has changed; judgment is expired, skip it
            continue
        kept.append(row)
    return kept


def append_attempt_judgment(branch_payload: dict[str, Any] | None, judgment: dict[str, Any]) -> dict[str, Any]:
    """Persist one judgment on finding payload (bounded)."""
    payload = dict(branch_payload or {}) if isinstance(branch_payload, dict) else {}
    rows = [dict(r) for r in list(payload.get(ATTEMPT_JUDGMENTS_KEY) or []) if isinstance(r, dict)]
    row = dict(judgment)
    row.setdefault("attempt_id", f"att_{uuid4().hex[:10]}")
    row.setdefault("at", _now_iso())
    rows.append(row)
    if len(rows) > MAX_ATTEMPT_JUDGMENTS:
        rows = rows[-MAX_ATTEMPT_JUDGMENTS:]
    payload[ATTEMPT_JUDGMENTS_KEY] = rows
    return payload


def record_attempt_on_branch(
    branch_id: str,
    *,
    tool_name: str,
    task_title: str = "",
    progress_before: dict[str, Any] | None,
    progress_after: dict[str, Any] | None,
) -> dict[str, Any]:
    """Classify and store attempt judgment on the branch finding."""
    import work_tree

    branch = work_tree.get_branch(str(branch_id or "").strip())
    if branch is None:
        return {"ok": False, "reason": "branch_missing"}
    payload = dict(branch.source_payload or {}) if isinstance(branch.source_payload, dict) else {}
    classified = classify_attempt(
        tool_name=tool_name,
        task_title=task_title,
        progress_before=progress_before,
        progress_after=progress_after,
        work_class=str(getattr(branch, "work_class", "") or ""),
        source_type=str(getattr(branch, "source_type", "") or ""),
        branch_payload=payload,
    )
    record = {
        **classified,
        "tool": _norm_tool(tool_name),
        "task_title": _text(task_title, 200),
        "at": _now_iso(),
        "attempt_id": f"att_{uuid4().hex[:10]}",
    }
    branch.source_payload = append_attempt_judgment(payload, record)
    return {"ok": True, "judgment": record}


def record_refuse_on_branch(
    branch_id: str,
    *,
    reason: str,
    retry_when: list[dict[str, Any]],
    do_not_retry_while: list[dict[str, Any]] | None = None,
    tool_name: str = "",
    task_title: str = "",
    causal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Teach unclaimable without an invoke. Same trail as attempt judgments.

    Pressure is inherited from the last trail row when present so later
    applications of the lesson do not require paying again.

    ``causal`` is an optional mapping of causal facts (causal_condition,
    causal_observed_failure, causal_verified_cause, causal_change_made,
    causal_observed_result, causal_scope) merged into the refusal record.
    It is inert when absent: the stored refusal is semantically identical to
    a refusal recorded without it.
    """
    import work_tree

    clean_id = str(branch_id or "").strip()
    why = _text(reason, 120)
    if not clean_id or not why:
        return {"ok": False, "reason": "missing_path"}
    branch = work_tree.get_branch(clean_id)
    if branch is None:
        return {"ok": False, "reason": "branch_missing"}
    payload = dict(branch.source_payload or {}) if isinstance(branch.source_payload, dict) else {}
    source_key = str(getattr(branch, "source_key", "") or "").strip()
    if source_key and not str(payload.get("source_key") or "").strip():
        payload["source_key"] = source_key
    existing = [dict(r) for r in list(payload.get(ATTEMPT_JUDGMENTS_KEY) or []) if isinstance(r, dict)]
    for row in reversed(existing):
        if _text(row.get("judgment"), 40).lower() != JUDGMENT_REFUSED:
            continue
        if _text(row.get("reason"), 120) != why:
            continue
        if judgment_still_suppresses(
            row,
            progress={},
            branch_payload=payload,
            source_key=source_key,
        ):
            return {"ok": True, "already": True, "judgment": row}
    prior = existing[-1] if existing else {}
    pressure = _refuse_pressure(prior)
    record = {
        "judgment": JUDGMENT_REFUSED,
        "reason": why,
        "tool": _norm_tool(tool_name),
        "task_title": _text(task_title, 200),
        "target_markers": [],
        "do_not_retry_while": [dict(c) for c in list(do_not_retry_while or []) if isinstance(c, dict)],
        "retry_when": [dict(c) for c in list(retry_when or []) if isinstance(c, dict)],
        "conditions": {"source_key": source_key},
        "pressure": pressure,
        "source": REFUSE_SOURCE,
    }
    if causal:
        record.update({str(k): v for k, v in dict(causal).items()})
    if not record["retry_when"]:
        return {"ok": False, "reason": "retry_when_required"}
    branch.source_payload = append_attempt_judgment(payload, record)
    try:
        work_tree.touch_branch(clean_id)
    except Exception:
        pass
    stored = list((branch.source_payload or {}).get(ATTEMPT_JUDGMENTS_KEY) or [])
    written = stored[-1] if stored else record
    return {"ok": True, "already": False, "judgment": written}


def branch_has_active_refuse(
    branch: Any,
    *,
    has_open_stem: bool = False,
    active_source_keys: set[str] | None = None,
) -> dict[str, Any] | None:
    """Active refused lesson on this branch, if the release contract has not fired."""
    payload = dict(getattr(branch, "source_payload", None) or {}) if isinstance(getattr(branch, "source_payload", None), dict) else {}
    source_key = str(getattr(branch, "source_key", "") or payload.get("source_key") or "").strip()
    progress: dict[str, Any] = {}
    try:
        import work_tree

        progress = dict(work_tree._branch_progress_payload(branch) or {})
    except Exception:
        progress = {}
    for row in reversed([dict(r) for r in list(payload.get(ATTEMPT_JUDGMENTS_KEY) or []) if isinstance(r, dict)]):
        if _text(row.get("judgment"), 40).lower() != JUDGMENT_REFUSED:
            continue
        if judgment_still_suppresses(
            row,
            progress=progress,
            branch_payload=payload,
            has_open_stem=has_open_stem,
            active_source_keys=active_source_keys,
            source_key=source_key,
        ):
            return row
    return None


def preferred_tool_from_progress(
    progress: dict[str, Any] | None,
    *,
    allowed_tools: list[str] | None = None,
    work_class: str = "",
    source_type: str = "",
) -> str:
    """First tool that can advance the next unsatisfied marker, if allowed."""
    payload = _as_dict(progress)
    allowed = {_norm_tool(t) for t in list(allowed_tools or []) if _norm_tool(t)}
    next_marker = payload.get("next_marker")
    if not isinstance(next_marker, dict):
        for row in list(payload.get("markers") or []):
            if isinstance(row, dict) and not row.get("counts"):
                next_marker = row
                break
    if not isinstance(next_marker, dict):
        return ""
    candidates: list[str] = []
    for key in ("verify_tools", "tools"):
        raw = next_marker.get(key)
        if isinstance(raw, (list, tuple)):
            candidates.extend(_norm_tool(t) for t in raw if _norm_tool(t))
    if not candidates:
        try:
            from services.work_tree_task_progress import get_ladder

            ladder = get_ladder(work_class=work_class, source_type=source_type)
            mid = _text(next_marker.get("id") or next_marker.get("marker_id"), 80)
            for marker in ladder.markers:
                if marker.marker_id == mid:
                    candidates.extend(_norm_tool(t) for t in marker.verify_tools if _norm_tool(t))
                    candidates.extend(_norm_tool(t) for t in marker.tools if _norm_tool(t))
                    break
        except Exception:
            candidates = []
    for tool in candidates:
        if not allowed or tool in allowed:
            return tool
    return ""


def align_branch_open_stem_to_trail(branch_id: str) -> dict[str, Any]:
    """Drop sequence stems already satisfied or still under reactivation suppress."""
    import work_tree
    from services.work_tree_signal_ingestion import (
        _sequence_item_satisfied,
        advance_branch_sequence_after_task,
    )

    clean_id = _text(branch_id, 80)
    if not clean_id:
        return {"ok": False, "reason": "missing_branch_id", "skipped": 0, "advanced": False}

    branch = work_tree.get_branch(clean_id)
    if branch is None:
        return {"ok": False, "reason": "branch_missing", "skipped": 0, "advanced": False}

    payload = (
        dict(branch.source_payload or {})
        if isinstance(getattr(branch, "source_payload", None), dict)
        else {}
    )
    sequence = [
        dict(item)
        for item in list(payload.get("task_sequence") or [])
        if isinstance(item, dict) and _text(item.get("title"), 200)
    ]
    if not sequence:
        return {"ok": True, "reason": "no_sequence", "skipped": 0, "advanced": False}

    judgments = [dict(r) for r in list(payload.get(ATTEMPT_JUDGMENTS_KEY) or []) if isinstance(r, dict)]
    progress = work_tree._branch_progress_payload(branch) or {}
    skipped = 0

    for _ in range(max(1, len(sequence) + 2)):
        open_tasks = [
            task
            for task in work_tree.list_branch_tasks(branch.branch_id)
            if str(getattr(getattr(task, "status", None), "value", getattr(task, "status", "")) or "")
            .strip()
            .lower()
            not in {"complete", "dropped", "attempted"}
        ]
        if not open_tasks:
            advanced = advance_branch_sequence_after_task(branch.branch_id)
            return {
                "ok": True,
                "reason": str(advanced.get("reason") or "advanced_after_empty"),
                "skipped": skipped,
                "advanced": bool(advanced.get("ok")),
                "task_id": str(advanced.get("task_id") or ""),
                "task_title": str(advanced.get("task_title") or ""),
            }

        current = open_tasks[0]
        title = _text(getattr(current, "title", ""), 200)
        meta = dict(getattr(current, "meta", {}) or {}) if isinstance(getattr(current, "meta", None), dict) else {}
        expected = _norm_tool(meta.get("expected_tool") or getattr(branch, "preferred_tool", ""))
        matching = next(
            (item for item in sequence if _text(item.get("title"), 200) == title),
            None,
        )
        if matching is None:
            return {
                "ok": True,
                "reason": "open_stem_not_in_sequence",
                "skipped": skipped,
                "advanced": False,
                "task_id": str(getattr(current, "task_id", "") or ""),
                "task_title": title,
            }

        # Skip stems that cannot productively advance the solution trail.
        # Coaching / explicit learn stems must not be trail-skipped: "read markers
        # already held" would drop teaching paths and keep Nova from the learn loop.
        coaching_stem = bool(meta.get("coaching_required") or meta.get("coaching"))
        match_tool = _norm_tool(matching.get("preferred_tool") or expected)
        work_class = str(getattr(branch, "work_class", "") or "")
        source_type = str(getattr(branch, "source_type", "") or "")
        skip_why = None
        if not coaching_stem:
            skip_why = sequence_item_should_skip_for_trail(
                tool_name=match_tool or expected,
                task_title=title,
                judgments=judgments,
                progress=progress,
                branch_payload=payload,
                work_class=work_class,
                source_type=source_type,
            )
        if skip_why is not None:
            judgment = _as_dict(skip_why.get("judgment"))
            work_tree.mark_task_dropped(
                current.task_id,
                reason=(
                    f"solution_trail:skip:{_text(skip_why.get('reason'), 40)}"
                    f":{_text(judgment.get('judgment') or judgment.get('reason') or skip_why.get('tool'), 120)}"
                ),
            )
            skipped += 1
            continue

        if not _sequence_item_satisfied(branch.branch_id, matching):
            # Prefer next-marker tools from the full sequence, not only the current stem's allowlist.
            # Otherwise trail stays trapped on read after early markers are held.
            sequence_tools: list[str] = []
            for item in sequence:
                for t in list(item.get("allowed_tools") or []):
                    nt = _norm_tool(t)
                    if nt and nt not in sequence_tools:
                        sequence_tools.append(nt)
                pt = _norm_tool(item.get("preferred_tool"))
                if pt and pt not in sequence_tools:
                    sequence_tools.append(pt)
            allowed = [
                _norm_tool(t)
                for t in list(meta.get("allowed_tools") or []) + list(getattr(branch, "allowed_tools", []) or [])
                if _norm_tool(t)
            ]
            progress = work_tree._branch_progress_payload(branch) or {}
            trail_tool = preferred_tool_from_progress(
                progress,
                allowed_tools=sequence_tools or allowed or None,
                work_class=work_class,
                source_type=source_type,
            )
            if trail_tool and action_suppressed_by_trail(
                tool_name=trail_tool,
                task_title=title,
                judgments=judgments,
                progress=progress,
                branch_payload=payload,
            ):
                trail_tool = ""
            # Next marker needs a different sequence stem — jump instead of retooling a dead title.
            # Do not jump off coaching stems (learn path is intentional order).
            if (
                not coaching_stem
                and trail_tool
                and trail_tool not in set(allowed)
                and trail_tool in set(sequence_tools)
            ):
                work_tree.mark_task_dropped(
                    current.task_id,
                    reason=f"solution_trail:jump_to_next_marker_tool:{trail_tool}",
                )
                skipped += 1
                continue
            tool_adjusted = False
            if (
                not coaching_stem
                and trail_tool
                and trail_tool != expected
                and (not allowed or trail_tool in allowed)
            ):
                meta["expected_tool"] = trail_tool
                if trail_tool not in list(meta.get("allowed_tools") or []):
                    meta["allowed_tools"] = [trail_tool] + [
                        t for t in list(meta.get("allowed_tools") or []) if _norm_tool(t) != trail_tool
                    ]
                work_tree.update_task_meta(current.task_id, meta)
                try:
                    work_tree.set_branch_tools(
                        branch.branch_id,
                        allowed_tools=list(meta.get("allowed_tools") or allowed) or [trail_tool],
                        preferred_tool=trail_tool,
                    )
                except Exception:
                    pass
                tool_adjusted = True
            return {
                "ok": True,
                "reason": "trail_step_active" + ("_tool_aligned" if tool_adjusted else ""),
                "skipped": skipped,
                "advanced": False,
                "task_id": str(current.task_id),
                "task_title": title,
                "preferred_tool": trail_tool or expected,
            }

        work_tree.mark_task_dropped(
            current.task_id,
            reason="solution_trail:sequence_step_already_satisfied",
        )
        skipped += 1

    advanced = advance_branch_sequence_after_task(branch.branch_id)
    return {
        "ok": True,
        "reason": "trail_skipped_satisfied_stems",
        "skipped": skipped,
        "advanced": bool(advanced.get("ok")),
        "task_id": str(advanced.get("task_id") or ""),
        "task_title": str(advanced.get("task_title") or ""),
    }
