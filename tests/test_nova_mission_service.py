import unittest

from services.layer_maturity_policy import CORE_GATE_ROOT_IDS
from services.nova_mission import NOVA_MISSION_SERVICE, NovaMissionService


def _core_gate_inventory(*, ok: bool = True, missing: tuple[str, ...] = ()) -> dict:
    missing_set = set(missing)
    roots = []
    for root_id in CORE_GATE_ROOT_IDS:
        root_ok = ok and root_id not in missing_set
        roots.append({"root_id": root_id, "ok": root_ok, "gaps": [] if root_ok else ["missing_probe"]})
    return {
        "ok": ok and not missing_set,
        "gap_count": sum(0 if row["ok"] else 1 for row in roots),
        "roots": roots,
    }


def _truth_evidence(
    *,
    validation_ok=True,
    validation_status="ok",
    hidden_by_green_regression=False,
    regression_status="OK",
    regression_stale=False,
    release_identity="nyo-base:rc:work-tree",
    release_drift=False,
    release_drift_tolerated=False,
    core_gate_ok=True,
    core_gate_missing: tuple[str, ...] = (),
    layer_core_gate=None,
):
    evidence = {
        "validation_artifact_truth": {
            "ok": validation_ok,
            "status": validation_status,
            "hidden_by_green_regression": hidden_by_green_regression,
        },
        "last_regression_status": regression_status,
        "last_regression_stale": regression_stale,
        "release_runtime_truth": {
            "running_build_identity": release_identity,
            "latest_source_changed_after_build": release_drift,
            "runtime_drift_tolerated": release_drift_tolerated,
        },
        "release_status": {
            "latest_artifact_name": release_identity,
            "latest_source_changed_after_build": release_drift,
            "runtime_drift_tolerated": release_drift_tolerated,
        },
    }
    if layer_core_gate is not None:
        evidence["layer_maturity"] = {"core_gate": dict(layer_core_gate)}
    elif core_gate_ok and not core_gate_missing:
        evidence["root_closure_inventory"] = _core_gate_inventory()
    elif core_gate_missing:
        evidence["root_closure_inventory"] = _core_gate_inventory(missing=core_gate_missing)
    return evidence


def _base_inputs(**overrides):
    payload = {
        "work_tree_snapshot": {"latent_root_signal_count": 0, "branches": []},
        "steward_posture": {
            "posture_band": "green",
            "critical_alerts": 0,
            "health_score": 96,
        },
        "queue_pressure": {
            "pressure_band": "low",
            "high_priority_count": 0,
            "generated_actionable_count": 0,
            "generated_pending_count": 0,
            "patch_ready_count": 0,
            "aging_items_count": 0,
        },
        "runtime_guard_status": {
            "guard_running": True,
            "core_running": True,
            "webui_running": True,
        },
        "triage_hints": {
            "approved_review_count": 0,
        },
        "policy_snapshot": {
            "mission": {
                "enabled": True,
                "mode": "steady_state_guard",
                "subconscious_triage_is_pressure": False,
                "generated_queue_backlog_is_pressure": False,
            }
        },
        "truth_evidence": _truth_evidence(),
    }
    payload.update(overrides)
    return payload


def _steady_hold_mission(**overrides):
    mission = NOVA_MISSION_SERVICE.build_snapshot(**_base_inputs())
    mission.update(overrides)
    return mission


class TestNovaMissionService(unittest.TestCase):
    def test_green_cycle_requires_fresh_truth_evidence(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(**_base_inputs())

        self.assertTrue(bool(mission.get("green_cycle")))
        self.assertEqual(mission.get("status"), "green")
        self.assertEqual(mission.get("action"), "hold")
        self.assertTrue(bool(mission.get("truth_ready")))
        self.assertEqual(mission.get("truth_blockers"), [])
        self.assertTrue(bool(mission.get("validation_fresh")))
        self.assertTrue(bool(mission.get("regression_current")))
        self.assertTrue(bool(mission.get("release_truth_current")))
        self.assertTrue(bool(mission.get("core_gate_ok")))
        self.assertEqual(mission.get("blocking_owner_count"), 0)
        owners = {
            str(item.get("owner") or ""): item
            for item in list(mission.get("owner_verdicts") or [])
            if isinstance(item, dict)
        }
        self.assertIn("validation", owners)
        self.assertIn("regression", owners)
        self.assertIn("release", owners)
        self.assertIn("generated_queue", owners)
        self.assertIn("layer_maturity", owners)

    def test_steady_state_hold_without_green_when_truth_is_missing(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                truth_evidence=_truth_evidence(
                    validation_ok=False,
                    validation_status="validation_actions_missing",
                )
            )
        )

        self.assertFalse(bool(mission.get("green_cycle")))
        self.assertEqual(mission.get("action"), "hold")
        self.assertEqual(mission.get("status"), "validation_required")
        self.assertIn("validation_truth_missing", mission.get("truth_blockers") or [])

    def test_high_generated_queue_blocks_green_but_can_still_hold(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                queue_pressure={
                    "pressure_band": "high",
                    "high_priority_count": 4,
                    "generated_actionable_count": 4,
                    "generated_pending_count": 4,
                    "patch_ready_count": 0,
                    "aging_items_count": 0,
                },
                triage_hints={"approved_review_count": 2},
            )
        )

        self.assertFalse(bool(mission.get("green_cycle")))
        self.assertEqual(mission.get("action"), "hold")
        self.assertEqual(mission.get("status"), "validation_required")
        self.assertIn("generated_queue_untested", mission.get("truth_blockers") or [])
        self.assertEqual(mission.get("ambient_gap_signal_count"), 6)
        self.assertEqual(mission.get("fresh_gap_signal_count"), 0)
        self.assertEqual(mission.get("effective_queue_pressure_band"), "high")

    def test_generated_queue_validation_can_run_to_clear_own_truth_blocker(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                queue_pressure={
                    "pressure_band": "high",
                    "high_priority_count": 2,
                    "generated_actionable_count": 2,
                    "generated_pending_count": 2,
                    "patch_ready_count": 0,
                    "aging_items_count": 0,
                },
            )
        )

        self.assertFalse(bool(mission.get("green_cycle")))
        self.assertFalse(bool(mission.get("truth_ready")))
        self.assertFalse(bool(mission.get("active_work_evidence_current")))
        self.assertIn("generated_queue_untested", mission.get("truth_blockers") or [])
        generated_blockers = [
            item
            for item in list(mission.get("green_blockers") or [])
            if isinstance(item, dict) and item.get("code") == "generated_queue_untested"
        ]
        self.assertEqual(
            dict((generated_blockers[0] or {}).get("remediation") or {}).get("action"),
            "generated_queue_run_next",
        )
        self.assertFalse(
            NovaMissionService.hold_blocks_action(
                "generated_queue_run_next",
                mission_snapshot=mission,
            )
        )
        self.assertTrue(
            NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                action_context={"recommended_tool": "core_thinning"},
            )
        )

    def test_generated_queue_validation_stays_held_when_base_truth_is_missing(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                truth_evidence=_truth_evidence(
                    validation_ok=False,
                    validation_status="validation_actions_missing",
                ),
                queue_pressure={
                    "pressure_band": "high",
                    "high_priority_count": 2,
                    "generated_actionable_count": 2,
                    "generated_pending_count": 2,
                    "patch_ready_count": 0,
                    "aging_items_count": 0,
                },
            )
        )

        self.assertIn("validation_truth_missing", mission.get("truth_blockers") or [])
        self.assertIn("generated_queue_untested", mission.get("truth_blockers") or [])
        self.assertTrue(
            NovaMissionService.hold_blocks_action(
                "generated_queue_run_next",
                mission_snapshot=mission,
            )
        )

    def test_active_regression_failure_never_returns_green_cycle(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                truth_evidence=_truth_evidence(
                    regression_status="FAIL",
                    regression_stale=False,
                )
            )
        )

        self.assertFalse(bool(mission.get("green_cycle")))
        self.assertIn("regression_failed", mission.get("truth_blockers") or [])
        self.assertTrue(bool(mission.get("regression_current")))
        self.assertFalse(bool(mission.get("regression_passed")))
        self.assertIn(
            {"owner": "regression", "code": "regression_failed"},
            [
                {"owner": item.get("owner"), "code": item.get("code")}
                for item in list(mission.get("owner_blockers") or [])
                if isinstance(item, dict)
            ],
        )

    def test_hidden_validation_failures_block_green_cycle(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                truth_evidence=_truth_evidence(
                    validation_ok=True,
                    validation_status="validation_failure_in_green_regression",
                    hidden_by_green_regression=True,
                )
            )
        )

        self.assertFalse(bool(mission.get("green_cycle")))
        self.assertIn("validation_truth_missing", mission.get("truth_blockers") or [])

    def test_actionable_pressure_still_blocks_green_cycle_when_policy_flags_enabled(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                policy_snapshot={
                    "mission": {
                        "enabled": True,
                        "mode": "steady_state_guard",
                        "subconscious_triage_is_pressure": True,
                        "generated_queue_backlog_is_pressure": True,
                    }
                },
                triage_hints={"approved_review_count": 2},
                queue_pressure={
                    "pressure_band": "high",
                    "high_priority_count": 4,
                    "generated_actionable_count": 4,
                    "generated_pending_count": 4,
                    "patch_ready_count": 0,
                    "aging_items_count": 0,
                },
            )
        )

        self.assertFalse(bool(mission.get("green_cycle")))
        self.assertEqual(mission.get("action"), "investigate")
        self.assertEqual(mission.get("status"), "watch")
        self.assertGreater(int(mission.get("fresh_gap_signal_count") or 0), 0)

    def test_operator_holds_do_not_block_green_cycle(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                work_tree_snapshot={
                    "latent_root_signal_count": 0,
                    "blocked_count": 3,
                    "operator_hold_count": 3,
                },
                queue_pressure={
                    "pressure_band": "low",
                    "high_priority_count": 0,
                    "generated_actionable_count": 0,
                    "generated_pending_count": 0,
                    "patch_ready_count": 0,
                    "aging_items_count": 0,
                },
            )
        )

        self.assertTrue(bool(mission.get("green_cycle")))
        self.assertEqual(mission.get("operator_hold_count"), 3)
        self.assertEqual(mission.get("non_operator_blocked_count"), 0)

    def test_runtime_not_ready_blocks_green_cycle_even_when_truth_is_fresh(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                runtime_guard_status={
                    "guard_running": True,
                    "core_running": True,
                    "webui_running": False,
                }
            )
        )

        self.assertFalse(bool(mission.get("green_cycle")))
        self.assertFalse(bool(mission.get("runtime_ready")))
        self.assertEqual(mission.get("action"), "investigate")

    def test_release_drift_without_tolerance_blocks_green_cycle(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                truth_evidence=_truth_evidence(
                    release_drift=True,
                    release_drift_tolerated=False,
                )
            )
        )

        self.assertFalse(bool(mission.get("green_cycle")))
        self.assertIn("release_truth_stale", mission.get("truth_blockers") or [])
        self.assertFalse(bool(mission.get("release_truth_current")))

    def test_release_truth_stale_allows_release_rebuild_verify_remediation(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                truth_evidence=_truth_evidence(
                    release_drift=True,
                    release_drift_tolerated=False,
                ),
            )
        )

        green_blockers = list(mission.get("green_blockers") or [])
        release_blocker = next(
            (
                item
                for item in green_blockers
                if isinstance(item, dict) and item.get("code") == "release_truth_stale"
            ),
            None,
        )
        if release_blocker is None:
            release_blocker = next(
                (
                    item
                    for item in list(mission.get("truth_blockers") or [])
                    if isinstance(item, dict) and item.get("code") == "release_truth_stale"
                ),
                None,
            )
        if isinstance(release_blocker, dict):
            remediation = dict(release_blocker.get("remediation") or {})
            self.assertIn("release_rebuild_verify", list(remediation.get("tools") or []))
        self.assertTrue(NovaMissionService._hold_allows_active_work_tool(mission, "release_rebuild_verify"))
        self.assertFalse(
            NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                action_context={"recommended_tool": "release_rebuild_verify"},
            )
        )
        self.assertFalse(
            NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                action_context={"recommended_tool": "core_thinning"},
            )
        )

    def test_core_gate_missing_roots_block_green_cycle(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                truth_evidence=_truth_evidence(core_gate_missing=("http_api_control",)),
            )
        )

        self.assertFalse(bool(mission.get("green_cycle")))
        self.assertIn("core_gate_roots_blocked", mission.get("truth_blockers") or [])
        self.assertFalse(bool(mission.get("core_gate_ok")))

    def test_layer_maturity_core_gate_is_authoritative_owner_signal(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                truth_evidence=_truth_evidence(
                    layer_core_gate={
                        "ok": True,
                        "drift_blocked": False,
                        "missing_roots": [],
                        "required_roots": list(CORE_GATE_ROOT_IDS),
                    }
                )
            )
        )

        self.assertTrue(bool(mission.get("green_cycle")))
        self.assertTrue(bool(mission.get("core_gate_ok")))
        self.assertEqual(mission.get("core_gate_source"), "layer_maturity.core_gate")

    def test_explicit_owner_verdict_overrides_compatibility_mapping(self):
        evidence = _truth_evidence(regression_status="OK", regression_stale=False)
        evidence["owner_verdicts"] = [
            {
                "owner": "regression",
                "ready": False,
                "source": "regression.owner_verdict",
                "blockers": [
                    {
                        "code": "regression_stale",
                        "detail": "canonical owner verdict blocked the cycle",
                    }
                ],
            }
        ]
        mission = NOVA_MISSION_SERVICE.build_snapshot(**_base_inputs(truth_evidence=evidence))

        self.assertFalse(bool(mission.get("green_cycle")))
        self.assertFalse(bool(mission.get("regression_current")))
        self.assertIn("regression_stale", mission.get("truth_blockers") or [])
        self.assertIn(
            {"owner": "regression", "code": "regression_stale"},
            [
                {"owner": item.get("owner"), "code": item.get("code")}
                for item in list(mission.get("owner_blockers") or [])
                if isinstance(item, dict)
            ],
        )

    def test_non_green_blocking_owner_pressure_stays_visible_without_false_truth_blocker(self):
        evidence = _truth_evidence()
        evidence["owner_verdicts"] = [
            {
                "owner": "core_thinning",
                "ready": False,
                "source": "core_thinning",
                "blocks_green": False,
                "blockers": [
                    {
                        "code": "core_http_thinning_pressure",
                        "detail": "3 core/http thinning work orders ready",
                    }
                ],
            }
        ]
        mission = NOVA_MISSION_SERVICE.build_snapshot(**_base_inputs(truth_evidence=evidence))

        self.assertTrue(bool(mission.get("truth_ready")))
        self.assertTrue(bool(mission.get("green_cycle")))
        self.assertNotIn("core_http_thinning_pressure", mission.get("truth_blockers") or [])
        self.assertEqual(mission.get("green_blockers"), [])
        self.assertEqual(mission.get("blocking_owner_count"), 0)
        self.assertIn(
            {"owner": "core_thinning", "code": "core_http_thinning_pressure"},
            [
                {"owner": item.get("owner"), "code": item.get("code")}
                for item in list(mission.get("owner_blockers") or [])
                if isinstance(item, dict)
            ],
        )

    def test_core_thinning_can_run_when_only_release_drift_blocks_green(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                truth_evidence=_truth_evidence(
                    release_drift=True,
                    release_drift_tolerated=True,
                    layer_core_gate={"ok": False, "drift_blocked": True, "missing_roots": []},
                ),
            )
        )

        self.assertFalse(bool(mission.get("green_cycle")))
        self.assertFalse(bool(mission.get("truth_ready")))
        self.assertTrue(bool(mission.get("active_work_evidence_current")))
        self.assertEqual(mission.get("truth_blockers"), ["core_gate_release_drift"])
        green_blockers = list(mission.get("green_blockers") or [])
        self.assertEqual(len(green_blockers), 1)
        remediation = dict(green_blockers[0].get("remediation") or {})
        self.assertEqual(remediation.get("action"), "active_work_tree_run_next")
        self.assertIn("release_rebuild_verify", list(remediation.get("tools") or []))
        self.assertFalse(
            NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                action_context={"recommended_tool": "core_thinning"},
            )
        )
        self.assertFalse(
            NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                action_context={"recommended_tool": "release_rebuild_verify"},
            )
        )
        self.assertTrue(
            NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                action_context={"recommended_tool": "read"},
            )
        )

    def test_core_thinning_stays_held_when_core_gate_roots_are_blocked(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                truth_evidence=_truth_evidence(core_gate_missing=("http_api_control",)),
            )
        )

        self.assertTrue(bool(mission.get("active_work_evidence_current")))
        self.assertIn("core_gate_roots_blocked", mission.get("truth_blockers") or [])
        self.assertTrue(
            NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                action_context={"recommended_tool": "core_thinning"},
            )
        )

    def test_core_thinning_release_drift_allowance_requires_core_gate_evidence(self):
        mission = {
            "enabled": True,
            "mode": "steady_state_guard",
            "green_cycle": False,
            "truth_ready": False,
            "status": "validation_required",
            "action": "hold",
            "truth_blockers": ["core_gate_release_drift"],
            "green_blockers": [{"owner": "layer_maturity", "code": "core_gate_release_drift"}],
            "validation_fresh": True,
            "regression_current": True,
            "release_truth_current": True,
            "generated_queue_untested_count": 0,
        }

        self.assertTrue(bool(NovaMissionService.active_work_evidence_current(mission)))
        self.assertTrue(
            NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                action_context={"recommended_tool": "core_thinning"},
            )
        )

    def test_core_thinning_stays_held_when_release_drift_hides_missing_roots(self):
        mission = NOVA_MISSION_SERVICE.build_snapshot(
            **_base_inputs(
                truth_evidence=_truth_evidence(
                    release_drift=True,
                    release_drift_tolerated=True,
                    layer_core_gate={
                        "ok": False,
                        "drift_blocked": True,
                        "missing_roots": ["http_api_control"],
                    },
                ),
            )
        )

        self.assertTrue(bool(mission.get("active_work_evidence_current")))
        self.assertIn("core_gate_release_drift", mission.get("truth_blockers") or [])
        self.assertTrue(
            NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                action_context={"recommended_tool": "core_thinning"},
            )
        )

    def test_execution_contract_blocks_legacy_actions_but_allows_patch_queue(self):
        mission = _steady_hold_mission()
        policy = {"mission": NovaMissionService.DEFAULT_POLICY}

        self.assertTrue(
            NovaMissionService.hold_blocks_action(
                "generated_queue_run_next",
                mission_snapshot=mission,
                policy_snapshot=policy,
            )
        )
        self.assertTrue(
            NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                policy_snapshot=policy,
            )
        )
        self.assertFalse(
            NovaMissionService.hold_blocks_action(
                "patch_queue_run_next",
                mission_snapshot=mission,
                policy_snapshot=policy,
            )
        )

    def test_ingestion_suppresses_ambient_governance_on_quiet_hold(self):
        mission = _steady_hold_mission(actionable_fresh_gap_signal_count=0)
        policy = {"mission": NovaMissionService.DEFAULT_POLICY}

        self.assertTrue(
            NovaMissionService.ingestion_suppresses_ambient_governance(mission, policy_snapshot=policy)
        )

    def test_ingestion_does_not_suppress_when_actionable_gaps_present(self):
        mission = _steady_hold_mission(actionable_fresh_gap_signal_count=2, status="watch", action="investigate")
        policy = {"mission": NovaMissionService.DEFAULT_POLICY}

        self.assertFalse(
            NovaMissionService.ingestion_suppresses_ambient_governance(mission, policy_snapshot=policy)
        )

    def test_hold_allows_remediation_when_any_blocker_prescribes_it(self):
        mission = {
            "enabled": True,
            "mode": "steady_state_guard",
            "green_cycle": False,
            "truth_ready": False,
            "status": "validation_required",
            "action": "hold",
            "validation_fresh": True,
            "regression_current": True,
            "release_truth_current": True,
            "generated_queue_untested_count": 2,
            "green_blockers": [
                {
                    "owner": "regression",
                    "code": "regression_failed",
                    "remediation": {
                        "action": "run_regression",
                        "tools": ["release_rebuild_verify", "core_thinning"],
                    },
                },
                {
                    "owner": "generated_queue",
                    "code": "generated_queue_untested",
                    "remediation": {"action": "generated_queue_run_next"},
                },
                {
                    "owner": "layer_maturity",
                    "code": "core_gate_release_drift",
                    "remediation": {
                        "action": "active_work_tree_run_next",
                        "tools": ["release_rebuild_verify", "core_thinning"],
                    },
                },
            ],
            "truth_blockers": [
                "regression_failed",
                "generated_queue_untested",
                "core_gate_release_drift",
            ],
            "core_gate": {"drift_blocked": True, "missing_roots": []},
        }

        self.assertFalse(
            NovaMissionService.hold_blocks_action(
                "generated_queue_run_next",
                mission_snapshot=mission,
            )
        )
        self.assertFalse(
            NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                action_context={"recommended_tool": "release_rebuild_verify"},
            )
        )
        self.assertFalse(
            NovaMissionService.hold_blocks_action(
                "active_work_tree_run_next",
                mission_snapshot=mission,
                action_context={"recommended_tool": "core_thinning"},
            )
        )

    def test_release_truth_stale_remediation_allows_parallel_generated_queue_untested(self):
        mission = {
            "validation_fresh": True,
            "regression_current": True,
            "release_truth_current": False,
            "generated_queue_untested_count": 2,
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
        }

        self.assertTrue(NovaMissionService._release_truth_stale_remediation_window(mission))
        self.assertTrue(NovaMissionService._hold_allows_active_work_tool(mission, "release_rebuild_verify"))
        self.assertTrue(NovaMissionService._hold_allows_active_work_tool(mission, "core_thinning"))

    def test_generated_queue_run_next_allowed_when_release_truth_stale_without_base_pillars(self):
        mission = {
            "enabled": True,
            "mode": "steady_state_guard",
            "action": "hold",
            "status": "validation_required",
            "validation_fresh": True,
            "regression_current": True,
            "release_truth_current": False,
            "generated_queue_untested_count": 2,
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
        }

        self.assertFalse(
            NovaMissionService.hold_blocks_action(
                "generated_queue_run_next",
                mission_snapshot=mission,
            )
        )

    def test_generated_queue_run_next_still_blocked_when_validation_not_fresh(self):
        mission = {
            "enabled": True,
            "mode": "steady_state_guard",
            "action": "hold",
            "status": "validation_required",
            "validation_fresh": False,
            "regression_current": True,
            "release_truth_current": False,
            "generated_queue_untested_count": 2,
            "truth_blockers": ["validation_truth_missing", "generated_queue_untested"],
            "green_blockers": [
                {"owner": "validation", "code": "validation_truth_missing"},
                {
                    "owner": "generated_queue",
                    "code": "generated_queue_untested",
                    "remediation": {"action": "generated_queue_run_next"},
                },
            ],
        }

        self.assertTrue(
            NovaMissionService.hold_blocks_action(
                "generated_queue_run_next",
                mission_snapshot=mission,
            )
        )

    def test_append_history_tracks_sustained_watch(self):
        state: dict = {}
        for _ in range(7):
            NovaMissionService.append_history(
                state,
                {
                    "snapshot_ts_utc": f"2026-07-10T12:0{_}0Z",
                    "status": "watch",
                    "action": "investigate",
                    "green_cycle": False,
                    "truth_ready": False,
                    "truth_blockers": ["validation_truth_missing"],
                    "headline": "mission watch",
                    "sustained_watch_cycles": 6,
                },
            )

        self.assertEqual(len(state.get("nova_mission_history") or []), 7)
        self.assertEqual(state.get("nova_mission_watch_streak"), 7)
        self.assertTrue(bool(state.get("nova_mission_sustained_watch")))

    def test_anti_drift_matrix_never_green_under_stale_testing_pressure(self):
        scenarios = [
            {
                "name": "missing_validation_truth",
                "truth_evidence": _truth_evidence(
                    validation_ok=False,
                    validation_status="validation_actions_missing",
                ),
            },
            {
                "name": "stale_regression",
                "truth_evidence": _truth_evidence(
                    regression_status="FAIL",
                    regression_stale=True,
                ),
            },
            {
                "name": "generated_queue_untested",
                "queue_pressure": {
                    "pressure_band": "high",
                    "high_priority_count": 2,
                    "generated_actionable_count": 2,
                    "generated_pending_count": 2,
                    "patch_ready_count": 0,
                    "aging_items_count": 0,
                },
            },
            {
                "name": "core_gate_roots_blocked",
                "truth_evidence": _truth_evidence(core_gate_missing=("operator_control",)),
            },
        ]
        for scenario in scenarios:
            with self.subTest(scenario=scenario["name"]):
                mission = NOVA_MISSION_SERVICE.build_snapshot(
                    **_base_inputs(
                        truth_evidence=scenario.get("truth_evidence", _truth_evidence()),
                        queue_pressure=scenario.get(
                            "queue_pressure",
                            {
                                "pressure_band": "low",
                                "high_priority_count": 0,
                                "generated_actionable_count": 0,
                                "generated_pending_count": 0,
                                "patch_ready_count": 0,
                                "aging_items_count": 0,
                            },
                        ),
                    )
                )
                self.assertFalse(
                    bool(mission.get("green_cycle")),
                    msg=f"{scenario['name']} must not report green_cycle=true",
                )


if __name__ == "__main__":
    unittest.main()
