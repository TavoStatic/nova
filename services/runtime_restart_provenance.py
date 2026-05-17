from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


class RuntimeRestartProvenanceService:
    """Persist one-shot restart intent so guard boot metrics have origin."""

    DEFAULT_TTL_SECONDS = 15 * 60

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(path).with_suffix(Path(path).suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        tmp.replace(path)

    def build_intent(
        self,
        *,
        source: str,
        action: str,
        reason: str,
        requested_by: str = "operator",
        planned: bool = True,
        ttl_seconds: int | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        ts = float(now if now is not None else time.time())
        ttl = int(ttl_seconds or self.DEFAULT_TTL_SECONDS)
        return {
            "ok": True,
            "intent_id": f"{int(ts)}-{uuid.uuid4().hex[:8]}",
            "ts": ts,
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
            "expires_at": ts + max(1, ttl),
            "ttl_seconds": max(1, ttl),
            "source": str(source or "unknown").strip() or "unknown",
            "action": str(action or "runtime_restart").strip() or "runtime_restart",
            "reason": str(reason or "").strip(),
            "requested_by": str(requested_by or "operator").strip() or "operator",
            "planned": bool(planned),
        }

    def read_pending_intent(self, path: Path, *, now: float | None = None) -> dict[str, Any]:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        expires_at = payload.get("expires_at")
        if isinstance(expires_at, (int, float)) and float(expires_at) < float(now if now is not None else time.time()):
            return {}
        return dict(payload)

    def write_pending_intent(
        self,
        path: Path,
        *,
        source: str,
        action: str,
        reason: str,
        requested_by: str = "operator",
        planned: bool = True,
        ttl_seconds: int | None = None,
        replace: bool = True,
        now: float | None = None,
    ) -> dict[str, Any]:
        try:
            if not replace:
                existing = self.read_pending_intent(path, now=now)
                if existing:
                    return {**existing, "preserved": True}
            intent = self.build_intent(
                source=source,
                action=action,
                reason=reason,
                requested_by=requested_by,
                planned=planned,
                ttl_seconds=ttl_seconds,
                now=now,
            )
            self._atomic_write_json(Path(path), intent)
            return intent
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "source": str(source or "unknown"),
                "action": str(action or "runtime_restart"),
            }

    def consume_pending_intent(self, path: Path, *, now: float | None = None) -> dict[str, Any]:
        payload = self.read_pending_intent(path, now=now)
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass
        if not payload:
            return {}
        ts = payload.get("ts")
        if isinstance(ts, (int, float)):
            payload["age_sec"] = round(float(now if now is not None else time.time()) - float(ts), 3)
        return payload


RUNTIME_RESTART_PROVENANCE_SERVICE = RuntimeRestartProvenanceService()
