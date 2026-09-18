from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.backpack_host.sanitize import sanitize_uninstalled_backpack, scan_backpack_residue


class TestBackpackSanitize(unittest.TestCase):
    def test_uninstall_clears_declared_runtime_and_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "example_backpack").mkdir()
            (runtime / "example_backpack" / "settings.json").write_text("{}", encoding="utf-8")
            worker = runtime / "pipelines" / "example_backpack"
            worker.mkdir(parents=True)
            (worker / "worker.lease.json").write_text("{}", encoding="utf-8")
            with mock.patch("services.backpack_host.sanitize._sanitize_work_tree", return_value=[]):
                result = sanitize_uninstalled_backpack(
                    "example_backpack",
                    runtime_root=runtime,
                    nova_user="operator",
                    backpacks_root=runtime / "no-packages",
                )
            self.assertTrue(result.get("ok"), result)
            self.assertFalse((runtime / "example_backpack").exists())
            self.assertFalse(worker.exists())

    def test_residue_scan_reports_leftover_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "example_backpack").mkdir()
            (runtime / "example_backpack" / "settings.json").write_text("{}", encoding="utf-8")
            scan = scan_backpack_residue("example_backpack", runtime_root=runtime, backpacks_root=runtime / "no-packages")
            self.assertTrue(scan.get("installed"))
            self.assertTrue(scan.get("residue"))
            self.assertTrue(any("example_backpack" in str(item) for item in scan.get("found") or []))


if __name__ == "__main__":
    unittest.main()
