from __future__ import annotations

from datetime import datetime
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
from pathlib import PurePosixPath
from typing import Any, Callable, Sequence

from services.release_validation_contracts import NOVA_WEBUI_START_8080_LABEL
from services.release_promotion_judgment import release_validation_record_payload


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "runtime" / "validation" / "release"
LATEST_REPORT = REPORT_DIR / "latest_release_validation.json"
REGRESSION_STATUS_FILE = ROOT / "runtime" / "regression_status.json"
REGRESSION_STATUS_MAX_AGE_SEC = 6 * 60 * 60
REQUIRED_REGRESSION_LANES = ("unit", "behavior", "integration")

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


def _safe_zip_parts(name: str) -> tuple[str, ...]:
    normalized = str(name or "").replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute():
        return ()
    parts = tuple(part for part in path.parts if part not in {"", "."})
    if not parts or any(part == ".." for part in parts):
        return ()
    return parts


def _strip_prefix(parts: tuple[str, ...], prefix: tuple[str, ...]) -> tuple[str, ...]:
    if prefix and parts[: len(prefix)] != prefix:
        return ()
    return parts[len(prefix) :]


def _prepare_package_root(artifact_path: Path, work_root: Path) -> tuple[Path, Path]:
    artifact = artifact_path.resolve()
    if artifact.is_dir():
        return artifact, artifact
    if not artifact.exists():
        raise FileNotFoundError(f"release artifact not found: {artifact}")
    if artifact.suffix.lower() != ".zip":
        raise ValueError(f"release validation expects a zip artifact or extracted package directory: {artifact}")

    work_root.mkdir(parents=True, exist_ok=True)
    extract_root = work_root / f"x-{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    extract_root.mkdir(parents=True, exist_ok=True)
    try:
        package_root = extract_root / "pkg"
        package_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(artifact, "r") as archive:
            members = archive.infolist()
            member_parts = [(info, _safe_zip_parts(info.filename)) for info in members]
            nova_prefixes = [
                parts[:-1]
                for info, parts in member_parts
                if parts and not info.is_dir() and parts[-1].lower() == "nova.cmd"
            ]
            if not nova_prefixes:
                raise FileNotFoundError(f"release artifact does not contain nova.cmd: {artifact}")
            package_prefix = sorted(nova_prefixes, key=len)[0]
            for info, parts in member_parts:
                if not parts:
                    continue
                relative_parts = _strip_prefix(parts, package_prefix)
                if not relative_parts:
                    continue
                target = package_root.joinpath(*relative_parts)
                target_resolved = target.resolve()
                try:
                    target_resolved.relative_to(package_root.resolve())
                except ValueError as exc:
                    raise ValueError(f"refusing to extract package member outside {package_root}: {info.filename}") from exc
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)

        if (package_root / "nova.cmd").exists():
            return package_root, extract_root
        raise FileNotFoundError(f"extracted artifact does not contain nova.cmd: {artifact}")
    except Exception:
        _remove_inside(work_root, extract_root)
        raise


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


def _nova_run_probe_command(nova_cmd: Path, *, exercise_turn: bool = False) -> list[str]:
    probe_input = "ping`nq`n" if exercise_turn else "q`n"
    if platform.system().lower().startswith("windows"):
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f'& {{ param($novaCmd) "{probe_input}" | & $novaCmd run --fix }}',
            str(nova_cmd),
        ]
    probe_input = "ping\nq\n" if exercise_turn else "q\n"
    return [
        "sh",
        "-c",
        "printf '%s' \"$2\" | \"$1\" run --fix",
        "nova-run-probe",
        str(nova_cmd),
        probe_input,
    ]


def _parse_regression_generated_at(payload: dict[str, Any]) -> float:
    raw = str(payload.get("generated_at") or "").strip()
    if not raw:
        return 0.0
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return float(datetime.strptime(raw, fmt).timestamp())
        except ValueError:
            continue
    return 0.0


def _load_regression_status(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _regression_status_gate(
    *,
    status_path: Path,
    max_age_sec: int = REGRESSION_STATUS_MAX_AGE_SEC,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    now = float(now_epoch if now_epoch is not None else time.time())
    path = Path(status_path)
    payload = _load_regression_status(path)
    status = str(payload.get("status") or "").strip().upper()
    lanes = [str(item).strip() for item in list(payload.get("lanes") or []) if str(item).strip()]
    generated_epoch = _parse_regression_generated_at(payload)
    age_sec = max(0.0, now - generated_epoch) if generated_epoch else None
    returncode = int(payload.get("returncode", 1) or 0) if payload else 1
    missing_lanes = [lane for lane in REQUIRED_REGRESSION_LANES if lane not in set(lanes)]
    blocking: list[str] = []
    if not path.exists():
        blocking.append(f"full regression status missing: {path}")
    elif not payload:
        blocking.append(f"full regression status unreadable: {path}")
    if status != "OK" or returncode != 0:
        detail = str(payload.get("detail") or "").strip()
        suffix = f" detail={detail}" if detail else ""
        blocking.append(f"full regression status is not OK: status={status or 'UNKNOWN'} returncode={returncode}{suffix}")
    if missing_lanes:
        blocking.append(f"full regression status missing required lanes: {', '.join(missing_lanes)}")
    if generated_epoch <= 0:
        blocking.append("full regression status has no parseable generated_at timestamp")
    elif age_sec is not None and age_sec > int(max_age_sec):
        # Honest: stale host regression is a host refresh problem, not a package rebuild problem.
        blocking.append(
            f"full regression status is stale: age_sec={int(age_sec)} max_age_sec={int(max_age_sec)} "
            f"(refresh host runtime/regression_status.json via scripts/run_regression.py all; "
            f"rebuilding the package zip does not refresh this gate)"
        )
    return {
        "ok": not blocking,
        "path": str(path),
        "status": status,
        "returncode": returncode,
        "generated_at": str(payload.get("generated_at") or ""),
        "age_sec": None if age_sec is None else int(age_sec),
        "max_age_sec": int(max_age_sec),
        "lanes": lanes,
        "required_lanes": list(REQUIRED_REGRESSION_LANES),
        "missing_lanes": missing_lanes,
        "detail": str(payload.get("detail") or ""),
        "blocking_issues": blocking,
    }


def classify_release_validation_failures(
    *,
    blocking_issues: list[Any] | None = None,
    regression_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Root classification of why release validation failed.

    Used to choose the next rail honestly:
    - host regression issues are fixed by refreshing host regression, not rebuild
    - package command/wiring/test issues need package/source fixes (then rebuild)
    - mixed failures need host first, then package
    """
    issues = [str(item or "").strip() for item in list(blocking_issues or []) if str(item or "").strip()]
    gate = dict(regression_gate or {}) if isinstance(regression_gate, dict) else {}
    classes: list[str] = []
    for issue in issues:
        low = issue.lower()
        if "regression status is stale" in low:
            classes.append("host_regression_stale")
        elif "regression status is not ok" in low or "regression status missing" in low or "regression status unreadable" in low:
            classes.append("host_regression_unhealthy")
        elif "regression status has no parseable" in low or "missing required lanes" in low:
            classes.append("host_regression_unhealthy")
        elif "wiring-check" in low:
            classes.append("package_wiring_check_failed")
        elif "nova test failed" in low or low.rstrip(".").endswith("nova test failed"):
            classes.append("package_test_failed")
        elif "modulenotfound" in low or "no module named" in low or "package incomplete" in low:
            classes.append("package_incomplete")
        elif any(
            token in low
            for token in (
                "package-verify",
                "nova install failed",
                "nova doctor failed",
                "nova runtime-status failed",
            )
        ):
            classes.append("package_bootstrap_failed")
        elif "failed" in low:
            classes.append("package_command_failed")

    # Also derive host class from gate flags when issues already listed.
    if gate and not gate.get("ok", True):
        gate_issues = [str(item).lower() for item in list(gate.get("blocking_issues") or [])]
        if any("stale" in item for item in gate_issues) and "host_regression_stale" not in classes:
            if str(gate.get("status") or "").upper() == "OK" and int(gate.get("returncode", 1) or 0) == 0:
                classes.append("host_regression_stale")
            elif "host_regression_unhealthy" not in classes and "host_regression_stale" not in classes:
                classes.append("host_regression_unhealthy")

    unique = sorted(set(classes))
    host = sorted(c for c in unique if c.startswith("host_"))
    package = sorted(c for c in unique if c.startswith("package_"))

    if host and not package:
        next_rail = "host_regression_refresh"
        rebuild_helps = False
    elif package and not host:
        next_rail = "package_source_fix_then_rebuild"
        rebuild_helps = True
    elif host and package:
        next_rail = "host_then_package"
        rebuild_helps = True
    elif unique:
        next_rail = "revalidate"
        rebuild_helps = False
    else:
        next_rail = "none"
        rebuild_helps = False

    return {
        "classes": unique,
        "host_blockers": host,
        "package_blockers": package,
        "next_rail": next_rail,
        # Rebuild without a package-side fix (or source change) is thrash when
        # only host gates failed — rebuild never refreshes host regression_status.
        "rebuild_helps": bool(rebuild_helps),
        "rebuild_is_thrash_without_source_or_package_fix": bool(host and not package) or next_rail == "host_regression_refresh",
        "recommended_host_action": (
            "Run scripts/run_regression.py all so runtime/regression_status.json is fresh OK"
            if host
            else ""
        ),
        "recommended_package_action": (
            "Fix package/source failures (wiring-check, tests, missing modules), then rebuild+revalidate"
            if package
            else ""
        ),
    }


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
    regression_gate: dict[str, Any],
    follow_up_owner: str,
) -> None:
    lines = [
        "# Nova RC Validation Record",
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
        f"- full regression status: {'pass' if regression_gate.get('ok') else 'fail'}",
        f"- full regression source: {regression_gate.get('path') or ''}",
        f"- full regression generated_at: {regression_gate.get('generated_at') or ''}",
        f"- full regression lanes: {', '.join(list(regression_gate.get('lanes') or [])) or 'none'}",
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
        f"- {NOVA_WEBUI_START_8080_LABEL}: {step_values.get(NOVA_WEBUI_START_8080_LABEL, 'not-run')}",
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
    regression_status_path: str | Path | None = None,
    regression_max_age_sec: int = REGRESSION_STATUS_MAX_AGE_SEC,
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
    regression_gate = _regression_status_gate(
        status_path=Path(regression_status_path).resolve()
        if regression_status_path is not None
        else (root / "runtime" / "regression_status.json").resolve(),
        max_age_sec=int(regression_max_age_sec),
    )
    blocking_issues.extend(list(regression_gate.get("blocking_issues") or []))
    step_by_label: dict[str, dict[str, Any]] = {}
    control_load_result = "not-run"
    package_root: Path | None = None
    extract_root: Path | None = None
    extract_root_removed = False
    extract_cleanup_error = ""
    webui_attempted = False
    port = 0

    try:
        package_root, extract_root = _prepare_package_root(artifact, validation_root)
        nova_cmd = package_root / "nova.cmd"
        command_plan: list[tuple[str, list[str], int]] = [
            ("nova package-verify .", [str(nova_cmd), "package-verify", "."], 300),
            ("nova install", [str(nova_cmd), "install"], 900),
            ("nova doctor", [str(nova_cmd), "doctor"], 300),
            ("nova runtime-status", [str(nova_cmd), "runtime-status"], 120),
            ("nova run", _nova_run_probe_command(nova_cmd, exercise_turn=include_runtime), 240),
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
        webui_label = NOVA_WEBUI_START_8080_LABEL
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
                stop_step = runner(
                    "nova webui-stop",
                    [str(nova_cmd), "webui-stop", "--port", str(port)],
                    package_root,
                    90,
                )
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
        "nova run",
        "nova wiring-check --offline",
        "nova smoke-base --fix",
        "nova test",
        NOVA_WEBUI_START_8080_LABEL,
        "nova webui-stop",
    ):
        if _step_failed(step_by_label.get(label)):
            blocking_issues.append(f"{label} failed")
    if include_runtime and _step_failed(step_by_label.get("nova smoke --fix")):
        blocking_issues.append("nova smoke --fix failed")
    if control_load_result.startswith("fail"):
        blocking_issues.append("/control load failed")

    nonblocking_issues.append("fresh-machine or VM independence not proven by same-machine extracted-package profile")
    result = "fail" if blocking_issues else ("pass-with-notes" if nonblocking_issues else "pass")
    step_values = {label: _step_value(step_by_label.get(label)) for label in step_by_label}
    step_values["/control load result"] = control_load_result
    if _step_passed(step_by_label.get("nova run")):
        step_values["nova run"] = "pass (scripted turn)" if include_runtime else "pass (launch/exit)"
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
            regression_gate=regression_gate,
            follow_up_owner="release-validation",
        )

    record_payload = release_validation_record_payload(record, release_status={
        "latest_artifact_path": str(artifact),
        "latest_version": artifact_version,
        "latest_channel": release_channel,
    })
    failure_classes = classify_release_validation_failures(
        blocking_issues=blocking_issues,
        regression_gate=regression_gate,
    )
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
        "regression_gate": regression_gate,
        "blocking_issues": blocking_issues,
        "nonblocking_issues": nonblocking_issues,
        "failure_classes": failure_classes,
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
    failure = report.get("failure_classes") if isinstance(report.get("failure_classes"), dict) else {}
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
        f"- failure classes: {', '.join(list(failure.get('classes') or [])) or 'none'}",
        f"- next rail: {failure.get('next_rail') or 'none'}",
        f"- rebuild helps: {bool(failure.get('rebuild_helps'))}",
        f"- host action: {failure.get('recommended_host_action') or 'none'}",
        f"- package action: {failure.get('recommended_package_action') or 'none'}",
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
