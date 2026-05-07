from __future__ import annotations

from pathlib import Path
import unittest
import uuid

import work_tree
from services.core_thinning import (
    CORE_THINNING_WORK_IDENTITY,
    build_core_thinning_brief,
    execute_core_thinning_order,
    feed_core_thinning_brief_to_work_tree,
)


class TestCoreThinningService(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = Path("C:/Nova/runtime/_test_tmp")
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
        sample = Path("C:/Nova/runtime/_test_tmp") / f"core_thinning_sample_{uuid.uuid4().hex}.py"
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
        sample_core = Path("C:/Nova/runtime/_test_tmp") / f"core_thinning_core_{uuid.uuid4().hex}.py"
        sample_http = Path("C:/Nova/runtime/_test_tmp") / f"core_thinning_http_{uuid.uuid4().hex}.py"
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
        sample_http = Path("C:/Nova/runtime/_test_tmp") / f"nova_http_surface_{uuid.uuid4().hex}.py"
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
        self.assertEqual((order.get("target") or {}).get("theme"), "pipeline_control")

    def test_feed_brief_creates_deduped_core_thinning_tree(self):
        sample = Path("C:/Nova/runtime/_test_tmp") / f"core_thinning_feed_{uuid.uuid4().hex}.py"
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
        sample = Path("C:/Nova/runtime/_test_tmp") / f"core_thinning_exec_{uuid.uuid4().hex}.py"
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
        sample = Path("C:/Nova/runtime/_test_tmp") / f"core_thinning_drift_{uuid.uuid4().hex}.py"
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
        sample = Path("C:/Nova/runtime/_test_tmp") / f"core_thinning_drift_block_{uuid.uuid4().hex}.py"
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
        sample_dir = Path("C:/Nova/runtime/_test_tmp") / f"core_thinning_exec_hook_{uuid.uuid4().hex}"
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
        sample = Path("C:/Nova/runtime/_test_tmp") / f"core_thinning_block_{uuid.uuid4().hex}.py"
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
        sample = Path("C:/Nova/runtime/_test_tmp") / f"core_thinning_protect_{uuid.uuid4().hex}.py"
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
        sample_dir = Path("C:/Nova/runtime/_test_tmp") / f"core_thinning_hooks_{uuid.uuid4().hex}"
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

    def test_build_brief_protects_service_core_attribute_references(self):
        sample_dir = Path("C:/Nova/runtime/_test_tmp") / f"core_thinning_attrs_{uuid.uuid4().hex}"
        services_dir = sample_dir / "services"
        services_dir.mkdir(parents=True, exist_ok=True)
        sample = sample_dir / "nova_core.py"
        sample.write_text("def _runtime_wrapper():\n    return service_demo()\n", encoding="utf-8")
        (services_dir / "demo_attrs.py").write_text(
            "def run(core):\n    return core._runtime_wrapper()\n",
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
        self.assertEqual(brief.get("referenced_wrapper_count"), 1)
        self.assertFalse(any(item.get("kind") == "wrapper_candidate" for item in list(brief.get("orders") or [])))

    def test_execute_core_thinning_order_blocks_wrapper_used_as_callable_hook(self):
        sample = Path("C:/Nova/runtime/_test_tmp") / f"core_thinning_hook_{uuid.uuid4().hex}.py"
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
        sample_http = Path("C:/Nova/runtime/_test_tmp") / f"nova_http_map_{uuid.uuid4().hex}.py"
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
        self.assertEqual(result.get("action"), "mapped_http_extraction_boundary")
        self.assertEqual(sample_http.read_text(encoding="utf-8"), source)
        sample_http.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
