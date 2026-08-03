"""Shared tool name identity and evidence quality for progress honesty.

Not the full tool registry. This module owns:

  - stable name constants (one edit + grep for renames)
  - EVIDENCE_QUALITY: verified vs observed evidence tier
  - optional TOOL_ALIASES for historical evidence rows after a rename

Quality is policy, not "is registered." ``read`` is registered and observed;
``release_rebuild_verify`` is registered and verified. Tool authors may own
this on the registry later; until then, this file is the single surface.

Membership against known work-tree tool names is enforced in tests only —
never at import/startup.
"""
from __future__ import annotations

from typing import Iterable

# ---------------------------------------------------------------------------
# Name constants (canonical spellings used in evidence and ladders)
# ---------------------------------------------------------------------------

READ = "read"
FIND = "find"
PULSE = "pulse"
LS = "ls"

RELEASE_REBUILD_VERIFY = "release_rebuild_verify"
RELEASE_RECORD_VALIDATION_OUTCOME = "release_record_validation_outcome"
RELEASE_VALIDATION_RUN = "release_validation_run"
RELEASE_PROMOTION_JUDGMENT = "release_promotion_judgment"

PHASE2_AUDIT = "phase2_audit"
OPERATOR_RESPONSE = "operator_response"
SOURCE_ROOT_JUDGMENT = "source_root_judgment"
GENERATED_QUEUE_RUN = "generated_queue_run"
MEMORY_BOOTSTRAP_JUDGMENT = "memory_bootstrap_judgment"
SUBCONSCIOUS_REVIEW_JUDGMENT = "subconscious_review_judgment"
INSTALLER_VALIDATION_RUN = "installer_validation_run"

# Structured judgment tools (schema+verdict payloads). Used by evidence_validity
# and specialized judgment detectors — single name surface for renames.
STRUCTURED_JUDGMENT_TOOLS: frozenset[str] = frozenset(
    {
        MEMORY_BOOTSTRAP_JUDGMENT,
        RELEASE_PROMOTION_JUDGMENT,
        SUBCONSCIOUS_REVIEW_JUDGMENT,
        SOURCE_ROOT_JUDGMENT,
    }
)

# ---------------------------------------------------------------------------
# Evidence quality policy: verified | observed
# ---------------------------------------------------------------------------

EVIDENCE_QUALITY: dict[str, str] = {
    # Observation-tier (read/find class)
    READ: "observed",
    FIND: "observed",
    PULSE: "observed",
    LS: "observed",
    # Verification-tier (specialized judgment / release / queue tools)
    RELEASE_REBUILD_VERIFY: "verified",
    RELEASE_RECORD_VALIDATION_OUTCOME: "verified",
    RELEASE_VALIDATION_RUN: "verified",
    RELEASE_PROMOTION_JUDGMENT: "verified",
    PHASE2_AUDIT: "verified",
    OPERATOR_RESPONSE: "verified",
    SOURCE_ROOT_JUDGMENT: "verified",
    GENERATED_QUEUE_RUN: "verified",
    MEMORY_BOOTSTRAP_JUDGMENT: "verified",
    SUBCONSCIOUS_REVIEW_JUDGMENT: "verified",
    INSTALLER_VALIDATION_RUN: "verified",
}

VERIFIED_TOOLS: frozenset[str] = frozenset(
    name for name, tier in EVIDENCE_QUALITY.items() if tier == "verified"
)
OBSERVED_TOOLS: frozenset[str] = frozenset(
    name for name, tier in EVIDENCE_QUALITY.items() if tier == "observed"
)

# Historical evidence: map old tool_name strings → current constant value.
# Empty until a rename happens; then add old → new so SQLite rows still measure.
TOOL_ALIASES: dict[str, str] = {}


def canonicalize_tool_name(name: object) -> str:
    """Normalize and resolve aliases for evidence / marker tool strings."""
    raw = str(name or "").strip().lower()
    if not raw:
        return ""
    return TOOL_ALIASES.get(raw, raw)


def evidence_quality(tool_name: object) -> str:
    """Return ``verified``, ``observed``, or ``unknown`` for a tool name."""
    canon = canonicalize_tool_name(tool_name)
    if not canon:
        return "unknown"
    return str(EVIDENCE_QUALITY.get(canon) or "unknown")


def is_verified_tool(tool_name: object) -> bool:
    return evidence_quality(tool_name) == "verified"


def is_observed_tool(tool_name: object) -> bool:
    return evidence_quality(tool_name) == "observed"


def quality_names(*, tier: str) -> frozenset[str]:
    want = str(tier or "").strip().lower()
    return frozenset(name for name, q in EVIDENCE_QUALITY.items() if q == want)


def all_quality_tool_names() -> frozenset[str]:
    return frozenset(EVIDENCE_QUALITY.keys()) | frozenset(TOOL_ALIASES.keys())


def collect_marker_tool_names(markers: Iterable[object]) -> frozenset[str]:
    """Gather tools= and verify_tools= from SolutionMarker-like objects."""
    found: set[str] = set()
    for marker in markers:
        for attr in ("tools", "verify_tools"):
            values = getattr(marker, attr, ()) or ()
            for item in values:
                name = canonicalize_tool_name(item)
                if name:
                    found.add(name)
    return frozenset(found)
