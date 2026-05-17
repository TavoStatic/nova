from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable


IDENTITY_BOOTSTRAP_SCHEMA = "nova.memory_identity_bootstrap.v1"
REQUIRED_FACT_KEYS = ("assistant_name", "developer_name", "developer_nickname")


def _text(value: Any, limit: int = 220) -> str:
    return " ".join(str(value or "").strip().split())[: max(1, int(limit))]


def _slot_values(origin_contract: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for slot in list(origin_contract.get("required_slots") or []):
        if not isinstance(slot, dict):
            continue
        key = _text(slot.get("key"), 80)
        value = _text(slot.get("value"), 120)
        if key and value and bool(slot.get("confirmed", False)):
            values[key] = value
    return values


def _ready_origin(origin_contract: dict[str, Any]) -> tuple[bool, str, dict[str, str]]:
    origin = dict(origin_contract or {})
    if not bool(origin.get("valid", False)):
        return False, "origin_contract_invalid", {}
    if _text(origin.get("status"), 80) != "ready":
        return False, "origin_contract_not_ready", {}
    if _text(origin.get("authority"), 80) != "operator_confirmed":
        return False, "origin_authority_not_operator_confirmed", {}
    if not bool(origin.get("may_seed_identity_facts", False)):
        return False, "origin_contract_does_not_allow_identity_seed", {}
    pending = [_text(item, 80) for item in list(origin.get("pending_slots") or []) if _text(item, 80)]
    if pending:
        return False, "origin_contract_has_pending_slots", {}
    values = _slot_values(origin)
    missing = [key for key in REQUIRED_FACT_KEYS if not values.get(key)]
    if missing:
        return False, "origin_contract_missing_confirmed_values", values
    return True, "ready", values


def build_identity_bootstrap_preview(origin_contract: dict[str, Any]) -> dict[str, Any]:
    ready, reason, values = _ready_origin(origin_contract)
    return {
        "ok": ready,
        "status": "ready" if ready else "blocked",
        "reason": reason,
        "facts": {key: values.get(key, "") for key in REQUIRED_FACT_KEYS},
        "origin": {
            "status": _text(origin_contract.get("status"), 80),
            "authority": _text(origin_contract.get("authority"), 80),
            "pending_slots": list(origin_contract.get("pending_slots") or []),
            "path": _text(origin_contract.get("path"), 260),
        },
    }


def apply_identity_bootstrap(
    *,
    origin_contract: dict[str, Any],
    identity_file: Path,
    learned_facts_file: Path,
    load_identity_profile_fn: Callable[[], dict],
    save_identity_profile_fn: Callable[[dict], None],
    load_learned_facts_fn: Callable[[], dict],
    save_learned_facts_fn: Callable[[dict], None],
    mem_add_fn: Callable[[str, str, str], object] | None = None,
    record_memory_event_fn: Callable[..., None] | None = None,
    now_fn: Callable[[], float] = time.time,
) -> dict[str, Any]:
    preview = build_identity_bootstrap_preview(origin_contract)
    if not bool(preview.get("ok", False)):
        if callable(record_memory_event_fn):
            record_memory_event_fn(
                "identity_bootstrap",
                "blocked",
                reason=str(preview.get("reason") or "blocked"),
                lane="memory_bootstrap",
            )
        return {
            "ok": False,
            "status": "blocked",
            "reason": str(preview.get("reason") or "blocked"),
            "preview": preview,
        }

    facts = dict(preview.get("facts") or {})
    existing_facts = dict(load_learned_facts_fn() or {})
    conflicts = {
        key: {"existing": _text(existing_facts.get(key), 120), "incoming": _text(value, 120)}
        for key, value in facts.items()
        if _text(existing_facts.get(key), 120) and _text(existing_facts.get(key), 120) != _text(value, 120)
    }
    if conflicts:
        if callable(record_memory_event_fn):
            record_memory_event_fn(
                "identity_bootstrap",
                "blocked",
                reason="learned_fact_conflict",
                lane="memory_bootstrap",
            )
        return {
            "ok": False,
            "status": "blocked",
            "reason": "learned_fact_conflict",
            "conflicts": conflicts,
            "preview": preview,
        }

    applied_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_fn()))
    profile = dict(load_identity_profile_fn() or {})
    profile.setdefault("schema", IDENTITY_BOOTSTRAP_SCHEMA)
    profile["assistant_name"] = facts["assistant_name"]
    profile["developer"] = {
        "name": facts["developer_name"],
        "nickname": facts["developer_nickname"],
    }
    profile["bootstrap"] = {
        "schema": IDENTITY_BOOTSTRAP_SCHEMA,
        "origin_status": preview["origin"]["status"],
        "origin_authority": preview["origin"]["authority"],
        "origin_path": preview["origin"]["path"],
        "applied_at": applied_at,
    }

    learned = dict(existing_facts)
    learned.update(facts)
    learned["identity_bootstrap_origin"] = "operator_confirmed"
    learned["updated_at"] = applied_at

    save_identity_profile_fn(profile)
    save_learned_facts_fn(learned)

    memory_rows: list[str] = []
    if callable(mem_add_fn):
        for key in REQUIRED_FACT_KEYS:
            row = f"learned_fact: {key}={facts[key]}"
            mem_add_fn("identity", "bootstrap", row)
            memory_rows.append(row)

    if callable(record_memory_event_fn):
        record_memory_event_fn(
            "identity_bootstrap",
            "ok",
            result_count=len(REQUIRED_FACT_KEYS),
            lane="memory_bootstrap",
            mode="operator_confirmed",
        )

    return {
        "ok": True,
        "status": "applied",
        "reason": "operator_confirmed_identity_bootstrap_applied",
        "facts": facts,
        "identity_file": str(identity_file),
        "learned_facts_file": str(learned_facts_file),
        "memory_rows": memory_rows,
        "applied_at": applied_at,
    }


def render_identity_bootstrap_result(result: dict[str, Any]) -> str:
    facts = result.get("facts") if isinstance(result.get("facts"), dict) else {}
    lines = [
        "Memory Identity Bootstrap",
        f"- status: {result.get('status')}",
        f"- reason: {result.get('reason')}",
    ]
    if facts:
        lines.extend(
            [
                f"- assistant_name: {facts.get('assistant_name') or ''}",
                f"- developer_name: {facts.get('developer_name') or ''}",
                f"- developer_nickname: {facts.get('developer_nickname') or ''}",
            ]
        )
    if result.get("identity_file"):
        lines.append(f"- identity_file: {result.get('identity_file')}")
    if result.get("learned_facts_file"):
        lines.append(f"- learned_facts_file: {result.get('learned_facts_file')}")
    if isinstance(result.get("conflicts"), dict) and result.get("conflicts"):
        lines.append(f"- conflicts: {result.get('conflicts')}")
    return "\n".join(lines)
