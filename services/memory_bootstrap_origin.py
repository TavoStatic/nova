from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable


BOOTSTRAP_ORIGIN_SCHEMA = "nova.memory_bootstrap_origin.v1"
DEFAULT_REQUIRED_SLOTS = ("assistant_name", "developer_name", "developer_nickname")
_INVALID_PERSON_TOKENS = {
    "your",
    "yours",
    "you",
    "me",
    "my",
    "i",
    "nova",
    "nova's",
    "creator",
    "developer",
    "the same person",
    "same person",
}


def _compact(value: Any, max_chars: int = 220) -> str:
    text = str(value or "").strip()
    return text[: max(1, int(max_chars))]


def _issue(severity: str, code: str, detail: str, *, path: Path | None = None) -> dict[str, str]:
    out = {
        "severity": _compact(severity, 24) or "warning",
        "code": _compact(code, 80) or "memory_bootstrap_origin_issue",
        "detail": _compact(detail, 260),
    }
    if path is not None:
        out["path"] = str(path)
    return out


def _default_slot_payload(slot: str) -> dict[str, object]:
    return {
        "key": str(slot or "").strip(),
        "required_origin": "operator_confirmation",
        "confirmed": False,
    }


def default_pending_origin_contract(*, created_by: str = "codex_root_repair", now_fn: Callable[[], float] = time.time) -> dict[str, object]:
    return {
        "schema": BOOTSTRAP_ORIGIN_SCHEMA,
        "status": "pending_operator_confirmation",
        "created_at": int(now_fn()),
        "created_by": str(created_by or "").strip() or "unknown",
        "purpose": "Record memory bootstrap authority without seeding identity facts.",
        "required_slots": [_default_slot_payload(slot) for slot in DEFAULT_REQUIRED_SLOTS],
        "rules": {
            "may_create_identity_json": False,
            "may_create_learned_facts_json": False,
            "may_seed_identity_facts": False,
            "requires_operator_confirmation": True,
        },
        "blocked_shortcuts": [
            "do_not_flip_memory_enabled_as_a_fix",
            "do_not_seed_identity_from_code_defaults",
            "do_not_mark_memory_ready_without_event_evidence",
        ],
    }


def write_origin_contract(path: Path, payload: dict[str, object]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(f"{target.suffix}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(target)


def _clean_slot_value(slot_key: str, raw_value: Any) -> str:
    value = " ".join(str(raw_value or "").strip().split())
    if not value:
        return ""
    if slot_key == "assistant_name":
        return value[:80]
    if value.lower() in _INVALID_PERSON_TOKENS:
        return ""
    return value[:120]


def _load_json_dict(path: Path) -> tuple[dict[str, object], str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, str(exc)
    if not isinstance(data, dict):
        return {}, "json_root_not_object"
    return data, ""


def _slot_rows(raw_slots: Any) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in list(raw_slots or []):
        if isinstance(raw, str):
            slot = _default_slot_payload(raw)
        elif isinstance(raw, dict):
            slot = dict(raw)
        else:
            continue
        key = str(slot.get("key") or "").strip()
        if not key:
            continue
        slot["key"] = key
        slot["confirmed"] = bool(slot.get("confirmed", False))
        slot["required_origin"] = str(slot.get("required_origin") or "operator_confirmation").strip() or "operator_confirmation"
        rows.append(slot)
    return rows


def _raw_origin_contract(path: Path, *, now_fn: Callable[[], float] = time.time) -> dict[str, object]:
    target = Path(path)
    if not target.exists():
        return default_pending_origin_contract(now_fn=now_fn)
    data, error = _load_json_dict(target)
    if error:
        return default_pending_origin_contract(now_fn=now_fn)
    return dict(data)


def confirm_origin_contract(
    path: Path,
    slot_values: dict[str, Any],
    *,
    confirmed_by: str = "operator",
    evidence: str = "",
    now_fn: Callable[[], float] = time.time,
) -> dict[str, object]:
    """Confirm bootstrap origin slots without writing identity facts."""

    target = Path(path)
    payload = _raw_origin_contract(target, now_fn=now_fn)
    now = int(now_fn())
    confirmed_by_text = _compact(confirmed_by, 120) or "operator"
    evidence_text = _compact(evidence, 500)
    incoming = {
        str(key or "").strip(): value
        for key, value in dict(slot_values or {}).items()
        if str(key or "").strip()
    }

    existing_slots = {str(slot.get("key") or "").strip(): dict(slot) for slot in _slot_rows(payload.get("required_slots"))}
    slots: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for slot_key in DEFAULT_REQUIRED_SLOTS:
        slot = existing_slots.get(slot_key) or _default_slot_payload(slot_key)
        if slot_key in incoming:
            value = _clean_slot_value(slot_key, incoming.get(slot_key))
            if value:
                slot["value"] = value
                slot["confirmed"] = True
                slot["confirmed_at"] = now
                slot["confirmed_by"] = confirmed_by_text
                if evidence_text:
                    slot["confirmation_evidence"] = evidence_text
            else:
                slot["confirmed"] = False
                slot.pop("value", None)
                errors.append(
                    _issue(
                        "failure",
                        f"{slot_key}_confirmation_invalid",
                        f"{slot_key} confirmation value is empty or not allowed.",
                        path=target,
                    )
                )
        slots.append(slot)

    missing = [
        str(slot.get("key") or "")
        for slot in slots
        if not bool(slot.get("confirmed", False)) or not str(slot.get("value") or "").strip()
    ]
    ready = not errors and not missing
    rules = dict(payload.get("rules") if isinstance(payload.get("rules"), dict) else {})
    rules.update(
        {
            "requires_operator_confirmation": True,
            "may_create_identity_json": ready,
            "may_create_learned_facts_json": ready,
            "may_seed_identity_facts": ready,
        }
    )
    payload.update(
        {
            "schema": BOOTSTRAP_ORIGIN_SCHEMA,
            "status": "ready" if ready else "pending_operator_confirmation",
            "required_slots": slots,
            "rules": rules,
            "updated_at": now,
            "updated_by": confirmed_by_text,
        }
    )
    if ready:
        payload["confirmed_at"] = now
        payload["confirmed_by"] = confirmed_by_text
    if errors:
        payload["confirmation_errors"] = errors
    else:
        payload.pop("confirmation_errors", None)

    write_origin_contract(target, payload)
    return load_origin_contract(target)


def load_origin_contract(path: Path) -> dict[str, object]:
    target = Path(path)
    issues: list[dict[str, str]] = []
    payload: dict[str, object] = {
        "path": str(target),
        "exists": target.exists(),
        "valid": False,
        "schema": "",
        "status": "missing",
        "authority": "none",
        "required_slots": [_default_slot_payload(slot) for slot in DEFAULT_REQUIRED_SLOTS],
        "confirmed_slots": [],
        "pending_slots": list(DEFAULT_REQUIRED_SLOTS),
        "may_seed_identity_facts": False,
        "rules": {},
        "issues": issues,
    }
    if not target.exists():
        issues.append(_issue("warning", "memory_bootstrap_origin_missing", "Memory bootstrap origin contract is missing.", path=target))
        return payload

    data, error = _load_json_dict(target)
    if error:
        issues.append(_issue("failure", "memory_bootstrap_origin_invalid", f"Memory bootstrap origin contract is not readable: {error}", path=target))
        payload["status"] = "invalid"
        return payload

    schema = str(data.get("schema") or "").strip()
    if schema != BOOTSTRAP_ORIGIN_SCHEMA:
        issues.append(
            _issue(
                "failure",
                "memory_bootstrap_origin_schema_invalid",
                f"Memory bootstrap origin schema is {schema or 'missing'}, expected {BOOTSTRAP_ORIGIN_SCHEMA}.",
                path=target,
            )
        )

    slots = _slot_rows(data.get("required_slots"))
    if not slots:
        issues.append(_issue("failure", "memory_bootstrap_origin_slots_missing", "Memory bootstrap origin has no required slots.", path=target))
        slots = [_default_slot_payload(slot) for slot in DEFAULT_REQUIRED_SLOTS]

    confirmed_slots = [str(slot.get("key") or "") for slot in slots if bool(slot.get("confirmed", False))]
    pending_slots = [str(slot.get("key") or "") for slot in slots if not bool(slot.get("confirmed", False))]
    rules = data.get("rules") if isinstance(data.get("rules"), dict) else {}
    raw_status = str(data.get("status") or "").strip().lower()
    allowed_statuses = {"pending_operator_confirmation", "ready", "retired", "invalid"}
    status = raw_status if raw_status in allowed_statuses else "invalid"
    if status == "invalid" and raw_status:
        issues.append(_issue("failure", "memory_bootstrap_origin_status_invalid", f"Memory bootstrap origin status is not recognized: {raw_status}.", path=target))
    elif not raw_status:
        issues.append(_issue("failure", "memory_bootstrap_origin_status_missing", "Memory bootstrap origin status is missing.", path=target))

    may_seed = bool(rules.get("may_seed_identity_facts") or rules.get("may_create_identity_json") or rules.get("may_create_learned_facts_json"))
    may_seed = bool(may_seed and status == "ready" and not pending_slots)
    if pending_slots and status == "ready":
        issues.append(_issue("failure", "memory_bootstrap_origin_ready_with_pending_slots", "Memory bootstrap origin is marked ready while slots remain unconfirmed.", path=target))
        status = "invalid"
        may_seed = False

    if status == "pending_operator_confirmation" and pending_slots:
        issues.append(
            _issue(
                "warning",
                "memory_bootstrap_origin_pending",
                "Memory bootstrap origin exists, but operator confirmation is still pending.",
                path=target,
            )
        )

    valid = schema == BOOTSTRAP_ORIGIN_SCHEMA and not any(str(item.get("severity") or "") == "failure" for item in issues)
    if status == "ready" and may_seed:
        authority = "operator_confirmed"
    elif status == "pending_operator_confirmation":
        authority = "pending_operator_confirmation"
    else:
        authority = "none"

    payload.update(
        {
            "valid": valid,
            "schema": schema,
            "status": status,
            "authority": authority,
            "required_slots": slots,
            "confirmed_slots": confirmed_slots,
            "pending_slots": pending_slots,
            "may_seed_identity_facts": may_seed,
            "rules": dict(rules),
            "created_at": data.get("created_at"),
            "created_by": str(data.get("created_by") or "").strip(),
            "purpose": str(data.get("purpose") or "").strip(),
        }
    )
    return payload
