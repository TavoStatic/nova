from __future__ import annotations

import os
from pathlib import Path
import unittest
import uuid

import work_tree
from services.core_thinning import (
    CORE_THINNING_WORK_IDENTITY,
    build_core_thinning_brief,
    build_core_thinning_owner_verdict,
    execute_core_thinning_order,
    feed_core_thinning_brief_to_work_tree,
)
from services.recurring_finding_lifecycle import summarize_feed_pressure


def _validation_tmp_root() -> Path:
    return Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "_test_tmp"


class TestCoreThinningService(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = _validation_tmp_root()
        base_tmp.mkdir(parents=True, exist_ok=True)
        self._db_path = base_tmp / f"core_thinning_{uuid.uuid4().hex}.sqlite3"
        work_tree._set_db_path(self._db_path)

    def tearDown(self) -> None:
        for path in (self._db_path, self._db_path.with_name(f"{self._db_path.name}-journal")):
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass

    def test_build_brief_finds_wrapper_and_large_function_candidates(self):
        sample = _validation_tmp_root() / f"core_thinning_sample_{uuid.uuid4().hex}.py"
        sample.write_text(
            "\n".join(
                [
                    "def wrapper():",
                    "    return service_demo()",
                    "",
                    "def large():",
                    *["    x = 1" for _ in range(12)],
                ]
            ),
            encoding="utf-8",
        )
        try:
            brief = build_core_thinning_brief(sample, large_function_threshold=10)
        finally:
            sample.unlink(missing_ok=True)

        self.assertTrue(brief.get("ok"))
        self.assertEqual(brief.get("wrapper_candidate_count"), 1)
        self.assertEqual(brief.get("large_function_count"), 1)
        self.assertGreaterEqual(brief.get("order_count"), 2)

    def test_build_brief_can_cover_core_and_http_surfaces(self):
        sample_core = _validation_tmp_root() / f"core_thinning_core_{uuid.uuid4().hex}.py"
        sample_http = _validation_tmp_root() / f"core_thinning_http_{uuid.uuid4().hex}.py"
        sample_core.write_text("def core_wrapper():\n    return service_core()\n", encoding="utf-8")
        sample_http.write_text("def http_wrapper():\n    return service_http()\n", encoding="utf-8")
        try:
            brief = build_core_thinning_brief([sample_core, sample_http])
        finally:
            sample_core.unlink(missing_ok=True)
            sample_http.unlink(missing_ok=True)

        self.assertTrue(brief.get("ok"))
        self.assertEqual(brief.get("wrapper_candidate_count"), 2)
        self.assertEqual(len(list(brief.get("files") or [])), 2)
        targets = [dict(item.get("target") or {}) for item in list(brief.get("orders") or [])]
        self.assertEqual({Path(str(item.get("file") or "")).name for item in targets}, {sample_core.name, sample_http.name})

    def test_build_brief_finds_http_surface_candidates(self):
        sample_http = _validation_tmp_root() / f"nova_http_surface_{uuid.uuid4().hex}.py"
        sample_http.write_text(
            "\n".join(
                [
                    "def _pipeline_create_action(payload):",
                    *["    value = 1" for _ in range(10)],
                    "    return True, '', {}, ''",
                    "",
                    "def _pipeline_start_action(payload):",
                    *["    value = 1" for _ in range(10)],
                    "    return True, '', {}, ''",
                    "",
                    "def _pipeline_pause_action(payload):",
                    *["    value = 1" for _ in range(10)],
                    "    return True, '', {}, ''",
                    "",
                    "def _pipeline_archive_action(payload):",
                    *["    value = 1" for _ in range(10)],
                    "    return True, '', {}, ''",
                ]
            ),
            encoding="utf-8",
        )
        try:
            brief = build_core_thinning_brief(sample_http)
        finally:
            sample_http.unlink(missing_ok=True)

        self.assertTrue(brief.get("ok"))
        self.assertEqual(brief.get("http_surface_candidate_count"), 1)
        order = next(item for item in list(brief.get("orders") or []) if item.get("kind") == "http_surface_candidate")
        extract = next(item for item in list(brief.get("orders") or []) if item.get("kind") == "http_surface_extract")
        self.assertEqual((order.get("target") or {}).get("theme"), "pipeline_control")
        self.assertIn("non-shim", str(order.get("reason") or ""))
        self.assertEqual((extract.get("target") or {}).get("block"), "http_surface_extract")

    def test_build_brief_ignores_pure_http_delegation_shims(self):
        """Already-extracted service shims must not invent HTTP extraction pressure."""
        sample_http = _validation_tmp_root() / f"nova_http_shims_{uuid.uuid4().hex}.py"
        sample_http.write_text(
            "\n".join(
                [
                    "def _pipeline_create_action(payload):",
                    "    return CONTROL_PIPELINES_SERVICE.create(payload)",
                    "",
                    "def _pipeline_start_action(payload):",
                    "    return CONTROL_PIPELINES_SERVICE.start(payload)",
                    "",
                    "def _pipeline_pause_action(payload):",
                    "    return CONTROL_PIPELINES_SERVICE.pause(payload)",
                    "",
                    "def _pipeline_archive_action(payload):",
                    "    return CONTROL_PIPELINES_SERVICE.archive(payload)",
                    "",
                    "def _pipeline_update_action(payload):",
                    "    return CONTROL_PIPELINES_SERVICE.update(payload)",
                    "",
                    "def _runtime_timeline_payload(limit=24):",
                    "    return RUNTIME_TIMELINE_SERVICE.payload(limit=limit)",
                    "",
                    "def _runtime_artifacts_payload():",
                    "    return RUNTIME_ARTIFACTS_SERVICE.payload()",
                    "",
                    "def _runtime_artifact_show_action(payload):",
                    "    return RUNTIME_CONTROL_SERVICE.show(payload)",
                    "",
                    "def _guard_control_action(payload):",
                    "    return RUNTIME_CONTROL_SERVICE.guard(payload)",
                ]
            ),
            encoding="utf-8",
        )
        try:
            brief = build_core_thinning_brief(sample_http)
        finally:
            sample_http.unlink(missing_ok=True)

        self.assertTrue(brief.get("ok"))
        self.assertEqual(brief.get("http_surface_candidate_count"), 0)
        self.assertEqual(
            [item for item in list(brief.get("orders") or []) if item.get("kind") == "http_surface_candidate"],
            [],
        )

    def test_owner_verdict_surfaces_lifecycle_gap_when_pressure_is_not_executable(self):
        verdict = build_core_thinning_owner_verdict(
            {
                "ok": True,
                "order_count": 8,
                "line_count": 1200,
                "function_count": 80,
            },
            feed_result={
                "ok": True,
                "status": "deduped",
                "executable_count": 0,
                "reopened_count": 0,
                "satisfied_count": 0,
                "satisfied_active_count": 0,
            },
        )

        evidence = dict(verdict.get("evidence") or {})
        self.assertEqual(evidence.get("lifecycle_gap"), "pressure_without_executable_work")
        self.assertIn("0 executable", str((verdict.get("blockers") or [{}])[0].get("detail") or ""))

    def test_owner_verdict_keeps_lifecycle_gap_when_only_witnessed_http_mapping(self):
        verdict = build_core_thinning_owner_verdict(
            {
                "ok": True,
                "order_count": 8,
                "line_count": 1200,
                "function_count": 80,
            },
            feed_result={
                "ok": True,
                "status": "reopened",
                "executable_count": 0,
                "reopened_count": 8,
                "satisfied_count": 0,
                "satisfied_active_count": 0,
            },
        )

        evidence = dict(verdict.get("evidence") or {})
        self.assertEqual(evidence.get("lifecycle_gap"), "pressure_without_executable_work")
        self.assertEqual(int(evidence.get("unresolved_pressure_count", 0) or 0), 8)

    def test_owner_verdict_clears_lifecycle_gap_after_productive_wrapper_removal(self):
        verdict = build_core_thinning_owner_verdict(
            {
                "ok": True,
                "order_count": 1,
                "line_count": 40,
                "function_count": 2,
            },
            feed_result={
                "ok": True,
                "status": "deduped",
                "executable_count": 0,
                "reopened_count": 0,
                "satisfied_count": 1,
                "satisfied_active_count": 1,
            },
        )

        evidence = dict(verdict.get("evidence") or {})
        self.assertFalse(evidence.get("lifecycle_gap"))
        self.assertEqual(int(evidence.get("unresolved_pressure_count", -1)), 0)

    def test_owner_verdict_marks_thinning_orders_as_non_green_blocking_pressure(self):
        verdict = build_core_thinning_owner_verdict(
            {
                "ok": True,
                "order_count": 3,
                "line_count": 1200,
                "function_count": 80,
                "large_function_count": 2,
                "http_surface_candidate_count": 1,
                "wrapper_candidate_count": 0,
            },
            feed_result={"ok": True, "status": "seeded"},
        )

        self.assertEqual(verdict.get("owner"), "core_thinning")
        self.assertFalse(verdict.get("ready"))
        self.assertFalse(verdict.get("blocks_green"))
        self.assertEqual((verdict.get("blockers") or [])[0].get("code"), "core_http_thinning_pressure")

    def test_owner_verdict_blocks_green_when_thinning_evidence_is_unavailable(self):
        verdict = build_core_thinning_owner_verdict(
            {"ok": False, "error": "parse failed"},
            feed_result={"ok": False, "status": "failed"},
        )

        self.assertFalse(verdict.get("ready"))
        self.assertTrue(verdict.get("blocks_green"))
        self.assertEqual((verdict.get("blockers") or [])[0].get("code"), "core_thinning_unavailable")

    def test_feed_closes_http_mapping_and_keeps_extract_executable(self):
        sample_http = _validation_tmp_root() / "nova_http.py"
        source = "\n".join(
            [
                "def _pipeline_create_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_start_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_pause_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_archive_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
            ]
        )
        sample_http.write_text(source, encoding="utf-8")
        try:
            brief = build_core_thinning_brief(sample_http)
            order = next(item for item in list(brief.get("orders") or []) if item.get("kind") == "http_surface_candidate")
            from services.core_thinning import _order_satisfaction_key, stamp_core_thinning_task_satisfaction

            feed_fingerprint = _order_satisfaction_key(order)
            self.assertGreater(len(str(order.get("reason") or "")), 40)
            first = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
            task = work_tree.list_tree_tasks(str(first.get("tree_id")))[0]
            self.assertEqual(str((task.meta or {}).get("reason") or ""), str(order.get("reason") or ""))
            result = execute_core_thinning_order({"target": order["target"]})
            stamp_core_thinning_task_satisfaction(task, result)
            stamped_fingerprint = str((task.meta or {}).get("recurring_finding_satisfaction_fingerprint") or "")
            self.assertEqual(stamped_fingerprint, feed_fingerprint)
            work_tree.mark_task_complete(task.task_id)
            second = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
        finally:
            sample_http.unlink(missing_ok=True)

        self.assertEqual(second.get("reopened_count"), 0)
        self.assertGreaterEqual(int(second.get("satisfied_active_count") or 0), 1)
        extract_tasks = [
            task
            for task in work_tree.list_tree_tasks(str(first.get("tree_id")))
            if str((task.meta or {}).get("kind") or "") == "http_surface_extract"
        ]
        self.assertTrue(extract_tasks)
        self.assertEqual(
            str(getattr(getattr(extract_tasks[0], "status", None), "value", getattr(extract_tasks[0], "status", ""))).lower(),
            "complete",
        )
        self.assertEqual(
            str((extract_tasks[0].meta or {}).get("recurring_finding_completion_action") or ""),
            "blocked_http_extraction",
        )
        self.assertEqual(
            sum(
                1
                for task in extract_tasks
                if str(getattr(getattr(task, "status", None), "value", getattr(task, "status", ""))).lower()
                not in {"complete", "dropped"}
            ),
            0,
        )
        self.assertFalse((summarize_feed_pressure(pressure_count=2, feed_result=second) or {}).get("lifecycle_gap"))

    def test_feed_does_not_recreate_mapping_when_theme_already_closed(self):
        from services.core_thinning import _target_semantic_key
        from services.recurring_finding_lifecycle import KEY_FINDING, stamp_satisfaction

        sample_http = _validation_tmp_root() / "nova_http.py"
        source = "\n".join(
            [
                "def _pipeline_create_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_start_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_pause_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_archive_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
            ]
        )
        sample_http.write_text(source, encoding="utf-8")
        try:
            brief = build_core_thinning_brief(sample_http)
            mapping = next(item for item in list(brief.get("orders") or []) if item.get("kind") == "http_surface_candidate")
            first = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
            tree_id = str(first.get("tree_id"))
            mapping_task = next(
                task
                for task in work_tree.list_tree_tasks(tree_id)
                if str((task.meta or {}).get("kind") or "") == "http_surface_candidate"
            )
            mapping_task.meta = stamp_satisfaction(
                dict(mapping_task.meta or {}),
                satisfaction_fingerprint="legacy-cluster-fp",
                completion_action="witnessed_http_extraction_boundary",
            )
            mapping_task.meta[KEY_FINDING] = "core_thinning:legacy-chat-sessions-cluster-1"
            mapping_task.meta["target"] = {
                **dict((mapping.get("target") or {}) if isinstance(mapping.get("target"), dict) else {}),
                "name": "http:chat_sessions:1",
                "cluster": 1,
            }
            work_tree.mark_task_complete(mapping_task.task_id)
            second = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
            mapping_tasks = [
                task
                for task in work_tree.list_tree_tasks(tree_id)
                if str((task.meta or {}).get("kind") or "") == "http_surface_candidate"
                and str(getattr(getattr(task, "status", None), "value", getattr(task, "status", ""))).lower()
                not in {"dropped"}
            ]
        finally:
            sample_http.unlink(missing_ok=True)

        self.assertEqual(second.get("reopened_count"), 0)
        self.assertEqual(len(mapping_tasks), 1)
        self.assertEqual(
            _target_semantic_key("http_surface_candidate", mapping.get("target") if isinstance(mapping.get("target"), dict) else {}),
            _target_semantic_key("http_surface_candidate", (mapping_tasks[0].meta or {}).get("target") if isinstance((mapping_tasks[0].meta or {}).get("target"), dict) else {}),
        )

    def test_feed_does_not_reopen_extract_after_operator_do_not_retry(self):
        from services.recurring_finding_lifecycle import stamp_satisfaction

        sample_http = _validation_tmp_root() / "nova_http.py"
        source = "\n".join(
            [
                "def _pipeline_create_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_start_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_pause_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_archive_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
            ]
        )
        sample_http.write_text(source, encoding="utf-8")
        try:
            brief = build_core_thinning_brief(sample_http)
            first = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
            tree_id = str(first.get("tree_id"))
            extract_task = next(
                task
                for task in work_tree.list_tree_tasks(tree_id)
                if str((task.meta or {}).get("kind") or "") == "http_surface_extract"
            )
            extract_task.meta = stamp_satisfaction(
                dict(extract_task.meta or {}),
                satisfaction_fingerprint="extract-closed",
                completion_action="operator_do_not_retry",
            )
            work_tree.mark_task_complete(extract_task.task_id)
            second = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
            extract_tasks = [
                task
                for task in work_tree.list_tree_tasks(tree_id)
                if str((task.meta or {}).get("kind") or "") == "http_surface_extract"
            ]
        finally:
            sample_http.unlink(missing_ok=True)

        self.assertEqual(second.get("reopened_count"), 0)
        self.assertEqual(len(extract_tasks), 1)
        self.assertEqual(
            str(getattr(getattr(extract_tasks[0], "status", None), "value", getattr(extract_tasks[0], "status", ""))).lower(),
            "complete",
        )

    def test_feed_repairs_legacy_task_missing_reason_before_productive_closure_check(self):
        sample_http = _validation_tmp_root() / "nova_http.py"
        source = "\n".join(
            [
                "def _pipeline_create_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_start_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_pause_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_archive_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
            ]
        )
        sample_http.write_text(source, encoding="utf-8")
        try:
            from services.core_thinning import _order_satisfaction_key, stamp_core_thinning_task_satisfaction
            from services.recurring_finding_lifecycle import stamp_satisfaction

            brief = build_core_thinning_brief(sample_http)
            order = next(item for item in list(brief.get("orders") or []) if item.get("kind") == "http_surface_candidate")
            feed_fingerprint = _order_satisfaction_key(order)
            first = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
            task = work_tree.list_tree_tasks(str(first.get("tree_id")))[0]
            task.meta.pop("reason", None)
            task.meta = stamp_satisfaction(
                dict(task.meta or {}),
                satisfaction_fingerprint="legacy-missing-reason",
                completion_action="mapped_http_extraction_boundary",
            )
            work_tree.mark_task_complete(task.task_id)
            second = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
            repaired = work_tree.list_tree_tasks(str(first.get("tree_id")))[0]
        finally:
            sample_http.unlink(missing_ok=True)

        self.assertEqual(second.get("reopened_count"), 0)
        self.assertGreaterEqual(int(second.get("satisfied_active_count") or 0), 1)
        self.assertEqual(str((repaired.meta or {}).get("reason") or ""), str(order.get("reason") or ""))
        self.assertEqual(
            str((repaired.meta or {}).get("recurring_finding_completion_action") or ""),
            "mapped_http_extraction_boundary",
        )

    def test_feed_reopens_completed_order_when_pressure_recurs(self):
        sample = _validation_tmp_root() / f"core_thinning_reopen_{uuid.uuid4().hex}.py"
        sample.write_text("def wrapper():\n    return service_demo()\n", encoding="utf-8")
        try:
            brief = build_core_thinning_brief(sample)
            brief["generated_at"] = "2026-07-13 10:00:00"
        finally:
            sample.unlink(missing_ok=True)

        first = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
        task = work_tree.list_tree_tasks(str(first.get("tree_id")))[0]
        work_tree.mark_task_complete(task.task_id)

        second = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)

        self.assertEqual(second.get("reopened_count"), 1)
        self.assertEqual(second.get("executable_count"), 1)
        self.assertEqual(second.get("status"), "reopened")
        reopened_task = work_tree.list_tree_tasks(str(first.get("tree_id")))[0]
        self.assertEqual(str(getattr(getattr(reopened_task, "status", None), "value", getattr(reopened_task, "status", ""))).lower(), "open")
        self.assertEqual(int((reopened_task.meta or {}).get("recurring_finding_version", 0)), 2)
        self.assertEqual((reopened_task.meta or {}).get("recurring_finding_reopened_reason"), "recurring_pressure")

    def test_feed_marks_completed_orders_satisfied_when_pressure_clears(self):
        sample = _validation_tmp_root() / f"core_thinning_clear_{uuid.uuid4().hex}.py"
        sample.write_text("def wrapper():\n    return service_demo()\n", encoding="utf-8")
        try:
            brief = build_core_thinning_brief(sample)
        finally:
            sample.unlink(missing_ok=True)

        feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
        tree = next(tree for tree in work_tree.list_trees() if (tree.meta or {}).get("work_identity_key") == CORE_THINNING_WORK_IDENTITY)
        task = work_tree.list_tree_tasks(tree.tree_id)[0]
        work_tree.mark_task_complete(task.task_id)

        empty_brief = {
            "ok": True,
            "generated_at": "2026-07-13 11:00:00",
            "orders": [],
            "order_count": 0,
            "line_count": 0,
            "function_count": 0,
            "wrapper_candidate_count": 0,
            "large_function_count": 0,
            "http_surface_candidate_count": 0,
        }
        result = feed_core_thinning_brief_to_work_tree(empty_brief, work_tree_module=work_tree)

        self.assertEqual(result.get("satisfied_count"), 1)
        self.assertEqual(result.get("resolved_count"), 1)
        self.assertEqual(result.get("executable_count"), 0)

    def test_stamp_core_thinning_task_satisfaction_records_completion_evidence(self):
        from services.core_thinning import stamp_core_thinning_task_satisfaction

        task = type("Task", (), {})()
        task.meta = {
            "kind": "wrapper_candidate",
            "target": {"file": "nova_core.py", "name": "demo_wrapper", "wrapped_call": "service_demo"},
        }

        stamp_core_thinning_task_satisfaction(
            task,
            {"ok": True, "action": "removed_unused_wrapper"},
        )
        self.assertEqual(task.meta.get("recurring_finding_satisfaction_status"), "satisfied")
        self.assertEqual(task.meta.get("recurring_finding_completion_action"), "removed_unused_wrapper")
        self.assertTrue(task.meta.get("recurring_finding_satisfaction_fingerprint"))

    def test_feed_brief_creates_deduped_core_thinning_tree(self):
        sample = _validation_tmp_root() / f"core_thinning_feed_{uuid.uuid4().hex}.py"
        sample.write_text("def wrapper():\n    return service_demo()\n", encoding="utf-8")
        try:
            brief = build_core_thinning_brief(sample)
        finally:
            sample.unlink(missing_ok=True)

        first = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
        second = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)

        self.assertTrue(first.get("ok"))
        self.assertTrue(first.get("created"))
        self.assertEqual(first.get("added_count"), 1)
        self.assertEqual(second.get("added_count"), 0)
        self.assertEqual(second.get("deduped_count"), 1)

        tree = work_tree.get_tree(str(first.get("tree_id")))
        self.assertIsNotNone(tree)
        self.assertEqual((tree.meta or {}).get("work_identity_key"), CORE_THINNING_WORK_IDENTITY)
        task = work_tree.list_tree_tasks(tree.tree_id)[0]
        self.assertEqual(task.meta.get("scope"), "single_block_only")
        self.assertEqual((task.meta.get("target") or {}).get("function"), "wrapper")
        self.assertEqual((task.meta.get("target") or {}).get("block"), "wrapper_candidate")

    def test_execute_core_thinning_order_removes_unused_wrapper(self):
        sample = _validation_tmp_root() / f"core_thinning_exec_{uuid.uuid4().hex}.py"
        sample.write_text(
            "\n".join(
                [
                    "def wrapper():",
                    "    return service_demo()",
                    "",
                    "def keep():",
                    "    return 1",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        brief = build_core_thinning_brief(sample)
        order = next(item for item in list(brief.get("orders") or []) if item.get("kind") == "wrapper_candidate")

        result = execute_core_thinning_order({"target": order["target"]})

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("verified"))
        text = sample.read_text(encoding="utf-8")
        self.assertNotIn("def wrapper", text)
        self.assertIn("def keep", text)
        sample.unlink(missing_ok=True)

    def test_execute_core_thinning_order_resolves_wrapper_line_drift(self):
        sample = _validation_tmp_root() / f"core_thinning_drift_{uuid.uuid4().hex}.py"
        sample.write_text(
            "\n".join(
                [
                    "HEADER = True",
                    "",
                    "def wrapper():",
                    "    return service_demo()",
                    "",
                    "def keep():",
                    "    return 1",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        target = {
            "file": str(sample),
            "name": "wrapper",
            "start_line": 1,
            "end_line": 2,
            "wrapped_call": "service_demo",
        }

        result = execute_core_thinning_order({"target": target})

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("line_drift_resolved"))
        self.assertEqual((result.get("target") or {}).get("start_line"), 3)
        text = sample.read_text(encoding="utf-8")
        self.assertNotIn("def wrapper", text)
        self.assertIn("def keep", text)
        sample.unlink(missing_ok=True)

    def test_execute_core_thinning_order_resolves_line_drift_before_caller_block(self):
        sample = _validation_tmp_root() / f"core_thinning_drift_block_{uuid.uuid4().hex}.py"
        sample.write_text(
            "\n".join(
                [
                    "HEADER = True",
                    "",
                    "def wrapper():",
                    "    return service_demo()",
                    "",
                    "def caller():",
                    "    return wrapper()",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        target = {
            "file": str(sample),
            "name": "wrapper",
            "start_line": 1,
            "end_line": 2,
            "wrapped_call": "service_demo",
        }

        result = execute_core_thinning_order({"target": target})

        self.assertFalse(result.get("ok"))
        self.assertTrue(result.get("scope_ok"))
        self.assertTrue(result.get("line_drift_resolved"))
        self.assertEqual(result.get("reason"), "callers_still_present")
        self.assertIn("def wrapper", sample.read_text(encoding="utf-8"))
        sample.unlink(missing_ok=True)

    def test_execute_core_thinning_order_blocks_runtime_hook_reference(self):
        sample_dir = _validation_tmp_root() / f"core_thinning_exec_hook_{uuid.uuid4().hex}"
        services_dir = sample_dir / "services"
        services_dir.mkdir(parents=True, exist_ok=True)
        sample = sample_dir / "nova_core.py"
        sample.write_text(
            "\n".join(
                [
                    "HEADER = True",
                    "",
                    "def _wrapper():",
                    "    return service_demo()",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (services_dir / "demo_hook.py").write_text(
            "def run(runtime_scope):\n    return _runtime_hook(runtime_scope, \"_wrapper\", None)\n",
            encoding="utf-8",
        )
        target = {
            "file": str(sample),
            "name": "_wrapper",
            "start_line": 1,
            "end_line": 2,
            "wrapped_call": "service_demo",
        }

        result = execute_core_thinning_order({"target": target})

        self.assertFalse(result.get("ok"))
        self.assertTrue(result.get("scope_ok"))
        self.assertTrue(result.get("line_drift_resolved"))
        self.assertEqual(result.get("reason"), "runtime_hook_still_present")
        self.assertIn("def _wrapper", sample.read_text(encoding="utf-8"))
        (services_dir / "demo_hook.py").unlink(missing_ok=True)
        sample.unlink(missing_ok=True)
        services_dir.rmdir()
        sample_dir.rmdir()

    def test_execute_core_thinning_order_blocks_wrapper_with_callers(self):
        sample = _validation_tmp_root() / f"core_thinning_block_{uuid.uuid4().hex}.py"
        sample.write_text(
            "\n".join(
                [
                    "def wrapper():",
                    "    return service_demo()",
                    "",
                    "def caller():",
                    "    return wrapper()",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        target = {
            "file": str(sample),
            "name": "wrapper",
            "start_line": 1,
            "end_line": 2,
            "wrapped_call": "service_demo",
        }

        result = execute_core_thinning_order({"target": target})

        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("reason"), "callers_still_present")
        self.assertIn("def wrapper", sample.read_text(encoding="utf-8"))
        sample.unlink(missing_ok=True)

    def test_build_brief_protects_referenced_wrapper_from_work_orders(self):
        sample = _validation_tmp_root() / f"core_thinning_protect_{uuid.uuid4().hex}.py"
        sample.write_text(
            "\n".join(
                [
                    "def wrapper():",
                    "    return service_demo()",
                    "",
                    "def caller():",
                    "    return wrapper()",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        try:
            brief = build_core_thinning_brief(sample)
        finally:
            sample.unlink(missing_ok=True)

        self.assertEqual(brief.get("wrapper_candidate_count"), 0)
        self.assertEqual(brief.get("referenced_wrapper_count"), 1)
        self.assertFalse(any(item.get("kind") == "wrapper_candidate" for item in list(brief.get("orders") or [])))

    def test_build_brief_protects_service_hook_map_wrappers(self):
        sample_dir = _validation_tmp_root() / f"core_thinning_hooks_{uuid.uuid4().hex}"
        services_dir = sample_dir / "services"
        services_dir.mkdir(parents=True, exist_ok=True)
        sample = sample_dir / "nova_core.py"
        sample.write_text("def _runtime_wrapper():\n    return service_demo()\n", encoding="utf-8")
        (services_dir / "demo_hooks.py").write_text(
            "HOOKS = {'runtime_wrapper_fn': '_runtime_wrapper'}\n",
            encoding="utf-8",
        )
        try:
            brief = build_core_thinning_brief(sample)
        finally:
            (services_dir / "demo_hooks.py").unlink(missing_ok=True)
            sample.unlink(missing_ok=True)
            services_dir.rmdir()
            sample_dir.rmdir()

        self.assertEqual(brief.get("wrapper_candidate_count"), 0)
        self.assertEqual(brief.get("referenced_wrapper_count"), 1)
        self.assertFalse(any(item.get("kind") == "wrapper_candidate" for item in list(brief.get("orders") or [])))

    def test_build_brief_protects_cross_module_nova_core_attribute_reference(self):
        sample_dir = _validation_tmp_root() / f"core_thinning_http_ref_{uuid.uuid4().hex}"
        sample_dir.mkdir(parents=True, exist_ok=True)
        sample = sample_dir / "nova_core.py"
        sample.write_text(
            "\n".join(
                [
                    "def demo_http_adapter(payload=None):",
                    "    return service_demo_http_adapter(payload)",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (sample_dir / "nova_http.py").write_text(
            "def pulse():\n    return nova_core.demo_http_adapter\n",
            encoding="utf-8",
        )
        try:
            brief = build_core_thinning_brief(sample)
        finally:
            (sample_dir / "nova_http.py").unlink(missing_ok=True)
            sample.unlink(missing_ok=True)
            sample_dir.rmdir()

        self.assertEqual(brief.get("wrapper_candidate_count"), 0)
        self.assertEqual(brief.get("referenced_wrapper_count"), 1)
        self.assertFalse(any(item.get("kind") == "wrapper_candidate" for item in list(brief.get("orders") or [])))

    def test_execute_core_thinning_order_blocks_cross_module_attribute_reference(self):
        sample_dir = _validation_tmp_root() / f"core_thinning_http_block_{uuid.uuid4().hex}"
        sample_dir.mkdir(parents=True, exist_ok=True)
        sample = sample_dir / "nova_core.py"
        sample.write_text(
            "\n".join(
                [
                    "def demo_http_adapter(payload=None):",
                    "    return service_demo_http_adapter(payload)",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (sample_dir / "nova_http.py").write_text(
            "def pulse():\n    return nova_core.demo_http_adapter\n",
            encoding="utf-8",
        )
        target = {
            "file": str(sample),
            "name": "demo_http_adapter",
            "start_line": 1,
            "end_line": 2,
            "wrapped_call": "service_demo_http_adapter",
        }
        try:
            result = execute_core_thinning_order({"target": target})

            self.assertFalse(result.get("ok"))
            self.assertTrue(result.get("scope_ok"))
            self.assertEqual(result.get("reason"), "callers_still_present")
            self.assertGreaterEqual(int(result.get("reference_count", 0) or 0), 1)
            self.assertIn("def demo_http_adapter", sample.read_text(encoding="utf-8"))
        finally:
            (sample_dir / "nova_http.py").unlink(missing_ok=True)
            sample.unlink(missing_ok=True)
            sample_dir.rmdir()

    def test_build_brief_protects_service_core_attribute_references(self):
        sample_dir = _validation_tmp_root() / f"core_thinning_attrs_{uuid.uuid4().hex}"
        services_dir = sample_dir / "services"
        services_dir.mkdir(parents=True, exist_ok=True)
        sample = sample_dir / "nova_core.py"
        sample.write_text(
            "\n".join(
                [
                    "def _runtime_wrapper():",
                    "    return service_demo()",
                    "",
                    "def execute_planned_action(tool, args=None):",
                    "    return service_execute_planned_action_from_runtime(tool, args)",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (services_dir / "demo_attrs.py").write_text(
            "def run(core):\n    core._runtime_wrapper()\n    return core.execute_planned_action('status')\n",
            encoding="utf-8",
        )
        try:
            brief = build_core_thinning_brief(sample)
        finally:
            (services_dir / "demo_attrs.py").unlink(missing_ok=True)
            sample.unlink(missing_ok=True)
            services_dir.rmdir()
            sample_dir.rmdir()

        self.assertEqual(brief.get("wrapper_candidate_count"), 0)
        self.assertEqual(brief.get("referenced_wrapper_count"), 2)
        self.assertFalse(any(item.get("kind") == "wrapper_candidate" for item in list(brief.get("orders") or [])))

    def test_build_brief_protects_public_runtime_adapters(self):
        sample = _validation_tmp_root() / f"core_thinning_public_{uuid.uuid4().hex}.py"
        sample.write_text(
            "\n".join(
                [
                    "def tool_update_now_cancel():",
                    "    return service_tool_update_now_cancel()",
                    "",
                    "def update_now_pending_payload():",
                    "    return service_update_now_pending_payload()",
                    "",
                    "def speak_chunked(tts, text):",
                    "    return service_speak_chunked(tts, text)",
                    "",
                    "def clear_runtime_device_location():",
                    "    return service_clear_runtime_device_location()",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        try:
            brief = build_core_thinning_brief(sample)
        finally:
            sample.unlink(missing_ok=True)

        self.assertEqual(brief.get("wrapper_candidate_count"), 0)
        self.assertEqual(brief.get("referenced_wrapper_count"), 4)
        self.assertFalse(any(item.get("kind") == "wrapper_candidate" for item in list(brief.get("orders") or [])))

    def test_execute_core_thinning_order_blocks_public_runtime_adapter(self):
        sample = _validation_tmp_root() / f"core_thinning_public_exec_{uuid.uuid4().hex}.py"
        sample.write_text(
            "\n".join(
                [
                    "def tool_update_now_cancel():",
                    "    return service_tool_update_now_cancel()",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        target = {
            "file": str(sample),
            "name": "tool_update_now_cancel",
            "start_line": 1,
            "end_line": 2,
            "wrapped_call": "service_tool_update_now_cancel",
        }

        try:
            result = execute_core_thinning_order({"target": target})

            self.assertFalse(result.get("ok"))
            self.assertTrue(result.get("scope_ok"))
            self.assertEqual(result.get("reason"), "public_adapter_protected")
            self.assertIn("def tool_update_now_cancel", sample.read_text(encoding="utf-8"))
        finally:
            sample.unlink(missing_ok=True)

    def test_execute_core_thinning_order_blocks_wrapper_used_as_callable_hook(self):
        sample = _validation_tmp_root() / f"core_thinning_hook_{uuid.uuid4().hex}.py"
        sample.write_text(
            "\n".join(
                [
                    "def wrapper():",
                    "    return service_demo()",
                    "",
                    "HOOK = wrapper",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        target = {
            "file": str(sample),
            "name": "wrapper",
            "start_line": 1,
            "end_line": 2,
            "wrapped_call": "service_demo",
        }

        result = execute_core_thinning_order({"target": target})

        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("reason"), "callers_still_present")
        self.assertIn("def wrapper", sample.read_text(encoding="utf-8"))
        sample.unlink(missing_ok=True)

    def test_execute_core_thinning_order_maps_http_boundary_without_mutation(self):
        sample_http = _validation_tmp_root() / f"nova_http_map_{uuid.uuid4().hex}.py"
        source = "\n".join(
            [
                "def _pipeline_create_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_start_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_pause_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
                "def _pipeline_archive_action(payload):",
                *["    value = 1" for _ in range(10)],
                "    return True, '', {}, ''",
                "",
            ]
        )
        sample_http.write_text(source, encoding="utf-8")
        brief = build_core_thinning_brief(sample_http)
        order = next(item for item in list(brief.get("orders") or []) if item.get("kind") == "http_surface_candidate")

        result = execute_core_thinning_order({"target": order["target"]})

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("scope_ok"))
        self.assertTrue(result.get("verified"))
        self.assertEqual(result.get("action"), "witnessed_http_extraction_boundary")
        self.assertEqual(sample_http.read_text(encoding="utf-8"), source)
        sample_http.unlink(missing_ok=True)

    def test_execute_http_extract_order_is_honestly_blocked(self):
        result = execute_core_thinning_order(
            {
                "kind": "http_surface_extract",
                "target": {
                    "file": "nova_http.py",
                    "name": "http:chat_sessions:1",
                    "block": "http_surface_extract",
                    "start_line": 1,
                    "end_line": 2,
                },
            }
        )
        self.assertFalse(result.get("ok"))
        self.assertTrue(result.get("blocked"))
        self.assertEqual(result.get("reason"), "http_extraction_not_implemented")

    def test_feed_reopens_wrapper_when_historical_removal_but_source_still_has_it(self):
        from services.recurring_finding_lifecycle import stamp_satisfaction

        sample = _validation_tmp_root() / f"core_thinning_wrapper_lie_{uuid.uuid4().hex}.py"
        sample.write_text("def wrapper():\n    return service_demo()\n", encoding="utf-8")
        try:
            brief = build_core_thinning_brief(sample)
            first = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
            task = work_tree.list_tree_tasks(str(first.get("tree_id")))[0]
            task.meta = stamp_satisfaction(
                dict(task.meta or {}),
                satisfaction_fingerprint="stale-removed-fingerprint",
                completion_action="removed_unused_wrapper",
            )
            work_tree.mark_task_complete(task.task_id)
            second = feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
        finally:
            sample.unlink(missing_ok=True)

        self.assertEqual(second.get("reopened_count"), 1)
        self.assertEqual(second.get("satisfied_active_count"), 0)
        self.assertEqual(second.get("executable_count"), 1)


if __name__ == "__main__":
    unittest.main()
