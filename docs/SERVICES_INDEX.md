# Services Index

Last generated from code: 2026-08-16

This is the exhaustive service-module index. Architectural ownership is described in `SYSTEM_MAP.md`; function-level detail is in `FUNCTION_INDEX.md`.

**Check `docs/NOVA_LEDGER.md` drift alerts before relying on line counts or function lists — this index may lag recent changes.**

## Ownership Domains

- Runtime and process truth: `runtime_*`, `control_status*`, `port_ownership`, `ollama_health`, `server_side_runtime`.
- HTTP and operator surfaces: `nova_http_*`, `control_*`, `operator_*`, `leah_*`, `session_*`, `chat_identity`.
- Conversation and reply behavior: `nova_routing_*`, `nova_planner_contract`, `nova_reply_*`, `nova_fallback_flow`, `fulfillment_flow`, `supervisor_*`.
- Memory and identity: `memory_*`, `identity_memory`, `nova_memory_*`, `nova_operational_identity`.
- Tools and policy: `tool_*`, `nova_tool_*`, `policy_*`, `os_*`, `evidence_validity`.
- Autonomy and feedback: `autonomy_*`, `nova_mission*`, `work_tree_*`, `subconscious_*`, `core_*`, `layer_maturity_policy`.
- Patch, codegen, test, and release: `nova_patching`, `patch_*`, `codegen_*`, `test_session_*`, `regression_*`, `validation_*`, `release_*`, `installer_validation`.
- Data and data connector: `data_pipeline_registry`, `control_pipelines`, `pipeline_privileged_bridge`, and `services/edfi/*`.
- Backpack Host: `services/backpack_host/*` — discovery, install, grant enforcement, uninstall sanitizer, residue scan.
- Nova Shell: `services/nova_shell/*` — operator authentication, TOTP, role management, session trust.
- Decision Judge: `decision_proposal_judge` — pre-execution claim evaluation with judge reports and episodes.
- Solution Trail: `solution_trail` — solution path tracking and breadcrumb recording.
- Media, time, retrieval, and environment: `nova_voice_runtime`, `nova_vision_runtime`, `nova_temporal_service`, `nova_calendar_ingestion`, `nova_web_*`, `nova_location_weather`, `sock_service`.
- Inventory and diagnosis: `nova_wiring_inventory`, `nova_root_inventory`, `end_to_end_wiring`, `source_root_judgment`, `storage_watch`, `ops_journal`, `self_scan_rings`.

## Core Services

| Module | Lines | Public classes/functions | Singleton | Description |
|---|---:|---|---|---|
| `services/autonomy_execution_gate.py` | 262 | AutonomyExecutionGateService | AUTONOMY_EXECUTION_GATE_SERVICE | - |
| `services/autonomy_orchestrator.py` | 1586 | AutonomyOrchestratorService | AUTONOMY_ORCHESTRATOR_SERVICE | - |
| `services/autonomy_orchestrator_ledger.py` | 214 | AutonomyOrchestratorLedgerService | AUTONOMY_ORCHESTRATOR_LEDGER_SERVICE | - |
| `services/behavior_metrics.py` | 67 | BehaviorMetricsStore | - | - |
| `services/capabilities_gap_detector.py` | 128 | detect_capability_gaps, enhance_status_with_capability_gaps | CAPABILITY_GAP_DETECTOR_SERVICE | Capability gap detection service. |
| `services/capability_finish_ownership.py` | 171 | ownership_from_roadmap, classify_capability, partition_capability_gaps, nova_code_gap_names | NOVA_CODE_FINISHERS | Ownership of unfinished capability work: who must finish it. |
| `services/chat_identity.py` | 198 | ChatIdentityService | CHAT_IDENTITY_SERVICE | - |
| `services/codegen_memory_recorder.py` | 348 | record_generated_pattern, lookup_patterns_by_capability, lookup_patterns_by_spec, build_memory_injection_context, CodegenMemoryRecorderService | CODEGEN_MEMORY_RECORDER_SERVICE | Codegen Self-Extension Memory Service |
| `services/codegen_patch_bridge.py` | 318 | validate_codegen_preview, bridge_codegen_to_patch, materialize_codegen_patch_zip, format_bridge_summary | CODEGEN_PATCH_BRIDGE_SERVICE | Bridge from codegen preview payloads to formal patch artifacts. |
| `services/control_actions.py` | 43 | ControlActionsService | CONTROL_ACTIONS_SERVICE | - |
| `services/control_assets.py` | 36 | ControlAssetsService | CONTROL_ASSETS_SERVICE | - |
| `services/control_auth.py` | 253 | ControlAuthService | CONTROL_AUTH_SERVICE | - |
| `services/control_backpacks.py` | 894 | ControlBackpacksService | CONTROL_BACKPACKS_SERVICE | - |
| `services/control_login_frontdoor.py` | 89 | ControlLoginFrontdoorService | CONTROL_LOGIN_FRONTDOOR_SERVICE | - |
| `services/control_pipelines.py` | 549 | ControlPipelinesService | CONTROL_PIPELINES_SERVICE | - |
| `services/control_status.py` | 1686 |  | - | (syntax error — could not parse) |
| `services/control_status_cache.py` | 34 | ControlStatusCacheService | CONTROL_STATUS_CACHE_SERVICE | - |
| `services/control_status_surfaces.py` | 507 | signal_ingestion_top_level_keys, derive_surfaces_url, extract_signal_ingestion_surfaces, merge_http_supplement_into_local, release_drift_detected, ControlStatusSurfacesService | CONTROL_STATUS_SURFACES_SERVICE | - |
| `services/control_telemetry.py` | 724 | ControlTelemetryService | - | - |
| `services/control_work_trees.py` | 231 | ControlWorkTreesService | CONTROL_WORK_TREES_SERVICE | - |
| `services/core_health_brief.py` | 412 | build_core_health_brief, write_core_health_brief, render_core_health_brief, feed_core_health_brief_to_work_tree | - | - |
| `services/core_seam_guard.py` | 128 | CoreSeamGuardService | CORE_SEAM_GUARD_SERVICE | - |
| `services/core_steward.py` | 345 | build_core_steward_payload, build_core_steward_gates, render_core_steward | - | - |
| `services/core_steward_contracts.py` | 4 |  | - | - |
| `services/core_thinning.py` | 1411 | is_http_extract_stage_block, stamp_core_thinning_task_satisfaction, build_core_thinning_brief, build_core_thinning_owner_verdict, render_core_thinning_brief, execute_core_thinning_order, feed_core_thinning_brief_to_work_tree | - | - |
| `services/data_pipeline_registry.py` | 188 | build_pipeline_registry, list_pipeline_summaries, pipeline_worker_summary, get_pipeline_status, get_pipeline_schema_probe, search_pipeline_vendor_dictionary, plan_pipeline_report, preview_pipeline_query, +2 more | - | - |
| `services/decision_pipeline.py` | 120 | make_trace_entry, RegisteredStage, StageRegistry, run_registered_stages | - | - |
| `services/decision_proposal_judge.py` | 953 | derive_claim_fields, build_decision_proposal, judge_proposal, should_block_execution, compute_judge_was_useful, attach_outcome, build_decision_episode, evaluate_recommendation_packet, +2 more | - | Decision proposal + rule-based Judge (observation-first). |
| `services/end_to_end_wiring.py` | 764 | run_end_to_end_wiring_check | - | - |
| `services/evidence_validity.py` | 99 | invalid_tool_result, evidence_result_valid | - | - |
| `services/finish_areas_inventory.py` | 55 | build_finish_areas_inventory | - | Aggregate unfinished finish-areas (not pending thrash tasks). |
| `services/frontdoor_cli_parity.py` | 184 | build_frontdoor_cli_surfaces, FrontdoorCliParityService | FRONTDOOR_CLI_PARITY_SERVICE | - |
| `services/fulfillment_flow.py` | 247 | FulfillmentFlowService | - | - |
| `services/generated_work_queue_snapshot.py` | 35 | generated_work_queue_payload | - | - |
| `services/governance_chain.py` | 204 | release_rebuild_success, release_rebuild_tool_payload, governed_patch_apply, run_codegen_to_patch_chain | - | - |
| `services/identity_memory.py` | 54 | IdentityMemoryService | - | IdentityMemoryService - Encapsulates identity memory validity. |
| `services/installer_validation.py` | 279 | run_installer_validation, render_installer_validation_report | - | - |
| `services/layer_maturity_policy.py` | 390 | normalize_layer_policy, layer_for_capability, evaluate_core_gate, next_leah_capability_in_sequence, capability_action_block_reason, capability_action_allowed, filter_actionable_capability_gaps, build_layer_maturity_summary, +4 more | LAYER_MATURITY_POLICY_SERVICE | - |
| `services/leah_conversation_continuity.py` | 144 | LeahConversationContinuityStore, capability_registration | - | - |
| `services/leah_fast_chat.py` | 43 | leah_fast_chat_enabled, leah_fast_chat_skips_spine, load_leah_fast_chat_from_core, load_leah_fast_chat_skips_spine_from_core | - | - |
| `services/leah_frontdoor.py` | 200 | LeahFrontdoorService | - | - |
| `services/leah_memory_recall.py` | 193 | LeahMemoryRecallService, capability_registration | - | - |
| `services/leah_nova_pulse.py` | 159 | build_leah_nova_pulse, compose_nova_outreach, statement_from_nova_life | - | - |
| `services/memory_adapter.py` | 213 | MemoryAdapterService | - | - |
| `services/memory_bootstrap_contracts.py` | 3 |  | - | - |
| `services/memory_bootstrap_judgment.py` | 166 | build_memory_bootstrap_judgment, render_memory_bootstrap_judgment | - | - |
| `services/memory_bootstrap_origin.py` | 313 | default_pending_origin_contract, write_origin_contract, confirm_origin_contract, load_origin_contract | - | - |
| `services/memory_health.py` | 424 | build_memory_health_payload | - | - |
| `services/memory_identity_bootstrap.py` | 189 | build_identity_bootstrap_preview, apply_identity_bootstrap, render_identity_bootstrap_result | - | - |
| `services/memory_production.py` | 258 | build_memory_recall_plan, build_memory_read_plan, parse_correction, extract_color_preferences_from_text, MemoryLearningOutcome, apply_user_memory_learning | - | - |
| `services/memory_retention.py` | 289 | parse_retention_policy, evaluate_contamination, apply_memory_hygiene, render_memory_hygiene_result | - | - |
| `services/memory_routing.py` | 131 | MemoryRecallPlan, MemoryRoutingService | MEMORY_ROUTING_SERVICE | - |
| `services/nova_action_ledger.py` | 220 | start_action_ledger_record, write_action_ledger_record, finalize_action_ledger_record, finalize_action_ledger_record_from_runtime | - | - |
| `services/nova_action_ledger_helpers.py` | 336 | action_ledger_add_step, action_ledger_route_summary, recent_action_ledger_records, latest_action_ledger_record, action_history_reply, record_completed_tool_execution, record_requested_tool_clarification, detect_repeated_tool_intent_without_execution, +5 more | - | - |
| `services/nova_calendar_ingestion.py` | 516 | load_sidecar_enrichment, save_sidecar_enrichment, serialize_events_to_ics, parse_ics_text, parse_ics_file, normalize_calendar_event, read_calendar_events, write_calendar_event, +1 more | - | - |
| `services/nova_cli_delivery.py` | 94 | apply_cli_outcome_to_ledger, apply_cli_handled_outcome, emit_cli_reply_outcome | - | - |
| `services/nova_cli_loop.py` | 372 | run_loop | - | - |
| `services/nova_cli_sequence.py` | 127 | execute_cli_sequence, normalize_sequence_reply, apply_sequence_result | - | - |
| `services/nova_cli_session.py` | 43 | cli_session_store_path, load_cli_session_turns, persist_cli_session_turns | - | - |
| `services/nova_context_assembly.py` | 218 | render_chat_context, render_session_state_context, build_learning_context_details, build_fallback_context_details | - | - |
| `services/nova_control_action_dispatcher.py` | 719 | autonomy_advisory_action_catalog, autonomy_advisory_action_types, is_autonomy_advisory_action, NovaControlActionDispatcher | NOVA_CONTROL_ACTION_DISPATCHER | - |
| `services/nova_fallback_flow.py` | 360 | build_fallback_context, prepare_fallback_flow, finalize_llm_fallback_reply | - | - |
| `services/nova_fulfillment_routing.py` | 60 | evaluate_fulfillment_route_viability | - | - |
| `services/nova_grounded_self_report.py` | 470 | TroubleItem, NovaGroundedSelfReportService | GROUNDED_SELF_REPORT_SERVICE | Ground live self-report replies in runtime status and Work Tree truth. |
| `services/nova_http_backpack_control.py` | 40 | NovaHttpBackpackControlService | HTTP_BACKPACK_CONTROL_SERVICE | - |
| `services/nova_http_chat_runtime.py` | 277 | NovaHttpChatRuntimeService | HTTP_CHAT_RUNTIME_SERVICE | - |
| `services/nova_http_control_surface.py` | 111 | NovaHttpControlSurfaceService | HTTP_CONTROL_SURFACE_SERVICE | - |
| `services/nova_http_frontdoor.py` | 193 | NovaHttpFrontdoorService | NOVA_HTTP_FRONTDOOR_SERVICE | - |
| `services/nova_http_generated_work.py` | 90 | NovaHttpGeneratedWorkService | HTTP_GENERATED_WORK_SERVICE | - |
| `services/nova_http_get_routes.py` | 289 | NovaHttpGetRoutesService | HTTP_GET_ROUTES_SERVICE | - |
| `services/nova_http_pipeline_control.py` | 92 | NovaHttpPipelineControlService | HTTP_PIPELINE_CONTROL_SERVICE | - |
| `services/nova_http_policy_search.py` | 86 | NovaHttpPolicySearchService | HTTP_POLICY_SEARCH_SERVICE | - |
| `services/nova_http_post_dispatch.py` | 87 | NovaHttpPostDispatchService | HTTP_POST_DISPATCH_SERVICE | - |
| `services/nova_http_post_routes.py` | 94 | NovaHttpPostRoutesService | HTTP_POST_ROUTES_SERVICE | - |
| `services/nova_http_request_binding.py` | 212 | NovaHttpRequestBindingService | HTTP_REQUEST_BINDING_SERVICE | - |
| `services/nova_http_responses.py` | 125 | NovaHttpResponsesService | HTTP_RESPONSE_SERVICE | - |
| `services/nova_http_transport.py` | 61 | NovaHttpTransportService | HTTP_TRANSPORT_SERVICE | - |
| `services/nova_http_turn_finalization.py` | 225 | session_reply_for_context, NovaHttpTurnFinalizationService | HTTP_TURN_FINALIZATION_SERVICE | - |
| `services/nova_intent_understanding.py` | 343 | classify_turn_intent, select_response_strategy, self_status_belongs_to_turn, record_intent_outcome | - | nova_intent_understanding.py |
| `services/nova_inventory_labels.py` | 33 | shared_inventory_label | - | - |
| `services/nova_knowledge_packs.py` | 313 |  | - | (syntax error — could not parse) |
| `services/nova_live_closure.py` | 256 | build_live_closure_inventory_payload | - | - |
| `services/nova_location_weather.py` | 589 | weather_source_host, weather_unavailable_message, weather_response_style, format_weather_output, runtime_device_backend_provider, coerce_bounded_float, coerce_optional_metric, normalize_source_timestamp, +18 more | - | - |
| `services/nova_memory_events.py` | 56 | append_memory_event, record_memory_event | - | - |
| `services/nova_memory_learning.py` | 1125 | mem_stats_payload, mem_add, mem_recall, prefix_from_earlier_memory, normalize_recent_learning_item, mem_get_recent_learned, mem_stats, mem_audit, +21 more | - | - |
| `services/nova_mission.py` | 920 | NovaMissionService | NOVA_MISSION_SERVICE | - |
| `services/nova_mission_owner_verdicts.py` | 657 | build_mission_truth_gate | - | - |
| `services/nova_ollama_chat.py` | 175 | ollama_chat | - | - |
| `services/nova_operational_identity.py` | 46 | operational_identity_context_for_prompt | - | - |
| `services/nova_patching.py` | 1597 | snapshot_should_skip_relpath, parse_scoped_patch_payload, execute_scoped_patch_payload, log_patch, read_patch_revision, write_patch_revision, snapshot_meta_path, write_snapshot_meta, +37 more | - | - |
| `services/nova_pipeline_tools.py` | 439 | parse_pipeline_params, parse_pipeline_command, render_pipeline_help, render_pipeline_list, render_pipeline_status, render_pipeline_schema, render_pipeline_dictionary_search, render_pipeline_report_plan, +2 more | - | - |
| `services/nova_planner_contract.py` | 745 | build_planner_config, merge_route_evidence, maybe_handle_planner_sequence | - | - |
| `services/nova_pulse.py` | 374 | build_pulse_payload, write_pulse_snapshot, render_nova_pulse, tool_nova_pulse | - | - |
| `services/nova_reflection_health.py` | 384 | detect_repeated_tool_intent_without_execution, top_repeated_correction_class, count_routing_overrides_recently, record_used_routing_override, routing_stable_recently, sample_intents_last, append_self_reflection, append_health_snapshot, +4 more | - | - |
| `services/nova_reply_context_contract.py` | 4 |  | - | - |
| `services/nova_reply_runtime.py` | 39 | apply_reply_runtime_effects | - | - |
| `services/nova_reply_sequence.py` | 453 | execute_reply_sequence_from_runtime, execute_http_reply_sequence_from_runtime, execute_reply_sequence | - | - |
| `services/nova_root_inventory.py` | 702 | SourceRoot, source_root_ids, build_source_root_inventory_payload | - | - |
| `services/nova_route_probing.py` | 127 | evaluate_deterministic_route_viability, build_probe_turn_routes | - | - |
| `services/nova_routing_helpers.py` | 62 | strip_invocation_prefix, resolve_research_provider | - | - |
| `services/nova_routing_support.py` | 492 | intent_trace_preview, supervisor_result_has_route, supervisor_candidate_trace, supervisor_phase_record, build_routing_decision, finalize_routing_decision, llm_classify_routing_intent | - | - |
| `services/nova_runtime_context.py` | 131 | set_active_user, get_active_user, resolve_base_dir, runtime_scope_name, resolve_runtime_dir, resolve_python_executable | - | - |
| `services/nova_runtime_hooks.py` | 33 | resolve_runtime_hooks | - | - |
| `services/nova_scheduler.py` | 80 | NovaSchedulerService | - | - |
| `services/nova_search_endpoint.py` | 138 | normalize_search_endpoint, search_endpoint_candidates, is_local_search_endpoint, stable_probe_error, probe_search_endpoint | - | - |
| `services/nova_self_evidence_reply.py` | 183 | turn_asks_nova_self, maybe_build_self_evidence_reply | - | - |
| `services/nova_self_status.py` | 294 | read_recent_ops_events, build_repo_change_snapshot, build_self_status_payload, render_self_status | - | - |
| `services/nova_service_builders.py` | 34 | build_policy_manager, build_identity_memory_service, build_fulfillment_flow_service | - | - |
| `services/nova_session_state.py` | 33 | apply_reply_session_updates | - | - |
| `services/nova_setup_wizard.py` | 1674 | acquire_setup_singleton, release_setup_singleton, refresh_windows_path, known_python312_commands, ensure_user_path_entry, load_policy_models, required_ollama_models, parse_python_version, +25 more | - | - |
| `services/nova_shell_control_bridge.py` | 259 | ShellLoginResult, ShellSessionInfo, shell_is_active, shell_login, shell_verify_session, shell_logout, shell_status | - | nova_shell_control_bridge.py ----------------------------- Bridge between control_auth.py (nova_http.py's auth layer) and Nova Shell. |
| `services/nova_temporal_service.py` | 318 | TemporalEvent, TemporalPressure, NovaTemporalService, build_temporal_pressure | - | - |
| `services/nova_tool_dispatch.py` | 214 | execute_planned_action, execute_planned_action_from_runtime | - | - |
| `services/nova_tool_policy.py` | 179 | research_handlers, execute_research_action, patch_handlers, execute_patch_action, web_allowlist_message, web_fetch | - | - |
| `services/nova_turn_contract.py` | 196 | TurnRequest, normalize_channel, normalize_input_source, default_work_tree_seed_source, bind_turn_request, maybe_run_attachment_vision_turn, execute_conversation_turn | - | - |
| `services/nova_turn_intent_trace.py` | 241 | build_turn_intent_evidence_packet, render_turn_intent_evidence_packet, attach_turn_intent_evidence_packet | - | - |
| `services/nova_update_now.py` | 152 | read_update_now_pending, write_update_now_pending, clear_update_now_pending, update_now_pending_payload, build_update_now_token, extract_preview_status, extract_preview_zip, tool_update_now, +2 more | - | - |
| `services/nova_vision_runtime.py` | 148 | vision_model_from_policy, vision_model_from_policy_file, describe_image_file, vision_status_payload | - | - |
| `services/nova_voice_runtime.py` | 541 | ensure_voice_deps, voice_status_payload, record_seconds, transcribe, SubprocessTTS, speak_chunked | - | - |
| `services/nova_web_contracts.py` | 3 |  | - | - |
| `services/nova_web_tools.py` | 1173 | scan_candidate_urls_for_query, extract_urls, decode_search_href, extract_text_from_path, extract_text_from_html_content, extract_same_host_links, expand_research_terms, score_research_hit, +16 more | - | - |
| `services/nova_wiring_inventory.py` | 1371 | WiringSurface, build_source_wiring_probe_payload, build_wiring_inventory_payload, build_root_closure_inventory_payload, build_self_repair_closure_inventory_payload, wiring_surface_ids | - | - |
| `services/ollama_health.py` | 195 | build_ollama_health_payload | - | - |
| `services/operator_control.py` | 328 | OperatorControlService | OPERATOR_CONTROL_SERVICE | - |
| `services/operator_outbox.py` | 1494 | OperatorOutboxService | OPERATOR_OUTBOX_SERVICE | - |
| `services/ops_journal.py` | 123 | append_ops_event | - | - |
| `services/os_capability_operator_outbox.py` | 177 | build_os_capability_notice, publish_os_capability_notice | - | - |
| `services/os_capability_registry.py` | 583 | OsCapabilityRegistryService | OS_CAPABILITY_REGISTRY_SERVICE | - |
| `services/os_script_controller.py` | 678 | OsScriptControllerService | OS_SCRIPT_CONTROLLER_SERVICE | - |
| `services/patch_control.py` | 375 | PatchControlService | PATCH_CONTROL_SERVICE | - |
| `services/patch_promotion_memory.py` | 234 | extract_codegen_content_from_patch_zip, record_patch_promotion_to_memory, inject_memory_context_into_codegen_prompt, PatchPromotionMemoryService | PATCH_PROMOTION_MEMORY_SERVICE | Patch Promotion Memory Integration |
| `services/pipeline_privileged_bridge.py` | 135 | queue_privileged_pipeline_query, wait_for_privileged_pipeline_query, run_privileged_pipeline_query, unwrap_privileged_pipeline_response, run_governed_pipeline_query | - | - |
| `services/pipeline_worker_supervision.py` | 1118 | worker_heartbeat_path, worker_lease_path, worker_spawn_error_log_path, pid_alive, read_worker_lease, write_worker_lease, release_worker_lease, acquire_worker_lease, +9 more | - | - |
| `services/policy_control.py` | 187 | PolicyControlService | POLICY_CONTROL_SERVICE | - |
| `services/policy_manager.py` | 758 | PolicyManager | - | - |
| `services/port_ownership.py` | 164 | PortOwnershipService | PORT_OWNERSHIP_SERVICE | - |
| `services/probe_bootstrap.py` | 45 | validation_runtime_dir, apply_validation_probe_env, restore_probe_env | - | Validation-runtime bootstrap for operator probes. |
| `services/recurring_finding_lifecycle.py` | 439 | fingerprint_from_parts, read_task_state, finding_key_from_meta, finding_version, task_finding_key, task_fingerprint, initial_task_meta, stamp_satisfaction, +14 more | - | - |
| `services/regression_evidence.py` | 134 | regression_outcome_label, regression_outcome_failed, regression_outcome_passed, regression_evidence_stale, regression_failure_is_lock_contention, regression_failure_active, regression_tail_from_payload, apply_regression_status_payload | - | - |
| `services/regression_lanes.py` | 307 |  | - | - |
| `services/regression_profile_inventory.py` | 247 | build_regression_profile_inventory_payload | REGRESSION_PROFILE_INVENTORY_SERVICE | - |
| `services/release_clean.py` | 324 | run_release_clean | - | - |
| `services/release_promotion_judgment.py` | 313 | release_validation_record_payload, build_release_promotion_judgment, render_release_promotion_judgment | - | - |
| `services/release_runtime_truth.py` | 132 | running_build_identity, enrich_release_status, build_release_runtime_truth_summary, release_drift_suppresses_closure_signals, evaluate_http_model_runtime_probe, ReleaseRuntimeTruthService | RELEASE_RUNTIME_TRUTH_SERVICE | - |
| `services/release_status.py` | 484 | ReleaseStatusService | RELEASE_STATUS_SERVICE | - |
| `services/release_validation.py` | 831 | classify_release_validation_failures, run_release_validation, render_release_validation_report, record_release_validation_outcome, render_release_outcome_recording | - | - |
| `services/release_validation_contracts.py` | 3 |  | - | - |
| `services/runtime_analytics.py` | 349 | RuntimeAnalyticsService | RUNTIME_ANALYTICS_SERVICE | - |
| `services/runtime_artifacts.py` | 250 | RuntimeArtifactsService | RUNTIME_ARTIFACTS_SERVICE | - |
| `services/runtime_console_frontdoor.py` | 391 | RuntimeConsoleFrontdoorService | RUNTIME_CONSOLE_FRONTDOOR_SERVICE | - |
| `services/runtime_control.py` | 818 | RuntimeControlService | RUNTIME_CONTROL_SERVICE | - |
| `services/runtime_heartbeat.py` | 146 | heartbeat_status_path, heartbeat_log_path, read_heartbeat_status, heartbeat_write_once, start_heartbeat | - | - |
| `services/runtime_process_state.py` | 245 | RuntimeProcessStateService | RUNTIME_PROCESS_STATE_SERVICE | - |
| `services/runtime_restart_provenance.py` | 112 | RuntimeRestartProvenanceService | RUNTIME_RESTART_PROVENANCE_SERVICE | - |
| `services/runtime_status.py` | 367 | RuntimeStatusService | RUNTIME_STATUS_SERVICE | - |
| `services/runtime_timeline.py` | 328 | RuntimeTimelineService | RUNTIME_TIMELINE_SERVICE | - |
| `services/schedule_registry.py` | 231 | ScheduledTask, get_task, get_schedule_status | SCHEDULE_REGISTRY | Central registry of all scheduled background tasks in Nova. |
| `services/self_scan_rings.py` | 321 | scan_nova_doc_coverage, resolve_probe_context, run_ring1_map_integrity, run_ring2_contract_integrity, assess_stem_climbability, run_ring3_climb_integrity, run_self_scan_rings | - | Self-scan rings: map (1), contract (2), climb (3) — weave, not a second engine. |
| `services/server_side_runtime.py` | 148 | ServerSideRuntimeService | SERVER_SIDE_RUNTIME_SERVICE | - |
| `services/session_admin.py` | 108 | SessionAdminService | SESSION_ADMIN_SERVICE | - |
| `services/session_state.py` | 201 | SubconsciousState, SessionStateService | - | Session state management service. Consolidates fulfillment state and subconscious state handling. |
| `services/sock_service.py` | 919 | HardwareProfile, ModelRecommendation, OllamaInventory, PolicyDiff, WarmResult, SockReport, scan_hardware, scan_ollama, +8 more | - | - |
| `services/solution_trail.py` | 614 | classify_attempt, judgment_still_suppresses, action_suppressed_by_trail, tool_targets_already_held, sequence_item_should_skip_for_trail, append_attempt_judgment, record_attempt_on_branch, preferred_tool_from_progress, +1 more | - | Solution trail: attempt journal → judgment → next productive move. |
| `services/source_root_judgment.py` | 328 | build_source_root_judgment, build_source_root_operator_notice, publish_source_root_operator_notice, render_source_root_judgment | - | - |
| `services/storage_watch.py` | 182 | StorageWatchService | STORAGE_WATCH_SERVICE | - |
| `services/subconscious_control.py` | 134 | SubconsciousControlService | SUBCONSCIOUS_CONTROL_SERVICE | - |
| `services/subconscious_reporting.py` | 95 | build_training_backlog_summary, build_robust_weakness_summary | - | - |
| `services/subconscious_review_authority.py` | 466 | SubconsciousReviewAuthorityService | SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE | - |
| `services/subconscious_review_judgment.py` | 419 | is_no_owner_root_repair_judgment, parse_subconscious_review_judgment_result, latest_subconscious_review_judgment_for_branch, build_subconscious_review_judgment, render_subconscious_review_judgment | - | - |
| `services/subconscious_runtime.py` | 49 | ConfiguredSubconsciousService | SUBCONSCIOUS_SERVICE | Configured runtime boundary for Nova's subconscious state helpers. |
| `services/subconscious_work_tree_triage.py` | 613 | SubconsciousWorkTreeTriageService | SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE | - |
| `services/supervisor_authority.py` | 129 | default_rule_handlers, result_is_explicitly_owned, register_rule, evaluate_rules | - | - |
| `services/supervisor_finish.py` | 73 | supervisor_ownership_finish_status | - | Unfinished supervisor ownership area (operator policy). |
| `services/supervisor_patterns.py` | 9 | normalize_text | - | - |
| `services/supervisor_probes.py` | 254 | status_line, normalize_decision, recent_issue_names, suggest_hardening, looks_like_identity_location_turn, looks_like_suspicious_fallback, build_suggestions, probe_entrypoint_parity, +6 more | - | - |
| `services/supervisor_registry.py` | 35 |  | - | - |
| `services/supervisor_rules.py` | 284 | rule_intent_move_classify, rule_identity_location_guard, rule_ambiguous_clarifier_gate, rule_safe_fallback_contract | - | supervisor_rules.py -------------------- Default Supervisor rule implementations. |
| `services/supervisor_runtime.py` | 18 |  | - | - |
| `services/test_session_control.py` | 717 | TestSessionControlService | TEST_SESSION_CONTROL_SERVICE | - |
| `services/test_session_definitions.py` | 36 | iter_definition_files, count_definition_files, relative_definition_name | - | - |
| `services/thorough_audit_verdict.py` | 52 | live_closure_hard_fail, build_hard_fail_report | - | Verdict logic for the thorough audit probe (canonical, testable). |
| `services/tool_console.py` | 90 | ToolConsoleService | - | - |
| `services/tool_execution.py` | 70 | ToolExecutionService | - | - |
| `services/tool_execution_contracts.py` | 3 |  | - | - |
| `services/tool_identity.py` | 132 | canonicalize_tool_name, evidence_quality, is_verified_tool, is_observed_tool, quality_names, all_quality_tool_names, collect_marker_tool_names | - | Shared tool name identity and evidence quality for progress honesty. |
| `services/tool_registry.py` | 208 | ToolInvocationEvent, ToolRegistryService | - | ToolRegistryService - Manages tool registry and event logging. |
| `services/validation_artifact_truth.py` | 306 | ValidationArtifactTruthService | VALIDATION_ARTIFACT_TRUTH_SERVICE | - |
| `services/voice_interaction.py` | 100 | VoiceInteractionService | VOICE_INTERACTION_SERVICE | - |
| `services/web_research_session.py` | 80 | WebResearchPage, WebResearchSessionStore | - | - |
| `services/work_tree_decision_adapter.py` | 417 | WorkTreeDecisionOutcome, IdentityDecisionScores, WorkTreeDecisionAdapter | - | Decision-only adaptive learning for work-tree routing. |
| `services/work_tree_operator_hold.py` | 70 | node_is_operator_hold | - | - |
| `services/work_tree_pressure_snapshot.py` | 260 | build_work_tree_pressure_snapshot, build_work_tree_pressure_snapshot_from_module | - | - |
| `services/work_tree_seeding.py` | 1185 | WorkTreeSeedingService | WORK_TREE_SEEDING_SERVICE | - |
| `services/work_tree_signal_ingestion.py` | 8107 | advance_branch_sequence_after_task, WorkTreeSignalIngestionService | WORK_TREE_SIGNAL_INGESTION_SERVICE | - |
| `services/work_tree_task_progress.py` | 1297 | SolutionMarker, SolutionLadder, family_key, learned_ladders_path, work_tree_db_path, load_learned_ladders, save_learned_ladders, get_ladder, +5 more | - | Work-tree task progress: distance to a defined solution. |

## Backpack Host

| Module | Lines | Public classes/functions | Singleton | Description |
|---|---:|---|---|---|
| `services/backpack_host/__init__.py` | 31 |  | - | - |
| `services/backpack_host/capability_surface.py` | 446 | declared_capabilities_edfi, scan_backpack_fusion, load_last_scan, get_fusion_status | - | - |
| `services/backpack_host/grant_enforcer.py` | 102 | load_operations, check_grant, require_grant, list_allowed_operations, operation_summary | - | - |
| `services/backpack_host/install_state.py` | 49 | backpack_settings_path, backpack_runtime_installed, backpack_uninstall_mark_path, write_backpack_uninstall_mark, clear_backpack_uninstall_mark | - | - |
| `services/backpack_host/installer.py` | 372 | BackpackInstaller | - | - |
| `services/backpack_host/loader.py` | 123 | load_backpack_manifest | - | - |
| `services/backpack_host/ops_map.py` | 97 | pipeline_op_to_backpack_op, backpack_dir_for_pipeline_id, resolve_shell_role | - | - |
| `services/backpack_host/query.py` | 204 | run_backpack_query, backpack_status, list_backpack_summaries | - | - |
| `services/backpack_host/registry.py` | 112 | BackpackAwarePipelineRegistry | - | - |
| `services/backpack_host/reports.py` | 624 | list_report_intents, resolve_report_intent, clear_report_cache, run_backpack_report | - | - |
| `services/backpack_host/sanitize.py` | 396 | backpack_touch_points, planned_sanitize_paths, scan_backpack_residue, sanitize_uninstalled_backpack | - | - |
| `services/backpack_host/scope_settings.py` | 231 | normalize_scope_mode, normalize_access_tier, lea_identity_key, format_lea_id, lea_in_list, parse_lea_list, allowed_leas_from_settings, primary_lea_from_settings, +2 more | - | - |

## data connector Data Layer

| Module | Lines | Public classes/functions | Singleton | Description |
|---|---:|---|---|---|
| `services/edfi/__init__.py` | 221 | run_self_profile | - | - |
| `services/edfi/auth.py` | 170 | AuthResult, EdFiAuthService | - | - |
| `services/edfi/auth_probe.py` | 191 | probe_auth | - | - |
| `services/edfi/change_tracking.py` | 490 | resolve_change_queries_base, resolve_data_management_api, fetch_available_change_versions, load_sync_state, save_sync_state, sync_status, maybe_advance_tracked_cursors, pull_changes_since | - | - |
| `services/edfi/client.py` | 255 | get_cooldown_remaining, clear_cooldown, EdFiResponse, EdFiClient | - | - |
| `services/edfi/config.py` | 227 | ConnectionConfig, TokenCacheEntry, connection_dir, connection_config_path, profile_path, ensure_runtime_dirs, change_cursor_path, validate_connection_payload, +6 more | - | - |
| `services/edfi/core_readiness.py` | 231 | read_edfi_core_readiness | - | - |
| `services/edfi/diagnostics.py` | 140 | build_health_payload, build_config_error_health, append_audit_event | - | - |
| `services/edfi/discovery.py` | 317 | DiscoveryResult, discover_metadata, build_capability_profile, discover_and_save_profile | - | - |
| `services/edfi/district_scope.py` | 138 | normalize_district_lea_id, district_lea_filter_clause, merge_filter_params, uses_client_side_district_filter, item_matches_district, district_filter_strategy | - | - |
| `services/edfi/errors.py` | 69 | classify_http_status, classify_request_exception, issue_from_error, config_validation_issues, empty_health_shell | - | - |
| `services/edfi/extract_store.py` | 205 | canonical_extract_intent, extract_path, save_extract, load_extract, list_extracts | - | - |
| `services/edfi/inventory.py` | 472 | build_client, profile_summary, refresh_resource_catalog, list_resources, read_resource, read_preset | - | - |
| `services/edfi/present.py` | 308 | format_lea_display, shape_school_row, shape_student_row, shape_association_row, shape_health_row, shape_resource_name_rows, present_operation_result | - | - |
| `services/edfi/profile_evidence.py` | 422 | extract_profile_from_read_result, capability_profile_payload_valid, profile_read_evidence_valid, audit_runtime_profile_contract, build_capability_profile_evidence, get_district_layer_facts | - | - |
| `services/edfi/rate_limit_evidence.py` | 351 | evidence_dir, extract_rate_limit_headers, parse_retry_after_seconds, suggested_cooldown_seconds, record_rate_limit_event, record_recovery_if_pending, load_latest_evidence, load_recent_events, +2 more | - | - |
| `services/edfi/resources.py` | 367 | PageResult, ResourceReadResult, get_page, get_district_scoped_page, get_all | - | - |
| `services/edfi/warehouse.py` | 1819 | warehouse_path, begin_sync_run, finish_sync_run, last_successful_sync, replace_schools, list_schools, schools_count, replace_students, +28 more | - | - |
| `services/edfi/warehouse_sync.py` | 966 | load_backpack_settings, sync_schedule_config, due_for_scheduled_sync, run_resource_sync, run_full_sync, run_full_schools_sync, maybe_run_scheduled_warehouse_sync, schools_report_from_warehouse | - | - |

## Nova Shell

| Module | Lines | Public classes/functions | Singleton | Description |
|---|---:|---|---|---|
| `services/nova_shell/__init__.py` | 20 |  | - | - |
| `services/nova_shell/_constants.py` | 155 |  | - | - |
| `services/nova_shell/admin.py` | 453 | TOTPSetupResult, ShellAdmin | - | - |
| `services/nova_shell/auth.py` | 245 | hash_password, verify_password, LoginResult, SessionInfo, ShellAuth | - | - |
| `services/nova_shell/external_finish.py` | 84 | external_finish_status | - | Unfinished Nova Shell areas that require LLC / operator pieces. |
| `services/nova_shell/http_trust.py` | 91 | resolve_control_panel_role, shell_http_status | - | - |
| `services/nova_shell/identity.py` | 78 | NodeIdentity, generate_installation_id, load_or_create_identity, get_installation_id | - | - |
| `services/nova_shell/recovery.py` | 110 | generate_recovery_codes, verify_and_consume_code, remaining_code_count, codes_from_json, codes_to_json | - | - |
| `services/nova_shell/roles.py` | 230 | role_exists, is_static_role, role_level, role_label, is_assignable, has_permission, can_assign_role, assignable_roles_for, +7 more | - | - |
| `services/nova_shell/store.py` | 282 | ShellStore | - | - |
| `services/nova_shell/telemetry.py` | 79 | configured_central_url, emit_signal, connect_central, is_connected, telemetry_status | - | - |
| `services/nova_shell/totp.py` | 64 | generate_totp_secret, totp_uri, verify_totp, totp_available | - | - |
| `services/nova_shell/update_receiver.py` | 77 | verify_update_signature, accept_update, receiver_status | - | - |

## Maintenance Rule

Any added, removed, or renamed file under `services/` must update this index.
Regenerate with: `python scripts/regenerate_services_index.py`
A service is not documented merely because a nearby subsystem is described.
