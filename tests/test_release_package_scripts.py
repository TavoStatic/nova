import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build_release_package.ps1"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_release_package.ps1"


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_script(destination_root: Path, source: Path) -> Path:
    target = destination_root / "scripts" / source.name
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


def _zip_relative_entries(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as archive:
        names = sorted(archive.namelist())
    manifest_name = next(name for name in names if name.endswith("/package_manifest.json") or name == "package_manifest.json")
    root_prefix = ""
    if manifest_name.endswith("/package_manifest.json"):
        root_prefix = manifest_name[: -len("/package_manifest.json")]
    relative = []
    for name in names:
        candidate = name
        if root_prefix and candidate.startswith(root_prefix + "/"):
            candidate = candidate[len(root_prefix) + 1 :]
        relative.append(candidate)
    return relative


class TestReleasePackageScripts(unittest.TestCase):
    def test_build_release_package_excludes_non_package_content(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            build_script = _copy_script(repo, BUILD_SCRIPT)
            verify_script = _copy_script(repo, VERIFY_SCRIPT)

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
            _write(repo / ".ci_venv" / "pyvenv.cfg", "home = C:/Python\n")
            _write(repo / "knowledge" / "packs" / "demo.txt", "pack\n")
            _write(repo / "knowledge" / "peims" / "rules.txt", "peims\n")
            _write(repo / "knowledge" / "web" / "snapshot.txt", "web\n")
            _write(repo / "updates" / "patch.log", "patch log\n")
            _write(repo / "updates" / "artifact.zip", "zip\n")
            _write(repo / "services" / "__pycache__" / "demo.pyc", "pyc")
            _write(repo / "debug.log", "debug\n")
            _write(repo / "LAST_SESSION.json", "{}\n")
            _write(repo / "RESUME_HERE.txt", "resume\n")
            _write(repo / "nova_memory.sqlite", "sqlite")

            build_result = _run_powershell(build_script, repo)
            self.assertEqual(build_result.returncode, 0, msg=build_result.stdout + build_result.stderr)

            artifacts = list((repo / "runtime" / "exports" / "release_packages").glob("*.zip"))
            self.assertEqual(len(artifacts), 1)
            artifact_path = artifacts[0]
            entries = _zip_relative_entries(artifact_path)

            self.assertIn("nova.cmd", entries)
            self.assertIn("nova.ps1", entries)
            self.assertIn("requirements.txt", entries)
            self.assertIn("docs/FRESH_MACHINE_VALIDATION.md", entries)
            self.assertIn("docs/RC_VALIDATION_TEMPLATE.md", entries)
            self.assertNotIn(".ci_venv/pyvenv.cfg", entries)
            self.assertNotIn("knowledge/packs/demo.txt", entries)
            self.assertNotIn("knowledge/peims/rules.txt", entries)
            self.assertNotIn("knowledge/web/snapshot.txt", entries)
            self.assertNotIn("updates/patch.log", entries)
            self.assertNotIn("updates/artifact.zip", entries)
            self.assertNotIn("LAST_SESSION.json", entries)
            self.assertNotIn("RESUME_HERE.txt", entries)
            self.assertNotIn("nova_memory.sqlite", entries)
            self.assertTrue(all("__pycache__" not in entry for entry in entries))
            self.assertTrue(all(not entry.endswith(".pyc") for entry in entries))
            self.assertTrue(all(not entry.endswith(".log") for entry in entries))

            verify_result = _run_powershell(verify_script, repo, str(artifact_path))
            self.assertEqual(verify_result.returncode, 0, msg=verify_result.stdout + verify_result.stderr)

            ledger_path = repo / "runtime" / "exports" / "release_packages" / "release_ledger.jsonl"
            ledger_rows = [
                __import__("json").loads(line)
                for line in ledger_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(ledger_rows[0]["artifact_kind"], "package-zip")
            self.assertEqual(ledger_rows[-1]["artifact_kind"], "package-zip")

    def test_verify_release_package_rejects_forbidden_payload_content(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            verify_script = _copy_script(repo, VERIFY_SCRIPT)
            candidate_dir = repo / "candidate"

            _write(candidate_dir / "package_manifest.json", """{
  \"schema_version\": 1,
  \"package_name\": \"NYO System Base\",
  \"artifact_type\": \"source-bootstrap-zip\",
  \"artifact_version\": \"2026.03.30.9\",
  \"release_channel\": \"rc\",
  \"built_at\": \"2026-03-30T00:00:00Z\",
  \"bootstrap_entrypoint\": \".\\\\nova.cmd install\",
  \"validation_commands\": [
    \".\\\\nova.cmd doctor\",
    \".\\\\nova.cmd runtime-status\",
    \".\\\\nova.cmd smoke-base --fix\",
    \".\\\\nova.cmd smoke --fix\",
    \".\\\\nova.cmd test\"
  ],
  \"validation_profiles\": {
    \"base_package\": \".\\\\nova.cmd smoke-base --fix\",
    \"runtime_model\": \".\\\\nova.cmd smoke --fix\",
    \"fresh_machine_checklist\": \"docs\\\\FRESH_MACHINE_VALIDATION.md\",
    \"validation_record_template\": \"docs\\\\RC_VALIDATION_TEMPLATE.md\"
  },
  \"includes\": [\"tracked source files\"],
  \"excludes\": [\"runtime\"]
}\n""")
            _write(candidate_dir / "nova.cmd", "@echo off\n")
            _write(candidate_dir / "nova.ps1", "Write-Host 'nova'\n")
            _write(candidate_dir / "requirements.txt", "requests\n")
            _write(candidate_dir / "docs" / "FRESH_MACHINE_VALIDATION.md", "# Fresh\n")
            _write(candidate_dir / "docs" / "RC_VALIDATION_TEMPLATE.md", "# RC\n")
            _write(candidate_dir / ".ci_venv" / "pyvenv.cfg", "home = C:/Python\n")
            _write(candidate_dir / "knowledge" / "peims" / "rules.txt", "peims\n")
            _write(candidate_dir / "LAST_SESSION.json", "{}\n")
            _write(candidate_dir / "RESUME_HERE.txt", "resume\n")
            _write(candidate_dir / "nova_memory.sqlite", "sqlite")

            verify_result = _run_powershell(verify_script, repo, str(candidate_dir))

            self.assertNotEqual(verify_result.returncode, 0)
            combined = verify_result.stdout + verify_result.stderr
            self.assertIn("forbidden path present: .ci_venv", combined)
            self.assertIn("forbidden path present: knowledge/peims", combined)
            self.assertIn("forbidden path present: LAST_SESSION.json", combined)
            self.assertIn("forbidden path present: RESUME_HERE.txt", combined)
            self.assertIn("forbidden path present: nova_memory.sqlite", combined)


if __name__ == "__main__":
    unittest.main()