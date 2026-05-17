from __future__ import annotations

from pathlib import Path
from typing import Any


def _issue_codes(memory_health: dict[str, Any]) -> list[str]:
    issues = memory_health.get("issues") if isinstance(memory_health.get("issues"), list) else []
    codes: list[str] = []
    for item in issues:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if code and code not in codes:
            codes.append(code)
    return codes


def _evidence_tools(evidence_rows: list[dict[str, Any]]) -> list[str]:
    tools: list[str] = []
    for row in evidence_rows:
        tool_name = str(row.get("tool_name") or "").strip()
        args = row.get("tool_args") if isinstance(row.get("tool_args"), list) else []
        label = tool_name
        if args:
            label = f"{tool_name}({', '.join(str(item) for item in args[:3])})"
        if label and label not in tools:
            tools.append(label)
    return tools


def build_memory_bootstrap_judgment(
    *,
    memory_enabled: bool,
    memory_health: dict[str, Any],
    identity_file: Path,
    learned_facts_file: Path,
    memory_events_log: Path,
    branch_payload: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    bootstrap = memory_health.get("bootstrap") if isinstance(memory_health.get("bootstrap"), dict) else {}
    bootstrap_origin = memory_health.get("bootstrap_origin") if isinstance(memory_health.get("bootstrap_origin"), dict) else {}
    origin_status = str(bootstrap_origin.get("status") or bootstrap.get("origin_status") or "").strip().lower()
    origin_authority = str(bootstrap_origin.get("authority") or bootstrap.get("origin_authority") or "").strip().lower()
    origin_pending_slots = [
        str(item or "").strip()
        for item in list(bootstrap_origin.get("pending_slots") or bootstrap.get("origin_pending_slots") or [])
        if str(item or "").strip()
    ]
    missing_bootstrap = [
        str(item or "").strip()
        for item in list(bootstrap.get("missing") or [])
        if str(item or "").strip()
    ]
    if not identity_file.exists() and "identity" not in missing_bootstrap:
        missing_bootstrap.append("identity")
    if not learned_facts_file.exists() and "learned_facts" not in missing_bootstrap:
        missing_bootstrap.append("learned_facts")

    issue_codes = _issue_codes(memory_health)
    if not memory_events_log.exists() and "memory_events_log_missing" not in issue_codes:
        issue_codes.append("memory_events_log_missing")

    if not memory_enabled:
        classification = "policy_closed"
        verdict = "blocked"
        root_cause = "Memory policy is disabled, so persistence cannot be judged as ready."
    elif missing_bootstrap and origin_status == "missing":
        classification = "bootstrap_origin_missing"
        verdict = "incomplete"
        root_cause = "Memory is enabled, but durable identity files are missing and no bootstrap origin contract exists."
    elif missing_bootstrap and origin_status == "pending_operator_confirmation":
        classification = "bootstrap_origin_pending"
        verdict = "blocked"
        root_cause = "Memory is enabled and the origin contract exists, but identity slots still require operator confirmation."
    elif missing_bootstrap:
        classification = "bootstrap_contract_missing"
        verdict = "incomplete"
        root_cause = "Memory is enabled, but durable identity and learned-facts bootstrap files are missing."
    elif "memory_events_log_missing" in issue_codes:
        classification = "event_trace_missing"
        verdict = "incomplete"
        root_cause = "Memory files exist, but the event ledger has not produced durable operation evidence."
    else:
        classification = "ready"
        verdict = "ready"
        root_cause = "Memory policy, bootstrap files, and event trace are present."

    if classification == "ready":
        next_work = ["No memory bootstrap action is open; keep monitoring memory health and event evidence."]
    else:
        next_work = [
            "Confirm the bootstrap origin slots before writing identity facts.",
            "Define learned-facts bootstrap as an output of the memory learning path, not a hand-written guess.",
            "Make the memory event ledger create durable evidence for the first valid memory operation.",
        ]

    return {
        "verdict": verdict,
        "classification": classification,
        "root_cause": root_cause,
        "memory_enabled": bool(memory_enabled),
        "health_status": str(memory_health.get("status") or branch_payload.get("memory_health_status") or "unknown"),
        "issue_codes": issue_codes,
        "missing_bootstrap": missing_bootstrap,
        "files": {
            "identity": {"path": str(identity_file), "exists": identity_file.exists()},
            "learned_facts": {"path": str(learned_facts_file), "exists": learned_facts_file.exists()},
            "memory_events_log": {"path": str(memory_events_log), "exists": memory_events_log.exists()},
        },
        "bootstrap_origin": {
            "path": str(bootstrap_origin.get("path") or bootstrap.get("origin_contract_path") or ""),
            "exists": bool(bootstrap_origin.get("exists", False)),
            "valid": bool(bootstrap_origin.get("valid", False)),
            "status": origin_status or "unknown",
            "authority": origin_authority or "none",
            "pending_slots": origin_pending_slots,
            "may_seed_identity_facts": bool(bootstrap_origin.get("may_seed_identity_facts", False)),
        },
        "evidence": {
            "row_count": len(evidence_rows),
            "tools": _evidence_tools(evidence_rows),
        },
        "blocked_shortcuts": [
            "do_not_flip_memory_enabled_as_a_fix",
            "do_not_seed_identity_from_code_defaults_or_guesses",
            "do_not_mark_memory_ready_without_event_evidence",
        ],
        "next_work": next_work,
    }


def render_memory_bootstrap_judgment(judgment: dict[str, Any]) -> str:
    files = judgment.get("files") if isinstance(judgment.get("files"), dict) else {}
    origin = judgment.get("bootstrap_origin") if isinstance(judgment.get("bootstrap_origin"), dict) else {}
    evidence = judgment.get("evidence") if isinstance(judgment.get("evidence"), dict) else {}
    lines = [
        "Memory Bootstrap Judgment",
        f"- verdict: {judgment.get('verdict')}",
        f"- classification: {judgment.get('classification')}",
        f"- root cause: {judgment.get('root_cause')}",
        f"- memory enabled: {bool(judgment.get('memory_enabled'))}",
        f"- health status: {judgment.get('health_status')}",
        f"- issue codes: {', '.join(judgment.get('issue_codes') or []) or 'none'}",
        f"- missing bootstrap: {', '.join(judgment.get('missing_bootstrap') or []) or 'none'}",
        f"- evidence rows: {int(evidence.get('row_count', 0) or 0)}",
        f"- evidence tools: {', '.join(evidence.get('tools') or []) or 'none'}",
    ]
    for name in ("identity", "learned_facts", "memory_events_log"):
        row = files.get(name) if isinstance(files.get(name), dict) else {}
        lines.append(f"- {name}: {'present' if row.get('exists') else 'missing'} ({row.get('path')})")
    lines.append(
        "- bootstrap_origin: "
        f"{origin.get('status') or 'unknown'}; "
        f"authority={origin.get('authority') or 'none'}; "
        f"pending_slots={', '.join(origin.get('pending_slots') or []) or 'none'} "
        f"({origin.get('path') or ''})"
    )
    lines.append("Blocked shortcuts:")
    lines.extend(f"- {item}" for item in list(judgment.get("blocked_shortcuts") or []))
    lines.append("Next work:")
    lines.extend(f"- {item}" for item in list(judgment.get("next_work") or []))
    return "\n".join(lines)
