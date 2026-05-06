import unittest

from services.autonomy_orchestrator import (
    ALLOWED_DECISIONS,
    AUTONOMY_ORCHESTRATOR_SERVICE,
    AutonomyOrchestratorService,
    DECISION_BLOCK_WITH_REASON,
    DECISION_DEFER_WITH_REASON,
    DECISION_RECOMMEND_ACTION,
    SPEC_DECISION_BLOCK,
    SPEC_DECISION_DEFER,
    SPEC_DECISION_RECOMMEND_ACTION,
)
from services.nova_control_action_dispatcher import autonomy_advisory_action_types


def _core_steward(
    *,
    score=100,
    level="strong",
    worker_status="running",
    fallback_overuse_score=0.0,
    approved_eligible_previews=0,
):
    return {
        "score": score,
        "level": level,
        "summary": "core surfaces look stable",
        "runtime": {
            "heartbeat": {"ok": True, "info": "heartbeat ok"},
            "core_state": {"ok": True, "info": "core state ok"},
            "ollama": {"ok": True, "info": "ollama ok"},
        },
        "autonomy_maintenance": {
            "worker_status": worker_status,
            "last_completed_at": "2026-05-06 12:00:00",
        },
        "pulse": {
            "fallback_overuse_score": fallback_overuse_score,
            "approved_eligible_previews": approved_eligible_previews,
        },
    }


def _work_tree(*, active=0, working=0, total=0):
    return {
        "ok": True,
        "counts": {
            "total": total,
            "active": active,
            "branches": active + working,
            "open_tasks": active + working,
            "working": working,
            "pending": 0,
            "blocked": 0,
            "complete": 0,
        },
        "trees": [],
    }


def _queue(*, status="ready", open_count=0, actionable_count=0, blocked_count=0, next_item=None):
    return {
        "status": status,
        "count": open_count,
        "open_count": open_count,
        "actionable_count": actionable_count,
        "blocked_count": blocked_count,
        "next_item": next_item or {},
    }


def _guard(**overrides):
    payload = {"ok": True, "running": True, "status": "running", "info": "guard running"}
    payload.update(overrides)
    return payload


def _spec_envelope(
    *,
    policy=None,
    queue=None,
    runtime=None,
    posture=None,
    work_tree=None,
    triage=None,
    last_action=None,
):
    return {
        "cycle_id": "cycle-test-001",
        "timestamp_utc": "2026-05-06T12:00:00Z",
        "work_tree_snapshot": {
            "open_count": 0,
            "working_count": 0,
            "blocked_count": 0,
            "stale_count": 0,
            "oldest_open_age_min": 0,
            "branches": [],
            "source_freshness_sec": 0,
            **(work_tree or {}),
        },
        "steward_posture": {
            "health_score": 96,
            "alert_count": 0,
            "critical_alerts": 0,
            "pass_ratio": 0.96,
            "posture_band": "green",
            "source_freshness_sec": 0,
            **(posture or {}),
        },
        "queue_pressure": {
            "pending_count": 0,
            "aging_items_count": 0,
            "high_priority_count": 0,
            "pressure_band": "low",
            "source_freshness_sec": 0,
            **(queue or {}),
        },
        "runtime_guard_status": {
            "guard_running": True,
            "core_running": True,
            "webui_running": True,
            "restart_in_progress": False,
            "stop_flag": False,
            "source_freshness_sec": 0,
            **(runtime or {}),
        },
        "policy_snapshot": {
            "autonomy_enabled": True,
            "allowed_actions": list(autonomy_advisory_action_types()),
            "blocked_actions": [],
            "quiet_hours_active": False,
            "requires_operator_ack_for": ["update_now_dry_run"],
            "source_freshness_sec": 0,
            **(policy or {}),
        },
        "triage_hints": {
            "likely_owner_by_branch": {},
            "seam_pressure_scores": {},
            "confidence": 0.6,
            "source_freshness_sec": 0,
            **(triage or {}),
        },
        "last_action_context": {
            "last_action_type": "",
            "last_action_at_utc": "",
            "cooldown_active": False,
            "cooldown_remaining_sec": 0,
            "last_result": "unknown",
            "source_freshness_sec": 0,
            **(last_action or {}),
        },
    }


class TestAutonomyOrchestratorService(unittest.TestCase):
    def test_evaluate_next_action_recommends_single_spec_action_and_records_ledger(self):
        service = AutonomyOrchestratorService()
        ledger_rows = []

        packet = service.evaluate_next_action(
            _spec_envelope(queue={"pending_count": 3, "high_priority_count": 1, "pressure_band": "high"}),
            record_ledger_fn=ledger_rows.append,
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["decision"], DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["action_type"], "generated_queue_run_next")
        self.assertEqual(packet["action"]["act"], "generated_queue_run_next")
        self.assertGreater(packet["confidence"], 0.55)
        self.assertEqual(packet["ledger"]["status"], "recorded")
        self.assertEqual(len(ledger_rows), 1)
        self.assertEqual(ledger_rows[0]["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertIn("recommended_action_summary", ledger_rows[0])
        self.assertIn("candidates_considered", ledger_rows[0])
        self.assertEqual(service.get_last_decision()["cycle_id"], "cycle-test-001")
        self.assertEqual(len(service.get_decision_history(limit=5)), 1)
        self.assertEqual(service.get_health()["cycle_count"], 1)

    def test_evaluate_next_action_only_recommends_dispatcher_owned_action(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(queue={"pending_count": 3, "high_priority_count": 1, "pressure_band": "high"})
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertIn(packet["recommended_action"]["action_type"], autonomy_advisory_action_types())

    def test_evaluate_next_action_blocks_when_policy_disables_autonomy(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                policy={"autonomy_enabled": False},
                queue={"pending_count": 1, "pressure_band": "medium"},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_BLOCK)
        self.assertEqual(packet["decision"], DECISION_BLOCK_WITH_REASON)
        self.assertIn("policy_autonomy_disabled", packet["refusal_reasons"])
        self.assertIsNone(packet["recommended_action"])

    def test_evaluate_next_action_defers_when_runtime_evidence_is_stale(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                runtime={"source_freshness_sec": 121},
                queue={"pending_count": 1, "pressure_band": "medium"},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("runtime_evidence_stale", packet["refusal_reasons"])

    def test_evaluate_next_action_blocks_disallowed_candidate(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                policy={"allowed_actions": ["guard_start"]},
                queue={"pending_count": 1, "pressure_band": "medium"},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_BLOCK)
        self.assertIn("action_not_allowed", packet["refusal_reasons"])

    def test_evaluate_next_action_defers_when_ack_required(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                queue={"approved_eligible_previews": 1},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("operator_ack_required", packet["refusal_reasons"])

    def test_evaluate_next_action_defers_for_active_cooldown(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                queue={"pending_count": 1, "pressure_band": "medium"},
                last_action={
                    "last_action_type": "generated_queue_run_next",
                    "cooldown_active": True,
                    "cooldown_remaining_sec": 90,
                },
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("cooldown_active", packet["refusal_reasons"])

    def test_set_mode_keeps_execution_policy_guarded(self):
        service = AutonomyOrchestratorService()

        blocked = service.set_mode("execute", {"autonomy_enabled": True})
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["mode"], "advisory")
        allowed = service.set_mode("execute", {"autonomy_enabled": True, "allow_execute_mode": True})
        self.assertTrue(allowed["ok"])
        self.assertEqual(service.get_health()["mode"], "execute")

    def test_recommends_next_generated_queue_action_and_records_ledger(self):
        ledger_rows = []

        packet = AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_cycle(
            core_steward=_core_steward(),
            work_tree_state=_work_tree(),
            queue_pressure=_queue(
                open_count=2,
                actionable_count=1,
                next_item={
                    "title": "Weather continuation review",
                    "payload": {
                        "preferred_owner": "supervisor",
                        "route_hint": "supervisor_owned",
                        "review_contract": "subconscious.review.supervisor",
                    },
                },
            ),
            guard_health=_guard(),
            record_ledger_fn=ledger_rows.append,
        )

        self.assertEqual(packet["decision"], DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["action"]["act"], "generated_queue_run_next")
        self.assertEqual(packet["mode"], "advisory")
        self.assertEqual(packet["ledger"]["status"], "recorded")
        self.assertEqual(len(ledger_rows), 1)
        self.assertIn("evidence", ledger_rows[0])
        self.assertIn("candidate_actions", ledger_rows[0])
        self.assertEqual((packet["evidence"]["ownership"] or {}).get("preferred_owner"), "supervisor")

    def test_blocks_when_posture_is_below_threshold(self):
        packet = AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_cycle(
            core_steward=_core_steward(score=70, level="watch"),
            work_tree_state=_work_tree(),
            queue_pressure=_queue(open_count=1, actionable_count=1),
            guard_health=_guard(),
        )

        self.assertEqual(packet["decision"], DECISION_BLOCK_WITH_REASON)
        self.assertEqual(packet["action"], {})
        self.assertIn("posture_below_threshold", packet["rejection_reasons"])
        self.assertEqual(packet["candidate_actions"][0]["rejection_reason"], "blocked_by_posture")

    def test_blocks_when_evidence_conflicts(self):
        packet = AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_cycle(
            core_steward=_core_steward(),
            work_tree_state=_work_tree(),
            queue_pressure=_queue(status="clear", open_count=1, actionable_count=1),
            guard_health=_guard(),
        )

        self.assertEqual(packet["decision"], DECISION_BLOCK_WITH_REASON)
        self.assertIn("queue_reports_clear_with_actionable_items", packet["rejection_reasons"])
        self.assertEqual(packet["candidate_actions"][0]["rejection_reason"], "blocked_by_evidence_conflict")

    def test_blocks_when_runtime_evidence_disagrees(self):
        packet = AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_cycle(
            core_steward=_core_steward(),
            work_tree_state=_work_tree(),
            queue_pressure=_queue(open_count=1, actionable_count=1),
            guard_health=_guard(),
            runtime_health={"heartbeat": {"ok": False, "info": "explicit probe failed"}},
        )

        self.assertEqual(packet["decision"], DECISION_BLOCK_WITH_REASON)
        self.assertIn("heartbeat_evidence_disagrees", packet["rejection_reasons"])

    def test_defers_when_work_tree_is_already_active(self):
        packet = AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_cycle(
            core_steward=_core_steward(),
            work_tree_state=_work_tree(total=1, active=1),
            queue_pressure=_queue(open_count=1, actionable_count=1),
            guard_health=_guard(),
        )

        self.assertEqual(packet["decision"], DECISION_DEFER_WITH_REASON)
        self.assertIn("work_tree_already_active", packet["rejection_reasons"])
        self.assertEqual(packet["candidate_actions"][0]["rejection_reason"], "deferred_active_work_tree")

    def test_managed_generated_queue_tree_does_not_block_queue_recommendation(self):
        packet = AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_cycle(
            core_steward=_core_steward(),
            work_tree_state={
                "ok": True,
                "counts": {"total": 1, "active": 1, "branches": 1, "open_tasks": 1, "working": 0},
                "trees": [
                    {
                        "tree_id": "tree_generated",
                        "kind": "generated_queue",
                        "status": "active",
                        "active_branch_id": "branch_generated",
                        "title": "Generated Queue: governed self-repair",
                    }
                ],
            },
            queue_pressure=_queue(open_count=1, actionable_count=1),
            guard_health=_guard(),
        )

        self.assertEqual(packet["decision"], DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["action"]["act"], "generated_queue_run_next")

    def test_defers_when_guard_health_is_missing(self):
        packet = AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_cycle(
            core_steward=_core_steward(),
            work_tree_state=_work_tree(),
            queue_pressure=_queue(open_count=1, actionable_count=1),
        )

        self.assertEqual(packet["decision"], DECISION_DEFER_WITH_REASON)
        self.assertIn("guard_health_unavailable", packet["rejection_reasons"])
        self.assertEqual(packet["action"], {})

    def test_recommends_guard_start_when_guard_is_stopped(self):
        packet = AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_cycle(
            core_steward=_core_steward(),
            work_tree_state=_work_tree(),
            queue_pressure=_queue(),
            guard_health={"running": False, "status": "stopped"},
        )

        self.assertEqual(packet["decision"], DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["action"]["act"], "guard_start")

    def test_recommends_maintenance_worker_start_when_worker_is_stopped(self):
        packet = AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_cycle(
            core_steward=_core_steward(score=95, level="watch", worker_status="stopped"),
            work_tree_state=_work_tree(),
            queue_pressure=_queue(),
            guard_health=_guard(),
        )

        self.assertEqual(packet["decision"], DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["action"]["act"], "autonomy_maintenance_start")

    def test_recommends_investigation_for_blocked_queue(self):
        packet = AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_cycle(
            core_steward=_core_steward(),
            work_tree_state=_work_tree(),
            queue_pressure=_queue(status="blocked", open_count=2, blocked_count=2),
            guard_health=_guard(),
        )

        self.assertEqual(packet["decision"], DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["action"]["act"], "generated_queue_investigate")

    def test_decision_contract_only_emits_allowed_decisions(self):
        packets = [
            AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_cycle(
                core_steward=_core_steward(),
                work_tree_state=_work_tree(),
                queue_pressure=_queue(),
                guard_health=_guard(),
            ),
            AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_cycle(
                core_steward=_core_steward(score=60, level="repair"),
                work_tree_state=_work_tree(),
                queue_pressure=_queue(open_count=1, actionable_count=1),
                guard_health=_guard(),
            ),
        ]

        self.assertEqual(packets[0]["decision"], DECISION_DEFER_WITH_REASON)
        for packet in packets:
            self.assertIn(packet["decision"], ALLOWED_DECISIONS)


if __name__ == "__main__":
    unittest.main()
