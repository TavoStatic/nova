from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class WiringSurface:
    surface_id: str
    label: str
    status_keys: tuple[str, ...]
    signal_sources: tuple[str, ...]
    planned_tools: tuple[str, ...]
    advisory_actions: tuple[str, ...]
    source_files: tuple[str, ...]


WIRING_SURFACES: tuple[WiringSurface, ...] = (
    WiringSurface(
        "runtime_core",
        "Runtime guard, core, HTTP UI, heartbeat, and process health",
        ("guard", "core", "webui", "runtime_summary", "runtime_failures"),
        ("control_status", "runtime_failures", "runtime_restart_analytics"),
        ("pulse", "system_check", "read", "find"),
        ("guard_start", "autonomy_maintenance_start", "active_work_tree_run_next"),
        ("services/control_status.py", "services/work_tree_signal_ingestion.py", "services/runtime_status.py"),
    ),
    WiringSurface(
        "model_runtime",
        "Ollama server, version/API contract, model availability, chat route, and port ownership",
        ("ollama_health", "ollama_api_up", "ollama_version", "ollama_api_contract_status", "ollama_chat_route_ok", "port_ownership"),
        ("control_status",),
        ("system_check", "read", "find"),
        ("active_work_tree_run_next",),
        ("services/ollama_health.py", "services/work_tree_signal_ingestion.py", "services/port_ownership.py"),
    ),
    WiringSurface(
        "web_search",
        "Web/search provider policy, SearXNG, provider telemetry, and research tools",
        ("web_enabled", "search_provider", "searxng_ok", "provider_telemetry"),
        ("control_status",),
        ("web_search", "web_research", "web_gather", "system_check"),
        ("active_work_tree_run_next",),
        ("services/nova_web_tools.py", "services/nova_http_policy_search.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "policy_gates",
        "Policy gates that can block Nova self-observation",
        ("web_enabled", "memory_enabled", "patch_enabled", "vision_status", "voice_status"),
        ("patch_status", "memory_health", "voice_status", "vision_status"),
        ("read", "find", "system_check"),
        ("active_work_tree_run_next",),
        ("services/policy_manager.py", "services/policy_control.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "memory_identity",
        "Memory health, bootstrap origin, identity persistence, and learned facts",
        ("memory_health", "memory_health_status", "memory_enabled", "memory_stats_ok"),
        ("memory_health",),
        ("memory_bootstrap_judgment", "memory_identity_bootstrap", "read", "find"),
        ("active_work_tree_run_next",),
        ("services/memory_health.py", "services/memory_bootstrap_judgment.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "work_tree",
        "Work Tree truth, active branches, evidence, and autonomous step execution",
        ("work_tree_truth", "work_tree_tree_count", "work_tree_open_task_count"),
        ("wiring_inventory",),
        ("read", "find", "pulse", "queue_status"),
        ("active_work_tree_run_next",),
        ("work_tree.py", "services/control_work_trees.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "tool_evidence",
        "Tool event ledger and evidence validity",
        ("tool_events_total", "last_tool_status", "last_tool_error_summary"),
        ("tool_events",),
        ("read", "find", "queue_status"),
        ("active_work_tree_run_next",),
        ("services/tool_execution.py", "services/evidence_validity.py", "work_tree.py"),
    ),
    WiringSurface(
        "action_ledger",
        "Action ledger readback, route summaries, and final answer evidence",
        ("action_ledger_ok", "action_ledger_total", "last_route_summary", "last_action_final_answer"),
        ("action_ledger",),
        ("read", "find", "pulse"),
        ("active_work_tree_run_next",),
        ("services/nova_action_ledger.py", "services/control_telemetry.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "generated_queue",
        "Generated session queue, blocked reasons, and echo-work pressure",
        ("generated_work_queue", "generated_queue_status", "queue_open_count", "queue_blocked_count"),
        ("generated_work_queue",),
        ("queue_status", "generated_queue_run", "read", "find"),
        ("generated_queue_run_next", "generated_queue_investigate"),
        ("services/nova_http_generated_work.py", "autonomy_maintenance.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "subconscious",
        "Subconscious reports, triage signals, and review judgment",
        ("subconscious_summary", "subconscious_ok", "subconscious_latest_report_path"),
        ("subconscious_status", "subconscious"),
        ("subconscious_review_judgment", "read", "find"),
        ("active_work_tree_run_next",),
        ("subconscious_live_simulator.py", "services/subconscious_work_tree_triage.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "patch_pipeline",
        "Patch previews, validated apply readiness, cleanup, and rollback",
        ("patch_status_ok", "patch_enabled", "patch_pipeline_ready", "patch_cleanup_status"),
        ("patch_status",),
        ("patch_preview_approve", "patch_preview_apply", "patch_apply", "patch_rollback", "read"),
        ("patch_queue_run_next", "update_now_dry_run"),
        ("services/nova_patching.py", "services/patch_control.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "release",
        "Release package readiness, validation evidence, promotion judgment, and rebuild",
        ("release_status",),
        ("release_status",),
        (
            "release_validation_run",
            "release_promotion_judgment",
            "release_record_validation_outcome",
            "release_rebuild_verify",
            "read",
            "find",
        ),
        ("active_work_tree_run_next",),
        (
            "services/release_status.py",
            "services/release_clean.py",
            "services/release_promotion_judgment.py",
            "services/release_validation.py",
            "scripts/validate_release_package.py",
            "services/work_tree_signal_ingestion.py",
        ),
    ),
    WiringSurface(
        "data_pipelines",
        "Data lane registry, schema probes, control actions, and pipeline tool",
        ("data_pipelines", "data_pipeline_count", "data_pipeline_registry_ok"),
        ("data_pipelines",),
        ("pipeline", "read", "find"),
        ("active_work_tree_run_next",),
        ("pipelines/registry.py", "services/control_pipelines.py", "services/data_pipeline_registry.py"),
    ),
    WiringSurface(
        "voice",
        "Voice runtime dependency loading and entrypoint wrappers",
        ("voice_status", "voice_runtime_status", "voice_runtime_requested"),
        ("voice_status",),
        ("read", "find", "system_check"),
        ("active_work_tree_run_next",),
        ("services/nova_voice_runtime.py", "services/voice_interaction.py", "nova_core.py"),
    ),
    WiringSurface(
        "vision",
        "Vision runtime, screen/camera policy, and model availability",
        ("vision_status", "vision_runtime_status", "vision_runtime_requested"),
        ("vision_status",),
        ("screen", "camera", "read", "find", "system_check"),
        ("active_work_tree_run_next",),
        ("tools/vision_tool.py", "services/nova_vision_runtime.py", "look_crop.py"),
    ),
    WiringSurface(
        "http_continuity",
        "HTTP conversation state, grounded self-report continuity, and active Work Tree identity",
        ("active_http_sessions", "last_route_summary", "last_action_final_answer"),
        ("http_conversation",),
        ("read", "find", "pulse"),
        ("active_work_tree_run_next",),
        ("conversation_manager.py", "services/nova_http_chat_runtime.py", "services/nova_reply_sequence.py"),
    ),
    WiringSurface(
        "test_ecosystem",
        "Regression status, validation artifacts, generated tests, and source/test contract drift",
        (
            "last_regression_status",
            "last_regression_stale",
            "validation_artifact_truth",
            "validation_artifact_truth_ok",
            "test_profile_inventory",
            "test_profile_inventory_ok",
            "test_profile_profile_drift_count",
        ),
        ("regression", "validation_artifact_truth", "test_profile_inventory"),
        ("read", "find", "queue_status"),
        ("active_work_tree_run_next",),
        (
            "run_regression.py",
            "services/test_session_control.py",
            "services/validation_artifact_truth.py",
            "services/regression_profile_inventory.py",
            "services/regression_lanes.py",
        ),
    ),
    WiringSurface(
        "storage_release_pressure",
        "Storage watch, archive growth, runtime artifacts, and release-clean pressure",
        (
            "storage_watch_status",
            "runtime_artifacts",
            "patch_snapshot_count",
            "kidney_snapshot_count",
            "release_validation_extract_bytes",
            "release_stage_bytes",
            "release_zip_bytes",
        ),
        ("storage_watch",),
        ("read", "find", "system_check"),
        ("active_work_tree_run_next",),
        ("services/storage_watch.py", "kidney.py", "services/release_clean.py"),
    ),
    WiringSurface(
        "runtime_control",
        "Runtime start/stop/restart control, process identity, timelines, and restart provenance",
        ("action_readiness", "runtime_timeline", "runtime_restart_analytics", "runtime_failures"),
        ("control_status", "runtime_failures", "runtime_restart_analytics"),
        ("system_check", "read", "find"),
        ("active_work_tree_run_next",),
        ("services/runtime_control.py", "services/runtime_process_state.py", "services/runtime_restart_provenance.py"),
    ),
    WiringSurface(
        "scheduler_registry",
        "Maintenance schedule registry and detached worker cycle ownership",
        ("maintenance_scheduler_status", "runtime_worker_status", "autonomy_maintenance"),
        ("control_status",),
        ("queue_status", "read", "find"),
        ("autonomy_maintenance_start", "active_work_tree_run_next"),
        ("services/schedule_registry.py", "autonomy_maintenance.py", "nova_guard.py"),
    ),
    WiringSurface(
        "frontdoor_cli",
        "Nova command front door, shell dispatch, and local CLI entrypoints",
        ("backend_commands", "backend_command_count", "source_root_inventory"),
        ("source_root_inventory",),
        ("read", "find", "system_check"),
        ("active_work_tree_run_next",),
        ("nova.cmd", "nova.ps1", "agent.py", "run.py"),
    ),
    WiringSurface(
        "http_api_control",
        "HTTP transport, API route dispatch, control room, auth, and action hooks",
        ("requests_total", "errors_total", "chat_login_enabled", "source_root_inventory"),
        ("control_status", "http_conversation"),
        ("read", "find", "pulse"),
        ("active_work_tree_run_next",),
        ("nova_http.py", "services/nova_http_get_routes.py", "services/nova_http_post_dispatch.py"),
    ),
    WiringSurface(
        "operator_control",
        "Operator macros, backend commands, local operator CLI, and control-action dispatcher",
        ("operator_macros", "backend_commands", "source_root_inventory"),
        ("source_root_inventory",),
        ("read", "find", "pulse"),
        ("active_work_tree_run_next",),
        ("services/operator_control.py", "services/nova_control_action_dispatcher.py", "scripts/operator_cli.py"),
    ),
    WiringSurface(
        "session_identity_auth",
        "Chat users, control sessions, active session state, and auth identity",
        ("chat_auth_source", "chat_users_count", "chat_login_enabled", "source_root_inventory"),
        ("http_conversation", "source_root_inventory"),
        ("read", "find", "pulse"),
        ("active_work_tree_run_next",),
        ("services/chat_identity.py", "services/session_admin.py", "http_session_store.py"),
    ),
    WiringSurface(
        "identity_profile_answers",
        "Developer identity, preference answers, profile followups, and identity-specific reply paths",
        ("memory_health", "last_route_summary", "source_root_inventory"),
        ("memory_health", "http_conversation", "source_root_inventory"),
        ("read", "find", "pulse"),
        ("active_work_tree_run_next",),
        ("services/nova_developer_profile.py", "services/nova_identity_answers.py", "services/nova_identity_preferences.py"),
    ),
    WiringSurface(
        "conversation_routing",
        "Turn parsing, HTTP routing, route probes, deterministic reply sequencing, and continuity",
        ("last_intent", "last_planner_decision", "last_route_summary", "source_root_inventory"),
        ("http_conversation", "action_ledger", "source_root_inventory"),
        ("read", "find", "pulse"),
        ("active_work_tree_run_next",),
        ("routing/context_router.py", "routing/command_router.py", "services/nova_http_routing.py"),
    ),
    WiringSurface(
        "supervisor_fulfillment",
        "Supervisor ownership, fulfillment flow, shared routing rules, and follow-up dispatch",
        ("last_route_summary", "last_route_trace", "source_root_inventory"),
        ("source_root_inventory", "http_conversation"),
        ("read", "find", "pulse"),
        ("active_work_tree_run_next",),
        ("supervisor.py", "services/supervisor_registry.py", "services/fulfillment_flow.py"),
    ),
    WiringSurface(
        "reply_quality_contracts",
        "Reply contracts, guards, truth hierarchy, reflection health, and final-turn shaping",
        ("last_action_final_answer", "last_route_grounded", "last_route_trace", "source_root_inventory"),
        ("action_ledger", "http_conversation", "source_root_inventory"),
        ("read", "find", "pulse"),
        ("active_work_tree_run_next",),
        ("services/nova_reply_contracts.py", "services/nova_reply_guards.py", "services/nova_truth_hierarchy.py"),
    ),
    WiringSurface(
        "retrieval_knowledge",
        "Local knowledge packs, retrieval followups, keyword tools, and research contracts",
        ("web_enabled", "last_provider_hit", "source_root_inventory"),
        ("control_status", "source_root_inventory"),
        ("web_search", "web_research", "read", "find"),
        ("active_work_tree_run_next",),
        ("services/nova_knowledge_packs.py", "services/nova_retrieval_followups.py", "services/nova_keyword_tools.py"),
    ),
    WiringSurface(
        "weather_location",
        "Weather, device location, saved location, and location-aware task constraints",
        ("web_enabled", "last_route_summary", "source_root_inventory"),
        ("control_status", "source_root_inventory"),
        ("weather_current_location", "weather_location", "location_coords", "read", "find"),
        ("active_work_tree_run_next",),
        ("services/nova_location_weather.py", "active_task_constraints.py"),
    ),
    WiringSurface(
        "tool_registry_policy",
        "Tool registry, direct tool catalog, tool policy, console, and planned action dispatch",
        ("tool_events_total", "backend_command_count", "source_root_inventory"),
        ("tool_events", "source_root_inventory"),
        ("read", "find", "queue_status"),
        ("active_work_tree_run_next",),
        ("tools/registry.py", "services/tool_registry.py", "services/nova_tool_policy.py"),
    ),
    WiringSurface(
        "installer_packaging",
        "Windows installer build, verification, ledger, and readiness flow",
        ("release_status", "source_root_inventory"),
        ("release_status", "source_root_inventory"),
        ("read", "find", "system_check"),
        ("active_work_tree_run_next",),
        ("scripts/build_windows_installer.ps1", "scripts/verify_windows_installer.ps1", "docs/WINDOWS_INSTALLER_PLAN.md"),
    ),
    WiringSurface(
        "tts_audio_output",
        "TTS output, Piper bridge, model assets, and spoken response delivery",
        ("voice_status", "voice_runtime_status", "source_root_inventory"),
        ("voice_status", "source_root_inventory"),
        ("read", "find", "system_check"),
        ("active_work_tree_run_next",),
        ("tts_say.py", "tts_piper.py", "tts_say.ps1"),
    ),
    WiringSurface(
        "diagnostics_hygiene",
        "Doctor, health checks, diagnostics, smoke checks, and repo hygiene",
        ("health_score", "self_check_pass_ratio", "source_root_inventory"),
        ("source_root_inventory", "control_status"),
        ("health", "system_check", "read", "find"),
        ("active_work_tree_run_next",),
        ("doctor.py", "health.py", "scripts/repo_hygiene_check.py"),
    ),
    WiringSurface(
        "safety_envelope",
        "Phase 2 safety envelope, review authority, generated-session quarantine, and promotion gates",
        ("subconscious_summary", "generated_work_queue", "source_root_inventory"),
        ("subconscious_status", "source_root_inventory"),
        ("phase2_audit", "read", "find"),
        ("active_work_tree_run_next",),
        ("nova_safety_envelope.py", "services/subconscious_review_authority.py", "docs/PHASE2_SAFETY_ENVELOPE.md"),
    ),
    WiringSurface(
        "metrics_ops_journal",
        "Behavior metrics, ops journal, metrics snapshots, and operator-visible telemetry",
        ("requests_total", "errors_total", "tool_events_total", "source_root_inventory"),
        ("action_ledger", "control_status", "source_root_inventory"),
        ("read", "find", "pulse"),
        ("active_work_tree_run_next",),
        ("services/behavior_metrics.py", "services/ops_journal.py", "services/control_telemetry.py"),
    ),
    WiringSurface(
        "core_steward_reflection",
        "Core steward posture, core health brief, thinning, and reflective health pressure",
        ("pulse", "health_score", "source_root_inventory"),
        ("control_status", "source_root_inventory"),
        ("core_health", "core_thinning", "pulse", "read", "find"),
        ("active_work_tree_run_next",),
        ("services/core_steward.py", "services/core_health_brief.py", "services/core_thinning.py"),
    ),
    WiringSurface(
        "source_root_inventory",
        "Source-root discovery, root coverage comparison, wiring inventory, and root closure completeness",
        (
            "source_root_inventory",
            "source_root_inventory_ok",
            "source_root_inventory_gap_count",
            "source_root_inventory_source_file_count",
            "source_root_inventory_unclassified_source_file_count",
            "source_root_inventory_unclassified_source_files",
            "root_closure_inventory",
            "root_closure_inventory_ok",
            "root_closure_inventory_gap_count",
        ),
        ("source_root_inventory", "root_closure_inventory"),
        ("read", "find", "pulse"),
        ("active_work_tree_run_next",),
        ("services/nova_root_inventory.py", "services/nova_wiring_inventory.py", "services/end_to_end_wiring.py"),
    ),
)


DEFAULT_SIGNAL_SOURCES = frozenset(
    source
    for surface in WIRING_SURFACES
    for source in surface.signal_sources
)

DEFAULT_PLANNED_TOOLS = frozenset(
    tool
    for surface in WIRING_SURFACES
    for tool in surface.planned_tools
)

DEFAULT_ADVISORY_ACTIONS = frozenset(
    action
    for surface in WIRING_SURFACES
    for action in surface.advisory_actions
)


def _clean_set(values: Iterable[str] | None) -> set[str]:
    return {str(item or "").strip() for item in list(values or []) if str(item or "").strip()}


def build_wiring_inventory_payload(
    status_payload: dict[str, Any] | None = None,
    *,
    signal_sources: Iterable[str] | None = None,
    planned_tools: Iterable[str] | None = None,
    advisory_actions: Iterable[str] | None = None,
) -> dict[str, Any]:
    status = status_payload if isinstance(status_payload, dict) else {}
    available_sources = _clean_set(signal_sources) or set(DEFAULT_SIGNAL_SOURCES)
    available_tools = _clean_set(planned_tools) or set(DEFAULT_PLANNED_TOOLS)
    available_actions = _clean_set(advisory_actions) or set(DEFAULT_ADVISORY_ACTIONS)

    surfaces: list[dict[str, Any]] = []
    missing_status: list[str] = []
    missing_signals: list[str] = []
    missing_tools: list[str] = []
    missing_actions: list[str] = []

    for surface in WIRING_SURFACES:
        present_status = [key for key in surface.status_keys if key in status]
        missing_status_keys = [key for key in surface.status_keys if key not in status]
        present_signals = [source for source in surface.signal_sources if source in available_sources]
        missing_signal_sources = [source for source in surface.signal_sources if source not in available_sources]
        present_tools = [tool for tool in surface.planned_tools if tool in available_tools]
        missing_planned_tools = [tool for tool in surface.planned_tools if tool not in available_tools]
        present_actions = [action for action in surface.advisory_actions if action in available_actions]
        missing_advisory_actions = [action for action in surface.advisory_actions if action not in available_actions]

        status_visible = not surface.status_keys or not missing_status_keys
        signal_wired = not surface.signal_sources or not missing_signal_sources
        tool_wired = not surface.planned_tools or not missing_planned_tools
        action_wired = not surface.advisory_actions or not missing_advisory_actions
        if not status_visible:
            missing_status.append(surface.surface_id)
        if not signal_wired:
            missing_signals.append(surface.surface_id)
        if not tool_wired:
            missing_tools.append(surface.surface_id)
        if not action_wired:
            missing_actions.append(surface.surface_id)
        surfaces.append({
            "surface_id": surface.surface_id,
            "label": surface.label,
            "status_visible": status_visible,
            "signal_wired": signal_wired,
            "tool_wired": tool_wired,
            "action_wired": action_wired,
            "status_keys": list(surface.status_keys),
            "present_status_keys": present_status,
            "missing_status_keys": missing_status_keys,
            "signal_sources": list(surface.signal_sources),
            "present_signal_sources": present_signals,
            "missing_signal_sources": missing_signal_sources,
            "planned_tools": list(surface.planned_tools),
            "present_planned_tools": present_tools,
            "missing_planned_tools": missing_planned_tools,
            "advisory_actions": list(surface.advisory_actions),
            "present_advisory_actions": present_actions,
            "missing_advisory_actions": missing_advisory_actions,
            "source_files": list(surface.source_files),
        })

    gap_count = len(missing_status) + len(missing_signals) + len(missing_tools) + len(missing_actions)
    return {
        "ok": gap_count == 0,
        "surface_count": len(surfaces),
        "surfaces": surfaces,
        "missing_status_surfaces": missing_status,
        "missing_signal_surfaces": missing_signals,
        "missing_tool_surfaces": missing_tools,
        "missing_action_surfaces": missing_actions,
        "gap_count": gap_count,
    }


def build_root_closure_inventory_payload(
    status_payload: dict[str, Any] | None = None,
    *,
    root: str | Path | None = None,
    signal_sources: Iterable[str] | None = None,
    planned_tools: Iterable[str] | None = None,
    advisory_actions: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Describe whether every declared root has a complete code wiring route.

    This inventory is intentionally stricter than source presence.  A root is
    not closure-wired just because it exists on disk; it needs a status surface,
    a signal source, a planned tool path, and an advisory action path.
    """
    from services.nova_root_inventory import SOURCE_ROOTS

    status = status_payload if isinstance(status_payload, dict) else {}
    repo_root = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    available_sources = _clean_set(signal_sources) or set(DEFAULT_SIGNAL_SOURCES)
    available_tools = _clean_set(planned_tools) or set(DEFAULT_PLANNED_TOOLS)
    available_actions = _clean_set(advisory_actions) or set(DEFAULT_ADVISORY_ACTIONS)
    surface_by_id = {surface.surface_id: surface for surface in WIRING_SURFACES}

    roots: list[dict[str, Any]] = []
    gap_roots: list[str] = []
    missing_surface_roots: list[str] = []
    missing_status_roots: list[str] = []
    missing_signal_roots: list[str] = []
    missing_tool_roots: list[str] = []
    missing_action_roots: list[str] = []
    missing_source_roots: list[str] = []

    for source_root in SOURCE_ROOTS:
        surface = surface_by_id.get(source_root.root_id)
        source_files_present = [
            path
            for path in source_root.evidence_files
            if (repo_root / path).exists()
        ]
        missing_source_files = [
            path
            for path in source_root.evidence_files
            if not (repo_root / path).exists()
        ]

        status_keys = list(surface.status_keys) if surface is not None else []
        signal_source_names = list(surface.signal_sources) if surface is not None else []
        planned_tool_names = list(surface.planned_tools) if surface is not None else []
        advisory_action_names = list(surface.advisory_actions) if surface is not None else []

        present_status_keys = [key for key in status_keys if key in status]
        missing_status_keys = [key for key in status_keys if key not in status]
        present_signal_sources = [source for source in signal_source_names if source in available_sources]
        missing_signal_sources = [source for source in signal_source_names if source not in available_sources]
        present_planned_tools = [tool for tool in planned_tool_names if tool in available_tools]
        missing_planned_tools = [tool for tool in planned_tool_names if tool not in available_tools]
        present_advisory_actions = [action for action in advisory_action_names if action in available_actions]
        missing_advisory_actions = [action for action in advisory_action_names if action not in available_actions]

        gaps: list[str] = []
        if surface is None:
            gaps.append("missing_wiring_surface")
            missing_surface_roots.append(source_root.root_id)
        if missing_source_files:
            gaps.append("missing_source_evidence")
            missing_source_roots.append(source_root.root_id)
        if surface is not None and status_keys and missing_status_keys:
            gaps.append("missing_status_surface_keys")
            missing_status_roots.append(source_root.root_id)
        if surface is not None and signal_source_names and missing_signal_sources:
            gaps.append("missing_signal_sources")
            missing_signal_roots.append(source_root.root_id)
        if surface is not None and planned_tool_names and missing_planned_tools:
            gaps.append("missing_planned_tools")
            missing_tool_roots.append(source_root.root_id)
        if surface is not None and advisory_action_names and missing_advisory_actions:
            gaps.append("missing_advisory_actions")
            missing_action_roots.append(source_root.root_id)

        if gaps:
            gap_roots.append(source_root.root_id)

        roots.append(
            {
                "root_id": source_root.root_id,
                "label": source_root.label,
                "ok": not gaps,
                "gaps": gaps,
                "source_files": list(source_root.evidence_files),
                "present_source_files": source_files_present,
                "missing_source_files": missing_source_files,
                "wiring_surface_present": surface is not None,
                "status_keys": status_keys,
                "present_status_keys": present_status_keys,
                "missing_status_keys": missing_status_keys,
                "signal_sources": signal_source_names,
                "present_signal_sources": present_signal_sources,
                "missing_signal_sources": missing_signal_sources,
                "planned_tools": planned_tool_names,
                "present_planned_tools": present_planned_tools,
                "missing_planned_tools": missing_planned_tools,
                "advisory_actions": advisory_action_names,
                "present_advisory_actions": present_advisory_actions,
                "missing_advisory_actions": missing_advisory_actions,
            }
        )

    return {
        "ok": not gap_roots,
        "root_count": len(roots),
        "gap_count": len(gap_roots),
        "gap_roots": gap_roots,
        "missing_surface_roots": missing_surface_roots,
        "missing_source_roots": missing_source_roots,
        "missing_status_roots": missing_status_roots,
        "missing_signal_roots": missing_signal_roots,
        "missing_tool_roots": missing_tool_roots,
        "missing_action_roots": missing_action_roots,
        "roots": roots,
    }


def wiring_surface_ids() -> tuple[str, ...]:
    return tuple(surface.surface_id for surface in WIRING_SURFACES)
