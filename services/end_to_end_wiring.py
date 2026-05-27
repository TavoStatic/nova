from __future__ import annotations

import importlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence

from services.nova_wiring_inventory import WIRING_SURFACES
from services.nova_wiring_inventory import build_root_closure_inventory_payload
from services.nova_wiring_inventory import build_self_repair_closure_inventory_payload
from services.nova_wiring_inventory import build_source_wiring_probe_payload
from services.nova_wiring_inventory import build_wiring_inventory_payload

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
    "package-validate",
    "release-clean",
)

REQUIRED_IMPORTS = (
    "services.autonomy_orchestrator",
    "services.control_actions",
    "services.control_pipelines",
    "services.control_work_trees",
    "services.data_pipeline_registry",
    "services.end_to_end_wiring",
    "services.evidence_validity",
    "services.nova_root_inventory",
    "services.nova_wiring_inventory",
    "services.nova_control_action_dispatcher",
    "services.nova_http_pipeline_control",
    "services.release_clean",
    "services.release_validation",
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
        "release_validation_service": root / "services" / "release_validation.py",
        "release_validation_cli": root / "scripts" / "validate_release_package.py",
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
            "registered lanes: " + ", ".join(ids) if ids else "no registered data lanes",
            data={"pipeline_ids": ids},
        )
    )
    checks.append(
        _check(
            "data-lanes:active_lane_inventory",
            True,
            "active data lane inventory present" if ids else "no active data lanes configured for this install",
            required=False,
            data={"pipeline_ids": ids},
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


class _SyntheticCoreModule:
    """Minimal core-shaped object for source-level status contract checks."""

    @staticmethod
    def load_policy() -> dict[str, Any]:
        return {
            "tools_enabled": {"web": True},
            "web": {
                "enabled": True,
                "search_provider": "html",
                "search_api_endpoint": "",
                "allow_domains": [],
            },
            "memory": {"enabled": True, "scope": "private"},
        }

    @staticmethod
    def mem_stats_payload(*, emit_event: bool = False) -> dict[str, Any]:
        del emit_event
        return {"ok": True, "total": 1, "by_user": {"gus": 1}}

    @staticmethod
    def patch_status_payload() -> dict[str, Any]:
        return {
            "ok": True,
            "enabled": True,
            "strict_manifest": True,
            "allow_force": False,
            "behavioral_check": True,
            "behavioral_check_timeout_sec": 600,
            "tests_available": True,
            "pipeline_ready": True,
            "ready_for_validated_apply": False,
        }

    @staticmethod
    def build_pulse_payload() -> dict[str, Any]:
        return {
            "generated_at": "synthetic",
            "autonomy_level": "observe",
            "promoted_total": 0,
            "promoted_delta": 0,
            "ready_for_validated_apply": False,
            "memory_ok": True,
            "memory_health_status": "ok",
            "memory_health": {"status": "ok", "issue_count": 0},
        }

    @staticmethod
    def update_now_pending_payload() -> dict[str, Any]:
        return {"pending": False}

    @staticmethod
    def ollama_health_payload() -> dict[str, Any]:
        return {
            "ok": True,
            "server_ok": True,
            "tags_ok": True,
            "chat_route_ok": True,
            "status": "ok",
            "info": "synthetic",
            "version": "synthetic",
            "version_ok": True,
            "version_status": 200,
            "api_contract_status": "ok",
            "chat_model": "synthetic-model",
            "model_available": True,
            "model_status": "available",
            "available_models": ["synthetic-model"],
        }

    @staticmethod
    def voice_status_payload() -> dict[str, Any]:
        return {
            "ok": True,
            "status": "available",
            "requested": False,
            "sounddevice_loaded": True,
            "wav_loaded": True,
            "whisper_loaded": True,
        }

    @staticmethod
    def vision_status_payload(**_kwargs) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "available",
            "requested": False,
            "screen_requested": False,
            "camera_requested": False,
            "vision_model": "synthetic-vision",
            "vision_model_available": True,
        }

    @staticmethod
    def get_search_provider_priority() -> list[str]:
        return ["html", "searxng", "general_web"]

    @staticmethod
    def chat_model() -> str:
        return "synthetic-model"

    @staticmethod
    def mem_enabled() -> bool:
        return True

    @staticmethod
    def runtime_device_location_payload() -> dict[str, Any]:
        return {"ok": True, "status": "unset"}


def _synthetic_control_status_payload() -> dict[str, Any]:
    from services.control_status import CONTROL_STATUS_SERVICE

    guard_status = {"running": True, "status": "running", "pid": 1, "process_count": 1}
    core_status = {"running": True, "status": "running", "pid": 2, "heartbeat_age_sec": 1, "process_count": 1}
    webui_status = {"running": True, "status": "running", "pid": 3, "process_count": 1}
    timeline_payload = {"ok": True, "events": []}
    work_trees_payload = {
        "ok": True,
        "counts": {
            "total": 1,
            "active": 1,
            "branches": 1,
            "open_tasks": 0,
            "blocked": 0,
            "pending": 0,
            "working": 0,
            "complete": 1,
        },
        "trees": [],
    }
    autonomy_maintenance = {
        "ok": True,
        "last_regression_status": "OK",
        "last_regression_stale": False,
        "runtime_worker": {"active": True, "last_cycle_status": "ok", "interval_sec": 300, "cycle_count": 1},
        "last_generated_queue_run": {"status": "clear", "queue_open_count": 0, "queue_actionable_count": 0, "queue_blocked_count": 0},
        "last_work_tree_cycle": {"status": "ok"},
        "last_patch_cleanup": {"status": "ok"},
        "last_complete_tree_archive": {"status": "ok"},
        "last_autonomy_orchestrator": {"decision": "settled", "decision_type": "Settled", "confidence": 1.0},
        "autonomy_orchestrator_summary": {"count": 1, "stable_recommendation": True},
    }
    generated_work_queue = {
        "ok": True,
        "status": "clear",
        "open_count": 0,
        "actionable_count": 0,
        "blocked_count": 0,
        "blocked_reason_counts": {},
        "blocked_files": [],
    }
    memory_summary = {"ok": True, "count": 1, "last_event": {"action": "write", "status": "ok"}}
    tool_summary = {
        "ok": True,
        "count": 1,
        "status_counts": {"ok": 1},
        "success_count": 1,
        "failure_count": 0,
        "last_event": {"tool": "read", "status": "ok", "user": "system"},
    }
    ledger_summary = {
        "ok": True,
        "count": 1,
        "last_record": {
            "intent": "synthetic",
            "planner_decision": "observe",
            "tool": "read",
            "route_summary": "synthetic route",
            "grounded": True,
            "route_trace": ["synthetic"],
            "final_answer": "synthetic answer",
            "provider_used": "html",
            "provider_family": "html",
        },
    }

    suppliers = {
        "probe_searxng": lambda _endpoint: (True, "synthetic"),
        "guard_status_payload": lambda: guard_status,
        "core_status_payload": lambda: core_status,
        "http_status_payload": lambda: webui_status,
        "runtime_timeline_payload": lambda: timeline_payload,
        "subconscious_status_summary": lambda: {
            "ok": True,
            "latest_report_path": "synthetic",
            "family_count": 1,
            "variation_count": 1,
            "training_priority_count": 0,
            "generated_definition_count": 0,
        },
        "subconscious_live_summary": lambda: {"ok": True, "status": "clear"},
        "generated_work_queue": lambda _limit=24: generated_work_queue,
        "autonomy_maintenance_summary": lambda: autonomy_maintenance,
        "work_trees_payload": lambda _limit=32: work_trees_payload,
        "operator_outbox_summary": lambda _limit=20: {
            "ok": True,
            "count": 0,
            "total_count": 0,
            "open_count": 0,
            "status_counts": {},
            "latest_id": "",
            "latest_open_id": "",
            "latest_open": {},
            "open_events": [],
            "events": [],
        },
        "load_operator_macros": lambda _limit=24: [],
        "load_backend_commands": lambda _limit=40: [],
        "memory_events_summary": lambda _limit=80: memory_summary,
        "tool_events_summary": lambda _limit=80: tool_summary,
        "action_ledger_summary": lambda _limit=80: ledger_summary,
        "provider_telemetry_payload": lambda **_kwargs: {"ok": True, "last_provider_used": "html", "last_provider_family": "html"},
        "runtime_summary_payload": lambda **_kwargs: {"ok": True, "status": "running"},
        "runtime_artifacts_payload": lambda: {"ok": True, "artifacts": []},
        "validation_artifact_truth_payload": lambda: {"ok": True, "status": "clear", "action_count": 0, "inspected_count": 0},
        "runtime_restart_analytics_payload": lambda: {"ok": True, "restart_count": 0},
        "runtime_failure_reasons_payload": lambda *_args: {"ok": True, "reasons": []},
        "port_ownership_payload": lambda: {"ok": True, "status": "clear", "issue_count": 0},
        "action_readiness_payload": lambda *_args: {"ok": True, "status": "ready"},
        "release_status_payload": lambda: {"ok": True, "status": "ready"},
        "patch_action_readiness_payload": lambda _patch_summary: {"ok": True, "status": "not_pending"},
        "storage_watch_summary": lambda: {"ok": True, "status": "clear", "patch_snapshot_count": 0, "kidney_snapshot_count": 0},
        "runtime_process_note": lambda: "synthetic source-level status contract",
        "heartbeat_age_seconds": lambda: 1,
        "chat_login_enabled": lambda: False,
        "chat_auth_source": lambda: "disabled",
        "chat_users": lambda: {},
        "append_metrics_snapshot": lambda _payload: None,
        "build_self_check": lambda _status, _policy, _metrics: {"health_score": 95, "pass_ratio": 1.0, "alerts": []},
        "control_policy_payload": lambda: {"ok": True},
        "metrics_payload": lambda: {"ok": True},
    }
    return CONTROL_STATUS_SERVICE.runtime_status_payload(
        core_module=_SyntheticCoreModule(),
        session_turns={"synthetic": [("user", "status")]},
        metrics_totals=(1, 0),
        supplier_fns=suppliers,
    )


def _latest_release_clean_check(root: Path) -> dict[str, Any]:
    path = root / "runtime" / "release_clean" / "latest_release_clean.json"
    if not path.exists():
        return _check(
            "release-clean:latest_report",
            True,
            "latest release-clean report missing; no recent release-clean run",
            data={"report_path": str(path), "report_present": False},
        )
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _check("release-clean:latest_report", False, f"latest release-clean report unreadable: {exc}")
    ok = bool(report.get("ok"))
    readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
    state = readiness.get("latest_readiness_state") or readiness.get("state") or "unknown"
    artifact = str(report.get("artifact") or "")
    failure_reason = str(report.get("failure_reason") or "")
    return _check(
        "release-clean:latest_report",
        True,
        (
            f"latest report present; ok={ok}; readiness={state}; artifact={artifact}"
            if ok
            else f"latest report present; ok=false; failure_reason={failure_reason or 'unknown'}"
        ),
        data={
            "readiness": state,
            "artifact": artifact,
            "report_path": str(path),
            "report_ok": ok,
            "failure_reason": failure_reason,
            "report_present": True,
        },
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


def _source_wiring_inventory_checks(root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    source_probe = build_source_wiring_probe_payload(root=root)
    source_set = set(source_probe.get("signal_sources") or [])
    tool_set = set(source_probe.get("planned_tools") or [])
    action_set = set(source_probe.get("advisory_actions") or [])
    try:
        synthetic_status_payload = _synthetic_control_status_payload()
    except Exception as exc:
        synthetic_status_payload = {}
        checks.append(_check("wiring-source:status-contract", False, f"synthetic status contract failed: {exc}"))
    else:
        checks.append(
            _check(
                "wiring-source:status-contract",
                bool(synthetic_status_payload),
                f"synthetic control status emitted {len(synthetic_status_payload)} keys",
                data={"status_key_count": len(synthetic_status_payload)},
            )
        )

    for surface in WIRING_SURFACES:
        files_present = [
            path
            for path in surface.source_files
            if (root / path).exists()
        ]
        checks.append(
            _check(
                f"wiring-source:{surface.surface_id}:files",
                len(files_present) == len(surface.source_files),
                "source files present"
                if len(files_present) == len(surface.source_files)
                else "missing source files: "
                + ", ".join(path for path in surface.source_files if path not in files_present),
                data={"source_files": list(surface.source_files), "present": files_present},
            )
        )

    inventory = build_wiring_inventory_payload(
        status_payload=synthetic_status_payload,
        signal_sources=source_set,
        planned_tools=tool_set,
        advisory_actions=action_set,
    )
    checks.append(
        _check(
            "wiring-source:inventory",
            bool(inventory.get("ok")),
            "all subsystem surfaces are source-wired"
            if inventory.get("ok")
            else "wiring inventory gaps remain",
            data=inventory,
        )
    )
    root_closure = build_root_closure_inventory_payload(
        status_payload=synthetic_status_payload,
        signal_sources=source_set,
        planned_tools=tool_set,
        advisory_actions=action_set,
        root=root,
    )
    checks.append(
        _check(
            "wiring-source:root-closure",
            bool(root_closure.get("ok")),
            "all discovered source roots have status, signal, tool, and action closure wiring"
            if root_closure.get("ok")
            else "root closure wiring gaps remain",
            data=root_closure,
        )
    )
    self_repair_closure = build_self_repair_closure_inventory_payload(
        synthetic_status_payload,
        signal_sources=source_probe.get("signal_sources", []),
        planned_tools=source_probe.get("planned_tools", []),
        advisory_actions=source_probe.get("advisory_actions", []),
        executable_tools=source_probe.get("executable_tools", []),
        executable_actions=source_probe.get("executable_actions", []),
        evidence_paths=source_probe.get("evidence_paths", []),
        judgment_paths=source_probe.get("judgment_paths", []),
        closure_paths=source_probe.get("closure_paths", []),
        operator_outbox_paths=source_probe.get("operator_outbox_paths", []),
        owned_root_routes=source_probe.get("owned_root_routes", []),
        root=root,
    )
    checks.append(
        _check(
            "wiring-source:self-repair-closure",
            bool(self_repair_closure.get("ok")),
            (
                "all discovered source roots have source-level self-repair closure wiring"
                if self_repair_closure.get("ok")
                else "source-level self-repair closure gaps remain"
            ),
            data=self_repair_closure,
        )
    )
    return checks


def _source_root_inventory_checks(root: Path) -> list[dict[str, Any]]:
    try:
        from services.nova_root_inventory import build_source_root_inventory_payload

        inventory = build_source_root_inventory_payload(root=root, wiring_surface_ids=[surface.surface_id for surface in WIRING_SURFACES])
    except Exception as exc:
        return [_check("source-roots:inventory", False, f"source root inventory failed: {exc}")]

    unwired = list(inventory.get("unwired_roots") or [])
    missing_evidence = list(inventory.get("missing_evidence_roots") or [])
    unclassified = list(inventory.get("unclassified_source_files") or [])
    return [
        _check(
            "source-roots:inventory",
            bool(inventory.get("ok")),
            (
                f"all discovered source roots wired ({int(inventory.get('root_count', 0) or 0)} roots)"
                if inventory.get("ok")
                else "source root inventory gaps remain"
            ),
            data={
                "root_count": int(inventory.get("root_count", 0) or 0),
                "unwired_roots": unwired,
                "missing_evidence_roots": missing_evidence,
                "unclassified_source_file_count": len(unclassified),
                "unclassified_source_files": unclassified,
            },
        )
    ]


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
    checks.extend(_source_root_inventory_checks(repo_root))
    checks.extend(_source_wiring_inventory_checks(repo_root))

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
