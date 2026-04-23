"""Decision-only adaptive learning for work-tree routing.

Tracks work decisions and their success/failure outcomes per work identity.
This module intentionally does not analyze response quality, language, or
user preference metrics.
"""

from __future__ import annotations

import json
from pathlib import Path
import threading
import time
from typing import Optional


class WorkTreeDecisionOutcome:
    """Record of a single work decision and its measured outcome."""

    def __init__(
        self,
        *,
        decision_type: str,  # "continue", "branch", "new", "complete"
        work_identity_key: str,
        timestamp: float = 0.0,
        branch_id: str = "",
        outcome: str = "",  # "success", "failure", ""
        outcome_timestamp: float = 0.0,
    ) -> None:
        self.decision_type = str(decision_type or "").strip()
        self.work_identity_key = str(work_identity_key or "").strip()
        self.timestamp = float(timestamp or time.time())
        self.branch_id = str(branch_id or "").strip()
        self.outcome = str(outcome or "").strip()
        self.outcome_timestamp = float(outcome_timestamp or 0.0)

    def to_dict(self) -> dict[str, object]:
        return {
            "decision_type": self.decision_type,
            "work_identity_key": self.work_identity_key,
            "timestamp": self.timestamp,
            "branch_id": self.branch_id,
            "outcome": self.outcome,
            "outcome_timestamp": self.outcome_timestamp,
        }


class IdentityDecisionScores:
    """Lightweight scoring for a single work identity."""

    def __init__(self, *, work_identity_key: str) -> None:
        self.work_identity_key = str(work_identity_key or "").strip()
        self.continue_score: float = 0.0
        self.branch_score: float = 0.0
        self.new_tree_score: float = 0.0
        self.completion_score: float = 0.0
        self.last_updated: float = time.time()
        self.decision_count: int = 0

    def record_outcome(self, *, decision_type: str, outcome: str) -> None:
        """Update score for a decision type using simple +/- 1 reinforcement."""
        decision = str(decision_type or "").strip().lower()
        result = str(outcome or "").strip().lower()

        if not decision or not result:
            return

        delta = 1.0 if result == "success" else -1.0 if result == "failure" else 0.0
        if delta == 0.0:
            return

        if decision == "continue":
            self.continue_score += delta
        elif decision == "branch":
            self.branch_score += delta
        elif decision == "new":
            self.new_tree_score += delta
        elif decision == "complete":
            self.completion_score += delta
        else:
            return

        self.last_updated = time.time()
        self.decision_count += 1

    def apply_decay(self, *, decay_factor: float = 0.99, age_seconds: int = 86400) -> None:
        """Apply exponential decay to older scores.

        Older decisions lose influence over time.
        """
        if decay_factor <= 0.0 or decay_factor > 1.0:
            return

        try:
            age = time.time() - self.last_updated
            if age > float(age_seconds):
                # Exponential decay: score *= decay_factor ^ (age / max_age)
                scaling = float(decay_factor) ** (float(age) / float(age_seconds))
                self.continue_score *= scaling
                self.branch_score *= scaling
                self.new_tree_score *= scaling
                self.completion_score *= scaling
        except Exception:
            pass

    def get_bias(self) -> str:
        """Return the decision type with highest current score.

        Used to bias future decisions for this identity.
        """
        scores: dict[str, float] = {
            "continue": self.continue_score,
            "branch": self.branch_score,
            "new": self.new_tree_score,
            "complete": self.completion_score,
        }
        significant = {k: v for k, v in scores.items() if v > 0.0}
        if not significant:
            return ""
        return max(significant, key=lambda k: significant[k])

    def to_dict(self) -> dict[str, object]:
        return {
            "work_identity_key": self.work_identity_key,
            "continue_score": self.continue_score,
            "branch_score": self.branch_score,
            "new_tree_score": self.new_tree_score,
            "completion_score": self.completion_score,
            "decision_count": self.decision_count,
            "last_updated": self.last_updated,
            "bias": self.get_bias(),
        }


class WorkTreeDecisionAdapter:
    """Adaptive judgment system that learns from decision outcomes."""

    def __init__(self, *, state_path: Optional[Path] = None) -> None:
        root = Path(__file__).resolve().parents[1]
        self._state_path = state_path or (root / "runtime" / "work_decision_learning.json")
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._identity_scores: dict[str, IdentityDecisionScores] = {}
        self._decision_history: list[WorkTreeDecisionOutcome] = []
        self._max_history: int = 500
        self._load_state()

    @staticmethod
    def _canonical_decision_type(decision_type: str) -> str:
        raw = str(decision_type or "").strip().lower()
        if raw in {"continue", "continue_work", "continuing_existing_work"}:
            return "continue"
        if raw in {"branch", "branch_work", "branching_work", "new_branch_under_same_tree"}:
            return "branch"
        if raw in {"new", "new_work", "new_tree"}:
            return "new"
        if raw in {"complete", "complete_tree", "completion", "completed"}:
            return "complete"
        return ""

    def _save_state(self) -> None:
        try:
            payload = {
                "identities": {k: v.to_dict() for k, v in self._identity_scores.items()},
                "decision_history": [d.to_dict() for d in self._decision_history[-self._max_history :]],
            }
            self._state_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        except Exception:
            pass

    def _load_state(self) -> None:
        try:
            if not self._state_path.exists():
                return
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            identities = payload.get("identities") if isinstance(payload, dict) else {}
            history = payload.get("decision_history") if isinstance(payload, dict) else []

            if isinstance(identities, dict):
                for key, raw in identities.items():
                    if not isinstance(raw, dict):
                        continue
                    score = IdentityDecisionScores(work_identity_key=str(key))
                    score.continue_score = float(raw.get("continue_score") or 0.0)
                    score.branch_score = float(raw.get("branch_score") or 0.0)
                    score.new_tree_score = float(raw.get("new_tree_score") or 0.0)
                    score.completion_score = float(raw.get("completion_score") or 0.0)
                    score.decision_count = int(raw.get("decision_count") or 0)
                    score.last_updated = float(raw.get("last_updated") or time.time())
                    self._identity_scores[score.work_identity_key] = score

            if isinstance(history, list):
                loaded: list[WorkTreeDecisionOutcome] = []
                for row in history[-self._max_history :]:
                    if not isinstance(row, dict):
                        continue
                    decision = self._canonical_decision_type(str(row.get("decision_type") or ""))
                    if not decision:
                        continue
                    loaded.append(
                        WorkTreeDecisionOutcome(
                            decision_type=decision,
                            work_identity_key=str(row.get("work_identity_key") or "").strip(),
                            timestamp=float(row.get("timestamp") or 0.0),
                            branch_id=str(row.get("branch_id") or "").strip(),
                            outcome=str(row.get("outcome") or "").strip().lower(),
                            outcome_timestamp=float(row.get("outcome_timestamp") or 0.0),
                        )
                    )
                self._decision_history = loaded
        except Exception:
            self._identity_scores = {}
            self._decision_history = []

    def record_decision(
        self,
        *,
        decision_type: str,
        work_identity_key: str,
        branch_id: str = "",
        timestamp: float = 0.0,
    ) -> None:
        """Record a work decision for future learning."""
        key = str(work_identity_key or "").strip()
        decision = self._canonical_decision_type(decision_type)
        if not key or not decision:
            return
        with self._lock:
            if key not in self._identity_scores:
                self._identity_scores[key] = IdentityDecisionScores(work_identity_key=key)
            entry = WorkTreeDecisionOutcome(
                decision_type=decision,
                work_identity_key=key,
                timestamp=float(timestamp or time.time()),
                branch_id=str(branch_id or "").strip(),
            )
            self._decision_history.append(entry)
            if len(self._decision_history) > self._max_history:
                self._decision_history = self._decision_history[-self._max_history :]
            self._save_state()

    def record_outcome(
        self,
        *,
        work_identity_key: str,
        decision_type: str,
        outcome: str,
    ) -> None:
        """Record the measured outcome of a prior decision."""
        key = str(work_identity_key or "").strip()
        decision = self._canonical_decision_type(decision_type)
        result = str(outcome or "").strip().lower()
        if result not in {"success", "failure"}:
            return
        if not key:
            return
        if not decision:
            return

        with self._lock:
            if key not in self._identity_scores:
                self._identity_scores[key] = IdentityDecisionScores(work_identity_key=key)

            self._identity_scores[key].record_outcome(
                decision_type=decision,
                outcome=result,
            )

            for row in reversed(self._decision_history):
                if row.work_identity_key == key and row.decision_type == decision and not row.outcome:
                    row.outcome = result
                    row.outcome_timestamp = time.time()
                    break
            self._save_state()

    def get_bias_for_identity(self, *, work_identity_key: str) -> str:
        """Get the decision bias for a work identity.

        Returns: "continue", "branch", "new", "complete", or ""
        """
        key = str(work_identity_key or "").strip()
        if not key:
            return ""

        if key not in self._identity_scores:
            return ""

        scores = self._identity_scores[key]
        scores.apply_decay()
        return scores.get_bias()

    def apply_bias_to_probability(
        self,
        *,
        work_identity_key: str,
        decision_type: str,
        base_probability: float = 0.5,
    ) -> float:
        """Adjust decision probability based on learned bias.

        If identity has positive history with this decision type,
        increase the probability slightly.

        Returns: adjusted probability (0.0 - 1.0)
        """
        key = str(work_identity_key or "").strip()
        decision = self._canonical_decision_type(decision_type)

        if not key or not decision:
            return float(base_probability)

        if key not in self._identity_scores:
            return float(base_probability)

        scores = self._identity_scores[key]
        scores.apply_decay()

        # Map decision to score
        score_map = {
            "continue": scores.continue_score,
            "branch": scores.branch_score,
            "new": scores.new_tree_score,
            "complete": scores.completion_score,
        }

        decision_score = float(score_map.get(decision, 0.0))

        clamped_score = max(-3.0, min(3.0, decision_score))
        bias_adjustment = clamped_score * 0.08

        adjusted = float(base_probability) + bias_adjustment
        return max(0.0, min(1.0, adjusted))

    def get_scores_for_identity(self, *, work_identity_key: str) -> Optional[dict[str, object]]:
        """Get raw scores for an identity (debugging / UI)."""
        key = str(work_identity_key or "").strip()
        if not key or key not in self._identity_scores:
            return None

        scores = self._identity_scores[key]
        scores.apply_decay()
        return scores.to_dict()

    def get_recent_decisions(self, *, limit: int = 10, work_identity_key: str = "") -> list[dict[str, object]]:
        """Get recent decision history."""
        key = str(work_identity_key or "").strip()
        rows = self._decision_history
        if key:
            rows = [r for r in rows if r.work_identity_key == key]
        recent = rows[-max(1, int(limit)) :]
        return [d.to_dict() for d in recent]

    def reset_state(self, *, clear_persistence: bool = False) -> None:
        """Reset adapter state (used by tests)."""
        with self._lock:
            self._identity_scores = {}
            self._decision_history = []
            if clear_persistence:
                try:
                    if self._state_path.exists():
                        self._state_path.unlink()
                except Exception:
                    pass
            else:
                self._save_state()

    def get_adapter_state(self) -> dict[str, object]:
        """Export full adapter state for inspection / debugging."""
        return {
            "identity_count": len(self._identity_scores),
            "recent_decisions": self.get_recent_decisions(limit=5),
            "all_identities": {
                key: scores.to_dict()
                for key, scores in self._identity_scores.items()
            },
        }


# Global singleton
WORK_TREE_DECISION_ADAPTER = WorkTreeDecisionAdapter()
