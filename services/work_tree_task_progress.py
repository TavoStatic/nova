"""Work-tree task progress: distance to a defined solution.

Foundation (stable):
  intent → solution → ordered partial truths → evidence → completion

Honesty layer (extensions that keep the same core):
  - prerequisites: later markers cannot count until earlier ones hold
  - quality: observed vs verified (read/find vs specialized tools)
  - confidence: 0.70 observed, 1.0 verified (per counting marker)
  - contradiction: e.g. stale release branch invalidates validation without rebuild chain
  - percent only from markers that count (prereqs met, not contradicted); cap 99 until complete

Ladders:
  - curated seeds (intent + solution + marker semantics)
  - learned proposals from completed history (runtime JSON)
  - hybrid merge prefers curated intent/solution
"""
from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from services.nova_runtime_context import resolve_runtime_dir
from services.tool_identity import (
    FIND,
    GENERATED_QUEUE_RUN,
    OPERATOR_RESPONSE,
    PHASE2_AUDIT,
    PULSE,
    READ,
    RELEASE_PROMOTION_JUDGMENT,
    RELEASE_REBUILD_VERIFY,
    RELEASE_RECORD_VALIDATION_OUTCOME,
    RELEASE_VALIDATION_RUN,
    SOURCE_ROOT_JUDGMENT,
    VERIFIED_TOOLS,
    canonicalize_tool_name,
    is_observed_tool,
    is_verified_tool,
)

SCHEMA = "nova.work_tree_solution_ladder.v1"
DEFAULT_STALL_HOURS = 6.0
_THINNING_PRODUCTIVE_ACTIONS = frozenset({"removed_unused_wrapper"})


def _result_action(row: dict[str, Any]) -> str:
    text = str(row.get("result_text") or "").strip()
    if not text.startswith("{"):
        return ""
    try:
        payload = json.loads(text)
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("action") or "").strip().lower()


def _evidence_counts_toward_markers(row: dict[str, Any]) -> bool:
    """A miss must not look like a solution step."""
    from services.evidence_validity import evidence_result_valid

    if not evidence_result_valid(row):
        return False
    tool = canonicalize_tool_name(row.get("tool_name"))
    if tool != "core_thinning":
        return True
    return _result_action(row) in _THINNING_PRODUCTIVE_ACTIONS


@dataclass(frozen=True)
class SolutionMarker:
    marker_id: str
    label: str
    weight: float
    stage: int = 0
    tools: tuple[str, ...] = ()
    title_keywords: tuple[str, ...] = ()
    result_keywords: tuple[str, ...] = ()
    requires_complete: bool = False
    any_evidence: bool = False
    min_evidence: int = 0
    # Marker ids that must already hold before this marker can count toward %.
    requires_markers: tuple[str, ...] = ()
    # Tools that raise this marker to verified (else VERIFIED_TOOLS ∩ tools).
    verify_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class SolutionLadder:
    family_key: str
    intent: str
    solution: str
    markers: tuple[SolutionMarker, ...]
    source: str = "seeded"  # seeded | learned | hybrid | generic


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def family_key(*, work_class: str = "", source_type: str = "") -> str:
    return f"{_norm(work_class) or 'unknown'}|{_norm(source_type) or 'unknown'}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _runtime_dir() -> Path:
    try:
        return resolve_runtime_dir(_repo_root())
    except Exception:
        return _repo_root() / "runtime"


def learned_ladders_path() -> Path:
    return _runtime_dir() / "work_tree" / "solution_ladders_learned.json"


def work_tree_db_path() -> Path:
    return _runtime_dir() / "_internal" / "work_tree.db"


# ---------------------------------------------------------------------------
# Curated seeds: intent + solution + meaningful intermediate states
# ---------------------------------------------------------------------------

_SEEDED: dict[str, SolutionLadder] = {
    "release_readiness_gap|release": SolutionLadder(
        family_key="release_readiness_gap|release",
        intent="Make the release package trustworthy relative to current source.",
        solution="Package matches live source and a validation outcome is recorded.",
        source="seeded",
        markers=(
            SolutionMarker(
                "package_identified",
                "Current package / ledger identified",
                0.25,
                stage=0,
                tools=(READ,),
                title_keywords=("ledger", "package", "artifact", "seed", "manifest"),
            ),
            SolutionMarker(
                "drift_understood",
                "Source vs package drift understood",
                0.25,
                stage=1,
                tools=(READ, FIND),
                title_keywords=("source", "changed", "stale", "newest", "drift"),
                requires_markers=("package_identified",),
            ),
            SolutionMarker(
                "package_rebuilt",
                "Package rebuilt/verified from current source",
                0.25,
                stage=2,
                tools=(RELEASE_REBUILD_VERIFY,),
                title_keywords=("rebuild", "verify"),
                requires_markers=("drift_understood",),
                verify_tools=(RELEASE_REBUILD_VERIFY,),
            ),
            SolutionMarker(
                "validation_recorded",
                "Validation outcome recorded",
                0.25,
                stage=3,
                tools=(
                    RELEASE_RECORD_VALIDATION_OUTCOME,
                    RELEASE_VALIDATION_RUN,
                    RELEASE_PROMOTION_JUDGMENT,
                ),
                title_keywords=("validation", "outcome", "promotion"),
                requires_markers=("package_rebuilt",),
                verify_tools=(
                    RELEASE_RECORD_VALIDATION_OUTCOME,
                    RELEASE_VALIDATION_RUN,
                    RELEASE_PROMOTION_JUDGMENT,
                ),
            ),
        ),
    ),
    "regression_failure|test_ecosystem": SolutionLadder(
        family_key="regression_failure|test_ecosystem",
        intent="Restore regression truth so compact lanes are trustworthy.",
        solution="Failing cause fixed and regression status is green (or finding satisfied).",
        source="seeded",
        markers=(
            SolutionMarker(
                "failure_located",
                "Failure / profile gap located",
                0.30,
                stage=0,
                tools=(READ, FIND),
                title_keywords=("regression", "profile", "inventory", "status", "lane", "failed"),
            ),
            SolutionMarker(
                "contract_read",
                "Regression contract / inventory understood",
                0.25,
                stage=1,
                tools=(READ,),
                title_keywords=("contract", "inventory", "lanes", "profile"),
                requires_markers=("failure_located",),
            ),
            SolutionMarker(
                "repair_applied",
                "Repair or classification applied",
                0.25,
                stage=2,
                tools=(READ, FIND, SOURCE_ROOT_JUDGMENT),
                title_keywords=("classify", "lane", "hold", "judgment", "fix"),
                requires_markers=("contract_read",),
            ),
            SolutionMarker(
                "regression_green",
                "Regression / finding closed",
                0.20,
                stage=3,
                requires_complete=True,
                requires_markers=("repair_applied",),
            ),
        ),
    ),
    "operator_requested|operator_control": SolutionLadder(
        family_key="operator_requested|operator_control",
        intent="Clear operator-control pressure so autonomy can proceed.",
        solution="Outbox item answered/resolved or no longer actionable.",
        source="seeded",
        markers=(
            SolutionMarker(
                "outbox_seen",
                "Open outbox item identified",
                0.35,
                stage=0,
                tools=(READ, OPERATOR_RESPONSE),
                title_keywords=("outbox", "operator", "notice"),
            ),
            SolutionMarker(
                "response_recorded",
                "Operator response or dismissal recorded",
                0.40,
                stage=1,
                tools=(OPERATOR_RESPONSE, READ),
                title_keywords=("response", "dismiss", "authority", "wait"),
                requires_markers=("outbox_seen",),
                verify_tools=(OPERATOR_RESPONSE,),
            ),
            SolutionMarker(
                "pressure_cleared",
                "Operator pressure cleared",
                0.25,
                stage=2,
                requires_complete=True,
                requires_markers=("response_recorded",),
            ),
        ),
    ),
    "governance_pressure|safety_envelope": SolutionLadder(
        family_key="governance_pressure|safety_envelope",
        intent="Settle safety-envelope review pressure.",
        solution="Pending/quarantine review pressure cleared.",
        source="seeded",
        markers=(
            SolutionMarker(
                "pressure_seen",
                "Safety review pressure identified",
                0.30,
                stage=0,
                tools=(READ, PHASE2_AUDIT),
                title_keywords=("safety", "envelope", "review", "quarantine"),
            ),
            SolutionMarker(
                "audit_run",
                "Safety audit / review step run",
                0.45,
                stage=1,
                tools=(PHASE2_AUDIT,),
                title_keywords=("audit", "phase2", "review"),
                requires_markers=("pressure_seen",),
                verify_tools=(PHASE2_AUDIT,),
            ),
            SolutionMarker(
                "settled",
                "Review pressure settled",
                0.25,
                stage=2,
                requires_complete=True,
                requires_markers=("audit_run",),
            ),
        ),
    ),
    "governance_pressure|test_ecosystem": SolutionLadder(
        family_key="governance_pressure|test_ecosystem",
        intent="Validation profile matches source tests (no harmful drift).",
        solution="Profile inventory clean enough for compact regression truth.",
        source="seeded",
        markers=(
            SolutionMarker(
                "drift_seen",
                "Profile drift / gap identified",
                0.30,
                stage=0,
                tools=(READ,),
                title_keywords=("profile", "drift", "observed", "inventory", "lane"),
            ),
            SolutionMarker(
                "contract_read",
                "Inventory contract read",
                0.35,
                stage=1,
                tools=(READ,),
                title_keywords=("contract", "inventory", "lane"),
                requires_markers=("drift_seen",),
            ),
            SolutionMarker(
                "classified",
                "Tests classified or finding closed",
                0.35,
                stage=2,
                requires_complete=True,
                requires_markers=("contract_read",),
            ),
        ),
    ),
    "governance_pressure|root_closure_inventory": SolutionLadder(
        family_key="governance_pressure|root_closure_inventory",
        intent="Close source-root / wiring gaps so roots are fully represented.",
        solution="Inventory and wiring probe no longer report blocking gaps for this finding.",
        source="seeded",
        markers=(
            SolutionMarker(
                "gap_located",
                "Unwired root or file gap located",
                0.30,
                stage=0,
                tools=(READ, FIND, PULSE),
                title_keywords=("root", "wiring", "inventory", "unwired", "gap"),
            ),
            SolutionMarker(
                "judgment",
                "Source-root judgment / classification applied",
                0.40,
                stage=1,
                tools=(SOURCE_ROOT_JUDGMENT, READ, FIND),
                title_keywords=("judgment", "classify", "inventory"),
                requires_markers=("gap_located",),
                verify_tools=(SOURCE_ROOT_JUDGMENT,),
            ),
            SolutionMarker(
                "closed",
                "Root closure finding closed",
                0.30,
                stage=2,
                requires_complete=True,
                requires_markers=("judgment",),
            ),
        ),
    ),
    "generated_session_repair|generated_queue_item": SolutionLadder(
        family_key="generated_session_repair|generated_queue_item",
        intent="Run or repair a generated session so queue pressure clears.",
        solution="Generated queue item executed or repaired to completion.",
        source="seeded",
        markers=(
            SolutionMarker(
                "item_seen",
                "Queue item identified",
                0.25,
                stage=0,
                any_evidence=True,
            ),
            SolutionMarker(
                "queue_run",
                "Generated queue run executed",
                0.50,
                stage=1,
                tools=(GENERATED_QUEUE_RUN,),
                requires_markers=("item_seen",),
                verify_tools=(GENERATED_QUEUE_RUN,),
            ),
            SolutionMarker(
                "closed",
                "Queue item closed",
                0.25,
                stage=2,
                requires_complete=True,
                requires_markers=("queue_run",),
            ),
        ),
    ),
    "core_thinning|core_scan": SolutionLadder(
        family_key="core_thinning|core_scan",
        intent="Thin wrappers and HTTP surfaces the core scan still owns.",
        solution="Unused wrapper removed. Mapping is a look, not a close.",
        source="seeded",
        markers=(
            SolutionMarker(
                "started",
                "Thinning evidence recorded",
                0.30,
                stage=0,
                any_evidence=True,
            ),
            SolutionMarker(
                "via_core_thinning",
                "Unused wrapper removed",
                0.50,
                stage=1,
                tools=("core_thinning",),
                requires_markers=("started",),
            ),
            SolutionMarker(
                "closed",
                "Finding closed after a real removal",
                0.20,
                stage=2,
                requires_complete=True,
                requires_markers=("via_core_thinning",),
            ),
        ),
    ),
}


def _generic_ladder(family: str) -> SolutionLadder:
    return SolutionLadder(
        family_key=family or "unknown|unknown",
        intent="Move this work item from open pressure to a closed, evidenced outcome.",
        solution="Task complete with supporting evidence (or finding satisfied).",
        source="generic",
        markers=(
            SolutionMarker(
                "started",
                "First investigation evidence recorded",
                0.40,
                stage=0,
                any_evidence=True,
            ),
            SolutionMarker(
                "advanced",
                "Multiple evidence steps recorded",
                0.30,
                stage=1,
                min_evidence=2,
                requires_markers=("started",),
            ),
            SolutionMarker(
                "closed",
                "Task completed",
                0.30,
                stage=2,
                requires_complete=True,
                requires_markers=("advanced",),
            ),
        ),
    )


def _marker_from_dict(raw: dict[str, Any], *, stage: int = 0) -> SolutionMarker | None:
    mid = str(raw.get("marker_id") or raw.get("id") or "").strip()
    label = str(raw.get("label") or mid).strip()
    if not mid or not label:
        return None
    try:
        weight = float(raw.get("weight") or 0.0)
    except Exception:
        weight = 0.0
    if weight <= 0:
        weight = 0.2
    tools = tuple(str(t).strip() for t in list(raw.get("tools") or []) if str(t).strip())
    title_kw = tuple(str(t).strip() for t in list(raw.get("title_keywords") or []) if str(t).strip())
    result_kw = tuple(str(t).strip() for t in list(raw.get("result_keywords") or []) if str(t).strip())
    try:
        stage_n = int(raw.get("stage", stage))
    except Exception:
        stage_n = stage
    try:
        min_ev = int(raw.get("min_evidence") or 0)
    except Exception:
        min_ev = 0
    requires = tuple(
        str(t).strip() for t in list(raw.get("requires_markers") or raw.get("requires") or []) if str(t).strip()
    )
    verify = tuple(str(t).strip() for t in list(raw.get("verify_tools") or []) if str(t).strip())
    return SolutionMarker(
        marker_id=mid[:80],
        label=label[:160],
        weight=weight,
        stage=max(0, stage_n),
        tools=tools,
        title_keywords=title_kw,
        result_keywords=result_kw,
        requires_complete=bool(raw.get("requires_complete")),
        any_evidence=bool(raw.get("any_evidence")),
        min_evidence=max(0, min_ev),
        requires_markers=requires,
        verify_tools=verify,
    )


def _ladder_from_dict(raw: dict[str, Any]) -> SolutionLadder | None:
    if not isinstance(raw, dict):
        return None
    key = str(raw.get("family_key") or "").strip()
    intent = str(raw.get("intent") or "").strip()
    solution = str(raw.get("solution") or "").strip()
    if not key:
        return None
    markers: list[SolutionMarker] = []
    for idx, item in enumerate(list(raw.get("markers") or [])):
        if not isinstance(item, dict):
            continue
        marker = _marker_from_dict(item, stage=idx)
        if marker is not None:
            markers.append(marker)
    if not markers:
        return None
    # normalize weights
    total = sum(m.weight for m in markers) or 1.0
    normed = tuple(
        SolutionMarker(
            marker_id=m.marker_id,
            label=m.label,
            weight=m.weight / total,
            stage=m.stage,
            tools=m.tools,
            title_keywords=m.title_keywords,
            result_keywords=m.result_keywords,
            requires_complete=m.requires_complete,
            any_evidence=m.any_evidence,
            min_evidence=m.min_evidence,
            requires_markers=m.requires_markers,
            verify_tools=m.verify_tools,
        )
        for m in markers
    )
    return SolutionLadder(
        family_key=key,
        intent=intent or f"Resolve work for {key}.",
        solution=solution or "Task complete with supporting evidence.",
        markers=normed,
        source=str(raw.get("source") or "learned"),
    )


def load_learned_ladders(*, path: Path | None = None) -> dict[str, SolutionLadder]:
    target = Path(path) if path is not None else learned_ladders_path()
    if not target.is_file():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    families = data.get("families") if isinstance(data, dict) else None
    if not isinstance(families, dict):
        return {}
    out: dict[str, SolutionLadder] = {}
    for key, raw in families.items():
        ladder = _ladder_from_dict(dict(raw) if isinstance(raw, dict) else {})
        if ladder is not None:
            out[str(key)] = ladder
    return out


def save_learned_ladders(
    families: dict[str, SolutionLadder],
    *,
    path: Path | None = None,
    meta: dict[str, Any] | None = None,
) -> Path:
    target = Path(path) if path is not None else learned_ladders_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "meta": dict(meta or {}),
        "families": {
            key: {
                "family_key": ladder.family_key,
                "intent": ladder.intent,
                "solution": ladder.solution,
                "source": ladder.source,
                "markers": [
                    {
                        "marker_id": m.marker_id,
                        "label": m.label,
                        "weight": m.weight,
                        "stage": m.stage,
                        "tools": list(m.tools),
                        "title_keywords": list(m.title_keywords),
                        "result_keywords": list(m.result_keywords),
                        "requires_complete": m.requires_complete,
                        "any_evidence": m.any_evidence,
                        "min_evidence": m.min_evidence,
                        "requires_markers": list(m.requires_markers),
                        "verify_tools": list(m.verify_tools),
                    }
                    for m in ladder.markers
                ],
            }
            for key, ladder in families.items()
        },
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return target


def _merge_ladder(seeded: SolutionLadder | None, learned: SolutionLadder | None, family: str) -> SolutionLadder:
    if seeded is not None and learned is None:
        return seeded
    if seeded is None and learned is not None:
        return learned
    if seeded is None and learned is None:
        return _generic_ladder(family)
    # Prefer seeded intent/solution; keep seeded markers (semantic); optionally
    # append high-frequency learned tools not already represented.
    assert seeded is not None and learned is not None
    known_tools = {t for m in seeded.markers for t in m.tools}
    extras: list[SolutionMarker] = []
    for m in learned.markers:
        if m.requires_complete or m.any_evidence:
            continue
        novel = [t for t in m.tools if t and t not in known_tools]
        if not novel:
            continue
        extras.append(
            SolutionMarker(
                marker_id=f"learned_{m.marker_id}"[:80],
                label=m.label or f"Learned step via {', '.join(novel[:2])}",
                weight=0.12,
                stage=max((x.stage for x in seeded.markers), default=0) + 1 + len(extras),
                tools=tuple(novel[:4]),
            )
        )
        if len(extras) >= 2:
            break
    if not extras:
        return SolutionLadder(
            family_key=seeded.family_key,
            intent=seeded.intent,
            solution=seeded.solution,
            markers=seeded.markers,
            source="seeded",
        )
    combined = list(seeded.markers) + extras
    total = sum(m.weight for m in combined) or 1.0
    normed = tuple(
        SolutionMarker(
            marker_id=m.marker_id,
            label=m.label,
            weight=m.weight / total,
            stage=m.stage,
            tools=m.tools,
            title_keywords=m.title_keywords,
            result_keywords=m.result_keywords,
            requires_complete=m.requires_complete,
            any_evidence=m.any_evidence,
            min_evidence=m.min_evidence,
            requires_markers=m.requires_markers,
            verify_tools=m.verify_tools,
        )
        for m in combined
    )
    return SolutionLadder(
        family_key=seeded.family_key,
        intent=seeded.intent,
        solution=seeded.solution,
        markers=normed,
        source="hybrid",
    )


def get_ladder(
    *,
    work_class: str = "",
    source_type: str = "",
    learned: dict[str, SolutionLadder] | None = None,
) -> SolutionLadder:
    key = family_key(work_class=work_class, source_type=source_type)
    learned_map = learned if learned is not None else load_learned_ladders()
    seeded = _SEEDED.get(key)
    if seeded is None:
        for sk, ladder in _SEEDED.items():
            if _norm(work_class) and sk.startswith(_norm(work_class) + "|"):
                seeded = ladder
                break
    learned_ladder = learned_map.get(key)
    return _merge_ladder(seeded, learned_ladder, key)


def _evidence_blob(row: dict[str, Any]) -> str:
    parts = [
        canonicalize_tool_name(row.get("tool_name")),
        _norm(row.get("result_text")),
        " ".join(_norm(x) for x in list(row.get("tool_args") or [])),
    ]
    return " ".join(parts)


def _evidence_tool(row: dict[str, Any]) -> str:
    return canonicalize_tool_name(row.get("tool_name"))


def _raw_observation(
    marker: SolutionMarker,
    *,
    task_title: str,
    task_status: str,
    evidence: list[dict[str, Any]],
) -> tuple[bool, str, str]:
    """Return (seen, note, quality) quality in {absent, observed, verified}."""
    status = _norm(task_status)
    if marker.requires_complete:
        if status in {"complete", "completed", "done"}:
            return True, "task status complete", "verified"
        return False, "task not complete yet", "absent"

    if marker.min_evidence > 0:
        if len(evidence) >= marker.min_evidence:
            return True, f"evidence_count={len(evidence)}", "observed"
        return False, f"need {marker.min_evidence}+ evidence steps", "absent"

    if marker.any_evidence:
        if evidence:
            quality = (
                "verified"
                if any(is_verified_tool(_evidence_tool(r)) for r in evidence)
                else "observed"
            )
            return True, f"evidence_count={len(evidence)}", quality
        return False, "no evidence yet", "absent"

    title = _norm(task_title)
    tool_set = {canonicalize_tool_name(t) for t in marker.tools if canonicalize_tool_name(t)}
    keys = [_norm(k) for k in (marker.title_keywords + marker.result_keywords) if _norm(k)]
    verify_set = {canonicalize_tool_name(t) for t in marker.verify_tools if canonicalize_tool_name(t)} or (
        tool_set & set(VERIFIED_TOOLS)
    )

    if tool_set:
        for row in evidence:
            tool = _evidence_tool(row)
            if tool not in tool_set:
                continue
            if tool in verify_set or is_verified_tool(tool):
                return True, f"tool={tool}", "verified"
            if keys:
                blob = title + " " + _evidence_blob(row)
                if any(k in blob for k in keys) or any(k in title for k in keys):
                    return True, f"tool={tool} matched keywords", "observed"
            else:
                # Unknown tools are not verified. Verified is only the listed tier.
                quality = "verified" if is_verified_tool(tool) else "observed"
                return True, f"tool={tool}", quality
        return False, "marker tool/evidence not seen", "absent"

    if keys:
        for row in evidence:
            blob = title + " " + _evidence_blob(row)
            if any(k in blob for k in keys):
                tool = _evidence_tool(row)
                quality = "verified" if is_verified_tool(tool) else "observed"
                return True, "keyword match in evidence", quality
        return False, "keywords not seen in evidence", "absent"

    return False, "no match rule", "absent"


def _marker_achieved(
    marker: SolutionMarker,
    *,
    task_title: str,
    task_status: str,
    evidence: list[dict[str, Any]],
) -> tuple[bool, str]:
    seen, note, _quality = _raw_observation(
        marker, task_title=task_title, task_status=task_status, evidence=evidence
    )
    return seen, note


def _confidence_for(quality: str, *, holds: bool) -> float:
    if not holds:
        return 0.0
    if quality == "verified":
        return 1.0
    if quality == "observed":
        return 0.70
    return 0.0


def _release_contradictions(
    *,
    branch_title: str,
    marker_id: str,
    evidence: list[dict[str, Any]],
    context: dict[str, Any] | None,
) -> tuple[bool, str]:
    ctx = dict(context or {})
    stale = bool(ctx.get("release_stale")) or (
        "stale" in _norm(branch_title) and "source" in _norm(branch_title)
    )
    if not stale or marker_id not in {"package_rebuilt", "validation_recorded"}:
        return False, ""
    rebuild_rows = [
        r for r in evidence if _evidence_tool(r) == RELEASE_REBUILD_VERIFY
    ]
    if marker_id == "validation_recorded":
        if not rebuild_rows:
            return True, "stale release branch: validation cannot hold without rebuild"
        last_rebuild = _parse_ts(str(rebuild_rows[-1].get("created_at") or "")) or 0.0
        val_tools = {
            RELEASE_RECORD_VALIDATION_OUTCOME,
            RELEASE_VALIDATION_RUN,
            RELEASE_PROMOTION_JUDGMENT,
        }
        later_val = [
            r
            for r in evidence
            if _evidence_tool(r) in val_tools
            and (_parse_ts(str(r.get("created_at") or "")) or 0.0) >= last_rebuild
        ]
        if not later_val:
            return True, "stale release branch: no validation after latest rebuild"
    return False, ""


def _parse_ts(value: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(text[:26], fmt).timestamp()
        except Exception:
            continue
    return None


def _motion(
    *,
    percent: int,
    task_status: str,
    evidence: list[dict[str, Any]],
    stall_hours: float = DEFAULT_STALL_HOURS,
) -> str:
    status = _norm(task_status)
    if status in {"complete", "completed", "done"} or percent >= 100:
        return "done"
    if status in {"blocked"}:
        return "blocked"
    if not evidence:
        return "not_started"
    last = evidence[-1] if evidence else {}
    ts = _parse_ts(str(last.get("created_at") or ""))
    if ts is not None and stall_hours > 0:
        age_h = (time.time() - ts) / 3600.0
        if age_h >= float(stall_hours):
            return "stalled"
    return "moving"


def measure_solution_progress(
    *,
    work_class: str = "",
    source_type: str = "",
    branch_title: str = "",
    current_step_title: str = "",
    solution_status: str = "",
    evidence: list[dict[str, Any]] | None = None,
    expected_tool: str = "",
    stall_hours: float = DEFAULT_STALL_HOURS,
    learned: dict[str, SolutionLadder] | None = None,
    context: dict[str, Any] | None = None,
    branch_id: str = "",
    current_task_id: str = "",
) -> dict[str, Any]:
    """Distance to a defined solution for one finding/branch.

    Root unit: the solution (branch/finding), not an individual sequence stem.
    Intermediate task completion must never force 100% — only solution_status
    complete (finding closed) does.
    """
    ladder = get_ladder(work_class=work_class, source_type=source_type, learned=learned)
    rows = list(evidence or [])
    marker_evidence = [row for row in rows if isinstance(row, dict) and _evidence_counts_toward_markers(row)]
    effort = [
        {
            "evidence_id": str(row.get("evidence_id") or ""),
            "tool_name": str(row.get("tool_name") or ""),
            "created_at": str(row.get("created_at") or ""),
            "summary": str(row.get("result_text") or "")[:180],
            "tool_args": list(row.get("tool_args") or [])[:6],
        }
        for row in rows
    ]

    status = _norm(solution_status)
    marker_rows: list[dict[str, Any]] = []
    # Observation context is the solution (branch), plus the active step for
    # keyword context — never a lone stem title that erases prior work.
    combined_title = f"{branch_title} {current_step_title}".strip()
    ctx = dict(context or {})
    if "stale" in _norm(branch_title) and "source" in _norm(branch_title):
        ctx.setdefault("release_stale", True)

    holding: dict[str, bool] = {}
    ordered = sorted(ladder.markers, key=lambda m: (m.stage, m.marker_id))

    conf_hold: list[float] = []
    solution_closed = status in {"complete", "completed", "done", "resolved", "retired"}
    # Closing a finding without tool evidence must not invent 100% verified work.
    # That produced "100% done" with empty "Completed so far" in the control panel.
    closed_without_effort = bool(solution_closed and not marker_evidence)
    closed_with_effort = bool(solution_closed and marker_evidence)

    earned = 0.0
    total_w = 0.0
    for marker in ordered:
        total_w += float(marker.weight)
        if closed_with_effort:
            # Finding closed after real work: solution unit is complete.
            holding[marker.marker_id] = True
            conf_hold.append(1.0)
            marker_rows.append(
                {
                    "id": marker.marker_id,
                    "label": marker.label,
                    "weight": marker.weight,
                    "stage": marker.stage,
                    "requires_markers": list(marker.requires_markers),
                    "observed": True,
                    "verified": True,
                    "still_valid": True,
                    "contradicted": False,
                    "prereqs_met": True,
                    "counts": True,
                    "achieved": True,
                    "quality": "verified",
                    "confidence": 1.0,
                    "note": "solution closed with recorded effort",
                }
            )
            earned += float(marker.weight)
            continue

        seen, note, quality = _raw_observation(
            marker,
            task_title=combined_title,
            task_status=solution_status,
            evidence=marker_evidence,
        )
        missing_prereq = [
            mid for mid in marker.requires_markers if not holding.get(mid, False)
        ]
        prereqs_met = not missing_prereq
        raw_contradicted, cnote = _release_contradictions(
            branch_title=branch_title,
            marker_id=marker.marker_id,
            evidence=rows,
            context=ctx,
        )
        contradicted = bool(raw_contradicted and seen)
        counts = bool(seen and prereqs_met and not contradicted)
        holding[marker.marker_id] = counts
        if counts:
            earned += float(marker.weight)
        verified = quality == "verified" and counts
        observed = seen
        still_valid = counts
        if closed_without_effort:
            note = "finding closed without recorded tool effort"
        elif contradicted:
            note = cnote or note
        elif missing_prereq and seen:
            note = f"seen but blocked by prerequisites: {', '.join(missing_prereq)}"
        conf = _confidence_for(quality if counts else "absent", holds=counts)
        if counts:
            conf_hold.append(conf)
        marker_rows.append(
            {
                "id": marker.marker_id,
                "label": marker.label,
                "weight": marker.weight,
                "stage": marker.stage,
                "requires_markers": list(marker.requires_markers),
                "observed": observed,
                "verified": verified,
                "still_valid": still_valid,
                "contradicted": contradicted,
                "prereqs_met": prereqs_met,
                "counts": counts,
                "achieved": counts,
                "quality": quality if seen else "absent",
                "confidence": conf,
                "note": note,
            }
        )

    if closed_with_effort:
        percent = 100
        motion = "done"
        confidence_avg = 1.0
    elif total_w <= 0:
        percent = 0
        motion = "done" if solution_closed else _motion(
            percent=0,
            task_status=solution_status,
            evidence=rows,
            stall_hours=stall_hours,
        )
        confidence_avg = 0.0
    else:
        percent = int(round(100.0 * min(1.0, earned / total_w)))
        if percent >= 100 and not solution_closed:
            percent = 99
        if closed_without_effort:
            # Administrative close / retired with no tools — never paint full solution.
            percent = 0
            motion = "done"
            confidence_avg = 0.0
        else:
            motion = _motion(
                percent=percent,
                task_status=solution_status,
                evidence=rows,
                stall_hours=stall_hours,
            )
            confidence_avg = (sum(conf_hold) / len(conf_hold)) if conf_hold else 0.0

    remaining = [m for m in marker_rows if not m.get("counts")]
    next_marker = remaining[0] if remaining else None
    achieved_n = sum(1 for m in marker_rows if m.get("counts"))

    if closed_without_effort:
        operator_summary = (
            f"{int(percent)}% · closed without recorded tool effort · "
            f"{achieved_n}/{len(marker_rows)} markers counting"
        )
    else:
        operator_summary = (
            f"{int(percent)}% · {motion} · "
            f"{achieved_n}/{len(marker_rows)} markers counting"
            + (
                f" · conf {round(float(confidence_avg), 2)}"
                if (not solution_closed) and conf_hold
                else ""
            )
        )

    return {
        "unit": "solution",
        "percent": int(percent),
        "motion": motion,
        "confidence": round(float(1.0 if closed_with_effort else confidence_avg), 2),
        "intent": ladder.intent,
        "solution": ladder.solution,
        "family_key": ladder.family_key,
        "ladder_source": ladder.source,
        "expected_tool": str(expected_tool or "").strip(),
        "markers": marker_rows,
        "markers_achieved": achieved_n,
        "markers_total": len(marker_rows),
        "next_marker": next_marker,
        "effort": effort,
        "effort_count": len(effort),
        "closed_without_effort": closed_without_effort,
        "branch_id": str(branch_id or ""),
        "branch_title": str(branch_title or ""),
        "current_task_id": str(current_task_id or ""),
        "current_step_title": str(current_step_title or ""),
        "solution_status": str(solution_status or ""),
        "doing": str(current_step_title or branch_title or "").strip() or ladder.intent,
        "operator_summary": operator_summary,
    }


def measure_task_progress(
    *,
    task_id: str = "",
    task_title: str = "",
    task_status: str = "",
    work_class: str = "",
    source_type: str = "",
    branch_title: str = "",
    evidence: list[dict[str, Any]] | None = None,
    task_meta: dict[str, Any] | None = None,
    stall_hours: float = DEFAULT_STALL_HOURS,
    learned: dict[str, SolutionLadder] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper around measure_solution_progress.

    Prefer measure_solution_progress / work_tree branch progress for live loop.
    When callers pass task_status=complete they mean the *solution* is closed
    (legacy tests); intermediate stems must not use that path.
    """
    meta = dict(task_meta or {})
    payload = measure_solution_progress(
        work_class=work_class,
        source_type=source_type,
        branch_title=branch_title,
        current_step_title=task_title,
        solution_status=task_status,
        evidence=evidence,
        expected_tool=str(meta.get("expected_tool") or "").strip(),
        stall_hours=stall_hours,
        learned=learned,
        context=context,
        current_task_id=task_id,
    )
    # Legacy field names expected by older callers/tests.
    payload["task_id"] = str(task_id or "")
    payload["task_title"] = str(task_title or "")
    payload["task_status"] = str(task_status or "")
    return payload


def learn_families_from_history(
    *,
    limit_tasks: int = 1500,
    min_samples: int = 5,
    db_path: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Mine completed tasks and write learned ladders for unknown/weak families."""
    path = Path(db_path) if db_path is not None else work_tree_db_path()
    if not path.is_file():
        return {"ok": False, "error": "work_tree_db_missing", "families": {}}

    by_family: dict[str, list[list[str]]] = defaultdict(list)
    title_samples: dict[str, Counter[str]] = defaultdict(Counter)
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        tasks = conn.execute(
            """
            SELECT t.task_id, t.title, b.work_class, b.source_type, b.title AS branch_title
            FROM work_tree_tasks t
            JOIN work_tree_branches b ON b.branch_id = t.branch_id
            WHERE t.status = 'complete'
            ORDER BY t.updated_at DESC
            LIMIT ?
            """,
            (max(50, int(limit_tasks)),),
        ).fetchall()
        for task in tasks:
            key = family_key(work_class=str(task["work_class"] or ""), source_type=str(task["source_type"] or ""))
            tools = [
                str(r["tool_name"] or "").strip()
                for r in conn.execute(
                    """
                    SELECT tool_name FROM work_tree_evidence
                    WHERE task_id = ?
                    ORDER BY created_at ASC
                    """,
                    (task["task_id"],),
                )
                if str(r["tool_name"] or "").strip()
            ]
            if tools:
                by_family[key].append(tools)
            title_samples[key][str(task["title"] or "").strip()[:80]] += 1
        conn.close()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "families": {}}

    learned: dict[str, SolutionLadder] = {}
    for key, sequences in by_family.items():
        if len(sequences) < int(min_samples):
            continue
        tool_counts: Counter[str] = Counter()
        for seq in sequences:
            for tool in seq:
                tool_counts[tool] += 1
        top_tools = [t for t, _n in tool_counts.most_common(5) if t]
        if not top_tools:
            continue
        # Build staged markers from frequent tools (history-shaped ladder).
        markers: list[SolutionMarker] = [
            SolutionMarker(
                "started",
                "First investigation evidence recorded",
                0.25,
                stage=0,
                any_evidence=True,
            )
        ]
        prev_id = "started"
        for idx, tool in enumerate(top_tools[:3]):
            mid = f"via_{tool}"[:80]
            markers.append(
                SolutionMarker(
                    mid,
                    f"Evidence via {tool}",
                    0.20,
                    stage=idx + 1,
                    tools=(tool,),
                    requires_markers=(prev_id,),
                )
            )
            prev_id = mid
        markers.append(
            SolutionMarker(
                "closed",
                "Task completed",
                0.20,
                stage=len(markers),
                requires_complete=True,
                requires_markers=(prev_id,),
            )
        )
        total = sum(m.weight for m in markers) or 1.0
        common_title = title_samples[key].most_common(1)[0][0] if title_samples[key] else key
        ladder = SolutionLadder(
            family_key=key,
            intent=f"Resolve recurring work like: {common_title}"[:240],
            solution="Task complete with the evidence pattern seen in successful history.",
            markers=tuple(
                SolutionMarker(
                    marker_id=m.marker_id,
                    label=m.label,
                    weight=m.weight / total,
                    stage=m.stage,
                    tools=m.tools,
                    title_keywords=m.title_keywords,
                    result_keywords=m.result_keywords,
                    requires_complete=m.requires_complete,
                    any_evidence=m.any_evidence,
                    min_evidence=m.min_evidence,
                    requires_markers=m.requires_markers,
                    verify_tools=m.verify_tools,
                )
                for m in markers
            ),
            source="learned",
        )
        learned[key] = ladder

    out_path = None
    if persist and learned:
        out_path = str(
            save_learned_ladders(
                learned,
                meta={
                    "min_samples": min_samples,
                    "limit_tasks": limit_tasks,
                    "family_count": len(learned),
                },
            )
        )

    return {
        "ok": True,
        "family_count": len(learned),
        "families": {
            key: {
                "family_key": ladder.family_key,
                "intent": ladder.intent,
                "solution": ladder.solution,
                "source": ladder.source,
                "sample_sequences": len(by_family.get(key) or []),
                "markers": [m.label for m in ladder.markers],
            }
            for key, ladder in learned.items()
        },
        "path": out_path,
        "seeded_count": len(_SEEDED),
    }


def learn_tool_patterns_from_history(
    *,
    work_class: str = "",
    source_type: str = "",
    limit: int = 200,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Mine one family for common tools (debug / operator report)."""
    path = Path(db_path) if db_path is not None else work_tree_db_path()
    if not path.is_file():
        return {"ok": False, "error": "work_tree_db_missing", "tools": []}
    key = family_key(work_class=work_class, source_type=source_type)
    tool_counts: Counter[str] = Counter()
    sequences: Counter[tuple[str, ...]] = Counter()
    sample = 0
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        tasks = conn.execute(
            """
            SELECT t.task_id, b.work_class, b.source_type
            FROM work_tree_tasks t
            JOIN work_tree_branches b ON b.branch_id = t.branch_id
            WHERE t.status = 'complete'
            ORDER BY t.updated_at DESC
            LIMIT ?
            """,
            (max(20, int(limit)),),
        ).fetchall()
        for task in tasks:
            if family_key(work_class=str(task["work_class"] or ""), source_type=str(task["source_type"] or "")) != key:
                if work_class or source_type:
                    # filter only when caller specified family pieces
                    if _norm(work_class) and _norm(task["work_class"]) != _norm(work_class):
                        continue
                    if _norm(source_type) and _norm(task["source_type"]) != _norm(source_type):
                        continue
            sample += 1
            tools = [
                str(r["tool_name"] or "").strip()
                for r in conn.execute(
                    "SELECT tool_name FROM work_tree_evidence WHERE task_id=? ORDER BY created_at ASC",
                    (task["task_id"],),
                )
                if str(r["tool_name"] or "").strip()
            ]
            for tool in tools:
                tool_counts[tool] += 1
            if tools:
                sequences[tuple(tools[:6])] += 1
        conn.close()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tools": []}
    return {
        "ok": True,
        "family_key": key,
        "sample_tasks": sample,
        "tools": [{"tool": t, "count": n} for t, n in tool_counts.most_common(12)],
        "common_sequences": [{"tools": list(seq), "count": n} for seq, n in sequences.most_common(8)],
    }


def list_seeded_families() -> list[dict[str, Any]]:
    return [
        {
            "family_key": ladder.family_key,
            "intent": ladder.intent,
            "solution": ladder.solution,
            "marker_count": len(ladder.markers),
            "source": ladder.source,
        }
        for ladder in _SEEDED.values()
    ]
