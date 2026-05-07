import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock
import uuid

import autonomy_maintenance
import work_tree


class TestAutonomyMaintenance(unittest.TestCase):
    def _isolated_work_tree_db(self):
        original_path = Path(work_tree._DB_REQUESTED_PATH)
        base_tmp = Path("C:/Nova/runtime/_test_tmp")
        base_tmp.mkdir(parents=True, exist_ok=True)
        db_path = base_tmp / f"autonomy_maintenance_{uuid.uuid4().hex}.sqlite3"
        work_tree._set_db_path(db_path)

        def _cleanup() -> None:
            try:
                work_tree._set_db_path(original_path)
            finally:
                for candidate in (
                    db_path,
                    db_path.with_name(f"{db_path.name}-journal"),
                    db_path.with_suffix(f"{db_path.suffix}-wal"),
                    db_path.with_suffix(f"{db_path.suffix}-shm"),
                ):
                    try:
                        if candidate.exists():
                            candidate.unlink()
                    except Exception:
                        pass

        self.addCleanup(_cleanup)
        return db_path

    def test_archive_stale_complete_trees_keeps_recent_history_visible(self):
        self._isolated_work_tree_db()
        now = work_tree._now()
        created_ids = []
        for idx in range(4):
            tree = work_tree.initialize_tree(
                f"Cli: stale {idx}",
                meta={"kind": "system", "source": "cli"},
            )
            work_tree._refresh_tree_state(tree.tree_id, persist=True)
            tree.updated_at = now - timedelta(hours=idx + 1)
            work_tree.save_tree(tree)
            work_tree._persist_tree_state(tree.tree_id)
            created_ids.append(tree.tree_id)

        state: dict = {}
        with mock.patch.object(autonomy_maintenance, "COMPLETE_TREE_VISIBLE_KEEP", 2), \
             mock.patch.object(autonomy_maintenance, "COMPLETE_TREE_ARCHIVE_MIN_AGE_SEC", 0):
            payload = autonomy_maintenance._archive_stale_complete_trees(state)

        self.assertEqual(payload.get("archived_count"), 2)
        self.assertEqual(payload.get("retained_count"), 2)
        retained_ids = set(created_ids[:2])
        archived_ids = set(created_ids[2:])
        visible_ids = {item.get("tree_id") for item in work_tree.list_visual_trees(limit=None)}
        self.assertTrue(retained_ids.issubset(visible_ids))
        self.assertTrue(archived_ids.isdisjoint(visible_ids))
        for tree_id in archived_ids:
            self.assertEqual(work_tree.get_tree(tree_id).status, work_tree.TreeStatus.ARCHIVED)

    def test_archive_empty_active_trees_archives_only_old_root_shells(self):
        self._isolated_work_tree_db()
        now = work_tree._now()
        old_empty = work_tree.initialize_tree("Cli: empty old")
        old_empty.updated_at = now - timedelta(hours=2)
        work_tree.save_tree(old_empty)
        work_tree._persist_tree_state(old_empty.tree_id)

        old_with_task = work_tree.initialize_tree("Cli: task old")
        old_with_task.updated_at = now - timedelta(hours=2)
        work_tree.add_task_to_branch(old_with_task.root_branch_id, "Keep this task")
        work_tree.save_tree(old_with_task)
        work_tree._persist_tree_state(old_with_task.tree_id)

        recent_empty = work_tree.initialize_tree("Cli: empty recent")
        recent_empty.updated_at = now
        work_tree.save_tree(recent_empty)
        work_tree._persist_tree_state(recent_empty.tree_id)

        state: dict = {}
        with mock.patch.object(autonomy_maintenance, "EMPTY_ACTIVE_TREE_ARCHIVE_MIN_AGE_SEC", 3600):
            payload = autonomy_maintenance._archive_empty_active_trees(state)

        self.assertEqual(payload.get("archived_count"), 1)
        self.assertEqual(payload.get("skipped_recent_count"), 1)
        self.assertEqual(work_tree.get_tree(old_empty.tree_id).status, work_tree.TreeStatus.ARCHIVED)
        self.assertEqual(work_tree.get_tree(old_with_task.tree_id).status, work_tree.TreeStatus.ACTIVE)
        self.assertEqual(work_tree.get_tree(recent_empty.tree_id).status, work_tree.TreeStatus.ACTIVE)
        self.assertEqual((state.get("last_empty_active_tree_archive") or {}).get("archived_count"), 1)

    def test_archive_stale_cli_active_trees_archives_only_simple_prompt_shells(self):
        self._isolated_work_tree_db()
        now = work_tree._now()

        stale_cli = work_tree.initialize_tree(
            "Cli: stale prompt",
            meta={"kind": "system", "source": "cli", "work_identity_key": "work:stale-prompt"},
        )
        work_tree.add_task_to_branch(stale_cli.root_branch_id, "stale followup")
        stale_cli.created_at = now - timedelta(hours=13)
        stale_cli.updated_at = now - timedelta(hours=13)
        work_tree.save_tree(stale_cli)
        work_tree._persist_tree_state(stale_cli.tree_id)

        recent_cli = work_tree.initialize_tree(
            "Cli: recent prompt",
            meta={"kind": "system", "source": "cli", "work_identity_key": "work:recent-prompt"},
        )
        work_tree.add_task_to_branch(recent_cli.root_branch_id, "recent followup")
        recent_cli.created_at = now - timedelta(minutes=10)
        recent_cli.updated_at = now - timedelta(minutes=10)
        work_tree.save_tree(recent_cli)
        work_tree._persist_tree_state(recent_cli.tree_id)

        core_thinning = work_tree.initialize_tree(
            "Core Thinning",
            meta={"source": "core_thinning", "work_identity_key": "system:core-thinning"},
        )
        work_tree.add_task_to_branch(core_thinning.root_branch_id, "keep thinning")
        core_thinning.created_at = now - timedelta(hours=48)
        core_thinning.updated_at = now - timedelta(hours=48)
        work_tree.save_tree(core_thinning)
        work_tree._persist_tree_state(core_thinning.tree_id)

        complex_cli = work_tree.initialize_tree(
            "Cli: complex prompt",
            meta={"kind": "system", "source": "cli", "work_identity_key": "work:complex-prompt"},
        )
        for idx in range(5):
            work_tree.add_branch_to_tree(complex_cli.tree_id, f"complex branch {idx}", "work", complex_cli.root_branch_id)
        complex_cli.created_at = now - timedelta(hours=13)
        complex_cli.updated_at = now - timedelta(hours=13)
        work_tree.save_tree(complex_cli)
        work_tree._persist_tree_state(complex_cli.tree_id)

        state: dict = {}
        with mock.patch.object(autonomy_maintenance, "STALE_CLI_ACTIVE_TREE_ARCHIVE_MIN_AGE_SEC", 3600), \
             mock.patch.object(autonomy_maintenance, "STALE_CLI_ACTIVE_TREE_MAX_BRANCHES", 5), \
             mock.patch.object(autonomy_maintenance, "STALE_CLI_ACTIVE_TREE_MAX_OPEN_TASKS", 2):
            payload = autonomy_maintenance._archive_stale_cli_active_trees(state)

        self.assertEqual(payload.get("archived_count"), 1)
        self.assertEqual(payload.get("skipped_recent_count"), 1)
        self.assertEqual(payload.get("skipped_complex_count"), 1)
        self.assertEqual(work_tree.get_tree(stale_cli.tree_id).status, work_tree.TreeStatus.ARCHIVED)
        self.assertEqual(work_tree.get_tree(recent_cli.tree_id).status, work_tree.TreeStatus.ACTIVE)
        self.assertEqual(work_tree.get_tree(core_thinning.tree_id).status, work_tree.TreeStatus.ACTIVE)
        self.assertEqual(work_tree.get_tree(complex_cli.tree_id).status, work_tree.TreeStatus.ACTIVE)
        self.assertTrue(
            all(task.status == work_tree.TaskStatus.DROPPED for task in work_tree.list_tree_tasks(stale_cli.tree_id))
        )
        self.assertEqual((state.get("last_stale_cli_tree_archive") or {}).get("archived_count"), 1)

    def test_run_once_records_generated_queue_outcome(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            latest_path = runtime_dir / "subconscious_runs" / "latest.json"
            latest_path.parent.mkdir(parents=True, exist_ok=True)
            latest_path.write_text(
                json.dumps({"generated_at": "2026-04-04 02:00:00", "families": []}, ensure_ascii=True),
                encoding="utf-8",
            )
            state_path = runtime_dir / "autonomy_maintenance_state.json"
            log_path = runtime_dir / "autonomy_maintenance.log"

            def _generated_queue_cycle(state):
                autonomy_maintenance._record_generated_queue_run(
                    state,
                    True,
                    "generated_work_queue_cycle_executed",
                    {
                        "selected": {"file": "demo.json", "latest_status": "warning"},
                        "latest_report": {"status": "warning", "run_id": "demo_run"},
                        "work_queue": {
                            "status": "actionable",
                            "open_count": 3,
                            "actionable_count": 2,
                            "blocked_count": 1,
                            "blocked_reason_counts": {"parity_drift_locked": 1},
                            "blocked_files": ["stuck.json"],
                            "count": 5,
                        },
                    },
                )
                payload = {
                    "ts": "2026-04-04 02:00:01",
                    "status": "ok",
                    "tree_id": "tree_generated_demo",
                    "tree_title": autonomy_maintenance.GENERATED_QUEUE_TREE_TITLE,
                    "tree_count": 1,
                    "executed_count": 1,
                    "history_count": 1,
                    "last_action": "executed",
                    "actionable_count": 2,
                    "queue_status": "actionable",
                    "selected_file": "demo.json",
                }
                state["last_generated_queue_tree_cycle"] = payload
                return payload

            with mock.patch.object(autonomy_maintenance, "LATEST_SUBCONSCIOUS", latest_path), \
                 mock.patch.object(autonomy_maintenance, "STATE_FILE", state_path), \
                 mock.patch.object(autonomy_maintenance, "MAINT_LOG", log_path), \
                 mock.patch.object(autonomy_maintenance, "_run_subconscious_pack", return_value=(True, "ok")), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_sync_generated_queue_work_tree",
                     return_value={
                         "ts": "2026-04-04 02:00:01",
                         "status": "ok",
                         "tree_id": "tree_generated_demo",
                         "tree_title": autonomy_maintenance.GENERATED_QUEUE_TREE_TITLE,
                         "queue_status": "actionable",
                         "queue_count": 5,
                         "open_count": 3,
                         "actionable_count": 2,
                         "blocked_count": 1,
                         "created_count": 1,
                         "updated_count": 0,
                         "reopened_count": 0,
                         "retired_count": 0,
                         "next_file": "demo.json",
                     },
                 ), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_run_generated_queue_work_tree_cycle",
                     side_effect=_generated_queue_cycle,
                 ), \
                 mock.patch.object(
                     autonomy_maintenance.kidney,
                     "run_kidney",
                     return_value={
                         "ts": "2026-04-04 02:00:01",
                         "mode": "enforce",
                         "candidate_count": 2,
                         "archive_count": 1,
                         "delete_count": 1,
                         "snapshot_path": "snapshot.zip",
                     },
                 ), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_run_patch_queue_cleanup",
                     return_value={
                         "ts": "2026-04-04 02:00:01",
                         "status": "ok",
                         "orphan_rejected_count": 0,
                         "orphan_failed_count": 0,
                         "superseded_archived_count": 0,
                         "superseded_failed_count": 0,
                         "review_total_before": 0,
                         "review_total_after": 0,
                     },
                 ), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_sync_patch_queue_work_tree",
                     return_value={
                         "ts": "2026-04-04 02:00:01",
                         "status": "ok",
                         "tree_id": "tree_demo",
                         "tree_title": "Patch Queue",
                         "apply_ready_count": 0,
                         "created_count": 0,
                         "updated_count": 0,
                     },
                 ), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_run_patch_queue_work_tree_cycle",
                     return_value={
                         "ts": "2026-04-04 02:00:01",
                         "status": "idle",
                         "tree_count": 1,
                         "executed_count": 0,
                     },
                 ), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_run_active_work_tree_cycle",
                     return_value={
                         "ts": "2026-04-04 02:00:01",
                         "status": "idle",
                         "tree_count": 0,
                         "executed_count": 0,
                     },
                 ), \
                 mock.patch.object(autonomy_maintenance, "_legacy_maintenance_execution_enabled", return_value=True), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_retire_legacy_patch_update_trees",
                     return_value={
                         "ts": "2026-04-04 02:00:01",
                         "status": "idle",
                         "retired_count": 0,
                     },
                 ), \
                 mock.patch.object(autonomy_maintenance, "_run_daily_regression_if_due", return_value="daily_regression_ok"), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_run_autonomy_orchestrator_advisory",
                     side_effect=lambda state, _kidney: state.setdefault(
                         "last_autonomy_orchestrator",
                         {
                             "decision": "defer_with_reason",
                             "action": {},
                             "reason": "test advisory",
                             "ledger_status": "recorded",
                         },
                     ),
                 ):
                code = autonomy_maintenance.run_once()

            self.assertEqual(code, 0)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            queue_run = dict(state.get("last_generated_queue_run") or {})
            self.assertEqual(queue_run.get("status"), "actionable")
            self.assertEqual(queue_run.get("selected_file"), "demo.json")
            self.assertEqual(queue_run.get("selected_status"), "warning")
            self.assertEqual(queue_run.get("latest_report_status"), "warning")
            self.assertEqual(queue_run.get("latest_report_run_id"), "demo_run")
            self.assertEqual(queue_run.get("queue_open_count"), 3)
            self.assertEqual(queue_run.get("queue_actionable_count"), 2)
            self.assertEqual(queue_run.get("queue_blocked_count"), 1)
            self.assertEqual(queue_run.get("queue_blocked_reason_counts"), {"parity_drift_locked": 1})
            self.assertEqual(queue_run.get("queue_blocked_files"), ["stuck.json"])
            self.assertEqual(queue_run.get("queue_count"), 5)
            self.assertEqual((state.get("last_generated_queue_tree_cycle") or {}).get("executed_count"), 1)

    def test_execute_autonomy_recommendation_uses_dispatcher_for_canary_action(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-test",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "generated_queue_run_next",
                "target_kind": "queue",
                "target_id": "generated_work_queue",
                "reason_code": "queue_pressure_actionable",
                "requires_ack": False,
                "cooldown_sec": 180,
            },
            "confidence": 0.72,
            "refusal_reasons": [],
        }
        policy = {
            "enabled": True,
            "mode": "canary",
            "execute_enabled": True,
            "execute_allowed_actions": ["generated_queue_run_next"],
            "execute_blocked_actions": [],
            "requires_operator_ack_for": [],
            "execute_min_confidence": 0.55,
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_run_next_generated_work_queue_item",
            return_value=(
                True,
                "generated_work_queue_run_ok",
                {
                    "selected": {"file": "demo.json", "latest_status": "pass"},
                    "latest_report": {"status": "pass", "run_id": "run-demo"},
                    "work_queue": {"status": "actionable", "open_count": 1, "actionable_count": 1, "count": 1},
                },
            ),
        ):
            result = autonomy_maintenance._execute_autonomy_recommendation(state, packet, policy)

        self.assertEqual(result.get("result"), "success")
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("action_type"), "generated_queue_run_next")
        self.assertEqual((state.get("last_generated_queue_run") or {}).get("selected_file"), "demo.json")
        events = list(result.get("events") or [])
        self.assertEqual(events[0].get("act"), "generated_queue_run_next")
        self.assertEqual(events[0].get("status"), "ok")

    def test_execute_autonomy_recommendation_dispatches_patch_queue_conduit_action(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-test",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "patch_queue_run_next",
                "target_kind": "lane",
                "target_id": "patch_queue",
                "reason_code": "patch_queue_ready",
                "requires_ack": False,
                "cooldown_sec": 240,
            },
            "confidence": 0.72,
            "refusal_reasons": [],
        }
        policy = {
            "enabled": True,
            "mode": "canary",
            "execute_enabled": True,
            "execute_allowed_actions": [],
            "execute_allowed_action_groups": ["patch_queue"],
            "execute_blocked_actions": [],
            "requires_operator_ack_for": [],
            "execute_min_confidence": 0.55,
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_run_patch_queue_work_tree_cycle",
            return_value={"status": "ok", "executed_count": 1, "tree_count": 1},
        ) as cycle_mock:
            result = autonomy_maintenance._execute_autonomy_recommendation(state, packet, policy)

        cycle_mock.assert_called_once_with(state, max_steps=1)
        self.assertEqual(result.get("result"), "success")
        self.assertEqual(result.get("action_type"), "patch_queue_run_next")
        self.assertEqual(((result.get("extra") or {}).get("cycle") or {}).get("executed_count"), 1)
        self.assertEqual((result.get("events") or [])[0].get("act"), "patch_queue_run_next")

    def test_execute_autonomy_recommendation_dispatches_active_work_tree_conduit_action(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-test",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "active_work_tree_run_next",
                "target_kind": "lane",
                "target_id": "active_work_tree",
                "reason_code": "active_work_tree_ready",
                "requires_ack": False,
                "cooldown_sec": 120,
            },
            "confidence": 0.72,
            "refusal_reasons": [],
        }
        policy = {
            "enabled": True,
            "mode": "canary",
            "execute_enabled": True,
            "execute_allowed_actions": [],
            "execute_allowed_action_groups": ["active_work_tree"],
            "execute_blocked_actions": [],
            "requires_operator_ack_for": [],
            "execute_min_confidence": 0.55,
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_run_active_work_tree_cycle",
            return_value={"status": "ok", "executed_count": 1, "tree_count": 1},
        ) as cycle_mock:
            result = autonomy_maintenance._execute_autonomy_recommendation(state, packet, policy)

        cycle_mock.assert_called_once_with(state, max_steps=1)
        self.assertEqual(result.get("result"), "success")
        self.assertEqual(result.get("action_type"), "active_work_tree_run_next")
        self.assertEqual(((result.get("extra") or {}).get("cycle") or {}).get("executed_count"), 1)
        self.assertEqual((result.get("events") or [])[0].get("act"), "active_work_tree_run_next")

    def test_run_worker_loops_for_bounded_cycles_and_records_status(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            state_path = runtime_dir / "autonomy_maintenance_state.json"
            log_path = runtime_dir / "autonomy_maintenance.log"
            cycles = []
            sleeps = []

            with mock.patch.object(autonomy_maintenance, "STATE_FILE", state_path), \
                 mock.patch.object(autonomy_maintenance, "MAINT_LOG", log_path):
                code = autonomy_maintenance.run_worker(
                    interval_sec=7,
                    max_cycles=2,
                    run_once_fn=lambda: cycles.append("cycle") or 0,
                    sleep_fn=lambda seconds: sleeps.append(seconds),
                )

            self.assertEqual(code, 0)
            self.assertEqual(len(cycles), 2)
            self.assertEqual(sleeps, [7.0])
            state = json.loads(state_path.read_text(encoding="utf-8"))
            worker = dict(state.get("runtime_worker") or {})
            self.assertEqual(worker.get("interval_sec"), 7)
            self.assertEqual(worker.get("last_cycle"), 2)
            self.assertEqual(worker.get("cycle_count"), 2)
            self.assertEqual(worker.get("last_cycle_status"), "ok")
            self.assertEqual(worker.get("last_cycle_code"), 0)
            self.assertGreater(int(worker.get("pid") or 0), 0)
            self.assertEqual(worker.get("script_path"), str(Path(autonomy_maintenance.__file__).resolve()))
            self.assertTrue(worker.get("active"))
            self.assertFalse(worker.get("stale_identity"))

    def test_autonomy_orchestrator_advisory_records_state_and_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            ledger_path = Path(td) / "runtime" / "autonomy_orchestrator_ledger.jsonl"
            state: dict = {}
            core_steward = {
                "score": 100,
                "level": "strong",
                "summary": "core surfaces look stable",
                "runtime": {
                    "heartbeat": {"ok": True, "info": "heartbeat ok"},
                    "core_state": {"ok": True, "info": "core ok"},
                    "ollama": {"ok": True, "info": "ollama ok"},
                },
                "autonomy_maintenance": {"worker_status": "running"},
                "pulse": {"fallback_overuse_score": 0.0, "approved_eligible_previews": 0},
            }

            with mock.patch.object(autonomy_maintenance, "AUTONOMY_ORCHESTRATOR_LEDGER", ledger_path), \
                 mock.patch.object(autonomy_maintenance, "_core_steward_for_orchestrator", return_value=core_steward), \
                 mock.patch.object(
                     autonomy_maintenance.CONTROL_WORK_TREES_SERVICE,
                     "payload",
                     return_value={
                         "ok": True,
                         "counts": {"total": 0, "active": 0, "branches": 0, "open_tasks": 0, "working": 0},
                         "trees": [],
                     },
                 ), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_generated_work_queue",
                     return_value={
                         "status": "ready",
                         "count": 1,
                         "open_count": 1,
                         "actionable_count": 1,
                         "blocked_count": 0,
                         "next_item": {"file": "generated_demo.json"},
                     },
                 ), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_guard_health_for_orchestrator",
                     return_value={"running": True, "status": "running"},
                 ), \
                 mock.patch.object(autonomy_maintenance, "_autonomy_policy_settings", return_value={"enabled": True, "mode": "advisory"}):
                packet = autonomy_maintenance._run_autonomy_orchestrator_advisory(state, {"mode": "enforce"})

            self.assertEqual(packet.get("decision"), "recommend_action")
            self.assertEqual((packet.get("action") or {}).get("act"), "generated_queue_run_next")
            self.assertEqual((state.get("last_autonomy_orchestrator") or {}).get("ledger_status"), "recorded")
            rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].get("decision"), "recommend_action")
            self.assertIn("candidate_actions", rows[0])

    def test_triage_hints_for_orchestrator_use_live_subconscious_triage(self):
        report = {
            "_source_freshness_sec": 9,
            "families": [
                {
                    "family_id": "patch-routing-fallthrough-family",
                    "target_seam": "patch_routing_fallthrough",
                    "training_priorities": [
                        {
                            "seam": "patch_routing_fallthrough",
                            "signal": "fallback_overuse",
                            "robustness": 0.97,
                            "suggested_test_name": "test_patch_routing_route",
                            "rationale": "Patch routing slipped to fallback.",
                            "urgency": "high",
                        }
                    ],
                    "variation_results": [],
                }
            ],
        }
        generated_queue = {
            "status": "actionable",
            "drift_count": 2,
            "next_item": {
                "file": "subconscious_patch-routing-fallthrough-family_patch-apply-direct-tool.json",
                "highest_priority": {
                    "seam": "patch_routing_fallthrough",
                    "signal": "fallback_overuse",
                    "robustness": 0.97,
                },
            },
        }

        hints = autonomy_maintenance._triage_hints_for_orchestrator(
            {"pulse": {"fallback_overuse_score": 0.1}},
            generated_queue,
            latest_report=report,
            state={"last_regression_status": "OK"},
            kidney_summary={"mode": "enforce", "candidate_count": 3},
        )

        self.assertEqual(hints.get("source"), "subconscious_work_tree_triage")
        self.assertEqual(hints.get("source_freshness_sec"), 9)
        self.assertEqual(hints.get("approved_review_count"), 1)
        self.assertAlmostEqual((hints.get("lane_pressure_scores") or {}).get("patch_queue"), 0.97)
        self.assertAlmostEqual((hints.get("lane_pressure_scores") or {}).get("generated_queue"), 0.97)
        self.assertAlmostEqual((hints.get("owner_pressure_scores") or {}).get("supervisor"), 0.97)
        self.assertIn("generated:subconscious_patch-routing-fallthrough-family_patch-apply-direct-tool.json", hints.get("likely_owner_by_branch") or {})
        top = (hints.get("top_triage_candidates") or [])[0]
        self.assertEqual(top.get("preferred_owner"), "supervisor")
        self.assertEqual(top.get("review_contract"), "subconscious.review.supervisor")

    def test_run_once_marks_failed_regression_stale_when_regression_is_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            latest_path = runtime_dir / "subconscious_runs" / "latest.json"
            latest_path.parent.mkdir(parents=True, exist_ok=True)
            latest_path.write_text(json.dumps({"generated_at": "2026-04-23 08:00:00", "families": []}, ensure_ascii=True), encoding="utf-8")
            state_path = runtime_dir / "autonomy_maintenance_state.json"
            log_path = runtime_dir / "autonomy_maintenance.log"
            state_path.write_text(
                json.dumps(
                    {
                        "last_regression_date": "2026-04-23",
                        "last_regression_status": "FAILED",
                        "last_regression_stale": False,
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )

            def _generated_queue_cycle(state):
                autonomy_maintenance._record_generated_queue_run(
                    state,
                    True,
                    "generated_work_queue_clear",
                    {
                        "work_queue": {
                            "status": "clear",
                            "open_count": 0,
                            "actionable_count": 0,
                            "blocked_count": 0,
                            "count": 7,
                        }
                    },
                )
                payload = {
                    "ts": "2026-04-23 08:00:01",
                    "status": "idle",
                    "tree_id": "tree_generated_demo",
                    "tree_title": autonomy_maintenance.GENERATED_QUEUE_TREE_TITLE,
                    "tree_count": 1,
                    "executed_count": 0,
                    "reason": "no_actionable_generated_queue_item",
                    "actionable_count": 0,
                    "queue_status": "clear",
                }
                state["last_generated_queue_tree_cycle"] = payload
                return payload

            with mock.patch.object(autonomy_maintenance, "LATEST_SUBCONSCIOUS", latest_path), \
                 mock.patch.object(autonomy_maintenance, "STATE_FILE", state_path), \
                 mock.patch.object(autonomy_maintenance, "MAINT_LOG", log_path), \
                 mock.patch.object(autonomy_maintenance, "_run_subconscious_pack", return_value=(True, "ok")), \
                 mock.patch.object(autonomy_maintenance, "_sync_generated_queue_work_tree", return_value={"ts": "2026-04-23 08:00:01", "status": "ok", "tree_id": "tree_generated_demo", "tree_title": autonomy_maintenance.GENERATED_QUEUE_TREE_TITLE, "queue_status": "clear", "queue_count": 7, "open_count": 0, "actionable_count": 0, "blocked_count": 0, "created_count": 0, "updated_count": 0, "reopened_count": 0, "retired_count": 0}), \
                 mock.patch.object(autonomy_maintenance, "_run_generated_queue_work_tree_cycle", side_effect=_generated_queue_cycle), \
                 mock.patch.object(autonomy_maintenance.kidney, "run_kidney", return_value={"ts": "2026-04-23 08:00:01", "mode": "enforce", "candidate_count": 0, "archive_count": 0, "delete_count": 0, "snapshot_path": ""}), \
                 mock.patch.object(autonomy_maintenance, "_run_patch_queue_cleanup", return_value={"ts": "2026-04-23 08:00:01", "status": "ok"}), \
                 mock.patch.object(autonomy_maintenance, "_sync_patch_queue_work_tree", return_value={"ts": "2026-04-23 08:00:01", "status": "ok", "tree_id": "tree_demo", "tree_title": "Patch Queue", "apply_ready_count": 0, "created_count": 0, "updated_count": 0}), \
                 mock.patch.object(autonomy_maintenance, "_run_patch_queue_work_tree_cycle", return_value={"ts": "2026-04-23 08:00:01", "status": "idle", "tree_count": 1, "executed_count": 0}), \
                 mock.patch.object(autonomy_maintenance, "_run_active_work_tree_cycle", return_value={"ts": "2026-04-23 08:00:01", "status": "idle", "tree_count": 0, "executed_count": 0}), \
                 mock.patch.object(autonomy_maintenance, "_legacy_maintenance_execution_enabled", return_value=True), \
                 mock.patch.object(autonomy_maintenance, "_retire_legacy_patch_update_trees", return_value={"ts": "2026-04-23 08:00:01", "status": "idle", "retired_count": 0}), \
                 mock.patch.object(autonomy_maintenance, "_run_daily_regression_if_due", return_value="daily_regression_skipped_already_ran"), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_run_autonomy_orchestrator_advisory",
                     side_effect=lambda state, _kidney: state.setdefault(
                         "last_autonomy_orchestrator",
                         {
                             "decision": "defer_with_reason",
                             "action": {},
                             "reason": "test advisory",
                             "ledger_status": "recorded",
                         },
                     ),
                 ):
                code = autonomy_maintenance.run_once()

            self.assertEqual(code, 0)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(state.get("last_regression_stale"))
            self.assertEqual((state.get("last_generated_queue_run") or {}).get("status"), "clear")
            self.assertTrue(bool((state.get("last_signal_ingestion") or {}).get("last_regression_stale")))

    def test_sync_signal_intake_work_tree_creates_regression_branch_for_live_failure(self):
        self._isolated_work_tree_db()
        state = {
            "last_regression_status": "FAILED",
            "last_regression_stale": False,
        }

        payload = autonomy_maintenance._sync_signal_intake_work_tree(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertTrue(payload.get("active_regression_failure"))
        self.assertEqual(payload.get("created_count"), 1)
        tree = work_tree.get_tree(str(payload.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(str(branch.work_class or ""), "regression_failure")
        self.assertEqual(str(branch.source_type or ""), "regression")
        self.assertEqual(str(branch.resolution_state or ""), "open")
        self.assertEqual(branch.status, work_tree.BranchStatus.READY)

    def test_sync_signal_intake_work_tree_resolves_stale_regression_branch(self):
        self._isolated_work_tree_db()
        live_state = {
            "last_regression_status": "FAILED",
            "last_regression_stale": False,
        }
        autonomy_maintenance._sync_signal_intake_work_tree(live_state)

        stale_state = {
            "last_regression_status": "FAILED",
            "last_regression_stale": True,
        }
        payload = autonomy_maintenance._sync_signal_intake_work_tree(stale_state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertFalse(payload.get("active_regression_failure"))
        self.assertEqual(payload.get("resolved_count"), 1)
        tree = work_tree.get_tree(str(payload.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(str(branch.work_class or ""), "regression_failure")
        self.assertEqual(str(branch.resolution_state or ""), "resolved")
        self.assertEqual(branch.status, work_tree.BranchStatus.COMPLETE)

    def test_sync_generated_queue_work_tree_creates_actionable_branch(self):
        self._isolated_work_tree_db()
        state = {}
        item = {
            "file": "subconscious_demo_family_turn.json",
            "actionable": True,
            "latest_status": "drift",
            "family_id": "demo-family",
            "variation_id": "turn-1",
            "opportunity_reason": "parity_drift",
            "highest_priority": {
                "signal": "fallback_overuse",
                "seam": "followup_dispatch",
                "urgency": "high",
                "rationale": "HTTP and CLI diverged on the same followup.",
            },
            "latest_comparison": {
                "diff_count": 2,
                "flagged_probe_count": 1,
            },
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_generated_work_queue",
            return_value={
                "status": "actionable",
                "count": 1,
                "open_count": 1,
                "actionable_count": 1,
                "blocked_count": 0,
                "items": [item],
                "next_item": item,
            },
        ):
            payload = autonomy_maintenance._sync_generated_queue_work_tree(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("created_count"), 1)
        self.assertEqual(payload.get("actionable_count"), 1)
        tree = work_tree.get_tree(payload.get("tree_id"))
        self.assertIsNotNone(tree)
        self.assertEqual(tree.title, autonomy_maintenance.GENERATED_QUEUE_TREE_TITLE)

        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.title, "Repair generated session: subconscious_demo_family_turn.json")
        self.assertEqual(branch.bucket, autonomy_maintenance.GENERATED_QUEUE_BUCKET)
        self.assertEqual(branch.source_type, autonomy_maintenance.GENERATED_QUEUE_SOURCE_TYPE)
        self.assertEqual(branch.source_key, "generated_session::subconscious_demo_family_turn.json")
        self.assertEqual(branch.preferred_tool, "generated_queue_run")
        self.assertEqual(branch.allowed_tools, ["generated_queue_run"])
        self.assertIn("Family: demo-family", branch.notes)
        self.assertIn("Rationale: HTTP and CLI diverged on the same followup.", branch.notes)

        tasks = work_tree.list_branch_tasks(branch.branch_id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].title, "run generated session subconscious_demo_family_turn.json")
        self.assertEqual(tasks[0].meta.get("session_file"), "subconscious_demo_family_turn.json")
        self.assertEqual(tasks[0].meta.get("family_id"), "demo-family")
        self.assertEqual(tasks[0].meta.get("variation_id"), "turn-1")

    def test_execute_generated_queue_planned_action_treats_reported_drift_as_completed_run(self):
        with mock.patch.object(
            autonomy_maintenance,
            "_run_test_session_definition",
            return_value=(
                False,
                "generated session drift",
                {
                    "latest_report": {
                        "status": "drift",
                        "run_id": "demo_run",
                        "report_path": "C:/Nova/runtime/test_sessions/reports/demo_run.json",
                    },
                    "stdout": "runner output tail",
                },
            ),
        ):
            result = autonomy_maintenance._execute_generated_queue_planned_action(
                "generated_queue_run",
                ["subconscious_demo_family_turn.json"],
            )

        self.assertTrue(result.get("ok"))
        self.assertFalse(result.get("runner_ok"))
        self.assertEqual(result.get("session_file"), "subconscious_demo_family_turn.json")
        self.assertEqual(result.get("report_status"), "drift")
        self.assertEqual(result.get("report_run_id"), "demo_run")
        self.assertEqual(
            result.get("report_path"),
            "C:/Nova/runtime/test_sessions/reports/demo_run.json",
        )

    def test_run_patch_queue_cleanup_records_reductions(self):
        state = {}
        before = {
            "previews_total": 20,
            "review_previews_total": 9,
            "review_previews_orphaned": 4,
            "review_previews_superseded_total": 6,
        }
        after = {
            "previews_total": 14,
            "review_previews_total": 5,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 2,
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", side_effect=[before, after]), \
             mock.patch.object(autonomy_maintenance, "service_patch_preview_summaries", side_effect=[[], [], []]), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_reject_orphaned_previews",
                 return_value={"ok": True, "count": 4, "failed": []},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_archive_superseded_previews",
                 return_value={"ok": True, "count": 3, "failed": [], "archive_dir": "C:/Nova/updates/previews/archive"},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_archive_preview_report",
                 return_value={"ok": True, "name": "archived.txt"},
             ):
            payload = autonomy_maintenance._run_patch_queue_cleanup(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("orphan_rejected_count"), 4)
        self.assertEqual(payload.get("superseded_archived_count"), 3)
        self.assertEqual(payload.get("review_total_before"), 9)
        self.assertEqual(payload.get("review_total_after"), 5)
        self.assertEqual(payload.get("orphaned_before"), 4)
        self.assertEqual(payload.get("orphaned_after"), 0)
        self.assertEqual(payload.get("superseded_before"), 6)
        self.assertEqual(payload.get("superseded_after"), 2)
        self.assertEqual((state.get("last_patch_cleanup") or {}).get("archive_dir"), "C:/Nova/updates/previews/archive")

    def test_auto_apply_if_eligible_skips_definition_only_zip_without_preview(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            zip_path = root / "autonomy_micro_patch_demo.zip"
            with autonomy_maintenance.zipfile.ZipFile(zip_path, "w", compression=autonomy_maintenance.zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("runtime/test_sessions/promoted/demo.json", "{}")
                archive.writestr("nova_patch.json", json.dumps({"patch_revision": 1}, ensure_ascii=True))

            with mock.patch.object(autonomy_maintenance.nova_core, "patch_preview") as preview_mock, \
                 mock.patch.object(autonomy_maintenance.nova_core, "execute_patch_action") as apply_mock:
                result = autonomy_maintenance._auto_apply_if_eligible(zip_path)

            self.assertEqual(result, "skipped_generated_definitions_require_review")
            preview_mock.assert_not_called()
            apply_mock.assert_not_called()

    def test_run_patch_queue_cleanup_rejects_definition_only_noop_preview(self):
        state = {}
        before = {
            "previews_total": 1,
            "previews": [{"name": "preview_noop.txt"}],
            "review_previews_total": 1,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 0,
        }
        after = {
            "previews_total": 1,
            "review_previews_total": 0,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 0,
        }
        noop_row = {
            "name": "preview_noop.txt",
            "path": "C:/Nova/updates/previews/preview_noop.txt",
            "status": "eligible",
            "decision": "pending",
            "artifact_state": "ok",
            "added_files": ["nova_patch.json"],
            "skipped_files": ["runtime/test_sessions/promoted/demo.json"],
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", side_effect=[before, after]), \
             mock.patch.object(autonomy_maintenance, "service_patch_preview_summaries", side_effect=[[noop_row], [], []]), \
             mock.patch.object(autonomy_maintenance.nova_core, "_record_approval", return_value=True) as record_mock, \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_reject_orphaned_previews",
                 return_value={"ok": True, "count": 0, "failed": []},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_archive_superseded_previews",
                 return_value={"ok": True, "count": 0, "failed": [], "archive_dir": ""},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_archive_preview_report",
                 return_value={"ok": True, "name": "archived.txt"},
             ):
            payload = autonomy_maintenance._run_patch_queue_cleanup(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("noop_rejected_count"), 1)
        self.assertEqual(payload.get("review_total_before"), 1)
        self.assertEqual(payload.get("review_total_after"), 0)
        record_mock.assert_called_once()

    def test_run_patch_queue_cleanup_archives_rejected_previews(self):
        state = {}
        before = {
            "previews_total": 3,
            "previews": [{"name": "preview_rejected.txt"}],
            "review_previews_total": 0,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 0,
        }
        after = {
            "previews_total": 2,
            "review_previews_total": 0,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 0,
        }
        rejected_row = {
            "name": "preview_rejected.txt",
            "path": "C:/Nova/updates/previews/preview_rejected.txt",
            "status": "eligible",
            "decision": "rejected",
            "artifact_state": "orphaned",
            "added_files": ["nova_patch.json"],
            "skipped_files": [],
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", side_effect=[before, after]), \
             mock.patch.object(autonomy_maintenance, "service_patch_preview_summaries", side_effect=[[], [rejected_row], []]), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_reject_orphaned_previews",
                 return_value={"ok": True, "count": 0, "failed": []},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_archive_superseded_previews",
                 return_value={"ok": True, "count": 0, "failed": [], "archive_dir": "C:/Nova/updates/previews/archive"},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_archive_preview_report",
                 return_value={"ok": True, "name": "preview_rejected.txt"},
             ) as archive_mock:
            payload = autonomy_maintenance._run_patch_queue_cleanup(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("rejected_archived_count"), 1)
        archive_mock.assert_called_once()

    def test_run_patch_queue_cleanup_archives_stale_noneligible_previews(self):
        state = {}
        before = {
            "previews_total": 3,
            "previews": [{"name": "preview_incompatible.txt"}],
            "review_previews_total": 0,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 0,
        }
        after = {
            "previews_total": 2,
            "review_previews_total": 0,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 0,
        }
        stale_row = {
            "name": "preview_incompatible.txt",
            "path": "C:/Nova/updates/previews/preview_incompatible.txt",
            "status": "rejected: incompatible base revision",
            "decision": "pending",
            "artifact_state": "ok",
            "added_files": ["nova_patch.json"],
            "skipped_files": ["runtime/test_sessions/promoted/demo.json"],
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", side_effect=[before, after]), \
             mock.patch.object(autonomy_maintenance, "service_patch_preview_summaries", side_effect=[[], [], [stale_row]]), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_reject_orphaned_previews",
                 return_value={"ok": True, "count": 0, "failed": []},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_archive_superseded_previews",
                 return_value={"ok": True, "count": 0, "failed": [], "archive_dir": "C:/Nova/updates/previews/archive"},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_archive_preview_report",
                 return_value={"ok": True, "name": "preview_incompatible.txt"},
             ) as archive_mock:
            payload = autonomy_maintenance._run_patch_queue_cleanup(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("stale_noneligible_archived_count"), 1)
        archive_mock.assert_called_once()

    def test_sync_patch_queue_work_tree_creates_apply_branch(self):
        self._isolated_work_tree_db()
        state = {}
        row = {
            "name": "preview_demo_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_demo_patch.zip.txt",
            "status": "eligible",
            "decision": "approved",
            "zip_name": "demo_patch.zip",
            "zip_exists": True,
            "zip_path": "C:/Nova/updates/demo_patch.zip",
            "artifact_state": "ok",
            "artifact_reason": "",
            "review_bucket": "approved",
            "collapsed_count": 1,
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", return_value={"review_previews": [row]}):
            payload = autonomy_maintenance._sync_patch_queue_work_tree(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("apply_ready_count"), 1)
        tree = work_tree.get_tree(str(payload.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id and str(branch.source_type or "") == autonomy_maintenance.PATCH_QUEUE_SOURCE_TYPE
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.title, "Apply preview: preview_demo_patch.zip.txt")
        self.assertEqual(branch.preferred_tool, "patch_preview_apply")
        self.assertEqual(list(branch.allowed_tools), autonomy_maintenance.PATCH_QUEUE_EXECUTE_TOOLS)
        tasks = work_tree.list_branch_tasks(branch.branch_id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].meta.get("patch_preview"), "preview_demo_patch.zip.txt")

    def test_sync_patch_queue_work_tree_selects_single_auto_approval_branch(self):
        self._isolated_work_tree_db()
        state = {}
        selected_row = {
            "name": "preview_selected_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_selected_patch.zip.txt",
            "status": "eligible",
            "decision": "pending",
            "zip_name": "selected_patch.zip",
            "zip_exists": True,
            "artifact_state": "ok",
            "review_bucket": "pending",
            "preview_kind": "autonomy_micro_patch",
            "patch_revision": "4",
            "min_base_revision": "3",
            "mtime": 5,
        }
        other_row = {
            "name": "preview_other_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_other_patch.zip.txt",
            "status": "eligible",
            "decision": "pending",
            "zip_name": "other_patch.zip",
            "zip_exists": True,
            "artifact_state": "ok",
            "review_bucket": "pending",
            "preview_kind": "teach_proposal",
            "patch_revision": "4",
            "min_base_revision": "3",
            "mtime": 9,
        }

        with mock.patch.object(
            autonomy_maintenance.nova_core,
            "patch_status_payload",
            return_value={"current_revision": 3, "review_previews": [other_row, selected_row]},
        ):
            payload = autonomy_maintenance._sync_patch_queue_work_tree(state)

        self.assertEqual(payload.get("approve_ready_count"), 1)
        self.assertEqual(payload.get("pending_count"), 1)
        tree = work_tree.get_tree(str(payload.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id and str(branch.source_type or "") == autonomy_maintenance.PATCH_QUEUE_SOURCE_TYPE
        ]
        self.assertEqual(len(branches), 2)
        approve_branch = next(branch for branch in branches if branch.title.startswith("Approve preview:"))
        review_branch = next(branch for branch in branches if branch.title.startswith("Review preview:"))
        self.assertEqual(approve_branch.title, "Approve preview: preview_selected_patch.zip.txt")
        self.assertEqual(approve_branch.preferred_tool, "patch_preview_approve")
        self.assertEqual(list(approve_branch.allowed_tools), autonomy_maintenance.PATCH_QUEUE_EXECUTE_TOOLS)
        self.assertIn("auto-approval lane", str(approve_branch.notes or "").lower())
        approve_tasks = work_tree.list_branch_tasks(approve_branch.branch_id)
        self.assertEqual(len(approve_tasks), 1)
        self.assertEqual(approve_tasks[0].meta.get("patch_preview"), "preview_selected_patch.zip.txt")
        self.assertEqual(review_branch.preferred_tool, "find")

    def test_decide_patch_queue_next_step_prefers_apply_then_approve(self):
        self._isolated_work_tree_db()
        tree = work_tree.initialize_tree("Patch Queue: governed review and apply")
        apply_branch = work_tree.add_branch_to_tree(tree.tree_id, "Apply preview: apply.txt", "patch_queue", tree.root_branch_id)
        approve_branch = work_tree.add_branch_to_tree(tree.tree_id, "Approve preview: approve.txt", "patch_queue", tree.root_branch_id)
        review_branch = work_tree.add_branch_to_tree(tree.tree_id, "Review preview: review.txt", "patch_queue", tree.root_branch_id)
        apply_branch.priority = 90
        approve_branch.priority = 80
        review_branch.priority = 95

        decision = autonomy_maintenance._decide_patch_queue_next_step(
            tree.tree_id,
            [
                {"branch_id": review_branch.branch_id, "recommended_tool": "find"},
                {"branch_id": approve_branch.branch_id, "recommended_tool": "patch_preview_approve"},
                {"branch_id": apply_branch.branch_id, "recommended_tool": "patch_preview_apply"},
            ],
        )
        self.assertEqual(decision.get("branch_id"), apply_branch.branch_id)

        decision = autonomy_maintenance._decide_patch_queue_next_step(
            tree.tree_id,
            [
                {"branch_id": review_branch.branch_id, "recommended_tool": "find"},
                {"branch_id": approve_branch.branch_id, "recommended_tool": "patch_preview_approve"},
            ],
        )
        self.assertEqual(decision.get("branch_id"), approve_branch.branch_id)

    def test_sync_patch_queue_work_tree_reuses_branch_when_preview_transitions(self):
        self._isolated_work_tree_db()
        state = {}
        pending_row = {
            "name": "preview_transition_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_transition_patch.zip.txt",
            "status": "eligible",
            "decision": "pending",
            "zip_name": "transition_patch.zip",
            "zip_exists": True,
            "artifact_state": "ok",
            "review_bucket": "pending",
        }
        approved_row = dict(pending_row)
        approved_row["decision"] = "approved"
        approved_row["review_bucket"] = "approved"

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", return_value={"review_previews": [pending_row]}):
            first = autonomy_maintenance._sync_patch_queue_work_tree(state)
        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", return_value={"review_previews": [approved_row]}):
            second = autonomy_maintenance._sync_patch_queue_work_tree(state)

        self.assertEqual(first.get("created_count"), 1)
        self.assertEqual(second.get("updated_count"), 1)
        tree = work_tree.get_tree(str(second.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id and str(branch.source_type or "") == autonomy_maintenance.PATCH_QUEUE_SOURCE_TYPE
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.title, "Apply preview: preview_transition_patch.zip.txt")
        self.assertEqual(branch.preferred_tool, "patch_preview_apply")
        self.assertGreaterEqual(int(branch.evidence_count or 0), 2)
        tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if str(getattr(getattr(task, "status", None), "value", task.status) or "").strip().lower() not in {"complete", "dropped"}
        ]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].meta.get("patch_preview"), "preview_transition_patch.zip.txt")

    def test_run_patch_queue_work_tree_cycle_records_execution(self):
        self._isolated_work_tree_db()
        state = {}
        row = {
            "name": "preview_cycle_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_cycle_patch.zip.txt",
            "status": "eligible",
            "decision": "approved",
            "zip_name": "cycle_patch.zip",
            "zip_exists": True,
            "artifact_state": "ok",
            "review_bucket": "approved",
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", return_value={"review_previews": [row]}):
            sync_payload = autonomy_maintenance._sync_patch_queue_work_tree(state)

        def _execute(tool_name, tool_args=None):
            self.assertEqual(tool_name, "patch_preview_apply")
            self.assertEqual(tool_args, ["preview_cycle_patch.zip.txt"])
            return {"ok": True, "message": "patch_preview_apply_ok"}

        with mock.patch.object(autonomy_maintenance.nova_core, "execute_planned_action", side_effect=_execute), \
             mock.patch.object(
                 autonomy_maintenance,
                 "_sync_patch_queue_work_tree",
                 return_value={
                     "ts": "2026-04-23 00:00:00",
                     "status": "ok",
                     "tree_id": str(sync_payload.get("tree_id") or ""),
                     "tree_title": "Patch Queue",
                     "apply_ready_count": 0,
                     "approve_ready_count": 0,
                     "pending_count": 0,
                     "orphaned_count": 0,
                 },
             ):
            cycle_payload = autonomy_maintenance._run_patch_queue_work_tree_cycle(state)

        self.assertEqual(sync_payload.get("apply_ready_count"), 1)
        self.assertEqual(cycle_payload.get("status"), "ok")
        self.assertEqual(cycle_payload.get("executed_count"), 1)
        self.assertEqual(cycle_payload.get("tree_count"), 1)
        inspect = work_tree.inspect_tree(str(sync_payload.get("tree_id") or ""))
        self.assertIsNotNone(inspect)
        self.assertEqual(inspect.get("counts", {}).get("tasks", {}).get("open"), 0)

    def test_run_active_work_tree_cycle_executes_safe_tree_and_skips_unsafe_tool(self):
        self._isolated_work_tree_db()
        state = {}
        safe_tree = work_tree.initialize_tree(
            "Cli: check queue status",
            meta={"kind": "system", "source": "cli"},
        )
        safe_root = work_tree._BRANCHES[safe_tree.root_branch_id]
        work_tree.add_task_to_branch(safe_root.branch_id, "check queue status")
        work_tree.set_branch_tools(safe_root.branch_id, allowed_tools=["queue_status"], preferred_tool="queue_status")

        unsafe_tree = work_tree.initialize_tree(
            "Cli: update runtime state",
            meta={"kind": "system", "source": "cli"},
        )
        unsafe_root = work_tree._BRANCHES[unsafe_tree.root_branch_id]
        work_tree.add_task_to_branch(unsafe_root.branch_id, "update runtime status accordingly")
        work_tree.set_branch_tools(unsafe_root.branch_id, allowed_tools=["update_now"], preferred_tool="update_now")

        with mock.patch.object(autonomy_maintenance.nova_core, "execute_planned_action", return_value="Queue is empty."):
            payload = autonomy_maintenance._run_active_work_tree_cycle(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("executed_count"), 1)
        self.assertEqual(payload.get("tree_count"), 2)
        self.assertEqual(payload.get("skipped_tree_count"), 1)
        skipped = payload.get("skipped") or []
        self.assertEqual(skipped[0].get("tool"), "update_now")
        safe_inspect = work_tree.inspect_tree(safe_tree.tree_id)
        unsafe_inspect = work_tree.inspect_tree(unsafe_tree.tree_id)
        self.assertEqual(safe_inspect.get("status"), "complete")
        self.assertEqual(unsafe_inspect.get("status"), "active")
        self.assertEqual((state.get("last_active_work_tree_cycle") or {}).get("executed_count"), 1)

    def test_run_active_work_tree_cycle_executes_core_thinning_lane(self):
        self._isolated_work_tree_db()
        state = {}
        thinning_tree = work_tree.initialize_tree(
            "Core Thinning",
            meta={"kind": "core_thinning", "source": "core_thinning", "work_identity_key": "system:core-thinning"},
        )
        root = work_tree._BRANCHES[thinning_tree.root_branch_id]
        work_tree.add_task_to_branch(
            root.branch_id,
            "thin wrapper shim",
            meta={
                "scope": "single_block_only",
                "target": {
                    "file": "C:/Nova/nova_core.py",
                    "function": "_wrapper_shim",
                    "block": "wrapper_candidate",
                    "name": "_wrapper_shim",
                    "start_line": 10,
                    "end_line": 12,
                },
            },
        )
        work_tree.set_branch_tools(root.branch_id, allowed_tools=["core_thinning"], preferred_tool="core_thinning")

        calls = []

        def _execute(tool_name, tool_args=None):
            calls.append((tool_name, list(tool_args or [])))
            return {"ok": True, "scope_ok": True, "verified": True, "message": "core_thinning_checked"}

        with mock.patch.object(autonomy_maintenance.nova_core, "execute_planned_action", side_effect=_execute):
            payload = autonomy_maintenance._run_active_work_tree_cycle(state, max_steps=1, max_trees=1)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("executed_count"), 1)
        self.assertEqual(payload.get("skipped_tree_count"), 0)
        self.assertEqual(calls[0][0], "core_thinning")
        self.assertIn("_wrapper_shim", calls[0][1][0])
        self.assertEqual((state.get("last_active_work_tree_cycle") or {}).get("executed_count"), 1)

    def test_work_tree_snapshot_uses_active_candidate_execution_truth(self):
        snapshot = autonomy_maintenance._work_tree_snapshot_for_orchestrator(
            {"counts": {"active": 30, "open_tasks": 95, "blocked": 37}},
            [
                {
                    "tree_id": "tree-core",
                    "title": "Core Thinning",
                    "status": "active",
                    "kind": "core_thinning",
                    "next_step": {
                        "branch_id": "branch-core",
                        "branch_title": "Review wrapper shim",
                        "recommended_tool": "core_thinning",
                    },
                },
                {
                    "tree_id": "tree-update",
                    "title": "Cli: update runtime",
                    "status": "active",
                    "kind": "system",
                    "next_step": {
                        "branch_id": "branch-update",
                        "branch_title": "Update now",
                        "recommended_tool": "update_now",
                    },
                },
            ],
        )

        self.assertEqual(snapshot.get("active_candidate_count"), 2)
        self.assertEqual(snapshot.get("active_executable_count"), 1)
        self.assertEqual(snapshot.get("active_unsafe_count"), 1)
        self.assertEqual((snapshot.get("branches") or [])[0].get("recommended_tool"), "core_thinning")
        self.assertTrue((snapshot.get("branches") or [])[0].get("executable"))
        self.assertFalse((snapshot.get("branches") or [])[1].get("executable"))

    def test_retire_legacy_patch_update_trees_drops_open_tasks_and_completes_tree(self):
        self._isolated_work_tree_db()
        state = {}
        legacy_tree = work_tree.initialize_tree(
            "Cli: please patch apply updates.zip",
            meta={"kind": "system", "source": "cli"},
        )
        legacy_root = work_tree._BRANCHES[legacy_tree.root_branch_id]
        task = work_tree.add_task_to_branch(legacy_root.branch_id, "please patch apply updates.zip")
        work_tree.set_branch_tools(legacy_root.branch_id, allowed_tools=["patch_apply"], preferred_tool="patch_apply")

        safe_tree = work_tree.initialize_tree(
            "Cli: check queue status",
            meta={"kind": "system", "source": "cli"},
        )
        safe_root = work_tree._BRANCHES[safe_tree.root_branch_id]
        work_tree.add_task_to_branch(safe_root.branch_id, "check queue status")
        work_tree.set_branch_tools(safe_root.branch_id, allowed_tools=["queue_status"], preferred_tool="queue_status")

        payload = autonomy_maintenance._retire_legacy_patch_update_trees(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("retired_count"), 1)
        legacy_inspect = work_tree.inspect_tree(legacy_tree.tree_id)
        safe_inspect = work_tree.inspect_tree(safe_tree.tree_id)
        self.assertEqual(legacy_inspect.get("status"), "complete")
        self.assertEqual((legacy_inspect.get("counts") or {}).get("tasks", {}).get("dropped"), 1)
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.DROPPED)
        self.assertEqual(safe_inspect.get("status"), "active")
        ready_branches = legacy_inspect.get("ready_branches") or []
        self.assertFalse(ready_branches)
        self.assertEqual((state.get("last_legacy_tree_retirement") or {}).get("retired_count"), 1)

    def test_run_patch_queue_work_tree_cycle_resyncs_from_approve_into_apply(self):
        state = {
            "last_patch_queue_sync": {
                "ts": "2026-04-23 00:00:00",
                "status": "ok",
                "tree_id": "tree_demo",
                "tree_title": "Patch Queue",
                "apply_ready_count": 0,
                "approve_ready_count": 1,
            }
        }

        with mock.patch.object(
            autonomy_maintenance.work_tree,
            "run_autonomous_loop",
            side_effect=[
                [{"action": "executed", "tool": "patch_preview_approve"}],
                [{"action": "executed", "tool": "patch_preview_apply"}],
            ],
        ) as run_loop_mock, \
            mock.patch.object(
                autonomy_maintenance,
                "_sync_patch_queue_work_tree",
                side_effect=[
                    {
                        "ts": "2026-04-23 00:00:01",
                        "status": "ok",
                        "tree_id": "tree_demo",
                        "tree_title": "Patch Queue",
                        "apply_ready_count": 1,
                        "approve_ready_count": 0,
                    },
                    {
                        "ts": "2026-04-23 00:00:02",
                        "status": "ok",
                        "tree_id": "tree_demo",
                        "tree_title": "Patch Queue",
                        "apply_ready_count": 0,
                        "approve_ready_count": 0,
                    },
                ],
            ):
            cycle_payload = autonomy_maintenance._run_patch_queue_work_tree_cycle(state)

        self.assertEqual(run_loop_mock.call_count, 2)
        self.assertEqual(cycle_payload.get("status"), "ok")
        self.assertEqual(cycle_payload.get("executed_count"), 2)
        self.assertEqual(cycle_payload.get("apply_ready_count"), 0)
        self.assertEqual(cycle_payload.get("approve_ready_count"), 0)
        self.assertEqual(len(cycle_payload.get("history") or []), 2)

    def test_sync_patch_queue_work_tree_reuses_legacy_seeded_branch(self):
        self._isolated_work_tree_db()
        state = {}
        tree = work_tree.initialize_tree(
            "Patch Queue: approved preview apply",
            meta={
                "kind": "system",
                "source": "autonomy",
                "patch_queue": True,
                "execution_policy": {
                    "allowed_tools": ["patch_preview_apply", "patch_rollback"],
                    "require_explicit_allow": True,
                },
            },
        )
        legacy_branch = work_tree.add_branch_to_tree(
            tree.tree_id,
            "Apply preview: preview_legacy_patch.zip.txt",
            "patch_queue",
            tree.root_branch_id,
        )
        legacy_branch.allowed_tools = ["patch_preview_apply", "patch_rollback"]
        legacy_branch.preferred_tool = "patch_rollback"
        work_tree.add_task_to_branch(
            legacy_branch.branch_id,
            "apply approved preview preview_legacy_patch.zip.txt",
        )
        work_tree.touch_branch(legacy_branch.branch_id)

        row = {
            "name": "preview_legacy_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_legacy_patch.zip.txt",
            "status": "eligible",
            "decision": "approved",
            "zip_name": "legacy_patch.zip",
            "zip_exists": True,
            "artifact_state": "ok",
            "review_bucket": "approved",
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", return_value={"review_previews": [row]}):
            payload = autonomy_maintenance._sync_patch_queue_work_tree(state)

        self.assertEqual(payload.get("created_count"), 0)
        self.assertEqual(payload.get("updated_count"), 1)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id and autonomy_maintenance._is_patch_queue_managed_branch(tree, branch)
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.branch_id, legacy_branch.branch_id)
        self.assertEqual(branch.source_type, autonomy_maintenance.PATCH_QUEUE_SOURCE_TYPE)
        self.assertEqual(branch.source_key, "patch_preview::preview_legacy_patch.zip.txt")
        self.assertEqual(branch.preferred_tool, "patch_preview_apply")

    def test_sync_patch_queue_work_tree_keeps_incompatible_base_preview_in_review_lane(self):
        self._isolated_work_tree_db()
        state = {}
        row = {
            "name": "preview_base_mismatch_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_base_mismatch_patch.zip.txt",
            "status": "eligible",
            "decision": "approved",
            "zip_name": "base_mismatch_patch.zip",
            "zip_exists": True,
            "artifact_state": "ok",
            "review_bucket": "approved",
            "min_base_revision": "4",
        }

        with mock.patch.object(
            autonomy_maintenance.nova_core,
            "patch_status_payload",
            return_value={"current_revision": 3, "review_previews": [row]},
        ):
            payload = autonomy_maintenance._sync_patch_queue_work_tree(state)

        self.assertEqual(payload.get("apply_ready_count"), 0)
        tree = work_tree.get_tree(str(payload.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id and str(branch.source_type or "") == autonomy_maintenance.PATCH_QUEUE_SOURCE_TYPE
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.title, "Review preview: preview_base_mismatch_patch.zip.txt")
        self.assertEqual(branch.preferred_tool, "find")
        self.assertEqual(list(branch.allowed_tools), autonomy_maintenance.PATCH_QUEUE_REVIEW_TOOLS)
        self.assertIn("waiting for the required patch revision", str(branch.notes or "").lower())

        cycle_payload = autonomy_maintenance._run_patch_queue_work_tree_cycle(state)
        self.assertEqual(cycle_payload.get("status"), "idle")
        self.assertEqual(cycle_payload.get("reason"), "no_apply_ready_preview")


if __name__ == "__main__":
    unittest.main()
