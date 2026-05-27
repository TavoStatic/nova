from __future__ import annotations

from datetime import datetime
import json
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Sequence

from services.release_status import RELEASE_STATUS_SERVICE


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "runtime" / "validation" / "installer"
LATEST_REPORT = REPORT_DIR / "latest_installer_validation.json"

CommandRunner = Callable[[str, Sequence[str], Path, int], dict[str, Any]]


def _tail(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _safe_fragment(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-")
    return text or "installer-validation"


def _command_log_paths(name: str, log_root: Path) -> tuple[Path, Path]:
    log_root.mkdir(parents=True, exist_ok=True)
    stem = f"{time.strftime('%Y%m%d_%H%M%S')}-{_safe_fragment(name)[:80]}-{uuid.uuid4().hex[:8]}"
    return log_root / f"{stem}.out.log", log_root / f"{stem}.err.log"


def _read_text_tail(path: Path, limit: int = 12000) -> str:
    try:
        return _tail(path.read_text(encoding="utf-8", errors="replace"), limit)
    except Exception as exc:
        return f"<unreadable command log: {exc}>"


def _default_command_runner(
    name: str,
    command: Sequence[str],
    cwd: Path,
    timeout_sec: int,
    *,
    log_root: Path | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    stdout_path, stderr_path = _command_log_paths(
        name,
        log_root or (Path(cwd) / "runtime" / "validation" / "installer_command_logs"),
    )
    try:
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_file, stderr_path.open("w", encoding="utf-8", errors="replace") as stderr_file:
            completed = subprocess.run(
                [str(part) for part in command],
                cwd=str(cwd),
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                timeout=timeout_sec,
            )
        return {
            "name": name,
            "command": [str(part) for part in command],
            "returncode": int(completed.returncode),
            "stdout": _read_text_tail(stdout_path),
            "stderr": _read_text_tail(stderr_path),
            "duration_sec": round(time.monotonic() - started, 3),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
    except subprocess.TimeoutExpired:
        return {
            "name": name,
            "command": [str(part) for part in command],
            "returncode": 124,
            "stdout": _read_text_tail(stdout_path),
            "stderr": _tail(_read_text_tail(stderr_path) + f"\nTimed out after {timeout_sec} seconds."),
            "duration_sec": round(time.monotonic() - started, 3),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
    except Exception as exc:
        return {
            "name": name,
            "command": [str(part) for part in command],
            "returncode": 1,
            "stdout": _read_text_tail(stdout_path) if stdout_path.exists() else "",
            "stderr": _tail((_read_text_tail(stderr_path) if stderr_path.exists() else "") + f"\nCommand runner failed: {exc}"),
            "duration_sec": round(time.monotonic() - started, 3),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }


def _step_failed(step: dict[str, Any] | None) -> bool:
    return bool(step) and int((step or {}).get("returncode", 1) or 0) != 0


def _info_value(stdout: str, label: str) -> str:
    prefix = f"[INFO] {label}"
    for line in str(stdout or "").splitlines():
        text = line.strip()
        if not text.startswith(prefix):
            continue
        if ":" in text:
            return text.split(":", 1)[1].strip()
    return ""


def _write_report(report: dict[str, Any], report_path: Path | None = None) -> None:
    path = Path(report_path or LATEST_REPORT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def run_installer_validation(
    *,
    repo_root: Path | str = ROOT,
    package_artifact_path: str = "",
    compiler_path: str = "",
    promote_result: str = "pass-with-notes",
    promotion_note: str = "automated installer file/provenance validation; guided install flow not independently proven",
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    runner = command_runner or _default_command_runner
    ledger_path = root / "runtime" / "exports" / "release_packages" / "release_ledger.jsonl"
    package_status = RELEASE_STATUS_SERVICE.status_payload(
        ledger_path,
        8,
        source_root=root,
        artifact_kind="package-zip",
    )
    package_artifact = str(package_artifact_path or package_status.get("latest_artifact_path") or "").strip()
    report: dict[str, Any] = {
        "schema": "installer_validation_report.v1",
        "generated_at": datetime.now().isoformat(),
        "ok": False,
        "completed": False,
        "validation_result": "",
        "failure_reason": "",
        "package_artifact": package_artifact,
        "installer_artifact": "",
        "validation_record": "",
        "report_path": str(LATEST_REPORT),
        "steps": [],
    }

    if not package_artifact:
        report["failure_reason"] = "package_artifact_missing"
        _write_report(report)
        return report

    build_command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(root / "scripts" / "build_windows_installer.ps1"),
        "-Artifact",
        package_artifact,
    ]
    if compiler_path:
        build_command.extend(["-Compiler", compiler_path])

    build_step = runner("build_windows_installer", build_command, root, 240)
    report["steps"].append(build_step)
    if _step_failed(build_step):
        report["failure_reason"] = "installer_build_failed"
        _write_report(report)
        return report

    installer_artifact = _info_value(str(build_step.get("stdout") or ""), "Installer output")
    validation_record = _info_value(str(build_step.get("stdout") or ""), "Validation seed")
    report["installer_artifact"] = installer_artifact
    report["validation_record"] = validation_record
    if not installer_artifact:
        report["failure_reason"] = "installer_artifact_not_reported"
        _write_report(report)
        return report

    verify_step = runner(
        "verify_windows_installer",
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / "scripts" / "verify_windows_installer.ps1"),
            installer_artifact,
        ],
        root,
        120,
    )
    report["steps"].append(verify_step)
    if _step_failed(verify_step):
        report["failure_reason"] = "installer_verify_failed"
        _write_report(report)
        return report

    promote_step = runner(
        "promote_windows_installer",
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / "scripts" / "promote_release_package.ps1"),
            "-ArtifactKind",
            "windows-installer",
            "-Artifact",
            installer_artifact,
            "-Result",
            promote_result,
            "-Note",
            promotion_note,
        ],
        root,
        120,
    )
    report["steps"].append(promote_step)
    if _step_failed(promote_step):
        report["failure_reason"] = "installer_promotion_failed"
        _write_report(report)
        return report

    installer_status = RELEASE_STATUS_SERVICE.status_payload(
        ledger_path,
        8,
        source_root=None,
        artifact_kind="windows-installer",
    )
    report.update(
        {
            "ok": True,
            "completed": True,
            "validation_result": promote_result,
            "failure_reason": "",
            "installer_status": installer_status,
        }
    )
    _write_report(report)
    return report


def render_installer_validation_report(report: dict[str, Any]) -> str:
    payload = dict(report or {})
    ok = bool(payload.get("ok"))
    prefix = "Installer Validation Run" if ok else "[FAIL] Installer Validation Run"
    steps = [
        f"{str(step.get('name') or 'step')}: exit {int(step.get('returncode', 1) or 0)}"
        for step in list(payload.get("steps") or [])
        if isinstance(step, dict)
    ]
    lines = [
        prefix,
        f"- completed: {bool(payload.get('completed'))}",
        f"- validation result: {str(payload.get('validation_result') or '')}",
        f"- package artifact: {str(payload.get('package_artifact') or '')}",
        f"- installer artifact: {str(payload.get('installer_artifact') or '')}",
        f"- validation record: {str(payload.get('validation_record') or '')}",
        f"- report: {str(payload.get('report_path') or LATEST_REPORT)}",
        f"- failure reason: {str(payload.get('failure_reason') or 'none')}",
    ]
    if steps:
        lines.append("- steps:")
        lines.extend(f"  - {step}" for step in steps)
    return "\n".join(lines)
