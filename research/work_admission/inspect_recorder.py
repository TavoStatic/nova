"""Inspect recorder: compare kernel JSON to frozen traces.

Does not modify decisions. Not a Nova gate. Not live mill proof.
"""
from __future__ import annotations

from typing import Any

from research.work_admission.frozen_traces import EXPECTED_EXPERIMENT, LABEL, experiment_cases
from research.work_admission.kernel import evaluate_admission

COMPARE_FIELDS = (
    "work_decision",
    "authority_decision",
    "execution_eligibility",
    "materialized",
    "duplicate_of",
)


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def compare_decision(actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    actual = _as_dict(actual)
    expected = _as_dict(expected)
    diffs: list[str] = []
    for field in COMPARE_FIELDS:
        if actual.get(field) != expected.get(field):
            diffs.append(f"{field}: actual={actual.get(field)!r} expected={expected.get(field)!r}")
    actual_codes = set(actual.get("reason_codes") or [])
    expected_codes = set(expected.get("reason_codes") or [])
    if actual_codes != expected_codes:
        missing = sorted(expected_codes - actual_codes)
        extra = sorted(actual_codes - expected_codes)
        diffs.append(f"reason_codes missing={missing} extra={extra}")
    eff_a = _as_dict(actual.get("effective_tool")).get("tool") or ""
    eff_e = _as_dict(expected.get("effective_tool")).get("tool") or ""
    if eff_a != eff_e:
        diffs.append(f"effective_tool.tool: actual={eff_a!r} expected={eff_e!r}")
    return {
        "match": not diffs,
        "diffs": diffs,
        "evaluation_label": LABEL,
        "judge": "frozen_table_compare",
        "not_a_nova_gate": True,
    }


def record_experiment() -> dict[str, Any]:
    rows = []
    for name, proposal, snapshot, policy in experiment_cases():
        actual = evaluate_admission(proposal, snapshot, policy)
        expected = EXPECTED_EXPERIMENT[name]
        cmp_ = compare_decision(actual, expected)
        rows.append(
            {
                "case": name,
                "match": cmp_["match"],
                "diffs": cmp_["diffs"],
                "actual_work_decision": actual.get("work_decision"),
                "expected_work_decision": expected.get("work_decision"),
                "failure_kind": (
                    "nova_decision_failure" if not cmp_["match"] else ""
                ),
            }
        )
    failed = [r for r in rows if not r["match"]]
    return {
        "evaluation_label": LABEL,
        "inspect_role": "recorder_compare_only",
        "not_live_nova_proof": True,
        "case_count": len(rows),
        "failed_count": len(failed),
        "failed_cases": [r["case"] for r in failed],
        "rows": rows,
    }
