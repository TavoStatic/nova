import json
import tempfile
import unittest
from pathlib import Path

from services.installer_validation import render_installer_validation_report
from services.installer_validation import run_installer_validation
from services.release_status import RELEASE_STATUS_SERVICE


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


class TestInstallerValidationService(unittest.TestCase):
    def test_installer_validation_builds_verifies_and_promotes_installer_kind(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger = root / "runtime" / "exports" / "release_packages" / "release_ledger.jsonl"
            package = ledger.parent / "nova.zip"
            installer = root / "runtime" / "exports" / "installers" / "nyo-system-installer-2026.05.26.exe"
            record = root / "runtime" / "exports" / "installers" / "validation_records" / "nyo-system-installer-2026.05.26.md"
            package.parent.mkdir(parents=True, exist_ok=True)
            package.write_text("zip", encoding="utf-8")
            _append_jsonl(
                ledger,
                {
                    "recorded_at": "2026-05-26T10:00:00-05:00",
                    "event": "build",
                    "artifact_kind": "package-zip",
                    "artifact_name": package.name,
                    "artifact_path": str(package),
                    "artifact_version": "2026.05.26",
                    "release_channel": "rc",
                    "release_label": "test",
                },
            )
            _append_jsonl(
                ledger,
                {
                    "recorded_at": "2026-05-26T10:01:00-05:00",
                    "event": "verify",
                    "artifact_kind": "package-zip",
                    "artifact_name": package.name,
                    "artifact_path": str(package),
                    "artifact_version": "2026.05.26",
                    "release_channel": "rc",
                    "release_label": "test",
                    "verification_result": "pass",
                },
            )

            def runner(name, command, cwd, timeout):
                if name == "build_windows_installer":
                    installer.parent.mkdir(parents=True, exist_ok=True)
                    installer.write_text("installer", encoding="utf-8")
                    record.parent.mkdir(parents=True, exist_ok=True)
                    record.write_text("# record\n", encoding="utf-8")
                    _append_jsonl(
                        ledger,
                        {
                            "recorded_at": "2026-05-26T10:02:00-05:00",
                            "event": "build",
                            "artifact_kind": "windows-installer",
                            "artifact_name": installer.name,
                            "artifact_path": str(installer),
                            "artifact_version": "2026.05.26",
                            "release_channel": "rc",
                            "release_label": "test",
                            "source_package_artifact_path": str(package),
                            "validation_record_seed_path": str(record),
                        },
                    )
                    return {"name": name, "command": list(command), "returncode": 0, "stdout": f"[INFO] Installer output : {installer}\n[INFO] Validation seed  : {record}\n", "stderr": ""}
                if name == "verify_windows_installer":
                    _append_jsonl(
                        ledger,
                        {
                            "recorded_at": "2026-05-26T10:03:00-05:00",
                            "event": "verify",
                            "artifact_kind": "windows-installer",
                            "artifact_name": installer.name,
                            "artifact_path": str(installer),
                            "artifact_version": "2026.05.26",
                            "release_channel": "rc",
                            "release_label": "test",
                            "verification_result": "pass",
                        },
                    )
                    return {"name": name, "command": list(command), "returncode": 0, "stdout": "[OK] verified\n", "stderr": ""}
                if name == "promote_windows_installer":
                    _append_jsonl(
                        ledger,
                        {
                            "recorded_at": "2026-05-26T10:04:00-05:00",
                            "event": "promotion",
                            "artifact_kind": "windows-installer",
                            "artifact_name": installer.name,
                            "artifact_path": str(installer),
                            "artifact_version": "2026.05.26",
                            "release_channel": "rc",
                            "release_label": "test",
                            "validation_result": "pass-with-notes",
                        },
                    )
                    return {"name": name, "command": list(command), "returncode": 0, "stdout": "[OK] promoted\n", "stderr": ""}
                return {"name": name, "command": list(command), "returncode": 1, "stdout": "", "stderr": "unknown"}

            report = run_installer_validation(repo_root=root, command_runner=runner)
            installer_status = RELEASE_STATUS_SERVICE.status_payload(ledger, artifact_kind="windows-installer")

        self.assertTrue(report["ok"])
        self.assertEqual(report["validation_result"], "pass-with-notes")
        self.assertEqual(installer_status["latest_readiness_state"], "ready-with-notes")
        self.assertTrue(installer_status["latest_ready_to_ship"])
        self.assertIn("Installer Validation Run", render_installer_validation_report(report))

    def test_installer_validation_failure_renders_failed_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package = root / "runtime" / "exports" / "release_packages" / "nova.zip"
            package.parent.mkdir(parents=True, exist_ok=True)
            package.write_text("zip", encoding="utf-8")

            def runner(name, command, cwd, timeout):
                return {"name": name, "command": list(command), "returncode": 1, "stdout": "[FAIL] Inno Setup compiler not found.", "stderr": ""}

            report = run_installer_validation(
                repo_root=root,
                package_artifact_path=str(package),
                command_runner=runner,
            )

        self.assertFalse(report["ok"])
        self.assertEqual(report["failure_reason"], "installer_build_failed")
        self.assertTrue(render_installer_validation_report(report).startswith("[FAIL]"))


if __name__ == "__main__":
    unittest.main()
