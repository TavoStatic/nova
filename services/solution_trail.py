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

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

ATTEMPT_JUDGMENTS_KEY = "attempt_judgments"
MAX_ATTEMPT_JUDGMENTS = 24

JUDGMENT_PROVEN = "proven"
JUDGMENT_REDUNDANT = "redundant"
JUDGMENT_PREMATURE = "premature"

_SUPPRESSING = frozenset({JUDGMENT_REDUNDANT, JUDGMENT_PREMATURE})


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
    return False


def judgment_still_suppresses(
    judgment: dict[str, Any],
    *,
    progress: dict[str, Any] | None,
    branch_payload: dict[str, Any] | None = None,
) -> bool:
    """True while reactivation contract has not fired."""
    row = _as_dict(judgment)
    klass = _text(row.get("judgment"), 40).lower()
    if klass not in _SUPPRESSING:
        return False
    holding = _holding_map(progress)
    package_identity = _package_identity(_as_dict(branch_payload))
    # Prefer explicit retry_when: suppress until ALL retry clauses hold.
    retry_when = [dict(c) for c in list(row.get("retry_when") or []) if isinstance(c, dict)]
    if retry_when:
        return not all(
            _clause_holds(c, holding=holding, package_identity=package_identity) for c in retry_when
        )
    # Fallback: suppress while any do_not_retry_while holds.
    blockers = [dict(c) for c in list(row.get("do_not_retry_while") or []) if isinstance(c, dict)]
    if blockers:
        return any(_clause_holds(c, holding=holding, package_identity=package_identity) for c in blockers)
    # Redundant with empty contract: suppress only if still no work needed (conservative).
    return klass == JUDGMENT_REDUNDANT


def action_suppressed_by_trail(
    *,
    tool_name: str = "",
    task_title: str = "",
    judgments: list[dict[str, Any]] | None = None,
    progress: dict[str, Any] | None = None,
    branch_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return the active suppressing judgment for this tool/title, if any."""
    tool = _norm_tool(tool_name)
    title = _text(task_title, 200).lower()
    if not tool and not title:
        return None
    rows = [dict(r) for r in list(judgments or []) if isinstance(r, dict)]
    for row in reversed(rows):
        j_tool = _norm_tool(row.get("tool"))
        j_title = _text(row.get("task_title"), 200).lower()
        if tool and j_tool:
            if tool != j_tool:
                continue
        elif title and j_title:
            if title != j_title:
                continue
        else:
            continue
        if not judgment_still_suppresses(row, progress=progress, branch_payload=branch_payload):
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
            not in {"complete", "dropped"}
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
