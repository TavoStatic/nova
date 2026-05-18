from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Sequence
from unittest import mock

from services.release_clean import run_release_clean


def _load_repo_hygiene_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "repo_hygiene_check.py"
    spec = importlib.util.spec_from_file_location("repo_hygiene_check_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ReleaseCleanServiceTests(unittest.TestCase):
    def test_release_clean_runs_package_lane_and_writes_report(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            calls: list[str] = []

            def runner(name: str, command: Sequence[str], cwd: Path, timeout_sec: int) -> dict[str, Any]:
                calls.append(name)
                stdout = ""
                if name == "package_build":
                    package_dir = cwd / "runtime" / "exports" / "release_packages"
                    package_dir.mkdir(parents=True)
                    record_dir = package_dir / "validation_records"
                    record_dir.mkdir(parents=True)
                    zip_path = package_dir / "nyo-system-base-rc-test.zip"
                    record_path = record_dir / "nyo-system-base-rc-test.md"
                    zip_path.write_bytes(b"zip")
                    record_path.write_text("- Result: pass-with-notes\n", encoding="utf-8")
                    stdout = f"[OK]   Zip artifact   : {zip_path}\n[OK]   Validation seed: {record_path}\n"
                elif name == "package_readiness":
                    stdout = json.dumps({"latest_readiness_state": "ready-with-notes", "latest_ready_to_ship": True})
                return {
                    "name": name,
                    "command": list(command),
                    "returncode": 0,
                    "stdout": stdout,
                    "stderr": "",
                    "duration_sec": 0.01,
                }

            report = run_release_clean(
                root=tmp_path,
                label="test",
                python_executable="python",
                command_runner=runner,
            )

            self.assertTrue(report["ok"])
            self.assertEqual(
                calls,
                [
                    "repo_hygiene",
                    "regression_all",
                    "smoke_runtime",
                    "package_build",
                    "package_verify",
                    "package_validate",
                    "package_record_outcome",
                    "package_readiness",
                ],
            )
            self.assertTrue(report["artifact"].endswith("nyo-system-base-rc-test.zip"))
            self.assertTrue((tmp_path / "runtime" / "release_clean" / "latest_release_clean.json").exists())

    def test_release_clean_stops_on_hygiene_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            calls: list[str] = []

            def runner(name: str, command: Sequence[str], cwd: Path, timeout_sec: int) -> dict[str, Any]:
                calls.append(name)
                return {
                    "name": name,
                    "command": list(command),
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "hygiene failed",
                    "duration_sec": 0.01,
                }

            report = run_release_clean(
                root=tmp_path,
                label="test",
                python_executable="python",
                command_runner=runner,
            )

            self.assertFalse(report["ok"])
            self.assertEqual(report["failure_reason"], "repo_hygiene_failed")
            self.assertEqual(calls, ["repo_hygiene"])

    def test_release_clean_parses_raw_readiness_when_report_stdout_is_tailed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)

            def runner(name: str, command: Sequence[str], cwd: Path, timeout_sec: int) -> dict[str, Any]:
                stdout = ""
                if name == "package_build":
                    package_dir = cwd / "runtime" / "exports" / "release_packages"
                    package_dir.mkdir(parents=True)
                    record_dir = package_dir / "validation_records"
                    record_dir.mkdir(parents=True)
                    zip_path = package_dir / "nyo-system-base-rc-test.zip"
                    record_path = record_dir / "nyo-system-base-rc-test.md"
                    zip_path.write_bytes(b"zip")
                    record_path.write_text("- Result: pass-with-notes\n", encoding="utf-8")
                    stdout = f"[OK]   Zip artifact   : {zip_path}\n[OK]   Validation seed: {record_path}\n"
                elif name == "package_readiness":
                    raw = json.dumps(
                        {
                            "latest_readiness_state": "ready-with-notes",
                            "latest_ready_to_ship": True,
                            "recent_entries": [{"note": "x" * 2000} for _ in range(8)],
                        }
                    )
                    return {
                        "name": name,
                        "command": list(command),
                        "returncode": 0,
                        "stdout": raw[-4000:],
                        "_stdout_raw": raw,
                        "stderr": "",
                        "duration_sec": 0.01,
                    }
                return {
                    "name": name,
                    "command": list(command),
                    "returncode": 0,
                    "stdout": stdout,
                    "stderr": "",
                    "duration_sec": 0.01,
                }

            report = run_release_clean(
                root=tmp_path,
                label="test",
                python_executable="python",
                command_runner=runner,
            )

            self.assertTrue(report["ok"])
            self.assertEqual((report.get("readiness") or {}).get("latest_readiness_state"), "ready-with-notes")
            self.assertFalse(any("_stdout_raw" in step for step in report.get("steps") or []))


class RepoHygieneCheckTests(unittest.TestCase):
    def _init_repo(self, root: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True, text=True)

    def test_hygiene_accepts_smudged_lfs_asset_when_index_blob_is_pointer(self) -> None:
        module = _load_repo_hygiene_module()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._init_repo(root)
            asset = root / "piper" / "models" / "voice.onnx"
            asset.parent.mkdir(parents=True)
            asset.write_text(
                "\n".join(
                    [
                        "version https://git-lfs.github.com/spec/v1",
                        "oid sha256:" + ("a" * 64),
                        "size 63201234",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "piper/models/voice.onnx"], cwd=str(root), check=True, capture_output=True, text=True)
            asset.write_bytes(b"x" * 64)

            with mock.patch.object(module, "MAX_TRACKED_FILE_BYTES", 16):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    result = module.run_hygiene(root)

        self.assertEqual(result, 0)
        self.assertIn("repo_hygiene_check: OK", stdout.getvalue())

    def test_hygiene_rejects_large_non_lfs_blob(self) -> None:
        module = _load_repo_hygiene_module()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._init_repo(root)
            asset = root / "source_blob.bin"
            asset.write_bytes(b"x" * 64)
            subprocess.run(["git", "add", "source_blob.bin"], cwd=str(root), check=True, capture_output=True, text=True)

            with mock.patch.object(module, "MAX_TRACKED_FILE_BYTES", 16):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    result = module.run_hygiene(root)

        self.assertEqual(result, 1)
        self.assertIn("oversized tracked blob", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
