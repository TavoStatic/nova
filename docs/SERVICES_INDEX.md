# Services Index

Last generated from code: 2026-07-12

This is the exhaustive service-module index. Architectural ownership is described in `SYSTEM_MAP.md`; function-level detail is in `FUNCTION_INDEX.md`.

## Ownership Domains

- Runtime and process truth: `runtime_*`, `control_status*`, `port_ownership`, `ollama_health`, `server_side_runtime`.
- HTTP and operator surfaces: `nova_http_*`, `control_*`, `operator_*`, `leah_*`, `session_*`, `chat_identity`.
- Conversation and reply behavior: `nova_routing_*`, `nova_planner_contract`, `nova_reply_*`, `nova_fallback_flow`, `fulfillment_flow`, `supervisor_*`.
- Memory and identity: `memory_*`, `identity_memory`, `nova_memory_*`, `nova_operational_identity`.
- Tools and policy: `tool_*`, `nova_tool_*`, `policy_*`, `os_*`, `evidence_validity`.
- Autonomy and feedback: `autonomy_*`, `nova_mission*`, `work_tree_*`, `subconscious_*`, `core_*`, `layer_maturity_policy`.
- Patch, codegen, test, and release: `nova_patching`, `patch_*`, `codegen_*`, `test_session_*`, `regression_*`, `validation_*`, `release_*`, `installer_validation`.
- Data and Ed-Fi: `data_pipeline_registry`, `control_pipelines`, `pipeline_privileged_bridge`, and `services/edfi/*`.
- Media, time, retrieval, and environment: `nova_voice_runtime`, `nova_vision_runtime`, `nova_temporal_service`, `nova_calendar_ingestion`, `nova_web_*`, `nova_location_weather`, `sock_service`.
- Inventory and diagnosis: `nova_wiring_inventory`, `nova_root_inventory`, `end_to_end_wiring`, `source_root_judgment`, `storage_watch`, `ops_journal`.

## Exhaustive Module Inventory

| Module | Lines | Public classes/functions | Service singleton |
|---|---:|---|---|
| `services/autonomy_execution_gate.py` | 262 | `AutonomyExecutionGateService` | `AUTONOMY_EXECUTION_GATE_SERVICE` |
| `services/autonomy_orchestrator.py` | 1550 | `AutonomyOrchestratorService` | `AUTONOMY_ORCHESTRATOR_SERVICE` |
| `services/autonomy_orchestrator_ledger.py` | 214 | `AutonomyOrchestratorLedgerService` | `AUTONOMY_ORCHESTRATOR_LEDGER_SERVICE` |
| `services/behavior_metrics.py` | 67 | `BehaviorMetricsStore` | - |
| `services/capabilities_gap_detector.py` | 122 | `detect_capability_gaps`, `enhance_status_with_capability_gaps` | `CAPABILITY_GAP_DETECTOR_SERVICE` |
| `services/chat_identity.py` | 198 | `ChatIdentityService` | `CHAT_IDENTITY_SERVICE` |
| `services/codegen_memory_recorder.py` | 348 | `record_generated_pattern`, `lookup_patterns_by_capability`, `lookup_patterns_by_spec`, `build_memory_injection_context`, `CodegenMemoryRecorderService` | `CODEGEN_MEMORY_RECORDER_SERVICE` |
| `services/codegen_patch_bridge.py` | 231 | `validate_codegen_preview`, `bridge_codegen_to_patch`, `format_bridge_summary` | `CODEGEN_PATCH_BRIDGE_SERVICE` |
| `services/control_actions.py` | 43 | `ControlActionsService` | `CONTROL_ACTIONS_SERVICE` |
| `services/control_assets.py` | 36 | `ControlAssetsService` | `CONTROL_ASSETS_SERVICE` |
| `services/control_auth.py` | 143 | `ControlAuthService` | `CONTROL_AUTH_SERVICE` |
| `services/control_login_frontdoor.py` | 89 | `ControlLoginFrontdoorService` | `CONTROL_LOGIN_FRONTDOOR_SERVICE` |
| `services/control_pipelines.py` | 549 | `ControlPipelinesService` | `CONTROL_PIPELINES_SERVICE` |
| `services/control_status.py` | 1601 | `ControlStatusService` | `CONTROL_STATUS_SERVICE` |
| `services/control_status_cache.py` | 34 | `ControlStatusCacheService` | `CONTROL_STATUS_CACHE_SERVICE` |
| `services/control_status_surfaces.py` | 501 | `signal_ingestion_top_level_keys`, `derive_surfaces_url`, `extract_signal_ingestion_surfaces`, `merge_http_supplement_into_local`, `release_drift_detected`, `ControlStatusSurfacesService` | `CONTROL_STATUS_SURFACES_SERVICE` |
| `services/control_telemetry.py` | 724 | `ControlTelemetryService` | - |
| `services/control_work_trees.py` | 231 | `ControlWorkTreesService` | `CONTROL_WORK_TREES_SERVICE` |
| `services/core_health_brief.py` | 412 | `build_core_health_brief`, `write_core_health_brief`, `render_core_health_brief`, `feed_core_health_brief_to_work_tree` | - |
| `services/core_seam_guard.py` | 128 | `CoreSeamGuardService` | `CORE_SEAM_GUARD_SERVICE` |
| `services/core_steward.py` | 345 | `build_core_steward_payload`, `build_core_steward_gates`, `render_core_steward` | - |
| `services/core_steward_contracts.py` | 4 | - | - |
| `services/core_thinning.py` | 810 | `build_core_thinning_brief`, `build_core_thinning_owner_verdict`, `render_core_thinning_brief`, `execute_core_thinning_order`, `feed_core_thinning_brief_to_work_tree` | - |
| `services/data_pipeline_registry.py` | 126 | `build_pipeline_registry`, `list_pipeline_summaries`, `get_pipeline_status`, `get_pipeline_schema_probe`, `search_pipeline_vendor_dictionary`, `plan_pipeline_report`, `preview_pipeline_query`, `run_pipeline_query` | - |
| `services/decision_pipeline.py` | 120 | `make_trace_entry`, `RegisteredStage`, `StageRegistry`, `run_registered_stages` | - |
| `services/edfi/__init__.py` | 221 | `run_self_profile` | - |
| `services/edfi/auth.py` | 170 | `AuthResult`, `EdFiAuthService` | - |
| `services/edfi/change_tracking.py` | 427 | `resolve_change_queries_base`, `resolve_data_management_api`, `fetch_available_change_versions`, `load_sync_state`, `save_sync_state`, `sync_status`, `pull_changes_since` | - |
| `services/edfi/client.py` | 157 | `EdFiResponse`, `EdFiClient` | - |
| `services/edfi/config.py` | 227 | `ConnectionConfig`, `TokenCacheEntry`, `connection_dir`, `connection_config_path`, `profile_path`, `ensure_runtime_dirs`, `change_cursor_path`, `validate_connection_payload`, `load_connection_config`, `connection_config_from_dict`, `save_connection_config`, `save_capability_profile`, `load_capability_profile`, `runtime_roots` | - |
| `services/edfi/core_readiness.py` | 125 | `read_edfi_core_readiness` | - |
| `services/edfi/diagnostics.py` | 140 | `build_health_payload`, `build_config_error_health`, `append_audit_event` | - |
| `services/edfi/discovery.py` | 317 | `DiscoveryResult`, `discover_metadata`, `build_capability_profile`, `discover_and_save_profile` | - |
| `services/edfi/district_scope.py` | 76 | `normalize_district_lea_id`, `district_lea_filter_clause`, `merge_filter_params`, `uses_client_side_district_filter`, `item_matches_district`, `district_filter_strategy` | - |
| `services/edfi/errors.py` | 69 | `classify_http_status`, `classify_request_exception`, `issue_from_error`, `config_validation_issues`, `empty_health_shell` | - |
| `services/edfi/inventory.py` | 358 | `build_client`, `profile_summary`, `refresh_resource_catalog`, `list_resources`, `read_resource`, `read_preset` | - |
| `services/edfi/profile_evidence.py` | 387 | `extract_profile_from_read_result`, `capability_profile_payload_valid`, `profile_read_evidence_valid`, `audit_runtime_profile_contract`, `build_capability_profile_evidence`, `get_district_layer_facts` | - |
| `services/edfi/resources.py` | 325 | `PageResult`, `ResourceReadResult`, `get_page`, `get_district_scoped_page`, `get_all` | - |
| `services/end_to_end_wiring.py` | 746 | `run_end_to_end_wiring_check` | - |
| `services/evidence_validity.py` | 106 | `invalid_tool_result`, `evidence_result_valid` | - |
| `services/frontdoor_cli_parity.py` | 184 | `build_frontdoor_cli_surfaces`, `FrontdoorCliParityService` | `FRONTDOOR_CLI_PARITY_SERVICE` |
| `services/fulfillment_flow.py` | 247 | `FulfillmentFlowService` | - |
| `services/generated_work_queue_snapshot.py` | 35 | `generated_work_queue_payload` | - |
| `services/identity_memory.py` | 54 | `IdentityMemoryService` | - |
| `services/installer_validation.py` | 279 | `run_installer_validation`, `render_installer_validation_report` | - |
| `services/layer_maturity_policy.py` | 361 | `normalize_layer_policy`, `layer_for_capability`, `evaluate_core_gate`, `next_leah_capability_in_sequence`, `capability_action_block_reason`, `capability_action_allowed`, `filter_actionable_capability_gaps`, `build_layer_maturity_summary`, `enrich_status_with_layer_maturity`, `capability_gap_signal_suppressed`, `orchestrator_codegen_action_allowed`, `LayerMaturityPolicyService` | `LAYER_MATURITY_POLICY_SERVICE` |
| `services/leah_conversation_continuity.py` | 73 | `LeahConversationContinuityStore`, `capability_registration` | - |
| `services/leah_fast_chat.py` | 21 | `leah_fast_chat_enabled`, `load_leah_fast_chat_from_core` | - |
| `services/leah_frontdoor.py` | 298 | `LeahFrontdoorService` | - |
| `services/memory_adapter.py` | 213 | `MemoryAdapterService` | - |
| `services/memory_bootstrap_contracts.py` | 3 | - | - |
| `services/memory_bootstrap_judgment.py` | 166 | `build_memory_bootstrap_judgment`, `render_memory_bootstrap_judgment` | - |
| `services/memory_bootstrap_origin.py` | 313 | `default_pending_origin_contract`, `write_origin_contract`, `confirm_origin_contract`, `load_origin_contract` | - |
| `services/memory_health.py` | 424 | `build_memory_health_payload` | - |
| `services/memory_identity_bootstrap.py` | 189 | `build_identity_bootstrap_preview`, `apply_identity_bootstrap`, `render_identity_bootstrap_result` | - |
| `services/memory_retention.py` | 289 | `parse_retention_policy`, `evaluate_contamination`, `apply_memory_hygiene`, `render_memory_hygiene_result` | - |
| `services/memory_routing.py` | 79 | `MemoryRecallPlan`, `MemoryRoutingService` | - |
| `services/nova_action_ledger.py` | 220 | `start_action_ledger_record`, `write_action_ledger_record`, `finalize_action_ledger_record`, `finalize_action_ledger_record_from_runtime` | - |
| `services/nova_action_ledger_helpers.py` | 336 | `action_ledger_add_step`, `action_ledger_route_summary`, `recent_action_ledger_records`, `latest_action_ledger_record`, `action_history_reply`, `record_completed_tool_execution`, `record_requested_tool_clarification`, `detect_repeated_tool_intent_without_execution`, `top_repeated_correction_class`, `count_routing_overrides_recently`, `record_used_routing_override`, `routing_stable_recently`, `sample_intents_last` | - |
| `services/nova_calendar_ingestion.py` | 516 | `load_sidecar_enrichment`, `save_sidecar_enrichment`, `serialize_events_to_ics`, `parse_ics_text`, `parse_ics_file`, `normalize_calendar_event`, `read_calendar_events`, `write_calendar_event`, `delete_calendar_event` | - |
| `services/nova_cli_delivery.py` | 94 | `apply_cli_outcome_to_ledger`, `apply_cli_handled_outcome`, `emit_cli_reply_outcome` | - |
| `services/nova_cli_loop.py` | 415 | `run_loop` | - |
| `services/nova_cli_sequence.py` | 113 | `execute_cli_sequence`, `normalize_sequence_reply`, `apply_sequence_result` | - |
| `services/nova_control_action_dispatcher.py` | 719 | `autonomy_advisory_action_catalog`, `autonomy_advisory_action_types`, `is_autonomy_advisory_action`, `NovaControlActionDispatcher` | - |
| `services/nova_fallback_flow.py` | 340 | `build_fallback_context`, `prepare_fallback_flow`, `finalize_llm_fallback_reply` | - |
| `services/nova_fulfillment_routing.py` | 60 | `evaluate_fulfillment_route_viability` | - |
| `services/nova_grounded_self_report.py` | 470 | `TroubleItem`, `NovaGroundedSelfReportService` | `GROUNDED_SELF_REPORT_SERVICE` |
| `services/nova_http_chat_runtime.py` | 191 | `NovaHttpChatRuntimeService` | `HTTP_CHAT_RUNTIME_SERVICE` |
| `services/nova_http_frontdoor.py` | 192 | `NovaHttpFrontdoorService` | `NOVA_HTTP_FRONTDOOR_SERVICE` |
| `services/nova_http_generated_work.py` | 90 | `NovaHttpGeneratedWorkService` | `HTTP_GENERATED_WORK_SERVICE` |
| `services/nova_http_get_routes.py` | 255 | `NovaHttpGetRoutesService` | `HTTP_GET_ROUTES_SERVICE` |
| `services/nova_http_pipeline_control.py` | 92 | `NovaHttpPipelineControlService` | `HTTP_PIPELINE_CONTROL_SERVICE` |
| `services/nova_http_policy_search.py` | 86 | `NovaHttpPolicySearchService` | `HTTP_POLICY_SEARCH_SERVICE` |
| `services/nova_http_post_dispatch.py` | 87 | `NovaHttpPostDispatchService` | `HTTP_POST_DISPATCH_SERVICE` |
| `services/nova_http_post_routes.py` | 94 | `NovaHttpPostRoutesService` | `HTTP_POST_ROUTES_SERVICE` |
| `services/nova_http_request_binding.py` | 209 | `NovaHttpRequestBindingService` | `HTTP_REQUEST_BINDING_SERVICE` |
| `services/nova_http_responses.py` | 125 | `NovaHttpResponsesService` | `HTTP_RESPONSE_SERVICE` |
| `services/nova_http_transport.py` | 61 | `NovaHttpTransportService` | `HTTP_TRANSPORT_SERVICE` |
| `services/nova_http_turn_finalization.py` | 225 | `session_reply_for_context`, `NovaHttpTurnFinalizationService` | `HTTP_TURN_FINALIZATION_SERVICE` |
| `services/nova_intent_understanding.py` | 327 | `classify_turn_intent`, `select_response_strategy`, `record_intent_outcome` | - |
| `services/nova_inventory_labels.py` | 33 | `shared_inventory_label` | - |
| `services/nova_knowledge_packs.py` | 313 | `tokenize`, `kb_active_pack`, `kb_set_active`, `kb_list_packs`, `kb_add_zip`, `active_knowledge_root`, `kb_search`, `read_text_safely`, `extract_key_lines`, `topic_tokens`, `extract_matching_lines`, `build_local_topic_digest_answer` | - |
| `services/nova_location_weather.py` | 589 | `weather_source_host`, `weather_unavailable_message`, `weather_response_style`, `format_weather_output`, `runtime_device_backend_provider`, `coerce_bounded_float`, `coerce_optional_metric`, `normalize_source_timestamp`, `format_runtime_coords`, `distance_meters`, `location_label_for_coords`, `live_device_location_summary`, `device_location_status_payload`, `runtime_device_location_payload`, `set_runtime_device_location`, `clear_runtime_device_location`, `resolve_windows_device_coords`, `resolve_current_device_coords`, `parse_lat_lon`, `coords_for_location_hint`, `coords_from_saved_location`, `get_saved_location_text`, `set_location_coords`, `get_weather_for_location`, `need_confirmed_location_message`, `tool_weather` | - |
| `services/nova_memory_events.py` | 56 | `append_memory_event`, `record_memory_event` | - |
| `services/nova_memory_learning.py` | 1125 | `mem_stats_payload`, `mem_add`, `mem_recall`, `prefix_from_earlier_memory`, `normalize_recent_learning_item`, `mem_get_recent_learned`, `mem_stats`, `mem_audit`, `mem_remember_fact`, `load_identity_profile`, `save_identity_profile`, `looks_invalid_person_token`, `sanitize_learned_facts`, `load_json_dict_with_tmp_fallback`, `load_learned_facts`, `save_learned_facts`, `clean_fact_value`, `title_name`, `learn_from_user_correction`, `get_learned_fact`, `speaker_matches_developer`, `learn_self_identity_binding`, `learn_contextual_self_facts`, `remember_name_origin`, `get_name_origin_story`, `identity_context_for_prompt`, `extract_name_origin_teach_text`, `build_learning_context_details`, `build_learning_context` | - |
| `services/nova_mission.py` | 681 | `NovaMissionService` | `NOVA_MISSION_SERVICE` |
| `services/nova_mission_owner_verdicts.py` | 407 | `build_mission_truth_gate` | - |
| `services/nova_ollama_chat.py` | 174 | `ollama_chat` | - |
| `services/nova_operational_identity.py` | 46 | `operational_identity_context_for_prompt` | - |
| `services/nova_patching.py` | 1582 | `snapshot_should_skip_relpath`, `parse_scoped_patch_payload`, `execute_scoped_patch_payload`, `log_patch`, `read_patch_revision`, `write_patch_revision`, `snapshot_meta_path`, `write_snapshot_meta`, `read_snapshot_meta`, `snapshot_current`, `overlay_change_candidates`, `overlay_zip`, `py_compile_check`, `last_nonempty_line`, `read_patch_manifest`, `behavioral_check_command`, `behavioral_check`, `read_patch_log_tail_line`, `preview_status_from_report`, `preview_report_files`, `preview_archive_dir`, `resolve_preview_report_path`, `preview_report_summary`, `compact_preview_review_queue`, `patch_preview_summaries`, `patch_status_payload`, `control_status_patch_fields`, `archive_preview_report`, `bulk_reject_orphaned_previews`, `bulk_archive_superseded_previews`, `patch_reject_message`, `patch_apply`, `patch_rollback`, `patch_preview`, `approvals_file`, `read_approvals`, `record_approval`, `list_previews`, `show_preview`, `approve_preview`, `reject_preview`, `interactive_preview_review`, `teach_propose_patch`, `teach_autoapply_proposal`, `interactive_patch_review_enabled` | - |
| `services/nova_pipeline_tools.py` | 439 | `parse_pipeline_params`, `parse_pipeline_command`, `render_pipeline_help`, `render_pipeline_list`, `render_pipeline_status`, `render_pipeline_schema`, `render_pipeline_dictionary_search`, `render_pipeline_report_plan`, `render_pipeline_query_result`, `handle_pipeline_command` | - |
| `services/nova_planner_contract.py` | 729 | `build_planner_config`, `merge_route_evidence`, `maybe_handle_planner_sequence` | - |
| `services/nova_pulse.py` | 374 | `build_pulse_payload`, `write_pulse_snapshot`, `render_nova_pulse`, `tool_nova_pulse` | - |
| `services/nova_reflection_health.py` | 384 | `detect_repeated_tool_intent_without_execution`, `top_repeated_correction_class`, `count_routing_overrides_recently`, `record_used_routing_override`, `routing_stable_recently`, `sample_intents_last`, `append_self_reflection`, `append_health_snapshot`, `record_health_snapshot`, `recent_self_reflection_rows`, `maybe_log_self_reflection`, `build_turn_reflection` | - |
| `services/nova_reply_context_contract.py` | 4 | - | - |
| `services/nova_reply_runtime.py` | 39 | `apply_reply_runtime_effects` | - |
| `services/nova_reply_sequence.py` | 385 | `execute_reply_sequence_from_runtime`, `execute_http_reply_sequence_from_runtime`, `execute_reply_sequence` | - |
| `services/nova_root_inventory.py` | 652 | `SourceRoot`, `source_root_ids`, `build_source_root_inventory_payload` | - |
| `services/nova_route_probing.py` | 127 | `evaluate_deterministic_route_viability`, `build_probe_turn_routes` | - |
| `services/nova_routing_helpers.py` | 62 | `strip_invocation_prefix`, `resolve_research_provider` | - |
| `services/nova_routing_support.py` | 490 | `intent_trace_preview`, `supervisor_result_has_route`, `supervisor_candidate_trace`, `supervisor_phase_record`, `build_routing_decision`, `finalize_routing_decision`, `llm_classify_routing_intent` | - |
| `services/nova_runtime_context.py` | 128 | `set_active_user`, `get_active_user`, `resolve_base_dir`, `runtime_scope_name`, `resolve_runtime_dir`, `resolve_python_executable` | - |
| `services/nova_runtime_hooks.py` | 33 | `resolve_runtime_hooks` | - |
| `services/nova_scheduler.py` | 80 | `NovaSchedulerService` | - |
| `services/nova_search_endpoint.py` | 138 | `normalize_search_endpoint`, `search_endpoint_candidates`, `is_local_search_endpoint`, `stable_probe_error`, `probe_search_endpoint` | - |
| `services/nova_self_evidence_reply.py` | 152 | `maybe_build_self_evidence_reply` | - |
| `services/nova_self_status.py` | 294 | `read_recent_ops_events`, `build_repo_change_snapshot`, `build_self_status_payload`, `render_self_status` | - |
| `services/nova_service_builders.py` | 34 | `build_policy_manager`, `build_identity_memory_service`, `build_fulfillment_flow_service` | - |
| `services/nova_session_state.py` | 33 | `apply_reply_session_updates` | - |
| `services/nova_temporal_service.py` | 318 | `TemporalEvent`, `TemporalPressure`, `NovaTemporalService`, `build_temporal_pressure` | - |
| `services/nova_tool_dispatch.py` | 198 | `execute_planned_action`, `execute_planned_action_from_runtime` | - |
| `services/nova_tool_policy.py` | 179 | `research_handlers`, `execute_research_action`, `patch_handlers`, `execute_patch_action`, `web_allowlist_message`, `web_fetch` | - |
| `services/nova_turn_intent_trace.py` | 241 | `build_turn_intent_evidence_packet`, `render_turn_intent_evidence_packet`, `attach_turn_intent_evidence_packet` | - |
| `services/nova_update_now.py` | 152 | `read_update_now_pending`, `write_update_now_pending`, `clear_update_now_pending`, `update_now_pending_payload`, `build_update_now_token`, `extract_preview_status`, `extract_preview_zip`, `tool_update_now`, `tool_update_now_confirm`, `tool_update_now_cancel` | - |
| `services/nova_vision_runtime.py` | 112 | `vision_model_from_policy`, `vision_model_from_policy_file`, `vision_status_payload` | - |
| `services/nova_voice_runtime.py` | 541 | `ensure_voice_deps`, `voice_status_payload`, `record_seconds`, `transcribe`, `SubprocessTTS`, `speak_chunked` | - |
| `services/nova_web_contracts.py` | 3 | - | - |
| `services/nova_web_tools.py` | 1183 | `scan_candidate_urls_for_query`, `extract_urls`, `decode_search_href`, `extract_text_from_path`, `extract_text_from_html_content`, `extract_same_host_links`, `expand_research_terms`, `score_research_hit`, `crawl_domain_for_query`, `seed_urls_for_domain`, `looks_like_code_discovery_query`, `host_label`, `summary_from_gather_output`, `is_weak_grounded_snippet`, `build_grounded_answer`, `fetch_sitemap_urls`, `tool_web_fetch`, `tool_wikipedia_lookup`, `tool_stackexchange_search`, `tool_web_search`, `tool_web_gather`, `tool_web_research`, `web_search`, `tool_search` | - |
| `services/nova_wiring_inventory.py` | 1239 | `WiringSurface`, `build_source_wiring_probe_payload`, `build_wiring_inventory_payload`, `build_root_closure_inventory_payload`, `build_self_repair_closure_inventory_payload`, `wiring_surface_ids` | - |
| `services/ollama_health.py` | 168 | `build_ollama_health_payload` | - |
| `services/operator_control.py` | 328 | `OperatorControlService` | `OPERATOR_CONTROL_SERVICE` |
| `services/operator_outbox.py` | 1382 | `OperatorOutboxService` | `OPERATOR_OUTBOX_SERVICE` |
| `services/ops_journal.py` | 123 | `append_ops_event` | - |
| `services/os_capability_operator_outbox.py` | 177 | `build_os_capability_notice`, `publish_os_capability_notice` | - |
| `services/os_capability_registry.py` | 583 | `OsCapabilityRegistryService` | `OS_CAPABILITY_REGISTRY_SERVICE` |
| `services/os_script_controller.py` | 678 | `OsScriptControllerService` | `OS_SCRIPT_CONTROLLER_SERVICE` |
| `services/patch_control.py` | 375 | `PatchControlService` | `PATCH_CONTROL_SERVICE` |
| `services/patch_promotion_memory.py` | 234 | `extract_codegen_content_from_patch_zip`, `record_patch_promotion_to_memory`, `inject_memory_context_into_codegen_prompt`, `PatchPromotionMemoryService` | `PATCH_PROMOTION_MEMORY_SERVICE` |
| `services/pipeline_privileged_bridge.py` | 89 | `queue_privileged_pipeline_query`, `wait_for_privileged_pipeline_query`, `run_privileged_pipeline_query` | - |
| `services/policy_control.py` | 187 | `PolicyControlService` | `POLICY_CONTROL_SERVICE` |
| `services/policy_manager.py` | 758 | `PolicyManager` | - |
| `services/port_ownership.py` | 164 | `PortOwnershipService` | `PORT_OWNERSHIP_SERVICE` |
| `services/regression_lanes.py` | 265 | - | - |
| `services/regression_profile_inventory.py` | 247 | `build_regression_profile_inventory_payload` | `REGRESSION_PROFILE_INVENTORY_SERVICE` |
| `services/release_clean.py` | 324 | `run_release_clean` | - |
| `services/release_promotion_judgment.py` | 313 | `release_validation_record_payload`, `build_release_promotion_judgment`, `render_release_promotion_judgment` | - |
| `services/release_runtime_truth.py` | 132 | `running_build_identity`, `enrich_release_status`, `build_release_runtime_truth_summary`, `release_drift_suppresses_closure_signals`, `evaluate_http_model_runtime_probe`, `ReleaseRuntimeTruthService` | `RELEASE_RUNTIME_TRUTH_SERVICE` |
| `services/release_status.py` | 448 | `ReleaseStatusService` | `RELEASE_STATUS_SERVICE` |
| `services/release_validation.py` | 722 | `run_release_validation`, `render_release_validation_report`, `record_release_validation_outcome`, `render_release_outcome_recording` | - |
| `services/release_validation_contracts.py` | 3 | - | - |
| `services/runtime_analytics.py` | 349 | `RuntimeAnalyticsService` | `RUNTIME_ANALYTICS_SERVICE` |
| `services/runtime_artifacts.py` | 250 | `RuntimeArtifactsService` | `RUNTIME_ARTIFACTS_SERVICE` |
| `services/runtime_console_frontdoor.py` | 391 | `RuntimeConsoleFrontdoorService` | `RUNTIME_CONSOLE_FRONTDOOR_SERVICE` |
| `services/runtime_control.py` | 797 | `RuntimeControlService` | `RUNTIME_CONTROL_SERVICE` |
| `services/runtime_heartbeat.py` | 146 | `heartbeat_status_path`, `heartbeat_log_path`, `read_heartbeat_status`, `heartbeat_write_once`, `start_heartbeat` | - |
| `services/runtime_process_state.py` | 245 | `RuntimeProcessStateService` | `RUNTIME_PROCESS_STATE_SERVICE` |
| `services/runtime_restart_provenance.py` | 112 | `RuntimeRestartProvenanceService` | `RUNTIME_RESTART_PROVENANCE_SERVICE` |
| `services/runtime_status.py` | 367 | `RuntimeStatusService` | `RUNTIME_STATUS_SERVICE` |
| `services/runtime_timeline.py` | 328 | `RuntimeTimelineService` | `RUNTIME_TIMELINE_SERVICE` |
| `services/schedule_registry.py` | 231 | `ScheduledTask`, `get_task`, `get_schedule_status` | `SCHEDULE_REGISTRY` |
| `services/server_side_runtime.py` | 148 | `ServerSideRuntimeService` | `SERVER_SIDE_RUNTIME_SERVICE` |
| `services/session_admin.py` | 108 | `SessionAdminService` | `SESSION_ADMIN_SERVICE` |
| `services/session_state.py` | 201 | `SubconsciousState`, `SessionStateService` | - |
| `services/sock_service.py` | 731 | `HardwareProfile`, `ModelRecommendation`, `OllamaInventory`, `PolicyDiff`, `WarmResult`, `SockReport`, `scan_hardware`, `scan_ollama`, `recommend_models`, `build_diff`, `apply_policy`, `validate_concurrent_warm`, `run_sock`, `get_sock_status_keys` | - |
| `services/source_root_judgment.py` | 320 | `build_source_root_judgment`, `build_source_root_operator_notice`, `publish_source_root_operator_notice`, `render_source_root_judgment` | - |
| `services/storage_watch.py` | 182 | `StorageWatchService` | `STORAGE_WATCH_SERVICE` |
| `services/subconscious_control.py` | 134 | `SubconsciousControlService` | `SUBCONSCIOUS_CONTROL_SERVICE` |
| `services/subconscious_reporting.py` | 95 | `build_training_backlog_summary`, `build_robust_weakness_summary` | - |
| `services/subconscious_review_authority.py` | 466 | `SubconsciousReviewAuthorityService` | `SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE` |
| `services/subconscious_review_judgment.py` | 419 | `is_no_owner_root_repair_judgment`, `parse_subconscious_review_judgment_result`, `latest_subconscious_review_judgment_for_branch`, `build_subconscious_review_judgment`, `render_subconscious_review_judgment` | - |
| `services/subconscious_runtime.py` | 49 | `ConfiguredSubconsciousService` | `SUBCONSCIOUS_SERVICE` |
| `services/subconscious_work_tree_triage.py` | 613 | `SubconsciousWorkTreeTriageService` | `SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE` |
| `services/supervisor_authority.py` | 123 | `default_rule_handlers`, `result_is_explicitly_owned`, `register_rule`, `evaluate_rules` | - |
| `services/supervisor_patterns.py` | 9 | `normalize_text` | - |
| `services/supervisor_probes.py` | 255 | `status_line`, `normalize_decision`, `recent_issue_names`, `suggest_hardening`, `looks_like_identity_location_turn`, `looks_like_suspicious_fallback`, `build_suggestions`, `probe_entrypoint_parity`, `probe_continuation_drop`, `probe_pending_action_leak`, `probe_override_consistency`, `probe_thin_answer_frequency`, `probe_identity_location_route`, `probe_rule_coverage` | - |
| `services/supervisor_registry.py` | 4 | - | - |
| `services/supervisor_runtime.py` | 18 | - | - |
| `services/test_session_control.py` | 685 | `TestSessionControlService` | `TEST_SESSION_CONTROL_SERVICE` |
| `services/test_session_definitions.py` | 36 | `iter_definition_files`, `count_definition_files`, `relative_definition_name` | - |
| `services/tool_console.py` | 90 | `ToolConsoleService` | - |
| `services/tool_execution.py` | 70 | `ToolExecutionService` | - |
| `services/tool_execution_contracts.py` | 3 | - | - |
| `services/tool_registry.py` | 208 | `ToolInvocationEvent`, `ToolRegistryService` | - |
| `services/validation_artifact_truth.py` | 306 | `ValidationArtifactTruthService` | `VALIDATION_ARTIFACT_TRUTH_SERVICE` |
| `services/voice_interaction.py` | 100 | `VoiceInteractionService` | `VOICE_INTERACTION_SERVICE` |
| `services/web_research_session.py` | 80 | `WebResearchPage`, `WebResearchSessionStore` | - |
| `services/work_tree_decision_adapter.py` | 417 | `WorkTreeDecisionOutcome`, `IdentityDecisionScores`, `WorkTreeDecisionAdapter` | - |
| `services/work_tree_operator_hold.py` | 70 | `node_is_operator_hold` | - |
| `services/work_tree_pressure_snapshot.py` | 260 | `build_work_tree_pressure_snapshot`, `build_work_tree_pressure_snapshot_from_module` | - |
| `services/work_tree_seeding.py` | 1185 | `WorkTreeSeedingService` | `WORK_TREE_SEEDING_SERVICE` |
| `services/work_tree_signal_ingestion.py` | 6929 | `WorkTreeSignalIngestionService` | `WORK_TREE_SIGNAL_INGESTION_SERVICE` |

## Maintenance Rule

Any added, removed, or renamed file under `services/` must update this index and the function index. A service is not documented merely because a nearby subsystem is described.
