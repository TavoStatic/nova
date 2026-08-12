"""Capability gap detection service.

Compares declared capabilities (roadmap) with registered capabilities
and signals when desired capabilities are not yet implemented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_capabilities_json(base_dir: Path = None) -> dict[str, str]:
    """Load registered capabilities from capabilities.json."""
    if base_dir is None:
        base_dir = Path(__file__).parent.parent

    cap_file = base_dir / "capabilities.json"
    if not cap_file.exists():
        return {}

    try:
        return dict(json.loads(cap_file.read_text(encoding="utf-8")))
    except Exception:
        return {}


def _load_capabilities_roadmap(base_dir: Path = None) -> dict[str, Any]:
    """Load capability roadmap from capabilities_roadmap.json."""
    if base_dir is None:
        base_dir = Path(__file__).parent.parent

    roadmap_file = base_dir / "capabilities_roadmap.json"
    if not roadmap_file.exists():
        return {}

    try:
        return dict(json.loads(roadmap_file.read_text(encoding="utf-8")))
    except Exception:
        return {}


def detect_capability_gaps(base_dir: Path = None) -> tuple[list[str], dict[str, Any]]:
    """Detect gaps between registered and declared capabilities.

    Returns:
        (gaps_list, summary_dict)
        - gaps_list: List of capability names that are declared but not yet registered
        - summary_dict: Metadata including finish ownership partition
    """
    if base_dir is None:
        base_dir = Path(__file__).parent.parent

    registered = _load_capabilities_json(base_dir)
    roadmap = _load_capabilities_roadmap(base_dir)

    if not roadmap:
        return [], {"ok": False, "reason": "roadmap_missing"}

    declared_caps = roadmap.get("declared_capabilities", {})
    if not isinstance(declared_caps, dict):
        return [], {"ok": False, "reason": "declared_capabilities_invalid"}

    registered_names = set(str(name or "").strip().lower() for name in registered.keys())
    declared_names = set(str(name or "").strip().lower() for name in declared_caps.keys())

    gaps = sorted(list(declared_names - registered_names))

    from services.capability_finish_ownership import partition_capability_gaps

    ownership = partition_capability_gaps(gaps, roadmap=roadmap)

    gap_config = roadmap.get("gap_detection_config", {})
    enabled = bool(gap_config.get("enabled", True))

    summary = {
        "ok": True,
        "enabled": enabled,
        "registered_count": len(registered_names),
        "declared_count": len(declared_names),
        "gap_count": len(gaps),
        "gaps": gaps,
        "gap_detection_ts": "",
        "nova_code_gap_count": int(ownership.get("nova_code_count") or 0),
        "external_gap_count": int(ownership.get("external_count") or 0),
        "nova_code_gaps": list(ownership.get("nova_code_gap_names") or []),
        "external_gaps": list(ownership.get("external_gap_names") or []),
        "finish_ownership": ownership,
    }

    return gaps, summary


def enhance_status_with_capability_gaps(status_payload: dict[str, Any], base_dir: Path = None) -> dict[str, Any]:
    """Inject capability gap information into status payload."""
    gaps, summary = detect_capability_gaps(base_dir)

    enhanced = dict(status_payload)
    enhanced["capability_gap_count"] = len(gaps)
    enhanced["capability_gaps"] = gaps
    enhanced["capabilities_gap_summary"] = summary
    enhanced["capability_gaps_nova_code"] = list(summary.get("nova_code_gaps") or [])
    enhanced["capability_gaps_external"] = list(summary.get("external_gaps") or [])
    enhanced["capability_gap_nova_code_count"] = int(summary.get("nova_code_gap_count") or 0)
    enhanced["capability_gap_external_count"] = int(summary.get("external_gap_count") or 0)
    enhanced["capability_finish_ownership"] = dict(summary.get("finish_ownership") or {})

    registered = _load_capabilities_json(base_dir)
    enhanced["capabilities_registered"] = dict(registered)

    roadmap = _load_capabilities_roadmap(base_dir)
    if roadmap:
        enhanced["capabilities_roadmap"] = roadmap

    return enhanced


CAPABILITY_GAP_DETECTOR_SERVICE = type(
    "CapabilityGapDetectorService",
    (),
    {
        "detect_capability_gaps": staticmethod(detect_capability_gaps),
        "enhance_status_with_capability_gaps": staticmethod(enhance_status_with_capability_gaps),
        "load_capabilities_json": staticmethod(_load_capabilities_json),
        "load_capabilities_roadmap": staticmethod(_load_capabilities_roadmap),
    },
)()
