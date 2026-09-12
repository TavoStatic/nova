"""Regression Truth Registry (slice 1).

Pure per-lane evidence store for regression observations. Records are
immutable and keyed to a source fingerprint; freshness is fingerprint-only
(never age). The registry answers "what do we know", never "what should we do":
the scheduler decides what to observe next and the runner performs it.

The narrow FAILED contract: a lane is FAILED only when it produced an explicit
FAILED result on the current fingerprint. A TIMED_OUT result is an incomplete
observation, not a failure. Time does not invalidate evidence - changed
causation does.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

REQUIRED_LANES: tuple[str, ...] = ("unit", "behavior", "integration")
LANE_ORDER: tuple[str, ...] = REQUIRED_LANES

LANE_STATUSES: tuple[str, ...] = ("PASS", "FAILED", "TIMED_OUT")


def _text(value: Any, limit: int = 120) -> str:
    return str(value or "").strip()[:limit]


def validate_lane_result(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    lane = _text(record.get("lane"), 40)
    if lane not in LANE_ORDER:
        errors.append(f"lane_not_required:{_text(lane, 40) or 'missing'}")
    fingerprint = _text(record.get("source_fingerprint"), 80)
    if not fingerprint:
        errors.append("source_fingerprint_required")
    status = _text(record.get("status"), 24).upper()
    if status not in LANE_STATUSES:
        errors.append(f"status_unknown:{_text(status, 24) or 'missing'}")
    for key, cast in (("duration_sec", float), ("tests", int), ("failures", int)):
        value = record.get(key)
        if value is None:
            continue
        try:
            cast(value)
        except (TypeError, ValueError):
            errors.append(f"{key}_must_be_numeric")
    if record.get("failures") is not None:
        try:
            if int(record.get("failures")) < 0:
                errors.append("failures_negative")
        except (TypeError, ValueError):
            pass
    if not _text(record.get("started_at"), 40) or not _text(record.get("finished_at"), 40):
        errors.append("started_and_finished_required")
    return errors


def _canonical_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane": _text(record.get("lane"), 40),
        "source_fingerprint": _text(record.get("source_fingerprint"), 80),
        "status": _text(record.get("status"), 24).upper(),
        "started_at": _text(record.get("started_at"), 40),
        "finished_at": _text(record.get("finished_at"), 40),
        "duration_sec": round(float(record.get("duration_sec") or 0.0), 1),
        "tests": int(record.get("tests") or 0),
        "failures": int(record.get("failures") or 0),
        "artifact_log_ref": _text(record.get("artifact_log_ref"), 320),
    }


def record_lane_result(record: dict[str, Any], records_path: Path) -> list[str]:
    errors = validate_lane_result(record)
    if errors:
        return errors
    path = Path(records_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_record(record)
    with open(str(path), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    return []


def read_lane_records(records_path: Path) -> list[dict[str, Any]]:
    path = Path(records_path)
    lines: list[dict[str, Any]] = []
    if not path.exists():
        return lines
    with open(str(path), encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if isinstance(payload, dict):
                lines.append(payload)
    return lines


def _latest_for_lane(records: list[dict[str, Any]], lane: str) -> dict[str, Any] | None:
    matching = [record for record in records if _text(record.get("lane"), 40) == lane]
    if not matching:
        return None
    return matching[-1]


def _lane_current(record: dict[str, Any] | None, fingerprint: str) -> bool:
    if record is None:
        return False
    return _text(record.get("source_fingerprint"), 80) == fingerprint


def lanes_needing_observation(records_path: Path, fingerprint: str) -> list[str]:
    """All required lanes without a PASS on the current fingerprint, in
    preferred observation order. Deciding to run them sequentially is the
    scheduler's call; the registry only reports what is missing."""
    records = read_lane_records(records_path)
    missing: list[str] = []
    for lane in LANE_ORDER:
        latest = _latest_for_lane(records, lane)
        current_pass = bool(latest) and _text(latest.get("status"), 24).upper() == "PASS" and _lane_current(latest, fingerprint)
        if not current_pass:
            missing.append(lane)
    return missing


def _consequence_codes(records: list[dict[str, Any]], fingerprint: str) -> dict[str, str]:
    codes: dict[str, str] = {}
    for lane in LANE_ORDER:
        latest = _latest_for_lane(records, lane)
        if latest is None:
            codes[lane] = f"{lane}_not_observed_on_current"
        elif not _lane_current(latest, fingerprint):
            codes[lane] = f"{lane}_not_current"
        elif _text(latest.get("status"), 24).upper() == "TIMED_OUT":
            codes[lane] = f"{lane}_timed_out_on_current"
        elif _text(latest.get("status"), 24).upper() == "FAILED":
            codes[lane] = f"{lane}_failed_on_current"
    return codes


def truth(records_path: Path, fingerprint: str) -> dict[str, Any]:
    records = read_lane_records(records_path)
    lanes: dict[str, Any] = {}
    for lane in LANE_ORDER:
        latest = _latest_for_lane(records, lane)
        current = _lane_current(latest, fingerprint)
        status = "UNKNOWN"
        if latest is not None:
            status = _text(latest.get("status"), 24).upper()
            if not current:
                status = "UNKNOWN"
        lanes[lane] = {
            "status": status,
            "current": current,
            "source_fingerprint": _text(latest.get("source_fingerprint"), 80) if latest else "",
            "finished_at": _text(latest.get("finished_at"), 40) if latest else "",
            "duration_sec": round(float(latest.get("duration_sec") or 0.0), 1) if latest else 0.0,
            "tests": int(latest.get("tests") or 0) if latest else 0,
            "failures": int(latest.get("failures") or 0) if latest else 0,
            "artifact_log_ref": _text(latest.get("artifact_log_ref"), 320) if latest else "",
        }

    codes = _consequence_codes(records, fingerprint)
    reason = [code for lane in LANE_ORDER if (code := codes.get(lane))]
    current_statuses = {lane: item["status"] for lane, item in lanes.items()}
    passed_current = [lane for lane, status in current_statuses.items() if status == "PASS"]
    failed_current = [lane for lane, status in current_statuses.items() if status == "FAILED"]
    timed_out_current = [lane for lane, status in current_statuses.items() if status == "TIMED_OUT"]
    any_current_observation = bool(passed_current or failed_current or timed_out_current)

    if len(passed_current) == len(REQUIRED_LANES):
        certification = "FULL"
        reason = []
    elif failed_current:
        certification = "FAILED"
    elif any_current_observation:
        certification = "PARTIAL"
    else:
        certification = "NOT_CURRENT"
    return {
        "fingerprint": _text(fingerprint, 80),
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "certification": certification,
        "reason": reason,
        "lanes": lanes,
        "lanes_needing_observation": lanes_needing_observation(records_path, fingerprint),
    }


def write_truth_snapshot(records_path: Path, fingerprint: str, snapshot_path: Path) -> dict[str, Any]:
    snapshot = truth(records_path, fingerprint)
    path = Path(snapshot_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=True, indent=2))
    return snapshot