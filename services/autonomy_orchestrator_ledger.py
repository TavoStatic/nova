from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _safe_text(value: Any, limit: int = 220) -> str:
    return str(value or "").strip()[:limit]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


class AutonomyOrchestratorLedgerService:
    """Summarize advisory autonomy ledger rows for operator readback."""

    @staticmethod
    def recent_rows(ledger_path: Path, *, limit: int = 80) -> list[dict[str, Any]]:
        try:
            path = Path(ledger_path)
            if not path.exists():
                return []
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return []

        rows: list[dict[str, Any]] = []
        for line in lines[-max(1, int(limit)) :]:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    @staticmethod
    def _recommendation_key(row: dict[str, Any]) -> str:
        decision = _safe_text(row.get("decision"), 80) or "unknown"
        action = _safe_text(_as_dict(row.get("action")).get("act"), 80)
        if decision == "recommend_action" and action:
            return f"{decision}:{action}"
        return decision

    @staticmethod
    def _weak_posture(row: dict[str, Any]) -> bool:
        evidence = _as_dict(row.get("evidence"))
        posture = _as_dict(evidence.get("posture"))
        conflicts = evidence.get("conflicts") if isinstance(evidence.get("conflicts"), list) else []
        score = _as_int(posture.get("score"))
        threshold = _as_int(posture.get("threshold"), 85)
        level = _safe_text(posture.get("level"), 80).lower()
        return bool(conflicts) or score < threshold or level in {"", "unknown", "repair", "watch"}

    def summary(self, ledger_path: Path, *, limit: int = 80) -> dict[str, Any]:
        rows = self.recent_rows(ledger_path, limit=limit)
        out: dict[str, Any] = {
            "ok": True,
            "count": len(rows),
            "limit": max(1, int(limit)),
            "decision_counts": {},
            "action_counts": {},
            "rejection_reason_counts": {},
            "recommend_count": 0,
            "defer_count": 0,
            "block_count": 0,
            "refusal_count": 0,
            "weak_posture_count": 0,
            "weak_posture_refusal_count": 0,
            "weak_posture_refusal_rate": 0.0,
            "recommendation_changes": 0,
            "recommendation_change_rate": 0.0,
            "stable_recommendation": True,
            "last_ts": "",
            "last_decision": "",
            "last_action": "",
            "last_reason": "",
            "last_rejection_reasons": [],
            "last_recommendation_key": "",
        }
        previous_key = ""
        transitions = 0

        for row in rows:
            decision = _safe_text(row.get("decision"), 80) or "unknown"
            action = _safe_text(_as_dict(row.get("action")).get("act"), 80) or "none"
            recommendation_key = self._recommendation_key(row)
            out["decision_counts"][decision] = int(out["decision_counts"].get(decision, 0)) + 1
            out["action_counts"][action] = int(out["action_counts"].get(action, 0)) + 1
            if decision == "recommend_action":
                out["recommend_count"] += 1
            elif decision == "defer_with_reason":
                out["defer_count"] += 1
                out["refusal_count"] += 1
            elif decision == "block_with_reason":
                out["block_count"] += 1
                out["refusal_count"] += 1
            else:
                out["refusal_count"] += 1

            for reason in list(row.get("rejection_reasons") or []):
                clean = _safe_text(reason, 120)
                if clean:
                    out["rejection_reason_counts"][clean] = int(out["rejection_reason_counts"].get(clean, 0)) + 1

            if self._weak_posture(row):
                out["weak_posture_count"] += 1
                if decision != "recommend_action":
                    out["weak_posture_refusal_count"] += 1

            if previous_key and recommendation_key != previous_key:
                transitions += 1
            previous_key = recommendation_key

        count = int(out["count"])
        if count > 1:
            out["recommendation_changes"] = transitions
            out["recommendation_change_rate"] = round(transitions / float(count - 1), 4)
            out["stable_recommendation"] = bool(out["recommendation_change_rate"] <= 0.25)
        if out["weak_posture_count"]:
            out["weak_posture_refusal_rate"] = round(
                out["weak_posture_refusal_count"] / float(out["weak_posture_count"]),
                4,
            )

        if rows:
            last = rows[-1]
            out["last_ts"] = _safe_text(last.get("ts"), 80)
            out["last_decision"] = _safe_text(last.get("decision"), 80)
            out["last_action"] = _safe_text(_as_dict(last.get("action")).get("act"), 80)
            out["last_reason"] = _safe_text(last.get("reason"), 360)
            out["last_rejection_reasons"] = [
                _safe_text(item, 120)
                for item in list(last.get("rejection_reasons") or [])[:8]
                if _safe_text(item, 120)
            ]
            out["last_recommendation_key"] = self._recommendation_key(last)
        return out


AUTONOMY_ORCHESTRATOR_LEDGER_SERVICE = AutonomyOrchestratorLedgerService()
