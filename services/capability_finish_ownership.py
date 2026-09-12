"""Ownership of unfinished capability work: who must finish it.

Nova-code gaps are climbable in-repo. External/operator gaps need pieces
Nova does not have — finish those areas by naming missing pieces honestly,
not by thrashing codegen on them.
"""
from __future__ import annotations

from typing import Any

# Default when roadmap omits ownership. Prefer roadmap overrides.
DEFAULT_FINISH_OWNERSHIP: dict[str, dict[str, str]] = {
    # In-repo code finish work
    "codegen_tool": {
        "finisher": "nova_code",
        "missing": "Complete and register codegen tool surface if not already real",
    },
    "codegen_patch_bridge": {
        "finisher": "nova_code",
        "missing": "Complete and register patch bridge if not already real",
    },
    "capability_gap_detection": {
        "finisher": "nova_code",
        "missing": "Register capability_gap_detection once detection is accepted as shipped",
    },
    "autonomous_code_generation": {
        "finisher": "nova_code",
        "missing": "Wire autonomous codegen path end to end under policy",
    },
    "generated_code_tests": {
        "finisher": "nova_code",
        "missing": "Generate and attach tests for generated artifacts",
    },
    "code_generation_memory": {
        "finisher": "nova_code",
        "missing": "Persist and reuse codegen patterns in production path",
    },
    "leah_conversation_continuity": {
        "finisher": "nova_code",
        "missing": "Finish continuity wiring and honest registration",
    },
    "leah_memory_recall": {
        "finisher": "nova_code",
        "missing": "Finish Leah recall path on real memory surfaces",
    },
    "leah_emotional_state_model": {
        "finisher": "nova_code",
        "missing": None,
    },
    "dependency_resolution": {
        "finisher": "nova_code",
        "missing": "Implement package dependency analysis for generated code",
    },
    "type_checking": {
        "finisher": "nova_code",
        "missing": "Wire static type/lint pass for generated code",
    },
    "configuration_management": {
        "finisher": "nova_code",
        "missing": "Generate config schemas/validation in-repo",
    },
    "documentation_generation": {
        "finisher": "nova_code",
        "missing": "Generate API/docs from code artifacts",
    },
    "integration_testing": {
        "finisher": "nova_code",
        "missing": "Generate/run integration tests for generated features",
    },
    # Needs environment / models / runtime stack
    "leah_voice_persona_engine": {
        "finisher": "environment",
        "missing": "Voice/TTS runtime, models, and machine capacity",
    },
    # Needs product decision + external systems (not local thrash)
    "api_gateway": {
        "finisher": "operator_product",
        "missing": "Product design and hosting for HTTP API gateway surface",
    },
    "database_schema_generation": {
        "finisher": "operator_product",
        "missing": "Target DB product choice and migration authority",
    },
    "performance_profiling": {
        "finisher": "environment",
        "missing": "Profiler tooling and representative workloads",
    },
    "security_scanning": {
        "finisher": "operator_product",
        "missing": "Scanner product/policy and vulnerability triage ownership",
    },
    "deployment_automation": {
        "finisher": "operator_product",
        "missing": "Deploy target, secrets, and infrastructure authority",
    },
    "rollback_management": {
        "finisher": "operator_product",
        "missing": "Deploy/rollback authority and production change policy",
    },
}

NOVA_CODE_FINISHERS = frozenset({"nova_code"})
EXTERNAL_FINISHERS = frozenset({"operator_product", "operator_policy", "llc_external", "environment", "hardware"})


def _clean_name(value: Any) -> str:
    return str(value or "").strip().lower()


def ownership_from_roadmap(roadmap: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    """Merge defaults with optional roadmap.capability_finish_ownership."""
    out = {k: dict(v) for k, v in DEFAULT_FINISH_OWNERSHIP.items()}
    raw = dict(roadmap or {})
    custom = raw.get("capability_finish_ownership")
    if not isinstance(custom, dict):
        return out
    for name, row in custom.items():
        key = _clean_name(name)
        if not key or not isinstance(row, dict):
            continue
        merged = dict(out.get(key) or {})
        finisher = _clean_name(row.get("finisher") or merged.get("finisher") or "operator_product")
        missing = str(row.get("missing") or merged.get("missing") or "").strip()
        merged["finisher"] = finisher or "operator_product"
        if missing:
            merged["missing"] = missing
        out[key] = merged
    return out


def classify_capability(name: str, *, roadmap: dict[str, Any] | None = None) -> dict[str, str]:
    key = _clean_name(name)
    table = ownership_from_roadmap(roadmap)
    row = dict(table.get(key) or {})
    finisher = _clean_name(row.get("finisher") or "operator_product") or "operator_product"
    missing = str(row.get("missing") or "Finisher and missing piece not declared").strip()
    return {
        "capability": key,
        "finisher": finisher,
        "missing": missing,
        "nova_can_finish_alone": finisher in NOVA_CODE_FINISHERS,
    }


def partition_capability_gaps(
    gaps: list[str],
    *,
    roadmap: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Split gaps into nova-finishable vs needs-external/operator."""
    nova_code: list[dict[str, str]] = []
    external: list[dict[str, str]] = []
    for gap in list(gaps or []):
        row = classify_capability(gap, roadmap=roadmap)
        if row.get("nova_can_finish_alone"):
            nova_code.append(row)
        else:
            external.append(row)
    return {
        "ok": True,
        "nova_code_gaps": nova_code,
        "external_gaps": external,
        "nova_code_gap_names": [r["capability"] for r in nova_code],
        "external_gap_names": [r["capability"] for r in external],
        "nova_code_count": len(nova_code),
        "external_count": len(external),
    }


def nova_code_gap_names(gaps: list[str], *, roadmap: dict[str, Any] | None = None) -> list[str]:
    return list(partition_capability_gaps(gaps, roadmap=roadmap).get("nova_code_gap_names") or [])
