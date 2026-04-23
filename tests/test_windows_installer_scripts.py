import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_BUILD_SCRIPT = ROOT / "scripts" / "build_release_package.ps1"
PACKAGE_VERIFY_SCRIPT = ROOT / "scripts" / "verify_release_package.ps1"
INSTALLER_BUILD_SCRIPT = ROOT / "scripts" / "build_windows_installer.ps1"
INSTALLER_VERIFY_SCRIPT = ROOT / "scripts" / "verify_windows_installer.ps1"
PROMOTE_SCRIPT = ROOT / "scripts" / "promote_release_package.ps1"
STATUS_SCRIPT = ROOT / "scripts" / "show_release_status.ps1"
READINESS_SCRIPT = ROOT / "scripts" / "show_release_readiness.ps1"
INSTALLER_ISS = ROOT / "installer" / "NYO_System.iss"


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_file(destination_root: Path, source: Path, relative_path: str) -> Path:
    target = destination_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def _run_powershell(script: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *args,
        ],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )


class TestWindowsInstallerScripts(unittest.TestCase):
    def test_installer_artifact_participates_in_release_governance(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            build_script = _copy_file(repo, PACKAGE_BUILD_SCRIPT, "scripts/build_release_package.ps1")
            _copy_file(repo, PACKAGE_VERIFY_SCRIPT, "scripts/verify_release_package.ps1")
            installer_build_script = _copy_file(repo, INSTALLER_BUILD_SCRIPT, "scripts/build_windows_installer.ps1")
            installer_verify_script = _copy_file(repo, INSTALLER_VERIFY_SCRIPT, "scripts/verify_windows_installer.ps1")
            promote_script = _copy_file(repo, PROMOTE_SCRIPT, "scripts/promote_release_package.ps1")
            status_script = _copy_file(repo, STATUS_SCRIPT, "scripts/show_release_status.ps1")
            readiness_script = _copy_file(repo, READINESS_SCRIPT, "scripts/show_release_readiness.ps1")
            _copy_file(repo, INSTALLER_ISS, "installer/NYO_System.iss")

            _write(repo / "nova.cmd", "@echo off\n")
            _write(repo / "nova.ps1", "Write-Host 'nova'\n")
            _write(repo / "requirements.txt", "requests\n")
            _write(repo / "policy.json", "{}\n")
            _write(repo / "doctor.py", "print('doctor')\n")
            _write(repo / "docs" / "FRESH_MACHINE_VALIDATION.md", "# Fresh Machine\n")
            _write(repo / "docs" / "RC_VALIDATION_TEMPLATE.md", "# RC Validation\n")
            _write(repo / "templates" / "control.html", "<html></html>\n")
            _write(repo / "static" / "control.js", "console.log('x');\n")
            _write(repo / "tests" / "test_placeholder.py", "def test_placeholder():\n    assert True\n")
            _write(repo / "scripts" / "installer_hardware_check.ps1", "Write-Host 'installer-check'\n")

            fake_compiler = repo / "tools" / "fake_iscc.ps1"
            _write(
                fake_compiler,
                "param([string]$issPath)\n"
                "$outDir = [string]$env:NYO_INSTALLER_OUTPUT_DIR\n"
                "$version = [string]$env:NYO_APP_VERSION\n"
                "$payloadDir = [string]$env:NYO_PAYLOAD_DIR\n"
                "New-Item -ItemType Directory -Force -Path $outDir | Out-Null\n"
                "$artifact = Join-Path $outDir ('nyo-system-installer-' + $version + '.exe')\n"
                "Set-Content -Path $artifact -Value \"installer\" -Encoding UTF8\n"
                "$payload = [ordered]@{ iss_path = $issPath; version = $version; payload_dir = $payloadDir; output_dir = $outDir }\n"
                "$payload | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $outDir 'compiler_env.json') -Encoding UTF8\n"
                "exit 0\n",
            )

            build_result = _run_powershell(build_script, repo)
            self.assertEqual(build_result.returncode, 0, msg=build_result.stdout + build_result.stderr)

            installer_result = _run_powershell(installer_build_script, repo, "-Compiler", str(fake_compiler))
            self.assertEqual(installer_result.returncode, 0, msg=installer_result.stdout + installer_result.stderr)

            installer_dir = repo / "runtime" / "exports" / "installers"
            installer_artifacts = list(installer_dir.glob("nyo-system-installer-*.exe"))
            self.assertEqual(len(installer_artifacts), 1)
            self.assertTrue(installer_artifacts[0].exists())
            self.assertTrue((installer_dir / "validation_records").exists())

            compiler_env = json.loads((installer_dir / "compiler_env.json").read_text(encoding="utf-8-sig"))
            self.assertTrue(str(compiler_env.get("iss_path") or "").endswith("installer\\NYO_System.iss"))
            self.assertFalse(str(compiler_env.get("payload_dir") or "").endswith("_stage"))
            self.assertEqual(Path(compiler_env.get("output_dir")), installer_dir)
            self.assertTrue((repo / "runtime" / "exports" / "installers" / "_payload").exists())

            installer_verify_result = _run_powershell(installer_verify_script, repo, str(installer_artifacts[0]))
            self.assertEqual(installer_verify_result.returncode, 0, msg=installer_verify_result.stdout + installer_verify_result.stderr)

            status_result = _run_powershell(
                status_script,
                repo,
                "-ArtifactKind",
                "windows-installer",
                "-Json",
            )
            self.assertEqual(status_result.returncode, 0, msg=status_result.stdout + status_result.stderr)
            status_payload = json.loads(status_result.stdout)
            self.assertEqual(status_payload["artifact_kind"], "windows-installer")
            self.assertEqual(status_payload["latest_state"], "built-only")

            promote_result = _run_powershell(
                promote_script,
                repo,
                "-ArtifactKind",
                "windows-installer",
                "-Artifact",
                str(installer_artifacts[0]),
                "-Result",
                "pass-with-notes",
                "-Note",
                "validated on vm",
            )
            self.assertEqual(promote_result.returncode, 0, msg=promote_result.stdout + promote_result.stderr)

            readiness_result = _run_powershell(
                readiness_script,
                repo,
                "-ArtifactKind",
                "windows-installer",
                "-Json",
            )
            self.assertEqual(readiness_result.returncode, 0, msg=readiness_result.stdout + readiness_result.stderr)
            readiness_payload = json.loads(readiness_result.stdout)
            self.assertEqual(readiness_payload["artifact_kind"], "windows-installer")
            self.assertEqual(readiness_payload["latest_readiness_state"], "ready-with-notes")
            self.assertTrue(readiness_payload["latest_ready_to_ship"])

            ledger_rows = [
                json.loads(line)
                for line in (repo / "runtime" / "exports" / "release_packages" / "release_ledger.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            installer_rows = [row for row in ledger_rows if row.get("artifact_kind") == "windows-installer"]
            self.assertEqual([row["event"] for row in installer_rows], ["build", "verify", "promotion"])
            self.assertEqual(installer_rows[0]["artifact_path"], str(installer_artifacts[0]))
            self.assertEqual(installer_rows[-1]["validation_result"], "pass-with-notes")


if __name__ == "__main__":
    unittest.main()