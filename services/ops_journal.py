from __future__ import annotations

import json
import time
from pathlib import Path


THIS_IS_NOVA_FILE = "This_is_nova"
THIS_IS_NOVA_SECTION = "ACTIVITY LOG"


def _append_this_is_nova_entry(workspace_root: Path, entry: dict) -> None:
    target = workspace_root / THIS_IS_NOVA_FILE
    timestamp = int(entry.get("ts") or 0)
    rendered = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)) if timestamp else ""
    parts = [
        rendered,
        str(entry.get("category") or "runtime").strip(),
        str(entry.get("action") or "").strip(),
        str(entry.get("result") or "ok").strip(),
        str(entry.get("detail") or "").strip(),
    ]
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    payload_text = json.dumps(payload, ensure_ascii=True, sort_keys=True) if payload else ""
    line = " | ".join(part for part in parts if part)
    if payload_text:
        line = f"{line} | payload={payload_text}" if line else f"payload={payload_text}"
    if not line:
        return

    file_exists = target.exists()
    existing: str | None = None
    if file_exists:
        try:
            existing = target.read_text(encoding="utf-8")
        except Exception:
            existing = None

    with open(target, "a", encoding="utf-8") as handle:
        if not file_exists:
            handle.write(f"{THIS_IS_NOVA_SECTION}\n")
            handle.write(f"{line}\n")
            return

        if existing is not None and THIS_IS_NOVA_SECTION not in existing:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(f"\n{THIS_IS_NOVA_SECTION}\n")
            handle.write(f"{line}\n")
            return

        if existing is not None and existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(f"{line}\n")


def append_ops_event(
    runtime_dir: Path,
    *,
    category: str,
    action: str,
    result: str,
    detail: str = "",
    payload: dict | None = None,
    journal_name: str = "ops_journal.jsonl",
) -> None:
    """Append a single normalized event to the unified operations journal.

    This journal is append-only and intentionally lightweight so it can be
    called from high-frequency paths without raising runtime errors.
    """
    entry = {
        "ts": int(time.time()),
        "category": str(category or "runtime").strip() or "runtime",
        "action": str(action or "").strip(),
        "result": str(result or "").strip() or "ok",
        "detail": str(detail or "")[:500],
    }
    if isinstance(payload, dict) and payload:
        # Keep payload compact and safe for logging.
        safe_payload = {}
        for key, value in payload.items():
            key_text = str(key).strip()
            if not key_text:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe_payload[key_text] = value
            elif isinstance(value, dict):
                safe_payload[key_text] = {str(k): str(v)[:200] for k, v in list(value.items())[:20]}
            elif isinstance(value, list):
                safe_payload[key_text] = [str(item)[:200] for item in value[:20]]
            else:
                safe_payload[key_text] = str(value)[:200]
        if safe_payload:
            entry["payload"] = safe_payload

    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        path = runtime_dir / str(journal_name or "ops_journal.jsonl")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
        workspace_root = runtime_dir.parent if runtime_dir.name.lower() == "runtime" else runtime_dir
        _append_this_is_nova_entry(workspace_root, entry)
    except Exception:
        # Never break runtime flow because journaling failed.
        pass
