"""Pre-registered experiment table.

Registered before kernel implementation. Do not edit expected traces to match
kernel output. Failures are preserved.

Label: white-box kernel evaluation, not live Nova proof.
No live branch_76a2bb4e.
"""
from __future__ import annotations

from typing import Any

LABEL = "white-box kernel evaluation, not live Nova proof"
SCHEMA_PROPOSAL = "nova.work_admission.proposal.v1"
SCHEMA_DECISION = "nova.work_admission.decision.v1"

# --- Fingerprints (relevant vs unrelated) ---

RELEVANT_FP_FIELDS = (
    "target_type",
    "target_id",
    "artifact_id",
    "artifact_content_id",
    "validation_status",
    "validation_generated_at",
    "source_identity",
)

UNRELATED_FP_FIELDS = (
    "unrelated_token",
    "operator_outbox_open_count",
)

FP_P_T0 = {
    "target_type": "finding",
    "target_id": "finding_pkg_validation",
    "artifact_id": "pkg-A",
    "artifact_content_id": "hash-A",
    "validation_status": "TIMED_OUT",
    "validation_generated_at": "2026-08-29 08:35:47",
    "source_identity": "src-A",
}

FP_P_T2_RELEVANT_UNSAT = {
    **FP_P_T0,
    "artifact_id": "pkg-B",
    "artifact_content_id": "hash-B",
    "source_identity": "src-B",
    "validation_status": "TIMED_OUT",
    "validation_generated_at": "2026-08-29 18:00:00",
}

FP_P_T2_SAT = {
    **FP_P_T0,
    "validation_status": "OK",
    "validation_generated_at": "2026-08-29 19:00:00",
}

FP_Q = {
    "target_type": "capability_gap",
    "target_id": "finding_capability_gap_fixture",
    "artifact_id": "caps-manifest",
    "artifact_content_id": "caps-v1",
    "validation_status": "n/a",
    "validation_generated_at": "n/a",
    "source_identity": "caps-src",
}

T0_STAMP = "2026-08-29T12:00:00Z"
T1_STAMP = "2026-08-29T13:00:00Z"
T2_STAMP = "2026-08-29T19:00:00Z"

# --- Proposal identity ---

def _target_p() -> dict[str, Any]:
    return {
        "target_type": "finding",
        "target_id": "finding_pkg_validation",
        "target_fingerprint": "finding:pkg-validation:status-ok-current",
        "title": "Fixture package validation is not current OK",
        "current_state_ref": ["snapshot:regression_status", "snapshot:artifact"],
        "satisfaction_state": {
            "description": "Validation status is OK for the current package/source.",
            "observable_checks": [
                {
                    "kind": "ledger",
                    "ref": "runtime/regression_status.json",
                    "predicate": "status == OK and generated_at is current",
                }
            ],
        },
    }


def proposal_p_causal(*, request_id: str, source: str = "test") -> dict[str, Any]:
    return {
        "schema": SCHEMA_PROPOSAL,
        "request_id": request_id,
        "source": source,
        "actor": {
            "actor_id": "fixture-operator",
            "actor_kind": "evaluator",
            "authority_claims": ["control_local"],
        },
        "target": _target_p(),
        "proposed_work": {
            "title": "Run release validation for current package",
            "completion_condition": "A current validation record exists and matches the current package/source.",
            "proposed_tool": "release_validation_run",
            "proposed_args": {"artifact_id": "current"},
            "causal_claim": "Running release validation can change the missing/failing validation evidence state.",
        },
        "evidence": [],
        "idempotency": {
            "dedupe_key": "finding:finding_pkg_validation:validation_ok_current_package",
            "supersedes": [],
        },
    }


def proposal_p_cover(*, request_id: str, source: str = "test") -> dict[str, Any]:
    p = proposal_p_causal(request_id=request_id, source=source)
    p["proposed_work"] = {
        "title": "Read something because a stem is required",
        "completion_condition": "A current validation record exists and matches the current package/source.",
        "proposed_tool": "read",
        "proposed_args": {},
        "causal_claim": "Reading will close the validation gap.",
    }
    return p


def proposal_q(*, request_id: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA_PROPOSAL,
        "request_id": request_id,
        "source": "test",
        "actor": {
            "actor_id": "fixture-operator",
            "actor_kind": "evaluator",
            "authority_claims": ["control_local"],
        },
        "target": {
            "target_type": "capability_gap",
            "target_id": "finding_capability_gap_fixture",
            "target_fingerprint": "finding:capability-gap:declared-absent",
            "title": "Fixture declared capability is absent",
            "current_state_ref": ["snapshot:capability_manifest"],
            "satisfaction_state": {
                "description": "Declared capability is registered.",
                "observable_checks": [
                    {
                        "kind": "file",
                        "ref": "capabilities.json",
                        "predicate": "named capability present",
                    }
                ],
            },
        },
        "proposed_work": {
            "title": "No known next causal step",
            "completion_condition": "Capability is registered.",
            "proposed_tool": "",
            "proposed_args": {},
            "causal_claim": "",
        },
        "evidence": [],
        "idempotency": {
            "dedupe_key": "finding:finding_capability_gap_fixture:capability_registered",
            "supersedes": [],
        },
    }


DEFAULT_POLICY = {
    "actor_authority": {
        "allowed_actor_ids": ["fixture-operator", "fixture-service"],
        "allowed_actor_kinds": ["human", "service", "evaluator", "system"],
    },
    "tool_policy": {
        "allowed_tools": ["release_validation_run", "read", "core_thinning", "find", "ls"],
    },
    "mission_policy": {},
    "capability_policy": {"allowed_capabilities": ["*"]},
}


def _obs_val(fp: dict[str, str], *, observed_at: str) -> dict[str, Any]:
    return {
        "ref": "snapshot:regression_status",
        "kind": "ledger",
        "observed_at": observed_at,
        "producer": "inspect",
        "provenance_class": "independent",
        "freshness_ttl_seconds": 86400,
        "summary": f"status={fp['validation_status']} generated_at={fp['validation_generated_at']}",
        "supports": ["validation_status", "validation_generated_at"],
        "values": {
            "status": fp["validation_status"],
            "generated_at": fp["validation_generated_at"],
        },
    }


def snapshot_for(
    fp_p: dict[str, str],
    *,
    current_time: str,
    unrelated_token: str = "noise-0",
    outbox_open: int = 0,
    history: list[dict[str, Any]] | None = None,
    tree_open_after_sat: bool = False,
    tool_ran_unsatisfied: bool = False,
) -> dict[str, Any]:
    sat = fp_p["validation_status"] == "OK"
    open_targets: list[dict[str, Any]] = []
    closed_targets: list[dict[str, Any]] = []
    target_row = {
        "target_id": "finding_pkg_validation",
        "target_fingerprint": "finding:pkg-validation:status-ok-current",
        "target_type": "finding",
        "satisfied": sat,
        "completion_condition": "validation_ok_current_package",
        "surface": "runtime/regression_status.json",
    }
    if sat:
        closed_targets.append({**target_row, "satisfied": True})
        if tree_open_after_sat:
            open_targets.append({**target_row, "satisfied": False, "stale_representation": True})
    else:
        open_targets.append({**target_row, "satisfied": False})
    open_targets.append(
        {
            "target_id": "finding_capability_gap_fixture",
            "target_fingerprint": "finding:capability-gap:declared-absent",
            "target_type": "capability_gap",
            "satisfied": False,
            "completion_condition": "capability_registered",
            "surface": "capabilities.json",
        }
    )
    evidence = [_obs_val(fp_p, observed_at=current_time)]
    if tool_ran_unsatisfied:
        evidence.append(
            {
                "ref": "snapshot:tool_result",
                "kind": "ledger",
                "observed_at": current_time,
                "producer": "nova",
                "provenance_class": "nova_runtime",
                "freshness_ttl_seconds": 300,
                "summary": "release_validation_run returned ok; validation_status still TIMED_OUT",
                "supports": ["tool_execution"],
                "values": {"tool": "release_validation_run", "ok": True},
            }
        )
    return {
        "work_tree": {
            "branches": [],
            "tasks": [],
            "evidence": [],
            "open_targets": open_targets,
            "closed_targets": closed_targets,
        },
        "runtime": {
            "mission_snapshot": {},
            "regression_status": {
                "status": fp_p["validation_status"],
                "generated_at": fp_p["validation_generated_at"],
                "date": "2026-08-29",
            },
            "release_status": {
                "artifact_id": fp_p["artifact_id"],
                "artifact_content_id": fp_p["artifact_content_id"],
            },
            "operator_outbox": {"open_count": outbox_open},
            "current_time": current_time,
            "artifact_id": fp_p["artifact_id"],
            "artifact_content_id": fp_p["artifact_content_id"],
            "source_identity": fp_p["source_identity"],
            "unrelated_token": unrelated_token,
            "controlling_fingerprint": dict(fp_p),
        },
        "policy": dict(DEFAULT_POLICY),
        "admission_history": list(history or []),
        "evidence": evidence,
    }


HISTORY_T0 = [
    {
        "proposal_family": "P_cover",
        "work_decision": "rejected",
        "reason_codes": ["COVER_OR_GOAL_SUBSTITUTION"],
        "controlling_fingerprint": dict(FP_P_T0),
        "dedupe_key": "finding:finding_pkg_validation:validation_ok_current_package",
        "satisfied": False,
    },
    {
        "proposal_family": "P_causal",
        "work_decision": "admitted",
        "reason_codes": ["CAUSAL_ACTION_MATCH"],
        "controlling_fingerprint": dict(FP_P_T0),
        "dedupe_key": "finding:finding_pkg_validation:validation_ok_current_package",
        "proposed_tool": "release_validation_run",
        "attempt_satisfied": False,
        "satisfied": False,
    },
]


def _dec(
    *,
    request_id: str,
    work: str,
    authority: str,
    eligibility: str,
    reasons: list[str],
    tool: str | None,
    duplicate_of: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_DECISION,
        "request_id": request_id,
        "work_decision": work,
        "authority_decision": authority,
        "execution_eligibility": eligibility,
        "materialized": False,
        "effective_tool": {
            "tool": tool or "",
            "args": {},
            "source": "server_resolved" if tool else "none",
            "caller_tool_was_proposal": True,
        },
        "reason_codes": list(reasons),
        "decision_trace": [],
        "required_clarifications": [],
        "duplicate_of": duplicate_of,
        "materialization_preconditions": [],
        "evaluation_label": LABEL,
    }


# Expected traces registered before kernel implementation. Do not edit after runs.

EXPECTED_EXPERIMENT: dict[str, dict[str, Any]] = {
    "P_cover@T0": _dec(
        request_id="exp-P-cover-T0",
        work="rejected",
        authority="not_evaluated",
        eligibility="not_evaluated",
        reasons=[
            "TARGET_IDENTIFIED",
            "TARGET_REAL",
            "TARGET_UNSATISFIED",
            "COMPLETION_OBSERVABLE",
            "COVER_OR_GOAL_SUBSTITUTION",
        ],
        tool=None,
    ),
    "P_causal@T0": _dec(
        request_id="exp-P-causal-T0",
        work="admitted",
        authority="authorized",
        eligibility="eligible_now",
        reasons=[
            "TARGET_IDENTIFIED",
            "TARGET_REAL",
            "TARGET_UNSATISFIED",
            "COMPLETION_OBSERVABLE",
            "ACTIONABLE_STEP_PRESENT",
            "CAUSAL_ACTION_MATCH",
            "EVIDENCE_CURRENT",
            "ACTOR_AUTHORIZED",
            "TOOL_AUTHORIZED",
            "CAPABILITY_AUTHORIZED",
            "EXECUTION_ELIGIBLE_NOW",
        ],
        tool="release_validation_run",
    ),
    "P_cover@T1_unchanged": _dec(
        request_id="exp-P-cover-T1",
        work="rejected",
        authority="not_evaluated",
        eligibility="not_evaluated",
        reasons=[
            "TARGET_IDENTIFIED",
            "TARGET_REAL",
            "TARGET_UNSATISFIED",
            "COMPLETION_OBSERVABLE",
            "COVER_OR_GOAL_SUBSTITUTION",
        ],
        tool=None,
    ),
    "P_causal@T1_unchanged": _dec(
        request_id="exp-P-causal-T1",
        work="duplicate",
        authority="not_evaluated",
        eligibility="not_evaluated",
        reasons=[
            "TARGET_IDENTIFIED",
            "TARGET_REAL",
            "TARGET_UNSATISFIED",
            "COMPLETION_OBSERVABLE",
            "DUPLICATE_TARGET",
        ],
        tool=None,
        duplicate_of="finding:finding_pkg_validation:validation_ok_current_package",
    ),
    "P_causal@T1_unrelated": _dec(
        request_id="exp-P-causal-T1u",
        work="duplicate",
        authority="not_evaluated",
        eligibility="not_evaluated",
        reasons=[
            "TARGET_IDENTIFIED",
            "TARGET_REAL",
            "TARGET_UNSATISFIED",
            "COMPLETION_OBSERVABLE",
            "DUPLICATE_TARGET",
        ],
        tool=None,
        duplicate_of="finding:finding_pkg_validation:validation_ok_current_package",
    ),
    "P_causal@T2_relevant_unsat": _dec(
        request_id="exp-P-causal-T2u",
        work="admitted",
        authority="authorized",
        eligibility="eligible_now",
        reasons=[
            "TARGET_IDENTIFIED",
            "TARGET_REAL",
            "TARGET_UNSATISFIED",
            "COMPLETION_OBSERVABLE",
            "ACTIONABLE_STEP_PRESENT",
            "CAUSAL_ACTION_MATCH",
            "EVIDENCE_CURRENT",
            "ACTOR_AUTHORIZED",
            "TOOL_AUTHORIZED",
            "CAPABILITY_AUTHORIZED",
            "EXECUTION_ELIGIBLE_NOW",
        ],
        tool="release_validation_run",
    ),
    "P_causal@T_tool_unsat": _dec(
        request_id="exp-P-causal-tool",
        work="duplicate",
        authority="not_evaluated",
        eligibility="not_evaluated",
        reasons=[
            "TARGET_IDENTIFIED",
            "TARGET_REAL",
            "TARGET_UNSATISFIED",
            "COMPLETION_OBSERVABLE",
            "DUPLICATE_TARGET",
        ],
        tool=None,
        duplicate_of="finding:finding_pkg_validation:validation_ok_current_package",
    ),
    "P_causal@T2_sat": _dec(
        request_id="exp-P-causal-T2s",
        work="rejected",
        authority="not_evaluated",
        eligibility="not_evaluated",
        reasons=[
            "TARGET_IDENTIFIED",
            "TARGET_REAL",
            "TARGET_ALREADY_SATISFIED",
            "COMPLETION_OBSERVABLE",
        ],
        tool=None,
    ),
    "P_cover@T2_sat": _dec(
        request_id="exp-P-cover-T2s",
        work="rejected",
        authority="not_evaluated",
        eligibility="not_evaluated",
        reasons=[
            "TARGET_IDENTIFIED",
            "TARGET_REAL",
            "TARGET_ALREADY_SATISFIED",
            "COMPLETION_OBSERVABLE",
            "COVER_OR_GOAL_SUBSTITUTION",
        ],
        tool=None,
    ),
    "Q@T0": _dec(
        request_id="exp-Q-T0",
        work="no_actionable_target",
        authority="not_evaluated",
        eligibility="not_evaluated",
        reasons=[
            "TARGET_IDENTIFIED",
            "TARGET_REAL",
            "TARGET_UNSATISFIED",
            "COMPLETION_OBSERVABLE",
            "NO_ACTIONABLE_STEP",
        ],
        tool=None,
    ),
    "Q@T1_unchanged": _dec(
        request_id="exp-Q-T1",
        work="no_actionable_target",
        authority="not_evaluated",
        eligibility="not_evaluated",
        reasons=[
            "TARGET_IDENTIFIED",
            "TARGET_REAL",
            "TARGET_UNSATISFIED",
            "COMPLETION_OBSERVABLE",
            "NO_ACTIONABLE_STEP",
        ],
        tool=None,
    ),
    "Q@T1_unrelated": _dec(
        request_id="exp-Q-T1u",
        work="no_actionable_target",
        authority="not_evaluated",
        eligibility="not_evaluated",
        reasons=[
            "TARGET_IDENTIFIED",
            "TARGET_REAL",
            "TARGET_UNSATISFIED",
            "COMPLETION_OBSERVABLE",
            "NO_ACTIONABLE_STEP",
        ],
        tool=None,
    ),
    "Q@T2_sat": _dec(
        request_id="exp-Q-T2s",
        work="no_actionable_target",
        authority="not_evaluated",
        eligibility="not_evaluated",
        reasons=[
            "TARGET_IDENTIFIED",
            "TARGET_REAL",
            "TARGET_UNSATISFIED",
            "COMPLETION_OBSERVABLE",
            "NO_ACTIONABLE_STEP",
        ],
        tool=None,
    ),
}


def experiment_cases() -> list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]]:
    """(name, proposal, snapshot, policy) with expected in EXPECTED_EXPERIMENT[name]."""
    snap_t0 = snapshot_for(FP_P_T0, current_time=T0_STAMP)
    snap_t1 = snapshot_for(FP_P_T0, current_time=T1_STAMP, history=HISTORY_T0)
    snap_t1u = snapshot_for(
        FP_P_T0,
        current_time=T1_STAMP,
        unrelated_token="noise-9",
        outbox_open=7,
        history=HISTORY_T0,
    )
    snap_t2u = snapshot_for(FP_P_T2_RELEVANT_UNSAT, current_time="2026-08-29T18:00:00Z", history=HISTORY_T0)
    snap_tool = snapshot_for(
        FP_P_T0,
        current_time=T1_STAMP,
        history=HISTORY_T0,
        tool_ran_unsatisfied=True,
    )
    snap_t2s = snapshot_for(FP_P_T2_SAT, current_time=T2_STAMP, history=HISTORY_T0, tree_open_after_sat=True)
    pol = DEFAULT_POLICY
    return [
        ("P_cover@T0", proposal_p_cover(request_id="exp-P-cover-T0"), snap_t0, pol),
        ("P_causal@T0", proposal_p_causal(request_id="exp-P-causal-T0"), snap_t0, pol),
        ("P_cover@T1_unchanged", proposal_p_cover(request_id="exp-P-cover-T1"), snap_t1, pol),
        ("P_causal@T1_unchanged", proposal_p_causal(request_id="exp-P-causal-T1"), snap_t1, pol),
        ("P_causal@T1_unrelated", proposal_p_causal(request_id="exp-P-causal-T1u"), snap_t1u, pol),
        ("P_causal@T2_relevant_unsat", proposal_p_causal(request_id="exp-P-causal-T2u"), snap_t2u, pol),
        ("P_causal@T_tool_unsat", proposal_p_causal(request_id="exp-P-causal-tool"), snap_tool, pol),
        ("P_causal@T2_sat", proposal_p_causal(request_id="exp-P-causal-T2s"), snap_t2s, pol),
        ("P_cover@T2_sat", proposal_p_cover(request_id="exp-P-cover-T2s"), snap_t2s, pol),
        ("Q@T0", proposal_q(request_id="exp-Q-T0"), snap_t0, pol),
        ("Q@T1_unchanged", proposal_q(request_id="exp-Q-T1"), snap_t1, pol),
        ("Q@T1_unrelated", proposal_q(request_id="exp-Q-T1u"), snap_t1u, pol),
        ("Q@T2_sat", proposal_q(request_id="exp-Q-T2s"), snap_t2s, pol),
    ]
