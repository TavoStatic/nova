from __future__ import annotations

import json
from typing import Any

from services.subconscious_review_authority import SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE


_INVALID_RESULT_PREFIXES = (
    "no matches found.",
    "not a file:",
    "not a folder:",
    "file not found:",
    "not found:",
    "error:",
)

_NO_OWNER_ROOT_REPAIR_CLASSIFICATIONS = {
    "authority_rejected",
}


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _lower_text(value: object) -> str:
    return _clean_text(value).lower()


def _is_invalid_evidence(row: dict[str, Any]) -> bool:
    result = _lower_text(row.get("result_text"))
    if not result:
        return True
    return any(result.startswith(prefix) for prefix in _INVALID_RESULT_PREFIXES)


def _latest_subconscious_branch(work_tree_module: Any) -> object | None:
    newest = None
    for tree in work_tree_module.list_trees():
        for branch in work_tree_module.list_tree_branches(tree.tree_id):
            if _clean_text(getattr(branch, "source_type", "")) != "subconscious":
                continue
            if newest is None or getattr(branch, "updated_at", None) > getattr(newest, "updated_at", None):
                newest = branch
    return newest


def _branch_by_id(work_tree_module: Any, branch_id: str) -> object | None:
    clean_id = _clean_text(branch_id)
    if not clean_id:
        return _latest_subconscious_branch(work_tree_module)
    try:
        return work_tree_module.get_branch(clean_id)
    except Exception:
        return None


def _evidence_task_titles(work_tree_module: Any, branch_id: str) -> dict[str, str]:
    titles: dict[str, str] = {}
    try:
        tasks = work_tree_module.list_branch_tasks(branch_id)
    except Exception:
        return titles
    for task in tasks:
        task_id = _clean_text(getattr(task, "task_id", ""))
        if task_id:
            titles[task_id] = _clean_text(getattr(task, "title", ""))
    return titles


def _evidence_label(row: dict[str, Any], task_titles: dict[str, str]) -> str:
    args = row.get("tool_args") if isinstance(row.get("tool_args"), list) else []
    parts = [
        _clean_text(row.get("tool_name")),
        " ".join(_clean_text(item) for item in args),
        task_titles.get(_clean_text(row.get("task_id")), ""),
        _clean_text(row.get("result_text"))[:1000],
    ]
    return " ".join(part for part in parts if part).lower()


def _evidence_summary(
    *,
    evidence_rows: list[dict[str, Any]],
    task_titles: dict[str, str],
    target_seam: str,
    signal_name: str,
) -> dict[str, Any]:
    valid_rows = [row for row in evidence_rows if not _is_invalid_evidence(row)]
    invalid_rows = [row for row in evidence_rows if _is_invalid_evidence(row)]
    labels = [_evidence_label(row, task_titles) for row in valid_rows]
    seam = _lower_text(target_seam)
    signal = _lower_text(signal_name)

    route_evidence = any(
        seam and seam in label and "subconscious_live_simulator.py" in label and "find" in label
        for label in labels
    )
    pressure_evidence = any(
        signal and signal in label and "find" in label and not label.startswith("queue_status")
        for label in labels
    )
    latest_report = any("runtime/subconscious_runs/latest.json" in label and "read" in label for label in labels)
    queue_status = any(_lower_text(row.get("tool_name")) == "queue_status" for row in valid_rows)

    required = {
        "route_evidence": route_evidence,
        "pressure_evidence": pressure_evidence,
        "latest_report": latest_report,
        "queue_status": queue_status,
    }
    return {
        "row_count": len(evidence_rows),
        "valid_count": len(valid_rows),
        "invalid_count": len(invalid_rows),
        "tools": _evidence_tools(valid_rows),
        "required": required,
        "complete": all(required.values()),
        "missing": [name for name, present in required.items() if not present],
    }


def _evidence_tools(evidence_rows: list[dict[str, Any]]) -> list[str]:
    tools: list[str] = []
    for row in evidence_rows:
        tool_name = _clean_text(row.get("tool_name"))
        args = row.get("tool_args") if isinstance(row.get("tool_args"), list) else []
        label = tool_name
        if args:
            label = f"{tool_name}({', '.join(_clean_text(item) for item in args[:3])})"
        if label and label not in tools:
            tools.append(label)
    return tools


def _gate_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    gate = payload.get("review_gate") if isinstance(payload.get("review_gate"), dict) else {}
    if gate:
        return dict(gate)
    return {
        "approved": False,
        "status": "missing_review_gate",
        "reason": "branch payload does not carry the approved subconscious triage gate",
        "preferred_owner": _clean_text(payload.get("preferred_owner")),
        "route_hint": _clean_text(payload.get("route_hint")),
        "review_contract": _clean_text(payload.get("review_contract")),
    }


def _classification(
    *,
    gate: dict[str, Any],
    evidence: dict[str, Any],
    authority: dict[str, Any],
) -> tuple[str, str, str]:
    authority_status = _lower_text(authority.get("authority_status"))
    if not bool(gate.get("approved")):
        return (
            "blocked",
            "review_not_authorized",
            "Subconscious pressure has not cleared its triage gate, so owner-root repair cannot be authorized.",
        )
    if not bool(evidence.get("complete")):
        missing = ", ".join(evidence.get("missing") or []) or "required evidence"
        return (
            "blocked",
            "evidence_incomplete",
            f"Branch has not gathered all required route evidence yet: {missing}.",
        )
    if authority_status == "already_staged":
        return (
            "blocked",
            "owner_root_repair_already_staged",
            _clean_text(authority.get("authority_reason")) or "Authority says this repair is already staged.",
        )
    if bool(authority.get("approved")):
        return (
            "owner_root_repair_required",
            "authority_confirmed_owner_root",
            _clean_text(authority.get("authority_reason")) or "Authority confirmed the owner lane for repair.",
        )
    classification = f"authority_{authority_status or 'rejected'}"
    verdict = "no_owner_root_repair" if classification in _NO_OWNER_ROOT_REPAIR_CLASSIFICATIONS else "blocked"
    return (
        verdict,
        classification,
        _clean_text(authority.get("authority_reason")) or "Authority did not confirm an owner-root repair lane.",
    )


def _next_work(
    *,
    verdict: str,
    classification: str,
    target_seam: str,
    signal_name: str,
    preferred_owner: str,
    evidence: dict[str, Any],
) -> list[str]:
    if classification == "review_not_authorized":
        return ["Route the candidate back through the subconscious triage gate before treating it as repair work."]
    if classification == "evidence_incomplete":
        return [f"Gather missing evidence: {', '.join(evidence.get('missing') or [])}."]
    if verdict == "owner_root_repair_required":
        owner = preferred_owner or "the confirmed owner"
        return [
            f"Open or advance the owner-root repair lane in {owner} for {target_seam} / {signal_name}.",
            "Change the route or ownership path that produces the pressure; do not run generated tests as the repair.",
            "After repair, let subconscious pressure re-observe the behavior instead of manually clearing the branch.",
        ]
    if verdict == "no_owner_root_repair":
        return [
            f"Retire this candidate as observed pressure without an owner-root repair for {target_seam} / {signal_name}.",
            "Let a fresh subconscious report reopen work only when it points to a concrete viable owner route.",
        ]
    return ["Keep the branch blocked until authority and evidence point to a concrete owner-root repair lane."]


def is_no_owner_root_repair_judgment(judgment: dict[str, Any]) -> bool:
    classification = _clean_text((judgment or {}).get("classification"))
    verdict = _clean_text((judgment or {}).get("verdict"))
    return verdict == "no_owner_root_repair" or classification in _NO_OWNER_ROOT_REPAIR_CLASSIFICATIONS


def _parse_rendered_judgment(result_text: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for raw_line in str(result_text or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        body = line[2:].strip()
        if ":" not in body:
            continue
        key, value = body.split(":", 1)
        normalized_key = key.strip().lower().replace(" ", "_")
        parsed[normalized_key] = value.strip()
    if parsed:
        parsed["ok"] = True
    return parsed


def parse_subconscious_review_judgment_result(result: object) -> dict[str, Any]:
    if isinstance(result, dict):
        if isinstance(result.get("judgment"), dict):
            return dict(result.get("judgment") or {})
        return dict(result)
    text = _clean_text(result)
    if not text:
        return {}
    try:
        loaded = json.loads(text)
    except Exception:
        loaded = None
    if isinstance(loaded, dict):
        if isinstance(loaded.get("judgment"), dict):
            return dict(loaded.get("judgment") or {})
        return dict(loaded)
    return _parse_rendered_judgment(text)


def latest_subconscious_review_judgment_for_branch(work_tree_module: Any, branch_id: str) -> dict[str, Any]:
    clean_branch_id = _clean_text(branch_id)
    if not clean_branch_id:
        return {}
    try:
        evidence_rows = work_tree_module.list_branch_evidence(clean_branch_id, limit=200)
    except Exception:
        return {}
    latest: dict[str, Any] = {}
    for row in [dict(item) for item in list(evidence_rows or []) if isinstance(item, dict)]:
        if _clean_text(row.get("tool_name")) != "subconscious_review_judgment":
            continue
        parsed = parse_subconscious_review_judgment_result(row.get("result_text"))
        if parsed:
            latest = parsed
    return latest


def build_subconscious_review_judgment(
    *,
    branch_id: str = "",
    work_tree_module: Any,
    review_authority_service: Any = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE,
    probe_turn_routes_fn: Any = None,
    session_factory: Any = None,
    evaluate_supervisor_rules_fn: Any = None,
    supervisor_has_route_fn: Any = None,
    fulfillment_viability_fn: Any = None,
    supervisor_process_turn_fn: Any = None,
) -> dict[str, Any]:
    branch = _branch_by_id(work_tree_module, branch_id)
    if branch is None:
        return {
            "ok": False,
            "verdict": "blocked",
            "classification": "branch_missing",
            "root_cause": f"Work Tree branch not found: {_clean_text(branch_id) or 'latest subconscious branch'}",
            "branch_id": _clean_text(branch_id),
            "blocked_shortcuts": ["do_not_guess_subconscious_branch_identity"],
            "next_work": ["Pass the exact Work Tree branch id into subconscious_review_judgment."],
        }

    actual_branch_id = _clean_text(getattr(branch, "branch_id", ""))
    source_type = _clean_text(getattr(branch, "source_type", ""))
    payload = dict(getattr(branch, "source_payload", {}) or {})
    target_seam = _clean_text(payload.get("target_seam"))
    signal_name = _clean_text(payload.get("signal"))
    preferred_owner = _clean_text(payload.get("preferred_owner"))
    route_hint = _clean_text(payload.get("route_hint"))
    review_contract = _clean_text(payload.get("review_contract"))
    if source_type != "subconscious":
        return {
            "ok": False,
            "verdict": "blocked",
            "classification": "wrong_branch_source",
            "root_cause": f"Branch {actual_branch_id} is source_type={source_type or 'unknown'}, not subconscious.",
            "branch_id": actual_branch_id,
            "branch_title": _clean_text(getattr(branch, "title", "")),
            "blocked_shortcuts": ["do_not_apply_subconscious_authority_to_non_subconscious_branch"],
            "next_work": ["Use this judgment only on Work Tree branches sourced from subconscious pressure."],
        }

    try:
        evidence_rows = work_tree_module.list_branch_evidence(actual_branch_id, limit=100)
    except Exception:
        evidence_rows = []
    task_titles = _evidence_task_titles(work_tree_module, actual_branch_id)
    evidence = _evidence_summary(
        evidence_rows=[dict(row) for row in evidence_rows if isinstance(row, dict)],
        task_titles=task_titles,
        target_seam=target_seam,
        signal_name=signal_name,
    )

    gate = _gate_from_payload(payload)
    signal = {
        "source": "subconscious",
        "signal_class": "subconscious_candidate",
        "title": _clean_text(getattr(branch, "title", "")),
        "payload": payload,
    }
    authority = review_authority_service.review_candidate(
        signal,
        gate,
        probe_turn_routes_fn=probe_turn_routes_fn,
        session_factory=session_factory,
        evaluate_supervisor_rules_fn=evaluate_supervisor_rules_fn,
        supervisor_has_route_fn=supervisor_has_route_fn,
        fulfillment_viability_fn=fulfillment_viability_fn,
        supervisor_process_turn_fn=supervisor_process_turn_fn,
    )
    authority = dict(authority) if isinstance(authority, dict) else {
        "approved": False,
        "authority_owner": preferred_owner,
        "authority_status": "invalid_authority_result",
        "authority_reason": "review authority returned a non-dict result",
    }
    verdict, classification, root_cause = _classification(
        gate=gate,
        evidence=evidence,
        authority=authority,
    )
    return {
        "ok": True,
        "verdict": verdict,
        "classification": classification,
        "root_cause": root_cause,
        "branch_id": actual_branch_id,
        "branch_title": _clean_text(getattr(branch, "title", "")),
        "target_seam": target_seam,
        "signal": signal_name,
        "review_contract": review_contract,
        "preferred_owner": preferred_owner,
        "route_hint": route_hint,
        "review_gate": gate,
        "authority": authority,
        "evidence": evidence,
        "blocked_shortcuts": [
            "do_not_run_generated_tests_as_progress",
            "do_not_patch_by_keyword_or_fallback_count",
            "do_not_mark_pressure_resolved_because_queue_is_clear",
        ],
        "next_work": _next_work(
            verdict=verdict,
            classification=classification,
            target_seam=target_seam,
            signal_name=signal_name,
            preferred_owner=preferred_owner,
            evidence=evidence,
        ),
    }


def render_subconscious_review_judgment(judgment: dict[str, Any]) -> str:
    evidence = judgment.get("evidence") if isinstance(judgment.get("evidence"), dict) else {}
    required = evidence.get("required") if isinstance(evidence.get("required"), dict) else {}
    gate = judgment.get("review_gate") if isinstance(judgment.get("review_gate"), dict) else {}
    authority = judgment.get("authority") if isinstance(judgment.get("authority"), dict) else {}
    lines = [
        "Subconscious Review Judgment",
        f"- verdict: {judgment.get('verdict')}",
        f"- classification: {judgment.get('classification')}",
        f"- root cause: {judgment.get('root_cause')}",
        f"- branch: {judgment.get('branch_id')} ({judgment.get('branch_title') or ''})",
        f"- seam/signal: {judgment.get('target_seam') or 'unknown'} / {judgment.get('signal') or 'unknown'}",
        f"- owner route: {judgment.get('preferred_owner') or 'unknown'}; hint={judgment.get('route_hint') or 'unknown'}; contract={judgment.get('review_contract') or 'unknown'}",
        f"- review gate: {gate.get('status') or 'unknown'}; approved={bool(gate.get('approved'))}; reason={gate.get('reason') or ''}",
        f"- authority: {authority.get('authority_status') or 'unknown'}; approved={bool(authority.get('approved'))}; owner={authority.get('authority_owner') or 'unknown'}",
        f"- authority reason: {authority.get('authority_reason') or ''}",
        f"- evidence rows: {int(evidence.get('row_count', 0) or 0)} valid={int(evidence.get('valid_count', 0) or 0)} invalid={int(evidence.get('invalid_count', 0) or 0)}",
        f"- required evidence: route={bool(required.get('route_evidence'))}; pressure={bool(required.get('pressure_evidence'))}; latest_report={bool(required.get('latest_report'))}; queue={bool(required.get('queue_status'))}",
        f"- evidence tools: {', '.join(evidence.get('tools') or []) or 'none'}",
    ]
    lines.append("Blocked shortcuts:")
    lines.extend(f"- {item}" for item in list(judgment.get("blocked_shortcuts") or []))
    lines.append("Next work:")
    lines.extend(f"- {item}" for item in list(judgment.get("next_work") or []))
    return "\n".join(lines)
