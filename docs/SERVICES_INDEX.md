# Services Index

Last verified: 2026-06-11

This page maps the major service clusters under `services/`. It is a practical orientation guide, not an exhaustive API reference.

## Control Plane

- `control_actions.py`, `control_auth.py`, `control_assets.py`, `control_status.py`, `control_status_cache.py`, `control_telemetry.py`
- `control_login_frontdoor.py`, `control_work_trees.py`, `control_pipelines.py`
- owns operator-console payloads, auth gates, UI assets, work-tree views, data-lane controls, and status caching

## HTTP Runtime

- `nova_http_frontdoor.py`, `nova_http_transport.py`, `nova_http_get_routes.py`, `nova_http_post_routes.py`, `nova_http_post_dispatch.py`
- `nova_http_chat_runtime.py`, `nova_http_turn_finalization.py`
- `nova_http_request_binding.py`, `nova_http_responses.py`, `nova_http_policy_search.py`, `nova_http_generated_work.py`
- `nova_http_pipeline_control.py`, `nova_http_generated_work.py`
- `leah_frontdoor.py`: Leah assistant front door — separate chat UI served at `/leah`
- `session_admin.py`: session administration helpers
- `operator_control.py`: operator-facing runtime control actions
- owns HTTP request binding, route dispatch, response emission, chat-turn runtime/finalization, and the Leah frontend while `nova_http.py` remains the stable transport wrapper

## Decision And Reply Behavior

- `decision_pipeline.py`, `fulfillment_flow.py`, `nova_fulfillment_routing.py`
- `nova_planner_contract.py`, `nova_reply_context_contract.py`, `nova_reply_runtime.py`, `nova_reply_sequence.py`
- `nova_routing_support.py`, `nova_routing_helpers.py`, `nova_turn_intent_trace.py`
- `nova_grounded_self_report.py`, `nova_self_evidence_reply.py`, `nova_fallback_flow.py`, `nova_ollama_chat.py`
- owns turn evidence, planner contracts, grounded internal self-reports, fallback control, reply context, and reply shape

## Supervisor And Routing Rules

- `supervisor_authority.py`, `supervisor_registry.py`, `supervisor_runtime.py`, `supervisor_patterns.py`, `supervisor_probes.py`
- owns deterministic rule ownership and the rule-family arbitration surface

## Memory And Identity

- `memory_adapter.py`, `memory_routing.py`, `identity_memory.py`
- `memory_bootstrap_contracts.py`, `memory_bootstrap_judgment.py`, `memory_bootstrap_origin.py`, `memory_identity_bootstrap.py`, `memory_health.py`
- `nova_memory_events.py`, `nova_memory_learning.py`, `chat_identity.py`, `nova_operational_identity.py`
- owns scoped memory access, learning events, identity bootstrap evidence, and operational identity surfaces

## Tools, Research, And Data Lanes

- `tool_registry.py`, `tool_execution.py`, `tool_console.py`, `nova_tool_dispatch.py`, `nova_tool_policy.py`
- `os_capability_registry.py`, `os_script_controller.py`, `os_capability_operator_outbox.py`, `operator_outbox.py`
- `nova_web_tools.py`, `nova_web_contracts.py`, `web_research_session.py`, `nova_search_endpoint.py`
- `data_pipeline_registry.py`, `control_pipelines.py`, `nova_http_pipeline_control.py`, `nova_pipeline_tools.py`, `pipeline_privileged_bridge.py`
- owns tool registration/execution, OS capability contracts, operator notices, web research sessions, and governed data-lane access

## Autonomy And Orchestration

- `autonomy_orchestrator.py`: central autonomous decision-making — selects maintenance actions, manages orchestrator ledger, drives work-tree execution cycles
- `autonomy_orchestrator_ledger.py`: persistent ledger for orchestrator decisions
- `autonomy_execution_gate.py`: execution gate that enforces autonomy policy before autonomous actions run
- `subconscious_work_tree_triage.py`: routes subconscious signals into work-tree branches
- `subconscious_review_authority.py`: authority checks for subconscious branch reviews
- `subconscious_review_judgment.py`: judgment layer for subconscious review outcomes
- `subconscious_control.py`, `subconscious_runtime.py`, `subconscious_reporting.py`
- owns autonomous task orchestration, execution gating, and subconscious signal routing into work-tree pressure

## Regression And Test Governance

- `regression_lanes.py`: defines unit/behavior/integration lane membership for the full regression suite
- `regression_profile_inventory.py`: tracks test-profile state, drift detection, gap detection, and unclassified-test detection
- `validation_artifact_truth.py`: release-gate service that tracks validation artifact truth including failure and LLM-unavailable counts
- `test_session_control.py`, `test_session_definitions.py`: test-session orchestration and definition contracts
- owns regression lane membership, profile drift/gap detection, and release-gate validation truth

## Runtime Health And Maintenance

- `runtime_status.py`, `runtime_process_state.py`, `runtime_timeline.py`, `runtime_control.py`, `runtime_heartbeat.py`, `runtime_artifacts.py`, `runtime_analytics.py`
- `runtime_restart_provenance.py`: tracks restart lineage and records restart intent with source attribution
- `core_health_brief.py`, `core_steward.py`, `core_thinning.py`, `core_seam_guard.py`
- `schedule_registry.py`, `nova_scheduler.py`: scheduler registry and APScheduler lazy wrapper for timed maintenance tasks
- `port_ownership.py`: tracks port ownership across processes for conflict detection
- `storage_watch.py`: watches runtime storage sizes and patch/kidney snapshot counts
- owns runtime truth, health summaries, maintenance pressure, core-thinning work, restart provenance, scheduling, and status projection of operator-outbox pressure

## CLI And Voice

- `nova_cli_loop.py`, `nova_cli_delivery.py`, `nova_cli_sequence.py`, `runtime_console_frontdoor.py`, `voice_interaction.py`, `nova_voice_runtime.py`
- owns CLI loop behavior, command delivery, voice interaction, and local runtime speech paths

## Patch And Release Support

- `nova_patching.py`, `patch_control.py`, `policy_control.py`, `policy_manager.py`, `release_status.py`, `release_validation.py`
- `release_clean.py`: release-clean lane validation
- `release_promotion_judgment.py`: judgment layer for release promotion decisions
- `release_validation_contracts.py`: release-validation contract constants
- `installer_validation.py`: Windows installer artifact validation
- `source_root_judgment.py`: source-root identity and operator-notice for source-root drift
- `nova_update_now.py`: operator-triggered update-now flow and pending-update state
- owns patch governance, policy mutation flows, extracted-package and installer validation, release/readiness status, and promotion judgment

## Temporal And Scheduling

- `nova_temporal_service.py`: temporal pressure scoring — converts calendar events into scored pressure signals with proximity, importance, and confidence dimensions
- `nova_calendar_ingestion.py`: ICS parser for local operator calendar files with TZID handling
- `nova_scheduler.py`: APScheduler lazy wrapper used by the maintenance feed
- `schedule_registry.py`: runtime schedule registry for recurring maintenance tasks
- owns temporal event ingestion, pressure scoring, and maintenance feed scheduling

## Work Tree And Signal Ingestion

- `work_tree_signal_ingestion.py` (root): central signal bus — converts status payloads, autonomy events, and temporal pressure into work-tree branches and signals
- `work_tree_seeding.py`: seeding logic for new work-tree branch creation from signals
- `work_tree_decision_adapter.py`: adapter that maps work-tree state into orchestrator decision inputs
- `nova_wiring_inventory.py`: wiring inventory and closure analysis — detects which surfaces, signals, tools, and advisory actions are connected end-to-end
- `nova_root_inventory.py`: root inventory for tracking source-root signal coverage
- `nova_inventory_labels.py`: shared label constants for inventory surfaces
- owns signal ingestion, work-tree seeding, decision adaptation, and wiring closure verification
