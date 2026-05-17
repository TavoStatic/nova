from __future__ import annotations

import json
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable, Sequence

from services.release_promotion_judgment import release_validation_record_payload


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "runtime" / "validation" / "release"
LATEST_REPORT = REPORT_DIR / "latest_release_validation.json"

CommandRunner = Callable[[str, Sequence[str], Path, int], dict[str, Any]]
HttpGet = Callable[[str, float], tuple[int, str]]


def _tail(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _read_text_tail(path: Path, limit: int = 12000) -> str:
    try:
        return _tail(path.read_text(encoding="utf-8", errors="replace"), limit)
    except Exception as exc:
        return f"<unreadable command log: {exc}>"


def _terminate_process_tree(pid: int) -> None:
    if pid <= 0:
        return
    if platform.system().lower().startswith("windows"):
        subprocess.run(
            ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        return
    try:
        subprocess.run(
            ["pkill", "-TERM", "-P", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except Exception:
        pass


def _command_log_paths(name: str, log_root: Path) -> tuple[Path, Path]:
    log_dir = Path(log_root)
    log_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{time.strftime('%Y%m%d_%H%M%S')}-{_safe_fragment(name)[:80]}-{uuid.uuid4().hex[:8]}"
    return log_dir / f"{stem}.out.log", log_dir / f"{stem}.err.log"


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
        log_root or (Path(cwd) / "runtime" / "validation" / "release_command_logs"),
    )
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if platform.system().lower().startswith("windows") else 0
    try:
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_file, stderr_path.open("w", encoding="utf-8", errors="replace") as stderr_file:
            process = subprocess.Popen(
                [str(part) for part in command],
                cwd=str(cwd),
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                creationflags=creationflags,
            )
            try:
                returncode = process.wait(timeout=timeout_sec)
                timed_out = False
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_tree(int(process.pid or 0))
                try:
                    returncode = process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    returncode = 124
        return {
            "name": name,
            "command": [str(part) for part in command],
            "returncode": 124 if timed_out else returncode,
            "stdout": _read_text_tail(stdout_path),
            "stderr": _read_text_tail(stderr_path) + (f"\nTimed out after {timeout_sec} seconds." if timed_out else ""),
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


def _default_http_get(url: str, timeout_sec: float) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=timeout_sec) as response:
        body = response.read(12000).decode("utf-8", errors="ignore")
        return int(getattr(response, "status", 0) or 0), body


def _safe_fragment(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-")
    return text or "release-validation"


def _remove_inside(parent: Path, target: Path) -> None:
    parent_resolved = parent.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(parent_resolved)
    except ValueError as exc:
        raise ValueError(f"refusing to remove validation path outside {parent_resolved}: {target_resolved}") from exc
    if target_resolved.exists():
        shutil.rmtree(target_resolved)


def _prepare_package_root(artifact_path: Path, work_root: Path) -> tuple[Path, Path]:
    artifact = artifact_path.resolve()
    if artifact.is_dir():
        return artifact, artifact
    if not artifact.exists():
        raise FileNotFoundError(f"release artifact not found: {artifact}")
    if artifact.suffix.lower() != ".zip":
        raise ValueError(f"release validation expects a zip artifact or extracted package directory: {artifact}")

    work_root.mkdir(parents=True, exist_ok=True)
    extract_root = work_root / f"{_safe_fragment(artifact.stem)}-{time.strftime('%Y%m%d_%H%M%S')}-{uuid.uuid4().hex[:8]}"
    extract_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(artifact, "r") as archive:
        archive.extractall(extract_root)

    package_root = extract_root
    if (package_root / "nova.cmd").exists():
        return package_root, extract_root
    direct_children = [path for path in extract_root.iterdir() if path.is_dir()]
    for child in direct_children:
        if (child / "nova.cmd").exists():
            return child, extract_root
    for candidate in extract_root.rglob("nova.cmd"):
        return candidate.parent, extract_root
    raise FileNotFoundError(f"extracted artifact does not contain nova.cmd: {artifact}")


def _pick_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _step_value(step: dict[str, Any] | None) -> str:
    if not step:
        return "not-run"
    code = int(step.get("returncode", 1) or 0)
    if code == 0:
        return "pass"
    if code == 124:
        return "fail (timeout)"
    return f"fail (exit {code})"


def _step_failed(step: dict[str, Any] | None) -> bool:
    return bool(step) and int(step.get("returncode", 1) or 0) != 0


def _step_passed(step: dict[str, Any] | None) -> bool:
    return bool(step) and int(step.get("returncode", 1) or 0) == 0


def _write_json_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_validation_record(
    record_path: Path,
    *,
    artifact_path: Path,
    artifact_version: str,
    release_channel: str,
    release_label: str,
    version_source: str,
    ledger_path: str,
    manifest_reviewed: str,
    machine_name: str,
    windows_version: str,
    python_source: str,
    ollama_expected: str,
    step_values: dict[str, str],
    result: str,
    blocking_issues: list[str],
    nonblocking_issues: list[str],
    follow_up_owner: str,
) -> None:
    lines = [
        "# NYO System RC Validation Record",
        "",
        f"Date: {time.strftime('%Y-%m-%d')}",
        "",
        "Generated from an observed release validation profile.",
        "",
        "## Candidate",
        "",
        f"- Artifact path: {artifact_path}",
        f"- Artifact version: {artifact_version}",
        f"- Version source: {version_source}",
        f"- Release channel: {release_channel}",
        f"- Release label: {release_label}",
        f"- Manifest reviewed: {manifest_reviewed}",
        f"- Release ledger path: {ledger_path}",
        "",
        "## Environment",
        "",
        f"- Machine or VM name: {machine_name}",
        f"- Windows version: {windows_version}",
        f"- Python source used during install: {python_source}",
        f"- Ollama expected for this target: {ollama_expected}",
        "",
        "## Results",
        "",
        "### Bootstrap",
        "",
        f"- nova package-verify .: {step_values.get('nova package-verify .', 'not-run')}",
        f"- nova install: {step_values.get('nova install', 'not-run')}",
        "- Notes: observed from extracted package root",
        "",
        "### Base Validation",
        "",
        f"- nova doctor: {step_values.get('nova doctor', 'not-run')}",
        f"- nova runtime-status: {step_values.get('nova runtime-status', 'not-run')}",
        f"- nova smoke-base --fix: {step_values.get('nova smoke-base --fix', 'not-run')}",
        f"- nova test: {step_values.get('nova test', 'not-run')}",
        f"- nova wiring-check --offline: {step_values.get('nova wiring-check --offline', 'not-run')}",
        "- Notes: base package validation commands were executed before final decision",
        "",
        "### Operator Surface",
        "",
        f"- nova run: {step_values.get('nova run', 'not-run')}",
        f"- nova webui-start --host 127.0.0.1 --port 8080: {step_values.get('nova webui-start --host 127.0.0.1 --port 8080', 'not-run')}",
        f"- /control load result: {step_values.get('/control load result', 'not-run')}",
        "- Notes: web UI validation used an available local port when 8080 was already owned",
        "",
        "### Extended Runtime Validation",
        "",
        f"- nova smoke --fix: {step_values.get('nova smoke --fix', 'not-run')}",
        "- Notes: extended runtime validation is required only when Ollama is expected for this target",
        "",
        "## Final Decision",
        "",
        f"- Result: {result}",
        f"- Blocking issues: {'; '.join(blocking_issues) if blocking_issues else 'none'}",
        f"- Non-blocking issues: {'; '.join(nonblocking_issues) if nonblocking_issues else 'none'}",
        f"- Follow-up owner: {follow_up_owner}",
    ]
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_release_validation(
    *,
    repo_root: Path | None = None,
    artifact_path: str | Path,
    record_path: str | Path,
    artifact_version: str = "",
    release_channel: str = "rc",
    release_label: str = "",
    version_source: str = "",
    ledger_path: str = "",
    include_runtime: bool = False,
    timeout_sec: int = 1800,
    command_runner: CommandRunner | None = None,
    http_get: HttpGet | None = None,
    work_root: Path | None = None,
    keep_extract: bool = False,
) -> dict[str, Any]:
    root = (repo_root or ROOT).resolve()
    artifact = Path(artifact_path).resolve()
    record = Path(record_path).resolve()
    get_url = http_get or _default_http_get
    validation_root = (work_root or (root / "runtime" / "validation" / "release")).resolve()
    report_path = validation_root / "latest_release_validation.json"
    if command_runner is None:
        command_log_root = validation_root / "release_command_logs"

        def runner(name: str, command: Sequence[str], cwd: Path, timeout_sec: int) -> dict[str, Any]:
            return _default_command_runner(
                name,
                command,
                cwd,
                timeout_sec,
                log_root=command_log_root,
            )
    else:
        runner = command_runner
    steps: list[dict[str, Any]] = []
    blocking_issues: list[str] = []
    nonblocking_issues: list[str] = []
    step_by_label: dict[str, dict[str, Any]] = {}
    control_load_result = "not-run"
    package_root: Path | None = None
    extract_root: Path | None = None
    extract_root_removed = False
    extract_cleanup_error = ""
    webui_attempted = False

    try:
        package_root, extract_root = _prepare_package_root(artifact, validation_root)
        nova_cmd = package_root / "nova.cmd"
        command_plan: list[tuple[str, list[str], int]] = [
            ("nova package-verify .", [str(nova_cmd), "package-verify", "."], 300),
            ("nova install", [str(nova_cmd), "install"], 900),
            ("nova doctor", [str(nova_cmd), "doctor"], 300),
            ("nova runtime-status", [str(nova_cmd), "runtime-status"], 120),
            ("nova wiring-check --offline", [str(nova_cmd), "wiring-check", "--offline"], 300),
            ("nova smoke-base --fix", [str(nova_cmd), "smoke-base", "--fix"], 600),
            ("nova test", [str(nova_cmd), "test"], timeout_sec),
        ]
        if include_runtime:
            command_plan.append(("nova smoke --fix", [str(nova_cmd), "smoke", "--fix"], 900))

        for label, command, step_timeout in command_plan:
            step = runner(label, command, package_root, step_timeout)
            steps.append(step)
            step_by_label[label] = step

        port = _pick_local_port()
        webui_label = "nova webui-start --host 127.0.0.1 --port 8080"
        webui_attempted = True
        webui_step = runner(
            webui_label,
            [str(nova_cmd), "webui-start", "--host", "127.0.0.1", "--port", str(port)],
            package_root,
            240,
        )
        steps.append(webui_step)
        step_by_label[webui_label] = webui_step
        if not _step_failed(webui_step):
            url = f"http://127.0.0.1:{port}/control"
            try:
                status, body = get_url(url, 15.0)
                control_load_result = f"pass (http {status})" if 200 <= status < 500 and body is not None else f"fail (http {status})"
            except Exception as exc:
                control_load_result = f"fail ({exc})"
    except Exception as exc:
        blocking_issues.append(str(exc))
    finally:
        if webui_attempted and package_root is not None and "nova webui-stop" not in step_by_label:
            try:
                nova_cmd = package_root / "nova.cmd"
                stop_step = runner("nova webui-stop", [str(nova_cmd), "webui-stop"], package_root, 90)
                steps.append(stop_step)
                step_by_label["nova webui-stop"] = stop_step
            except Exception as exc:
                blocking_issues.append(f"nova webui-stop cleanup failed: {exc}")
        if (
            not keep_extract
            and extract_root is not None
            and artifact.exists()
            and artifact.is_file()
            and artifact.suffix.lower() == ".zip"
        ):
            try:
                _remove_inside(validation_root, extract_root)
                extract_root_removed = True
            except Exception as exc:
                extract_cleanup_error = str(exc)
                blocking_issues.append(f"release validation extract cleanup failed: {exc}")

    for label in (
        "nova package-verify .",
        "nova install",
        "nova doctor",
        "nova runtime-status",
        "nova wiring-check --offline",
        "nova smoke-base --fix",
        "nova test",
        "nova webui-start --host 127.0.0.1 --port 8080",
        "nova webui-stop",
    ):
        if _step_failed(step_by_label.get(label)):
            blocking_issues.append(f"{label} failed")
    if include_runtime and _step_failed(step_by_label.get("nova smoke --fix")):
        blocking_issues.append("nova smoke --fix failed")
    if control_load_result.startswith("fail"):
        blocking_issues.append("/control load failed")

    nonblocking_issues.append("fresh-machine or VM independence not proven by same-machine extracted-package profile")
    nonblocking_issues.append("nova run interactive front door was not exercised by the noninteractive validation runner")
    result = "fail" if blocking_issues else ("pass-with-notes" if nonblocking_issues else "pass")
    step_values = {label: _step_value(step_by_label.get(label)) for label in step_by_label}
    step_values["/control load result"] = control_load_result
    step_values["nova run"] = "not-run (interactive front door not exercised by noninteractive validation)"
    if not include_runtime:
        step_values["nova smoke --fix"] = "not-run (Ollama not expected for this target)"

    if record:
        _write_validation_record(
            record,
            artifact_path=artifact,
            artifact_version=artifact_version,
            release_channel=release_channel,
            release_label=release_label,
            version_source=version_source,
            ledger_path=ledger_path,
            manifest_reviewed="yes" if _step_passed(step_by_label.get("nova package-verify .")) else "no",
            machine_name=platform.node() or "unknown",
            windows_version=platform.platform() or "unknown",
            python_source=f"{sys.executable} ({platform.python_version()})",
            ollama_expected="yes" if include_runtime else "no",
            step_values=step_values,
            result=result,
            blocking_issues=blocking_issues,
            nonblocking_issues=nonblocking_issues,
            follow_up_owner="release-validation",
        )

    record_payload = release_validation_record_payload(record, release_status={
        "latest_artifact_path": str(artifact),
        "latest_version": artifact_version,
        "latest_channel": release_channel,
    })
    report = {
        "ok": bool(record_payload.get("exists")) and not blocking_issues,
        "completed": bool(record_payload.get("exists")),
        "validation_result": result,
        "validation_record_path": str(record),
        "validation_record_complete": bool(record_payload.get("complete")),
        "artifact": str(artifact),
        "package_root": str(package_root or ""),
        "extract_root": str(extract_root or ""),
        "extract_root_removed": extract_root_removed,
        "extract_root_retained": bool(extract_root is not None and not extract_root_removed),
        "extract_cleanup_error": extract_cleanup_error,
        "include_runtime": include_runtime,
        "blocking_issues": blocking_issues,
        "nonblocking_issues": nonblocking_issues,
        "steps": steps,
        "report_path": str(report_path),
        "created_at_epoch": time.time(),
    }
    _write_json_report(report, report_path)
    return report


def render_release_validation_report(report: dict[str, Any]) -> str:
    steps = [
        f"{step.get('name')}: exit {int(step.get('returncode', 1) or 0)}"
        for step in list(report.get("steps") or [])
        if isinstance(step, dict)
    ]
    lines = [
        "Release Validation Run",
        f"- completed: {bool(report.get('completed'))}",
        f"- validation result: {report.get('validation_result') or 'unknown'}",
        f"- record complete: {bool(report.get('validation_record_complete'))}",
        f"- artifact: {report.get('artifact') or ''}",
        f"- validation record: {report.get('validation_record_path') or ''}",
        f"- report: {report.get('report_path') or ''}",
        f"- blocking issues: {'; '.join(report.get('blocking_issues') or []) or 'none'}",
        f"- non-blocking issues: {'; '.join(report.get('nonblocking_issues') or []) or 'none'}",
        "- steps:",
    ]
    lines.extend(f"  - {item}" for item in steps)
    return "\n".join(lines)


def record_release_validation_outcome(
    *,
    repo_root: Path | None = None,
    record_path: str | Path,
    release_status: dict[str, Any],
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    root = (repo_root or ROOT).resolve()
    record = Path(record_path).resolve()
    status = dict(release_status or {})
    payload = release_validation_record_payload(record, release_status=status)
    report: dict[str, Any] = {
        "ok": True,
        "recorded": False,
        "record_path": str(record),
        "result": str(payload.get("result") or ""),
        "reason": "",
        "step": {},
    }
    if not payload.get("complete"):
        report["reason"] = "validation_record_incomplete"
        report["missing_fields"] = list(payload.get("missing_fields") or [])
        return report

    runner = command_runner or _default_command_runner
    script = root / "scripts" / "promote_release_package.ps1"
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Record",
        str(record),
        "-Result",
        str(payload.get("result") or ""),
    ]
    step = runner("release validation ledger outcome", command, root, 300)
    report["step"] = step
    if int(step.get("returncode", 1) or 0) != 0:
        report["reason"] = "ledger_outcome_write_failed"
        report["ok"] = False
        return report
    report["recorded"] = True
    return report


def render_release_outcome_recording(report: dict[str, Any]) -> str:
    step = report.get("step") if isinstance(report.get("step"), dict) else {}
    lines = [
        "Release Validation Outcome Record",
        f"- recorded: {bool(report.get('recorded'))}",
        f"- result: {report.get('result') or 'unknown'}",
        f"- record: {report.get('record_path') or ''}",
        f"- reason: {report.get('reason') or 'none'}",
    ]
    if step:
        lines.append(f"- ledger command exit: {int(step.get('returncode', 1) or 0)}")
    missing = list(report.get("missing_fields") or [])
    if missing:
        lines.append(f"- missing fields: {', '.join(str(item) for item in missing)}")
    return "\n".join(lines)
