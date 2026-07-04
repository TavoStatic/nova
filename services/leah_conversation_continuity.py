from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from services.nova_runtime_context import RUNTIME_DIR

LEAH_SESSIONS_ROOT = RUNTIME_DIR / "leah_sessions"
CAPABILITY_NAME = "leah_conversation_continuity"
CAPABILITY_DESCRIPTION = "Leah can maintain continuity across turns and sessions"


def _safe_session_id(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "", str(session_id or "").strip())
    return safe or "session"


class LeahConversationContinuityStore:
    """Disk-backed Leah session handoff context (in-process memory remains in frontdoor)."""

    def __init__(self, *, root: Path | None = None, ttl_seconds: int = 30 * 60) -> None:
        self._root = Path(root or LEAH_SESSIONS_ROOT)
        self._ttl_seconds = max(60, int(ttl_seconds or 1800))

    def session_path(self, session_id: str) -> Path:
        return self._root / f"{_safe_session_id(session_id)}.json"

    def load(self, session_id: str, *, now: float | None = None) -> dict[str, Any] | None:
        path = self.session_path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        ts = float(data.get("ts") or 0.0)
        current = float(now if now is not None else time.time())
        if ts and current - ts > self._ttl_seconds:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            return None
        return data

    def save(self, session_id: str, payload: dict[str, Any]) -> None:
        safe_session = _safe_session_id(session_id)
        if not safe_session:
            return
        body = dict(payload or {})
        body["session_id"] = safe_session
        body["ts"] = float(body.get("ts") or time.time())
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            target = self.session_path(safe_session)
            target.write_text(json.dumps(body, ensure_ascii=True, indent=2), encoding="utf-8")
        except Exception:
            pass

    def clear(self, session_id: str) -> None:
        try:
            self.session_path(session_id).unlink(missing_ok=True)
        except Exception:
            pass


def capability_registration() -> dict[str, str]:
    return {CAPABILITY_NAME: CAPABILITY_DESCRIPTION}