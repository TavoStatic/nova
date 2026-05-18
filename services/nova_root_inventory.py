from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SourceRoot:
    root_id: str
    label: str
    evidence_files: tuple[str, ...]


SOURCE_ROOTS: tuple[SourceRoot, ...] = (
    SourceRoot(
        "runtime_core",
        "Guard, core, HTTP UI, heartbeat, and runtime process health",
        ("nova_guard.py", "nova_core.py", "nova_http.py", "services/runtime_status.py"),
    ),
    SourceRoot(
        "runtime_control",
        "Runtime start/stop/restart control, process identity, timelines, and restart provenance",
        ("services/runtime_control.py", "services/runtime_process_state.py", "services/runtime_restart_provenance.py"),
    ),
    SourceRoot(
        "scheduler_registry",
        "Maintenance schedule registry and detached worker cycle ownership",
        ("services/schedule_registry.py", "autonomy_maintenance.py", "nova_guard.py"),
    ),
    SourceRoot(
        "model_runtime",
        "Ollama server, version/API contract, model availability, chat route, and port ownership",
        ("services/ollama_health.py", "services/port_ownership.py", "services/nova_ollama_chat.py"),
    ),
    SourceRoot(
        "frontdoor_cli",
        "Nova command front door, shell dispatch, and local CLI entrypoints",
        ("nova.cmd", "nova.ps1", "agent.py", "run.py", "run_tools.py"),
    ),
    SourceRoot(
        "http_api_control",
        "HTTP transport, API route dispatch, control room, auth, and action hooks",
        ("nova_http.py", "services/nova_http_get_routes.py", "services/nova_http_post_dispatch.py", "services/control_auth.py"),
    ),
    SourceRoot(
        "operator_control",
        "Operator macros, backend commands, local operator CLI, and control-action dispatcher",
        ("services/operator_control.py", "services/operator_outbox.py", "services/nova_control_action_dispatcher.py", "scripts/operator_cli.py"),
    ),
    SourceRoot(
        "policy_gates",
        "Policy gates that can block Nova self-observation or action",
        ("policy.json", "services/policy_manager.py", "services/policy_control.py"),
    ),
    SourceRoot(
        "session_identity_auth",
        "Chat users, control sessions, active session state, and auth identity",
        ("services/chat_identity.py", "services/session_admin.py", "http_session_store.py", "services/control_login_frontdoor.py"),
    ),
    SourceRoot(
        "memory_identity",
        "Memory health, bootstrap origin, identity persistence, and learned facts",
        ("memory.py", "services/memory_health.py", "services/memory_identity_bootstrap.py", "services/memory_bootstrap_origin.py"),
    ),
    SourceRoot(
        "identity_profile_answers",
        "Developer identity, preference answers, profile followups, and identity-specific reply paths",
        ("services/nova_developer_profile.py", "services/nova_identity_answers.py", "services/nova_identity_preferences.py"),
    ),
    SourceRoot(
        "conversation_routing",
        "Turn parsing, HTTP routing, route probes, deterministic reply sequencing, and continuity",
        ("routing/context_router.py", "routing/command_router.py", "services/nova_http_routing.py", "services/nova_reply_sequence.py"),
    ),
    SourceRoot(
        "supervisor_fulfillment",
        "Supervisor ownership, fulfillment flow, shared routing rules, and follow-up dispatch",
        ("supervisor.py", "services/supervisor_registry.py", "services/fulfillment_flow.py", "services/nova_fulfillment_routing.py"),
    ),
    SourceRoot(
        "reply_quality_contracts",
        "Reply contracts, guards, truth hierarchy, reflection health, and final-turn shaping",
        ("services/nova_reply_contracts.py", "services/nova_reply_guards.py", "services/nova_truth_hierarchy.py"),
    ),
    SourceRoot(
        "web_search",
        "Web/search provider policy, SearXNG, provider telemetry, and research tools",
        ("services/nova_web_tools.py", "services/nova_http_policy_search.py", "services/web_research_session.py"),
    ),
    SourceRoot(
        "retrieval_knowledge",
        "Local knowledge packs, retrieval followups, keyword tools, and research contracts",
        ("services/nova_knowledge_packs.py", "services/nova_retrieval_followups.py", "services/nova_keyword_tools.py"),
    ),
    SourceRoot(
        "weather_location",
        "Weather, device location, saved location, and location-aware task constraints",
        ("services/nova_location_weather.py", "active_task_constraints.py"),
    ),
    SourceRoot(
        "work_tree",
        "Work Tree truth, active branches, evidence, and autonomous step execution",
        ("work_tree.py", "work_tree_contracts.py", "services/control_work_trees.py"),
    ),
    SourceRoot(
        "tool_registry_policy",
        "Tool registry, direct tool catalog, tool policy, console, and planned action dispatch",
        (
            "tools/registry.py",
            "services/tool_registry.py",
            "services/tool_console.py",
            "services/nova_tool_policy.py",
            "services/os_capability_registry.py",
            "services/os_capability_operator_outbox.py",
            "services/os_script_controller.py",
            "tools/os_capability_tool.py",
            "tools/os_capabilities/os_capabilities.json",
            "tools/os_capabilities/verify_ollama_model.ps1",
        ),
    ),
    SourceRoot(
        "tool_evidence",
        "Tool execution events, validity checks, result ledgers, and error evidence",
        ("services/tool_execution.py", "services/evidence_validity.py", "tools/base_tool.py"),
    ),
    SourceRoot(
        "action_ledger",
        "Action ledger readback, route summaries, and final answer evidence",
        ("services/nova_action_ledger.py", "services/nova_action_ledger_helpers.py", "services/control_telemetry.py"),
    ),
    SourceRoot(
        "generated_queue",
        "Generated session queue, blocked reasons, generated packs, and echo-work pressure",
        ("services/nova_http_generated_work.py", "services/test_session_control.py", "tests/sessions/run_tools_http_parity.json"),
    ),
    SourceRoot(
        "subconscious",
        "Subconscious runner, simulation, reporting, triage signals, and review judgment",
        ("subconscious_runner.py", "subconscious_live_simulator.py", "services/subconscious_work_tree_triage.py"),
    ),
    SourceRoot(
        "patch_pipeline",
        "Patch previews, validated apply readiness, cleanup, rollback, and update-now flow",
        ("services/nova_patching.py", "services/patch_control.py", "services/nova_update_now.py"),
    ),
    SourceRoot(
        "release",
        "Release package readiness, verification, promotion judgment, and release-clean flow",
        (
            "services/release_status.py",
            "services/release_clean.py",
            "services/release_promotion_judgment.py",
            "services/release_validation.py",
            "scripts/build_release_package.ps1",
            "scripts/validate_release_package.py",
        ),
    ),
    SourceRoot(
        "installer_packaging",
        "Windows installer build, verification, ledger, and readiness flow",
        ("scripts/build_windows_installer.ps1", "scripts/verify_windows_installer.ps1", "docs/WINDOWS_INSTALLER_PLAN.md"),
    ),
    SourceRoot(
        "data_pipelines",
        "Data lane registry, schema probes, privileged workers, control actions, and pipeline tool",
        ("pipelines/registry.py", "pipelines/privileged_worker.py", "services/control_pipelines.py"),
    ),
    SourceRoot(
        "voice",
        "Voice runtime dependency loading, recording, transcription, and voice entrypoints",
        ("services/nova_voice_runtime.py", "services/voice_interaction.py", "voice.py"),
    ),
    SourceRoot(
        "tts_audio_output",
        "TTS output, Piper bridge, model assets, and spoken response delivery",
        ("tts_say.py", "tts_piper.py", "tts_say.ps1", "piper/models/en_US-lessac-medium.onnx.json"),
    ),
    SourceRoot(
        "vision",
        "Vision runtime, screen/camera policy, webcam and screenshot entrypoints",
        ("tools/vision_tool.py", "services/nova_vision_runtime.py", "look_crop.py", "camera.py"),
    ),
    SourceRoot(
        "http_continuity",
        "HTTP conversation state, grounded self-report continuity, and active Work Tree identity",
        ("conversation_manager.py", "services/nova_http_chat_runtime.py", "services/nova_grounded_self_report.py"),
    ),
    SourceRoot(
        "test_ecosystem",
        "Regression lanes, generated tests, test sessions, and source/test contract drift",
        (
            "scripts/run_regression.py",
            "scripts/run_test_session.py",
            "services/validation_artifact_truth.py",
            "services/regression_profile_inventory.py",
            "services/regression_lanes.py",
        ),
    ),
    SourceRoot(
        "diagnostics_hygiene",
        "Doctor, health checks, diagnostics, smoke checks, and repo hygiene",
        ("doctor.py", "health.py", "diag.py", "scripts/repo_hygiene_check.py"),
    ),
    SourceRoot(
        "safety_envelope",
        "Phase 2 safety envelope, review authority, generated-session quarantine, and promotion gates",
        ("nova_safety_envelope.py", "services/subconscious_review_authority.py", "docs/PHASE2_SAFETY_ENVELOPE.md"),
    ),
    SourceRoot(
        "storage_release_pressure",
        "Storage watch, runtime artifacts, archive pressure, kidney cleanup, and recovery material",
        ("services/storage_watch.py", "services/runtime_artifacts.py", "kidney.py"),
    ),
    SourceRoot(
        "metrics_ops_journal",
        "Behavior metrics, ops journal, metrics snapshots, and operator-visible telemetry",
        ("services/behavior_metrics.py", "services/ops_journal.py", "services/control_telemetry.py"),
    ),
    SourceRoot(
        "core_steward_reflection",
        "Core steward posture, core health brief, thinning, and reflective health pressure",
        ("services/core_steward.py", "services/core_health_brief.py", "services/core_thinning.py"),
    ),
    SourceRoot(
        "source_root_inventory",
        "Source-root discovery, root coverage comparison, and wiring inventory completeness",
        ("services/nova_root_inventory.py", "services/nova_wiring_inventory.py", "services/end_to_end_wiring.py"),
    ),
)


_CODE_FILE_SUFFIXES = {
    ".cmd",
    ".css",
    ".db",
    ".dll",
    ".exe",
    ".html",
    ".ini",
    ".iss",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".onnx",
    ".ps1",
    ".py",
    ".sqlite",
    ".txt",
}

_CODE_FILE_NAMES = {
    ".gitattributes",
    ".gitignore",
    "This_is_nova",
}

_SOURCE_COVERAGE_IGNORED_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "logs",
    "runtime",
}


def source_root_ids() -> tuple[str, ...]:
    return tuple(root.root_id for root in SOURCE_ROOTS)


def _repo_root(root: Path | None = None) -> Path:
    return (root or Path(__file__).resolve().parents[1]).resolve()


def _clean_set(values: Iterable[str] | None) -> set[str]:
    return {str(item or "").strip() for item in list(values or []) if str(item or "").strip()}


def _default_wiring_surface_ids() -> set[str]:
    try:
        from services.nova_wiring_inventory import wiring_surface_ids

        return set(wiring_surface_ids())
    except Exception:
        return set()


def _relative_code_files(repo_root: Path) -> list[str]:
    rows: list[str] = []
    for current_dir, dir_names, file_names in os.walk(repo_root):
        dir_names[:] = [
            name
            for name in dir_names
            if name not in _SOURCE_COVERAGE_IGNORED_DIRS
        ]
        current_path = Path(current_dir)
        try:
            relative_dir = current_path.relative_to(repo_root)
        except ValueError:
            continue
        if any(part in _SOURCE_COVERAGE_IGNORED_DIRS for part in relative_dir.parts):
            continue
        for file_name in file_names:
            path = current_path / file_name
            if path.suffix.lower() not in _CODE_FILE_SUFFIXES and path.name not in _CODE_FILE_NAMES:
                continue
            try:
                relative = path.relative_to(repo_root)
            except ValueError:
                continue
            rows.append(relative.as_posix())
    rows.sort()
    return rows


def _coverage_root_for_path(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip()
    low = normalized.lower()
    name = Path(normalized).name.lower()

    if (
        low.startswith("tests/")
        or name.startswith("test_")
        or name in {"smoke_test.py", "http_test_session_helpers.py", "http_chat_flow.py", "run_regression.py"}
        or "run_regression" in low
        or "regression_lanes" in low
        or "validation_artifact" in low
        or "smoke" in low
    ):
        return "test_ecosystem"
    if name in {"readme.md", "requirements.txt"}:
        return "frontdoor_cli"
    if name in {".gitattributes", ".gitignore", "pytest.ini"}:
        return "diagnostics_hygiene"
    if name == "this_is_nova":
        return "source_root_inventory"
    if "root_inventory" in low or "wiring_inventory" in low or "end_to_end_wiring" in low:
        return "source_root_inventory"
    if "operator" in low or name in {"operator_macros.json"}:
        return "operator_control"
    if "developer_profile" in low or "identity_answers" in low or "identity_preferences" in low:
        return "identity_profile_answers"
    if "tool_execution" in low or "evidence_validity" in low or "base_tool" in low:
        return "tool_evidence"
    if "action_ledger" in low:
        return "action_ledger"
    if "generated_work" in low or "test_session_control" in low or "run_tools_http_parity" in low:
        return "generated_queue"
    if "windows_installer" in low:
        return "installer_packaging"
    if "safety_envelope" in low or "review_authority" in low or "phase2_safety_envelope" in low:
        return "safety_envelope"
    if (
        low.endswith("work_tree.db")
        or low.endswith("ops_journal.jsonl")
        or "kidney" in low
        or "storage_watch" in low
    ):
        return "storage_release_pressure"
    if low.endswith("nova_memory.sqlite"):
        return "memory_identity"
    if low.startswith("piper/") or low.endswith(".onnx") or low.endswith(".dll") or low.endswith(".exe"):
        return "tts_audio_output"
    if "autonomy_" in low or "schedule_registry" in low:
        return "scheduler_registry"
    if low.startswith("pipelines/") or low.startswith("data_sources/") or "pipeline" in low:
        return "data_pipelines"
    if (
        low.startswith("routing/")
        or "routing" in low
        or "route_" in low
        or "planner" in low
        or "turn_" in low
        or "query_classifiers" in low
        or name in {
            "action_planner.py",
            "active_task_constraints.py",
            "dynamic_replanner.py",
            "followup_move_classifier.py",
            "intent_interpreter.py",
            "planner_decision.py",
            "task_engine.py",
        }
    ):
        return "conversation_routing"
    if low.startswith("knowledge/") or "knowledge" in low or "retrieval" in low or "keyword" in low:
        return "retrieval_knowledge"
    if low.startswith("static/") or low.startswith("templates/") or "http_" in low or "http" in name or "leah" in low or "control_assets" in low:
        return "http_api_control"
    if "conversation_manager" in low or "grounded_self_report" in low or "conversation_followups" in low or "session_followups" in low:
        return "http_continuity"
    if "voice" in low or name == "tts_say.py":
        return "voice"
    if "tts" in low or low.startswith("piper/"):
        return "tts_audio_output"
    if "vision" in low or name in {"camera.py", "look.py", "look_crop.py"}:
        return "vision"
    if "memory" in low or low.startswith("memory/"):
        return "memory_identity"
    if "release" in low or "package" in low or "installer" in low or low.startswith("installer/"):
        return "release"
    if "patch" in low or "update_now" in low:
        return "patch_pipeline"
    if "subconscious" in low or "phase2" in low:
        return "subconscious"
    if "supervisor" in low or "fulfillment" in low:
        return "supervisor_fulfillment"
    if (
        "reply" in low
        or "truth" in low
        or "fallback" in low
        or "prompt" in low
        or "correction" in low
        or "teaching" in low
        or name in {"choice_presenter.py", "fit_evaluator.py"}
    ):
        return "reply_quality_contracts"
    if "ollama" in low or "port_ownership" in low:
        return "model_runtime"
    if "web" in low or "search" in low or "research" in low or "provider" in low:
        return "web_search"
    if "weather" in low or "location" in low:
        return "weather_location"
    if "tool" in low or low.startswith("tools/") or "capability" in low or "capabilities" in low or "os_script" in low:
        return "tool_registry_policy"
    if "ledger" in low or "telemetry" in low or "metrics" in low or "journal" in low:
        return "metrics_ops_journal"
    if "core" in low or "reflection" in low or "pulse" in low or "self_status" in low or "service_builders" in low:
        return "core_steward_reflection"
    if "work_tree" in low:
        return "work_tree"
    if "runtime" in low or "guard" in low or "stop" in low or "heartbeat" in low:
        return "runtime_core"
    if "auth" in low or "session" in low or "identity" in low or "profile" in low:
        return "session_identity_auth"
    if "policy" in low:
        return "policy_gates"
    if "operator" in low or "command" in low or "cli" in low or name in {"agent.py", "nova.cmd", "nova.ps1", "run.py", "run_tools.py"}:
        return "frontdoor_cli"
    if (
        name in {"diag.py", "diag_ollama_check.py", "doctor.py", "env_inspector.py", "health.py", "inspect_core_fail.py"}
        or low.startswith("docs/")
        or "health_check" in low
        or "hygiene" in low
        or "prepush" in low
    ):
        return "diagnostics_hygiene"
    if "control_" in low:
        return "runtime_control"
    return ""


def build_source_root_inventory_payload(
    root: Path | None = None,
    *,
    wiring_surface_ids: Iterable[str] | None = None,
) -> dict[str, object]:
    repo_root = _repo_root(root)
    surface_ids = _clean_set(wiring_surface_ids)
    if not surface_ids:
        surface_ids = _default_wiring_surface_ids()

    rows: list[dict[str, object]] = []
    unwired_roots: list[str] = []
    missing_evidence_roots: list[str] = []
    known_root_ids = {root.root_id for root in SOURCE_ROOTS}
    code_files = _relative_code_files(repo_root)
    source_files_by_root: dict[str, list[str]] = {root_id: [] for root_id in known_root_ids}
    unclassified_source_files: list[str] = []
    for path in code_files:
        root_id = _coverage_root_for_path(path)
        if root_id in known_root_ids:
            source_files_by_root[root_id].append(path)
        else:
            unclassified_source_files.append(path)

    for source_root in SOURCE_ROOTS:
        present = [
            path
            for path in source_root.evidence_files
            if (repo_root / path).exists()
        ]
        missing = [
            path
            for path in source_root.evidence_files
            if not (repo_root / path).exists()
        ]
        discovered = bool(present)
        wired = source_root.root_id in surface_ids
        if discovered and not wired:
            unwired_roots.append(source_root.root_id)
        if not discovered:
            missing_evidence_roots.append(source_root.root_id)
        rows.append(
            {
                "root_id": source_root.root_id,
                "label": source_root.label,
                "discovered": discovered,
                "wired": wired,
                "evidence_files": list(source_root.evidence_files),
                "present_evidence_files": present,
                "missing_evidence_files": missing,
                "covered_source_files": source_files_by_root.get(source_root.root_id, []),
                "covered_source_file_count": len(source_files_by_root.get(source_root.root_id, [])),
            }
        )

    gap_count = len(unwired_roots) + len(missing_evidence_roots) + len(unclassified_source_files)
    return {
        "ok": gap_count == 0,
        "root_count": len(rows),
        "discovered_root_count": sum(1 for row in rows if bool(row.get("discovered"))),
        "wired_root_count": sum(1 for row in rows if bool(row.get("wired"))),
        "source_file_count": len(code_files),
        "classified_source_file_count": len(code_files) - len(unclassified_source_files),
        "unclassified_source_file_count": len(unclassified_source_files),
        "unclassified_source_files": unclassified_source_files,
        "gap_count": gap_count,
        "unwired_roots": unwired_roots,
        "missing_evidence_roots": missing_evidence_roots,
        "roots": rows,
    }
