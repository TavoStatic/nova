from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from services.nova_runtime_context import OPERATOR_OUTBOX_FILE
from services.operator_outbox import OPERATOR_OUTBOX_SERVICE


SPECIALIZED_JUDGMENT_TOOLS = {
    "installer_validation_run",
    "memory_bootstrap_judgment",
    "release_promotion_judgment",
    "subconscious_review_judgment",
}


def _safe_text(value: Any, limit: int = 600) -> str:
    return str(value or "").strip()[: max(1, int(limit or 1))]


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _compact(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return _safe_text(value, 200)
    if isinstance(value, dict):
        return {str(key): _compact(item, depth=depth + 1) for key, item in list(value.items())[:40]}
    if isinstance(value, list):
        return [_compact(item, depth=depth + 1) for item in value[:40]]
    if isinstance(value, tuple):
        return [_compact(item, depth=depth + 1) for item in list(value)[:40]]
    if isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 4)
    if value is None:
        return None
    return _safe_text(value, 500)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(_compact(value), ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _task_status(task: Any) -> str:
    return _safe_text(getattr(getattr(task, "status", ""), "value", getattr(task, "status", "")), 80).lower()


def _branch_status(branch: Any) -> str:
    return _safe_text(getattr(getattr(branch, "status", ""), "value", getattr(branch, "status", "")), 80).lower()


def _evidence_tools(evidence_rows: list[dict[str, Any]]) -> list[str]:
    tools: list[str] = []
    for row in evidence_rows:
        tool = _safe_text(row.get("tool_name"), 120)
        if tool and tool not in tools:
            tools.append(tool)
    return tools


def _looks_like_failed_evidence(row: dict[str, Any]) -> bool:
    text = _safe_text(row.get("result_text"), 4000).lower()
    if not text:
        return True
    return (
        text.startswith("[fail]")
        or '"ok": false' in text
        or "'ok': false" in text
        or "tool error:" in text
        or "unknown planned tool" in text
    )


def _has_specialized_judgment(evidence_rows: list[dict[str, Any]]) -> bool:
    return bool(set(_evidence_tools(evidence_rows)) & SPECIALIZED_JUDGMENT_TOOLS)


def build_source_root_judgment(
    branch_id: str,
    *,
    work_tree_module: Any = None,
) -> dict[str, Any]:
    branch_key = _safe_text(branch_id, 160)
    if not branch_key:
        return {
            "ok": False,
            "verdict": "invalid_request",
            "reason": "branch_id_required",
            "operator_outbox": False,
        }

    if work_tree_module is None:
        import work_tree as work_tree_module  # local import keeps service load independent

    reload_fn = getattr(work_tree_module, "reload_persisted_state", None)
    if callable(reload_fn):
        reload_fn()

    branch = work_tree_module.get_branch(branch_key)
    if branch is None:
        return {
            "ok": False,
            "verdict": "invalid_request",
            "reason": "branch_not_found",
            "branch_id": branch_key,
            "operator_outbox": False,
        }

    tasks = list(work_tree_module.list_branch_tasks(branch_key))
    evidence_rows = list(work_tree_module.list_branch_evidence(branch_key, limit=80))
    open_tasks = [task for task in tasks if _task_status(task) not in {"complete", "dropped"}]
    blocked_tasks = [task for task in open_tasks if _task_status(task) == "blocked"]
    evidence_tools = _evidence_tools(evidence_rows)
    failed_evidence = [row for row in evidence_rows if _looks_like_failed_evidence(row)]
    source_payload = _safe_dict(getattr(branch, "source_payload", {}))
    source_type = _safe_text(getattr(branch, "source_type", ""), 120)
    work_class = _safe_text(getattr(branch, "work_class", ""), 120)
    actionability = _safe_text(getattr(branch, "actionability", ""), 80)
    branch_status = _branch_status(branch)
    preferred_tool = _safe_text(getattr(branch, "preferred_tool", ""), 120)
    allowed_tools = [_safe_text(tool, 120) for tool in _safe_list(getattr(branch, "allowed_tools", [])) if _safe_text(tool, 120)]

    operator_reason = ""
    verdict = "continue_with_evidence"
    ok = True
    next_work: list[str] = []

    if blocked_tasks or branch_status == "blocked" or actionability == "blocked":
        verdict = "operator_or_authority_needed"
        operator_reason = "branch_blocked"
        ok = False
        next_work.append("Ask the operator for the missing authority or information needed to continue.")
    elif not evidence_rows:
        verdict = "needs_evidence"
        ok = False
        next_work.append("Run the branch evidence tasks before judging closure.")
    elif failed_evidence:
        verdict = "evidence_failed"
        operator_reason = "failed_evidence"
        ok = False
        next_work.append("Inspect failed tool evidence and repair the execution path before closure.")
    elif _has_specialized_judgment(evidence_rows):
        verdict = "specialized_judgment_recorded"
        next_work.append("Let the specialized judgment own closure for this root.")
    elif preferred_tool and preferred_tool in {"read", "find", "pulse", "queue_status", "system_check"}:
        verdict = "evidence_review_needed"
        next_work.append("Evidence has been gathered; synthesize a repair decision before claiming closure.")
    else:
        verdict = "root_has_executable_path"
        next_work.append("Continue through the root-specific executable tool and verify the next status snapshot.")

    if not allowed_tools and preferred_tool:
        allowed_tools = [preferred_tool]

    judgment = {
        "ok": ok,
        "schema": "nova.source_root_judgment.v1",
        "verdict": verdict,
        "reason": operator_reason or verdict,
        "branch_id": branch_key,
        "branch_title": _safe_text(getattr(branch, "title", ""), 260),
        "source_type": source_type,
        "work_class": work_class,
        "branch_status": branch_status,
        "actionability": actionability,
        "preferred_tool": preferred_tool,
        "allowed_tools": allowed_tools,
        "evidence_count": len(evidence_rows),
        "evidence_tools": evidence_tools,
        "failed_evidence_count": len(failed_evidence),
        "open_task_count": len(open_tasks),
        "blocked_task_count": len(blocked_tasks),
        "open_tasks": [
            {
                "task_id": _safe_text(getattr(task, "task_id", ""), 160),
                "title": _safe_text(getattr(task, "title", ""), 260),
                "status": _task_status(task),
                "meta": _compact(getattr(task, "meta", {})),
            }
            for task in open_tasks[:8]
        ],
        "source_payload_keys": sorted(str(key) for key in source_payload.keys())[:40],
        "source_payload": _compact(source_payload),
        "next_work": next_work,
        "operator_outbox": bool(operator_reason),
        "operator_reason": operator_reason,
    }
    return judgment


def build_source_root_operator_notice(judgment: dict[str, Any]) -> dict[str, Any]:
    data = _safe_dict(judgment)
    if not bool(data.get("operator_outbox")):
        return {}

    source_type = _safe_text(data.get("source_type"), 120) or "source_root"
    branch_title = _safe_text(data.get("branch_title"), 220)
    reason = _safe_text(data.get("operator_reason") or data.get("reason"), 160)
    title = f"Source root needs operator judgment: {source_type}"
    message = (
        f"I have evidence for {source_type}, but the branch cannot close itself yet."
        f" Reason: {reason or 'operator_authority_required'}."
    )
    if branch_title:
        message = f"{message} Branch: {branch_title}."

    payload = {
        "request_kind": "source_root_judgment",
        "blocked_reason": reason or "operator_authority_required",
        "tree": {
            "branch_id": _safe_text(data.get("branch_id"), 160),
            "branch_title": branch_title,
            "task_id": _safe_text((_safe_list(data.get("open_tasks"))[0] if _safe_list(data.get("open_tasks")) else {}).get("task_id"), 160)
            if _safe_list(data.get("open_tasks"))
            else "",
            "task_title": _safe_text((_safe_list(data.get("open_tasks"))[0] if _safe_list(data.get("open_tasks")) else {}).get("title"), 260)
            if _safe_list(data.get("open_tasks"))
            else "",
        },
        "judgment": _compact(data),
    }
    return {
        "source": "source_root_judgment",
        "severity": "attention",
        "title": title,
        "message": message,
        "dedupe_key": f"source_root_judgment|{source_type}|{reason}|{_stable_hash(payload)}",
        "payload": payload,
    }


def publish_source_root_operator_notice(
    judgment: dict[str, Any],
    *,
    outbox_path: Path | None = None,
    operator_outbox_service: Any = None,
    now_fn: Any = None,
    uuid_fn: Any = None,
) -> dict[str, Any]:
    notice = build_source_root_operator_notice(judgment)
    if not notice:
        return {"ok": True, "published": False, "reason": "not_operator_outbox"}

    service = operator_outbox_service or OPERATOR_OUTBOX_SERVICE
    appended = service.append_notice(
        Path(outbox_path or OPERATOR_OUTBOX_FILE),
        source=str(notice["source"]),
        severity=str(notice["severity"]),
        title=str(notice["title"]),
        message=str(notice["message"]),
        dedupe_key=str(notice["dedupe_key"]),
        payload=_safe_dict(notice.get("payload")),
        now_fn=now_fn,
        uuid_fn=uuid_fn,
    )
    return {
        "ok": bool(appended.get("ok")),
        "published": bool(appended.get("ok")),
        "deduped": bool(appended.get("deduped")),
        "event": appended.get("event") or {},
        "notice": notice,
        "reason": _safe_text(appended.get("reason"), 120),
    }


def render_source_root_judgment(judgment: dict[str, Any]) -> str:
    data = _safe_dict(judgment)
    lines = [
        "Source Root Judgment",
        f"- verdict: {_safe_text(data.get('verdict'), 120)}",
        f"- ok: {bool(data.get('ok'))}",
        f"- source: {_safe_text(data.get('source_type'), 120)}",
        f"- branch: {_safe_text(data.get('branch_id'), 160)}",
        f"- evidence_count: {int(data.get('evidence_count', 0) or 0)}",
        f"- evidence_tools: {', '.join(_safe_text(tool, 80) for tool in _safe_list(data.get('evidence_tools'))) or 'none'}",
        f"- open_task_count: {int(data.get('open_task_count', 0) or 0)}",
        f"- blocked_task_count: {int(data.get('blocked_task_count', 0) or 0)}",
    ]
    next_work = [_safe_text(item, 240) for item in _safe_list(data.get("next_work")) if _safe_text(item, 240)]
    if next_work:
        lines.append("- next_work:")
        lines.extend(f"  - {item}" for item in next_work)
    if bool(data.get("operator_outbox")):
        lines.append(f"- operator_outbox: needed ({_safe_text(data.get('operator_reason'), 120)})")
    return "\n".join(lines)
