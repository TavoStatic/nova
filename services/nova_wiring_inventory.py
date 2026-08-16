from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from services.nova_inventory_labels import shared_inventory_label
from services.tool_identity import (
    FIND,
    INSTALLER_VALIDATION_RUN,
    LS,
    MEMORY_BOOTSTRAP_JUDGMENT,
    PHASE2_AUDIT,
    OPERATOR_RESPONSE,
    PULSE,
    READ,
    RELEASE_PROMOTION_JUDGMENT,
    RELEASE_REBUILD_VERIFY,
    RELEASE_RECORD_VALIDATION_OUTCOME,
    RELEASE_VALIDATION_RUN,
    SOURCE_ROOT_JUDGMENT,
    SUBCONSCIOUS_REVIEW_JUDGMENT,
)


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
        ("runtime_core",),
        (PULSE, "system_check", READ, FIND),
        ("guard_start", "autonomy_maintenance_start", "active_work_tree_run_next"),
        ("services/control_status.py", "services/work_tree_signal_ingestion.py", "services/runtime_status.py"),
    ),
    WiringSurface(
        "model_runtime",
        shared_inventory_label("model_runtime"),
        ("ollama_health", "ollama_api_up", "ollama_version", "ollama_api_contract_status", "ollama_chat_route_ok", "port_ownership"),
        ("model_runtime",),
        ("os_capability", "system_check", READ, FIND),
        ("active_work_tree_run_next",),
        (
            "services/ollama_health.py",
            "services/work_tree_signal_ingestion.py",
            "services/port_ownership.py",
            "tools/os_capabilities/verify_ollama_model.ps1",
            "tools/os_capabilities/inspect_ports.ps1",
        ),
    ),
    WiringSurface(
        "web_search",
        shared_inventory_label("web_search"),
        ("web_enabled", "search_provider", "searxng_ok", "provider_telemetry"),
        ("web_search",),
        ("web_search", "web_research", "web_gather", "system_check"),
        ("active_work_tree_run_next",),
        ("services/nova_web_tools.py", "services/nova_http_policy_search.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "policy_gates",
        "Policy gates that can block Nova self-observation",
        ("web_enabled", "memory_enabled", "patch_enabled", "vision_status", "voice_status"),
        ("policy_gates",),
        (READ, FIND, "system_check"),
        ("active_work_tree_run_next",),
        ("services/policy_manager.py", "services/policy_control.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "memory_identity",
        shared_inventory_label("memory_identity"),
        ("memory_health", "memory_health_status", "memory_enabled", "memory_stats_ok"),
        ("memory_identity",),
        ("memory_bootstrap_judgment", "memory_identity_bootstrap", "read", "find"),
        ("active_work_tree_run_next",),
        ("services/memory_health.py", "services/memory_bootstrap_judgment.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "identity_profile_answers",
        shared_inventory_label("identity_profile_answers"),
        ("memory_health", "memory_health_status", "memory_enabled", "source_root_inventory"),
        ("identity_profile_answers",),
        ("memory_bootstrap_judgment", "memory_identity_bootstrap", "read", "find"),
        ("active_work_tree_run_next",),
        ("services/memory_routing.py", "services/nova_memory_learning.py", "services/memory_identity_bootstrap.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "work_tree",
        shared_inventory_label("work_tree"),
        ("work_tree_truth", "work_tree_tree_count", "work_tree_open_task_count"),
        ("work_tree",),
        (READ, FIND, PULSE, "queue_status"),
        ("active_work_tree_run_next",),
        ("work_tree.py", "services/control_work_trees.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "tool_evidence",
        "Tool event ledger and evidence validity",
        ("tool_events_total", "last_tool_status", "last_tool_error_summary"),
        ("tool_evidence",),
        (READ, FIND, "queue_status"),
        ("active_work_tree_run_next",),
        ("services/tool_execution.py", "services/evidence_validity.py", "work_tree.py"),
    ),
    WiringSurface(
        "action_ledger",
        shared_inventory_label("action_ledger"),
        ("action_ledger_ok", "action_ledger_total", "last_route_summary", "last_action_final_answer"),
        ("action_ledger",),
        (READ, FIND, PULSE),
        ("active_work_tree_run_next",),
        ("services/nova_action_ledger.py", "services/control_telemetry.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "generated_queue",
        "Generated session queue, blocked reasons, and echo-work pressure",
        ("generated_work_queue", "generated_queue_status", "queue_open_count", "queue_blocked_count"),
        ("generated_queue",),
        ("queue_status", "generated_queue_run", "read", "find"),
        ("generated_queue_run_next", "generated_queue_investigate"),
        ("services/nova_http_generated_work.py", "autonomy_maintenance.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "subconscious",
        "Subconscious reports, triage signals, and review judgment",
        ("subconscious_summary", "subconscious_ok", "subconscious_latest_report_path"),
        ("subconscious",),
        ("subconscious_review_judgment", "read", "find"),
        ("active_work_tree_run_next",),
        ("subconscious_live_simulator.py", "services/subconscious_work_tree_triage.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "patch_pipeline",
        "Patch previews, validated apply readiness, cleanup, and rollback",
        ("patch_status_ok", "patch_enabled", "patch_pipeline_ready", "patch_cleanup_status"),
        ("patch_pipeline",),
        ("patch_preview_approve", "patch_preview_apply", "patch_apply", "patch_rollback", "read"),
        ("patch_queue_run_next", "update_now_dry_run"),
        ("services/nova_patching.py", "services/patch_control.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "codegen_pipeline",
        "Code generation previews, capability gap detection, memory promotion, and Leah build routing",
        ("capability_gap_count", "capability_gaps", "capabilities_roadmap"),
        ("codegen_pipeline",),
        (READ, FIND, PULSE),
        ("codegen_run", "leah_build_run_next"),
        (
            "services/control_status.py",
            "services/capabilities_gap_detector.py",
            "services/work_tree_signal_ingestion.py",
            "services/nova_control_action_dispatcher.py",
            "services/autonomy_orchestrator.py",
            "tools/codegen_tool.py",
            "services/codegen_memory_recorder.py",
            "services/patch_promotion_memory.py",
        ),
    ),
    WiringSurface(
        "release",
        "Release package readiness, validation evidence, promotion judgment, and rebuild",
        ("release_status",),
        ("release",),
        (
            RELEASE_VALIDATION_RUN,
            RELEASE_PROMOTION_JUDGMENT,
            RELEASE_RECORD_VALIDATION_OUTCOME,
            RELEASE_REBUILD_VERIFY,
            READ,
            FIND,
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
        "edfi_capability_profile",
        "data connector capability profile evidence, saved district contract, and profile-grounded signal closure",
        (
            "edfi_capability_profile",
            "edfi_capability_profile_ok",
            "edfi_capability_profile_status",
            "edfi_capability_profile_present",
            "edfi_capability_profile_connection_id",
            "edfi_capability_profile_resource_count",
            "edfi_capability_profile_discovered_at",
            "edfi_capability_profile_auth_ok",
            "edfi_capability_profile_issue_count",
            "edfi_capability_profile_path",
        ),
        ("edfi_capability_profile",),
        (READ, FIND),
        ("active_work_tree_run_next",),
        (
            "services/edfi/profile_evidence.py",
            "services/control_status.py",
            "services/work_tree_signal_ingestion.py",
            "scripts/run_edfi_profile.py",
        ),
    ),
    WiringSurface(
        "edfi_core",
        "Vendor-neutral data connector core services, explore tool, and core readiness lifecycle",
        (
            "edfi_core_readiness",
            "edfi_core_ready",
            "edfi_capability_profile",
        ),
        ("edfi_core",),
        ("edfi_explore", "read", "find", "pipeline"),
        ("active_work_tree_run_next",),
        (
            "services/edfi/core_readiness.py",
            "services/edfi/client.py",
            "services/edfi/discovery.py",
            "tools/edfi_tool.py",
            "scripts/demo_edfi_core_lifecycle.py",
        ),
    ),
    WiringSurface(
        "backpack_edfi",
        "data connector backpack package, host, capability fusion scan, and control surface for Nova nervous system",
        (
            "backpack_fusion",
            "backpack_fusion_ok",
            "backpack_available_capabilities",
            "backpack_capability_count",
            "backpack_teach_rules",
            "backpack_nova_must_know",
            "backpack_local_schools_rows",
        ),
        ("backpack_edfi", "edfi_core"),
        ("edfi_explore", "read", "find"),
        ("active_work_tree_run_next",),
        (
            "backpacks/edfi/backpack.json",
            "services/backpack_host/capability_surface.py",
            "services/backpack_host/query.py",
            "services/control_backpacks.py",
            "tools/edfi_tool.py",
        ),
    ),
    WiringSurface(
        "backpack_host",
        "Backpack host install contract — discovery, settings, uninstall sanitizer, and residue scan",
        (
            "backpack_fusion",
            "backpack_fusion_ok",
        ),
        ("backpack_host",),
        ("read", "find"),
        ("active_work_tree_run_next",),
        (
            "services/backpack_host/sanitize.py",
            "services/backpack_host/install_state.py",
            "services/control_backpacks.py",
        ),
    ),
    WiringSurface(
        "data_lane_data_connector",
        "LEGACY data connector data lane (prefer installed backpack)",
        ("data_pipelines", "data_pipeline_count"),
        ("data_lane_data_connector",),
        ("pipeline", "read", "find"),
        ("active_work_tree_run_next",),
        (
            "data_sources/data_connector/connector.py",
            "data_sources/data_connector/pipeline.json",
            "scripts/run_edfi_profile.py",
            "scripts/run_edfi_explore.py",
        ),
    ),
    WiringSurface(
        "voice",
        "Voice runtime dependency loading and entrypoint wrappers",
        ("voice_status", "voice_runtime_status", "voice_runtime_requested"),
        ("voice",),
        (READ, FIND, "system_check"),
        ("active_work_tree_run_next",),
        ("services/nova_voice_runtime.py", "services/voice_interaction.py", "nova_core.py"),
    ),
    WiringSurface(
        "vision",
        "Vision runtime, screen/camera policy, and model availability",
        ("vision_status", "vision_runtime_status", "vision_runtime_requested"),
        ("vision",),
        ("screen", "camera", "read", "find", "system_check"),
        ("active_work_tree_run_next",),
        ("tools/vision_tool.py", "services/nova_vision_runtime.py", "look_crop.py"),
    ),
    WiringSurface(
        "http_continuity",
        shared_inventory_label("http_continuity"),
        ("active_http_sessions", "last_route_summary", "last_action_final_answer"),
        ("http_continuity",),
        (READ, FIND, PULSE),
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
        ("test_ecosystem",),
        (READ, FIND, "queue_status"),
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
        ("storage_release_pressure",),
        (READ, FIND, "system_check"),
        ("active_work_tree_run_next",),
        ("services/storage_watch.py", "kidney.py", "services/release_clean.py"),
    ),
    WiringSurface(
        "runtime_control",
        shared_inventory_label("runtime_control"),
        ("action_readiness", "runtime_timeline", "runtime_restart_analytics", "runtime_failures"),
        ("runtime_control",),
        ("system_check", READ, FIND),
        ("active_work_tree_run_next",),
        ("services/runtime_control.py", "services/runtime_process_state.py", "services/runtime_restart_provenance.py"),
    ),
    WiringSurface(
        "scheduler_registry",
        shared_inventory_label("scheduler_registry"),
        ("maintenance_scheduler_status", "runtime_worker_status", "autonomy_maintenance"),
        ("scheduler_registry",),
        ("queue_status", "read", "find"),
        ("autonomy_maintenance_start", "active_work_tree_run_next"),
        ("services/schedule_registry.py", "autonomy_maintenance.py", "nova_guard.py"),
    ),
    WiringSurface(
        "autonomy_maintenance",
        "Autonomy maintenance worker state, cycle execution, and maintenance error pressure",
        ("autonomy_maintenance", "runtime_worker_status", "runtime_worker_stale_identity"),
        ("autonomy_maintenance",),
        (READ, FIND, PULSE, "system_check", SOURCE_ROOT_JUDGMENT),
        ("autonomy_maintenance_start", "active_work_tree_run_next"),
        ("autonomy_maintenance.py", "services/work_tree_signal_ingestion.py", "services/runtime_control.py"),
    ),
    WiringSurface(
        "autonomy_orchestrator",
        "Autonomy orchestrator decisions, advisory actions, ledger evidence, and blockage pressure",
        (
            "autonomy_orchestrator",
            "autonomy_orchestrator_summary",
            "autonomy_orchestrator_ledger_status",
            "autonomy_orchestrator_rejection_reasons",
        ),
        ("autonomy_orchestrator",),
        (READ, FIND, PULSE, SOURCE_ROOT_JUDGMENT),
        ("active_work_tree_run_next",),
        (
            "services/autonomy_orchestrator.py",
            "services/nova_mission.py",
            "autonomy_maintenance.py",
            "services/work_tree_signal_ingestion.py",
        ),
    ),
    WiringSurface(
        "frontdoor_cli",
        shared_inventory_label("frontdoor_cli"),
        ("backend_commands", "backend_command_count", "source_root_inventory"),
        ("frontdoor_cli",),
        (READ, FIND, "system_check"),
        ("active_work_tree_run_next",),
        ("nova.cmd", "nova.ps1", "agent.py", "run.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "http_api_control",
        shared_inventory_label("http_api_control"),
        ("requests_total", "errors_total", "chat_login_enabled", "source_root_inventory"),
        ("http_api_control", "http_continuity"),
        (READ, FIND, PULSE),
        ("active_work_tree_run_next",),
        ("nova_http.py", "services/nova_http_get_routes.py", "services/nova_http_post_dispatch.py"),
    ),
    WiringSurface(
        "operator_control",
        shared_inventory_label("operator_control"),
        ("operator_macros", "backend_commands", "operator_outbox", "operator_outbox_open_count", "source_root_inventory"),
        ("operator_control",),
        (READ, FIND, PULSE),
        ("active_work_tree_run_next",),
        ("services/operator_control.py", "services/operator_outbox.py", "services/nova_control_action_dispatcher.py", "scripts/operator_cli.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "session_identity_auth",
        shared_inventory_label("session_identity_auth"),
        ("chat_auth_source", "chat_users_count", "chat_login_enabled", "source_root_inventory"),
        ("session_identity_auth",),
        (READ, FIND, PULSE),
        ("active_work_tree_run_next",),
        ("services/chat_identity.py", "services/session_admin.py", "http_session_store.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "conversation_routing",
        shared_inventory_label("conversation_routing"),
        ("last_intent", "last_planner_decision", "last_route_summary", "source_root_inventory"),
        ("conversation_routing",),
        (READ, FIND, PULSE),
        ("active_work_tree_run_next",),
        ("services/nova_routing_support.py", "services/nova_reply_sequence.py", "services/nova_planner_contract.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "supervisor_fulfillment",
        shared_inventory_label("supervisor_fulfillment"),
        ("last_route_summary", "last_route_trace", "source_root_inventory"),
        ("supervisor_fulfillment",),
        (READ, FIND, PULSE),
        ("active_work_tree_run_next",),
        ("supervisor.py", "services/supervisor_registry.py", "services/fulfillment_flow.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "reply_quality_contracts",
        shared_inventory_label("reply_quality_contracts"),
        ("last_action_final_answer", "last_route_grounded", "last_route_trace", "source_root_inventory"),
        ("reply_quality_contracts",),
        (READ, FIND, PULSE),
        ("active_work_tree_run_next",),
        ("services/nova_reflection_health.py", "services/nova_reply_runtime.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "retrieval_knowledge",
        shared_inventory_label("retrieval_knowledge"),
        ("web_enabled", "last_provider_hit", "source_root_inventory"),
        ("retrieval_knowledge",),
        ("web_search", "web_research", "read", "find"),
        ("active_work_tree_run_next",),
        ("services/nova_knowledge_packs.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "weather_location",
        shared_inventory_label("weather_location"),
        ("web_enabled", "last_route_summary", "source_root_inventory"),
        ("weather_location",),
        ("weather_current_location", "weather_location", "location_coords", "read", "find"),
        ("active_work_tree_run_next",),
        ("services/nova_location_weather.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "tool_registry_policy",
        shared_inventory_label("tool_registry_policy"),
        (
            "tool_events_total",
            "backend_command_count",
            "os_capability_ledger",
            "os_capability_ledger_ok",
            "os_capability_ledger_current_issue_count",
            "source_root_inventory",
        ),
        ("tool_registry_policy", "source_root_inventory"),
        (READ, FIND, "queue_status", "os_capability"),
        ("active_work_tree_run_next",),
        (
            "tools/registry.py",
            "services/tool_registry.py",
            "services/nova_tool_policy.py",
            "services/os_capability_registry.py",
            "services/os_capability_operator_outbox.py",
            "services/os_script_controller.py",
            "tools/os_capability_tool.py",
            "tools/os_capabilities/os_capabilities.json",
            "tools/os_capabilities/collect_diagnostics_bundle.ps1",
            "tools/os_capabilities/inspect_ports.ps1",
            "tools/os_capabilities/inspect_processes.ps1",
            "tools/os_capabilities/inspect_runtime_health.ps1",
            "tools/os_capabilities/scan_large_files.ps1",
            "tools/os_capabilities/verify_ollama_model.ps1",
        ),
    ),
    WiringSurface(
        "installer_packaging",
        shared_inventory_label("installer_packaging"),
        ("release_status", "installer_release_status", "installer_status", "source_root_inventory"),
        ("installer_packaging",),
        (INSTALLER_VALIDATION_RUN, READ, FIND, "system_check", SOURCE_ROOT_JUDGMENT),
        ("active_work_tree_run_next",),
        (
            "services/installer_validation.py",
            "scripts/build_windows_installer.ps1",
            "scripts/verify_windows_installer.ps1",
            "docs/WINDOWS_INSTALLER_PLAN.md",
            "services/work_tree_signal_ingestion.py",
        ),
    ),
    WiringSurface(
        "tts_audio_output",
        shared_inventory_label("tts_audio_output"),
        ("voice_status", "voice_runtime_status", "source_root_inventory"),
        ("tts_audio_output",),
        (READ, FIND, "system_check"),
        ("active_work_tree_run_next",),
        ("tts_say.py", "tts_piper.py", "tts_say.ps1", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "diagnostics_hygiene",
        shared_inventory_label("diagnostics_hygiene"),
        ("health_score", "self_check_pass_ratio", "source_root_inventory"),
        ("diagnostics_hygiene", "source_root_inventory"),
        ("health", "system_check", READ, FIND),
        ("active_work_tree_run_next",),
        ("doctor.py", "health.py", "scripts/repo_hygiene_check.py"),
    ),
    WiringSurface(
        "hardware_profile",
        "SOCK — System Optimization and Compatibility Check: hardware scan, tier mapping, model recommendation",
        ("sock_hardware_profile", "sock_recommendation", "sock_policy_diff", "source_root_inventory"),
        ("source_root_inventory",),
        ("system_check", READ, FIND),
        ("active_work_tree_run_next",),
        ("services/sock_service.py", "scripts/run_sock.py"),
    ),
    WiringSurface(
        "safety_envelope",
        shared_inventory_label("safety_envelope"),
        ("subconscious_summary", "generated_work_queue", "source_root_inventory"),
        ("safety_envelope",),
        (PHASE2_AUDIT, READ, FIND),
        ("active_work_tree_run_next",),
        ("nova_safety_envelope.py", "services/subconscious_review_authority.py", "docs/PHASE2_SAFETY_ENVELOPE.md", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "metrics_ops_journal",
        shared_inventory_label("metrics_ops_journal"),
        ("requests_total", "errors_total", "tool_events_total", "source_root_inventory"),
        ("metrics_ops_journal",),
        (READ, FIND, PULSE),
        ("active_work_tree_run_next",),
        ("services/behavior_metrics.py", "services/ops_journal.py", "services/control_telemetry.py", "services/work_tree_signal_ingestion.py"),
    ),
    WiringSurface(
        "core_steward_reflection",
        shared_inventory_label("core_steward_reflection"),
        (PULSE, "health_score", "source_root_inventory"),
        ("core_steward_reflection",),
        ("core_health", "core_thinning", PULSE, READ, FIND),
        ("active_work_tree_run_next",),
        ("services/core_steward.py", "services/core_health_brief.py", "services/core_thinning.py", "services/work_tree_signal_ingestion.py"),
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
            "source_wiring_probe",
            "source_wiring_probe_ok",
            "source_wiring_probe_gap_count",
            "root_closure_inventory",
            "root_closure_inventory_ok",
            "root_closure_inventory_gap_count",
            "self_repair_closure_inventory",
            "self_repair_closure_inventory_ok",
            "self_repair_closure_inventory_gap_count",
        ),
        ("source_root_inventory", "source_wiring_probe", "root_closure_inventory", "self_repair_closure_inventory"),
        (READ, FIND, PULSE),
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

EXECUTION_TOOL_CONSTANTS = (
    "ACTIVE_WORK_TREE_EXECUTE_TOOLS",
    "PATCH_QUEUE_EXECUTE_TOOLS",
    "GENERATED_QUEUE_EXECUTE_TOOLS",
    "OPERATOR_GOVERNED_PATCH_EXECUTE_TOOLS",
)

REQUIRED_EVIDENCE_PATHS = frozenset(("work_tree_evidence",))
REQUIRED_JUDGMENT_PATHS = frozenset(
    ("signal_branch_resolution", SOURCE_ROOT_JUDGMENT, "tool_result_validation")
)
REQUIRED_CLOSURE_PATHS = frozenset(("work_tree_task_completion", "signal_branch_resolution"))
REQUIRED_OPERATOR_OUTBOX_PATHS = frozenset(("operator_outbox_notice", "work_tree_operator_notice"))
REQUIRED_OWNED_ROOT_ROUTES = frozenset(("self_repair_closure_inventory", "source_root_judgment_sequence"))

_LITERAL_NAME_TO_TOOL = {
    "LS": LS,
    "READ": READ,
    "FIND": FIND,
    "PULSE": PULSE,
    "PHASE2_AUDIT": PHASE2_AUDIT,
    "OPERATOR_RESPONSE": OPERATOR_RESPONSE,
    "SOURCE_ROOT_JUDGMENT": SOURCE_ROOT_JUDGMENT,
    "GENERATED_QUEUE_RUN": "generated_queue_run",
    "MEMORY_BOOTSTRAP_JUDGMENT": MEMORY_BOOTSTRAP_JUDGMENT,
    "SUBCONSCIOUS_REVIEW_JUDGMENT": SUBCONSCIOUS_REVIEW_JUDGMENT,
    "INSTALLER_VALIDATION_RUN": INSTALLER_VALIDATION_RUN,
    "RELEASE_PROMOTION_JUDGMENT": RELEASE_PROMOTION_JUDGMENT,
    "RELEASE_VALIDATION_RUN": RELEASE_VALIDATION_RUN,
    "RELEASE_RECORD_VALIDATION_OUTCOME": RELEASE_RECORD_VALIDATION_OUTCOME,
    "RELEASE_REBUILD_VERIFY": RELEASE_REBUILD_VERIFY,
}


def _clean_set(values: Iterable[str] | None) -> set[str]:
    return {str(item or "").strip() for item in list(values or []) if str(item or "").strip()}


def _read_source(repo_root: Path, relative_path: str) -> str:
    path = repo_root / relative_path
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _literal_string_sequence(source: str, constant_names: Iterable[str]) -> set[str]:
    wanted = _clean_set(constant_names)
    if not source.strip() or not wanted:
        return set()
    try:
        module = ast.parse(source)
    except SyntaxError:
        return set()

    values: set[str] = set()
    for node in module.body:
        targets = []
        value_node = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value_node = node.value
        else:
            continue
        if value_node is None:
            continue
        target_names = {
            target.id
            for target in targets
            if isinstance(target, ast.Name)
        }
        if not target_names.intersection(wanted):
            continue
        if not isinstance(value_node, (ast.List, ast.Tuple, ast.Set)):
            continue
        for item in value_node.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str) and item.value.strip():
                values.add(item.value.strip())
            elif isinstance(item, ast.Name):
                resolved = _LITERAL_NAME_TO_TOOL.get(item.id)
                if resolved:
                    values.add(str(resolved).strip())
    return values


def _source_mentions(source: str, token: str) -> bool:
    if not source or not token:
        return False
    variants = {
        token,
        token.lower(),
        token.upper(),
        token.replace("_", ""),
        token.replace("_", "").lower(),
        token.replace("_", "").upper(),
    }
    for key, value in _LITERAL_NAME_TO_TOOL.items():
        if str(value).strip() == str(token).strip():
            variants.add(key)
            variants.add(key.lower())
            variants.add(key.upper())
    return any(variant in source for variant in variants)


def _literal_dict_string_values(source: str, key_name: str) -> set[str]:
    if not source.strip() or not key_name.strip():
        return set()
    try:
        module = ast.parse(source)
    except SyntaxError:
        return set()

    values: set[str] = set()
    for node in ast.walk(module):
        if not isinstance(node, ast.Dict):
            continue
        for key_node, value_node in zip(node.keys, node.values):
            if not (
                isinstance(key_node, ast.Constant)
                and isinstance(key_node.value, str)
                and key_node.value == key_name
            ):
                continue
            if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str) and value_node.value.strip():
                values.add(value_node.value.strip())
    return values


def build_source_wiring_probe_payload(*, root: str | Path | None = None) -> dict[str, Any]:
    """Probe the source tree for the code paths required by Nova self-repair.

    This is intentionally source-derived instead of declared-by-registry.  The
    registry says what should exist; this probe checks whether the execution,
    evidence, judgment, closure, and outbox paths are actually present in code.
    """
    repo_root = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    signal_text = _read_source(repo_root, "services/work_tree_signal_ingestion.py")
    tool_dispatch_text = _read_source(repo_root, "services/nova_tool_dispatch.py")
    work_tree_text = _read_source(repo_root, "work_tree.py")
    dispatcher_text = _read_source(repo_root, "services/nova_control_action_dispatcher.py")
    autonomy_text = _read_source(repo_root, "autonomy_maintenance.py")
    operator_outbox_text = _read_source(repo_root, "services/operator_outbox.py")
    os_controller_text = _read_source(repo_root, "services/os_script_controller.py")
    tool_registry_text = _read_source(repo_root, "tools/registry.py")
    actual_signal_sources = _literal_dict_string_values(signal_text, "source")

    signal_sources = {
        source
        for surface in WIRING_SURFACES
        for source in surface.signal_sources
        if source in actual_signal_sources
    }
    planned_tools = {
        tool
        for surface in WIRING_SURFACES
        for tool in surface.planned_tools
        if _source_mentions(tool_dispatch_text, tool) or _source_mentions(work_tree_text, tool)
    }
    advisory_actions = {
        action
        for surface in WIRING_SURFACES
        for action in surface.advisory_actions
        if _source_mentions(dispatcher_text, action)
    }
    executable_tools = _literal_string_sequence(autonomy_text, EXECUTION_TOOL_CONSTANTS)
    executable_actions = {
        action
        for action in DEFAULT_ADVISORY_ACTIONS
        if action in dispatcher_text and action in autonomy_text
    }

    evidence_paths: set[str] = set()
    if "def record_task_evidence" in work_tree_text and "work_tree_evidence" in work_tree_text:
        evidence_paths.add("work_tree_evidence")
    if "TOOL_EVENTS_FILE" in tool_registry_text or "ToolExecutionService" in _read_source(repo_root, "services/tool_execution.py"):
        evidence_paths.add("tool_events")
    if "AUTONOMY_ORCHESTRATOR_LEDGER" in autonomy_text:
        evidence_paths.add("autonomy_orchestrator_ledger")
    if "append_ledger" in os_controller_text or "ledger" in os_controller_text:
        evidence_paths.add("os_capability_ledger")

    judgment_paths: set[str] = set()
    if "def resolve_signal_branches" in signal_text:
        judgment_paths.add("signal_branch_resolution")
    if "def mark_task_complete" in work_tree_text:
        judgment_paths.add("work_tree_task_completion")
    if "invalid_tool_result" in work_tree_text or "_is_invalid_tool_result" in work_tree_text:
        judgment_paths.add("tool_result_validation")
    if _source_mentions(tool_dispatch_text, RELEASE_PROMOTION_JUDGMENT) and _source_mentions(work_tree_text, RELEASE_PROMOTION_JUDGMENT):
        judgment_paths.add(RELEASE_PROMOTION_JUDGMENT)
    if _source_mentions(tool_dispatch_text, MEMORY_BOOTSTRAP_JUDGMENT) and _source_mentions(work_tree_text, MEMORY_BOOTSTRAP_JUDGMENT):
        judgment_paths.add(MEMORY_BOOTSTRAP_JUDGMENT)
    if _source_mentions(tool_dispatch_text, SUBCONSCIOUS_REVIEW_JUDGMENT) and _source_mentions(work_tree_text, SUBCONSCIOUS_REVIEW_JUDGMENT):
        judgment_paths.add(SUBCONSCIOUS_REVIEW_JUDGMENT)
    if (
        _source_mentions(tool_dispatch_text, SOURCE_ROOT_JUDGMENT)
        and _source_mentions(work_tree_text, SOURCE_ROOT_JUDGMENT)
        and "SOURCE_ROOT_JUDGMENT_TOOL" in signal_text
    ):
        judgment_paths.add(SOURCE_ROOT_JUDGMENT)
    if "def respond_to_notice" in operator_outbox_text and "_record_response_in_work_tree" in operator_outbox_text:
        judgment_paths.add("operator_response_judgment")

    closure_paths: set[str] = set()
    if "def mark_task_complete" in work_tree_text:
        closure_paths.add("work_tree_task_completion")
    if "def is_tree_complete" in work_tree_text:
        closure_paths.add("tree_completion")
    if "def resolve_signal_branches" in signal_text:
        closure_paths.add("signal_branch_resolution")
    if "def resolve_inactive_signal_branches" in signal_text:
        closure_paths.add("inactive_signal_retirement")
    if "def reconcile_work_tree_notices" in operator_outbox_text:
        closure_paths.add("operator_notice_reconciliation")

    operator_outbox_paths: set[str] = set()
    if "def append_notice" in operator_outbox_text:
        operator_outbox_paths.add("operator_outbox_notice")
    if "def notices_from_work_tree_state" in operator_outbox_text:
        operator_outbox_paths.add("work_tree_operator_notice")
    if "def notice_from_autonomy" in operator_outbox_text:
        operator_outbox_paths.add("autonomy_operator_notice")
    if "os_capability" in operator_outbox_text and "reconcile_os_capability_notices" in operator_outbox_text:
        operator_outbox_paths.add("os_capability_operator_notice")
    if "publish_source_root_operator_notice" in _read_source(repo_root, "services/source_root_judgment.py"):
        operator_outbox_paths.add("source_root_operator_notice")

    owned_root_routes: set[str] = set()
    if (
        "def _root_closure_inventory_signals_from_status" in signal_text
        and '"symbol": root_id' in signal_text
        and '"source": "root_closure_inventory"' in signal_text
        and '"tool_args": [first_source_file]' in signal_text
    ):
        owned_root_routes.add("root_closure_inventory")
    if (
        "def _self_repair_closure_inventory_signals_from_status" in signal_text
        and '"symbol": root_id' in signal_text
        and '"source": "self_repair_closure_inventory"' in signal_text
        and '"tool_args": [first_source_file]' in signal_text
        and "active_source_keys" in signal_text
        and 'source="self_repair_closure_inventory"' in signal_text
    ):
        owned_root_routes.add("self_repair_closure_inventory")
    if (
        "def _append_source_root_judgment_task" in signal_text
        and "SOURCE_ROOT_JUDGMENT_TOOL" in signal_text
        and "SOURCE_ROOT_JUDGMENT_TASK_TITLE" in signal_text
    ):
        owned_root_routes.add("source_root_judgment_sequence")

    missing_signal_sources = sorted(DEFAULT_SIGNAL_SOURCES - signal_sources)
    missing_planned_tools = sorted(DEFAULT_PLANNED_TOOLS - planned_tools)
    missing_advisory_actions = sorted(DEFAULT_ADVISORY_ACTIONS - advisory_actions)
    planned_tools_without_execution = sorted(DEFAULT_PLANNED_TOOLS - executable_tools)
    advisory_actions_without_execution = sorted(DEFAULT_ADVISORY_ACTIONS - executable_actions)
    missing_required_evidence_paths = sorted(REQUIRED_EVIDENCE_PATHS - evidence_paths)
    missing_required_judgment_paths = sorted(REQUIRED_JUDGMENT_PATHS - judgment_paths)
    missing_required_closure_paths = sorted(REQUIRED_CLOSURE_PATHS - closure_paths)
    missing_required_operator_outbox_paths = sorted(REQUIRED_OPERATOR_OUTBOX_PATHS - operator_outbox_paths)
    missing_required_owned_root_routes = sorted(REQUIRED_OWNED_ROOT_ROUTES - owned_root_routes)
    gap_count = sum(
        len(items)
        for items in (
            missing_signal_sources,
            missing_planned_tools,
            missing_advisory_actions,
            planned_tools_without_execution,
            advisory_actions_without_execution,
            missing_required_evidence_paths,
            missing_required_judgment_paths,
            missing_required_closure_paths,
            missing_required_operator_outbox_paths,
            missing_required_owned_root_routes,
        )
    )

    return {
        "ok": gap_count == 0,
        "root": str(repo_root),
        "gap_count": gap_count,
        "missing_signal_sources": missing_signal_sources,
        "missing_planned_tools": missing_planned_tools,
        "missing_advisory_actions": missing_advisory_actions,
        "planned_tools_without_execution": planned_tools_without_execution,
        "advisory_actions_without_execution": advisory_actions_without_execution,
        "missing_required_evidence_paths": missing_required_evidence_paths,
        "missing_required_judgment_paths": missing_required_judgment_paths,
        "missing_required_closure_paths": missing_required_closure_paths,
        "missing_required_operator_outbox_paths": missing_required_operator_outbox_paths,
        "missing_required_owned_root_routes": missing_required_owned_root_routes,
        "signal_sources": sorted(signal_sources),
        "planned_tools": sorted(planned_tools),
        "advisory_actions": sorted(advisory_actions),
        "executable_tools": sorted(executable_tools),
        "executable_actions": sorted(executable_actions),
        "evidence_paths": sorted(evidence_paths),
        "judgment_paths": sorted(judgment_paths),
        "closure_paths": sorted(closure_paths),
        "operator_outbox_paths": sorted(operator_outbox_paths),
        "owned_root_routes": sorted(owned_root_routes),
    }


def build_wiring_inventory_payload(
    status_payload: dict[str, Any] | None = None,
    *,
    signal_sources: Iterable[str] | None = None,
    planned_tools: Iterable[str] | None = None,
    advisory_actions: Iterable[str] | None = None,
    probe_context: str | None = None,
) -> dict[str, Any]:
    status = status_payload if isinstance(status_payload, dict) else {}
    # Ring 2: do not score status-key gaps without live_status probe context.
    try:
        from services.self_scan_rings import PROBE_LIVE, resolve_probe_context

        context = resolve_probe_context(status, explicit=probe_context)
    except Exception:
        context = str(probe_context or ("live_status" if status else "offline")).strip().lower()
        PROBE_LIVE = "live_status"
    score_status_keys = context == PROBE_LIVE
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

        if score_status_keys:
            status_visible = not surface.status_keys or not missing_status_keys
        else:
            # Offline/partial: status keys are not evidence of architecture failure.
            status_visible = True
            missing_status_keys = []
        signal_wired = not surface.signal_sources or not missing_signal_sources
        tool_wired = not surface.planned_tools or not missing_planned_tools
        action_wired = not surface.advisory_actions or not missing_advisory_actions
        if score_status_keys and not status_visible:
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
        "probe_context": context,
        "status_gaps_scored": score_status_keys,
    }


def build_root_closure_inventory_payload(
    status_payload: dict[str, Any] | None = None,
    *,
    root: str | Path | None = None,
    signal_sources: Iterable[str] | None = None,
    planned_tools: Iterable[str] | None = None,
    advisory_actions: Iterable[str] | None = None,
    probe_context: str | None = None,
) -> dict[str, Any]:
    """Describe whether every declared root has a complete code wiring route.

    This inventory is intentionally stricter than source presence.  A root is
    not closure-wired just because it exists on disk; it needs a status surface,
    a signal source, a planned tool path, and an advisory action path.

    Ring 2 probe context: offline/partial must not report all status keys missing
    as architecture failures (false 46-gap storms).
    """
    from services.nova_root_inventory import SOURCE_ROOTS

    status = status_payload if isinstance(status_payload, dict) else {}
    try:
        from services.self_scan_rings import PROBE_LIVE, resolve_probe_context

        context = resolve_probe_context(status, explicit=probe_context)
    except Exception:
        context = str(probe_context or ("live_status" if status else "offline")).strip().lower()
        PROBE_LIVE = "live_status"
    score_status_keys = context == PROBE_LIVE
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
        if not score_status_keys:
            missing_status_keys = []
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
        if score_status_keys and surface is not None and status_keys and missing_status_keys:
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
        "probe_context": context,
        "status_gaps_scored": score_status_keys,
    }


def _closure_depth(row: dict[str, Any]) -> str:
    if not bool(row.get("source_evidence_available", False)):
        return "source_missing"
    if not bool(row.get("status_visible", False)) or not bool(row.get("signal_wired", False)):
        return "visible_only"
    if not bool(row.get("owned_root_route_available", False)):
        return "signal_borrowed"
    if not bool(row.get("action_available", False)):
        return "signal_wired"
    if not bool(row.get("execution_available", False)):
        return "action_wired"
    if not bool(row.get("evidence_available", False)):
        return "execution_wired"
    if not bool(row.get("judgment_available", False)):
        return "evidence_wired"
    if not bool(row.get("closure_available", False)):
        return "judgment_wired"
    if not bool(row.get("operator_outbox_available", False)):
        return "closure_no_outbox"
    return "source_contract_ready"


def build_self_repair_closure_inventory_payload(
    status_payload: dict[str, Any] | None = None,
    *,
    root: str | Path | None = None,
    signal_sources: Iterable[str] | None = None,
    planned_tools: Iterable[str] | None = None,
    advisory_actions: Iterable[str] | None = None,
    executable_tools: Iterable[str] | None = None,
    executable_actions: Iterable[str] | None = None,
    evidence_paths: Iterable[str] | None = None,
    judgment_paths: Iterable[str] | None = None,
    closure_paths: Iterable[str] | None = None,
    operator_outbox_paths: Iterable[str] | None = None,
    owned_root_routes: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Classify each root by static self-repair wiring depth.

    A root is only source-contract ready when code evidence shows the full chain:
    signal -> Work Tree -> action/capability -> execution -> evidence ->
    judgment -> branch closure, with operator outbox available for authority
    or missing-tool gaps. Live closure is intentionally not claimed here.
    """
    probe = build_source_wiring_probe_payload(root=root)

    available_sources = _clean_set(signal_sources) if signal_sources is not None else set(probe.get("signal_sources") or [])
    available_tools = _clean_set(planned_tools) if planned_tools is not None else set(probe.get("planned_tools") or [])
    available_actions = _clean_set(advisory_actions) if advisory_actions is not None else set(probe.get("advisory_actions") or [])
    available_executable_tools = (
        _clean_set(executable_tools) if executable_tools is not None else set(probe.get("executable_tools") or [])
    )
    available_executable_actions = (
        _clean_set(executable_actions) if executable_actions is not None else set(probe.get("executable_actions") or [])
    )
    available_evidence_paths = _clean_set(evidence_paths) if evidence_paths is not None else set(probe.get("evidence_paths") or [])
    available_judgment_paths = _clean_set(judgment_paths) if judgment_paths is not None else set(probe.get("judgment_paths") or [])
    available_closure_paths = _clean_set(closure_paths) if closure_paths is not None else set(probe.get("closure_paths") or [])
    available_outbox_paths = (
        _clean_set(operator_outbox_paths)
        if operator_outbox_paths is not None
        else set(probe.get("operator_outbox_paths") or [])
    )
    available_owned_root_routes = (
        _clean_set(owned_root_routes)
        if owned_root_routes is not None
        else set(probe.get("owned_root_routes") or [])
    )

    root_closure = build_root_closure_inventory_payload(
        status_payload,
        root=root,
        signal_sources=available_sources,
        planned_tools=available_tools,
        advisory_actions=available_actions,
    )

    roots: list[dict[str, Any]] = []
    gap_roots: list[str] = []
    missing_execution_roots: list[str] = []
    missing_evidence_roots: list[str] = []
    missing_judgment_roots: list[str] = []
    missing_closure_roots: list[str] = []
    missing_outbox_roots: list[str] = []
    missing_owned_route_roots: list[str] = []
    depth_counts: dict[str, int] = {}

    evidence_missing = sorted(REQUIRED_EVIDENCE_PATHS - available_evidence_paths)
    judgment_missing = sorted(REQUIRED_JUDGMENT_PATHS - available_judgment_paths)
    closure_missing = sorted(REQUIRED_CLOSURE_PATHS - available_closure_paths)
    outbox_missing = sorted(REQUIRED_OPERATOR_OUTBOX_PATHS - available_outbox_paths)
    owned_route_missing = sorted(REQUIRED_OWNED_ROOT_ROUTES - available_owned_root_routes)

    for base_row in list(root_closure.get("roots") or []):
        if not isinstance(base_row, dict):
            continue
        row = dict(base_row)
        root_id = str(row.get("root_id") or "").strip()
        present_source_files = list(row.get("present_source_files") or [])
        present_planned_tools = _clean_set(row.get("present_planned_tools") or [])
        present_advisory_actions = _clean_set(row.get("present_advisory_actions") or [])
        executable_planned_tools = sorted(present_planned_tools & available_executable_tools)
        executable_advisory_actions = sorted(present_advisory_actions & available_executable_actions)

        source_evidence_available = bool(present_source_files)
        status_visible = not list(row.get("missing_status_keys") or [])
        signal_wired = not list(row.get("missing_signal_sources") or [])
        action_available = bool(present_planned_tools or present_advisory_actions)
        execution_available = bool(executable_planned_tools or executable_advisory_actions)
        evidence_available = not evidence_missing
        judgment_available = not judgment_missing
        closure_available = not closure_missing
        operator_outbox_available = not outbox_missing
        owned_root_route_available = not owned_route_missing

        gaps = [str(item or "").strip() for item in list(row.get("gaps") or []) if str(item or "").strip()]
        if not owned_root_route_available:
            gaps.append("missing_owned_root_route")
            missing_owned_route_roots.append(root_id)
        if not execution_available:
            gaps.append("missing_execution_path")
            missing_execution_roots.append(root_id)
        if not evidence_available:
            gaps.append("missing_evidence_path")
            missing_evidence_roots.append(root_id)
        if not judgment_available:
            gaps.append("missing_judgment_path")
            missing_judgment_roots.append(root_id)
        if not closure_available:
            gaps.append("missing_closure_path")
            missing_closure_roots.append(root_id)
        if not operator_outbox_available:
            gaps.append("missing_operator_outbox_path")
            missing_outbox_roots.append(root_id)

        row.update(
            {
                "source_evidence_available": source_evidence_available,
                "status_visible": status_visible,
                "signal_wired": signal_wired,
                "action_available": action_available,
                "execution_available": execution_available,
                "evidence_available": evidence_available,
                "judgment_available": judgment_available,
                "closure_available": closure_available,
                "operator_outbox_available": operator_outbox_available,
                "owned_root_route_available": owned_root_route_available,
                "owned_root_routes": sorted(available_owned_root_routes),
                "missing_owned_root_routes": owned_route_missing,
                "executable_planned_tools": executable_planned_tools,
                "executable_advisory_actions": executable_advisory_actions,
                "non_executable_planned_tools": sorted(present_planned_tools - available_executable_tools),
                "non_executable_advisory_actions": sorted(present_advisory_actions - available_executable_actions),
                "missing_evidence_paths": evidence_missing,
                "missing_judgment_paths": judgment_missing,
                "missing_closure_paths": closure_missing,
                "missing_operator_outbox_paths": outbox_missing,
                "gaps": gaps,
            }
        )
        row["closure_depth"] = _closure_depth(row)
        row["ok"] = row["closure_depth"] == "source_contract_ready" and not gaps
        depth_counts[row["closure_depth"]] = depth_counts.get(row["closure_depth"], 0) + 1
        if not row["ok"]:
            gap_roots.append(root_id)
        roots.append(row)

    return {
        "ok": not gap_roots,
        "proof_scope": "source_contract",
        "root_count": len(roots),
        "source_contract_ready_count": sum(1 for row in roots if row.get("closure_depth") == "source_contract_ready"),
        "gap_count": len(gap_roots),
        "gap_roots": gap_roots,
        "depth_counts": depth_counts,
        "missing_execution_roots": missing_execution_roots,
        "missing_evidence_roots": missing_evidence_roots,
        "missing_judgment_roots": missing_judgment_roots,
        "missing_closure_roots": missing_closure_roots,
        "missing_operator_outbox_roots": missing_outbox_roots,
        "missing_owned_route_roots": missing_owned_route_roots,
        "required_owned_root_routes": sorted(REQUIRED_OWNED_ROOT_ROUTES),
        "required_evidence_paths": sorted(REQUIRED_EVIDENCE_PATHS),
        "required_judgment_paths": sorted(REQUIRED_JUDGMENT_PATHS),
        "required_closure_paths": sorted(REQUIRED_CLOSURE_PATHS),
        "required_operator_outbox_paths": sorted(REQUIRED_OPERATOR_OUTBOX_PATHS),
        "source_probe": probe,
        "roots": roots,
    }


def wiring_surface_ids() -> tuple[str, ...]:
    return tuple(surface.surface_id for surface in WIRING_SURFACES)
