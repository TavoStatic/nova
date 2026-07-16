import unittest
from unittest.mock import patch

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


def _safe_action_type(candidate):
    action = candidate.get("action") if isinstance(candidate, dict) else {}
    return (action or {}).get("action_type") if isinstance(action, dict) else None


def _green_mission_snapshot(**overrides):
    payload = {
        "enabled": True,
        "mode": "steady_state_guard",
        "objective": "hold_steady_and_surface_fresh_gaps",
        "status": "green",
        "action": "hold",
        "green_cycle": True,
        "headline": "steady governance cycle; no fresh gap pressure",
        "truth_ready": True,
        "truth_blockers": [],
        "owner_blockers": [],
        "owner_verdicts": [],
        "blocking_owner_count": 0,
        "validation_fresh": True,
        "regression_current": True,
        "release_truth_current": True,
        "fresh_gap_signal_count": 0,
        "release_stale_ready_count": 0,
        "source": "services.nova_mission",
        "source_freshness_sec": 0,
    }
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
    autonomy=None,
    mission=None,
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
        "autonomy_maintenance": {
            "worker_status": "running",
            "worker_active": True,
            "worker_stale_identity": False,
            "scheduler_active": True,
            "scheduler_mode": "worker_loop",
            "scheduler_status": "running",
            "source_freshness_sec": 0,
            **(autonomy or {}),
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
        **(
            {"mission_snapshot": _green_mission_snapshot(**(mission or {}))}
            if mission is not None
            else {}
        ),
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

    def test_evaluate_next_action_recommends_maintenance_worker_start_from_worker_evidence(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                autonomy={
                    "worker_status": "stopped",
                    "worker_active": False,
                    "worker_stale_identity": False,
                    "scheduler_active": False,
                    "scheduler_mode": "inactive",
                    "scheduler_status": "inactive",
                }
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["action_type"], "autonomy_maintenance_start")
        self.assertEqual(packet["recommended_action"]["execution_group"], "runtime_control")
        self.assertEqual(packet["evidence"]["autonomy_maintenance"]["worker_status"], "stopped")

    def test_evaluate_next_action_does_not_start_worker_when_guard_scheduler_is_active(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                autonomy={
                    "worker_status": "stopped",
                    "worker_active": False,
                    "worker_stale_identity": False,
                    "scheduler_active": True,
                    "scheduler_mode": "guard_tick",
                    "scheduler_status": "guard_scheduled",
                }
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        action_types = [
            (item.get("action") or {}).get("action_type")
            for item in packet["candidates_considered"]
        ]
        self.assertNotIn("autonomy_maintenance_start", action_types)

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
        self.assertEqual(packet["policy_checks"]["autonomy_enabled"], "fail")
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
        self.assertEqual(packet["policy_checks"]["action_allowed"], "fail")

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

    def test_evaluate_next_action_prefers_investigate_when_pending_is_fully_blocked(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                queue={
                    "pending_count": 1,
                    "generated_pending_count": 1,
                    "generated_actionable_count": 0,
                    "generated_blocked_count": 1,
                    "pressure_band": "high",
                    "aging_items_count": 1,
                }
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["action_type"], "generated_queue_investigate")
        action_types = {
            (item.get("action") or {}).get("action_type")
            for item in packet["candidates_considered"]
        }
        self.assertNotIn("generated_queue_run_next", action_types)
        self.assertIn("generated_queue_investigate", action_types)

    def test_evaluate_next_action_blocks_when_posture_is_red(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                posture={"posture_band": "red", "critical_alerts": 0},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_BLOCK)
        self.assertIn("posture_red", packet["refusal_reasons"])
        self.assertEqual(packet["policy_checks"]["posture_band"], "fail")
        self.assertEqual(packet["policy_checks"]["critical_alerts"], "pass")

    def test_evaluate_next_action_blocks_when_critical_alert_is_active(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                posture={"posture_band": "green", "critical_alerts": 1},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_BLOCK)
        self.assertIn("critical_alert_active", packet["refusal_reasons"])
        self.assertEqual(packet["policy_checks"]["posture_band"], "pass")
        self.assertEqual(packet["policy_checks"]["critical_alerts"], "fail")

    def test_evaluate_next_action_defers_when_primary_evidence_is_stale(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                work_tree={"source_freshness_sec": 121},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("evidence_stale", packet["refusal_reasons"])
        self.assertEqual(packet["policy_checks"]["primary_sources_present"], "pass")
        self.assertEqual(packet["policy_checks"]["runtime_freshness"], "pass")
        self.assertEqual(packet["policy_checks"]["posture_freshness"], "pass")
        self.assertEqual(packet["policy_checks"]["primary_freshness"], "fail")

    def test_evaluate_next_action_defers_when_evidence_conflicts(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                posture={"posture_band": "green", "health_score": 70},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("evidence_conflict", packet["refusal_reasons"])
        self.assertIn("posture_green_but_health_score_below_green_floor", packet["refusal_reasons"])
        self.assertEqual(packet["policy_checks"]["runtime_known"], "pass")
        self.assertEqual(packet["policy_checks"]["evidence_conflict"], "fail")

    def test_evaluate_next_action_defers_when_no_legal_action_exists(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(_spec_envelope())

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("no_legal_action", packet["refusal_reasons"])
        self.assertEqual(packet["policy_checks"]["candidate_available"], "fail")
        self.assertEqual(packet["policy_checks"]["primary_sources_present"], "pass")

    def test_evaluate_next_action_holds_green_mission_over_seam_pressure_probe(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                triage={
                    "seam_pressure_scores": {"fallback_overuse": 0.97},
                    "confidence": 0.97,
                    "source": "subconscious_work_tree_triage",
                },
                mission={},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("mission_green_cycle_hold", packet["refusal_reasons"])
        self.assertEqual(packet["policy_checks"]["candidate_available"], "mission_hold")
        action_types = [
            _safe_action_type(item)
            for item in packet.get("candidates_considered") or []
        ]
        self.assertNotIn("pulse_status", action_types)
        self.assertTrue(bool((packet.get("evidence") or {}).get("mission_snapshot")))

    def test_evaluate_next_action_holds_green_mission_over_investigate_candidate(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                work_tree={"stale_count": 2},
                mission={},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("mission_green_cycle_hold", packet["refusal_reasons"])
        action_types = [
            _safe_action_type(item)
            for item in packet.get("candidates_considered") or []
        ]
        self.assertNotIn("generated_queue_investigate", action_types)

    def test_evaluate_next_action_holds_green_mission_over_generated_queue_run_next(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                queue={
                    "pending_count": 4,
                    "high_priority_count": 4,
                    "generated_pending_count": 4,
                    "generated_actionable_count": 4,
                    "pressure_band": "high",
                },
                triage={
                    "seam_pressure_scores": {"fallback_overuse": 0.97},
                    "confidence": 0.97,
                },
                mission={},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("mission_green_cycle_hold", packet["refusal_reasons"])
        action_types = [
            _safe_action_type(item)
            for item in packet.get("candidates_considered") or []
        ]
        self.assertNotIn("generated_queue_run_next", action_types)
        self.assertNotIn("pulse_status", action_types)

    def test_evaluate_next_action_holds_green_mission_over_active_work_tree_run_next(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                work_tree={
                    "active_executable_count": 1,
                    "branches": [
                        {
                            "branch_id": "branch_5e7dc5b7",
                            "title": "Release package is verified but validation outcome is missing",
                            "status": "ready",
                            "executable": True,
                            "recommended_tool": "read",
                            "task_id": "task_b9b95578",
                        }
                    ],
                },
                mission={},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("mission_green_cycle_hold", packet["refusal_reasons"])
        action_types = [
            _safe_action_type(item)
            for item in packet.get("candidates_considered") or []
        ]
        self.assertNotIn("active_work_tree_run_next", action_types)

    def test_evaluate_next_action_allows_core_thinning_under_green_mission_hold(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                work_tree={
                    "open_count": 1,
                    "active_executable_count": 1,
                    "branches": [
                        {
                            "branch_id": "branch-core-thin",
                            "title": "Core thinning follow-up",
                            "status": "active",
                            "owner": "core_thinning",
                            "age_min": 4,
                            "recommended_tool": "core_thinning",
                            "tree_id": "tree-core",
                            "executable": True,
                        }
                    ],
                },
                mission={},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["action_type"], "active_work_tree_run_next")
        self.assertEqual(packet["recommended_action"]["target_id"], "branch-core-thin")
        self.assertEqual(packet["recommended_action"]["recommended_tool"], "core_thinning")
        self.assertEqual(packet["recommended_action"]["target_tree_id"], "tree-core")
        self.assertEqual(packet["action"]["payload"]["target_tree_id"], "tree-core")
        self.assertEqual(packet["action"]["payload"]["recommended_tool"], "core_thinning")

    def test_evaluate_next_action_allows_core_thinning_when_release_drift_blocks_green(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                work_tree={
                    "open_count": 1,
                    "active_executable_count": 1,
                    "operator_hold_count": 0,
                    "branches": [
                        {
                            "branch_id": "branch-core-thin",
                            "title": "Core thinning follow-up",
                            "status": "active",
                            "owner": "core_thinning",
                            "age_min": 4,
                            "recommended_tool": "core_thinning",
                            "tree_id": "tree-core",
                            "executable": True,
                        }
                    ],
                },
                mission={
                    "enabled": True,
                    "mode": "steady_state_guard",
                    "status": "validation_required",
                    "action": "hold",
                    "green_cycle": False,
                    "truth_ready": False,
                    "truth_blockers": ["core_gate_release_drift"],
                    "green_blockers": [
                        {"owner": "layer_maturity", "code": "core_gate_release_drift"},
                    ],
                    "owner_verdicts": [
                        {
                            "owner": "release",
                            "ready": True,
                            "evidence": {
                                "runtime_drift_expected": True,
                                "runtime_drift_tolerated": True,
                            },
                        }
                    ],
                    "validation_fresh": True,
                    "regression_current": True,
                    "release_truth_current": True,
                    "core_gate": {"ok": False, "drift_blocked": True, "missing_roots": []},
                    "generated_queue_untested_count": 0,
                },
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["action_type"], "active_work_tree_run_next")
        self.assertEqual(packet["recommended_action"]["target_id"], "branch-core-thin")
        self.assertEqual(packet["recommended_action"]["recommended_tool"], "core_thinning")
        self.assertEqual(packet["recommended_action"]["target_tree_id"], "tree-core")
        self.assertEqual(packet["action"]["payload"]["target_tree_id"], "tree-core")
        self.assertEqual(packet["action"]["payload"]["recommended_tool"], "core_thinning")

    def test_evaluate_next_action_holds_green_mission_over_codegen_run(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                policy={
                    "layers": {
                        "codegen": {
                            "mode": "active",
                            "promoted_capabilities": ["autonomous_code_generation"],
                        },
                        "leah": {"mode": "observe", "promoted_capabilities": []},
                    }
                },
                work_tree={
                    "branches": [
                        {
                            "branch_id": "branch_codegen_gap",
                            "title": "Close capability gap: autonomous_code_generation",
                            "status": "ready",
                            "kind": "capability_gap",
                            "metadata": {"capability_name": "autonomous_code_generation"},
                            "source_payload": {
                                "primary_capability": "autonomous_code_generation",
                                "execution_group": "codegen",
                                "gaps": ["autonomous_code_generation"],
                            },
                        }
                    ],
                },
                mission={},
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        action_types = [
            _safe_action_type(item)
            for item in packet.get("candidates_considered") or []
        ]
        self.assertNotIn("codegen_run", action_types)

    def test_evaluate_next_action_holds_validation_required_mission_without_green_cycle(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                queue={
                    "pending_count": 4,
                    "high_priority_count": 4,
                    "generated_pending_count": 4,
                    "generated_actionable_count": 4,
                    "pressure_band": "high",
                },
                mission={
                    "green_cycle": False,
                    "status": "validation_required",
                    "action": "hold",
                    "truth_ready": False,
                    "truth_blockers": ["validation_truth_missing", "generated_queue_untested"],
                    "owner_blockers": [
                        {
                            "owner": "validation",
                            "code": "validation_truth_missing",
                            "source": "validation_artifact_truth",
                        },
                        {
                            "owner": "generated_queue",
                            "code": "generated_queue_untested",
                            "source": "generated_work_queue",
                        }
                    ],
                    "green_blockers": [
                        {
                            "owner": "validation",
                            "code": "validation_truth_missing",
                            "source": "validation_artifact_truth",
                        },
                        {
                            "owner": "generated_queue",
                            "code": "generated_queue_untested",
                            "source": "generated_work_queue",
                        },
                    ],
                    "validation_fresh": False,
                    "regression_current": True,
                    "release_truth_current": True,
                    "generated_queue_untested_count": 4,
                    "blocking_owner_count": 2,
                },
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("mission_steady_state_hold", packet["refusal_reasons"])
        self.assertIn("mission_validation_required_hold", packet["refusal_reasons"])
        self.assertIn("mission_truth_blocker:validation_truth_missing", packet["refusal_reasons"])
        self.assertIn("mission_truth_blocker:generated_queue_untested", packet["refusal_reasons"])
        self.assertIn(
            "mission_owner_blocker:validation:validation_truth_missing",
            packet["refusal_reasons"],
        )
        self.assertIn(
            "mission_owner_blocker:generated_queue:generated_queue_untested",
            packet["refusal_reasons"],
        )
        self.assertNotIn("mission_green_cycle_hold", packet["refusal_reasons"])
        action_types = [
            _safe_action_type(item)
            for item in packet.get("candidates_considered") or []
        ]
        self.assertNotIn("generated_queue_run_next", action_types)

    def test_evaluate_next_action_runs_generated_queue_to_clear_own_truth_blocker(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                queue={
                    "pending_count": 2,
                    "high_priority_count": 2,
                    "generated_pending_count": 2,
                    "generated_actionable_count": 2,
                    "generated_blocked_count": 0,
                    "pressure_band": "high",
                },
                work_tree={
                    "operator_hold_count": 2,
                    "blocked_count": 2,
                },
                mission={
                    "green_cycle": False,
                    "status": "validation_required",
                    "action": "hold",
                    "truth_ready": False,
                    "truth_blockers": ["generated_queue_untested", "core_gate_release_drift"],
                    "green_blockers": [
                        {
                            "owner": "generated_queue",
                            "code": "generated_queue_untested",
                            "source": "generated_work_queue",
                        },
                        {
                            "owner": "layer_maturity",
                            "code": "core_gate_release_drift",
                            "source": "layer_maturity.core_gate",
                        },
                    ],
                    "owner_verdicts": [
                        {
                            "owner": "release",
                            "ready": True,
                            "evidence": {
                                "runtime_drift_expected": True,
                                "runtime_drift_tolerated": True,
                            },
                        }
                    ],
                    "validation_fresh": True,
                    "regression_current": True,
                    "release_truth_current": True,
                    "generated_queue_untested_count": 2,
                    "core_gate": {"ok": False, "drift_blocked": True, "missing_roots": []},
                },
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["action_type"], "generated_queue_run_next")
        self.assertEqual(packet["recommended_action"]["target_id"], "generated_work_queue")
        self.assertNotIn("operator_hold_pending", packet["refusal_reasons"])

    def test_evaluate_next_action_runs_generated_queue_when_release_truth_stale_and_operator_hold(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                queue={
                    "pending_count": 2,
                    "high_priority_count": 2,
                    "generated_pending_count": 2,
                    "generated_actionable_count": 2,
                    "generated_blocked_count": 0,
                    "pressure_band": "high",
                },
                work_tree={
                    "operator_hold_count": 1,
                    "blocked_count": 1,
                },
                mission={
                    "green_cycle": False,
                    "status": "validation_required",
                    "action": "hold",
                    "truth_ready": False,
                    "truth_blockers": ["release_truth_stale", "generated_queue_untested"],
                    "green_blockers": [
                        {
                            "owner": "release",
                            "code": "release_truth_stale",
                            "remediation": {
                                "action": "active_work_tree_run_next",
                                "tools": ["release_rebuild_verify"],
                            },
                        },
                        {
                            "owner": "generated_queue",
                            "code": "generated_queue_untested",
                            "remediation": {"action": "generated_queue_run_next"},
                        },
                    ],
                    "validation_fresh": True,
                    "regression_current": True,
                    "release_truth_current": False,
                    "generated_queue_untested_count": 2,
                },
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["action_type"], "generated_queue_run_next")
        self.assertNotIn("operator_hold_pending", packet["refusal_reasons"])

    def test_evaluate_next_action_defers_below_recommendation_threshold(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(
                posture={"posture_band": "yellow", "health_score": 84},
                triage={
                    "seam_pressure_scores": {"pulse_gate": 0.75},
                    "confidence": 0.0,
                },
            )
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("below_recommendation_threshold", packet["refusal_reasons"])
        self.assertEqual(packet["policy_checks"]["candidate_available"], "pass")
        self.assertEqual(packet["policy_checks"]["action_allowed"], "pass")
        self.assertEqual(packet["policy_checks"]["recommendation_threshold"], "fail")

    def test_evaluate_next_action_defers_when_top_candidates_tie(self):
        service = AutonomyOrchestratorService()

        envelope = _spec_envelope(
            queue={
                "pending_count": 1,
                "high_priority_count": 1,
                "pressure_band": "high",
                "generated_pending_count": 1,
                "generated_actionable_count": 1,
                "patch_apply_ready_count": 1,
                "patch_approve_ready_count": 0,
                "patch_ready_count": 1,
            }
        )
        with patch.object(
            AutonomyOrchestratorService,
            "_score_contract_candidate",
            return_value=(0.6, {"urgency": 0.0}),
        ):
            packet = service.evaluate_next_action(envelope)

        self.assertEqual(packet["decision_type"], SPEC_DECISION_DEFER)
        self.assertIn("candidate_tie", packet["refusal_reasons"])
        self.assertEqual(packet["policy_checks"]["candidate_available"], "pass")
        self.assertEqual(packet["policy_checks"]["action_allowed"], "pass")

    def test_set_mode_keeps_execution_policy_guarded(self):
        service = AutonomyOrchestratorService()

        blocked = service.set_mode("execute", {"autonomy_enabled": True})
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["mode"], "advisory")
        allowed = service.set_mode("execute", {"autonomy_enabled": True, "allow_execute_mode": True})
        self.assertTrue(allowed["ok"])
        self.assertEqual(service.get_health()["mode"], "execute")


    def test_evaluate_next_action_recommends_guard_start_when_guard_not_running(self):
        service = AutonomyOrchestratorService()

        packet = service.evaluate_next_action(
            _spec_envelope(runtime={"guard_running": False, "core_running": True})
        )

        self.assertEqual(packet["decision_type"], SPEC_DECISION_RECOMMEND_ACTION)
        self.assertEqual(packet["recommended_action"]["action_type"], "guard_start")
        self.assertEqual(packet["recommended_action"]["execution_group"], "runtime_control")

    def test_evaluate_next_action_only_emits_allowed_spec_decisions(self):
        service = AutonomyOrchestratorService()
        envelopes = [
            _spec_envelope(),
            _spec_envelope(queue={"pending_count": 3, "pressure_band": "high"}),
            _spec_envelope(runtime={"guard_running": False, "core_running": True}),
            _spec_envelope(policy={"autonomy_enabled": False}),
        ]
        for envelope in envelopes:
            packet = service.evaluate_next_action(envelope)
            self.assertIn(
                packet["decision_type"],
                {SPEC_DECISION_RECOMMEND_ACTION, SPEC_DECISION_DEFER, SPEC_DECISION_BLOCK},
                msg=f"Unexpected decision_type: {packet['decision_type']}",
            )



if __name__ == "__main__":
    unittest.main()
