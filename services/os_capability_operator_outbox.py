from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from services.nova_runtime_context import OPERATOR_OUTBOX_FILE
from services.operator_outbox import OPERATOR_OUTBOX_SERVICE


def _safe_text(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[: max(1, int(limit or 1))]


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _compact(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return _safe_text(value, 220)
    if isinstance(value, dict):
        return {str(key): _compact(item, depth=depth + 1) for key, item in list(value.items())[:50]}
    if isinstance(value, list):
        return [_compact(item, depth=depth + 1) for item in value[:50]]
    if isinstance(value, tuple):
        return [_compact(item, depth=depth + 1) for item in list(value)[:50]]
    if isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 4)
    if value is None:
        return None
    return _safe_text(value, 800)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(_compact(value), ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _detail_from_row(row: dict[str, Any]) -> str:
    detail = _safe_text(row.get("detail"), 600)
    if detail:
        return detail
    errors = _safe_list(row.get("errors"))
    if not errors:
        errors = _safe_list(_safe_dict(row.get("prepare")).get("errors"))
    if errors:
        return "; ".join(_safe_text(item, 160) for item in errors[:5] if _safe_text(item, 160))
    prepare_reason = _safe_text(_safe_dict(row.get("prepare")).get("reason"), 160)
    return prepare_reason


def _message_for(reason: str, capability: str, detail: str) -> tuple[str, str]:
    label = capability or "unknown"
    if reason == "missing_capability":
        title = f"OS capability missing: {label}"
        message = f"I know an OS capability is needed, but {label} is not registered in the verified capability registry."
    elif reason == "contract_stale":
        title = f"OS capability contract stale: {label}"
        message = f"I need OS capability {label}, but its script contract cannot be verified."
    elif reason == "invalid_args":
        title = f"OS capability request invalid: {label}"
        message = f"I need OS capability {label}, but the request arguments do not match the registered contract."
    elif reason == "authority_blocked":
        title = f"OS capability authority blocked: {label}"
        message = f"I need OS capability {label}, but the current authority context does not satisfy the contract."
    else:
        title = f"OS capability blocked: {label}"
        message = f"I need OS capability {label}, but execution is blocked by the capability contract."
    if detail:
        message = f"{message} {detail}"
    return title, message


def build_os_capability_notice(
    result: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = _safe_dict(result)
    if not bool(data.get("operator_outbox")):
        return {}

    row = _safe_dict(data.get("row"))
    ledger = _safe_dict(data.get("ledger"))
    prepare = _safe_dict(row.get("prepare"))
    reason = _safe_text(data.get("reason") or row.get("reason") or prepare.get("reason"), 120)
    status = _safe_text(data.get("status") or row.get("status"), 80)
    capability = _safe_text(row.get("capability") or data.get("capability"), 120)
    detail = _detail_from_row(row)
    title, message = _message_for(reason, capability, detail)
    errors = _safe_list(row.get("errors")) or _safe_list(prepare.get("errors"))
    context_payload = _compact(context or {})

    dedupe_payload = {
        "capability": capability,
        "reason": reason,
        "detail": detail,
        "errors": errors[:8],
        "script_sha256": row.get("script_sha256"),
    }

    payload = {
        "request_kind": "os_capability_contract",
        "blocked_reason": reason,
        "status": status,
        "capability": capability,
        "detail": detail,
        "request_id": _safe_text(row.get("request_id"), 140),
        "ledger_path": _safe_text(ledger.get("path"), 1000),
        "registry_path": _safe_text(row.get("registry_path"), 1000),
        "script_path": _safe_text(row.get("script_path"), 1000),
        "script_sha256": _safe_text(row.get("script_sha256"), 128),
        "contract_version": _safe_text(row.get("contract_version"), 40),
        "authority_level": _safe_text(row.get("authority_level"), 80),
        "mutating": bool(row.get("mutating")),
        "locality": _safe_text(row.get("locality"), 80),
        "args": _compact(row.get("args") or {}),
        "prepare": _compact(prepare),
        "errors": _compact(errors),
    }
    if isinstance(context_payload, dict) and context_payload:
        payload["context"] = context_payload

    return {
        "source": "os_capability",
        "severity": "attention",
        "title": title,
        "message": message,
        "dedupe_key": f"os_capability|{capability}|{reason}|{_stable_hash(dedupe_payload)}",
        "payload": payload,
    }


def publish_os_capability_notice(
    result: dict[str, Any],
    *,
    outbox_path: Path | None = None,
    context: dict[str, Any] | None = None,
    operator_outbox_service: Any = None,
    now_fn: Any = None,
    uuid_fn: Any = None,
) -> dict[str, Any]:
    notice = build_os_capability_notice(result, context=context)
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
