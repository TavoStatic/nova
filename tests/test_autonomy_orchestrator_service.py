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

    def test_evaluate_next_action_recommends_patch_queue_conduit_when_patch_ready(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                queue={
                    "pending_count": 1,
                    "high_priority_count": 1,
                    "pressure_band": "high",
                    "generated_pending_count": 0,
                    "generated_actionable_count": 0,
                    "patch_apply_ready_count": 1,
                    "patch_approve_ready_count": 0,
                    "patch_ready_count": 1,
                }
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["action_type"], "patch_queue_run_next")
        self.assertEqual(packet["recommended_action"]["execution_group"], "patch_queue")

    def test_evaluate_next_action_scores_generated_queue_with_triage_lane_pressure(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                queue={
                    "pending_count": 1,
                    "high_priority_count": 1,
                    "pressure_band": "medium",
                    "generated_pending_count": 1,
                    "generated_actionable_count": 1,
                },
                triage={
                    "lane_pressure_scores": {"generated_queue": 0.97},
                    "owner_pressure_scores": {"supervisor": 0.97},
                    "review_contract_pressure_scores": {"subconscious.review.supervisor": 0.97},
                    "seam_pressure_scores": {"weather_continuation_route_fallthrough": 0.97},
                    "top_triage_candidates": [
                        {
                            "family_id": "weather-continuation-fallthrough-family",
                            "target_seam": "weather_continuation_route_fallthrough",
                            "signal": "fallback_overuse",
                            "preferred_owner": "supervisor",
                            "route_hint": "supervisor_owned",
                            "review_contract": "subconscious.review.supervisor",
                            "lane": "generated_queue",
                            "robustness": 0.97,
                            "approved": True,
                        }
                    ],
                    "approved_review_count": 1,
                    "confidence": 0.97,
                    "source": "subconscious_work_tree_triage",
                },
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["action_type"], "generated_queue_run_next")
        self.assertIn("weather_continuation_route_fallthrough", packet["recommended_action"]["expected_effect"])
        evidence_triage = packet["evidence"]["triage_hints"]
        self.assertEqual(evidence_triage["approved_review_count"], 1)
        self.assertEqual(evidence_triage["source"], "subconscious_work_tree_triage")
        selected = next(
            item for item in packet["candidates_considered"]
            if (item.get("action") or {}).get("action_type") == "generated_queue_run_next"
        )
        self.assertEqual(selected.get("source"), "queue_pressure+triage_hints")
        self.assertEqual((selected.get("triage_focus") or {}).get("preferred_owner"), "supervisor")
        self.assertGreater((selected.get("score_components") or {}).get("triage_lane_pressure_bonus"), 0.0)

    def test_evaluate_next_action_recommends_active_work_tree_conduit(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                work_tree={
                    "open_count": 1,
                    "branches": [
                        {
                            "branch_id": "branch-active",
                            "title": "Core thinning follow-up",
                            "status": "active",
                            "owner": "core_thinning",
                            "age_min": 4,
                            "recommended_tool": "core_thinning",
                            "executable": True,
                        }
                    ],
                }
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["action_type"], "active_work_tree_run_next")
        self.assertEqual(packet["recommended_action"]["execution_group"], "active_work_tree")
        self.assertEqual(packet["recommended_action"]["target_id"], "branch-active")

    def test_evaluate_next_action_recommends_concrete_active_work_tree_in_watch_posture(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                posture={"health_score": 89, "pass_ratio": 0.89, "posture_band": "yellow"},
                work_tree={
                    "open_count": 2,
                    "active_candidate_count": 1,
                    "active_executable_count": 1,
                    "active_unsafe_count": 0,
                    "branches": [
                        {
                            "branch_id": "branch-memory",
                            "title": "Investigate memory persistence bootstrap gap",
                            "status": "ready",
                            "owner": "signal_ingestion",
                            "recommended_tool": "system_check",
                            "executable": True,
                        }
                    ],
                },
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["action_type"], "active_work_tree_run_next")
        self.assertEqual(packet["policy_checks"]["recommendation_threshold"], "concrete_active_work_tree")
        self.assertIn("Investigate memory persistence bootstrap gap", packet["recommended_action"]["expected_effect"])
        self.assertEqual(packet["recommended_action"]["target_id"], "branch-memory")
        self.assertEqual(packet["recommended_action"]["cooldown_sec"], 0)

    def test_active_work_tree_cooldown_is_branch_aware_for_evidence_steps(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                work_tree={
                    "open_count": 1,
                    "active_candidate_count": 1,
                    "active_executable_count": 1,
                    "branches": [
                        {
                            "branch_id": "branch-new",
                            "title": "Read release ledger for current package",
                            "status": "ready",
                            "owner": "signal_ingestion",
                            "recommended_tool": "read",
                            "executable": True,
                        }
                    ],
                },
                last_action={
                    "last_action_type": "active_work_tree_run_next",
                    "last_target_id": "branch-old",
                    "cooldown_active": True,
                    "cooldown_remaining_sec": 90,
                },
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["target_id"], "branch-new")
        self.assertEqual(packet["recommended_action"]["cooldown_sec"], 0)
        self.assertNotIn("cooldown_active", packet["refusal_reasons"])

    def test_active_work_tree_cooldown_is_task_aware_within_same_branch(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                work_tree={
                    "open_count": 1,
                    "active_candidate_count": 1,
                    "active_executable_count": 1,
                    "branches": [
                        {
                            "branch_id": "branch-release",
                            "title": "Release package is verified but validation outcome is missing",
                            "status": "ready",
                            "owner": "signal_ingestion",
                            "task_id": "task-promotion",
                            "task_title": "Run release promotion judgment from validation evidence",
                            "recommended_tool": "release_promotion_judgment",
                            "executable": True,
                        }
                    ],
                },
                last_action={
                    "last_action_type": "active_work_tree_run_next",
                    "last_target_id": "branch-release",
                    "last_target_step_id": "task-validation",
                    "cooldown_active": True,
                    "cooldown_remaining_sec": 90,
                },
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["target_id"], "branch-release")
        self.assertEqual(packet["recommended_action"]["target_step_id"], "task-promotion")
        self.assertNotIn("cooldown_active", packet["refusal_reasons"])

    def test_evaluate_next_action_prefers_concrete_active_lane_over_pulse(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                work_tree={
                    "open_count": 36,
                    "blocked_count": 37,
                    "active_candidate_count": 2,
                    "active_executable_count": 1,
                    "active_unsafe_count": 1,
                    "branches": [
                        {
                            "branch_id": "branch-core",
                            "title": "Review wrapper shim",
                            "status": "active",
                            "owner": "core_thinning",
                            "recommended_tool": "core_thinning",
                            "executable": True,
                        }
                    ],
                },
                triage={
                    "seam_pressure_scores": {"fallback_overuse": 0.97},
                    "lane_pressure_scores": {"generated_queue": 0.97},
                    "top_triage_candidates": [
                        {
                            "target_seam": "fulfillment_bridge_entry_fallthrough",
                            "signal": "fallback_overuse",
                            "preferred_owner": "fulfillment",
                            "lane": "generated_queue",
                            "robustness": 0.97,
                            "approved": True,
                        }
                    ],
                    "confidence": 0.97,
                    "source": "subconscious_work_tree_triage",
                },
                last_action={
                    "last_action_type": "generated_queue_run_next",
                    "cooldown_active": True,
                    "cooldown_remaining_sec": 90,
                },
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["action_type"], "active_work_tree_run_next")
        action_types = [
            (item.get("action") or {}).get("action_type")
            for item in packet["candidates_considered"]
        ]
        self.assertNotIn("pulse_status", action_types)
        self.assertEqual(packet["evidence"]["work_tree_snapshot"]["active_executable_count"], 1)

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

    def test_operator_hold_does_not_turn_into_generic_queue_investigation(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                work_tree={
                    "blocked_count": 1,
                    "observing_count": 1,
                    "operator_hold_count": 1,
                    "latent_root_signal_count": 0,
                },
                policy={"requires_operator_ack_for": ["generated_queue_investigate"]},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("operator_hold_pending", packet["refusal_reasons"])
        self.assertNotIn("operator_ack_required", packet["refusal_reasons"])
        self.assertEqual(packet["candidates_considered"], [])

    def test_blocked_observing_work_tree_does_not_become_generated_queue_ack_hold(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                work_tree={
                    "blocked_count": 1,
                    "observing_count": 1,
                    "operator_hold_count": 0,
                    "latent_root_signal_count": 0,
                    "active_executable_count": 0,
                },
                policy={"requires_operator_ack_for": ["generated_queue_investigate"]},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("work_tree_observing_root_truth", packet["refusal_reasons"])
        self.assertNotIn("operator_ack_required", packet["refusal_reasons"])
        self.assertEqual(packet["candidates_considered"], [])

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
