"""Evidence-backed observations about Nova's existing gates and rails.

This service observes gate decisions. It does not authorize actions, mutate
policy, retire gates, or override existing execution controls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.nova_runtime_context import RUNTIME_DIR

GATEKEEPER_RECORDS_PATH = RUNTIME_DIR / "gatekeeper_records.jsonl"
_REQUIRED_TOP_LEVEL = {
    "gate_id",
    "record_type",
    "status",
    "purpose",
    "decision_context",
    "evidence_before",
    "expected_effect",
    "outcome",
    "utility_verdict",
    "verification_contract",
    "automatic_policy_change",
    "automatic_gate_retirement",
}


def validate_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(key for key in _REQUIRED_TOP_LEVEL if key not in record)
    if missing:
        errors.append("missing:" + ",".join(missing))
    if not str(record.get("gate_id") or "").strip():
        errors.append("gate_id_required")
    utility = record.get("utility_verdict")
    if not isinstance(utility, dict) or utility.get("value") not in {"True", "False", True, False, "unknown", None}:
        errors.append("utility_verdict_invalid")
    verification = record.get("verification_contract")
    if isinstance(verification, dict) and verification.get("model_assessment_is_evidence") is True:
        errors.append("model_cannot_be_evidence")
    if record.get("automatic_policy_change") is True:
        errors.append("automatic_policy_change_forbidden")
    if record.get("automatic_gate_retirement") is True:
        errors.append("automatic_gate_retirement_forbidden")
    return errors


def read_records(path: Path = GATEKEEPER_RECORDS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                records.append(value)
    except Exception:
        return records
    return records


def _observation_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    context = record.get("decision_context") if isinstance(record.get("decision_context"), dict) else {}
    evidence_before = record.get("evidence_before")
    fingerprint = ""
    if isinstance(evidence_before, list):
        for item in evidence_before:
            if isinstance(item, dict) and str(item.get("fingerprint") or "").strip():
                fingerprint = str(item.get("fingerprint") or "").strip()
                break
    outcome = record.get("outcome") if isinstance(record.get("outcome"), dict) else {}
    return (
        str(record.get("gate_id") or "").strip(),
        str(context.get("controlling_reason") or "").strip(),
        fingerprint,
        str(outcome.get("classification") or "").strip(),
    )


def _observed_at(record: dict[str, Any]) -> str:
    context = record.get("decision_context") if isinstance(record.get("decision_context"), dict) else {}
    return str(context.get("observed_at") or record.get("observed_at") or "").strip()


def _apply_observation_timestamps(record: dict[str, Any], *, first: str = "", last: str = "") -> dict[str, Any]:
    row = dict(record)
    observed = _observed_at(row)
    row["first_observed_at"] = str(row.get("first_observed_at") or first or observed)
    row["last_observed_at"] = str(last or observed or row.get("last_observed_at") or row["first_observed_at"])
    return row


def append_record(record: dict[str, Any], path: Path = GATEKEEPER_RECORDS_PATH) -> list[str]:
    errors = validate_record(record)
    if errors:
        return errors
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for existing in read_records(path):
        if records and _observation_key(records[-1]) == _observation_key(existing):
            records[-1]["seen_count"] = int(records[-1].get("seen_count", 1) or 1) + int(
                existing.get("seen_count", 1) or 1
            )
        else:
            records.append(_apply_observation_timestamps(existing))
    current = _apply_observation_timestamps(record)
    current["seen_count"] = max(1, int(current.get("seen_count", 1) or 1))
    if records and _observation_key(records[-1]) == _observation_key(current):
        previous = dict(records[-1])
        current["seen_count"] = int(previous.get("seen_count", 1) or 1) + 1
        current["first_observed_at"] = str(previous.get("first_observed_at") or _observed_at(previous))
        current["last_observed_at"] = _observed_at(current) or str(previous.get("last_observed_at") or "")
        records[-1] = current
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            "".join(json.dumps(item, ensure_ascii=True, separators=(",", ":")) + "\n" for item in records),
            encoding="utf-8",
        )
        temporary.replace(path)
        return []
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(current, ensure_ascii=True, separators=(",", ":")) + "\n")
    return []


def compact_records(path: Path = GATEKEEPER_RECORDS_PATH) -> dict[str, int]:
    records = read_records(path)
    compacted: list[dict[str, Any]] = []
    merged = 0
    changed = False
    for record in records:
        if compacted and _observation_key(compacted[-1]) == _observation_key(record):
            compacted[-1]["seen_count"] = int(compacted[-1].get("seen_count", 1) or 1) + int(
                record.get("seen_count", 1) or 1
            )
            compacted[-1]["last_observed_at"] = str(
                record.get("last_observed_at") or _observed_at(record) or compacted[-1].get("last_observed_at") or ""
            )
            changed = True
            merged += 1
        else:
            row = _apply_observation_timestamps(record)
            row["seen_count"] = max(1, int(row.get("seen_count", 1) or 1))
            changed = changed or row != record
            compacted.append(row)
    if records and changed:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            "".join(json.dumps(item, ensure_ascii=True, separators=(",", ":")) + "\n" for item in compacted),
            encoding="utf-8",
        )
        temporary.replace(path)
    return {"records_before": len(records), "records_after": len(compacted), "merged": merged}


def summarize_records(path: Path = GATEKEEPER_RECORDS_PATH) -> dict[str, Any]:
    records = read_records(path)
    latest: dict[str, dict[str, Any]] = {}
    invalid_count = 0
    for record in records:
        errors = validate_record(record)
        if errors:
            invalid_count += 1
            continue
        latest[str(record.get("gate_id"))] = record
    latest_rows = list(latest.values())
    return {
        "ok": invalid_count == 0,
        "record_count": len(records),
        "valid_record_count": len(records) - invalid_count,
        "invalid_record_count": invalid_count,
        "gate_count": len(latest_rows),
        "unknown_utility_count": sum(
            1 for record in latest_rows if (record.get("utility_verdict") or {}).get("value") == "unknown"
        ),
        "stale_evidence_count": sum(
            1 for record in latest_rows if bool((record.get("outcome") or {}).get("evidence_freshness_fault"))
        ),
        "records": [
            {
                "gate_id": str(record.get("gate_id") or ""),
                "status": str(record.get("status") or ""),
                "classification": str((record.get("outcome") or {}).get("classification") or ""),
                "utility": (record.get("utility_verdict") or {}).get("value"),
                "next_action": str((record.get("lesson") or {}).get("proposed_resolution", {}).get("action") or ""),
                "seen_count": int(record.get("seen_count", 1) or 1),
            }
            for record in sorted(latest_rows, key=lambda item: str(item.get("gate_id") or ""))
        ],
    }


GATEKEEPER_SERVICE = summarize_records
