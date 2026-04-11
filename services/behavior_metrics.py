from __future__ import annotations

import json
import time
from pathlib import Path


DEFAULT_BEHAVIOR_METRICS: dict = {
    "deterministic_hit": 0,
    "tool_route": 0,
    "llm_fallback": 0,
    "low_confidence_block": 0,
    "correction_learned": 0,
    "correction_applied": 0,
    "self_correction_applied": 0,
    "conflict_detected": 0,
    "top_repeated_failure_class": "",
    "top_repeated_correction_class": "",
    "routing_stable": True,
    "unsupported_claims_blocked": False,
    "last_reflection_turn": 0,
    "last_reflection_at": "",
    "last_event": "",
    "updated_at": "",
}


class BehaviorMetricsStore:
    def __init__(self, metrics_file: Path, initial: dict | None = None) -> None:
        self.metrics_file = metrics_file
        self.metrics = dict(DEFAULT_BEHAVIOR_METRICS)
        if isinstance(initial, dict):
            self.metrics.update(initial)

    def save(self) -> None:
        try:
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.metrics_file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.metrics, ensure_ascii=True, indent=2), encoding="utf-8")
            tmp.replace(self.metrics_file)
        except Exception:
            pass

    def record_event(self, event: str) -> None:
        normalized = (event or "").strip()
        if not normalized:
            return
        if normalized in self.metrics and isinstance(self.metrics.get(normalized), int):
            self.metrics[normalized] = int(self.metrics.get(normalized, 0)) + 1
        self.metrics["last_event"] = normalized
        self.metrics["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.save()

    def snapshot(self) -> dict:
        return dict(self.metrics)

    def update_from_reflection(self, payload: dict, count_total: int) -> None:
        """Update metrics from reflection payload after reflection cycle."""
        if not isinstance(payload, dict):
            return
        try:
            if "top_repeated_failure_class" in payload:
                self.metrics["top_repeated_failure_class"] = payload["top_repeated_failure_class"]
            if "top_repeated_correction_class" in payload:
                self.metrics["top_repeated_correction_class"] = payload["top_repeated_correction_class"]
            if "routing_stable" in payload:
                self.metrics["routing_stable"] = bool(payload["routing_stable"])
            if "unsupported_claims_blocked" in payload:
                self.metrics["unsupported_claims_blocked"] = bool(payload["unsupported_claims_blocked"])
            self.metrics["last_reflection_turn"] = int(count_total or 0)
            if "ts" in payload:
                self.metrics["last_reflection_at"] = payload["ts"]
            self.save()
        except Exception:
            pass
