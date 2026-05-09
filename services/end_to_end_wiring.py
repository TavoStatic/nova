from __future__ import annotations

import importlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]

CommandRunner = Callable[[str, Sequence[str], Path, int], dict[str, Any]]

FRONTDOOR_COMMANDS = (
    "doctor",
    "runtime-status",
    "webui",
    "operator",
    "tools",
    "smoke",
    "test",
    "package-readiness",
    "wiring-check",
    "release-clean",
)

REQUIRED_IMPORTS = (
    "services.autonomy_orchestrator",
    "services.control_actions",
    "services.control_pipelines",
    "services.control_work_trees",
    "services.data_pipeline_registry",
    "services.end_to_end_wiring",
    "services.nova_control_action_dispatcher",
    "services.nova_http_pipeline_control",
    "services.nova_http_routing",
    "services.release_clean",
    "services.runtime_status",
    "work_tree",
)

PIPELINE_ACTION_HOOKS = (
    "pipeline_note_append_action_fn",
    "pipeline_create_action_fn",
    "pipeline_start_action_fn",
    "pipeline_pause_action_fn",
    "pipeline_update_action_fn",
    "pipeline_population_upsert_action_fn",
    "pipeline_archive_action_fn",
)

DISPATCHER_PIPELINE_ACTIONS = (
    "pipeline_note_append",
    "pipeline_create",
    "pipeline_start",
    "pipeline_pause",
    "pipeline_update",
    "pipeline_population_upsert",
    "pipeline_archive",
)


def _check(name: str, ok: bool, detail: str, *, required: bool = True, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "required": bool(required),
        "detail": detail,
        "data": data or {},
    }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _default_runner(name: str, command: Sequence[str], cwd: Path, timeout_sec: int) -> dict[str, Any]:
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
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
            "duration_sec": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "command": [str(part) for part in command],
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + f"\nTimed out after {timeout_sec} seconds.",
            "duration_sec": round(time.monotonic() - started, 3),
        }


def _frontdoor_checks(root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    nova_cmd = root / "nova.cmd"
    nova_ps1 = root / "nova.ps1"
    checks.append(_check("frontdoor:nova.cmd", nova_cmd.exists(), "nova.cmd exists"))
    checks.append(_check("frontdoor:nova.ps1", nova_ps1.exists(), "nova.ps1 exists"))

    cmd_text = _read_text(nova_cmd) if nova_cmd.exists() else ""
    ps1_text = _read_text(nova_ps1) if nova_ps1.exists() else ""
    checks.append(
        _check(
            "frontdoor:cmd_delegates_to_ps1",
            "powershell.exe" in cmd_text.lower() and "nova.ps1" in cmd_text.lower(),
            "nova.cmd delegates into nova.ps1",
        )
    )

    missing = [command for command in FRONTDOOR_COMMANDS if f'"{command}"' not in ps1_text]
    checks.append(
        _check(
            "frontdoor:command_cases",
            not missing,
            "front door command cases present" if not missing else "missing command cases: " + ", ".join(missing),
            data={"commands": list(FRONTDOOR_COMMANDS), "missing": missing},
        )
    )
    return checks


def _release_clean_checks(root: Path) -> list[dict[str, Any]]:
    paths = {
        "release_clean_service": root / "services" / "release_clean.py",
        "release_clean_cli": root / "scripts" / "release_clean_check.py",
    }
    checks = [
        _check(f"release-clean:{name}", path.exists(), f"{path.relative_to(root).as_posix()} exists")
        for name, path in paths.items()
    ]
    ps1_text = _read_text(root / "nova.ps1") if (root / "nova.ps1").exists() else ""
    checks.append(
        _check(
            "release-clean:frontdoor_wired",
            "Invoke-NovaReleaseClean" in ps1_text and "$RELEASECLEANPY" in ps1_text,
            "release-clean command resolves through the Nova front door",
        )
    )
    return checks


def _import_checks(root: Path) -> list[dict[str, Any]]:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    checks: list[dict[str, Any]] = []
    for module_name in REQUIRED_IMPORTS:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            checks.append(_check(f"import:{module_name}", False, f"import failed: {exc}"))
        else:
            checks.append(_check(f"import:{module_name}", True, "import ok"))
    return checks


def _pipeline_checks(root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        from services.data_pipeline_registry import list_pipeline_summaries

        summaries = list_pipeline_summaries(root / "data_sources")
    except Exception as exc:
        return [_check("data-lanes:registry", False, f"pipeline registry failed: {exc}")]

    ids = [str(item.get("pipeline_id") or "") for item in summaries]
    checks.append(
        _check(
            "data-lanes:registry",
            True,
            "registered lanes: " + ", ".join(ids)
            if ids
            else "pipeline registry available; no bundled data lanes",
            data={"pipeline_ids": ids},
        )
    )
    checks.append(
        _check(
            "data-lanes:sis_test_present",
            "sis_test" in ids,
            "sis_test lane present" if "sis_test" in ids else "sis_test lane missing",
            required=False,
        )
    )

    dispatcher_path = root / "services" / "nova_control_action_dispatcher.py"
    dispatcher_text = _read_text(dispatcher_path) if dispatcher_path.exists() else ""
    missing_actions = [action for action in DISPATCHER_PIPELINE_ACTIONS if action not in dispatcher_text]
    checks.append(
        _check(
            "data-lanes:dispatcher_actions",
            not missing_actions,
            "pipeline actions registered in dispatcher"
            if not missing_actions
            else "missing dispatcher actions: " + ", ".join(missing_actions),
            data={"missing": missing_actions},
        )
    )

    try:
        from services.nova_http_pipeline_control import HTTP_PIPELINE_CONTROL_SERVICE

        runtime_scope = {
            "CONTROL_PIPELINES_SERVICE": object(),
            "DATA_SOURCES_DIR": root / "data_sources",
            "pipeline_list_summaries": lambda *_args, **_kwargs: [],
        }
        hooks = HTTP_PIPELINE_CONTROL_SERVICE.action_hooks_from_runtime(runtime_scope)
        missing_hooks = [hook for hook in PIPELINE_ACTION_HOOKS if hook not in hooks]
    except Exception as exc:
        checks.append(_check("data-lanes:http_action_hooks", False, f"pipeline HTTP hooks failed: {exc}"))
    else:
        checks.append(
            _check(
                "data-lanes:http_action_hooks",
                not missing_hooks,
                "pipeline HTTP action hooks exposed"
                if not missing_hooks
                else "missing HTTP hooks: " + ", ".join(missing_hooks),
                data={"missing": missing_hooks},
            )
        )
    return checks


def _latest_release_clean_check(root: Path) -> dict[str, Any]:
    path = root / "runtime" / "release_clean" / "latest_release_clean.json"
    if not path.exists():
        return _check("release-clean:latest_report", False, "latest release-clean report missing")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _check("release-clean:latest_report", False, f"latest release-clean report unreadable: {exc}")
    ok = bool(report.get("ok"))
    readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
    state = readiness.get("latest_readiness_state") or readiness.get("state") or "unknown"
    artifact = str(report.get("artifact") or "")
    return _check(
        "release-clean:latest_report",
        ok,
        f"latest report ok; readiness={state}; artifact={artifact}" if ok else f"latest report not ok: {report.get('failure_reason')}",
        data={"readiness": state, "artifact": artifact, "report_path": str(path)},
    )


def _health_check(root: Path, runner: CommandRunner, python_executable: str, timeout_sec: int) -> dict[str, Any]:
    health_py = root / "health.py"
    if not health_py.exists():
        return _check("runtime:health", False, "health.py missing")
    result = runner("runtime_health", [python_executable, str(health_py), "check"], root, timeout_sec)
    if int(result.get("returncode", 1)) != 0:
        return _check("runtime:health", False, "health.py check failed", data={"result": result})
    try:
        payload = json.loads(str(result.get("stdout") or "{}"))
    except Exception as exc:
        return _check("runtime:health", False, f"health output was not JSON: {exc}", data={"result": result})
    return _check(
        "runtime:health",
        bool(payload.get("ok")),
        "runtime health ok" if payload.get("ok") else "runtime health returned ok=false",
        data={"health": payload},
    )


def _autonomy_log_check(root: Path, *, max_age_sec: int = 3600) -> dict[str, Any]:
    path = root / "runtime" / "autonomy_maintenance.log"
    if not path.exists():
        return _check("runtime:autonomy_log", False, "autonomy maintenance log missing")
    age = max(0, int(time.time() - path.stat().st_mtime))
    text = path.read_text(encoding="utf-8", errors="replace")[-12000:]
    has_orchestrator = "autonomy_orchestrator" in text
    has_cycle = "active_work_tree_cycle" in text or "generated_queue_cycle" in text or "work_tree_cycle" in text
    ok = age <= max_age_sec and has_orchestrator and has_cycle
    detail = f"age={age}s orchestrator={has_orchestrator} cycle={has_cycle}"
    return _check("runtime:autonomy_log", ok, detail, data={"age_sec": age})


def run_end_to_end_wiring_check(
    *,
    root: Path | None = None,
    include_runtime: bool = True,
    python_executable: str | None = None,
    command_runner: CommandRunner | None = None,
    timeout_sec: int = 60,
) -> dict[str, Any]:
    repo_root = (root or ROOT).resolve()
    runner = command_runner or _default_runner
    py = python_executable or sys.executable

    checks: list[dict[str, Any]] = []
    checks.extend(_frontdoor_checks(repo_root))
    checks.extend(_release_clean_checks(repo_root))
    checks.extend(_import_checks(repo_root))
    checks.extend(_pipeline_checks(repo_root))

    if include_runtime:
        checks.append(_latest_release_clean_check(repo_root))
        checks.append(_health_check(repo_root, runner, py, timeout_sec))
        checks.append(_autonomy_log_check(repo_root))
    else:
        checks.append(_check("runtime:live_checks", True, "skipped by offline mode", required=False))

    required_checks = [check for check in checks if check.get("required")]
    failed = [check for check in required_checks if not check.get("ok")]
    return {
        "ok": not failed,
        "root": str(repo_root),
        "include_runtime": include_runtime,
        "failed_count": len(failed),
        "check_count": len(checks),
        "checks": checks,
    }
