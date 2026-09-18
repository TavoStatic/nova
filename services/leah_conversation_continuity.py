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
TURN_TTL_SECONDS = 7 * 24 * 60 * 60


def _safe_session_id(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "", str(session_id or "").strip())
    return safe or "session"


def _clean_turns(turns: Any) -> list[tuple[str, str]]:
    cleaned: list[tuple[str, str]] = []
    for item in list(turns or []):
        role = ""
        text = ""
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            role = str(item[0] or "").strip().lower()
            text = str(item[1] or "").strip()
        elif isinstance(item, dict):
            role = str(item.get("role") or "").strip().lower()
            text = str(item.get("text") or "").strip()
        if role not in {"user", "assistant"} or not text:
            continue
        cleaned.append((role, text))
    return cleaned


class LeahConversationContinuityStore:
    """Disk-backed Leah session record: attachments plus conversation turns.

    Conversation turns outlive the short attachment handoff window.
    Source of truth for live HTTP turns remains http_session_store;
    this store is the Leah-facing recovery copy.
    """

    def __init__(self, *, root: Path | None = None, ttl_seconds: int = 30 * 60) -> None:
        self._root = Path(root or LEAH_SESSIONS_ROOT)
        self._ttl_seconds = max(60, int(ttl_seconds or 1800))
        self._turn_ttl_seconds = TURN_TTL_SECONDS

    def session_path(self, session_id: str) -> Path:
        return self._root / f"{_safe_session_id(session_id)}.json"

    def _read_raw(self, session_id: str) -> dict[str, Any] | None:
        path = self.session_path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def load(self, session_id: str, *, now: float | None = None) -> dict[str, Any] | None:
        data = self._read_raw(session_id)
        if not data:
            return None
        current = float(now if now is not None else time.time())
        ts = float(data.get("ts") or 0.0)
        turn_ts = float(data.get("turn_ts") or ts or 0.0)
        turns = _clean_turns(data.get("turns"))
        attachment_expired = bool(ts) and current - ts > self._ttl_seconds
        turns_expired = bool(turn_ts) and current - turn_ts > self._turn_ttl_seconds
        if attachment_expired:
            data = dict(data)
            data["items"] = []
            data["stage"] = ""
        if turns_expired:
            data = dict(data)
            data["turns"] = []
            turns = []
        if attachment_expired and not turns:
            try:
                self.session_path(session_id).unlink(missing_ok=True)
            except Exception:
                pass
            return None
        if turns:
            data = dict(data)
            data["turns"] = [{"role": role, "text": text} for role, text in turns]
        return data

    def save(self, session_id: str, payload: dict[str, Any]) -> None:
        safe_session = _safe_session_id(session_id)
        if not safe_session:
            return
        existing = self._read_raw(safe_session) or {}
        body = dict(existing)
        incoming = dict(payload or {})
        if "turns" not in incoming and existing.get("turns"):
            incoming.pop("turns", None)
        body.update(incoming)
        if "turns" not in incoming and existing.get("turns"):
            body["turns"] = existing.get("turns")
            if existing.get("turn_ts"):
                body["turn_ts"] = existing.get("turn_ts")
        body["session_id"] = safe_session
        body["ts"] = float(incoming.get("ts") or time.time())
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            target = self.session_path(safe_session)
            target.write_text(json.dumps(body, ensure_ascii=True, indent=2), encoding="utf-8")
        except Exception:
            pass

    def record_turns(self, session_id: str, turns: Any, *, limit: int = 80) -> None:
        cleaned = _clean_turns(turns)
        if limit > 0:
            cleaned = cleaned[-int(limit) :]
        payload: dict[str, Any] = {
            "turns": [{"role": role, "text": text} for role, text in cleaned],
            "turn_ts": time.time(),
        }
        existing = self._read_raw(session_id) or {}
        if existing.get("ts"):
            payload["ts"] = existing.get("ts")
        self.save(session_id, payload)

    def load_turns(self, session_id: str, *, now: float | None = None) -> list[tuple[str, str]]:
        loaded = self.load(session_id, now=now)
        if not loaded:
            return []
        return _clean_turns(loaded.get("turns"))

    def clear(self, session_id: str) -> None:
        try:
            self.session_path(session_id).unlink(missing_ok=True)
        except Exception:
            pass


def capability_registration() -> dict[str, str]:
    return {CAPABILITY_NAME: CAPABILITY_DESCRIPTION}
