from __future__ import annotations

import time
from typing import Any, Callable


DECISION_RECOMMEND_ACTION = "recommend_action"
DECISION_DEFER_WITH_REASON = "defer_with_reason"
DECISION_BLOCK_WITH_REASON = "block_with_reason"

ALLOWED_DECISIONS = {
    DECISION_RECOMMEND_ACTION,
    DECISION_DEFER_WITH_REASON,
    DECISION_BLOCK_WITH_REASON,
}


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_text(value: Any, limit: int = 220) -> str:
    return str(value or "").strip()[:limit]


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return _safe_text(value, 120)
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, item in list(value.items())[:30]:
            compact[str(key)] = _compact_value(item, depth=depth + 1)
        return compact
    if isinstance(value, list):
        return [_compact_value(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, tuple):
        return [_compact_value(item, depth=depth + 1) for item in list(value)[:20]]
    if isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 4)
    if value is None:
        return None
    return _safe_text(value, 500)


class AutonomyOrchestratorService:
    """Advisory-only control law for a single governed autonomy cycle."""

    def __init__(self, *, posture_threshold: int = 85) -> None:
        self.posture_threshold = int(posture_threshold)

    @staticmethod
    def _runtime_ok(section: dict[str, Any]) -> bool | None:
        if not section:
            return None
        if "ok" in section:
            return bool(section.get("ok"))
        status = str(section.get("status") or section.get("state") or "").strip().lower()
        if status in {"ok", "ready", "healthy", "running", "active"}:
            return True
        if status in {"failed", "error", "degraded", "stopped", "missing", "inactive"}:
            return False
        return None

    @staticmethod
    def _guard_state(guard_health: dict[str, Any]) -> dict[str, Any]:
        guard = _as_dict(guard_health)
        if not guard:
            return {"state": "unknown", "ok": None, "info": "guard health unavailable"}
        status = str(guard.get("status") or guard.get("state") or "").strip().lower()
        ok_value = guard.get("ok") if "ok" in guard else None
        running = guard.get("running") if "running" in guard else None
        if ok_value is True or running is True or status in {"ok", "ready", "healthy", "running", "active"}:
            state = "running"
            ok = True
        elif status in {"stopped", "inactive", "not_running"} or running is False:
            state = "stopped"
            ok = False
        elif ok_value is False or status in {"failed", "error", "degraded"}:
            state = "degraded"
            ok = False
        else:
            state = status or "unknown"
            ok = None
        return {
            "state": state,
            "ok": ok,
            "info": _safe_text(guard.get("info") or guard.get("detail") or status or state),
        }

    @staticmethod
    def _queue_summary(queue_pressure: dict[str, Any]) -> dict[str, Any]:
        queue = _as_dict(queue_pressure)
        next_item = _as_dict(queue.get("next_item"))
        return {
            "status": _safe_text(queue.get("status")).lower(),
            "count": _as_int(queue.get("count")),
            "open_count": _as_int(queue.get("open_count")),
            "actionable_count": _as_int(queue.get("actionable_count")),
            "blocked_count": _as_int(queue.get("blocked_count")),
            "drift_count": _as_int(queue.get("drift_count")),
            "warning_count": _as_int(queue.get("warning_count")),
            "never_run_count": _as_int(queue.get("never_run_count")),
            "next_item": _compact_value(next_item),
        }

    @staticmethod
    def _work_tree_summary(work_tree_state: dict[str, Any]) -> dict[str, Any]:
        work_tree = _as_dict(work_tree_state)
        counts = _as_dict(work_tree.get("counts"))
        trees: list[dict[str, Any]] = []
        for item in _as_list(work_tree.get("trees"))[:32]:
            tree = _as_dict(item)
            if not tree:
                continue
            tree_counts = _as_dict(tree.get("counts"))
            trees.append(
                {
                    "tree_id": _safe_text(tree.get("tree_id"), 80),
                    "kind": _safe_text(tree.get("kind"), 80).lower(),
                    "status": _safe_text(tree.get("status"), 80).lower(),
                    "title": _safe_text(tree.get("title"), 160),
                    "active_branch_id": _safe_text(tree.get("active_branch_id"), 80),
                    "counts": _compact_value(tree_counts),
                }
            )
        return {
            "ok": bool(work_tree.get("ok", True)),
            "status": _safe_text(work_tree.get("status")).lower(),
            "counts": {
                "total": _as_int(counts.get("total")),
                "active": _as_int(counts.get("active")),
                "branches": _as_int(counts.get("branches")),
                "open_tasks": _as_int(counts.get("open_tasks")),
                "working": _as_int(counts.get("working")),
                "pending": _as_int(counts.get("pending")),
                "blocked": _as_int(counts.get("blocked")),
                "complete": _as_int(counts.get("complete")),
            },
            "trees": trees,
        }

    @staticmethod
    def _ownership_summary(ownership_hints: Any, queue_pressure: dict[str, Any]) -> dict[str, Any]:
        hints = _as_list(ownership_hints)
        queue = _as_dict(queue_pressure)
        next_item = _as_dict(queue.get("next_item"))
        payload = _as_dict(next_item.get("payload"))
        if payload:
            preferred_owner = _safe_text(payload.get("preferred_owner"))
            route_hint = _safe_text(payload.get("route_hint"))
            review_contract = _safe_text(payload.get("review_contract"))
            if preferred_owner or route_hint or review_contract:
                return {
                    "source": "generated_queue.next_item",
                    "preferred_owner": preferred_owner,
                    "route_hint": route_hint,
                    "review_contract": review_contract,
                }
        for item in hints:
            hint = _as_dict(item)
            if not hint:
                continue
            return {
                "source": _safe_text(hint.get("source") or "ownership_hints"),
                "preferred_owner": _safe_text(hint.get("preferred_owner")),
                "route_hint": _safe_text(hint.get("route_hint")),
                "review_contract": _safe_text(hint.get("review_contract")),
            }
        return {}

    def _evidence_snapshot(
        self,
        *,
        core_steward: dict[str, Any],
        work_tree_state: dict[str, Any],
        queue_pressure: dict[str, Any],
        guard_health: dict[str, Any],
        runtime_health: dict[str, Any],
        ownership_hints: Any,
        posture_threshold: int,
    ) -> dict[str, Any]:
        steward = _as_dict(core_steward)
        steward_runtime = _as_dict(steward.get("runtime"))
        runtime = dict(steward_runtime)
        explicit_runtime = _as_dict(runtime_health)
        if explicit_runtime:
            runtime = {**runtime, **explicit_runtime}

        heartbeat = _as_dict(runtime.get("heartbeat"))
        core_state = _as_dict(runtime.get("core_state"))
        ollama = _as_dict(runtime.get("ollama"))
        autonomy = _as_dict(steward.get("autonomy_maintenance"))
        pulse = _as_dict(steward.get("pulse"))
        work_tree = self._work_tree_summary(work_tree_state)
        queue = self._queue_summary(queue_pressure)
        guard = self._guard_state(guard_health)
        conflicts = self._evidence_conflicts(
            steward=steward,
            work_tree=work_tree,
            queue=queue,
            heartbeat=_as_dict(steward_runtime.get("heartbeat")),
            core_state=_as_dict(steward_runtime.get("core_state")),
            explicit_runtime=explicit_runtime,
        )

        return {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "posture": {
                "score": _as_int(steward.get("score")),
                "level": _safe_text(steward.get("level")).lower() or "unknown",
                "threshold": int(posture_threshold),
                "summary": _safe_text(steward.get("summary"), 500),
            },
            "runtime": {
                "heartbeat": {
                    "ok": self._runtime_ok(heartbeat),
                    "info": _safe_text(heartbeat.get("info") or heartbeat.get("status") or heartbeat.get("state")),
                },
                "core_state": {
                    "ok": self._runtime_ok(core_state),
                    "info": _safe_text(core_state.get("info") or core_state.get("status") or core_state.get("state")),
                },
                "ollama": {
                    "ok": self._runtime_ok(ollama),
                    "info": _safe_text(ollama.get("info") or ollama.get("status") or ollama.get("state")),
                },
            },
            "guard": guard,
            "work_tree": work_tree,
            "queue_pressure": queue,
            "ownership": self._ownership_summary(ownership_hints, queue_pressure),
            "autonomy_maintenance": {
                "worker_status": _safe_text(autonomy.get("worker_status")).lower() or "unknown",
                "last_completed_at": _safe_text(autonomy.get("last_completed_at")),
            },
            "pulse": {
                "fallback_overuse_score": _as_float(pulse.get("fallback_overuse_score")),
                "approved_eligible_previews": _as_int(pulse.get("approved_eligible_previews")),
            },
            "conflicts": conflicts,
        }

    @staticmethod
    def _evidence_conflicts(
        *,
        steward: dict[str, Any],
        work_tree: dict[str, Any],
        queue: dict[str, Any],
        heartbeat: dict[str, Any],
        core_state: dict[str, Any],
        explicit_runtime: dict[str, Any],
    ) -> list[str]:
        conflicts: list[str] = []
        posture_score = _as_int(steward.get("score"))
        posture_level = _safe_text(steward.get("level")).lower()
        if posture_level == "strong" and posture_score < 85:
            conflicts.append("posture_level_strong_but_score_below_strong_floor")
        if queue["status"] in {"clear", "empty", "ok"} and queue["actionable_count"] > 0:
            conflicts.append("queue_reports_clear_with_actionable_items")
        if queue["open_count"] >= 0 and queue["actionable_count"] > queue["open_count"]:
            conflicts.append("queue_actionable_count_exceeds_open_count")
        counts = _as_dict(work_tree.get("counts"))
        if counts.get("active", 0) > counts.get("total", 0) and counts.get("total", 0) > 0:
            conflicts.append("work_tree_active_count_exceeds_total_count")
        if not bool(work_tree.get("ok", True)) and counts.get("active", 0) > 0:
            conflicts.append("work_tree_error_with_active_counts")

        explicit_heartbeat = _as_dict(explicit_runtime.get("heartbeat"))
        explicit_core = _as_dict(explicit_runtime.get("core_state"))
        if explicit_heartbeat and "ok" in explicit_heartbeat and "ok" in heartbeat:
            if bool(explicit_heartbeat.get("ok")) != bool(heartbeat.get("ok")):
                conflicts.append("heartbeat_evidence_disagrees")
        if explicit_core and "ok" in explicit_core and "ok" in core_state:
            if bool(explicit_core.get("ok")) != bool(core_state.get("ok")):
                conflicts.append("core_state_evidence_disagrees")
        return conflicts

    @staticmethod
    def _candidate(
        *,
        act: str,
        source: str,
        priority: int,
        reason: str,
        payload: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "act": act,
            "source": source,
            "priority": int(priority),
            "reason": reason,
            "payload": dict(payload or {}),
            "evidence": _compact_value(dict(evidence or {})),
            "status": "candidate",
            "rejection_reason": "",
        }

    def _candidate_actions(self, evidence: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        guard = _as_dict(evidence.get("guard"))
        queue = _as_dict(evidence.get("queue_pressure"))
        autonomy = _as_dict(evidence.get("autonomy_maintenance"))
        pulse = _as_dict(evidence.get("pulse"))

        if guard.get("state") == "stopped":
            candidates.append(
                self._candidate(
                    act="guard_start",
                    source="guard_health",
                    priority=10,
                    reason="Guard is stopped; restore the guard before allowing higher autonomy.",
                    evidence=guard,
                )
            )

        worker_status = str(autonomy.get("worker_status") or "").strip().lower()
        if worker_status not in {"running", "ok"}:
            candidates.append(
                self._candidate(
                    act="autonomy_maintenance_start",
                    source="core_steward.autonomy_maintenance",
                    priority=20,
                    reason="Autonomy maintenance is not reporting an active running cycle.",
                    evidence=autonomy,
                )
            )

        actionable_count = _as_int(queue.get("actionable_count"))
        blocked_count = _as_int(queue.get("blocked_count"))
        if actionable_count > 0:
            candidates.append(
                self._candidate(
                    act="generated_queue_run_next",
                    source="generated_work_queue",
                    priority=30,
                    reason=f"Generated Work Queue has {actionable_count} actionable item(s).",
                    evidence={
                        "actionable_count": actionable_count,
                        "next_item": _as_dict(queue.get("next_item")),
                    },
                )
            )
        elif blocked_count > 0:
            candidates.append(
                self._candidate(
                    act="generated_queue_investigate",
                    source="generated_work_queue",
                    priority=40,
                    reason=f"Generated Work Queue has {blocked_count} blocked item(s) that need review.",
                    evidence={"blocked_count": blocked_count},
                )
            )

        approved_updates = _as_int(pulse.get("approved_eligible_previews"))
        if approved_updates > 0:
            candidates.append(
                self._candidate(
                    act="update_now_dry_run",
                    source="core_steward.pulse",
                    priority=50,
                    reason=f"{approved_updates} approved eligible preview(s) should be dry-run reviewed.",
                    evidence={"approved_eligible_previews": approved_updates},
                )
            )

        fallback_score = _as_float(pulse.get("fallback_overuse_score"))
        if fallback_score >= 0.75:
            candidates.append(
                self._candidate(
                    act="pulse_status",
                    source="core_steward.pulse",
                    priority=60,
                    reason=f"Fallback pressure is elevated at {fallback_score:.2f}.",
                    evidence={"fallback_overuse_score": fallback_score},
                )
            )

        return candidates

    @staticmethod
    def _active_work_count(evidence: dict[str, Any]) -> int:
        work_tree = _as_dict(evidence.get("work_tree"))
        counts = _as_dict(work_tree.get("counts"))
        fallback_count = _as_int(counts.get("active")) + _as_int(counts.get("working"))
        trees = [_as_dict(item) for item in _as_list(work_tree.get("trees")) if isinstance(item, dict)]
        if not trees:
            return fallback_count
        managed_kinds = {"patch_queue", "generated_queue", "signal_ingestion"}
        unmanaged_count = 0
        for tree in trees:
            status = str(tree.get("status") or "").strip().lower()
            active_branch_id = str(tree.get("active_branch_id") or "").strip()
            if status != "active" and not active_branch_id:
                continue
            kind = str(tree.get("kind") or "").strip().lower()
            if kind in managed_kinds:
                continue
            unmanaged_count += 1
        return unmanaged_count

    @staticmethod
    def _reject_candidates(candidates: list[dict[str, Any]], reason: str) -> None:
        for candidate in candidates:
            if candidate.get("status") == "selected":
                continue
            candidate["status"] = "rejected"
            candidate["rejection_reason"] = reason

    @staticmethod
    def _select_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
        ordered = sorted(candidates, key=lambda item: (int(item.get("priority", 1000) or 1000), str(item.get("act") or "")))
        selected = ordered[0] if ordered else {}
        if selected:
            selected["status"] = "selected"
            selected["rejection_reason"] = ""
        for candidate in ordered[1:]:
            candidate["status"] = "rejected"
            candidate["rejection_reason"] = "lower_priority_than_selected"
        return selected

    def _decide(self, evidence: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[str, str, dict[str, Any], list[str]]:
        rejection_reasons: list[str] = []
        posture = _as_dict(evidence.get("posture"))
        runtime = _as_dict(evidence.get("runtime"))
        guard = _as_dict(evidence.get("guard"))
        conflicts = [str(item) for item in _as_list(evidence.get("conflicts")) if str(item).strip()]

        if conflicts:
            reason = "Evidence conflicts were found; advisory cycle refused action."
            rejection_reasons.extend(conflicts)
            self._reject_candidates(candidates, "blocked_by_evidence_conflict")
            return DECISION_BLOCK_WITH_REASON, reason, {}, rejection_reasons

        score = _as_int(posture.get("score"))
        level = str(posture.get("level") or "unknown").strip().lower()
        threshold = _as_int(posture.get("threshold"), self.posture_threshold)
        if score < threshold or level in {"repair", "unknown", ""}:
            reason = f"Core posture is {level or 'unknown'} at {score}/100; threshold is {threshold}."
            rejection_reasons.append("posture_below_threshold")
            self._reject_candidates(candidates, "blocked_by_posture")
            return DECISION_BLOCK_WITH_REASON, reason, {}, rejection_reasons

        heartbeat_ok = _as_dict(runtime.get("heartbeat")).get("ok")
        core_state_ok = _as_dict(runtime.get("core_state")).get("ok")
        if heartbeat_ok is False or core_state_ok is False:
            reason = "Core runtime health is degraded; no autonomy action is allowed this cycle."
            rejection_reasons.append("core_runtime_degraded")
            self._reject_candidates(candidates, "blocked_by_core_runtime")
            return DECISION_BLOCK_WITH_REASON, reason, {}, rejection_reasons

        if guard.get("state") in {"degraded", "failed", "error"}:
            reason = "Guard health is degraded; no autonomy action is allowed this cycle."
            rejection_reasons.append("guard_degraded")
            self._reject_candidates(candidates, "blocked_by_guard_health")
            return DECISION_BLOCK_WITH_REASON, reason, {}, rejection_reasons

        if guard.get("state") == "unknown":
            reason = "Guard health is unavailable, so the advisory cycle deferred action."
            rejection_reasons.append("guard_health_unavailable")
            self._reject_candidates(candidates, "deferred_missing_guard_health")
            return DECISION_DEFER_WITH_REASON, reason, {}, rejection_reasons

        active_work_count = self._active_work_count(evidence)
        has_protective_guard_candidate = any(candidate.get("act") == "guard_start" for candidate in candidates)
        if active_work_count > 0 and not has_protective_guard_candidate:
            reason = f"Work Tree already has {active_work_count} active/working branch signal(s); no new action was selected."
            rejection_reasons.append("work_tree_already_active")
            self._reject_candidates(candidates, "deferred_active_work_tree")
            return DECISION_DEFER_WITH_REASON, reason, {}, rejection_reasons

        if not candidates:
            reason = "No maintenance candidate cleared the advisory scan."
            rejection_reasons.append("no_candidate_action")
            return DECISION_DEFER_WITH_REASON, reason, {}, rejection_reasons

        selected = self._select_candidate(candidates)
        action = {
            "act": str(selected.get("act") or "").strip(),
            "payload": dict(selected.get("payload") or {}),
            "source": str(selected.get("source") or "").strip(),
            "reason": str(selected.get("reason") or "").strip(),
        }
        return DECISION_RECOMMEND_ACTION, action["reason"], action, rejection_reasons

    def evaluate_cycle(
        self,
        *,
        core_steward: dict[str, Any],
        work_tree_state: dict[str, Any],
        queue_pressure: dict[str, Any] | None = None,
        guard_health: dict[str, Any] | None = None,
        runtime_health: dict[str, Any] | None = None,
        ownership_hints: Any = None,
        posture_threshold: int | None = None,
        record_ledger_fn: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        threshold = int(self.posture_threshold if posture_threshold is None else posture_threshold)
        evidence = self._evidence_snapshot(
            core_steward=core_steward,
            work_tree_state=work_tree_state,
            queue_pressure=queue_pressure or {},
            guard_health=guard_health or {},
            runtime_health=runtime_health or {},
            ownership_hints=ownership_hints,
            posture_threshold=threshold,
        )
        candidates = self._candidate_actions(evidence)
        decision, reason, action, rejection_reasons = self._decide(evidence, candidates)
        if decision not in ALLOWED_DECISIONS:
            decision = DECISION_BLOCK_WITH_REASON
            reason = "Invalid autonomy decision was blocked by the decision contract."
            action = {}
            rejection_reasons = ["invalid_decision_contract"]
            self._reject_candidates(candidates, "blocked_invalid_decision_contract")

        ledger_row = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "services.autonomy_orchestrator",
            "mode": "advisory",
            "decision": decision,
            "reason": reason,
            "action": dict(action),
            "evidence": _compact_value(evidence),
            "candidate_actions": _compact_value(candidates),
            "rejection_reasons": list(rejection_reasons),
        }
        ledger_status = "not_requested"
        if record_ledger_fn is not None:
            try:
                record_ledger_fn(dict(ledger_row))
                ledger_status = "recorded"
            except Exception as exc:
                ledger_status = f"record_failed:{exc}"

        return {
            "mode": "advisory",
            "decision": decision,
            "reason": reason,
            "action": dict(action),
            "evidence": ledger_row["evidence"],
            "candidate_actions": ledger_row["candidate_actions"],
            "rejection_reasons": list(rejection_reasons),
            "ledger": {
                "status": ledger_status,
                "row": ledger_row,
            },
        }


AUTONOMY_ORCHESTRATOR_SERVICE = AutonomyOrchestratorService()
