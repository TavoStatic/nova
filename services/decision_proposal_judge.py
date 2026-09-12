"""Decision proposal + rule-based Judge (observation-first).

Contract: docs/DECISION_PROPOSAL_JUDGE.md

Actor proposes the move. Catalog/contracts define what it should change.
Judge challenges dimension-by-dimension. Disposition is from the controlling
weakness — not a blended confidence score. DecisionEpisode is durable on the
work item so prediction can be compared to evidence later.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from services.tool_identity import (
    FIND,
    LS,
    PULSE,
    READ,
    RELEASE_PROMOTION_JUDGMENT,
    RELEASE_REBUILD_VERIFY,
    RELEASE_RECORD_VALIDATION_OUTCOME,
    RELEASE_VALIDATION_RUN,
)

DISPOSITION_PROCEED = "proceed"
DISPOSITION_PROCEED_ANNOTATE = "proceed_annotate"
DISPOSITION_PAUSE_AND_SURFACE = "pause_and_surface"
DISPOSITION_ABORT_AND_FILE = "abort_and_file"

STATUS_CLEAR = "clear"
STATUS_CAUTION = "caution"
STATUS_FAIL = "fail"

ENFORCE_DISPOSITION_DEFAULT = False

# Per-dimension thresholds (score >= clear threshold → clear; >= caution → caution; else fail)
THRESHOLD_REVERSIBILITY = {"clear": 0.75, "caution": 0.45}
THRESHOLD_CONTEXT = {"clear": 0.80, "caution": 0.55}
THRESHOLD_ALIGNMENT = {"clear": 0.70, "caution": 0.40}

_READ_ONLY_TOOLS = frozenset(
    {
        READ,
        FIND,
        LS,
        PULSE,
        "health",
        "system_check",
        "queue_status",
        "os_capability",
        "core_health",
        "web_search",
        "web_fetch",
        "web_research",
        "web_gather",
        "wikipedia_lookup",
        "stackexchange_search",
        "guard_status",
        "pulse_status",
    }
)

_REVERSIBLE_WRITE_TOOLS = frozenset(
    {
        RELEASE_VALIDATION_RUN,
        RELEASE_REBUILD_VERIFY,
        RELEASE_RECORD_VALIDATION_OUTCOME,
        RELEASE_PROMOTION_JUDGMENT,
        "source_root_judgment",
        "generated_queue_run",
        "core_thinning",
        "patch_apply",
        "memory_hygiene",
    }
)

_DESTRUCTIVE_HINTS = (
    "delete",
    "rm ",
    "wipe",
    "drop_",
    "format",
    "destroy",
    "purge",
)

# capability_effect_map (v1): tool/action catalog. Missing tools fall back to actor_inferred.
_TOOL_CLAIM_CATALOG: dict[str, dict[str, Any]] = {
    RELEASE_VALIDATION_RUN: {
        "intended_effect": "Produce a current validation outcome for the selected release artifact.",
        "expected_evidence": [
            "validation record linked to the selected artifact with pass, pass-with-notes, or fail",
        ],
        "close_condition": (
            "selected artifact has a current validation outcome (pass / pass-with-notes / fail)"
        ),
        "evidence_sources": ["tool_contract", "release_validation_schema"],
    },
    RELEASE_REBUILD_VERIFY: {
        "intended_effect": "Rebuild and verify the release package against current source.",
        "expected_evidence": [
            "release rebuild/verify result with artifact path and readiness state",
        ],
        "close_condition": "release package rebuilt/verified with recorded readiness state",
        "evidence_sources": ["tool_contract"],
    },
    RELEASE_RECORD_VALIDATION_OUTCOME: {
        "intended_effect": "Record the validation outcome against the release ledger for the artifact.",
        "expected_evidence": ["ledger validation outcome entry for the selected artifact"],
        "close_condition": "validation outcome recorded on release ledger",
        "evidence_sources": ["tool_contract", "release_validation_schema"],
    },
    RELEASE_PROMOTION_JUDGMENT: {
        "intended_effect": "Judge promotion readiness from validation evidence.",
        "expected_evidence": ["promotion judgment verdict recorded"],
        "close_condition": "promotion judgment present for current package",
        "evidence_sources": ["tool_contract"],
    },
    READ: {
        "intended_effect": "Gather observation via read for the active work target.",
        "expected_evidence": ["read evidence row recorded on the active branch"],
        "close_condition": "read evidence recorded for the target path",
        "evidence_sources": ["tool_contract"],
    },
    FIND: {
        "intended_effect": "Locate paths/content via find for the active work target.",
        "expected_evidence": ["find evidence row recorded on the active branch"],
        "close_condition": "find evidence recorded",
        "evidence_sources": ["tool_contract"],
    },
    LS: {
        "intended_effect": "List directory contents for the active work target.",
        "expected_evidence": ["ls evidence row recorded on the active branch"],
        "close_condition": "ls evidence recorded",
        "evidence_sources": ["tool_contract"],
    },
    PULSE: {
        "intended_effect": "Sample current runtime pulse status.",
        "expected_evidence": ["pulse status payload recorded"],
        "close_condition": "fresh pulse observation available",
        "evidence_sources": ["tool_contract"],
    },
    "source_root_judgment": {
        "intended_effect": "Synthesize source-root judgment from collected branch evidence.",
        "expected_evidence": ["source_root_judgment evidence with verdict"],
        "close_condition": "source_root_judgment recorded on branch",
        "evidence_sources": ["tool_contract"],
    },
}

_ACTION_CLAIM_CATALOG: dict[str, dict[str, Any]] = {
    "guard_start": {
        "intended_effect": "Restore the runtime guard so maintenance ticks can resume.",
        "expected_evidence": ["guard status running=true with live pid"],
        "close_condition": "runtime guard is running",
        "evidence_sources": ["capability_effect_map"],
    },
    "autonomy_maintenance_start": {
        "intended_effect": "Start autonomy maintenance worker under runtime policy.",
        "expected_evidence": ["maintenance worker active or cycle launched"],
        "close_condition": "maintenance scheduler/worker active",
        "evidence_sources": ["capability_effect_map"],
    },
    "generated_queue_run_next": {
        "intended_effect": "Run the next generated-queue item and record its outcome.",
        "expected_evidence": ["generated queue run result for the selected item"],
        "close_condition": "selected generated-queue item has a recorded outcome",
        "evidence_sources": ["capability_effect_map"],
    },
    "patch_queue_run_next": {
        "intended_effect": "Advance the next patch-queue item under policy.",
        "expected_evidence": ["patch queue step result recorded"],
        "close_condition": "selected patch-queue item advanced with evidence",
        "evidence_sources": ["capability_effect_map"],
    },
    "generated_queue_investigate": {
        "intended_effect": "Investigate generated-queue pressure without mutation.",
        "expected_evidence": ["investigation notes or queue status evidence"],
        "close_condition": "investigation evidence recorded",
        "evidence_sources": ["capability_effect_map"],
    },
    "active_work_tree_run_next": {
        "intended_effect": "Advance one governed active-work step using the recommended tool.",
        "expected_evidence": [
            "work-tree evidence for the recommended tool",
            "task or branch progress update",
        ],
        "close_condition": "active work step advanced or recorded expected evidence",
        "evidence_sources": ["capability_effect_map"],
    },
}


from services.type_utils import _as_dict, _as_list, _text


def _clamp01(value: float) -> float:
    try:
        number = float(value)
    except Exception:
        return 0.0
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return number


def _status_for_score(score: float, thresholds: dict[str, float]) -> str:
    if score >= float(thresholds.get("clear", 0.8)):
        return STATUS_CLEAR
    if score >= float(thresholds.get("caution", 0.5)):
        return STATUS_CAUTION
    return STATUS_FAIL


def _tool_name_from_action(action: dict[str, Any]) -> str:
    return _text(
        action.get("recommended_tool")
        or action.get("tool")
        or action.get("tool_name")
        or "",
        120,
    )


def derive_claim_fields(
    *,
    action_id: str,
    tool_name: str,
    actor_text: str = "",
    pressure_close_condition: str = "",
) -> dict[str, Any]:
    """Derive claim fields with explicit field_sources (never silent actor authorship)."""
    tool_claim = dict(_TOOL_CLAIM_CATALOG.get(tool_name) or {})
    action_claim = dict(_ACTION_CLAIM_CATALOG.get(action_id) or {})

    field_sources: dict[str, Any] = {
        "close_condition": "none",
        "intended_effect": "actor_inferred",
        "expected_evidence": [],
    }

    # Close condition: pressure first, then catalog.
    close = _text(pressure_close_condition, 400)
    if close:
        field_sources["close_condition"] = "pressure_record"
    else:
        close = _text(tool_claim.get("close_condition") or action_claim.get("close_condition"), 400)
        if close:
            field_sources["close_condition"] = (
                "capability_effect_map" if tool_claim.get("close_condition") or action_claim.get("close_condition") else "none"
            )
        else:
            close = None
            field_sources["close_condition"] = "none"

    # Intended effect: capability map first; else actor_inferred.
    intended = _text(tool_claim.get("intended_effect") or action_claim.get("intended_effect"), 500)
    if intended:
        field_sources["intended_effect"] = "capability_effect_map"
    else:
        intended = _text(actor_text, 500) or (
            f"Execute governed action {action_id}." if action_id else "Execute the selected autonomy action."
        )
        field_sources["intended_effect"] = "actor_inferred"

    # Expected evidence: catalog / tool contract; else actor_inferred shell.
    expected = [
        _text(item, 240)
        for item in _as_list(tool_claim.get("expected_evidence") or action_claim.get("expected_evidence"))
        if _text(item, 240)
    ]
    ev_sources = [
        _text(s, 80)
        for s in _as_list(tool_claim.get("evidence_sources") or action_claim.get("evidence_sources"))
        if _text(s, 80)
    ]
    if expected:
        field_sources["expected_evidence"] = ev_sources or ["capability_effect_map"]
    else:
        expected = [f"execution result for {action_id or tool_name or 'action'}"]
        field_sources["expected_evidence"] = ["actor_inferred"]

    return {
        "intended_effect": intended,
        "expected_evidence": expected,
        "close_condition": close,
        "field_sources": field_sources,
    }


def build_decision_proposal(
    *,
    action: dict[str, Any] | None,
    packet: dict[str, Any] | None = None,
    pressure_id: str = "",
    pressure_close_condition: str = "",
) -> dict[str, Any]:
    action = _as_dict(action)
    packet = _as_dict(packet)
    action_type = _text(action.get("action_type") or action.get("action"), 120)
    tool_name = _tool_name_from_action(action)
    arguments: dict[str, Any] = {}
    for key in (
        "target_id",
        "target_step_id",
        "target_tree_id",
        "target_kind",
        "max_steps",
        "max_trees",
        "recommended_tool",
        "path",
    ):
        if key in action and action.get(key) not in (None, ""):
            arguments[key] = action.get(key)

    actor_reason = _text(
        action.get("reason")
        or action.get("reason_code")
        or packet.get("explain_text")
        or packet.get("reason"),
        400,
    )
    actor_text = _text(
        action.get("expected_effect") or action.get("intended_effect") or "",
        500,
    )
    pressure = _text(pressure_id, 200) or _text(
        action.get("reason_code") or packet.get("pressure_id"),
        200,
    )
    close_from_pressure = _text(
        pressure_close_condition
        or action.get("close_condition")
        or packet.get("close_condition"),
        400,
    )
    # Only treat packet/action close_condition as pressure_record when explicitly keyed.
    if close_from_pressure and not pressure_close_condition and not packet.get("close_condition"):
        # action.close_condition without pressure context is catalog-derived later
        close_from_pressure = ""

    claim = derive_claim_fields(
        action_id=action_type,
        tool_name=tool_name,
        actor_text=actor_text,
        pressure_close_condition=pressure_close_condition
        or _text(packet.get("close_condition"), 400),
    )

    return {
        "pressure_id": pressure,
        "action_id": action_type,
        "tool_name": tool_name,
        "arguments": arguments,
        "actor_reason": actor_reason,
        "close_condition": claim.get("close_condition"),
        "intended_effect": claim["intended_effect"],
        "expected_evidence": list(claim["expected_evidence"]),
        "field_sources": dict(claim.get("field_sources") or {}),
    }


def _reversibility_score(tool_name: str, action_id: str) -> tuple[float, str]:
    blob = f"{tool_name} {action_id}".lower()
    if any(hint in blob for hint in _DESTRUCTIVE_HINTS):
        return 0.15, "action looks destructive or hard to reverse"
    if tool_name in _READ_ONLY_TOOLS or action_id in {
        "pulse_status",
        "guard_status",
        "generated_queue_investigate",
    }:
        return 0.95, "read-only / observational action"
    if tool_name in _REVERSIBLE_WRITE_TOOLS or action_id in {
        "active_work_tree_run_next",
        "generated_queue_run_next",
        "patch_queue_run_next",
        "guard_start",
        "autonomy_maintenance_start",
    }:
        return 0.7, "mutating but generally recoverable / snapshot-backed"
    if not tool_name and action_id:
        return 0.65, "action-level mutation without tool detail"
    return 0.45, "unknown mutation class; treat with caution"


def _context_score(proposal: dict[str, Any]) -> tuple[float, list[str], str]:
    missing: list[str] = []
    action_id = _text(proposal.get("action_id"), 120)
    tool_name = _text(proposal.get("tool_name"), 120)
    args = _as_dict(proposal.get("arguments"))
    sources = _as_dict(proposal.get("field_sources"))

    if action_id == "active_work_tree_run_next":
        if not _text(args.get("target_id") or args.get("target_tree_id"), 160):
            missing.append("active work target_id/tree_id unresolved")
        if not tool_name:
            missing.append("recommended_tool missing for active work step")
        if tool_name in {READ, FIND, LS} and not (
            _text(args.get("path"), 240) or _text(args.get("target_step_id"), 160)
        ):
            missing.append("path/target_step not on proposal (may resolve at execution)")

    if _text(sources.get("intended_effect"), 40) == "actor_inferred":
        missing.append("intended_effect is actor_inferred (no capability_effect_map entry)")
    if "actor_inferred" in [
        _text(s, 40) for s in _as_list(sources.get("expected_evidence"))
    ]:
        missing.append("expected_evidence is actor_inferred")

    hard = [
        item
        for item in missing
        if "may resolve" not in item and "actor_inferred" not in item
    ]
    soft = [item for item in missing if item not in hard]
    if hard:
        score = max(0.2, 0.85 - 0.25 * len(hard))
        reason = "required context incomplete"
    elif soft:
        score = 0.68
        reason = "context present with soft provenance gaps"
    else:
        score = 0.9
        reason = "required context present on proposal"
    return _clamp01(score), missing, reason


def _alignment_score(proposal: dict[str, Any]) -> tuple[float, str, bool]:
    """Return score, reason, close_condition_absent."""
    intended = _text(proposal.get("intended_effect"), 500).lower()
    close = _text(proposal.get("close_condition"), 400).lower()
    pressure = _text(proposal.get("pressure_id"), 200).lower()
    sources = _as_dict(proposal.get("field_sources"))
    action_id = _text(proposal.get("action_id"), 120)
    tool_name = _text(proposal.get("tool_name"), 120)

    close_absent = not bool(close)
    if close_absent:
        # No scoring target → caution, not clear. Incomplete context for alignment.
        return 0.5, "no close condition; alignment cannot be clear", True

    if not intended:
        return 0.3, "no intended effect", False

    score = 0.5
    notes: list[str] = []
    if _text(sources.get("intended_effect"), 40) == "capability_effect_map":
        score += 0.15
        notes.append("intended_effect from capability_effect_map")
    elif _text(sources.get("intended_effect"), 40) == "actor_inferred":
        score -= 0.1
        notes.append("intended_effect actor_inferred — weight lower")

    close_tokens = [t for t in close.split() if len(t) > 4]
    if close_tokens and any(t in intended for t in close_tokens[:8]):
        score += 0.15
        notes.append("intended effect relates to close condition")

    if pressure:
        parts = [p for p in pressure.replace(":", "_").split("_") if len(p) > 4]
        if any(p in intended for p in parts[:6]):
            score += 0.1
            notes.append("pressure related to claim")

    if action_id == "active_work_tree_run_next" and tool_name:
        score += 0.05
    if action_id == "guard_start" and "guard" in intended:
        score += 0.1
        notes.append("guard restore claim")

    if not notes:
        notes.append("weak alignment signals")
    return _clamp01(score), "; ".join(notes), False


def _similar_failed_attempts(proposal: dict[str, Any], history: list[dict[str, Any]] | None) -> int:
    if not history:
        return 0
    action_id = _text(proposal.get("action_id"), 120)
    tool_name = _text(proposal.get("tool_name"), 120)
    target = _text(_as_dict(proposal.get("arguments")).get("target_id"), 160)
    count = 0
    for row in history:
        item = _as_dict(row)
        if _text(item.get("action_id") or item.get("action_type"), 120) != action_id:
            continue
        if tool_name and _text(item.get("tool_name") or item.get("recommended_tool"), 120) not in {
            "",
            tool_name,
        }:
            continue
        if target and _text(item.get("target_id"), 160) not in {"", target}:
            continue
        if item.get("close_condition_remained_false") is True:
            count += 1
            continue
        if item.get("progress_moved") is False:
            count += 1
            continue
        if _text(item.get("progress_moved"), 20).lower() in {"0", "false", "no"}:
            count += 1
            continue
        if _text(item.get("result"), 40).lower() == "failed":
            count += 1
    return count


def _dimension(
    *,
    score: float,
    thresholds: dict[str, float],
    reason: str,
    force_status: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = force_status or _status_for_score(score, thresholds)
    body = {
        "score": _clamp01(score),
        "threshold": float(thresholds.get("clear", 0.7)),
        "status": status,
        "reason": reason,
    }
    if extra:
        body.update(extra)
    return body


def _disposition_from_statuses(
    *,
    rev: dict[str, Any],
    ctx: dict[str, Any],
    align: dict[str, Any],
    failed: int,
    missing: list[str],
) -> tuple[str, str, dict[str, Any] | None, list[str]]:
    """Disposition from controlling weakness (dimension status), not blended score."""
    annotations: list[str] = []

    if align.get("status") == STATUS_FAIL:
        return (
            DISPOSITION_ABORT_AND_FILE,
            "mission_alignment",
            {
                "kind": "reject_move",
                "reason": "mission_alignment failed",
                "resume_condition": "new proposal that serves current pressure",
                "mission_aborted": False,
            },
            annotations,
        )

    if ctx.get("status") == STATUS_FAIL:
        hard = [m for m in missing if "may resolve" not in m]
        return (
            DISPOSITION_PAUSE_AND_SURFACE,
            "context_completeness",
            {
                "kind": "gather_context",
                "missing_context": hard or list(missing) or ["context fail"],
                "resolution_action": _resolution_for_missing(hard or missing),
                "resume_condition": "missing context resolved and proposal re-judged",
            },
            annotations,
        )

    if failed >= 2:
        return (
            DISPOSITION_PAUSE_AND_SURFACE,
            "attempt_history",
            {
                "kind": "reassess_after_non_solution",
                "missing_context": [
                    f"same move failed or non-solving {failed} times under similar targets"
                ],
                "resolution_action": "inspect prior attempt evidence and world delta before retry",
                "resume_condition": "world state materially changed or alternative move proposed",
            },
            [f"similar_failed_attempts={failed}"],
        )

    if rev.get("status") == STATUS_FAIL:
        # Reversibility fail: annotate or pause depending on severity (score).
        if float(rev.get("score") or 0) < 0.3:
            return (
                DISPOSITION_PAUSE_AND_SURFACE,
                "reversibility",
                {
                    "kind": "reassess_risk",
                    "missing_context": ["action appears poorly reversible"],
                    "resolution_action": "choose a safer observation or snapshot-backed path first",
                    "resume_condition": "safer move proposed or operator accepts risk",
                },
                annotations,
            )
        annotations.append("low reversibility; proceed only with caution if annotated")
        return DISPOSITION_PROCEED_ANNOTATE, "reversibility", None, annotations

    # Caution on any dimension → annotate
    cautions = [
        name
        for name, dim in (
            ("mission_alignment", align),
            ("context_completeness", ctx),
            ("reversibility", rev),
        )
        if dim.get("status") == STATUS_CAUTION
    ]
    if failed == 1:
        cautions.append("attempt_history")
        annotations.append("prior similar non-solution attempt=1")
    if cautions:
        # controlling = first in priority order for cautions
        order = ["mission_alignment", "context_completeness", "reversibility", "attempt_history"]
        controlling = next((c for c in order if c in cautions), cautions[0])
        if ctx.get("status") == STATUS_CAUTION:
            annotations.extend([m for m in missing if "actor_inferred" in m or "may resolve" in m])
        if align.get("status") == STATUS_CAUTION:
            annotations.append(str(align.get("reason") or "alignment caution"))
        if rev.get("status") == STATUS_CAUTION:
            annotations.append(str(rev.get("reason") or "reversibility caution"))
        return DISPOSITION_PROCEED_ANNOTATE, controlling, None, annotations

    return DISPOSITION_PROCEED, "none", None, annotations


def judge_proposal(
    proposal: dict[str, Any] | None,
    *,
    attempt_history: list[dict[str, Any]] | None = None,
    enforce_disposition: bool = ENFORCE_DISPOSITION_DEFAULT,
) -> dict[str, Any]:
    proposal = _as_dict(proposal)
    rev_score, rev_reason = _reversibility_score(
        _text(proposal.get("tool_name"), 120),
        _text(proposal.get("action_id"), 120),
    )
    ctx_score, missing, ctx_reason = _context_score(proposal)
    align_score, align_reason, close_absent = _alignment_score(proposal)
    failed = _similar_failed_attempts(proposal, attempt_history)

    rev = _dimension(
        score=rev_score,
        thresholds=THRESHOLD_REVERSIBILITY,
        reason=rev_reason,
    )
    ctx = _dimension(
        score=ctx_score,
        thresholds=THRESHOLD_CONTEXT,
        reason=ctx_reason,
        extra={"missing": missing},
    )
    # Hard context miss forces fail even if soft score mid-band
    hard_missing = [m for m in missing if "may resolve" not in m and "actor_inferred" not in m]
    if hard_missing:
        ctx["status"] = STATUS_FAIL
        ctx["reason"] = "required context incomplete"
    align = _dimension(
        score=align_score,
        thresholds=THRESHOLD_ALIGNMENT,
        reason=align_reason,
        force_status=STATUS_CAUTION if close_absent else None,
    )

    disposition, controlling, resolution, annotations = _disposition_from_statuses(
        rev=rev,
        ctx=ctx,
        align=align,
        failed=failed,
        missing=missing,
    )

    # Analytics only — never used for execution decisions.
    summary_score = _clamp01(min(rev_score, ctx_score, align_score))

    return {
        "reversibility": rev,
        "context_completeness": ctx,
        "mission_alignment": align,
        "similar_failed_attempts": failed,
        "disposition": disposition,
        "controlling_dimension": controlling,
        "resolution_action": resolution,
        "annotations": annotations,
        "summary_score": summary_score,
        "confidence": summary_score,  # alias for older readers; not decision truth
        "weakest_dimension": controlling,  # alias
        "observation_only": not bool(enforce_disposition),
        "enforce_disposition": bool(enforce_disposition),
    }


def _resolution_for_missing(missing: list[str]) -> str:
    joined = " ".join(missing).lower()
    if "tool" in joined:
        return "resolve recommended_tool from active work branch next_step"
    if "target" in joined or "tree" in joined:
        return "inspect active work tree snapshot for executable branch identity"
    if "artifact" in joined or "path" in joined:
        return "inspect current package ledger / release status for artifact identity"
    if "actor_inferred" in joined or "capability" in joined:
        return "add capability_effect_map entry for this tool/action or gather contract evidence"
    return "gather the listed missing context, then re-judge the proposal"


def should_block_execution(report: dict[str, Any] | None) -> bool:
    report = _as_dict(report)
    if not bool(report.get("enforce_disposition")):
        return False
    if not report.get("resolution_action") and _text(report.get("disposition"), 40) in {
        DISPOSITION_PAUSE_AND_SURFACE,
        DISPOSITION_ABORT_AND_FILE,
    }:
        # Never silent-block without resolution.
        return False
    return _text(report.get("disposition"), 40) in {
        DISPOSITION_PAUSE_AND_SURFACE,
        DISPOSITION_ABORT_AND_FILE,
    }


def compute_judge_was_useful(
    *,
    disposition: str,
    predicate_moved: bool | None,
) -> bool | None:
    """Automatic usefulness rule. None when predicate_moved still unknown."""
    if predicate_moved is None:
        return None
    disp = _text(disposition, 40)
    if disp in {DISPOSITION_PROCEED, DISPOSITION_PROCEED_ANNOTATE}:
        return bool(predicate_moved) is True
    if disp in {DISPOSITION_PAUSE_AND_SURFACE, DISPOSITION_ABORT_AND_FILE}:
        return bool(predicate_moved) is False
    return None


def attach_outcome(
    report: dict[str, Any] | None,
    *,
    execution_result: str = "",
    execution_ok: bool | None = None,
    close_condition_remained_false: bool | None = None,
    progress_moved: bool | None = None,
    expected_evidence_found: bool | None = None,
) -> dict[str, Any]:
    report = dict(_as_dict(report))
    predicate_moved: bool | None
    if progress_moved is not None:
        predicate_moved = bool(progress_moved)
    elif close_condition_remained_false is True:
        predicate_moved = False
    elif close_condition_remained_false is False:
        predicate_moved = True
    else:
        predicate_moved = None

    judge_was_useful = compute_judge_was_useful(
        disposition=_text(report.get("disposition"), 40),
        predicate_moved=predicate_moved,
    )
    report["outcome"] = {
        "execution_result": _text(execution_result, 80),
        "execution_ok": execution_ok,
        "close_condition_remained_false": close_condition_remained_false,
        "progress_moved": progress_moved,
        "expected_evidence_found": expected_evidence_found,
        "predicate_moved": predicate_moved,
        "judge_was_useful": judge_was_useful,
        "judge_disposition": _text(report.get("disposition"), 40),
        "controlling_dimension": _text(report.get("controlling_dimension"), 40),
        "summary_score": report.get("summary_score"),
    }
    return report


def build_decision_episode(
    *,
    proposal: dict[str, Any] | None,
    judge_report: dict[str, Any] | None,
    execution: dict[str, Any] | None = None,
    observed_evidence: list[dict] | None = None,
    close_condition_before: bool | None = None,
    close_condition_after: bool | None = None,
    expected_evidence_found: bool | None = None,
) -> dict[str, Any]:
    proposal = _as_dict(proposal)
    judge_report = _as_dict(judge_report)
    disposition = _text(judge_report.get("disposition"), 40)
    predicate_moved: bool | None = None
    if close_condition_before is not None and close_condition_after is not None:
        predicate_moved = bool(close_condition_after) and not bool(close_condition_before)
        if close_condition_before is False and close_condition_after is False:
            predicate_moved = False
        if close_condition_before is True and close_condition_after is True:
            predicate_moved = False
        if close_condition_before is False and close_condition_after is True:
            predicate_moved = True
        if close_condition_before is True and close_condition_after is False:
            predicate_moved = True  # moved the wrong way still "moved"
    outcome = _as_dict(judge_report.get("outcome"))
    if predicate_moved is None and outcome.get("predicate_moved") is not None:
        predicate_moved = bool(outcome.get("predicate_moved"))

    if expected_evidence_found is None and outcome.get("expected_evidence_found") is not None:
        expected_evidence_found = bool(outcome.get("expected_evidence_found"))

    judge_was_useful = compute_judge_was_useful(
        disposition=disposition,
        predicate_moved=predicate_moved,
    )

    return {
        "episode_id": f"de_{uuid.uuid4().hex[:12]}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "proposal": dict(proposal),
        "judge_report": dict(judge_report),
        "disposition": disposition,
        "execution": dict(execution) if isinstance(execution, dict) else execution,
        "observed_evidence": list(observed_evidence or []),
        "close_condition_before": close_condition_before,
        "close_condition_after": close_condition_after,
        "prediction_outcome": {
            "expected_evidence_found": expected_evidence_found,
            "predicate_moved": predicate_moved,
            "judge_was_useful": judge_was_useful,
        },
    }


def evaluate_recommendation_packet(
    packet: dict[str, Any] | None,
    *,
    attempt_history: list[dict[str, Any]] | None = None,
    enforce_disposition: bool = ENFORCE_DISPOSITION_DEFAULT,
    pressure_close_condition: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    packet = _as_dict(packet)
    action = _as_dict(packet.get("recommended_action") or packet.get("action"))
    proposal = build_decision_proposal(
        action=action,
        packet=packet,
        pressure_close_condition=pressure_close_condition,
    )
    report = judge_proposal(
        proposal,
        attempt_history=attempt_history,
        enforce_disposition=enforce_disposition,
    )
    return proposal, report


def persist_decision_episode(
    episode: dict[str, Any] | None,
    *,
    proposal: dict[str, Any] | None = None,
    work_tree_module: Any = None,
) -> dict[str, Any]:
    """Persist DecisionEpisode on task meta or branch trail."""
    episode = _as_dict(episode)
    proposal = _as_dict(proposal or episode.get("proposal"))
    args = _as_dict(proposal.get("arguments"))
    task_id = _text(args.get("target_step_id"), 160)
    branch_id = _text(args.get("target_id"), 160)

    if work_tree_module is None:
        try:
            import work_tree as work_tree_module
        except Exception as exc:
            return {"ok": False, "error": f"work_tree_import:{exc}"}

    if task_id and hasattr(work_tree_module, "update_task_meta"):
        try:
            work_tree_module.update_task_meta(
                task_id,
                {
                    "last_decision_episode": dict(episode),
                    "decision_proposal": dict(proposal),
                    "decision_judge": dict(_as_dict(episode.get("judge_report"))),
                },
            )
            # Keep a short trail on the task.
            task = None
            if hasattr(work_tree_module, "_TASKS"):
                task = work_tree_module._TASKS.get(task_id)
            if task is not None:
                meta = dict(getattr(task, "meta", None) or {})
                trail = list(meta.get("decision_episodes") or [])
                trail.append(dict(episode))
                meta["decision_episodes"] = trail[-12:]
                task.meta = meta
                if hasattr(work_tree_module, "update_task_meta"):
                    work_tree_module.update_task_meta(task_id, {"decision_episodes": meta["decision_episodes"]})
            return {"ok": True, "task_id": task_id, "branch_id": branch_id}
        except Exception as exc:
            return {"ok": False, "task_id": task_id, "error": str(exc)[:200]}

    if branch_id and hasattr(work_tree_module, "get_branch"):
        try:
            branch = work_tree_module.get_branch(branch_id)
            if branch is None:
                return {"ok": False, "branch_id": branch_id, "error": "branch_not_found"}
            payload = dict(getattr(branch, "source_payload", None) or {})
            trail = list(payload.get("decision_episodes") or [])
            trail.append(dict(episode))
            payload["decision_episodes"] = trail[-12:]
            payload["last_decision_episode"] = dict(episode)
            payload["last_decision_proposal"] = dict(proposal)
            payload["last_decision_judge"] = dict(_as_dict(episode.get("judge_report")))
            branch.source_payload = payload
            if hasattr(work_tree_module, "touch_branch"):
                work_tree_module.touch_branch(branch_id)
            if hasattr(work_tree_module, "_persist_tree_state"):
                tree_id = str(getattr(branch, "tree_id", "") or "")
                if tree_id:
                    work_tree_module._persist_tree_state(tree_id)
            return {"ok": True, "branch_id": branch_id}
        except Exception as exc:
            return {"ok": False, "branch_id": branch_id, "error": str(exc)[:200]}

    return {"ok": False, "error": "no_task_or_branch_target"}


# Back-compat name used by earlier wiring.
def persist_judge_on_work_item(
    proposal: dict[str, Any] | None,
    report: dict[str, Any] | None,
    *,
    work_tree_module: Any = None,
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    episode = build_decision_episode(
        proposal=proposal,
        judge_report=report,
        execution=execution,
    )
    return persist_decision_episode(
        episode,
        proposal=proposal,
        work_tree_module=work_tree_module,
    )
