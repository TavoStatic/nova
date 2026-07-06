from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

from services.nova_wiring_inventory import WIRING_SURFACES


_SIGNAL_INGESTION_DERIVED_KEYS = (
    "alerts",
    "self_check_pass_ratio",
    "health_score",
    "ok",
    "status_kind",
    "signal_ingestion_status_source",
    "release_runtime_truth",
    "http_model_runtime_probe",
    "http_model_runtime_probe_ok",
    "http_model_runtime_missing_keys",
    "source_root_inventory_ok",
    "source_root_inventory_gap_count",
    "source_root_inventory_unwired_roots",
    "source_root_inventory_missing_evidence_roots",
    "source_root_inventory_unclassified_source_file_count",
    "source_root_inventory_unclassified_source_files",
    "source_wiring_probe_ok",
    "source_wiring_probe_gap_count",
    "source_wiring_probe_missing_signal_sources",
    "source_wiring_probe_missing_planned_tools",
    "source_wiring_probe_missing_advisory_actions",
    "source_wiring_probe_planned_tools_without_execution",
    "source_wiring_probe_advisory_actions_without_execution",
    "source_wiring_probe_missing_required_evidence_paths",
    "source_wiring_probe_missing_required_judgment_paths",
    "source_wiring_probe_missing_required_closure_paths",
    "source_wiring_probe_missing_required_operator_outbox_paths",
    "source_wiring_probe_missing_required_owned_root_routes",
    "root_closure_inventory_ok",
    "root_closure_inventory_gap_count",
    "root_closure_inventory_gap_roots",
    "self_repair_closure_inventory_ok",
    "self_repair_closure_inventory_gap_count",
    "self_repair_closure_inventory_gap_roots",
    "wiring_inventory_ok",
    "wiring_inventory_gap_count",
    "operator_outbox_open_count",
    "operator_outbox_latest_open_id",
    "data_pipeline_registry_ok",
    "data_pipeline_registry_error",
    "data_pipeline_count",
    "data_pipeline_ids",
    "edfi_capability_profile_ok",
    "edfi_capability_profile_status",
    "edfi_capability_profile_present",
    "edfi_capability_profile_connection_id",
    "edfi_capability_profile_resource_count",
    "edfi_capability_profile_discovered_at",
    "edfi_capability_profile_auth_ok",
    "edfi_capability_profile_issue_count",
    "edfi_capability_profile_path",
    "validation_artifact_truth_ok",
    "validation_artifact_truth_status",
    "validation_artifact_failure_count",
    "validation_artifact_llm_unavailable_count",
    "validation_artifact_hidden_by_green_regression",
    "validation_artifact_latest_failure",
    "test_profile_inventory_ok",
    "test_profile_profile_drift_count",
    "generated_queue_status",
    "queue_open_count",
    "queue_actionable_count",
    "queue_blocked_count",
    "queue_blocked_reason_counts",
    "queue_blocked_files",
    "maintenance_scheduler_active",
    "maintenance_scheduler_mode",
    "maintenance_scheduler_status",
    "runtime_worker_status",
    "runtime_worker_active",
    "runtime_worker_stale_identity",
    "temporal_enabled",
    "temporal_feed_status",
    "temporal_pressure_count",
    "temporal_event",
    "temporal_events",
    "capability_gap_count",
    "capability_gaps",
    "capabilities_gap_summary",
    "capabilities_roadmap",
    "port_ownership_status",
    "port_ownership_issue_count",
    "last_regression_status",
    "last_regression_stale",
    "release_runtime_truth",
    "http_model_runtime_probe",
    "http_model_runtime_probe_ok",
    "http_model_runtime_missing_keys",
    "running_build_identity",
    "runtime_drift_expected",
    "runtime_drift_tolerated",
    "runtime_drift_reason",
    "backend_command_count",
    "frontdoor_cli_status",
    "cli_http_parity",
    "layer_maturity",
    "capability_gaps_observed",
    "capability_gaps_actionable",
    "capability_gap_actionable_count",
    "capability_gap_observed_count",
    "suppress_capability_gap_signals",
    "next_leah_capability",
)

_SIGNAL_INGESTION_OBJECT_KEYS = (
    "source_root_inventory",
    "source_wiring_probe",
    "root_closure_inventory",
    "self_repair_closure_inventory",
    "wiring_inventory",
    "operator_outbox",
    "autonomy_maintenance",
    "data_pipelines",
    "edfi_capability_profile",
    "release_status",
    "generated_work_queue",
    "validation_artifact_truth",
    "test_profile_inventory",
    "tool_summary",
    "os_capability_summary",
    "os_capability_control",
    "patch_summary",
    "subconscious_summary",
    "subconscious_live_summary",
    "runtime_failures",
    "runtime_restart_analytics",
    "runtime_artifacts",
    "provider_telemetry",
    "voice_status",
    "vision_status",
    "ollama_health",
    "port_ownership",
    "memory_health",
    "autonomy_orchestrator",
    "autonomy_orchestrator_summary",
    "action_ledger_summary",
    "ledger_summary",
    "guard_status",
    "core_status",
    "webui_status",
    "pulse",
    "pulse_summary",
    "installer_release_status",
    "installer_status",
    "sock_hardware_profile",
    "sock_recommendation",
    "sock_policy_diff",
)

HTTP_SUPPLEMENT_KEYS = frozenset(
    {
        "alerts",
        "self_check_pass_ratio",
        "health_score",
        "operator_outbox",
        "operator_outbox_open_count",
        "operator_outbox_latest_open_id",
        "release_status",
        "generated_work_queue",
        "generated_queue_status",
        "queue_open_count",
        "queue_actionable_count",
        "queue_blocked_count",
        "queue_blocked_reason_counts",
        "queue_blocked_files",
        "autonomy_maintenance",
        "tool_summary",
        "last_intent",
        "last_planner_decision",
        "last_route_summary",
        "last_route_trace",
        "last_action_final_answer",
        "provider_telemetry",
        "searx_ok",
        "searx_note",
        "search_provider",
        "search_provider_priority",
        "guard_status",
        "core_status",
        "webui_status",
        "runtime_failures",
        "runtime_restart_analytics",
        "subconscious_summary",
        "subconscious_live_summary",
        "patch_summary",
        "patch_action_readiness",
        "os_capability_summary",
        "os_capability_control",
        "voice_status",
        "vision_status",
        "autonomy_orchestrator",
        "autonomy_orchestrator_summary",
        "validation_artifact_truth",
        "validation_artifact_truth_ok",
        "validation_artifact_truth_status",
        "test_profile_inventory",
        "test_profile_inventory_ok",
        "root_closure_inventory",
        "root_closure_inventory_ok",
        "root_closure_inventory_gap_count",
        "root_closure_inventory_gap_roots",
        "self_repair_closure_inventory",
        "self_repair_closure_inventory_ok",
        "self_repair_closure_inventory_gap_count",
        "self_repair_closure_inventory_gap_roots",
        "installer_release_status",
        "installer_status",
        "installer_packaging_status",
        "active_http_sessions",
        "action_ledger_summary",
        "ledger_summary",
        "memory_summary",
        "memory_stats",
        "backend_commands",
        "backend_command_count",
        "frontdoor_cli_status",
        "cli_http_parity",
        "operator_macros",
        "runtime_artifacts",
        "storage_watch_status",
        "runtime_worker_status",
        "runtime_worker_active",
        "runtime_worker_stale_identity",
        "maintenance_scheduler_active",
        "maintenance_scheduler_mode",
        "maintenance_scheduler_status",
        "temporal_enabled",
        "temporal_feed_status",
        "temporal_feed_event_count",
        "temporal_feed_surfaced_count",
        "temporal_pressure_count",
        "temporal_event",
        "temporal_events",
        "capability_gap_count",
        "capability_gaps",
        "capabilities_gap_summary",
        "capabilities_roadmap",
        "layer_maturity",
        "capability_gaps_observed",
        "capability_gaps_actionable",
        "capability_gap_actionable_count",
        "capability_gap_observed_count",
        "suppress_capability_gap_signals",
        "next_leah_capability",
        "data_pipelines",
        "edfi_capability_profile",
        "data_pipeline_registry_ok",
        "data_pipeline_registry_error",
        "data_pipeline_count",
        "data_pipeline_ids",
    }
)

LOCAL_AUTHORITATIVE_KEYS = frozenset(
    {
        "source_root_inventory",
        "source_root_inventory_ok",
        "source_root_inventory_gap_count",
        "source_root_inventory_unwired_roots",
        "source_root_inventory_missing_evidence_roots",
        "source_root_inventory_unclassified_source_file_count",
        "source_root_inventory_unclassified_source_files",
        "source_wiring_probe",
        "source_wiring_probe_ok",
        "source_wiring_probe_gap_count",
        "wiring_inventory",
        "wiring_inventory_ok",
        "wiring_inventory_gap_count",
        "ollama_health",
        "ollama_api_up",
        "ollama_server_ok",
        "ollama_chat_ready",
        "ollama_health_status",
        "ollama_health_info",
        "ollama_tags_ok",
        "ollama_chat_route_ok",
        "ollama_version",
        "ollama_version_ok",
        "ollama_version_status",
        "ollama_api_contract_status",
        "ollama_configured_model",
        "ollama_model_available",
        "ollama_model_status",
        "ollama_available_models",
        "port_ownership",
        "port_ownership_status",
        "port_ownership_issue_count",
        "backend_commands",
        "backend_command_count",
        "frontdoor_cli_status",
        "cli_http_parity",
        "layer_maturity",
        "capability_gaps_observed",
        "capability_gaps_actionable",
        "capability_gap_actionable_count",
        "capability_gap_observed_count",
        "suppress_capability_gap_signals",
        "next_leah_capability",
    }
)


def signal_ingestion_top_level_keys() -> frozenset[str]:
    keys = set(_SIGNAL_INGESTION_DERIVED_KEYS)
    keys.update(_SIGNAL_INGESTION_OBJECT_KEYS)
    for surface in WIRING_SURFACES:
        keys.update(surface.status_keys)
    return frozenset(keys)


def derive_surfaces_url(status_url: str) -> str:
    url = str(status_url or "").strip()
    if not url:
        return "http://127.0.0.1:8080/api/control/status/surfaces"
    if url.endswith("/api/control/status/surfaces"):
        return url
    if url.endswith("/api/control/status"):
        return f"{url}/surfaces"
    parsed = urlparse(url)
    path = str(parsed.path or "").rstrip("/")
    if path.endswith("/status"):
        path = f"{path}/surfaces"
    elif not path.endswith("/surfaces"):
        path = f"{path}/surfaces" if path else "/api/control/status/surfaces"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def extract_signal_ingestion_surfaces(payload: dict[str, Any]) -> dict[str, Any]:
    source = dict(payload or {})
    allowed = signal_ingestion_top_level_keys()
    surfaces: dict[str, Any] = {"ok": bool(source.get("ok", True)), "status_kind": "signal_ingestion_surfaces"}
    for key in allowed:
        if key in {"ok", "status_kind"}:
            continue
        if key not in source:
            continue
        value = source.get(key)
        if value is None:
            continue
        if isinstance(value, (dict, list, tuple, bool, int, float, str)):
            surfaces[key] = value
    return surfaces


def _local_closure_inventory_authoritative(
    merged: dict[str, Any],
    *,
    inventory_key: str,
    ok_key: str,
    gap_count_key: str,
) -> bool:
    inventory = merged.get(inventory_key)
    if not isinstance(inventory, dict):
        return False
    gap_count = int(merged.get(gap_count_key, inventory.get("gap_count", 0)) or 0)
    ok = bool(merged.get(ok_key, inventory.get("ok", False)))
    return ok and gap_count <= 0


def merge_http_supplement_into_local(local_payload: dict[str, Any], http_payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(local_payload or {})
    http = dict(http_payload or {})
    preserve_root_closure = _local_closure_inventory_authoritative(
        merged,
        inventory_key="root_closure_inventory",
        ok_key="root_closure_inventory_ok",
        gap_count_key="root_closure_inventory_gap_count",
    )
    preserve_self_repair = _local_closure_inventory_authoritative(
        merged,
        inventory_key="self_repair_closure_inventory",
        ok_key="self_repair_closure_inventory_ok",
        gap_count_key="self_repair_closure_inventory_gap_count",
    )
    for key in HTTP_SUPPLEMENT_KEYS:
        if key not in http:
            continue
        if key in LOCAL_AUTHORITATIVE_KEYS and key in merged:
            continue
        if preserve_root_closure and key.startswith("root_closure_inventory"):
            continue
        if preserve_self_repair and key.startswith("self_repair_closure_inventory"):
            continue
        merged[key] = http[key]
    maintenance = http.get("autonomy_maintenance") if isinstance(http.get("autonomy_maintenance"), dict) else {}
    local_maintenance = merged.get("autonomy_maintenance") if isinstance(merged.get("autonomy_maintenance"), dict) else {}
    if maintenance:
        merged["autonomy_maintenance"] = {**dict(maintenance), **dict(local_maintenance)}
    return merged


def release_drift_detected(release_status: Any) -> bool:
    payload = dict(release_status) if isinstance(release_status, dict) else {}
    state = str(payload.get("latest_readiness_state") or payload.get("status") or "").strip().lower()
    return "source-changed" in state or "after-build" in state


class ControlStatusSurfacesService:
    @staticmethod
    def build_surfaces_payload(full_payload: dict[str, Any]) -> dict[str, Any]:
        return extract_signal_ingestion_surfaces(full_payload)


CONTROL_STATUS_SURFACES_SERVICE = ControlStatusSurfacesService()