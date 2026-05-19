# Services Index

Last verified: 2026-05-18

This page maps the major service clusters under `services/`. It is a practical orientation guide, not an exhaustive API reference.

## Control Plane

- `control_actions.py`, `control_auth.py`, `control_assets.py`, `control_status.py`, `control_status_cache.py`, `control_telemetry.py`
- `control_login_frontdoor.py`, `control_work_trees.py`, `control_pipelines.py`
- owns operator-console payloads, auth gates, UI assets, work-tree views, data-lane controls, and status caching

## HTTP Runtime

- `nova_http_frontdoor.py`, `nova_http_transport.py`, `nova_http_get_routes.py`, `nova_http_post_routes.py`, `nova_http_post_dispatch.py`
- `nova_http_chat_runtime.py`, `nova_http_turn_finalization.py`
- `nova_http_request_binding.py`, `nova_http_responses.py`, `nova_http_routing.py`
- owns HTTP request binding, route dispatch, response emission, and chat-turn runtime/finalization while `nova_http.py` remains the stable transport wrapper

## Decision And Reply Behavior

- `decision_pipeline.py`, `fulfillment_flow.py`, `nova_fulfillment_routing.py`, `nova_query_classifiers.py`
- `nova_planner_contract.py`, `nova_reply_contracts.py`, `nova_reply_deterministic.py`, `nova_reply_guards.py`, `nova_reply_runtime.py`, `nova_reply_sanitizer.py`, `nova_reply_sequence.py`, `nova_turn_heuristics.py`, `nova_turn_outcomes.py`
- `nova_grounded_self_report.py`
- owns structured outcomes, deterministic reply contracts, grounded internal self-reports, fallback control, and reply shape

## Supervisor And Routing Rules

- `supervisor_authority.py`, `supervisor_registry.py`, `supervisor_runtime.py`
- `supervisor_intent_rules.py`, `supervisor_identity_rules.py`, `supervisor_reflective_rules.py`, `supervisor_routing_rules.py`, `supervisor_patterns.py`, `supervisor_probes.py`
- owns deterministic rule ownership and the rule-family arbitration surface

## Memory And Identity

- `memory_adapter.py`, `memory_routing.py`, `identity_memory.py`
- `nova_memory_events.py`, `nova_memory_learning.py`
- `chat_identity.py`, `nova_identity_answers.py`, `nova_identity_history.py`, `nova_identity_preferences.py`
- owns scoped memory access, learning events, identity answers, and identity/history followups

## Tools, Research, And Data Lanes

- `tool_registry.py`, `tool_execution.py`, `tool_console.py`, `nova_tool_dispatch.py`, `nova_tool_policy.py`
- `os_capability_registry.py`, `os_script_controller.py`, `os_capability_operator_outbox.py`, `operator_outbox.py`
- `nova_web_tools.py`, `web_research_session.py`, `nova_research_contracts.py`, `nova_search_endpoint.py`
- `data_pipeline_registry.py`, `control_pipelines.py`, `nova_http_pipeline_control.py`, `nova_pipeline_tools.py`, `pipeline_privileged_bridge.py`
- owns tool registration/execution, OS capability contracts, operator notices, web research sessions, and governed data-lane access

## Runtime Health And Maintenance

- `runtime_status.py`, `runtime_process_state.py`, `runtime_timeline.py`, `runtime_control.py`, `runtime_heartbeat.py`, `runtime_artifacts.py`, `runtime_analytics.py`
- `core_health_brief.py`, `core_steward.py`, `core_thinning.py`, `core_seam_guard.py`
- `subconscious_control.py`, `subconscious_runtime.py`, `subconscious_reporting.py`, `subconscious_review_authority.py`, `subconscious_work_tree_triage.py`
- owns runtime truth, health summaries, maintenance pressure, core-thinning work, subconscious/reporting surfaces, and status projection of operator-outbox pressure

## CLI And Voice

- `nova_cli_loop.py`, `nova_cli_delivery.py`, `nova_cli_sequence.py`, `nova_command_handlers.py`, `voice_interaction.py`, `nova_voice_runtime.py`
- owns CLI loop behavior, command delivery, voice interaction, and local runtime speech paths

## Patch And Release Support

- `nova_patching.py`, `patch_control.py`, `policy_control.py`, `policy_manager.py`, `release_status.py`, `release_validation.py`
- owns patch governance, policy mutation flows, extracted-package validation, and release/readiness status services
