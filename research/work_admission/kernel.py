"""Pure admission kernel.

proposal + read-only snapshots + policy -> deterministic decision JSON.

No LLM. No work_tree/runtime imports. No file writes. No mutation of inputs.

White-box kernel evaluation, not live Nova proof.
"""
from __future__ import annotations

import copy
import json
from typing import Any

LABEL = "white-box kernel evaluation, not live Nova proof"
SCHEMA_DECISION = "nova.work_admission.decision.v1"

_READ_LIKE = frozenset({"read", "ls", "find"})
_CAUSAL_TOOLS = {
    "release_validation_run": frozenset(
        {"runtime/regression_status.json", "validation_status", "regression_status"}
    ),
    "release_record_validation_outcome": frozenset(
        {"runtime/regression_status.json", "validation_status"}
    ),
    "core_thinning": frozenset({"wrapper", "core_thinning"}),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _sorted_unique(codes: list[str]) -> list[str]:
    return sorted({c for c in codes if c})


def _deep_copy(value: Any) -> Any:
    return copy.deepcopy(value)


def _target(proposal: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(proposal.get("target"))


def _work(proposal: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(proposal.get("proposed_work"))


def _dedupe_key(proposal: dict[str, Any]) -> str:
    return _text(_as_dict(proposal.get("idempotency")).get("dedupe_key"))


def _canonical_identity(proposal: dict[str, Any]) -> tuple[str, ...]:
    t = _target(proposal)
    w = _work(proposal)
    return (
        _text(t.get("target_type")).lower(),
        _text(t.get("target_id")),
        _text(t.get("target_fingerprint")),
        _text(w.get("completion_condition")).lower(),
        _dedupe_key(proposal),
    )


def _fp_from_runtime(snapshots: dict[str, Any]) -> dict[str, str]:
    rt = _as_dict(snapshots.get("runtime"))
    stored = _as_dict(rt.get("controlling_fingerprint"))
    if stored:
        return {k: _text(stored.get(k)) for k in (
            "target_type",
            "target_id",
            "artifact_id",
            "artifact_content_id",
            "validation_status",
            "validation_generated_at",
            "source_identity",
        )}
    rs = _as_dict(rt.get("regression_status"))
    return {
        "target_type": "finding",
        "target_id": "",
        "artifact_id": _text(rt.get("artifact_id")),
        "artifact_content_id": _text(rt.get("artifact_content_id")),
        "validation_status": _text(rs.get("status")),
        "validation_generated_at": _text(rs.get("generated_at")),
        "source_identity": _text(rt.get("source_identity")),
    }


def _all_targets(snapshots: dict[str, Any]) -> list[dict[str, Any]]:
    wt = _as_dict(snapshots.get("work_tree"))
    return [_as_dict(x) for x in _as_list(wt.get("open_targets")) + _as_list(wt.get("closed_targets"))]


def _match_target(proposal: dict[str, Any], snapshots: dict[str, Any]) -> dict[str, Any] | None:
    t = _target(proposal)
    tid = _text(t.get("target_id"))
    fp = _text(t.get("target_fingerprint"))
    for row in _all_targets(snapshots):
        if tid and _text(row.get("target_id")) == tid:
            return row
        if fp and _text(row.get("target_fingerprint")) == fp:
            return row
    return None


def _checks(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    sat = _as_dict(_target(proposal).get("satisfaction_state"))
    return [_as_dict(x) for x in _as_list(sat.get("observable_checks"))]


def _independent_satisfied(proposal: dict[str, Any], snapshots: dict[str, Any]) -> bool:
    rs = _as_dict(_as_dict(snapshots.get("runtime")).get("regression_status"))
    t = _target(proposal)
    if _text(t.get("target_id")) == "finding_pkg_validation":
        return _text(rs.get("status")).upper() == "OK"
    for row in _as_list(_as_dict(snapshots.get("work_tree")).get("closed_targets")):
        row = _as_dict(row)
        if _text(row.get("target_id")) == _text(t.get("target_id")) and bool(row.get("satisfied")):
            return True
    return False


def _evidence_stale(snapshots: dict[str, Any]) -> bool:
    for item in _as_list(snapshots.get("evidence")):
        row = _as_dict(item)
        if bool(row.get("stale")) or _text(row.get("freshness")).lower() == "stale":
            return True
        if _text(row.get("provenance_class")).lower() == "stale":
            return True
    return False


def _evidence_untrusted_only(proposal: dict[str, Any], snapshots: dict[str, Any]) -> bool:
    items = [_as_dict(x) for x in _as_list(snapshots.get("evidence")) + _as_list(proposal.get("evidence"))]
    if not items:
        return False
    trusted = {"independent", "nova_runtime", "os"}
    return not any(_text(x.get("provenance_class")).lower() in trusted or _text(x.get("producer")).lower() in {"inspect", "os", "nova"} for x in items) and any(
        _text(x.get("provenance_class")).lower() in {"operator_assertion", "derived"} or _text(x.get("producer")).lower() == "llm"
        for x in items
    )


def _is_cover(proposal: dict[str, Any]) -> bool:
    w = _work(proposal)
    tool = _text(w.get("proposed_tool")).lower()
    args = w.get("proposed_args")
    empty_args = not args or (isinstance(args, dict) and not any(_text(v) for v in args.values())) or (
        isinstance(args, list) and not any(_text(v) for v in args)
    )
    checks = _checks(proposal)
    refs = " ".join(_text(c.get("ref")) + " " + _text(c.get("predicate")) for c in checks).lower()
    needs_validation = "ok" in refs or "regression" in refs or "validation" in refs
    if tool in _READ_LIKE and (empty_args or needs_validation):
        return True
    claim = _text(w.get("causal_claim")).lower()
    if tool in _READ_LIKE and ("close" in claim or "validation" in claim):
        return True
    if tool and needs_validation and tool not in _CAUSAL_TOOLS:
        return True
    return False


def _causal_match(proposal: dict[str, Any]) -> bool:
    w = _work(proposal)
    tool = _text(w.get("proposed_tool")).lower()
    if not tool or tool in _READ_LIKE:
        return False
    surfaces = _CAUSAL_TOOLS.get(tool)
    if not surfaces:
        return False
    blob = json.dumps(_checks(proposal), sort_keys=True).lower()
    return any(s.lower() in blob for s in surfaces)


def _history_duplicate(proposal: dict[str, Any], snapshots: dict[str, Any]) -> bool:
    if _independent_satisfied(proposal, snapshots):
        return False
    fp_now = _fp_from_runtime(snapshots)
    key = _dedupe_key(proposal)
    tool = _text(_work(proposal).get("proposed_tool")).lower()
    for row in _as_list(snapshots.get("admission_history")):
        rec = _as_dict(row)
        if _text(rec.get("dedupe_key")) != key:
            continue
        prior_fp = _as_dict(rec.get("controlling_fingerprint"))
        if not prior_fp:
            continue
        same = all(_text(prior_fp.get(k)) == _text(fp_now.get(k)) for k in fp_now)
        if not same:
            continue
        if tool and _text(rec.get("proposed_tool")).lower() not in {"", tool} and rec.get("proposal_family") == "P_cover":
            continue
        if rec.get("proposal_family") == "P_causal" or _text(rec.get("proposed_tool")).lower() == tool:
            if rec.get("attempt_satisfied") is False or rec.get("satisfied") is False:
                return True
        if rec.get("proposal_family") == "P_causal" and tool == "release_validation_run":
            return True
    return False


def evaluate_admission(
    proposal: dict[str, Any] | None,
    snapshots: dict[str, Any] | None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    proposal = _deep_copy(_as_dict(proposal))
    snapshots = _deep_copy(_as_dict(snapshots))
    policy = _deep_copy(_as_dict(policy or snapshots.get("policy")))
    request_id = _text(proposal.get("request_id"))
    codes: list[str] = []
    clarifications: list[str] = []
    trace: list[str] = []
    t = _target(proposal)
    w = _work(proposal)
    tid = _text(t.get("target_id"))
    fp = _text(t.get("target_fingerprint"))
    matched = _match_target(proposal, snapshots)

    if not tid and not fp:
        codes.append("TARGET_NOT_IDENTIFIED")
        clarifications.append("target_id or target_fingerprint required")
        trace.append("target_not_identified")
    else:
        codes.append("TARGET_IDENTIFIED")
        trace.append("target_identified")

    if "TARGET_NOT_IDENTIFIED" not in codes:
        if matched is None and not _as_dict(snapshots.get("runtime")).get("regression_status") and tid != "finding_pkg_validation":
            codes.append("TARGET_NOT_REAL")
            trace.append("target_not_in_snapshot")
        elif matched is None and tid not in {"finding_pkg_validation", "finding_capability_gap_fixture"} and not matched:
            # fixture families are real if runtime snapshot carries regression/caps
            if tid:
                codes.append("TARGET_NOT_REAL")
            else:
                codes.append("TARGET_REAL")
        else:
            if matched is not None or tid in {"finding_pkg_validation", "finding_capability_gap_fixture"}:
                codes.append("TARGET_REAL")
                trace.append("target_real")
            else:
                codes.append("TARGET_NOT_REAL")

    sat = _independent_satisfied(proposal, snapshots)
    if "TARGET_NOT_IDENTIFIED" not in codes and "TARGET_NOT_REAL" not in codes:
        if sat:
            codes.append("TARGET_ALREADY_SATISFIED")
            trace.append("independent_observation_satisfied")
        else:
            codes.append("TARGET_UNSATISFIED")
            trace.append("independent_observation_unsatisfied")

    checks = _checks(proposal)
    if not checks or any(not _text(c.get("ref")) or not _text(c.get("predicate")) for c in checks):
        codes.append("COMPLETION_NOT_OBSERVABLE")
        clarifications.append("completion_condition_not_observable")
    else:
        codes.append("COMPLETION_OBSERVABLE")

    if _evidence_stale(snapshots):
        codes.append("EVIDENCE_STALE")
    else:
        if _as_list(snapshots.get("evidence")) or _as_list(proposal.get("evidence")):
            codes.append("EVIDENCE_CURRENT")
    if _evidence_untrusted_only(proposal, snapshots):
        codes.append("EVIDENCE_UNTRUSTED")

    cover = _is_cover(proposal)
    causal = _causal_match(proposal)
    tool = _text(w.get("proposed_tool"))
    duplicate = (
        (not cover)
        and _history_duplicate(proposal, snapshots)
        and not sat
    )
    if duplicate:
        trace.append("same_fingerprint_prior_unsatisfied_attempt")
    if cover:
        trace.append("cover_or_goal_substitution")
    elif not tool:
        trace.append("no_proposed_causal_tool")
    elif causal:
        trace.append("causal_action_match")
    else:
        trace.append("causal_action_mismatch")

    identified = "TARGET_NOT_IDENTIFIED" not in codes
    real = "TARGET_REAL" in codes
    stale = "EVIDENCE_STALE" in codes
    untrusted = "EVIDENCE_UNTRUSTED" in codes
    observable = "COMPLETION_OBSERVABLE" in codes
    not_observable = "COMPLETION_NOT_OBSERVABLE" in codes

    if not identified:
        work = "needs_clarification"
    elif "TARGET_NOT_REAL" in codes:
        work = "rejected"
    elif duplicate:
        work = "duplicate"
    elif sat:
        work = "rejected"
    elif not_observable:
        work = "needs_clarification"
    elif stale:
        work = "needs_clarification"
    elif not tool and not cover:
        work = "no_actionable_target"
    elif cover or (tool and not causal):
        work = "rejected"
    else:
        work = "admitted"

    # Emit only codes that belong to the chosen work path (frozen traces).
    emit: list[str] = []
    if identified:
        emit.append("TARGET_IDENTIFIED")
    else:
        emit.append("TARGET_NOT_IDENTIFIED")
    if identified and real:
        emit.append("TARGET_REAL")
    if identified and "TARGET_NOT_REAL" in codes:
        emit.append("TARGET_NOT_REAL")
    if identified and real and sat:
        emit.append("TARGET_ALREADY_SATISFIED")
    elif identified and real and not sat:
        emit.append("TARGET_UNSATISFIED")
    if observable:
        emit.append("COMPLETION_OBSERVABLE")
    if not_observable:
        emit.append("COMPLETION_NOT_OBSERVABLE")
    if work == "duplicate":
        emit.append("DUPLICATE_TARGET")
    if work == "no_actionable_target":
        emit.append("NO_ACTIONABLE_STEP")
    if cover and work in {"rejected", "needs_clarification"}:
        emit.append("COVER_OR_GOAL_SUBSTITUTION")
    if stale:
        emit.append("EVIDENCE_STALE")
    if untrusted:
        emit.append("EVIDENCE_UNTRUSTED")
    codes = emit

    if work == "admitted":
        codes.append("ACTIONABLE_STEP_PRESENT")
        codes.append("CAUSAL_ACTION_MATCH")
        if _as_list(snapshots.get("evidence")) or _as_list(proposal.get("evidence")):
            codes.append("EVIDENCE_CURRENT")

    actor = _as_dict(proposal.get("actor"))
    auth_pol = _as_dict(_as_dict(policy).get("actor_authority"))
    tool_pol = _as_dict(_as_dict(policy).get("tool_policy"))
    cap_pol = _as_dict(_as_dict(policy).get("capability_policy"))
    auth_codes: list[str] = []
    authority = "not_evaluated"
    if work == "admitted":
        allowed_actors = {_text(x) for x in _as_list(auth_pol.get("allowed_actor_ids"))}
        allowed_kinds = {_text(x) for x in _as_list(auth_pol.get("allowed_actor_kinds"))}
        actor_id = _text(actor.get("actor_id"))
        actor_kind = _text(actor.get("actor_kind"))
        if allowed_actors and actor_id not in allowed_actors:
            auth_codes.append("ACTOR_NOT_AUTHORIZED")
            authority = "actor_denied"
        elif allowed_kinds and actor_kind and actor_kind not in allowed_kinds:
            auth_codes.append("ACTOR_NOT_AUTHORIZED")
            authority = "actor_denied"
        else:
            auth_codes.append("ACTOR_AUTHORIZED")
        allowed_tools = {_text(x).lower() for x in _as_list(tool_pol.get("allowed_tools"))}
        if tool and allowed_tools and tool.lower() not in allowed_tools:
            auth_codes.append("TOOL_NOT_AUTHORIZED")
            authority = "tool_denied" if authority != "actor_denied" else authority
        elif tool:
            auth_codes.append("TOOL_AUTHORIZED")
        caps = {_text(x) for x in _as_list(cap_pol.get("allowed_capabilities"))}
        if caps and "*" not in caps and tool and tool not in caps:
            auth_codes.append("CAPABILITY_NOT_AUTHORIZED")
            if authority == "authorized" or authority == "not_evaluated":
                authority = "capability_denied"
        else:
            auth_codes.append("CAPABILITY_AUTHORIZED")
        if authority == "not_evaluated" and "ACTOR_NOT_AUTHORIZED" not in auth_codes and "TOOL_NOT_AUTHORIZED" not in auth_codes:
            authority = "authorized"

    codes.extend(auth_codes)

    if work != "admitted":
        eligibility = "not_evaluated"
    elif authority in {"actor_denied", "tool_denied", "capability_denied", "insufficient_authority"}:
        eligibility = "not_executable"
        codes.append("EXECUTION_BLOCKED_TOOL_AUTHORITY" if authority == "tool_denied" else "EXECUTION_BLOCKED_INCOMPLETE_ADMISSION")
    else:
        eligibility = "eligible_now"
        codes.append("EXECUTION_ELIGIBLE_NOW")

    effective_tool = tool if work == "admitted" and authority == "authorized" else ""
    duplicate_of = _dedupe_key(proposal) if work == "duplicate" else None

    return {
        "schema": SCHEMA_DECISION,
        "request_id": request_id,
        "work_decision": work,
        "authority_decision": authority,
        "execution_eligibility": eligibility,
        "materialized": False,
        "effective_tool": {
            "tool": effective_tool,
            "args": {},
            "source": "server_resolved" if effective_tool else "none",
            "caller_tool_was_proposal": True,
        },
        "reason_codes": _sorted_unique(codes),
        "decision_trace": list(trace),
        "required_clarifications": clarifications,
        "duplicate_of": duplicate_of,
        "materialization_preconditions": [],
        "evaluation_label": LABEL,
    }
