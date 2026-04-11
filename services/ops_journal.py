from __future__ import annotations

import json
import time
from pathlib import Path


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
    except Exception:
        # Never break runtime flow because journaling failed.
        pass
