"""Derive the legacy compressed regression_status.json payload from registry
truth. This is the compatibility projection that keeps the pre-registry
consumers (release gate, mission, control status) working while they migrate
to the registry. It is pure and deterministic; it never executes anything.

Mapping (preserves the narrow FAILED contract):
    FULL       -> status OK         returncode 0
    FAILED     -> status FAILED     returncode 1
    PARTIAL    -> status PARTIAL    returncode 1
    NOT_CURRENT -> status NOT_CURRENT returncode 1
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from services.regression_truth_registry import REQUIRED_LANES, truth


def project_canonical_status(
    records_path: Path,
    fingerprint: str,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    current = truth(records_path, fingerprint)
    now = generated_at or time.strftime("%Y-%m-%d %H:%M:%S")
    certification = str(current.get("certification") or "NOT_CURRENT")
    reason = list(current.get("reason") or [])
    lanes = dict(current.get("lanes") or {})
    failed_lanes = [
        lane for lane in REQUIRED_LANES if str((lanes.get(lane) or {}).get("status") or "").upper() == "FAILED"
    ]
    detail = "; ".join(reason)
    if certification == "FULL":
        status, returncode, failed_lane = "OK", 0, ""
    elif certification == "FAILED":
        status, returncode, failed_lane = "FAILED", 1, str(failed_lanes[0]) if failed_lanes else ""
    elif certification == "PARTIAL":
        status, returncode, failed_lane = "PARTIAL", 1, ""
    else:
        status, returncode, failed_lane = "NOT_CURRENT", 1, ""
    return {
        "generated_at": now,
        "date": now[:10],
        "status": status,
        "lanes": list(REQUIRED_LANES),
        "returncode": returncode,
        "detail": detail.strip()[:500],
        "failed_lane": failed_lane,
        "failed_tests": [],
        "source": "scheduler:regression_truth_registry",
        "certification": certification,
        "registry_fingerprint": str(fingerprint or "").strip()[:80],
        "reason": reason,
    }