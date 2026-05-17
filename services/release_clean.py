from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "runtime" / "release_clean"
LATEST_REPORT = REPORT_DIR / "latest_release_clean.json"
PACKAGE_DIR = ROOT / "runtime" / "exports" / "release_packages"

CommandRunner = Callable[[str, Sequence[str], Path, int], dict[str, Any]]


def _tail(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _default_command_runner(
    name: str,
    command: Sequence[str],
    cwd: Path,
    timeout_sec: int,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [str(part) for part in command],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        return {
            "name": name,
            "command": [str(part) for part in command],
            "returncode": completed.returncode,
            "stdout": _tail(completed.stdout or ""),
            "_stdout_raw": completed.stdout or "",
            "stderr": _tail(completed.stderr or ""),
            "_stderr_raw": completed.stderr or "",
            "duration_sec": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + f"\nTimed out after {timeout_sec} seconds."
        return {
            "name": name,
            "command": [str(part) for part in command],
            "returncode": 124,
            "stdout": _tail(stdout),
            "_stdout_raw": stdout,
            "stderr": _tail(stderr),
            "_stderr_raw": stderr,
            "duration_sec": round(time.monotonic() - started, 3),
        }


def _latest_release_zip(package_dir: Path) -> Path | None:
    if not package_dir.exists():
        return None
    candidates = [
        path
        for path in package_dir.glob("*.zip")
        if path.is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _artifact_from_build_stdout(stdout: str, repo_root: Path) -> Path | None:
    for line in stdout.splitlines():
        match = re.search(r"Zip artifact\s*:\s*(.+\.zip)\s*$", line)
        if not match:
            continue
        candidate = Path(match.group(1).strip())
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if candidate.exists():
            return candidate
    return None


def _validation_record_from_build_stdout(stdout: str, repo_root: Path) -> Path | None:
    for line in stdout.splitlines():
        match = re.search(r"Validation seed\s*:\s*(.+\.md)\s*$", line)
        if not match:
            continue
        candidate = Path(match.group(1).strip())
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if candidate.exists():
            return candidate
    return None


def _step_ok(step: dict[str, Any]) -> bool:
    return int(step.get("returncode", 1)) == 0


def _run_step(
    steps: list[dict[str, Any]],
    runner: CommandRunner,
    name: str,
    command: Sequence[str],
    cwd: Path,
    timeout_sec: int,
) -> dict[str, Any]:
    step = runner(name, command, cwd, timeout_sec)
    steps.append(step)
    return step


def _parse_readiness(stdout: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {"parse_error": "readiness_json_invalid", "raw": _tail(stdout, 4000)}
    if isinstance(payload, dict):
        return payload
    return {"parse_error": "readiness_json_not_object", "raw": payload}


def _readiness_state(readiness: dict[str, Any]) -> str | None:
    state = readiness.get("latest_readiness_state", readiness.get("state"))
    if state is None:
        return None
    return str(state)


def _write_report(report: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _public_step(step: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in dict(step or {}).items()
        if not str(key).startswith("_")
    }


def run_release_clean(
    *,
    root: Path | None = None,
    label: str = "release-clean",
    python_executable: str | None = None,
    run_regression: bool = True,
    promote: bool = True,
    timeout_sec: int = 1800,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Run Nova's package-clean lane and write a local readiness report."""
    repo_root = (root or ROOT).resolve()
    package_dir = repo_root / "runtime" / "exports" / "release_packages"
    report_path = repo_root / "runtime" / "release_clean" / "latest_release_clean.json"
    py = python_executable or sys.executable
    runner = command_runner or _default_command_runner
    steps: list[dict[str, Any]] = []
    readiness: dict[str, Any] = {}
    artifact: Path | None = None
    validation_record: Path | None = None

    commands: list[tuple[str, list[str], int]] = [
        ("repo_hygiene", [py, str(repo_root / "scripts" / "repo_hygiene_check.py")], 300),
    ]
    if run_regression:
        commands.append(
            ("regression_all", [py, str(repo_root / "scripts" / "run_regression.py"), "all"], timeout_sec)
        )
    commands.append(("smoke_runtime", [py, str(repo_root / "scripts" / "smoke_test.py")], 600))
    commands.append(
        (
            "package_build",
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(repo_root / "scripts" / "build_release_package.ps1"),
                "-Label",
                label,
            ],
            900,
        )
    )

    ok = True
    failure_reason: str | None = None
    for name, command, step_timeout in commands:
        step = _run_step(steps, runner, name, command, repo_root, step_timeout)
        if not _step_ok(step):
            ok = False
            failure_reason = f"{name}_failed"
            break

    if ok:
        build_step = next((step for step in reversed(steps) if step.get("name") == "package_build"), {})
        artifact = _artifact_from_build_stdout(str(build_step.get("stdout", "")), repo_root)
        validation_record = _validation_record_from_build_stdout(str(build_step.get("stdout", "")), repo_root)
        if artifact is None:
            artifact = _latest_release_zip(package_dir)
        if artifact is None:
            ok = False
            failure_reason = "release_package_missing"

    if ok and artifact is not None:
        verify_step = _run_step(
            steps,
            runner,
            "package_verify",
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(repo_root / "scripts" / "verify_release_package.ps1"),
                str(artifact),
            ],
            repo_root,
            900,
        )
        if not _step_ok(verify_step):
            ok = False
            failure_reason = "package_verify_failed"

    if ok and promote and artifact is not None:
        if validation_record is None:
            ok = False
            failure_reason = "validation_record_missing"

    if ok and promote and artifact is not None and validation_record is not None:
        validate_step = _run_step(
            steps,
            runner,
            "package_validate",
            [
                py,
                str(repo_root / "scripts" / "validate_release_package.py"),
                "--artifact",
                str(artifact),
                "--record",
                str(validation_record),
            ],
            repo_root,
            timeout_sec,
        )
        if not _step_ok(validate_step):
            ok = False
            failure_reason = "package_validate_failed"

    if ok and promote and artifact is not None and validation_record is not None:
        promote_step = _run_step(
            steps,
            runner,
            "package_record_outcome",
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(repo_root / "scripts" / "promote_release_package.ps1"),
                "-Record",
                str(validation_record),
            ],
            repo_root,
            300,
        )
        if not _step_ok(promote_step):
            ok = False
            failure_reason = "package_record_outcome_failed"

    if ok:
        readiness_step = _run_step(
            steps,
            runner,
            "package_readiness",
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(repo_root / "scripts" / "show_release_readiness.ps1"),
                "-Json",
            ],
            repo_root,
            300,
        )
        if _step_ok(readiness_step):
            readiness = _parse_readiness(str(readiness_step.get("_stdout_raw") or readiness_step.get("stdout", "")))
        else:
            ok = False
            failure_reason = "package_readiness_failed"

    readiness_state = _readiness_state(readiness)
    if ok and readiness_state not in {"ready", "ready-with-notes"}:
        ok = False
        failure_reason = "package_readiness_not_ready"

    report = {
        "ok": ok,
        "label": label,
        "artifact": str(artifact) if artifact is not None else None,
        "validation_record": str(validation_record) if validation_record is not None else None,
        "failure_reason": failure_reason,
        "readiness": readiness,
        "steps": [_public_step(step) for step in steps],
        "report_path": str(report_path),
        "created_at_epoch": time.time(),
    }
    _write_report(report, report_path)
    return report
