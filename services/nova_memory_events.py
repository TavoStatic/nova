from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional


def append_memory_event(payload: dict, *, memory_events_log: Path) -> None:
    try:
        memory_events_log.parent.mkdir(parents=True, exist_ok=True)
        with open(memory_events_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def record_memory_event(
    action: str,
    status: str,
    *,
    user: Optional[str] = None,
    scope: str = "private",
    backend: str = "",
    kind: str = "",
    source: str = "",
    query: str = "",
    reason: str = "",
    error: str = "",
    lane: str = "",
    result_count: Optional[int] = None,
    duration_ms: Optional[int] = None,
    mode: str = "",
    append_memory_event_fn,
) -> None:
    payload = {
        "event": "memory_operation",
        "action": str(action or "").strip() or "unknown",
        "status": str(status or "").strip() or "unknown",
        "user": str(user or "").strip(),
        "scope": str(scope or "private").strip() or "private",
        "backend": str(backend or "").strip(),
        "kind": str(kind or "").strip(),
        "source": str(source or "").strip(),
        "query_preview": " ".join(str(query or "").split())[:120],
        "reason": str(reason or "").strip(),
        "error": str(error or "").strip()[:300],
        "lane": str(lane or "").strip(),
        "mode": str(mode or "").strip(),
        "ts": int(time.time()),
    }
    if result_count is not None:
        payload["result_count"] = int(result_count)
    if duration_ms is not None:
        payload["duration_ms"] = int(duration_ms)
    append_memory_event_fn(payload)