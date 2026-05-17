from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from services.release_clean import run_release_clean


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


if __name__ == "__main__":
    unittest.main()
