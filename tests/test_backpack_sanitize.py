from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.backpack_host.sanitize import (
    backpack_touch_points,
    sanitize_uninstalled_backpack,
    scan_backpack_residue,
)
from services.edfi.warehouse_sync import maybe_run_scheduled_warehouse_sync
from services.nova_runtime_context import BASE_DIR


class TestBackpackSanitize(unittest.TestCase):
    def test_edfi_touch_points_name_the_nova_surfaces(self) -> None:
        points = backpack_touch_points("edfi", backpacks_root=BASE_DIR / "backpacks")
        self.assertEqual(points["runtime_dir"], "edfi")
        self.assertIn("edfi", points["pipeline_ids"])
        self.assertIn("edfi_capability_profile", points["signal_sources"])
        self.assertIn("edfi_core", points["signal_sources"])
        self.assertIn("backpack_edfi", points["signal_sources"])
        self.assertTrue(points["fusion_scan"])
        self.assertTrue(any("runtime/edfi" in str(item) for item in points.get("runtime_decls") or []))

    def test_reports_touch_points_include_views_dir(self) -> None:
        points = backpack_touch_points(
            "reports",
            runtime_root=Path("C:/tmp-runtime-does-not-need-to-exist"),
            backpacks_root=BASE_DIR / "backpacks",
        )
        self.assertIn("reports", points["pipeline_ids"])
        self.assertTrue(any("runtime/views" in str(item) for item in points.get("runtime_decls") or []))
        self.assertTrue(any(str(item).replace("\\", "/").endswith("/views") for item in points.get("extra_runtime_paths") or []))

    def test_sanitize_clears_runtime_fusion_and_workers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "edfi").mkdir()
            (runtime / "edfi" / "settings.json").write_text("{}", encoding="utf-8")
            scan = runtime / "backpacks" / "capability_scan.json"
            scan.parent.mkdir(parents=True)
            scan.write_text("{}", encoding="utf-8")
            worker = runtime / "pipelines" / "edfi"
            worker.mkdir(parents=True)
            (worker / "worker.lease.json").write_text("{}", encoding="utf-8")

            with mock.patch("services.backpack_host.sanitize._sanitize_work_tree", return_value=[]):
                result = sanitize_uninstalled_backpack(
                    "edfi",
                    runtime_root=runtime,
                    nova_user="operator",
                    backpacks_root=BASE_DIR / "backpacks",
                )

            self.assertTrue(result.get("ok"))
            self.assertFalse((runtime / "edfi").exists())
            self.assertFalse(scan.exists())
            self.assertFalse(worker.exists())
            mark = json.loads((runtime / "backpacks" / "uninstalled" / "edfi.json").read_text(encoding="utf-8"))
            self.assertEqual(mark.get("status"), "uninstalled")
            self.assertFalse(result.get("installed"))

    def test_reports_uninstall_clears_declared_views_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "reports").mkdir()
            (runtime / "reports" / "settings.json").write_text("{}", encoding="utf-8")
            views = runtime / "views"
            views.mkdir()
            (views / "board.html").write_text("<html></html>", encoding="utf-8")
            with mock.patch("services.backpack_host.sanitize._sanitize_work_tree", return_value=[]):
                result = sanitize_uninstalled_backpack(
                    "reports",
                    runtime_root=runtime,
                    nova_user="operator",
                    backpacks_root=BASE_DIR / "backpacks",
                )
            self.assertTrue(result.get("ok"), result)
            self.assertFalse((runtime / "reports").exists())
            self.assertFalse(views.exists())
            self.assertFalse((result.get("residue") or {}).get("undeclared"))

    def test_unknown_backpack_still_clears_its_runtime_and_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "custompack").mkdir()
            (runtime / "custompack" / "settings.json").write_text("{}", encoding="utf-8")
            worker = runtime / "pipelines" / "custompack"
            worker.mkdir(parents=True)
            (worker / "worker.lease.json").write_text("{}", encoding="utf-8")
            with mock.patch("services.backpack_host.sanitize._sanitize_work_tree", return_value=[]):
                result = sanitize_uninstalled_backpack(
                    "custompack",
                    runtime_root=runtime,
                    nova_user="operator",
                    backpacks_root=runtime / "no-packages",
                )
            self.assertTrue(result.get("ok"), result)
            self.assertFalse((runtime / "custompack").exists())
            self.assertFalse(worker.exists())

    def test_residue_scan_reports_leftover_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "edfi").mkdir()
            (runtime / "edfi" / "settings.json").write_text("{}", encoding="utf-8")
            scan = scan_backpack_residue("edfi", runtime_root=runtime, backpacks_root=BASE_DIR / "backpacks")
            self.assertTrue(scan.get("installed"))
            self.assertTrue(scan.get("residue"))
            self.assertTrue(any("edfi" in str(item) for item in scan.get("found") or []))

    def test_scheduled_warehouse_sync_is_quiet_when_not_installed(self) -> None:
        with mock.patch(
            "services.backpack_host.install_state.backpack_runtime_installed",
            return_value=False,
        ):
            result = maybe_run_scheduled_warehouse_sync(force=False)
        self.assertTrue(result.get("ok"))
        self.assertFalse(result.get("ran"))
        self.assertTrue(result.get("skipped"))
        self.assertEqual(result.get("reason"), "not_installed")


if __name__ == "__main__":
    unittest.main()
