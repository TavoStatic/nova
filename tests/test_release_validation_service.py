import zipfile
from pathlib import Path
import sys
import time

from services.release_promotion_judgment import release_validation_record_payload
from services.release_validation import _default_command_runner
from services.release_validation import record_release_validation_outcome
from services.release_validation import run_release_validation


def _build_artifact(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("nova-package/nova.cmd", "@echo off\n")
        archive.writestr("nova-package/nova.ps1", "")


def test_release_validation_run_writes_complete_record_from_observed_steps(tmp_path: Path) -> None:
    artifact = tmp_path / "nova-rc.zip"
    record = tmp_path / "nova-rc.md"
    _build_artifact(artifact)
    calls: list[str] = []

    def runner(name, command, cwd, timeout_sec):
        calls.append(name)
        return {
            "name": name,
            "command": list(command),
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "duration_sec": 0.01,
        }

    report = run_release_validation(
        repo_root=tmp_path,
        artifact_path=artifact,
        record_path=record,
        artifact_version="2026.05.14.10",
        release_channel="rc",
        release_label="work-tree-rebuild",
        version_source="auto-date-sequence",
        ledger_path=str(tmp_path / "release_ledger.jsonl"),
        command_runner=runner,
        http_get=lambda _url, _timeout: (200, "<html>control</html>"),
        work_root=tmp_path / "validation",
    )

    payload = release_validation_record_payload(
        record,
        release_status={
            "latest_artifact_path": str(artifact),
            "latest_version": "2026.05.14.10",
            "latest_channel": "rc",
        },
    )

    assert report["completed"] is True
    assert report["validation_result"] == "pass-with-notes"
    assert payload["complete"] is True
    assert payload["result"] == "pass-with-notes"
    assert "nova test" in calls
    assert "nova webui-stop" in calls


def test_release_validation_removes_fresh_extract_root_for_repeated_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "nova-rc.zip"
    record = tmp_path / "nova-rc.md"
    _build_artifact(artifact)

    def runner(name, command, cwd, timeout_sec):
        return {
            "name": name,
            "command": list(command),
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "duration_sec": 0.01,
        }

    first = run_release_validation(
        repo_root=tmp_path,
        artifact_path=artifact,
        record_path=record,
        artifact_version="2026.05.14.10",
        release_channel="rc",
        command_runner=runner,
        http_get=lambda _url, _timeout: (200, "<html>control</html>"),
        work_root=tmp_path / "validation",
    )
    second = run_release_validation(
        repo_root=tmp_path,
        artifact_path=artifact,
        record_path=record,
        artifact_version="2026.05.14.10",
        release_channel="rc",
        command_runner=runner,
        http_get=lambda _url, _timeout: (200, "<html>control</html>"),
        work_root=tmp_path / "validation",
    )

    assert first["extract_root"] != second["extract_root"]
    assert first["extract_root_removed"] is True
    assert second["extract_root_removed"] is True
    assert not Path(first["extract_root"]).exists()
    assert not Path(second["extract_root"]).exists()


def test_release_validation_can_keep_extract_root_when_requested(tmp_path: Path) -> None:
    artifact = tmp_path / "nova-rc.zip"
    record = tmp_path / "nova-rc.md"
    _build_artifact(artifact)

    def runner(name, command, cwd, timeout_sec):
        return {
            "name": name,
            "command": list(command),
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "duration_sec": 0.01,
        }

    report = run_release_validation(
        repo_root=tmp_path,
        artifact_path=artifact,
        record_path=record,
        artifact_version="2026.05.14.10",
        release_channel="rc",
        command_runner=runner,
        http_get=lambda _url, _timeout: (200, "<html>control</html>"),
        work_root=tmp_path / "validation",
        keep_extract=True,
    )

    assert report["extract_root_removed"] is False
    assert report["extract_root_retained"] is True
    assert Path(report["extract_root"]).exists()


def test_release_validation_does_not_complete_record_when_profile_never_runs(tmp_path: Path) -> None:
    artifact = tmp_path / "missing.zip"
    record = tmp_path / "nova-rc.md"

    def runner(name, command, cwd, timeout_sec):
        raise AssertionError("validation commands should not run when artifact preparation fails")

    report = run_release_validation(
        repo_root=tmp_path,
        artifact_path=artifact,
        record_path=record,
        artifact_version="2026.05.14.10",
        release_channel="rc",
        command_runner=runner,
        work_root=tmp_path / "validation",
    )
    payload = release_validation_record_payload(
        record,
        release_status={
            "latest_artifact_path": str(artifact),
            "latest_version": "2026.05.14.10",
            "latest_channel": "rc",
        },
    )

    assert report["validation_result"] == "fail"
    assert report["validation_record_complete"] is False
    assert "nova package-verify ." in payload["missing_fields"]
    assert "- Manifest reviewed: no" in record.read_text(encoding="utf-8")


def test_default_command_runner_times_out_process_tree_with_inherited_output(tmp_path: Path) -> None:
    script = tmp_path / "spawn_child.py"
    script.write_text(
        "\n".join(
            [
                "import subprocess",
                "import sys",
                "import time",
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])",
                "time.sleep(30)",
            ]
        ),
        encoding="utf-8",
    )

    started = time.monotonic()
    result = _default_command_runner(
        "spawn child timeout",
        [sys.executable, str(script)],
        tmp_path,
        1,
    )

    assert result["returncode"] == 124
    assert time.monotonic() - started < 20
    assert Path(result["stdout_path"]).exists()
    assert Path(result["stderr_path"]).exists()


def test_default_command_runner_can_keep_logs_outside_command_cwd(tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    script = tmp_path / "ok.py"
    script.write_text("print('ok')\n", encoding="utf-8")

    result = _default_command_runner(
        "outside logs",
        [sys.executable, str(script)],
        package_root,
        10,
        log_root=tmp_path / "validation-logs",
    )

    assert result["returncode"] == 0
    assert not (package_root / "runtime").exists()
    assert Path(result["stdout_path"]).parent == tmp_path / "validation-logs"
    assert Path(result["stderr_path"]).parent == tmp_path / "validation-logs"


def test_record_release_validation_outcome_requires_complete_record(tmp_path: Path) -> None:
    record = tmp_path / "nova-rc.md"
    record.write_text("- Result: pass / pass-with-notes / fail\n", encoding="utf-8")

    report = record_release_validation_outcome(
        repo_root=tmp_path,
        record_path=record,
        release_status={},
        command_runner=lambda name, command, cwd, timeout_sec: {
            "name": name,
            "command": list(command),
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "duration_sec": 0.01,
        },
    )

    assert report["recorded"] is False
    assert report["reason"] == "validation_record_incomplete"
