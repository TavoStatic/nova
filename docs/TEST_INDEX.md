# Nova Test Surface Index

Generated from the test tree on 2026-07-12. It records discovery and declared regression-lane membership; it does not claim the tests currently pass.

- Test modules indexed: 215
- Test functions indexed: 2016

- Compact regression entries: 97
- Declared source-profile lanes: 20

## Declared Lanes

| Lane | Entries |
|---|---:|
| `unit` | 81 |
| `behavior` | 8 |
| `integration` | 8 |
| `source_data_pipelines` | 8 |
| `source_http_api_control` | 15 |
| `source_memory_identity` | 5 |
| `source_edfi_core` | 8 |
| `source_data_lane_edfi_bisd` | 1 |
| `source_model_runtime` | 2 |
| `source_patch_pipeline` | 2 |
| `source_generated_code` | 7 |
| `source_release` | 4 |
| `source_reply_quality_contracts` | 2 |
| `source_runtime_core` | 14 |
| `source_subconscious` | 4 |
| `source_source_root_inventory` | 4 |
| `source_test_ecosystem` | 30 |
| `source_tool_registry_policy` | 1 |
| `source_web_search` | 3 |
| `source_work_tree` | 8 |

## Test Modules

### `tests/authoritative/test_adaptive_behavior_paths.py`

Tests: 3 | Declared lanes: none

`test_semantic_work_tree_intent_continues_active_tree` (L35), `test_semantic_none_does_not_continue_active_tree_from_text_alone` (L68), `test_semantic_work_tree_intent_sets_identity_when_missing` (L86)

### `tests/authoritative/test_memory_write_filtering.py`

Tests: 14 | Declared lanes: none

`test_text_below_min_chars_is_rejected` (L29), `test_short_declarative_statement_is_accepted` (L35), `test_empty_text_is_rejected` (L41), `test_question_ending_with_mark_is_rejected` (L49), `test_question_without_terminal_mark_is_not_classified_by_phrase` (L55), `test_long_statement_eight_words_is_accepted` (L61), `test_one_word_low_signal_is_rejected` (L70), `test_one_word_thanks_is_low_signal_without_phrase_filter` (L76), `test_prefixed_text_is_not_blocked_by_builtin_phrase_filter` (L84), `test_assistant_source_text_is_not_blocked_by_builtin_phrase_filter` (L90), `test_include_pattern_keeps_otherwise_low_signal_text` (L98), `test_exclude_pattern_rejects_matching_text` (L108), `test_default_min_chars_is_12` (L116), `test_min_chars_respects_policy` (L120)

### `tests/authoritative/test_patch_revision_behavior.py`

Tests: 12 | Declared lanes: none

`test_read_revision_returns_zero_when_file_missing` (L40), `test_write_then_read_round_trips_revision` (L46), `test_write_stores_source_and_timestamp` (L54), `test_write_creates_updates_dir_if_missing` (L64), `test_revision_zero_after_corrupt_file` (L72), `test_manifest_reads_patch_revision_and_min_base` (L82), `test_no_manifest_returns_none_without_error` (L94), `test_invalid_json_manifest_returns_error` (L103), `test_non_object_json_manifest_returns_error` (L113), `test_bad_zip_returns_error` (L122), `test_incoming_must_be_greater_than_current` (L140), `test_min_base_must_not_exceed_current` (L154)

### `tests/authoritative/test_web_routing_behavior.py`

Tests: 11 | Declared lanes: none

`test_web_fetch_blocked_when_web_policy_disabled` (L33), `test_web_fetch_blocked_when_tool_missing` (L43), `test_web_fetch_returns_ok_when_allowed` (L53), `test_web_fetch_returns_allowlist_message_on_not_allowed_error` (L63), `test_web_fetch_returns_fail_on_generic_error` (L73), `test_web_search_blocked_when_policy_disabled` (L86), `test_web_search_blocked_when_missing_tool` (L101), `test_web_search_no_allow_domains_returns_unavailable` (L116), `test_wikipedia_blocked_when_policy_disabled` (L135), `test_wikipedia_blocked_when_web_fn_disabled` (L145), `test_wikipedia_empty_query_returns_usage` (L155)

### `tests/authoritative/test_work_tree_behavior.py`

Tests: 11 | Declared lanes: none

`test_create_tree_produces_active_tree_with_root_branch` (L40), `test_add_branch_creates_child_under_root` (L46), `test_add_task_makes_branch_have_open_tasks` (L54), `test_mark_task_complete_finalizes_branch_when_sole_task` (L62), `test_tree_persists_and_reloads_correctly` (L70), `test_branch_with_no_tools_reports_missing_assignment` (L99), `test_text_does_not_create_branch_tool_assignment` (L109), `test_execute_stops_before_executor_without_assignment` (L120), `test_task_stays_open_without_assignment` (L135), `test_branch_with_declared_tool_proceeds_to_execute` (L149), `test_blocked_tool_returns_wait_not_missing_assignment` (L165)

### `tests/legacy/test_adaptive_path_legacy_behavior.py`

Tests: 1 | Declared lanes: none

`test_legacy_exact_work_tree_wait_reply_text` (L7)

### `tests/legacy/test_core_seam_guard_service.py`

Tests: 2 | Declared lanes: none

`test_run_checks_passes_for_expected_shell_patterns` (L9), `test_run_checks_flags_transport_and_content_drift` (L34)

### `tests/legacy/test_core_seam_locks.py`

Tests: 1 | Declared lanes: none

`test_core_seam_locks` (L273)

### `tests/legacy/test_core_seam_wiring.py`

Tests: 1 | Declared lanes: none

`test_core_seam_wiring_markers_present` (L44)

### `tests/legacy/test_doctor_preflight_seams.py`

Tests: 2 | Declared lanes: none

`test_run_preflight_includes_seam_checks` (L60), `test_run_preflight_fails_required_when_seam_breaks` (L72)

### `tests/legacy/test_http_session_manager.py`

Tests: 74 | Declared lanes: none

`test_dev_mode_toggle_helper` (L84), `test_session_summaries_and_delete` (L97), `test_control_action_session_delete_returns_updated_sessions` (L117), `test_control_self_check_payload` (L136), `test_control_status_payload_includes_runtime_process_note` (L144), `test_control_status_payload_surfaces_control_telemetry_fields` (L179), `test_control_status_payload_surfaces_provider_priority_and_telemetry` (L284), `test_control_action_device_location_update_and_clear` (L324), `test_runtime_timeline_payload_combines_operator_guard_and_boot_events` (L353), `test_runtime_artifacts_payload_summarizes_runtime_files` (L403), `test_runtime_artifact_detail_payload_returns_full_detail` (L436), `test_release_status_payload_summarizes_latest_build_and_promotion` (L457), `test_runtime_restart_analytics_payload_detects_flapping` (L514), `test_runtime_failure_reasons_follow_status_and_timeline` (L537), `test_action_readiness_payload_explains_runtime_controls` (L557), `test_patch_action_readiness_payload_explains_preview_controls` (L569), `test_patch_action_readiness_payload_blocks_missing_preview_zip` (L593), `test_control_status_payload_includes_runtime_timeline` (L611), `test_control_self_check_alerts_when_patch_behavioral_gate_disabled` (L661), `test_control_action_refresh_status_returns_status_snapshot` (L683), `test_control_action_self_check_uses_current_status_policy_and_metrics` (L692), `test_control_action_patch_preview_list_returns_previews_and_patch_status` (L712), `test_control_action_runtime_artifact_show` (L729), `test_control_action_backend_command_list_returns_deck` (L739), `test_control_action_backend_command_run_executes_selected_command` (L749), `test_control_action_backend_command_run_requires_command` (L766), `test_control_action_patch_preview_show_returns_preview_text` (L774), `test_control_action_pulse_status_returns_structured_payload` (L789), `test_control_action_update_now_dry_run_returns_pending_payload` (L806), `test_control_action_patch_preview_approve_records_decision` (L820), `test_control_action_patch_preview_reject_records_decision` (L834), `test_control_action_patch_preview_apply_runs_patch_apply_for_approved_eligible_preview` (L848), `test_control_action_patch_preview_apply_blocks_pending_preview` (L867), `test_control_action_patch_preview_apply_blocks_noneligible_preview` (L881), `test_control_html_smoke_keeps_core_endpoints_and_tabs` (L895), `test_control_script_refresh_guards_parallel_requests` (L1004), `test_test_session_report_summaries_surface_runner_artifacts` (L1016), `test_available_test_session_definitions_reads_saved_sessions` (L1054), `test_available_test_session_definitions_merges_generated_sessions_and_skips_manifests` (L1075), `test_available_test_session_definitions_reads_nested_real_world_tasks` (L1106), `test_control_status_payload_includes_subconscious_summary` (L1136), `test_subconscious_live_summary_surfaces_replan_reasons_and_thresholds` (L1203), `test_control_action_test_session_run_executes_runner` (L1226), `test_control_action_real_world_task_create_writes_generated_definition` (L1245), `test_control_action_operator_prompt_routes_through_process_chat` (L1269), `test_control_action_operator_prompt_uses_saved_macro` (L1291), `test_control_action_operator_prompt_renders_macro_placeholders` (L1313), `test_control_action_operator_prompt_requires_required_macro_placeholder` (L1353), `test_control_action_operator_prompt_requires_message` (L1373), `test_control_action_generated_pack_run_executes_generated_definitions` (L1380), `test_control_action_generated_pack_run_priority_prefers_highest_priority` (L1404), `test_generated_work_queue_prefers_open_priority_items` (L1422), `test_control_action_generated_queue_run_next_executes_selected_item` (L1441), `test_control_action_generated_queue_investigate_routes_to_operator_prompt` (L1467), `test_export_capabilities_snapshot` (L1508), `test_control_action_export_ledger_and_bundle` (L1520), `test_control_login_action_wrapper_delegates_to_service` (L1559), `test_control_logout_action_wrapper_delegates_to_service` (L1572), `test_chat_login_action_wrapper_delegates_to_service` (L1586), `test_chat_logout_action_wrapper_delegates_to_service` (L1599), `test_control_action_nova_start` (L1613), `test_control_action_core_stop` (L1629), `test_control_action_guard_restart` (L1640), `test_control_action_webui_restart` (L1651), `test_control_action_autonomy_maintenance_start` (L1661), `test_control_action_autonomy_maintenance_stop` (L1671), `test_webui_restart_allows_fresh_control_status_hydration` (L1681), `test_start_guard_clears_stale_stop_flag` (L1749), `test_control_action_chat_user_management_uses_managed_file` (L1769), `test_control_action_memory_scope_set_updates_policy` (L1790), `test_control_action_search_endpoint_set_updates_policy` (L1811), `test_control_action_search_endpoint_probe_returns_probe_details` (L1832), `test_control_action_search_provider_priority_set_updates_policy` (L1841), `test_api_chat_success_invalidates_control_status_cache` (L1866)

### `tests/runtime/test_http_live_paths.py`

Tests: 2 | Declared lanes: none

`test_live_chat_route_returns_non_empty_reply` (L10), `test_live_session_remains_responsive_across_followup_turns` (L29)

### `tests/test_action_planner.py`

Tests: 3 | Declared lanes: `unit`

`test_static_planner_no_longer_routes_from_surface_text` (L11), `test_classify_route_returns_no_static_route` (L21), `test_classify_route_with_context_ignores_legacy_context_parser` (L31)

### `tests/test_autonomy_execution_gate.py`

Tests: 8 | Declared lanes: `unit`

`test_allows_canary_dispatch_for_policy_enabled_recommendation` (L39), `test_blocks_when_action_not_execute_allowed` (L47), `test_allows_action_when_execution_group_is_allowed` (L57), `test_allows_concrete_active_work_tree_below_generic_confidence_threshold` (L67), `test_explicit_block_wins_over_execution_group_allow` (L80), `test_defers_when_decision_is_not_recommend_action` (L94), `test_defers_when_cooldown_is_active` (L104), `test_allows_same_branch_when_cooldown_was_for_different_work_tree_task` (L119)

### `tests/test_autonomy_maintenance.py`

Tests: 93 | Declared lanes: `unit`

`test_queue_pressure_uses_open_count_zero_as_clear_truth` (L61), `test_queue_pressure_falls_back_to_count_only_when_open_count_missing` (L78), `test_queue_pressure_clear_status_without_open_count_does_not_invent_pending_work` (L93), `test_sync_regression_status_from_file_uses_newer_canonical_status` (L108), `test_daily_regression_uses_canonical_regression_runner` (L139), `test_run_temporal_feed_pass_reads_ics_and_surfaces_pressure` (L180), `test_sync_signal_intake_work_tree_includes_temporal_feed_payload` (L217), `test_subconscious_pack_timeout_uses_positive_timeout_evidence` (L262), `test_run_once_logs_cycle_duration_on_subconscious_failure` (L287), `test_archive_stale_complete_trees_keeps_recent_history_visible` (L303), `test_archive_empty_active_trees_archives_only_old_root_shells` (L333), `test_archive_stale_cli_active_trees_archives_only_simple_prompt_shells` (L363), `test_run_once_records_generated_queue_outcome` (L426), `test_run_once_syncs_signal_intake_before_orchestrator_execution` (L620), `test_execute_autonomy_recommendation_uses_dispatcher_for_canary_action` (L700), `test_execute_autonomy_recommendation_dispatches_guard_start_runtime_control_action` (L769), `test_execute_autonomy_recommendation_dispatches_maintenance_start_runtime_control_action` (L805), `test_execute_autonomy_recommendation_dispatches_patch_queue_conduit_action` (L851), `test_execute_autonomy_recommendation_dispatches_generated_queue_investigate_in_maintenance_scope` (L891), `test_execute_autonomy_recommendation_dispatches_active_work_tree_conduit_action` (L930), `test_execute_autonomy_recommendation_treats_active_work_tree_tool_failed_as_failed` (L970), `test_execute_autonomy_recommendation_honors_active_work_tree_step_budget` (L1026), `test_execute_autonomy_recommendation_honors_active_work_tree_target` (L1068), `test_run_worker_loops_for_bounded_cycles_and_records_status` (L1114), `test_non_loop_cycle_clears_dead_runtime_worker_identity` (L1147), `test_non_loop_cycle_preserves_live_loop_worker_identity` (L1179), `test_non_loop_cycle_clears_stale_flag_after_identity_was_removed` (L1199), `test_run_worker_uses_worker_loop_context_for_default_cycle` (L1223), `test_autonomy_orchestrator_advisory_records_state_and_ledger` (L1247), `test_orchestrator_input_envelope_carries_maintenance_worker_surface` (L1311), `test_orchestrator_input_envelope_green_cycle_includes_mission_snapshot` (L1340), `test_mission_hold_blocks_legacy_generated_queue_execution` (L1420), `test_mission_hold_blocks_legacy_active_work_tree_execution` (L1498), `test_mission_green_hold_allows_targeted_core_thinning_execution` (L1521), `test_release_drift_hold_allows_targeted_core_thinning_execution` (L1564), `test_autonomy_orchestrator_status_for_signal_ingestion_includes_execution_failure` (L1624), `test_run_autonomy_orchestrator_persists_mission_snapshot` (L1656), `test_triage_hints_for_orchestrator_use_live_subconscious_triage` (L1711), `test_subconscious_triage_signals_use_evidence_first_work_tree_tasks` (L1764), `test_subconscious_triage_skips_candidate_with_no_owner_root_judgment` (L1806), `test_run_once_marks_failed_regression_stale_when_regression_is_skipped` (L1872), `test_sync_signal_intake_work_tree_creates_regression_branch_for_live_failure` (L1974), `test_live_control_status_fetch_uses_release_safe_timeout` (L2007), `test_live_control_status_enriches_missing_model_runtime_keys_from_local_probe` (L2029), `test_local_first_status_uses_surfaces_timeout_and_merges_supplement_keys` (L2085), `test_local_first_status_falls_back_to_local_when_surfaces_fetch_fails` (L2129), `test_local_dependency_probe_enriches_layer_maturity_observe_mode` (L2148), `test_local_dependency_probe_enriches_frontdoor_cli_surfaces` (L2167), `test_local_dependency_probe_enriches_runtime_control_surfaces` (L2180), `test_local_first_preserves_http_root_closure_inventory` (L2203), `test_merge_authoritative_wiring_status_keys_pulls_web_enabled_from_http` (L2243), `test_local_dependency_probe_closes_core_gate_roots_without_http` (L2271), `test_apply_release_runtime_truth_adds_drift_summary_and_http_probe` (L2315), `test_release_drift_invalidates_control_status_cache_once` (L2355), `test_live_control_status_timeout_preserves_local_ollama_failure_for_ingestion` (L2374), `test_sync_signal_intake_work_tree_uses_local_validation_truth_when_http_falls_back` (L2399), `test_sync_signal_intake_work_tree_resolves_stale_regression_branch` (L2447), `test_sync_signal_intake_work_tree_passes_memory_health_bootstrap_gap` (L2485), `test_sync_generated_queue_work_tree_creates_actionable_branch` (L2534), `test_execute_generated_queue_planned_action_treats_reported_drift_as_completed_run` (L2600), `test_run_patch_queue_cleanup_records_reductions` (L2632), `test_auto_apply_if_eligible_skips_definition_only_zip_without_preview` (L2677), `test_run_patch_queue_cleanup_rejects_definition_only_noop_preview` (L2693), `test_run_patch_queue_cleanup_archives_rejected_previews` (L2744), `test_run_patch_queue_cleanup_archives_stale_noneligible_previews` (L2792), `test_sync_patch_queue_work_tree_creates_apply_branch` (L2840), `test_sync_patch_queue_work_tree_selects_single_auto_approval_branch` (L2877), `test_decide_patch_queue_next_step_prefers_apply_then_approve` (L2936), `test_sync_patch_queue_work_tree_reuses_branch_when_preview_transitions` (L2965), `test_run_patch_queue_work_tree_cycle_records_execution` (L3007), `test_run_active_work_tree_cycle_executes_safe_tree_and_skips_unsafe_tool` (L3054), `test_run_active_work_tree_cycle_executes_os_capability_lane` (L3088), `test_run_active_work_tree_cycle_executes_core_thinning_lane` (L3129), `test_run_active_work_tree_cycle_executes_release_validation_lane` (L3170), `test_run_active_work_tree_cycle_honors_target_branch_and_task` (L3206), `test_run_active_work_tree_cycle_resolves_target_tree_outside_candidate_window` (L3249), `test_run_active_work_tree_cycle_keeps_task_open_after_tool_failed` (L3306), `test_run_active_work_tree_cycle_uses_target_tree_for_pinned_branch` (L3339), `test_operator_continue_work_answer_feeds_next_active_work_tree_cycle` (L3388), `test_work_tree_pressure_truth_prefers_module_counts_over_stale_payload` (L3476), `test_work_tree_snapshot_uses_active_candidate_execution_truth` (L3503), `test_orchestrator_executed_lane_cycle_preserves_active_cycle_truth` (L3539), `test_run_active_work_tree_cycle_stops_after_one_attempt` (L3569), `test_run_active_work_tree_cycle_empty_history_still_consumes_attempt` (L3617), `test_run_active_work_tree_cycle_resyncs_core_thinning_before_execution` (L3654), `test_retire_legacy_patch_update_trees_drops_open_tasks_and_completes_tree` (L3707), `test_run_patch_queue_work_tree_cycle_resyncs_from_approve_into_apply` (L3740), `test_sync_patch_queue_work_tree_reuses_legacy_seeded_branch` (L3791), `test_sync_patch_queue_work_tree_keeps_incompatible_base_preview_in_review_lane` (L3847), `test_webui_health_requires_live_pid_port_and_http` (L3887), `test_ensure_operator_webui_running_waits_on_transient_degraded_health` (L3900), `test_ensure_operator_webui_running_uses_launcher_when_port_is_down` (L3912), `test_ensure_operator_webui_running_never_restarts_over_open_port` (L3931)

### `tests/test_autonomy_orchestrator_ledger_service.py`

Tests: 3 | Declared lanes: `unit`

`test_summary_tracks_churn_and_weak_posture_refusals` (L10), `test_summary_returns_empty_shape_when_ledger_missing` (L60), `test_summary_accepts_spec_v01_rows` (L68)

### `tests/test_autonomy_orchestrator_service.py`

Tests: 38 | Declared lanes: `unit`

`test_evaluate_next_action_recommends_single_spec_action_and_records_ledger` (L206), `test_evaluate_next_action_only_recommends_dispatcher_owned_action` (L229), `test_evaluate_next_action_recommends_patch_queue_conduit_when_patch_ready` (L239), `test_evaluate_next_action_scores_generated_queue_with_triage_lane_pressure` (L261), `test_evaluate_next_action_recommends_active_work_tree_conduit` (L312), `test_evaluate_next_action_recommends_maintenance_worker_start_from_worker_evidence` (L339), `test_evaluate_next_action_does_not_start_worker_when_guard_scheduler_is_active` (L360), `test_evaluate_next_action_recommends_concrete_active_work_tree_in_watch_posture` (L383), `test_active_work_tree_cooldown_is_branch_aware_for_evidence_steps` (L415), `test_active_work_tree_cooldown_is_task_aware_within_same_branch` (L449), `test_evaluate_next_action_prefers_concrete_active_lane_over_pulse` (L486), `test_evaluate_next_action_blocks_when_policy_disables_autonomy` (L541), `test_evaluate_next_action_defers_when_runtime_evidence_is_stale` (L557), `test_evaluate_next_action_blocks_disallowed_candidate` (L570), `test_evaluate_next_action_defers_when_ack_required` (L584), `test_operator_hold_does_not_turn_into_generic_queue_investigation` (L596), `test_blocked_observing_work_tree_does_not_become_generated_queue_ack_hold` (L616), `test_evaluate_next_action_defers_for_active_cooldown` (L637), `test_evaluate_next_action_prefers_investigate_when_pending_is_fully_blocked` (L654), `test_evaluate_next_action_blocks_when_posture_is_red` (L679), `test_evaluate_next_action_blocks_when_critical_alert_is_active` (L693), `test_evaluate_next_action_defers_when_primary_evidence_is_stale` (L707), `test_evaluate_next_action_defers_when_evidence_conflicts` (L723), `test_evaluate_next_action_defers_when_no_legal_action_exists` (L738), `test_evaluate_next_action_holds_green_mission_over_seam_pressure_probe` (L748), `test_evaluate_next_action_holds_green_mission_over_investigate_candidate` (L772), `test_evaluate_next_action_holds_green_mission_over_generated_queue_run_next` (L790), `test_evaluate_next_action_holds_green_mission_over_active_work_tree_run_next` (L819), `test_evaluate_next_action_allows_core_thinning_under_green_mission_hold` (L849), `test_evaluate_next_action_allows_core_thinning_when_release_drift_blocks_green` (L882), `test_evaluate_next_action_holds_green_mission_over_codegen_run` (L942), `test_evaluate_next_action_holds_validation_required_mission_without_green_cycle` (L983), `test_evaluate_next_action_runs_generated_queue_to_clear_own_truth_blocker` (L1054), `test_evaluate_next_action_defers_below_recommendation_threshold` (L1113), `test_evaluate_next_action_defers_when_top_candidates_tie` (L1132), `test_set_mode_keeps_execution_policy_guarded` (L1159), `test_evaluate_next_action_recommends_guard_start_when_guard_not_running` (L1170), `test_evaluate_next_action_only_emits_allowed_spec_decisions` (L1181)

### `tests/test_behavior_metrics_service.py`

Tests: 2 | Declared lanes: `unit`

`test_record_event_increments_counter_and_persists` (L10), `test_update_from_reflection_updates_expected_fields` (L26)

### `tests/test_capability_gap_detector.py`

Tests: 17 | Declared lanes: `source_generated_code`

`test_detect_no_gaps_when_all_capabilities_registered` (L36), `test_detect_gaps_when_capabilities_missing` (L59), `test_detect_gaps_case_insensitive` (L82), `test_detect_gaps_returns_empty_without_roadmap` (L99), `test_detect_gaps_returns_empty_without_capabilities` (L110), `test_enhance_status_with_gaps` (L123), `test_enhance_status_preserves_existing_fields` (L146), `test_service_exposes_all_methods` (L169), `test_signal_class_is_valid` (L182), `test_signal_class_maps_to_work_class` (L187), `test_capability_gap_in_bucket_mappings` (L192), `test_signal_generated_when_gaps_present` (L205), `test_signal_not_generated_when_no_gaps` (L245), `test_signal_not_generated_without_capability_surface` (L257), `test_signal_title_reflects_gap_count` (L268), `test_signal_task_sequence_includes_roadmap_review` (L304), `test_leah_gap_uses_leah_build_execution_group` (L344)

### `tests/test_chat_identity_service.py`

Tests: 6 | Declared lanes: `unit`

`test_chat_users_reads_managed_file_with_normalized_names` (L10), `test_new_chat_session_and_login_auth_use_session_store` (L24), `test_save_managed_chat_users_hashes_plaintext_passwords` (L49), `test_chat_login_action_returns_cookie_and_user_id` (L64), `test_chat_login_action_rejects_invalid_credentials` (L78), `test_chat_logout_action_clears_session_and_returns_cookie_header` (L92)

### `tests/test_codegen_memory_recorder.py`

Tests: 38 | Declared lanes: `source_generated_code`

`test_compute_spec_hash_deterministic` (L36), `test_compute_spec_hash_different_for_different_inputs` (L43), `test_extract_code_patterns_finds_classes` (L51), `test_extract_code_patterns_finds_functions` (L64), `test_extract_code_patterns_finds_exception_handling` (L77), `test_extract_code_patterns_finds_imports` (L90), `test_extract_code_patterns_deduplicates` (L101), `test_extract_test_patterns_finds_test_classes` (L112), `test_extract_test_patterns_finds_test_methods` (L125), `test_extract_test_patterns_finds_assertions` (L139), `test_extract_test_patterns_finds_mocking` (L149), `test_extract_test_patterns_finds_setup_teardown` (L159), `test_record_pattern_returns_pattern_id` (L177), `test_record_pattern_creates_store_file` (L190), `test_record_pattern_writes_valid_json` (L202), `test_record_pattern_includes_patterns` (L219), `test_record_pattern_stores_generation_context` (L236), `test_lookup_by_capability_returns_empty_when_no_store` (L257), `test_lookup_by_capability_finds_matching_patterns` (L264), `test_lookup_by_capability_case_insensitive` (L286), `test_lookup_by_capability_respects_limit` (L299), `test_lookup_by_capability_returns_newest_first` (L314), `test_lookup_by_spec_finds_exact_matches` (L336), `test_lookup_by_spec_with_capability_filter` (L351), `test_lookup_by_spec_returns_empty_when_no_match` (L374), `test_build_injection_context_exact_spec_match` (L385), `test_build_injection_context_capability_fallback` (L400), `test_build_injection_context_empty_when_no_patterns` (L413), `test_format_pattern_context_includes_capability_name` (L420), `test_format_pattern_context_includes_code_patterns` (L433), `test_format_pattern_context_includes_test_patterns` (L447), `test_service_singleton_exposes_record_pattern` (L464), `test_service_singleton_exposes_lookup_by_capability` (L476), `test_service_singleton_exposes_lookup_by_spec` (L489), `test_service_singleton_exposes_memory_injection_context` (L503), `test_record_pattern_raises_on_io_error` (L523), `test_lookup_handles_corrupted_json_gracefully` (L540), `test_lookup_handles_missing_fields_gracefully` (L551)

### `tests/test_codegen_patch_bridge.py`

Tests: 13 | Declared lanes: `source_generated_code`

`test_validate_valid_preview` (L18), `test_validate_rejects_invalid_schema` (L50), `test_validate_rejects_non_preview` (L62), `test_validate_rejects_missing_spec` (L74), `test_validate_rejects_artifact_count_mismatch` (L86), `test_bridge_creates_valid_patch_artifact` (L143), `test_bridge_generates_test_files` (L155), `test_bridge_preserves_spec_metadata` (L168), `test_bridge_captures_provenance` (L178), `test_bridge_manifest_includes_governance_gates` (L193), `test_format_summary` (L208), `test_summary_is_readable` (L237), `test_service_exposes_all_methods` (L267)

### `tests/test_codegen_tool.py`

Tests: 6 | Declared lanes: `source_generated_code`

`test_preview_returns_preview_only_artifacts` (L25), `test_codegen_requires_policy_enablement` (L52), `test_codegen_rejects_unsafe_path` (L75), `test_preview_includes_memory_injection_when_patterns_available` (L91), `test_preview_handles_memory_injection_failure_gracefully` (L121), `test_preview_omits_injection_context_when_no_patterns` (L147)

### `tests/test_control_actions_service.py`

Tests: 3 | Declared lanes: `unit`

`test_refresh_status_action_returns_status_snapshot` (L7), `test_device_location_update_invalidates_cache_on_success` (L17), `test_self_check_action_uses_summary_as_message` (L31)

### `tests/test_control_assets_service.py`

Tests: 2 | Declared lanes: `unit`

`test_render_control_html_replaces_asset_tokens` (L9), `test_read_asset_text_returns_missing_asset_fallback` (L29)

### `tests/test_control_auth_service.py`

Tests: 7 | Declared lanes: `unit`

`test_control_login_enabled_reads_env_pair` (L8), `test_new_control_session_and_login_auth_use_cookie_store` (L12), `test_control_page_gate_blocks_remote_without_token` (L35), `test_control_api_auth_accepts_matching_token` (L47), `test_control_login_action_returns_cookie_header_on_success` (L60), `test_control_login_action_rejects_bad_credentials` (L73), `test_control_logout_action_clears_session_and_returns_cookie_header` (L85)

### `tests/test_control_pipelines_service.py`

Tests: 7 | Declared lanes: `source_data_pipelines`

`test_payload_includes_selected_pipeline_detail` (L12), `test_append_note_scopes_to_pipeline_intake_log` (L30), `test_create_pause_start_and_archive_lane` (L52), `test_created_lane_can_be_paused_before_execution` (L107), `test_update_lane_metadata_edits_manifest_without_renaming_lane` (L136), `test_upsert_population_definition_scopes_to_lane` (L176), `test_run_query_preview_delegates_to_registry` (L236)

### `tests/test_control_status_cache_service.py`

Tests: 2 | Declared lanes: `unit`

`test_invalidate_resets_cache` (L8), `test_cached_payload_reuses_recent_value` (L17)

### `tests/test_control_status_service.py`

Tests: 13 | Declared lanes: `unit`

`test_runtime_supplier_fns_from_scope_collects_http_supplier_contract` (L7), `test_runtime_status_payload_collects_supplier_outputs` (L63), `test_runtime_signal_ingestion_surfaces_payload_uses_thin_work_tree_pressure` (L333), `test_status_payload_includes_voice_runtime_fields_when_provided` (L414), `test_status_payload_keeps_old_os_capability_failures_as_history_not_live_pressure` (L491), `test_status_payload_counts_release_validation_gap_as_self_repair_blocked` (L569), `test_status_payload_includes_runtime_timeline_and_patch_fields` (L651), `test_status_payload_includes_subconscious_and_queue_fields` (L850), `test_status_payload_ignores_legacy_last_provider_when_priority_removed` (L949), `test_status_payload_treats_nullish_provider_values_as_no_provider_hit` (L1005), `test_status_payload_splits_operator_hold_from_self_repair_truth` (L1061), `test_status_payload_marks_guard_scheduled_maintenance_when_worker_is_not_persistent` (L1145), `test_status_payload_includes_storage_watch_fields_when_provided` (L1209)

### `tests/test_control_status_surfaces_service.py`

Tests: 6 | Declared lanes: `source_http_api_control`, `unit`

`test_derive_surfaces_url_appends_surfaces_suffix` (L12), `test_extract_signal_ingestion_surfaces_keeps_wiring_keys_only` (L18), `test_merge_http_supplement_preserves_local_authoritative_inventory` (L63), `test_release_drift_detected_matches_source_changed_after_build` (L90), `test_merge_http_supplement_preserves_local_frontdoor_cli_surfaces` (L96), `test_merge_http_supplement_prefers_http_root_closure_inventory` (L118)

### `tests/test_control_telemetry_service.py`

Tests: 12 | Declared lanes: `unit`

`test_action_ledger_summary_aggregates_recent_records` (L11), `test_tool_events_summary_computes_latency_and_statuses` (L50), `test_tool_events_summary_marks_error_stale_after_later_success` (L75), `test_memory_events_summary_counts_actions` (L95), `test_build_self_check_flags_missing_allow_domains` (L117), `test_build_self_check_flags_validation_artifact_truth_gap` (L140), `test_metrics_helpers_append_and_read_payload` (L176), `test_provider_telemetry_payload_filters_to_active_provider_family` (L201), `test_provider_telemetry_payload_ignores_nullish_provider_values` (L233), `test_tail_log_action_rejects_unknown_names` (L260), `test_export_ledger_summary_action_writes_json` (L274), `test_export_diagnostics_bundle_action_from_runtime_writes_bundle` (L293)

### `tests/test_control_work_trees_service.py`

Tests: 3 | Declared lanes: `source_work_tree`

`test_payload_summarizes_visible_tree_counts` (L7), `test_payload_keeps_priority_tree_visible_when_trimmed` (L53), `test_payload_semantically_dedupes_runtime_ops_shells` (L98)

### `tests/test_core_health_brief_service.py`

Tests: 4 | Declared lanes: `source_test_ecosystem`

`test_build_brief_turns_existing_health_signals_into_repair_orders` (L35), `test_training_pressure_without_drift_is_advisory_not_repair` (L72), `test_enforced_cleanup_pressure_is_advisory_not_repair` (L126), `test_feed_brief_creates_deduped_core_health_work_tree` (L145)

### `tests/test_core_seam_guard_service.py`

Tests: 2 | Declared lanes: `source_runtime_core`

`test_run_checks_passes_for_expected_shell_patterns` (L9), `test_run_checks_flags_transport_and_content_drift` (L47)

### `tests/test_core_steward_service.py`

Tests: 7 | Declared lanes: `unit`

`test_build_payload_flags_repair_when_required_checks_fail` (L7), `test_render_core_steward_includes_queue_and_score` (L27), `test_build_core_steward_gates_blocks_patch_and_release_when_level_is_watch` (L58), `test_build_core_steward_gates_allows_release_when_ready_and_strong` (L69), `test_build_payload_keeps_runtime_strong_when_pressure_is_only_training_and_enforced_cleanup` (L79), `test_build_payload_watches_memory_health` (L109), `test_build_payload_accepts_guard_tick_scheduler` (L134)

### `tests/test_core_thinning_service.py`

Tests: 18 | Declared lanes: `source_test_ecosystem`

`test_build_brief_finds_wrapper_and_large_function_candidates` (L37), `test_build_brief_can_cover_core_and_http_surfaces` (L61), `test_build_brief_finds_http_surface_candidates` (L78), `test_owner_verdict_marks_thinning_orders_as_non_green_blocking_pressure` (L112), `test_owner_verdict_blocks_green_when_thinning_evidence_is_unavailable` (L131), `test_feed_brief_creates_deduped_core_thinning_tree` (L141), `test_execute_core_thinning_order_removes_unused_wrapper` (L166), `test_execute_core_thinning_order_resolves_wrapper_line_drift` (L193), `test_execute_core_thinning_order_resolves_line_drift_before_caller_block` (L228), `test_execute_core_thinning_order_blocks_runtime_hook_reference` (L262), `test_execute_core_thinning_order_blocks_wrapper_with_callers` (L303), `test_build_brief_protects_referenced_wrapper_from_work_orders` (L333), `test_build_brief_protects_service_hook_map_wrappers` (L357), `test_build_brief_protects_service_core_attribute_references` (L379), `test_build_brief_protects_public_runtime_adapters` (L413), `test_execute_core_thinning_order_blocks_public_runtime_adapter` (L443), `test_execute_core_thinning_order_blocks_wrapper_used_as_callable_hook` (L473), `test_execute_core_thinning_order_maps_http_boundary_without_mutation` (L502)

### `tests/test_data_pipeline_registry_service.py`

Tests: 9 | Declared lanes: none

`test_list_pipeline_summaries_includes_sis_test` (L25), `test_get_pipeline_status_reports_read_only_pipeline` (L30), `test_get_pipeline_schema_probe_returns_grounded_tables` (L37), `test_search_pipeline_vendor_dictionary_finds_core_columns` (L47), `test_plan_pipeline_report_matches_population_and_candidate_tables` (L63), `test_preview_pipeline_query_returns_governed_dry_run` (L92), `test_preview_schema_inventory_uses_twenty_row_guard` (L104), `test_preview_pipeline_query_blocks_paused_lane` (L118), `test_run_pipeline_query_requests_live_mode` (L139)

### `tests/test_decision_pipeline.py`

Tests: 1 | Declared lanes: `source_data_pipelines`

`test_registry_runs_in_priority_order_and_marks_skipped_stages` (L8)

### `tests/test_edfi_bisd_pipeline.py`

Tests: 7 | Declared lanes: `source_data_lane_edfi_bisd`

`test_registry_discovers_edfi_bisd` (L28), `test_status_reports_edfi_lane` (L33), `test_schema_probe_lists_templates` (L50), `test_preview_list_schools_dry_run` (L68), `test_live_list_schools_returns_rows` (L90), `test_preview_sync_status_dry_run` (L123), `test_list_summaries_includes_lane_state` (L146)

### `tests/test_edfi_change_tracking.py`

Tests: 4 | Declared lanes: `source_edfi_core`

`test_fetch_available_change_versions_reads_root_manifest` (L31), `test_save_and_load_sync_state_round_trip` (L53), `test_pull_changes_since_uses_data_api_when_change_query_404` (L73), `test_sync_status_reports_cursor_map` (L121)

### `tests/test_edfi_core.py`

Tests: 17 | Declared lanes: `source_edfi_core`

`test_golden_rule_no_domain_imports_in_edfi_package` (L62), `test_connection_config_validation_matrix` (L74), `test_connection_config_requires_complete_credentials` (L112), `test_nova_edfi_001_self_profile_happy_path` (L117), `test_self_profile_fails_closed_when_auth_fails_401` (L178), `test_self_profile_auth_forbidden_403` (L198), `test_self_profile_config_missing_url` (L215), `test_self_profile_invalid_connection_json` (L230), `test_partial_discovery_metadata_ok_sample_failed` (L240), `test_discover_metadata_falls_back_to_root_dependencies` (L269), `test_fetch_token_retries_with_basic_auth_on_invalid_request` (L321), `test_auth_transport_error_classification` (L340), `test_expired_token_is_refreshed` (L364), `test_client_get_resource_name_resolves_under_api_root` (L382), `test_profile_path_is_scoped_by_connection_id` (L398), `test_audit_log_lines_are_valid_json` (L402), `test_classify_request_exception_helper` (L414)

### `tests/test_edfi_core_lifecycle_demo.py`

Tests: 1 | Declared lanes: `source_edfi_core`

`test_demo_runs_cold_start_to_operational` (L14)

### `tests/test_edfi_core_readiness.py`

Tests: 5 | Declared lanes: `source_edfi_core`

`test_readiness_reports_operational_when_core_contract_is_complete` (L33), `test_readiness_reports_blocked_when_profile_is_missing` (L66), `test_readiness_reports_blocked_when_district_lea_id_is_missing` (L86), `test_readiness_marks_sync_status_present_without_requiring_it` (L108), `test_live_runtime_readiness_when_bisd_contract_is_present` (L141)

### `tests/test_edfi_district_scope.py`

Tests: 7 | Declared lanes: `source_edfi_core`

`test_normalize_accepts_numeric_strings` (L15), `test_school_filter_uses_lea_reference` (L20), `test_lea_resource_filters_direct_id` (L24), `test_tea_uses_client_side_filter` (L28), `test_item_matches_district_by_lea_reference` (L33), `test_item_matches_district_by_school_id_prefix` (L41), `test_merge_filter_params_combines_clauses` (L45)

### `tests/test_edfi_inventory.py`

Tests: 4 | Declared lanes: `source_edfi_core`

`test_profile_summary` (L64), `test_list_resources_filters_query_and_namespace` (L73), `test_read_resource_delegates_to_get_page` (L85), `test_read_preset_tries_candidates` (L108)

### `tests/test_edfi_profile_evidence.py`

Tests: 13 | Declared lanes: `source_edfi_core`

`test_build_evidence_from_saved_profile_without_api` (L41), `test_missing_profile_reports_failure` (L64), `test_healthy_profile_without_cursor_state_omits_sync_status` (L80), `test_saved_change_cursors_attach_optional_sync_status_without_affecting_ok` (L99), `test_get_district_layer_facts_returns_only_safe_profile_fields` (L142), `test_get_district_layer_facts_includes_optional_sync_status` (L191), `test_capability_profile_payload_valid_requires_auth_resources_and_timestamp` (L216), `test_profile_read_evidence_valid_accepts_saved_profile_read` (L233), `test_profile_read_evidence_valid_rejects_missing_file_read` (L241), `test_profile_read_evidence_valid_rejects_wrong_path` (L249), `test_audit_runtime_profile_contract_checks_bisd_contract` (L257), `test_audit_runtime_profile_contract_fails_on_lea_or_resource_mismatch` (L284), `test_live_runtime_profile_matches_bisd_contract_when_present` (L311)

### `tests/test_edfi_resources.py`

Tests: 23 | Declared lanes: `source_edfi_core`

`test_list_body` (L51), `test_dict_body_returns_empty` (L54), `test_none_body_returns_empty` (L57), `test_empty_list` (L60), `test_happy_path_returns_items` (L68), `test_limit_capped_at_max` (L84), `test_offset_passed_through` (L94), `test_filter_params_merged` (L104), `test_server_error_returns_not_ok` (L115), `test_non_list_response_body_not_ok` (L127), `test_429_triggers_backoff_and_retry` (L140), `test_429_both_attempts_fail` (L162), `test_audit_event_written_when_requested` (L177), `test_no_audit_by_default` (L189), `test_collects_only_matching_rows` (L209), `test_single_page_exhausted` (L232), `test_multi_page_fetch` (L246), `test_limit_cap_truncation` (L261), `test_max_limit_cap_enforced` (L274), `test_first_page_error_returns_not_ok` (L283), `test_error_mid_page_stops_and_returns_partial` (L295), `test_audit_event_written` (L307), `test_offset_advances_per_page` (L322)

### `tests/test_end_to_end_wiring_service.py`

Tests: 1 | Declared lanes: `source_source_root_inventory`, `unit`

`test_offline_wiring_check_closes_source_self_repair_lane` (L9)

### `tests/test_evidence_validity.py`

Tests: 6 | Declared lanes: `source_test_ecosystem`, `unit`

`test_specific_ollama_chat_failures_are_not_valid_evidence` (L7), `test_fail_marker_is_not_valid_evidence` (L16), `test_no_allowlisted_web_results_is_valid_non_failure_evidence` (L25), `test_structured_judgment_false_ok_is_valid_evidence` (L34), `test_read_source_with_ok_false_literal_is_valid_evidence` (L48), `test_structured_json_tool_failure_is_not_valid_evidence` (L57)

### `tests/test_frontdoor_cli_parity_service.py`

Tests: 4 | Declared lanes: `source_http_api_control`, `unit`

`test_build_surfaces_reports_ok_for_real_repo` (L10), `test_build_surfaces_marks_missing_frontdoor_as_missing` (L25), `test_build_surfaces_marks_malformed_backend_commands_unreadable` (L33), `test_local_frontdoor_surfaces_do_not_raise_frontdoor_cli_signal` (L39)

### `tests/test_fulfillment_flow_service.py`

Tests: 5 | Declared lanes: `unit`

`test_should_attempt_when_fulfillment_route_is_clear` (L12), `test_should_not_attempt_when_supervisor_route_wins` (L30), `test_render_single_result_reply` (L48), `test_render_multi_choice_reply` (L69), `test_maybe_run_marks_generic_fallback_when_not_viable` (L86)

### `tests/test_health.py`

Tests: 7 | Declared lanes: `unit`

`test_check_heartbeat_missing` (L15), `test_check_state_invalid_pid` (L23), `test_check_heartbeat_stale` (L32), `test_run_check_skip_ollama_allows_base_package_profile` (L43), `test_run_check_requires_ollama_by_default` (L64), `test_required_models_follow_policy_models` (L78), `test_repair_does_not_restart_when_server_endpoint_is_reachable` (L88)

### `tests/test_health_check_script.py`

Tests: 1 | Declared lanes: `source_test_ecosystem`

`test_suite_command_targets_unit_lane_runner` (L14)

### `tests/test_http_chat_flow.py`

Tests: 6 | Declared lanes: `behavior`

`test_prepare_chat_turn_appends_user_text_without_route_rewrite` (L7), `test_resume_requires_session_id` (L22), `test_resume_no_turns` (L37), `test_resume_no_pending_user_turn` (L53), `test_resume_success` (L69), `test_resume_success_from_runtime_scope` (L96)

### `tests/test_http_session_manager.py`

Tests: 74 | Declared lanes: `behavior`

`test_dev_mode_toggle_helper` (L92), `test_session_summaries_and_delete` (L105), `test_control_action_session_delete_returns_updated_sessions` (L125), `test_control_self_check_payload` (L144), `test_control_status_payload_includes_runtime_process_note` (L152), `test_control_status_payload_surfaces_control_telemetry_fields` (L187), `test_control_status_payload_surfaces_provider_priority_and_telemetry` (L292), `test_control_action_device_location_update_and_clear` (L332), `test_runtime_timeline_payload_combines_operator_guard_and_boot_events` (L361), `test_runtime_artifacts_payload_summarizes_runtime_files` (L411), `test_runtime_artifact_detail_payload_returns_full_detail` (L444), `test_release_status_payload_summarizes_latest_build_and_promotion` (L465), `test_runtime_restart_analytics_payload_detects_flapping` (L522), `test_runtime_failure_reasons_follow_status_and_timeline` (L545), `test_action_readiness_payload_explains_runtime_controls` (L565), `test_patch_action_readiness_payload_explains_preview_controls` (L577), `test_patch_action_readiness_payload_blocks_missing_preview_zip` (L601), `test_control_status_payload_includes_runtime_timeline` (L619), `test_control_self_check_alerts_when_patch_behavioral_gate_disabled` (L669), `test_control_action_refresh_status_returns_status_snapshot` (L691), `test_control_action_self_check_uses_current_status_policy_and_metrics` (L700), `test_control_action_patch_preview_list_returns_previews_and_patch_status` (L720), `test_control_action_runtime_artifact_show` (L737), `test_control_action_backend_command_list_returns_deck` (L747), `test_control_action_backend_command_run_executes_selected_command` (L757), `test_control_action_backend_command_run_requires_command` (L774), `test_control_action_patch_preview_show_returns_preview_text` (L782), `test_control_action_pulse_status_returns_structured_payload` (L797), `test_control_action_update_now_dry_run_returns_pending_payload` (L814), `test_control_action_patch_preview_approve_records_decision` (L828), `test_control_action_patch_preview_reject_records_decision` (L842), `test_control_action_patch_preview_apply_runs_patch_apply_for_approved_eligible_preview` (L856), `test_control_action_patch_preview_apply_blocks_pending_preview` (L875), `test_control_action_patch_preview_apply_blocks_noneligible_preview` (L889), `test_control_html_smoke_keeps_core_endpoints_and_tabs` (L903), `test_control_script_refresh_guards_parallel_requests` (L999), `test_test_session_report_summaries_surface_runner_artifacts` (L1011), `test_available_test_session_definitions_reads_saved_sessions` (L1049), `test_available_test_session_definitions_merges_generated_sessions_and_skips_manifests` (L1070), `test_available_test_session_definitions_reads_nested_real_world_tasks` (L1101), `test_control_status_payload_includes_subconscious_summary` (L1131), `test_subconscious_live_summary_surfaces_replan_reasons_and_thresholds` (L1198), `test_control_action_test_session_run_executes_runner` (L1221), `test_control_action_real_world_task_create_writes_generated_definition` (L1240), `test_control_action_operator_prompt_routes_through_process_chat` (L1264), `test_control_action_operator_prompt_uses_saved_macro` (L1286), `test_control_action_operator_prompt_renders_macro_placeholders` (L1308), `test_control_action_operator_prompt_requires_required_macro_placeholder` (L1348), `test_control_action_operator_prompt_requires_message` (L1368), `test_control_action_generated_pack_run_executes_generated_definitions` (L1375), `test_control_action_generated_pack_run_priority_prefers_highest_priority` (L1399), `test_generated_work_queue_prefers_open_priority_items` (L1417), `test_control_action_generated_queue_run_next_executes_selected_item` (L1442), `test_control_action_generated_queue_investigate_routes_to_operator_prompt` (L1468), `test_export_capabilities_snapshot` (L1509), `test_control_action_export_ledger_and_bundle` (L1521), `test_control_login_action_wrapper_delegates_to_service` (L1560), `test_control_logout_action_wrapper_delegates_to_service` (L1573), `test_chat_login_action_wrapper_delegates_to_service` (L1587), `test_chat_logout_action_wrapper_delegates_to_service` (L1600), `test_control_action_nova_start` (L1614), `test_control_action_core_stop` (L1630), `test_control_action_guard_restart` (L1641), `test_control_action_webui_restart` (L1652), `test_control_action_autonomy_maintenance_start` (L1662), `test_control_action_autonomy_maintenance_stop` (L1672), `test_webui_restart_allows_fresh_control_status_hydration` (L1682), `test_start_guard_clears_stale_stop_flag` (L1750), `test_control_action_chat_user_management_uses_managed_file` (L1770), `test_control_action_memory_scope_set_updates_policy` (L1791), `test_control_action_search_endpoint_set_updates_policy` (L1812), `test_control_action_search_endpoint_probe_returns_probe_details` (L1833), `test_control_action_search_provider_priority_set_updates_policy` (L1842), `test_api_chat_success_invalidates_control_status_cache` (L1867)

### `tests/test_http_session_store.py`

Tests: 6 | Declared lanes: `unit`

`test_trim_turns_caps_history` (L39), `test_append_and_get_turns` (L45), `test_session_summaries` (L61), `test_delete_session` (L75), `test_assert_session_owner` (L98), `test_persist_and_load_sessions` (L124)

### `tests/test_http_test_session_helpers.py`

Tests: 3 | Declared lanes: `unit`

`test_generated_queue_operator_note_includes_core_fields` (L7), `test_investigate_generated_work_queue_item_success` (L24), `test_investigate_generated_work_queue_item_no_open_item` (L48)

### `tests/test_identity_memory_service.py`

Tests: 5 | Declared lanes: `unit`

`test_is_identity_memory_text_allowed_non_identity` (L19), `test_is_identity_memory_text_allowed_identity_assistant_name` (L24), `test_is_identity_memory_text_allowed_identity_developer` (L33), `test_is_identity_memory_text_allowed_identity_origin` (L42), `test_is_identity_memory_text_allowed_identity_rejected` (L51)

### `tests/test_installer_validation_service.py`

Tests: 2 | Declared lanes: `source_release`, `unit`

`test_installer_validation_builds_verifies_and_promotes_installer_kind` (L18), `test_installer_validation_failure_renders_failed_evidence` (L120)

### `tests/test_intent_understanding.py`

Tests: 45 | Declared lanes: `source_reply_quality_contracts`

`test_requesting_weather_fulfills` (L48), `test_commanding_weather_fulfills` (L53), `test_responding_fulfills` (L58), `test_sharing_weather_no_data_accepts` (L63), `test_sharing_weather_data_confirms` (L71), `test_sharing_weather_data_contradicts` (L80), `test_sharing_weather_data_available_but_vague_claim` (L89), `test_casual_weather_remark_accepts` (L98), `test_casual_general_accepts` (L103), `test_low_confidence_triggers_clarify` (L108), `test_confidence_just_above_threshold_does_not_clarify` (L115), `test_sharing_location_no_data_accepts` (L121), `test_sharing_location_data_confirms` (L128), `test_strategy_has_required_keys` (L136), `test_well_formed_sharing_weather` (L148), `test_well_formed_requesting` (L163), `test_unknown_level_falls_back_to_casual` (L175), `test_unknown_domain_falls_back_to_general` (L186), `test_partial_json_extracted` (L197), `test_empty_string_returns_none` (L204), `test_malformed_returns_none` (L207), `test_confidence_clamped_to_range` (L210), `test_null_user_claim_becomes_none` (L221), `test_records_when_mem_fn_provided` (L247), `test_no_crash_without_mem_fn` (L263), `test_does_not_record_empty_text` (L271), `test_does_not_record_missing_level` (L281), `test_outcome_included_in_record` (L291), `test_clarify_strategy_routes_to_work_tree` (L302), `test_clarify_signal_is_governance_pressure` (L315), `test_clarify_signal_fingerprint_encodes_domain_and_level` (L328), `test_successful_outcome_does_not_ingest_signal` (L340), `test_no_crash_if_ingest_fn_raises` (L353), `test_gap_outcome_keyword_routes_to_work_tree` (L363), `test_clarify_strategy_is_gap` (L380), `test_successful_strategies_are_not_gaps` (L383), `test_gap_outcome_keyword_is_gap` (L387), `test_build_signal_has_required_fields` (L392), `test_build_signal_sample_text_truncated` (L401), `test_ollama_down_returns_default` (L417), `test_live_not_allowed_returns_default` (L429), `test_empty_text_returns_default` (L437), `test_well_formed_ollama_response_parsed` (L445), `test_malformed_ollama_response_returns_default` (L468), `test_timeout_returns_default` (L480)

### `tests/test_kidney.py`

Tests: 14 | Declared lanes: `source_test_ecosystem`

`test_add_protect_pattern_persists` (L105), `test_scan_candidates_flags_old_low_novelty_definition` (L112), `test_scan_candidates_flags_nested_generated_definition` (L128), `test_run_kidney_enforce_archives_and_deletes` (L145), `test_dry_run_does_not_overwrite_live_status` (L180), `test_dry_run_can_explicitly_write_status_to_isolated_path` (L200), `test_protected_pattern_skips_candidate` (L210), `test_pending_review_high_fallback_is_retained_until_age_limit` (L221), `test_pending_review_marked_quarantined_is_deleted` (L242), `test_scan_candidates_flags_excess_snapshot_count_and_size` (L266), `test_run_kidney_delete_snapshot_removes_sidecar_meta` (L293), `test_run_kidney_skips_cleanup_snapshot_for_stale_snapshot_batch` (L320), `test_run_kidney_prunes_cleanup_snapshots_even_without_candidates` (L343), `test_run_kidney_prunes_cleanup_snapshots_after_new_snapshot` (L368)

### `tests/test_layer_maturity_policy_service.py`

Tests: 8 | Declared lanes: `source_generated_code`, `unit`

`test_normalize_layer_policy_defaults_to_observe` (L19), `test_observe_mode_suppresses_capability_gap_signals` (L26), `test_active_mode_requires_explicit_promotion` (L44), `test_leah_sequence_requires_ordered_promotion` (L79), `test_core_gate_passes_when_required_roots_close_and_drift_clear` (L93), `test_leah_capability_blocked_until_core_gate_passes` (L116), `test_orchestrator_blocks_codegen_actions_in_observe_mode` (L146), `test_build_layer_maturity_summary_exposes_next_leah_capability` (L164)

### `tests/test_leah_conversation_continuity.py`

Tests: 3 | Declared lanes: `source_memory_identity`

`test_store_persists_and_reloads_session_context` (L21), `test_frontdoor_recovers_context_from_continuity_store` (L34), `test_remember_writes_through_to_store` (L54)

### `tests/test_leah_fast_chat.py`

Tests: 3 | Declared lanes: `source_http_api_control`

`test_enabled_for_http_when_policy_flag_set` (L9), `test_disabled_for_cli_even_when_flag_set` (L13), `test_disabled_when_flag_missing` (L17)

### `tests/test_memory_adapter_service.py`

Tests: 7 | Declared lanes: `unit`

`test_scope_validation` (L13), `test_context_top_k_clamped` (L19), `test_memory_should_keep_text_question_rejected` (L23), `test_memory_should_keep_text_policy_include` (L29), `test_memory_should_keep_text_declarative_statement` (L35), `test_format_memory_recall_hits_dedup` (L41), `test_format_memory_recall_hits_renders_corrections_without_json` (L52)

### `tests/test_memory_capture.py`

Tests: 1 | Declared lanes: `integration`

`test_mem_add_and_recall` (L9)

### `tests/test_memory_cli.py`

Tests: 1 | Declared lanes: `integration`

`test_add_and_recall` (L10)

### `tests/test_memory_health_service.py`

Tests: 6 | Declared lanes: `unit`

`test_memory_health_flags_orphan_learned_facts_tmp` (L42), `test_memory_health_preserves_last_good_count_on_drop` (L65), `test_learned_facts_loader_recovers_from_valid_tmp` (L87), `test_memory_health_flags_invalid_recent_memory_event_log` (L106), `test_memory_health_names_missing_bootstrap_when_memory_enabled` (L133), `test_memory_health_distinguishes_pending_bootstrap_origin` (L154)

### `tests/test_memory_identity_bootstrap_service.py`

Tests: 3 | Declared lanes: `source_memory_identity`

`test_confirmed_origin_contract_allows_identity_bootstrap` (L16), `test_apply_identity_bootstrap_writes_identity_and_learned_facts` (L44), `test_ready_memory_bootstrap_judgment_does_not_repeat_blocked_work` (L96)

### `tests/test_memory_retention_service.py`

Tests: 5 | Declared lanes: `source_memory_identity`

`test_parse_retention_policy_defaults` (L43), `test_evaluate_contamination_flags_chat_user_rows` (L48), `test_apply_memory_hygiene_dry_run_then_apply` (L64), `test_memory_health_reports_contamination_issue` (L93), `test_mem_add_blocks_chat_user_kind` (L110)

### `tests/test_memory_routing_service.py`

Tests: 5 | Declared lanes: `source_memory_identity`

`test_preference_query_is_allowed` (L10), `test_generic_query_is_blocked` (L20), `test_session_priority_blocks_general_context` (L26), `test_identity_fallback_overrides_session_priority` (L35), `test_recent_learning_summary_overrides_session_priority` (L46)

### `tests/test_memory_scope.py`

Tests: 5 | Declared lanes: `unit`

`test_connections_close_when_embed_raises` (L34), `test_private_scope_requires_user` (L65), `test_private_scope_isolated_per_user` (L69), `test_hybrid_scope_includes_private_and_shared` (L81), `test_shared_scope_reads_shared_and_hybrid_but_not_private_records` (L91)

### `tests/test_nova_action_ledger_helpers.py`

Tests: 7 | Declared lanes: `source_test_ecosystem`

`test_recent_action_ledger_records_reads_latest_dict_files` (L21), `test_latest_action_ledger_record_returns_last_payload` (L33), `test_action_history_reply_formats_last_record` (L45), `test_record_completed_tool_execution_detects_tool_execution_step` (L64), `test_record_requested_tool_clarification_detects_pending_location` (L69), `test_detect_repeated_tool_intent_without_execution_uses_labels` (L74), `test_sample_intents_last_returns_unknown_for_blank_intent` (L93)

### `tests/test_nova_action_ledger_service.py`

Tests: 3 | Declared lanes: `unit`

`test_finalize_action_ledger_record_from_runtime_uses_scope_hooks` (L25), `test_write_action_ledger_record_appends_ops_journal_event` (L60), `test_write_record_filename_uses_single_clock_sample_for_sorting` (L89)

### `tests/test_nova_cli_delivery.py`

Tests: 5 | Declared lanes: `source_test_ecosystem`

`test_apply_cli_handled_outcome_clears_pending_and_delivers_reply` (L10), `test_apply_cli_outcome_to_ledger_updates_basic_block_fields` (L46), `test_apply_cli_outcome_to_ledger_updates_reply_fields_without_forcing_none_grounded` (L58), `test_emit_cli_reply_outcome_speaks_standard_reply` (L78), `test_emit_cli_reply_outcome_announces_tool_output` (L99)

### `tests/test_nova_cli_sequence.py`

Tests: 3 | Declared lanes: `source_test_ecosystem`

`test_normalize_sequence_reply_falls_back_when_override_raises` (L12), `test_apply_sequence_result_updates_ledger_and_context` (L19), `test_execute_cli_sequence_enables_early_planner_and_stops_before_llm` (L78)

### `tests/test_nova_control_action_dispatcher.py`

Tests: 3 | Declared lanes: `unit`

`test_dispatch_control_action_from_runtime_resolves_runtime_hooks` (L125), `test_autonomy_advisory_catalog_is_dispatcher_owned_and_routable` (L140), `test_dispatches_operator_outbox_response_and_seen_actions` (L163)

### `tests/test_nova_core_fulfillment_bridge.py`

Tests: 5 | Declared lanes: `behavior`

`test_probe_turn_routes_reports_weak_route_without_existing_fulfillment_state` (L11), `test_probe_turn_routes_reports_fulfillment_viable_from_existing_state` (L25), `test_snapshot_records_weak_route_pressure_without_immediate_replan` (L39), `test_snapshot_records_supervisor_owned_pressure_without_route_cracks` (L53), `test_repeated_weak_route_pressure_requests_replan` (L72)

### `tests/test_nova_core_guardrails.py`

Tests: 2 | Declared lanes: `source_runtime_core`

`test_nova_core_line_count_stays_below_guardrail` (L32), `test_service_owned_wrappers_remain_single_return_delegates` (L40)

### `tests/test_nova_core_identity_context.py`

Tests: 4 | Declared lanes: `unit`

`test_learning_context_includes_confirmed_identity_when_memory_and_kb_are_empty` (L10), `test_learning_context_includes_operational_self_evidence_from_capability_registry` (L35), `test_fallback_context_orders_conversation_before_answer_evidence` (L60), `test_fallback_context_keeps_current_turn_out_of_prior_transcript` (L85)

### `tests/test_nova_fallback_flow.py`

Tests: 21 | Declared lanes: `source_reply_quality_contracts`

`test_build_fallback_context_uses_context_builder_only` (L11), `test_prepare_fallback_flow_builds_retrieved_context_without_policy_gate` (L39), `test_fallback_context_summary_does_not_expose_internal_packet_labels` (L65), `test_finalize_llm_fallback_reply_returns_model_reply_without_content_hooks` (L91), `test_finalize_llm_fallback_reply_supports_preprocess_only` (L123), `test_finalize_conversation_scoped_fallback_drops_trailing_question_shape` (L143), `test_finalize_conversation_scoped_fallback_keeps_direct_paragraph_only` (L180), `test_finalize_conversation_scoped_fallback_uses_conversation_reply_form_before_generation` (L216), `test_finalize_conversation_scoped_fallback_keeps_stale_session_evidence_out` (L275), `test_finalize_fallback_uses_existing_tool_evidence_as_context_not_answer` (L326), `test_finalize_conversation_scoped_fallback_keeps_first_complete_thought` (L383), `test_finalize_conversation_scoped_fallback_prefers_statement_over_question_opener` (L419), `test_finalize_fallback_binds_operational_self_answer_to_evidence_without_llm` (L455), `test_finalize_fallback_binds_confirmed_identity_answer_to_evidence_without_llm` (L505), `test_finalize_fallback_does_not_upgrade_unclear_self_evidence_need` (L545), `test_finalize_fallback_does_not_bind_low_confidence_self_evidence` (L583), `test_intent_evidence_packet_keeps_trace_below_authority` (L621), `test_conversation_scoped_intent_marks_conversation_as_complete_without_task` (L640), `test_conversation_scoped_intent_uses_structured_pair_not_numeric_confidence` (L670), `test_intent_evidence_render_does_not_replay_prior_assistant_text` (L696), `test_finalize_fallback_does_not_answer_repeat_observation_without_model` (L716)

### `tests/test_nova_frontdoor_script.py`

Tests: 1 | Declared lanes: `source_test_ecosystem`

`test_smoke_base_frontdoor_does_not_start_guard` (L8)

### `tests/test_nova_fulfillment_routing.py`

Tests: 4 | Declared lanes: `unit`

`test_not_viable_without_existing_fulfillment_state` (L12), `test_viable_when_existing_fulfillment_state_exists` (L24), `test_not_viable_when_pending_action_exists` (L35), `test_not_viable_when_another_conversation_state_is_active` (L47)

### `tests/test_nova_grounded_self_report_service.py`

Tests: 10 | Declared lanes: `source_test_ecosystem`

`test_service_no_longer_classifies_user_phrases` (L42), `test_health_reply_uses_live_score_alerts_and_work_tree_truth` (L46), `test_trouble_reply_names_current_open_branch_and_task` (L57), `test_release_status_normalizes_latest_readiness_shape` (L67), `test_operator_attention_payload_names_live_help_request` (L89), `test_operator_attention_does_not_label_open_work_as_operator_hold` (L100), `test_ready_with_notes_release_is_status_not_stuck_point` (L110), `test_completed_branch_with_stale_current_task_is_not_current_work` (L133), `test_live_cleared_runtime_branch_does_not_drive_attention` (L168), `test_only_live_cleared_runtime_branch_leaves_attention_clear` (L215)

### `tests/test_nova_guard_boot.py`

Tests: 4 | Declared lanes: `source_runtime_core`

`test_observe_boot_progress_attempts_adoption_before_alive_check` (L17), `test_boot_failed_does_not_fail_early_within_boot_window_when_launcher_is_missing` (L48), `test_boot_failed_returns_boot_pid_missing_after_timeout_when_no_runtime_signals` (L62), `test_boot_failed_stays_healthy_when_child_is_adopted_and_signals_are_good` (L76)

### `tests/test_nova_http.py`

Tests: 9 | Declared lanes: `behavior`

`test_generate_chat_reply_routes_semantic_web_fetch` (L12), `test_generate_chat_reply_semantic_none_uses_model_fallback` (L39), `test_process_chat_appends_user_and_assistant_turns` (L55), `test_cached_control_status_payload_reuses_recent_value` (L70), `test_status_and_surfaces_caches_use_separate_locks` (L86), `test_cached_control_status_surfaces_payload_reuses_recent_value` (L89), `test_probe_searxng_status_path_is_bounded_and_non_mutating` (L105), `test_status_runtime_processes_cache_reuses_recent_scan` (L123), `test_storage_watch_summary_reuses_recent_snapshot_with_age` (L139)

### `tests/test_nova_http_autonomy_summary.py`

Tests: 1 | Declared lanes: `source_http_api_control`

`test_autonomy_maintenance_summary_preserves_patch_queue_fields` (L18)

### `tests/test_nova_http_chat_runtime.py`

Tests: 4 | Declared lanes: `source_runtime_core`

`test_process_chat_from_runtime_resolves_http_runtime_bundle` (L55), `test_process_chat_returns_ok_for_empty_text_and_restores_active_user` (L84), `test_process_chat_url_fetch_reaches_runtime_web_fetch_tool` (L108), `test_process_chat_web_fetch_failure_question_stays_llm_owned` (L156)

### `tests/test_nova_http_frontdoor.py`

Tests: 3 | Declared lanes: `source_http_api_control`

`test_route_contract_contains_frontdoor_and_control_surfaces` (L8), `test_startup_banner_lines_reflect_auth_and_lan_state` (L30), `test_serve_from_runtime_sets_and_clears_server_state` (L45)

### `tests/test_nova_http_generated_work.py`

Tests: 3 | Declared lanes: `source_http_api_control`

`test_generated_pack_action_hook_binds_runtime_functions` (L8), `test_generated_queue_run_next_hook_uses_runtime_queue_and_runner` (L33), `test_generated_queue_investigate_hook_binds_operator_dependencies` (L52)

### `tests/test_nova_http_get_routes.py`

Tests: 13 | Declared lanes: `source_http_api_control`

`test_handle_basic_route_request_returns_health_payload` (L8), `test_handle_basic_route_request_returns_file_route` (L30), `test_handle_basic_route_request_enforces_control_login_gate` (L49), `test_handle_chat_history_request_shapes_turns` (L68), `test_handle_chat_history_request_ignores_other_paths` (L86), `test_handle_control_api_request_requires_auth` (L101), `test_handle_basic_route_request_from_runtime_resolves_scope` (L117), `test_handle_control_status_surfaces_request_returns_slim_payload` (L140), `test_handle_control_status_request_preserves_richer_maintenance_truth` (L164), `test_handle_control_work_trees_request_shapes_payload` (L204), `test_handle_control_work_trees_request_preserves_failure_payload` (L276), `test_handle_control_pipelines_from_runtime_uses_pipeline_control_service` (L298), `test_handle_control_test_sessions_request_shapes_payload` (L338)

### `tests/test_nova_http_grounded_self_report.py`

Tests: 2 | Declared lanes: `source_http_api_control`

`test_http_no_longer_exposes_grounded_self_report_phrase_helper` (L4), `test_core_no_longer_exposes_grounded_self_report_phrase_helper` (L8)

### `tests/test_nova_http_pipeline_control.py`

Tests: 3 | Declared lanes: `source_data_pipelines`

`test_payload_from_runtime_binds_data_lane_dependencies` (L62), `test_action_hooks_from_runtime_bind_pipeline_actions` (L77), `test_action_hooks_bind_pipeline_query_actions` (L92)

### `tests/test_nova_http_policy_search.py`

Tests: 6 | Declared lanes: `source_http_api_control`

`test_policy_hooks_bind_core_policy_actions` (L67), `test_search_provider_hook_returns_policy_snapshot_and_invalidates_cache` (L79), `test_memory_scope_hook_returns_policy_snapshot_and_invalidates_cache` (L93), `test_server_side_hook_returns_policy_snapshot_and_invalidates_cache` (L107), `test_probe_hook_uses_current_endpoint_when_payload_is_empty` (L126), `test_toggle_hook_ignores_payload_and_invalidates_cache` (L138)

### `tests/test_nova_http_post_dispatch.py`

Tests: 5 | Declared lanes: `source_http_api_control`

`test_handle_post_request_returns_not_found_for_unknown_path` (L15), `test_handle_post_request_returns_invalid_json_error` (L29), `test_handle_post_request_dispatches_resume` (L43), `test_handle_post_request_returns_basic_route_result_when_present` (L57), `test_handle_post_request_from_runtime_routes_to_peer_services` (L71)

### `tests/test_nova_http_post_routes.py`

Tests: 4 | Declared lanes: `source_http_api_control`

`test_handle_basic_post_route_returns_header_response_for_chat_login` (L7), `test_handle_basic_post_route_enforces_control_auth_for_actions` (L26), `test_handle_basic_post_route_shapes_control_action_payload` (L42), `test_handle_basic_post_route_from_runtime_resolves_scope` (L58)

### `tests/test_nova_http_request_binding.py`

Tests: 6 | Declared lanes: `source_http_api_control`

`test_handle_chat_request_generates_session_and_invalidates_cache` (L41), `test_handle_resume_request_invalidates_only_when_resumed` (L62), `test_handle_upload_request_stages_items` (L83), `test_handle_upload_request_from_runtime_resolves_scope` (L103), `test_handle_chat_request_direct_attachment_reply_uses_attachment_context` (L124), `test_handle_chat_request_from_runtime_resolves_scope` (L161)

### `tests/test_nova_http_responses.py`

Tests: 4 | Declared lanes: `source_http_api_control`

`test_json_response_with_headers_writes_payload_and_records_status` (L27), `test_file_response_returns_asset_not_found_json_when_missing` (L44), `test_emit_post_result_uses_headers_branch` (L62), `test_emit_basic_route_result_handles_text` (L77)

### `tests/test_nova_http_transport.py`

Tests: 4 | Declared lanes: `source_http_api_control`

`test_handle_get_request_emits_basic_route_result` (L24), `test_handle_get_request_routes_chat_history_through_json_response` (L44), `test_handle_get_request_routes_control_api_through_json_response` (L61), `test_handle_post_request_dispatches_and_emits_result` (L78)

### `tests/test_nova_http_turn_finalization.py`

Tests: 3 | Declared lanes: `source_http_api_control`

`test_finalize_http_reply_builds_reflection_and_finalizes_ledger` (L33), `test_apply_reply_outcome_updates_pending_and_retrieval_state` (L74), `test_finalize_reply_sequence_result_handles_writeback_and_finalization` (L105)

### `tests/test_nova_knowledge_packs.py`

Tests: 2 | Declared lanes: `source_test_ecosystem`

`test_kb_search_returns_reference_block_for_active_pack` (L21), `test_build_local_topic_digest_answer_cites_matching_source` (L47)

### `tests/test_nova_location_weather_service.py`

Tests: 10 | Declared lanes: `source_test_ecosystem`

`test_saved_location_text_reads_core_state_only` (L9), `test_saved_location_text_does_not_read_memory_audit_rows` (L17), `test_coords_from_saved_location_reads_structured_core_state` (L25), `test_parse_lat_lon_accepts_bare_coordinates_with_accuracy_suffix` (L33), `test_live_device_location_summary_prefers_fresh_payload` (L38), `test_live_device_location_summary_refreshes_stale_payload_before_use` (L55), `test_device_location_status_payload_marks_stale_by_age` (L81), `test_format_weather_output_uses_structured_label_and_summary` (L98), `test_tool_weather_uses_api_weather_coords_and_formatter` (L107), `test_runtime_device_location_payload_reports_error_for_bad_json` (L125)

### `tests/test_nova_memory_learning_service.py`

Tests: 9 | Declared lanes: `source_memory_identity`

`test_get_learned_fact_returns_default_when_missing` (L7), `test_learn_self_identity_binding_binds_known_developer` (L16), `test_learn_contextual_self_facts_stores_developer_colors` (L32), `test_remember_and_recall_name_origin_story` (L47), `test_identity_context_for_prompt_carries_confirmed_bootstrap_evidence` (L66), `test_mem_recall_skips_when_router_blocks` (L88), `test_mem_recall_uses_memory_when_router_allows` (L116), `test_mem_get_recent_learned_skips_when_router_blocks` (L143), `test_mem_get_recent_learned_records_allowed_read` (L167)

### `tests/test_nova_mission_service.py`

Tests: 24 | Declared lanes: `source_test_ecosystem`, `unit`

`test_green_cycle_requires_fresh_truth_evidence` (L107), `test_steady_state_hold_without_green_when_truth_is_missing` (L131), `test_high_generated_queue_blocks_green_but_can_still_hold` (L146), `test_generated_queue_validation_can_run_to_clear_own_truth_blocker` (L169), `test_generated_queue_validation_stays_held_when_base_truth_is_missing` (L201), `test_stale_regression_never_returns_green_cycle` (L228), `test_hidden_validation_failures_block_green_cycle` (L250), `test_actionable_pressure_still_blocks_green_cycle_when_policy_flags_enabled` (L264), `test_operator_holds_do_not_block_green_cycle` (L292), `test_runtime_not_ready_blocks_green_cycle_even_when_truth_is_fresh` (L315), `test_release_drift_without_tolerance_blocks_green_cycle` (L330), `test_core_gate_missing_roots_block_green_cycle` (L344), `test_layer_maturity_core_gate_is_authoritative_owner_signal` (L355), `test_explicit_owner_verdict_overrides_compatibility_mapping` (L373), `test_non_green_blocking_owner_pressure_stays_visible_without_false_truth_blocker` (L402), `test_core_thinning_can_run_when_only_release_drift_blocks_green` (L434), `test_core_thinning_stays_held_when_core_gate_roots_are_blocked` (L464), `test_core_thinning_release_drift_allowance_requires_core_gate_evidence` (L481), `test_core_thinning_stays_held_when_release_drift_hides_missing_roots` (L506), `test_execution_contract_blocks_legacy_actions_but_allows_patch_queue` (L531), `test_ingestion_suppresses_ambient_governance_on_quiet_hold` (L557), `test_ingestion_does_not_suppress_when_actionable_gaps_present` (L565), `test_append_history_tracks_sustained_watch` (L573), `test_anti_drift_matrix_never_green_under_stale_testing_pressure` (L594)

### `tests/test_nova_ollama_chat.py`

Tests: 7 | Declared lanes: `source_model_runtime`

`test_returns_error_when_live_calls_disallowed` (L31), `test_builds_prompt_and_returns_response_content` (L50), `test_assist_prompt_omits_tool_citation_examples` (L112), `test_conversation_reply_form_uses_compact_generation_surface` (L151), `test_chat_failure_does_not_restart_or_retry` (L184), `test_chat_route_404_reports_api_contract_without_restart` (L215), `test_missing_model_does_not_restart_ollama` (L247)

### `tests/test_nova_patching_service.py`

Tests: 18 | Declared lanes: `source_patch_pipeline`

`test_parse_scoped_patch_payload_accepts_single_block_payload` (L25), `test_execute_scoped_patch_payload_verifies_required_fragments` (L46), `test_read_patch_manifest_reads_valid_manifest` (L81), `test_snapshot_current_skips_git_and_local_baggage` (L95), `test_patch_preview_summaries_merges_decision_by_name` (L128), `test_compact_preview_review_queue_collapses_duplicate_pending_and_approved_families` (L153), `test_patch_status_payload_exposes_compacted_review_queue` (L197), `test_patch_preview_summaries_marks_orphaned_preview_artifacts` (L244), `test_control_status_patch_fields_expose_review_queue_counts` (L268), `test_nova_core_execute_planned_action_supports_patch_preview_apply` (L301), `test_nova_core_execute_planned_action_supports_patch_preview_approve` (L313), `test_nova_core_execute_planned_action_supports_system_check` (L325), `test_nova_core_execute_planned_action_supports_read` (L332), `test_nova_core_execute_planned_action_supports_ls` (L339), `test_nova_core_execute_planned_action_supports_find` (L346), `test_patch_apply_skips_snapshot_when_zip_has_no_real_changes` (L353), `test_bulk_reject_orphaned_previews_records_rejections` (L390), `test_bulk_archive_superseded_previews_moves_hidden_duplicates` (L416)

### `tests/test_nova_pipeline_tools.py`

Tests: 9 | Declared lanes: `source_data_pipelines`

`test_parse_pipeline_preview_command_extracts_params` (L8), `test_parse_pipeline_search_command_extracts_query` (L20), `test_parse_pipeline_plan_command_extracts_request` (L29), `test_schema_renderer_shows_population_definitions` (L38), `test_status_renderer_shows_readiness_and_trusted_identity` (L62), `test_preview_uses_dry_run_registry_path` (L90), `test_search_uses_vendor_dictionary_registry_path` (L117), `test_plan_uses_report_planning_registry_path` (L151), `test_run_uses_privileged_bridge` (L214)

### `tests/test_nova_pulse_service.py`

Tests: 5 | Declared lanes: `unit`

`test_build_pulse_payload_and_render_roundtrip` (L18), `test_write_pulse_snapshot_writes_expected_fields` (L116), `test_pulse_counts_nested_generated_definition_files` (L139), `test_live_generated_queue_drift_overrides_stale_maintenance_clear` (L152), `test_memory_health_watch_marks_pulse_memory_not_ok` (L204)

### `tests/test_nova_reflection_health_service.py`

Tests: 2 | Declared lanes: `source_test_ecosystem`

`test_maybe_log_self_reflection_accepts_runtime_scope` (L45), `test_build_turn_reflection_accepts_runtime_scope` (L74)

### `tests/test_nova_reply_runtime.py`

Tests: 4 | Declared lanes: `source_runtime_core`

`test_run_tool_records_tool_route_and_updates_recent_context` (L7), `test_conversation_followup_does_not_infer_context_from_reply_text` (L23), `test_deterministic_reply_records_hit_without_identity_conflict_hook` (L40), `test_llm_fallback_records_fallback_without_context_update` (L55)

### `tests/test_nova_reply_sequence.py`

Tests: 17 | Declared lanes: `unit`

`test_execute_reply_sequence_from_runtime_delegates_to_current_sequence_shape` (L47), `test_execute_http_reply_sequence_from_runtime_builds_http_normalizer` (L78), `test_fallback_uses_safe_memory_defaults_when_core_stub_is_minimal` (L106), `test_fulfillment_handles_turn_before_llm_fallback` (L134), `test_fulfillment_typeerror_falls_back_without_crashing` (L165), `test_semantic_tool_result_returns_route_evidence_and_execution_profile` (L176), `test_structured_tool_selection_executes_even_when_confidence_metadata_is_empty` (L195), `test_no_confidence_status_route_falls_back_to_conversation` (L214), `test_weak_status_route_does_not_feed_stale_tool_evidence_to_conversation` (L233), `test_status_followup_does_not_reuse_prior_self_status_without_current_live_intent` (L266), `test_live_status_tool_evidence_is_synthesized_by_fallback` (L338), `test_stop_before_fallback_carries_deferred_status_evidence` (L368), `test_semantic_none_flows_to_model_fallback_without_content_hooks` (L390), `test_semantic_self_evidence_need_returns_evidence_bound_reply_before_model` (L415), `test_stop_before_llm_fallback_returns_unhandled_after_semantic_none` (L452), `test_planner_timing_is_included_in_execution_profile` (L463), `test_llm_fallback_records_execution_profile_and_slow_llm_trace` (L487)

### `tests/test_nova_route_probing.py`

Tests: 2 | Declared lanes: `unit`

`test_deterministic_route_viability_prefers_supervisor_owned_result` (L8), `test_build_probe_turn_routes_marks_weak_when_multiple_routes_viable` (L28)

### `tests/test_nova_routing_helpers.py`

Tests: 5 | Declared lanes: `source_test_ecosystem`

`test_strip_invocation_prefix_removes_direct_address` (L7), `test_strip_invocation_prefix_keeps_non_invocation_phrase` (L13), `test_strip_invocation_prefix_removes_space_separated_direct_address` (L19), `test_resolve_research_provider_prefers_priority_match` (L25), `test_resolve_research_provider_falls_back_to_default_tool` (L34)

### `tests/test_nova_routing_support.py`

Tests: 18 | Declared lanes: `source_test_ecosystem`

`test_supervisor_candidate_trace_trims_fields` (L8), `test_build_routing_decision_records_phases_without_bypass_contract` (L31), `test_llm_classify_routing_intent_returns_none_for_model_none` (L53), `test_routing_prompt_keeps_tools_bound_to_evidence_gap` (L79), `test_llm_classify_routing_intent_can_return_explicit_none_payload` (L88), `test_none_payload_with_conversation_evidence_normalizes_to_current_conversation` (L110), `test_structured_url_routes_to_fetch_when_classifier_omits_tool` (L121), `test_llm_classify_routing_intent_reads_json_from_prose_envelope` (L133), `test_coerce_tool_intent_does_not_turn_prose_into_tool_name` (L165), `test_llm_classify_routing_intent_keeps_current_turn_out_of_recent_turns` (L175), `test_llm_classify_routing_intent_keeps_identity_evidence_need_without_tool` (L210), `test_llm_classify_routing_intent_promotes_live_status_target_to_tool` (L236), `test_coerce_tool_intent_downgrades_identity_target_away_from_live_status_tool` (L262), `test_llm_classify_routing_intent_maps_weather_tool_goal` (L273), `test_llm_classify_routing_intent_maps_live_self_status_goal` (L304), `test_llm_classify_routing_intent_prefers_routing_model_when_provided` (L328), `test_coerce_tool_intent_rejects_removed_content_tools` (L355), `test_coerce_tool_intent_accepts_work_tree_tool` (L366)

### `tests/test_nova_runtime_context.py`

Tests: 4 | Declared lanes: `unit`

`test_active_user_round_trip` (L7), `test_runtime_paths_are_derived_from_base_dir` (L18), `test_runtime_scope_resolves_live_and_validation_roots` (L39), `test_validation_runtime_override_is_honored` (L63)

### `tests/test_nova_search_endpoint.py`

Tests: 3 | Declared lanes: `source_web_search`

`test_search_endpoint_candidates_include_local_fallbacks` (L7), `test_probe_search_endpoint_auto_repairs_local_fallback` (L14), `test_probe_search_endpoint_can_bound_candidate_count` (L48)

### `tests/test_nova_self_status_service.py`

Tests: 8 | Declared lanes: `unit`

`test_self_status_reports_hurt_failure_and_update_signals` (L8), `test_self_status_reads_ops_journal_and_classifies_update_activity` (L36), `test_self_status_is_steady_without_signals` (L63), `test_self_status_ignores_stale_regression_failure` (L81), `test_self_status_keeps_green_fallback_history_out_of_active_status` (L99), `test_self_status_reports_memory_health_watch` (L123), `test_self_status_reports_local_code_change_with_validation` (L151), `test_repo_change_snapshot_parses_git_status_and_numstat` (L178)

### `tests/test_nova_session_state_service.py`

Tests: 2 | Declared lanes: `source_test_ecosystem`

`test_apply_reply_session_updates_sets_pending_action_from_meta` (L8), `test_apply_reply_session_updates_clears_pending_when_meta_has_none` (L29)

### `tests/test_nova_temporal_service.py`

Tests: 9 | Declared lanes: `unit`

`test_scores_proximity_and_routes_to_work_tree_for_immediate_deadline` (L20), `test_background_awareness_stays_silent` (L41), `test_assess_many_groups_results_by_pressure` (L55), `test_route_pressure_returns_structured_payload` (L68), `test_parse_ics_text_extracts_event` (L81), `test_parse_ics_file_reads_event` (L102), `test_normalize_calendar_event_accepts_dict` (L114), `test_falls_back_when_apscheduler_unavailable` (L122), `test_add_job_raises_without_backend` (L131)

### `tests/test_nova_tool_dispatch.py`

Tests: 10 | Declared lanes: `source_patch_pipeline`

`test_execute_planned_action_from_runtime_builds_tool_map_from_scope` (L59), `test_execute_planned_action_from_runtime_rejects_removed_content_tools` (L67), `test_execute_planned_action_from_runtime_wires_web_fetch` (L77), `test_execute_planned_action_from_runtime_wires_os_capability` (L86), `test_execute_planned_action_from_runtime_wires_source_root_judgment` (L95), `test_execute_planned_action_from_runtime_wires_installer_validation` (L104), `test_weather_current_location_prefers_live_coords` (L113), `test_location_coords_routes_to_setter` (L127), `test_location_coords_without_args_returns_current_device_fix` (L142), `test_unknown_tool_returns_error_payload` (L157)

### `tests/test_nova_tool_policy_service.py`

Tests: 2 | Declared lanes: `source_web_search`, `unit`

`test_web_allowlist_message_reports_policy_boundary_not_backend_failure` (L7), `test_web_allowlist_message_reports_empty_allowlist_without_dependency_failure` (L18)

### `tests/test_nova_vision_runtime.py`

Tests: 5 | Declared lanes: `source_runtime_core`

`test_reports_not_requested_when_policy_keeps_vision_disabled` (L11), `test_reports_missing_screen_and_camera_modules_when_enabled` (L21), `test_reports_missing_vision_model_when_ollama_lacks_configured_model` (L35), `test_reads_vision_model_from_policy_file_for_helper_scripts` (L49), `test_policy_file_helper_falls_back_to_default_model_when_policy_is_missing` (L61)

### `tests/test_nova_voice_runtime.py`

Tests: 13 | Declared lanes: `source_runtime_core`

`test_ensure_voice_deps_updates_runtime_scope_from_importer` (L87), `test_voice_status_payload_reports_unrequested_voice_without_failure` (L108), `test_voice_status_payload_reports_requested_dependency_failure` (L128), `test_speak_chunked_groups_sentences_under_max_len` (L146), `test_record_seconds_uses_named_preferred_input_device` (L158), `test_record_seconds_auto_avoids_virtual_default_device` (L187), `test_record_seconds_auto_deprioritizes_mic_array_vs_dedicated_mic` (L213), `test_record_seconds_uses_device_native_capture_channels` (L239), `test_record_seconds_falls_back_when_selected_device_is_invalid` (L264), `test_record_seconds_stops_after_silence_when_speech_detected` (L293), `test_record_seconds_raises_clear_error_when_no_speech_detected` (L337), `test_transcribe_raises_clear_error_for_no_speech_like_phrase` (L364), `test_transcribe_keeps_valid_speech` (L383)

### `tests/test_nova_web_tools_service.py`

Tests: 11 | Declared lanes: `source_web_search`

`test_tool_web_fetch_surfaces_allowlist_message` (L21), `test_tool_web_search_reports_local_backend_unavailable` (L32), `test_tool_web_research_continue_uses_cached_session` (L56), `test_tool_web_research_stops_after_enough_hits` (L83), `test_tool_web_research_uses_query_first_direct_fetch_before_sitemap` (L116), `test_tool_web_research_falls_back_to_crawl_after_query_first_miss` (L145), `test_tool_web_research_skips_seeds_after_domain_timeout` (L180), `test_tool_web_gather_returns_summary_snippet` (L210), `test_build_grounded_answer_formats_strong_sources_and_filters_weak_ones` (L228), `test_scan_candidate_urls_for_query_keeps_html_and_non_html_hits` (L254), `test_fetch_sitemap_urls_follows_nested_sitemaps_and_filters_host` (L284)

### `tests/test_nova_wiring_inventory_service.py`

Tests: 12 | Declared lanes: `source_source_root_inventory`, `source_test_ecosystem`

`test_empty_status_is_not_self_repair_closed` (L29), `test_missing_execution_path_is_reported_as_action_wired_only` (L36), `test_borrowed_global_signal_without_owned_root_route_is_not_wired` (L56), `test_source_contract_reports_all_roots_have_direct_signal_routes` (L75), `test_source_probe_finds_owned_root_signal_route` (L84), `test_source_probe_reports_missing_path_sets` (L92), `test_source_probe_has_direct_signal_for_every_source_root` (L106), `test_identity_profile_answers_is_declared_as_a_root_and_surface` (L112), `test_codegen_pipeline_is_declared_as_a_root` (L116), `test_model_runtime_declares_owned_signal_and_os_capability_route` (L119), `test_edfi_capability_profile_is_declared_as_a_wiring_surface` (L129), `test_runtime_search_and_scheduler_roots_do_not_borrow_control_status_signal_routes` (L142)

### `tests/test_ollama_health_service.py`

Tests: 6 | Declared lanes: `source_model_runtime`

`test_requires_tags_and_chat_route` (L16), `test_configured_chat_model_must_exist_in_tags` (L30), `test_configured_chat_model_available_is_ok` (L51), `test_surfaces_ollama_server_version_and_api_contract` (L69), `test_tags_green_chat_404_is_not_ok` (L89), `test_live_call_guard_blocks_without_network` (L104)

### `tests/test_ollama_test_guard.py`

Tests: 14 | Declared lanes: `unit`

`test_llm_classify_routing_intent_is_blocked_under_unittest_by_default` (L9), `test_llm_classify_routing_intent_can_be_opted_in_under_unittest` (L17), `test_ollama_api_up_is_blocked_under_unittest_by_default` (L41), `test_ollama_chat_is_blocked_under_unittest_by_default` (L48), `test_ollama_chat_is_blocked_under_regression_runner_test_mode` (L56), `test_ollama_api_up_can_be_opted_in_for_unittest` (L64), `test_ensure_ollama_does_not_restart_when_only_model_contract_is_unready` (L91), `test_ensure_ollama_boot_does_not_restart_when_only_model_contract_is_unready` (L101), `test_ensure_ollama_does_not_restart_when_api_contract_is_unready` (L111), `test_ensure_ollama_boot_does_not_restart_when_api_contract_is_unready` (L121), `test_ensure_ollama_boot_does_not_start_process_under_unittest_by_default` (L134), `test_warm_ollama_chat_model_is_blocked_under_unittest_by_default` (L143), `test_warm_ollama_chat_model_posts_bounded_probe_when_allowed` (L150), `test_ensure_ollama_does_not_start_process_under_unittest_by_default` (L176)

### `tests/test_operator_control_service.py`

Tests: 8 | Declared lanes: `source_test_ecosystem`

`test_operator_asset_paths_resolve_from_base_dir` (L11), `test_load_operator_macros_and_resolve` (L23), `test_render_operator_macro_prompt_applies_defaults_and_note` (L49), `test_load_backend_commands_and_parse_dynamic_args` (L67), `test_run_backend_command_executes_python_module` (L95), `test_backend_command_run_action_requires_command` (L129), `test_operator_prompt_action_renders_macro_and_returns_session` (L141), `test_operator_prompt_action_from_runtime_resolves_scope` (L174)

### `tests/test_operator_outbox_service.py`

Tests: 38 | Declared lanes: `source_runtime_core`

`test_append_notice_records_and_dedupes_pressure` (L14), `test_append_notice_updates_existing_open_pressure_instead_of_repeating` (L49), `test_closed_notice_does_not_dedupe_new_pressure` (L86), `test_summary_splits_actionable_open_count_from_autonomy_internal_notices` (L124), `test_summary_counts_autonomy_execution_failures_as_actionable` (L162), `test_notice_from_autonomy_uses_state_not_content_triggers` (L188), `test_notice_from_autonomy_ignores_internal_cooldown_wait` (L210), `test_notice_from_autonomy_ignores_mission_hold_wait` (L227), `test_notice_from_autonomy_ignores_mission_owner_blocker_wait` (L252), `test_notice_from_autonomy_ignores_operator_hold_wait` (L281), `test_work_tree_notice_names_missing_maintenance_tool_dispatch` (L298), `test_work_tree_notice_payload_keeps_target_without_full_tree_snapshot` (L326), `test_work_tree_notice_names_failed_tool_judgment` (L365), `test_work_tree_failed_tool_history_without_current_task_is_not_live_pressure` (L406), `test_reconcile_work_tree_notices_stales_cleared_pressure` (L433), `test_reconcile_work_tree_notices_stales_older_open_duplicates` (L481), `test_reconcile_source_root_judgment_notices_stales_closed_branch_pressure` (L527), `test_reconcile_source_root_judgment_notices_stales_missing_branch_pressure` (L609), `test_reconcile_stale_open_notices_stales_aged_new_and_seen_notices` (L692), `test_reconcile_duplicate_source_notices_keeps_latest_open_notice` (L744), `test_reconcile_autonomy_notices_stales_cleared_pressure` (L792), `test_reconcile_os_capability_notices_stales_restored_contract_pressure` (L840), `test_work_tree_notice_asks_for_operator_information_from_blocked_task` (L893), `test_blocked_work_notice_dedupes_on_branch_reason_not_task_id` (L931), `test_work_tree_notice_does_not_mirror_operator_control_branch_back_to_outbox` (L983), `test_work_tree_notice_names_internal_repair_hold` (L1017), `test_operator_response_records_work_tree_evidence_and_resolves_task` (L1053), `test_continue_work_response_satisfies_blocked_operator_wait` (L1110), `test_task_resolved_response_requires_work_tree_target` (L1179), `test_continue_work_response_requires_work_tree_target` (L1212), `test_autonomy_publish_writes_operator_notice` (L1242), `test_autonomy_publish_writes_work_tree_operator_requests` (L1266), `test_autonomy_publish_stales_old_work_tree_requests_when_pressure_clears` (L1297), `test_autonomy_publish_stales_old_autonomy_request_when_pressure_clears` (L1332), `test_autonomy_publish_stales_operator_hold_wait_notice` (L1370), `test_summary_keeps_open_notices_visible_when_latest_event_is_closed` (L1406), `test_summary_projects_legacy_tree_payload_without_carrying_snapshot` (L1444), `test_runtime_console_polls_operator_outbox_from_health` (L1485)

### `tests/test_ops_journal.py`

Tests: 2 | Declared lanes: `source_test_ecosystem`

`test_append_ops_event_writes_jsonl_entry` (L23), `test_append_ops_event_preserves_live_root_this_is_nova_content` (L50)

### `tests/test_orchestrator_codegen.py`

Tests: 14 | Declared lanes: `source_generated_code`

`test_codegen_run_in_catalog` (L17), `test_codegen_run_metadata` (L22), `test_codegen_run_is_advisory_action` (L33), `test_codegen_run_has_impact_and_risk` (L37), `test_leah_build_run_next_in_catalog` (L51), `test_leah_build_run_next_metadata` (L56), `test_orchestrator_detects_capability_gap_branches` (L71), `test_orchestrator_codegen_action_includes_branch_id` (L103), `test_orchestrator_skips_non_ready_capability_gaps` (L136), `test_orchestrator_handles_multiple_capability_gaps` (L165), `test_orchestrator_codegen_excluded_from_general_work_count` (L204), `test_orchestrator_codegen_action_contract` (L232), `test_codegen_prioritizes_capability_gaps` (L255), `test_orchestrator_routes_leah_capabilities_to_leah_build` (L296)

### `tests/test_os_capability_operator_outbox_service.py`

Tests: 4 | Declared lanes: `source_tool_registry_policy`, `unit`

`test_build_notice_from_controller_result_state` (L51), `test_publish_notice_dedupes_repeated_contract_gap` (L65), `test_registered_tool_publishes_operator_notice_when_controller_marks_outbox` (L90), `test_core_tool_publishes_operator_notice_when_controller_marks_outbox` (L132)

### `tests/test_os_capability_registry_service.py`

Tests: 9 | Declared lanes: `unit`

`test_draft_empty_hash_loads_but_cannot_prepare` (L78), `test_active_contract_hash_defaults_and_rejects_unknown_args` (L124), `test_hash_mismatch_loads_as_contract_stale` (L159), `test_execution_time_hash_catches_script_drift_after_load` (L185), `test_allowed_roots_are_contract_bounds_not_script_logic` (L213), `test_network_scope_rejects_non_localhost_base_url` (L264), `test_missing_capability_is_operator_worthy` (L288), `test_draft_does_not_hide_malformed_contract` (L304), `test_default_source_registry_has_active_first_slice_capabilities` (L338)

### `tests/test_os_script_controller_service.py`

Tests: 12 | Declared lanes: `unit`

`test_blocked_prepare_writes_ledger_without_running_script` (L108), `test_successful_script_execution_records_command_and_stdout` (L139), `test_invalid_args_write_operator_worthy_ledger_without_running` (L173), `test_timeout_kills_process_and_records_partial_output` (L198), `test_nonzero_exit_records_failed_evidence` (L227), `test_json_evidence_ok_false_records_failed_evidence` (L253), `test_execution_time_hash_drift_is_ledgered_without_running` (L286), `test_controller_rechecks_hash_after_prepare_before_command_build` (L313), `test_default_source_registry_executes_ollama_verifier_through_controller` (L358), `test_authority_block_records_ledger_without_running` (L380), `test_evidence_write_verifies_reported_output_path` (L409), `test_evidence_write_blocks_reported_path_outside_contract` (L449)

### `tests/test_patch_control_service.py`

Tests: 8 | Declared lanes: `unit`

`test_patch_preview_list_action_uses_preview_fallback_and_readiness` (L9), `test_pulse_status_action_returns_rendered_text_and_pending_state` (L22), `test_patch_action_readiness_payload_explains_preview_controls` (L35), `test_patch_preview_target_prefers_payload_then_first_preview` (L61), `test_patch_preview_apply_blocks_unapproved_preview` (L71), `test_update_now_confirm_requires_patch_applied_prefix` (L87), `test_update_now_confirm_action_uses_payload_token` (L98), `test_update_now_cancel_action_returns_pending_payload` (L114)

### `tests/test_patch_guard.py`

Tests: 7 | Declared lanes: `source_runtime_core`

`test_rejects_missing_manifest_in_strict_mode` (L33), `test_rejects_downgrade_revision` (L49), `test_rejects_incompatible_base` (L73), `test_accepts_forward_revision_and_updates_state` (L97), `test_behavioral_check_failure_rolls_back_patch` (L128), `test_teach_proposal_uses_forward_patch_manifest` (L161), `test_patch_status_payload_requires_approved_eligible_preview_for_validated_apply` (L184)

### `tests/test_patch_promotion_memory.py`

Tests: 15 | Declared lanes: `source_generated_code`

`test_record_promotion_extracts_spec_info` (L28), `test_record_promotion_handles_missing_zip` (L50), `test_record_promotion_extracts_from_zip` (L69), `test_record_promotion_returns_none_on_error` (L101), `test_extract_python_files_from_zip` (L115), `test_extract_handles_missing_zip` (L133), `test_extract_handles_missing_files_in_zip` (L142), `test_extract_filters_non_python_files` (L158), `test_inject_returns_string` (L186), `test_inject_empty_when_no_prior_patterns` (L193), `test_inject_includes_context_when_patterns_exist` (L200), `test_service_exposes_record_promotion` (L224), `test_service_exposes_get_memory_injection` (L236), `test_service_exposes_extract_codegen_from_zip` (L241), `test_full_promotion_workflow` (L256)

### `tests/test_pipeline_privileged_bridge.py`

Tests: 3 | Declared lanes: `source_data_pipelines`

`test_default_runtime_root_uses_runtime_context` (L24), `test_queue_and_wait_for_privileged_pipeline_query` (L29), `test_run_privileged_pipeline_query_waits_for_worker_response` (L57)

### `tests/test_pipeline_privileged_protocol.py`

Tests: 2 | Declared lanes: `source_data_pipelines`

`test_submit_claim_and_archive_request` (L23), `test_wait_for_response_returns_written_payload` (L39)

### `tests/test_pipeline_privileged_worker.py`

Tests: 1 | Declared lanes: `source_data_pipelines`

`test_process_next_privileged_request_writes_response` (L20)

### `tests/test_pipeline_query_guard.py`

Tests: 6 | Declared lanes: `source_data_pipelines`

`test_rejects_unknown_operation` (L23), `test_requires_one_of_required_any_groups` (L27), `test_rejects_unexpected_parameter` (L31), `test_clamps_row_limit_to_template_cap` (L39), `test_defaults_to_standard_twenty_row_limit` (L51), `test_allows_smaller_explicit_row_limit` (L61)

### `tests/test_pipeline_registry.py`

Tests: 2 | Declared lanes: none

`test_discovers_sis_test_pipeline` (L18), `test_instantiates_sis_test_connector` (L23)

### `tests/test_planner_contract_service.py`

Tests: 24 | Declared lanes: `source_test_ecosystem`

`test_build_planner_config_carries_turns_pending_and_override` (L56), `test_maybe_handle_planner_sequence_returns_route_evidence_for_tool_run` (L67), `test_maybe_handle_planner_sequence_uses_semantic_tool_intent` (L98), `test_maybe_handle_planner_sequence_prefers_semantic_intent_over_static_parser` (L123), `test_maybe_handle_planner_sequence_allows_semantic_non_self_tool_with_empty_turn_acts` (L157), `test_maybe_handle_planner_sequence_contracts_system_check_tool` (L181), `test_maybe_handle_planner_sequence_renders_system_check_json_by_contract` (L202), `test_maybe_handle_planner_sequence_does_not_fallback_to_static_parser_after_semantic_none` (L236), `test_maybe_handle_planner_sequence_blocks_low_confidence_no_arg_tool_payload` (L257), `test_maybe_handle_planner_sequence_does_not_run_no_confidence_status_route` (L282), `test_maybe_handle_planner_sequence_routes_live_status_from_structured_pair_without_numeric_confidence` (L308), `test_maybe_handle_planner_sequence_blocks_status_tool_without_live_status_contract` (L340), `test_maybe_handle_planner_sequence_does_not_rerun_no_arg_tool_when_evidence_is_available` (L370), `test_maybe_handle_planner_sequence_routes_semantic_work_tree_status` (L410), `test_maybe_handle_planner_sequence_sets_pending_weather_when_location_missing` (L432), `test_merge_route_evidence_updates_routing_decision` (L455), `test_maybe_handle_planner_sequence_returns_work_tree_step_for_active_tree` (L465), `test_maybe_handle_planner_sequence_returns_work_tree_wait_reply` (L492), `test_maybe_handle_planner_sequence_executes_work_tree_on_continue` (L514), `test_maybe_handle_planner_sequence_creates_work_tree_when_requested` (L540), `test_maybe_handle_planner_sequence_formats_tree_inspection` (L559), `test_maybe_handle_planner_sequence_does_not_auto_seed_from_message_content` (L576), `test_maybe_handle_planner_sequence_does_not_auto_seed_for_content_prompt` (L596), `test_maybe_handle_planner_sequence_continues_active_identity_without_continue_keyword` (L616)

### `tests/test_planner_decision.py`

Tests: 4 | Declared lanes: `source_test_ecosystem`

`test_city_name_without_context_stays_unowned` (L7), `test_city_name_with_location_context_does_not_route_to_wikipedia` (L12), `test_research_followup_without_online_intent_does_not_force_web` (L24), `test_research_followup_after_web_offer_stays_conversation_owned` (L37)

### `tests/test_policy_commands.py`

Tests: 15 | Declared lanes: `behavior`

`test_list_allowed_domains_reads_current_policy` (L39), `test_policy_allow_adds_domain` (L43), `test_policy_allow_duplicate_domain` (L51), `test_policy_allow_writes_audit_log` (L58), `test_policy_remove_domain` (L68), `test_policy_remove_not_found` (L76), `test_policy_audit_command` (L80), `test_web_mode_max_updates_policy` (L86), `test_web_mode_status` (L95), `test_probe_search_endpoint_auto_detects_local_fallback_port` (L100), `test_probe_search_endpoint_failure_reports_configured_endpoint_and_checked_candidates` (L122), `test_probe_search_endpoint_failure_sanitizes_volatile_object_addresses` (L140), `test_wikipedia_lookup_returns_summary_and_related_pages` (L157), `test_stackexchange_search_returns_ranked_results` (L189), `test_load_policy_sets_safety_envelope_defaults` (L214)

### `tests/test_policy_control_service.py`

Tests: 8 | Declared lanes: `unit`

`test_memory_scope_set_action_returns_policy_snapshot` (L7), `test_search_provider_action_marks_usage_as_failure` (L22), `test_server_side_settings_action_returns_policy_snapshot` (L37), `test_search_endpoint_set_action_returns_policy_snapshot` (L69), `test_search_provider_priority_action_returns_policy_snapshot` (L84), `test_search_provider_toggle_action_invalidates_status_cache` (L99), `test_search_endpoint_probe_action_returns_probe_payload` (L114), `test_policy_allow_action_passes_domain` (L125)

### `tests/test_policy_manager_resolver.py`

Tests: 1 | Declared lanes: `unit`

`test_load_policy_uses_current_policy_path_each_call` (L18)

### `tests/test_policy_manager_service.py`

Tests: 13 | Declared lanes: `unit`

`test_load_policy_applies_expected_defaults` (L17), `test_safety_envelope_defaults_use_runtime_context` (L30), `test_allow_and_remove_domain_mutates_policy` (L47), `test_audit_returns_recent_entries` (L64), `test_set_memory_scope_updates_policy` (L76), `test_set_search_provider_enables_web` (L87), `test_set_search_provider_accepts_brave` (L100), `test_set_search_provider_priority_updates_policy` (L112), `test_auto_repair_search_endpoint_updates_policy` (L123), `test_auto_repair_search_endpoint_ignores_local_alias_only_drift` (L135), `test_set_search_endpoint_normalizes_and_updates_policy` (L147), `test_set_web_mode_max_updates_research_limits` (L159), `test_set_server_side_settings_updates_policy` (L172)

### `tests/test_port_ownership_service.py`

Tests: 2 | Declared lanes: `source_test_ecosystem`

`test_payload_reports_expected_ollama_listener_owner` (L45), `test_payload_marks_unexpected_expected_port_owner` (L64)

### `tests/test_regression_contracts.py`

Tests: 6 | Declared lanes: `unit`

`test_memory_api_supports_scope_contract` (L14), `test_static_planner_does_not_claim_phrase_routes` (L26), `test_pending_correction_target_tracks_conversation_state` (L40), `test_core_thinning_keeps_runtime_public_adapters` (L48), `test_control_template_uses_current_branding` (L72), `test_smoke_workflow_uses_ci_safe_contract` (L77)

### `tests/test_regression_profile_inventory_service.py`

Tests: 4 | Declared lanes: `unit`

`test_inventory_separates_curated_source_observed_and_inactive_install_profile_tests` (L10), `test_source_observed_tests_are_profile_drift_until_classified` (L62), `test_source_profile_lanes_classify_current_source_tests` (L82), `test_edfi_tests_map_to_separate_source_profile_lanes` (L89)

### `tests/test_release_clean_service.py`

Tests: 5 | Declared lanes: `unit`

`test_release_clean_runs_package_lane_and_writes_report` (L27), `test_release_clean_stops_on_hygiene_failure` (L80), `test_release_clean_parses_raw_readiness_when_report_stdout_is_tailed` (L107), `test_hygiene_accepts_smudged_lfs_asset_when_index_blob_is_pointer` (L165), `test_hygiene_rejects_large_non_lfs_blob` (L193)

### `tests/test_release_package_scripts.py`

Tests: 3 | Declared lanes: `integration`

`test_build_release_package_excludes_non_package_content` (L63), `test_verify_release_package_rejects_forbidden_payload_content` (L146), `test_build_release_package_prunes_old_zip_artifacts_by_default` (L214)

### `tests/test_release_promotion_judgment_service.py`

Tests: 4 | Declared lanes: `source_release`

`test_validation_record_payload_treats_template_result_as_missing` (L75), `test_validation_record_payload_reads_seed_continuation_values` (L87), `test_release_promotion_judgment_reports_missing_validation_outcome` (L111), `test_release_promotion_judgment_accepts_complete_matching_record` (L126)

### `tests/test_release_runtime_truth_service.py`

Tests: 4 | Declared lanes: `source_release`, `unit`

`test_enrich_release_status_marks_expected_drift` (L12), `test_release_drift_suppresses_closure_signals` (L27), `test_build_release_runtime_truth_summary_exposes_suppression_flag` (L37), `test_evaluate_http_model_runtime_probe_reports_missing_keys` (L48)

### `tests/test_release_status_service.py`

Tests: 6 | Declared lanes: `unit`

`test_status_payload_summarizes_latest_build_and_promotion` (L12), `test_status_payload_filters_by_artifact_kind` (L68), `test_status_payload_filters_kind_before_recent_display_limit` (L128), `test_status_payload_marks_release_stale_when_source_changed_after_build` (L183), `test_status_payload_ignores_mtime_only_touch_when_artifact_content_matches` (L224), `test_status_payload_ignores_local_handoff_dirs_after_build` (L282)

### `tests/test_release_validation_service.py`

Tests: 14 | Declared lanes: `source_release`

`test_release_validation_run_writes_complete_record_from_observed_steps` (L47), `test_release_validation_blocks_when_regression_status_is_not_green` (L102), `test_release_validation_blocks_when_regression_status_is_stale` (L136), `test_release_validation_removes_fresh_extract_root_for_repeated_artifact` (L168), `test_release_validation_collapses_long_package_root_before_running_commands` (L212), `test_prepare_package_root_extracts_wrapped_zip_directly_into_short_pkg` (L248), `test_nova_run_probe_command_uses_front_door_without_runtime_turn_by_default` (L260), `test_nova_run_probe_command_can_exercise_scripted_runtime_turn` (L269), `test_prepare_package_root_removes_extract_workspace_when_prepare_fails` (L278), `test_release_validation_can_keep_extract_root_when_requested` (L294), `test_release_validation_does_not_complete_record_when_profile_never_runs` (L327), `test_default_command_runner_times_out_process_tree_with_inherited_output` (L359), `test_default_command_runner_can_keep_logs_outside_command_cwd` (L388), `test_record_release_validation_outcome_requires_complete_record` (L408)

### `tests/test_run_regression.py`

Tests: 8 | Declared lanes: `unit`

`test_resolve_requested_lanes_defaults_to_unit` (L24), `test_compact_lane_map_uses_shared_regression_source` (L29), `test_resolve_requested_lanes_expands_all` (L32), `test_main_runs_selected_lane` (L40), `test_main_fails_when_validation_artifacts_disagree_after_green_lanes` (L59), `test_main_lists_available_lanes` (L90), `test_run_unittest_suite_marks_regression_test_mode` (L101), `test_write_regression_status_records_validation_marker` (L154)

### `tests/test_run_test_session.py`

Tests: 13 | Declared lanes: `integration`

`test_isolated_runner_state_resets_and_restores_active_user` (L20), `test_run_http_session_does_not_override_user_identity` (L31), `test_run_run_tools_session_uses_run_tools_session_id` (L45), `test_load_session_reads_compare_modes` (L60), `test_load_session_reads_utf8_sig_json` (L78), `test_generated_canary_has_no_cli_http_drift` (L96), `test_generated_canary_has_no_run_tools_http_drift` (L145), `test_compare_sessions_ignores_route_summary_instrumentation_noise` (L193), `test_compare_sessions_tolerates_llm_fallback_question_wording` (L225), `test_compare_sessions_surfaces_runtime_error_answers_even_without_drift` (L257), `test_compare_sessions_surfaces_specific_ollama_chat_errors` (L295), `test_compare_sessions_tolerates_reported_fact_restatement` (L332), `test_compare_sessions_surfaces_generic_mode_labels` (L366)

### `tests/test_run_tools.py`

Tests: 6 | Declared lanes: `unit`

`test_parse_args_supports_list_tools` (L8), `test_handle_tools_uses_shared_planner_and_executes_direct_tool` (L12), `test_handle_tools_returns_clarify_prompt` (L20), `test_handle_tools_ignores_unknown_planner_steps` (L26), `test_list_tools_text_includes_direct_and_registered_sections` (L32), `test_ask_nova_uses_sessioned_voice_chat` (L41)

### `tests/test_runtime_analytics_service.py`

Tests: 16 | Declared lanes: `source_runtime_core`

`test_missing_file_returns_default_payload` (L43), `test_corrupt_file_returns_danger_payload` (L54), `test_empty_list_returns_default_payload` (L65), `test_all_successes_returns_good_level` (L77), `test_three_consecutive_failures_triggers_danger` (L96), `test_one_failure_triggers_warn` (L113), `test_planned_operator_restarts_do_not_become_pressure` (L127), `test_unattributed_successful_boots_report_provenance_gap_not_pressure` (L155), `test_older_unattributed_boots_become_legacy_gap_after_current_provenance` (L173), `test_supervised_recovery_restarts_are_pressure` (L202), `test_repeated_heartbeat_stale_restarts_warn_even_below_generic_pressure_threshold` (L228), `test_avg_success_boot_sec_computed` (L280), `test_recent_outcomes_capped_at_six` (L293), `test_last_success_age_computed` (L306), `test_nova_http_delegates_to_service` (L321), `test_singleton_exists` (L330)

### `tests/test_runtime_artifacts_service.py`

Tests: 2 | Declared lanes: `unit`

`test_payload_summarizes_runtime_files` (L10), `test_detail_payload_accepts_runtime_truth_aliases` (L64)

### `tests/test_runtime_control_service.py`

Tests: 24 | Declared lanes: `unit`

`test_autonomy_maintenance_summary_flattens_queue_truth` (L41), `test_autonomy_maintenance_summary_prefers_latest_queue_sync_over_stale_run` (L93), `test_autonomy_maintenance_summary_marks_missing_runtime_worker_stale` (L132), `test_autonomy_maintenance_summary_downgrades_stale_ok_worker_identity` (L159), `test_autonomy_maintenance_summary_does_not_treat_guard_cycle_as_worker_loop` (L186), `test_autonomy_maintenance_summary_recognizes_loop_worker_process` (L220), `test_autonomy_maintenance_summary_preserves_patch_queue_fields` (L246), `test_autonomy_maintenance_summary_passes_through_temporal_feed` (L280), `test_autonomy_maintenance_summary_temporal_feed_absent_yields_empty_dict` (L311), `test_autonomy_maintenance_summary_preserves_mission_and_owner_pressure` (L328), `test_runtime_artifact_show_action_preserves_message_and_detail` (L377), `test_guard_control_action_from_runtime_routes_restart` (L388), `test_core_runtime_action_from_runtime_routes_webui_restart` (L404), `test_autonomy_runtime_action_from_runtime_routes_start` (L418), `test_start_nova_core_routes_through_guard` (L432), `test_stop_core_owned_process_uses_runtime_identity` (L443), `test_restart_webui_schedules_and_shutdowns` (L462), `test_restart_webui_reports_start_when_no_server_is_available` (L479), `test_restart_guard_clears_stop_flag_before_delayed_start` (L496), `test_start_autonomy_maintenance_worker_starts_detached_loop` (L530), `test_stop_autonomy_maintenance_worker_uses_runtime_worker_identity` (L571), `test_core_stop_action_returns_guard_and_core_status` (L600), `test_autonomy_maintenance_start_action_returns_summary` (L613), `test_autonomy_maintenance_stop_action_returns_summary` (L624)

### `tests/test_runtime_heartbeat_service.py`

Tests: 1 | Declared lanes: `source_runtime_core`

`test_heartbeat_write_once_records_failure_and_recovery` (L12)

### `tests/test_runtime_process_state_service.py`

Tests: 6 | Declared lanes: `unit`

`test_logical_leaf_processes_filters_parent_launcher` (L13), `test_matches_relative_script_token_against_process_cwd` (L23), `test_prune_orphaned_guard_artifacts_removes_old_files` (L37), `test_cached_logical_service_processes_from_runtime_uses_cache_bundle` (L57), `test_runtime_process_tool_reads_expensive_process_fields_only_after_match` (L76), `test_prune_orphaned_core_artifacts_from_runtime_uses_runtime_scope` (L113)

### `tests/test_runtime_recovery.py`

Tests: 30 | Declared lanes: `integration`

`test_guard_status_payload_uses_pid_exists_and_runtime_flags` (L25), `test_guard_status_payload_collapses_wrapper_child_pair_to_leaf` (L45), `test_guard_status_payload_matches_relative_guard_script_against_process_cwd` (L67), `test_core_status_payload_treats_fresh_heartbeat_as_running` (L94), `test_core_status_payload_ignores_unrelated_live_process_during_heartbeat_only_fallback` (L113), `test_core_status_payload_collapses_wrapper_child_pair_to_leaf` (L142), `test_http_status_payload_reports_current_process_without_full_scan` (L164), `test_guard_status_payload_prunes_orphaned_lock_and_pid_artifacts` (L179), `test_cached_logical_service_processes_reuses_recent_fallback_scan` (L199), `test_guard_status_payload_uses_cached_fallback_only_without_runtime_artifacts` (L220), `test_guard_status_payload_can_skip_fallback_scan_for_fast_control_path` (L250), `test_core_status_payload_prunes_orphaned_state_and_stale_heartbeat` (L265), `test_acquire_lock_or_exit_replaces_stale_lock` (L286), `test_acquire_lock_or_exit_exits_when_live_guard_exists` (L334), `test_lock_identity_rejects_pid_reuse_with_wrong_command` (L381), `test_supervisor_tick_does_not_respawn_while_booting` (L400), `test_supervisor_tick_marks_running_attempt_failed_without_immediate_respawn` (L416), `test_runtime_failed_requires_sustained_heartbeat_staleness` (L433), `test_runtime_failed_clears_stale_latch_when_heartbeat_recovers` (L462), `test_supervisor_tick_resolves_failed_attempt_into_restart_wait` (L481), `test_boot_observation_records_supervised_restart_cause` (L501), `test_supervisor_tick_waits_for_resolution_before_restart_wait` (L518), `test_start_new_attempt_uses_observed_boot_window` (L534), `test_observe_boot_progress_adopts_runtime_child_from_wrapper` (L552), `test_supervisor_tick_waits_for_restart_deadline` (L580), `test_supervisor_tick_restarts_only_after_restart_wait_expires` (L594), `test_powershell_webui_status_uses_logical_processes` (L609), `test_command_center_ui_renders_runtime_process_note` (L637), `test_command_center_ui_separates_live_sessions_and_test_runs` (L646), `test_chat_ui_includes_browser_voice_controls` (L662)

### `tests/test_runtime_restart_provenance_service.py`

Tests: 2 | Declared lanes: `source_runtime_core`

`test_write_and_consume_pending_intent` (L30), `test_replace_false_preserves_existing_active_intent` (L48)

### `tests/test_runtime_status_service.py`

Tests: 6 | Declared lanes: `unit`

`test_action_readiness_payload_explains_runtime_controls` (L9), `test_runtime_failure_reasons_follow_status_and_timeline` (L21), `test_runtime_summary_payload_shapes_guard_core_and_webui` (L41), `test_http_status_payload_reads_current_process_identity` (L52), `test_guard_status_payload_uses_cached_fallback_without_artifacts` (L62), `test_guard_status_payload_from_runtime_resolves_scope` (L80)

### `tests/test_runtime_timeline_service.py`

Tests: 2 | Declared lanes: `unit`

`test_payload_combines_operator_guard_and_boot_events` (L11), `test_payload_keeps_guard_failures_when_no_recovery_anchor_exists` (L65)

### `tests/test_safety_envelope.py`

Tests: 9 | Declared lanes: `source_test_ecosystem`

`test_observe_mode_records_audit_without_copying` (L80), `test_enforce_mode_routes_new_family_to_pending_review` (L90), `test_enforce_mode_patch_filter_only_allows_promoted_matches` (L100), `test_patch_filter_reads_nested_generated_definitions` (L120), `test_short_single_turn_candidate_skips_diversity_gate` (L143), `test_pending_review_history_satisfies_human_veto_window` (L165), `test_promoted_history_satisfies_human_veto_window` (L184), `test_reevaluate_pending_reviews_moves_item_out_of_pending_when_window_is_satisfied` (L202), `test_replay_retry_recovers_transient_failure` (L226)

### `tests/test_schedule_registry.py`

Tests: 7 | Declared lanes: `source_test_ecosystem`

`test_all_task_names_are_unique` (L13), `test_required_tasks_are_registered` (L17), `test_work_tree_cycle_is_per_maintenance_cycle` (L31), `test_get_schedule_status_returns_all_tasks` (L39), `test_get_schedule_status_merges_live_state` (L46), `test_get_schedule_status_tolerates_empty_state` (L65), `test_schedule_registry_singleton_exposes_helpers` (L71)

### `tests/test_server_side_runtime_service.py`

Tests: 3 | Declared lanes: `source_runtime_core`, `unit`

`test_status_payload_direct_mode_uses_local_runtime_probe` (L8), `test_status_payload_proxy_mode_requires_frontdoor_base_url` (L24), `test_render_apache_reverse_proxy_vhost_contains_proxy_rules` (L33)

### `tests/test_session_admin_service.py`

Tests: 4 | Declared lanes: `unit`

`test_session_delete_action_returns_updated_sessions` (L8), `test_chat_user_upsert_hashes_via_save_callback` (L20), `test_delete_session_delegates_under_lock` (L35), `test_delete_session_from_runtime_uses_runtime_scope` (L55)

### `tests/test_session_state_service.py`

Tests: 7 | Declared lanes: `unit`

`test_fulfillment_state_get_set` (L16), `test_fulfillment_state_ignores_invalid` (L32), `test_subconscious_state_get_set` (L38), `test_subconscious_snapshot_empty` (L53), `test_subconscious_snapshot_with_state` (L67), `test_update_subconscious_state_uses_per_signal_window_thresholds` (L85), `test_update_subconscious_state_windowed_counts_decay_replan_pressure` (L135)

### `tests/test_sis_test_pipeline.py`

Tests: 15 | Declared lanes: none

`test_schema_probe_exposes_known_entities` (L20), `test_vendor_dictionary_index_contains_core_tables_and_columns` (L53), `test_predefined_report_index_contains_dashboard_patterns` (L67), `test_status_exposes_local_config_path` (L82), `test_schema_inventory_builds_metadata_query` (L98), `test_schema_inventory_rejects_unsafe_like_pattern` (L111), `test_safe_query_denies_missing_required_identifier` (L119), `test_safe_query_defaults_to_twenty_row_guard` (L124), `test_safe_query_live_mode_blocks_when_not_ready` (L131), `test_safe_query_live_mode_executes_when_ready` (L145), `test_sanitize_error_text_redacts_password_and_normalizes_login_failure` (L164), `test_sanitize_error_text_reports_integrated_identity_login_failure` (L174), `test_status_reports_trusted_auth_identity_mismatch` (L185), `test_status_reports_trusted_auth_failure_when_identity_matches` (L215), `test_safe_query_next_step_explains_trusted_identity_mismatch` (L241)

### `tests/test_smoke_e2e_script.py`

Tests: 1 | Declared lanes: `source_test_ecosystem`

`test_main_runs_unit_before_optional_memory_check` (L28)

### `tests/test_smoke_placeholder.py`

Tests: 1 | Declared lanes: `unit`

`test_placeholder` (L4)

### `tests/test_smoke_test.py`

Tests: 3 | Declared lanes: `unit`

`test_repo_root_is_importable_when_script_runs_directly` (L17), `test_run_health_check_base_uses_skip_ollama` (L20), `test_run_health_check_runtime_keeps_ollama_requirement` (L30)

### `tests/test_sock_service.py`

Tests: 43 | Declared lanes: `source_test_ecosystem`, `unit`

`test_mid_vram_selects_gpu_7b_chat_not_cpu_14b` (L51), `test_mid_vram_produces_stable_pair` (L58), `test_high_vram_selects_gpu_chat_model` (L64), `test_no_usable_gpu_falls_back_to_cpu_14b_on_large_ram` (L69), `test_limited_ram_and_vram_falls_back_to_3b` (L75), `test_routing_safe_pair_matches_chat_when_split_pair_unstable` (L80), `test_8gb_vram_produces_stable_pair_with_downgraded_routing` (L85), `test_routing_upgrades_on_high_vram` (L96), `test_vision_stays_7b_on_low_vram` (L101), `test_vision_upgrades_on_high_vram` (L106), `test_stt_upgrades_to_medium_on_capable_hardware` (L111), `test_stt_small_on_moderate_cpu` (L116), `test_stt_base_on_low_core_count` (L121), `test_rationale_populated_for_all_roles` (L126), `test_same_model_is_always_stable` (L135), `test_both_fitting_in_vram_is_stable` (L139), `test_split_pair_on_small_vram_is_unstable` (L143), `test_truly_cpu_only_chat_allows_routing_in_vram` (L147), `test_routing_safe_for_pair_avoids_unstable_split` (L154), `test_fast_warm_returns_ok` (L179), `test_slow_routing_rewarm_marks_validation_failed` (L189), `test_unreachable_ollama_returns_not_ok` (L210), `test_detects_changed_keys` (L224), `test_no_changes_when_policy_matches` (L245), `test_parses_pulled_models` (L265), `test_unreachable_ollama` (L274), `test_flags_unpulled_recommended_model` (L284), `test_no_missing_when_all_pulled` (L290), `test_run_returns_report_with_hardware_and_recommendation` (L299), `test_apply_writes_policy` (L320), `test_no_apply_when_policy_already_optimal` (L341), `test_detect_cpu_windows_parses_ps_json` (L369), `test_detect_cpu_windows_falls_back_on_none` (L377), `test_detect_ram_windows_converts_bytes` (L384), `test_detect_ram_windows_returns_zero_on_none` (L391), `test_detect_gpu_windows_nvidia_smi_path` (L397), `test_detect_gpu_windows_falls_back_to_cim` (L409), `test_detect_gpu_windows_no_gpu_returns_zero` (L420), `test_detect_npu_windows_pnp_device_found` (L428), `test_detect_npu_windows_falls_back_to_cpu_name` (L435), `test_detect_npu_windows_not_detected_on_standard_cpu` (L442), `test_find_nvidia_smi_returns_working_path` (L449), `test_find_nvidia_smi_returns_none_when_absent` (L459)

### `tests/test_source_root_inventory_service.py`

Tests: 4 | Declared lanes: `source_source_root_inventory`, `source_test_ecosystem`

`test_source_inventory_prunes_ignored_directories_before_classifying_files` (L12), `test_source_inventory_classifies_server_side_and_session_handoff_paths` (L38), `test_source_inventory_keeps_edfi_core_and_bisd_lane_separate` (L66), `test_source_inventory_ignores_vscode_tasks_json` (L88)

### `tests/test_source_root_judgment_service.py`

Tests: 5 | Declared lanes: `source_source_root_inventory`

`test_build_source_root_judgment_uses_work_tree_evidence` (L39), `test_build_source_root_judgment_ignores_ok_false_literals_in_read_source` (L59), `test_build_source_root_judgment_treats_fail_marker_as_failed_evidence` (L83), `test_restart_provenance_gap_requires_operator_attribution` (L102), `test_blocked_source_root_judgment_publishes_operator_notice` (L128)

### `tests/test_storage_watch_service.py`

Tests: 3 | Declared lanes: `source_test_ecosystem`

`test_snapshot_reports_warn_when_kidney_count_exceeds_limit` (L9), `test_snapshot_reports_release_validation_extract_pressure` (L34), `test_snapshot_reports_full_runtime_storage_pressure` (L66)

### `tests/test_subconscious_control_service.py`

Tests: 3 | Declared lanes: `unit`

`test_latest_report_reads_latest_json` (L11), `test_status_summary_orders_top_priorities_and_counts_generated_defs` (L20), `test_live_summary_surfaces_replan_sessions_and_reason_counts` (L62)

### `tests/test_subconscious_fallback_seams.py`

Tests: 3 | Declared lanes: `behavior`

`test_route_probe_does_not_turn_sample_text_into_supervisor_ownership` (L20), `test_weak_route_pressure_records_unclear_fit_without_overclaiming_owner` (L37), `test_fulfillment_viability_comes_from_existing_state_not_request_wording` (L47)

### `tests/test_subconscious_live_simulator.py`

Tests: 21 | Declared lanes: `integration`

`test_supervisor_boundary_scenario_stays_quiet_without_cracks` (L20), `test_single_weak_route_scenario_records_pressure_without_training_backlog` (L46), `test_multi_turn_weak_pressure_scenario_accumulates_cracks_and_backlog` (L66), `test_simulate_live_use_runs_default_scenarios` (L86), `test_default_live_scenario_families_create_variations_per_current_seam` (L95), `test_seed_turns_support_session_fact_recall_fallthrough_probe` (L112), `test_quiet_control_family_stays_quiet_across_variations` (L137), `test_fulfillment_family_records_weak_route_pressure_without_content_owner` (L157), `test_variation_aggregation_marks_script_specific_crack_when_only_one_variant_hits` (L172), `test_repeated_family_pressure_becomes_training_backlog_when_routes_stay_weak` (L217), `test_simulate_live_families_runs_family_aggregation` (L232), `test_memory_capture_family_is_retired_from_default_live_routes` (L246), `test_weather_continuation_family_stays_quiet_when_live_route_handles` (L251), `test_retrieval_followup_family_stays_quiet_when_live_route_handles` (L263), `test_patch_routing_family_records_weak_pressure_without_training_backlog` (L274), `test_session_fact_recall_family_records_noisy_unwired_pressure` (L288), `test_resolved_fulfillment_family_creates_no_training_priority` (L303), `test_script_specific_weakness_stays_lower_or_deferred` (L314), `test_robustness_scores_do_not_saturate_at_perfect_one` (L356), `test_script_specific_low_robustness_signals_do_not_enter_training_priority_queue` (L367), `test_quiet_control_creates_no_training_priority_noise` (L410)

### `tests/test_subconscious_review_authority_service.py`

Tests: 17 | Declared lanes: `source_subconscious`

`test_route_comparison_contract_approves_shared_lane` (L10), `test_ungated_candidate_is_not_reviewed` (L28), `test_probe_backed_supervisor_review_uses_real_route_snapshot` (L41), `test_live_supervisor_review_uses_runtime_supervisor_before_probe` (L75), `test_supervisor_reflection_can_approve_when_live_route_does_not_claim_turn` (L109), `test_live_fulfillment_review_uses_runtime_fulfillment_before_probe` (L148), `test_probe_backed_route_review_requires_both_routes_for_conflict` (L181), `test_probe_backed_weather_family_context_rejects_retired_supervisor_review` (L215), `test_probe_backed_patch_family_context_rejects_removed_supervisor_route` (L246), `test_probe_backed_memory_capture_family_context_rejects_retired_supervisor_review` (L277), `test_probe_backed_low_priority_review_can_defer_under_runtime_pressure` (L308), `test_runtime_pressure_ignores_stale_regression_failure` (L348), `test_low_priority_review_can_be_skipped_when_candidate_is_already_staged` (L368), `test_low_priority_review_can_be_skipped_when_prior_branch_is_staged_under_waiting_work_tree` (L412), `test_medium_priority_review_can_be_skipped_when_live_branch_has_open_work` (L456), `test_probe_backed_high_priority_review_notes_runtime_pressure_but_still_approves` (L507), `test_probe_backed_session_fact_family_context_rejects_removed_supervisor_route` (L548)

### `tests/test_subconscious_review_judgment_service.py`

Tests: 3 | Declared lanes: `source_subconscious`

`test_judgment_confirms_owner_root_repair_after_required_evidence` (L86), `test_judgment_retires_pressure_when_authority_finds_no_owner_root` (L133), `test_judgment_blocks_when_required_evidence_is_missing` (L184)

### `tests/test_subconscious_route_probe.py`

Tests: 5 | Declared lanes: `source_subconscious`

`test_explicit_supervisor_turn_emits_no_pressure_by_default` (L35), `test_clear_fulfillment_turn_flags_missed_when_fallback_used` (L50), `test_ordinary_fallback_turn_stays_low_pressure` (L64), `test_weak_comparison_emits_unclear_and_fit_weak` (L79), `test_route_conflict_case_emits_conflict_and_supervisor_overreach_when_chosen` (L92)

### `tests/test_subconscious_runner.py`

Tests: 8 | Declared lanes: `integration`

`test_select_live_scenario_families_filters_requested_family` (L41), `test_select_live_scenario_families_rejects_unknown_family` (L47), `test_build_unattended_report_creates_priorities_for_repeated_weak_routes` (L51), `test_write_report_bundle_writes_json_markdown_and_latest` (L65), `test_generated_session_definitions_cover_prioritized_family_scenarios` (L85), `test_write_generated_session_definitions_writes_manifest_and_payloads` (L98), `test_write_generated_session_definitions_skips_recently_retired_files` (L115), `test_main_runs_and_writes_requested_family_bundle` (L132)

### `tests/test_subconscious_training_backlog.py`

Tests: 4 | Declared lanes: `source_subconscious`

`test_repeated_weak_cracks_generate_candidate_tests` (L10), `test_single_weak_route_pressure_does_not_create_fulfillment_candidates` (L26), `test_clean_supervisor_snapshot_stays_empty` (L42), `test_backlog_builder_is_read_only_for_snapshot` (L63)

### `tests/test_subconscious_work_tree_triage_service.py`

Tests: 16 | Declared lanes: `source_work_tree`

`test_build_signal_marks_fulfillment_supervisor_route_review` (L7), `test_build_signal_uses_weather_family_context_when_available` (L33), `test_build_signal_can_match_family_context_by_suggested_test_name` (L55), `test_build_signal_treats_session_fact_recall_family_as_supervisor_owned` (L84), `test_build_signal_uses_patch_family_context_when_available` (L101), `test_build_signal_adds_family_specific_patch_guidance` (L125), `test_fallback_overuse_without_scenario_uses_family_review_context` (L142), `test_build_signal_ignores_retired_memory_capture_family_context` (L186), `test_build_signal_adds_family_specific_retrieval_guidance` (L211), `test_build_signal_uses_generic_route_guidance_for_retired_memory_family` (L228), `test_build_signal_adds_family_specific_weather_guidance` (L245), `test_build_signal_adds_family_specific_session_fact_guidance` (L262), `test_build_signal_sequences_subconscious_judgment_after_evidence` (L279), `test_build_signal_prefers_report_review_context_when_present` (L297), `test_build_signal_attaches_runtime_review_context_when_present` (L327), `test_review_gate_requires_owner_and_robustness` (L375)

### `tests/test_supervisor_ownership_gate.py`

Tests: 16 | Declared lanes: `behavior`

`test_default_supervisor_does_not_register_self_description_content_intents` (L9), `test_supervisor_does_not_claim_smalltalk_intent` (L21), `test_supervisor_does_not_claim_open_ended_name_origin_query` (L27), `test_supervisor_does_not_claim_open_ended_developer_profile_query` (L33), `test_supervisor_does_not_claim_session_summary_pattern` (L39), `test_supervisor_does_not_claim_explicit_weather_current_command` (L45), `test_supervisor_does_not_use_saved_location_for_pending_weather_affirmation` (L51), `test_supervisor_does_not_use_saved_location_for_pending_weather_consent_phrase` (L67), `test_supervisor_does_not_claim_retrieval_followup_content` (L83), `test_cli_loop_does_not_own_location_trigger_lists` (L101), `test_followup_dispatch_does_not_own_location_conversation_fallback` (L107), `test_cli_loop_does_not_own_pending_weather_followup_fallback` (L111), `test_http_chat_flow_does_not_import_turn_outcomes` (L116), `test_cli_loop_uses_shared_numeric_clarify_without_mixed_content_owner` (L138), `test_cli_loop_does_not_use_web_override_outcome` (L146), `test_cli_loop_does_not_apply_supervisor_bypass_reply_outcome` (L153)

### `tests/test_supervisor_probes.py`

Tests: 2 | Declared lanes: `unit`

`test_normalize_decision_captures_turn_acts_and_defaults` (L7), `test_build_suggestions_emits_repeated_issue_hint` (L25)

### `tests/test_supervisor_registry.py`

Tests: 1 | Declared lanes: `unit`

`test_default_registry_drives_supervisor_rule_order` (L8)

### `tests/test_supervisor_runtime.py`

Tests: 4 | Declared lanes: `source_runtime_core`

`test_register_rule_replaces_existing_name_and_sorts` (L8), `test_supervisor_does_not_claim_legacy_identity_intent_patterns` (L22), `test_result_is_explicitly_owned_requires_explicit_weather_ownership` (L32), `test_compatibility_wrapper_exposes_shared_intent_rules` (L48)

### `tests/test_teach_flow.py`

Tests: 2 | Declared lanes: `source_test_ecosystem`

`test_teach_store_example_and_file` (L35), `test_teach_propose_creates_zip` (L47)

### `tests/test_temporal_review_tool.py`

Tests: 25 | Declared lanes: `unit`

`test_policy_enabled_allows` (L33), `test_policy_disabled_blocks` (L38), `test_policy_key_absent_allows` (L43), `test_policy_tools_enabled_missing_allows` (L49), `test_admin_not_required` (L55), `test_empty_args_returns_no_temporal_input` (L66), `test_payload_empty_string_returns_no_temporal_input` (L71), `test_event_none_returns_no_temporal_input` (L75), `test_unknown_action_raises` (L85), `test_review_action_is_default_and_valid` (L89), `test_assess_action_is_valid` (L93), `test_route_action_is_valid` (L97), `test_event_dict_returns_ok_with_pressure_and_decision` (L107), `test_pressure_has_final_score` (L116), `test_decision_has_kind` (L124), `test_context_extra_forwarded` (L131), `test_json_string_payload_is_parsed` (L144), `test_list_of_two_events_returns_results_array` (L155), `test_each_batch_result_has_pressure` (L165), `test_empty_list_returns_no_temporal_input` (L171), `test_json_file_path_is_loaded` (L181), `test_ics_file_path_is_loaded` (L192), `test_missing_path_raises` (L212), `test_disabled_policy_check_policy_returns_false` (L223), `test_callers_honour_check_policy_before_run` (L228)

### `tests/test_test_profile_inventory_signal_service.py`

Tests: 3 | Declared lanes: `unit`

`test_signal_reports_validation_profile_gap` (L7), `test_signal_clears_when_profile_inventory_is_clean` (L31), `test_source_observed_tests_create_profile_drift_signal_without_becoming_gaps` (L40)

### `tests/test_test_session_control_service.py`

Tests: 19 | Declared lanes: `unit`

`test_saved_session_library_excludes_subconscious_generated_artifacts` (L11), `test_definition_root_helpers_build_saved_and_generated_paths` (L25), `test_generated_queue_operator_note_delegates_to_helper` (L39), `test_generated_queue_investigate_action_passes_payload_fields` (L51), `test_investigate_generated_work_queue_item_assembles_operator_dependencies` (L69), `test_available_test_session_definitions_merges_saved_and_generated` (L108), `test_available_test_session_definitions_reads_nested_real_world_tasks` (L127), `test_create_real_world_task_definition_writes_generated_task_file` (L159), `test_test_session_report_summaries_surface_status_and_artifacts` (L194), `test_test_session_report_summaries_surface_runtime_failure_status` (L228), `test_generated_work_queue_prefers_open_priority_items` (L270), `test_generated_work_queue_skips_action_on_current_drift_when_already_reviewed` (L287), `test_run_next_generated_work_queue_item_returns_blocked_when_open_items_are_not_actionable` (L308), `test_resolve_test_session_definition_accepts_absolute_or_catalog_lookup` (L318), `test_run_test_session_definition_executes_runner_and_returns_reports` (L330), `test_run_generated_test_session_pack_priority_orders_highest_first` (L351), `test_run_next_generated_work_queue_item_returns_clear_when_empty` (L373), `test_run_next_generated_work_queue_item_treats_reported_drift_as_evidence` (L383), `test_generated_pack_run_action_uses_payload_limit_and_mode` (L421)

### `tests/test_tool_console_service.py`

Tests: 3 | Declared lanes: `unit`

`test_list_tools_text_includes_direct_and_registered_sections` (L7), `test_handle_tools_runs_direct_tool` (L22), `test_handle_tools_ignores_unknown_planner_steps` (L37)

### `tests/test_tool_execution_service.py`

Tests: 5 | Declared lanes: `unit`

`test_build_tool_context` (L36), `test_execute_registered_tool_ok` (L43), `test_execute_registered_tool_invocation_error` (L48), `test_execute_registered_tool_runtime_error` (L53), `test_tool_error_message_admin` (L58)

### `tests/test_tool_registry.py`

Tests: 19 | Declared lanes: `unit`

`test_build_core_tool_exports_returns_expected_runtime_tools` (L18), `test_default_tool_events_path_uses_runtime_context` (L53), `test_manifest_lists_expected_tools` (L56), `test_temporal_review_tool_assesses_payload` (L82), `test_filesystem_ls_uses_allowed_root` (L113), `test_filesystem_denies_path_escape` (L129), `test_filesystem_find_defaults_to_live_workspace_scope` (L144), `test_filesystem_find_can_explicitly_search_archived_runtime_path` (L171), `test_filesystem_find_can_target_specific_file` (L193), `test_disabled_tool_is_denied` (L218), `test_tool_event_written_for_success` (L230), `test_patch_tool_requires_admin` (L252), `test_system_tool_queue_status_formats_generated_queue` (L266), `test_system_tool_system_check_alias_runs_health_check` (L305), `test_os_capability_tool_executes_through_controller_contract` (L324), `test_os_capability_tool_can_be_disabled_by_policy` (L356), `test_vision_tool_nonzero_helper_exit_is_recorded_as_error` (L370), `test_system_tool_nonzero_helper_exit_is_recorded_as_error` (L393), `test_core_keyword_to_status_event_pipeline` (L416)

### `tests/test_tool_registry_service.py`

Tests: 9 | Declared lanes: `unit`

`test_event_to_dict_basic` (L45), `test_event_to_dict_with_reason` (L63), `test_event_to_dict_with_error` (L76), `test_get_manifest_no_file` (L115), `test_get_manifest_caching` (L120), `test_append_event_creates_file` (L140), `test_append_event_appends_multiple` (L158), `test_list_tools_delegates_to_registry` (L171), `test_describe_tools_delegates_to_registry` (L177)

### `tests/test_validation_artifact_truth_service.py`

Tests: 4 | Declared lanes: `unit`

`test_missing_validation_action_directory_is_unknown_not_ok` (L12), `test_detects_llm_failure_hidden_under_green_regression` (L37), `test_older_validation_failure_does_not_taint_latest_regression_window` (L80), `test_detects_specific_ollama_chat_failure_as_llm_unavailable` (L116)

### `tests/test_voice_entrypoints.py`

Tests: 2 | Declared lanes: `unit`

`test_run_ask_nova_uses_run_cli_session` (L9), `test_voice_ask_nova_uses_voice_cli_session` (L16)

### `tests/test_voice_interaction_service.py`

Tests: 6 | Declared lanes: `unit`

`test_load_whisper_uses_policy_size_by_default` (L22), `test_record_and_transcribe_delegate_to_nova_core` (L38), `test_chat_uses_http_process_chat_by_default` (L55), `test_chat_defaults_to_shared_voice_session_id` (L63), `test_chat_falls_back_to_direct_llm_if_http_chat_raises` (L71), `test_speak_uses_engine_factory` (L84)

### `tests/test_weather_behavior.py`

Tests: 16 | Declared lanes: `behavior`

`test_weather_unavailable_without_structured_source` (L82), `test_weather_nws_success` (L88), `test_weather_formatter_deduplicates_prefixes` (L128), `test_weather_tool_style_outputs_single_tool_prefix` (L133), `test_weather_current_location_requires_coords` (L161), `test_location_coords_command_saves_state` (L166), `test_weather_current_location_uses_saved_coords` (L175), `test_weather_current_location_uses_live_runtime_location` (L208), `test_resolve_current_device_coords_uses_windows_fallback_and_persists_snapshot` (L252), `test_runtime_device_location_payload_reports_backend_provider_status` (L269), `test_jacket_question_classifies_as_weather` (L311), `test_umbrella_question_with_saved_location_still_requires_location_choice` (L319), `test_hot_outside_question_with_saved_location` (L327), `test_general_chat_returns_none` (L335), `test_ollama_failure_returns_none` (L343), `test_empty_text_returns_none` (L352)

### `tests/test_web_research_session_service.py`

Tests: 2 | Declared lanes: `unit`

`test_set_results_and_paginate` (L7), `test_next_page_empty_returns_none` (L34)

### `tests/test_windows_installer_scripts.py`

Tests: 1 | Declared lanes: `integration`

`test_installer_artifact_participates_in_release_governance` (L53)

### `tests/test_work_tree.py`

Tests: 58 | Declared lanes: `source_work_tree`

`test_next_open_branch_prefers_nearest_eligible_branch` (L40), `test_default_tree_allowed_tools_returns_full_copy` (L56), `test_inspect_tree_does_not_persist_snapshot_reads` (L65), `test_touch_branch_persists_resolution_state_without_status_change` (L76), `test_db_transaction_retries_retryable_operational_error` (L92), `test_dependency_blocks_branch_until_parent_branch_completes` (L125), `test_next_autonomous_step_waits_for_missing_tools` (L143), `test_next_autonomous_step_recommends_preferred_tool_when_ready` (L161), `test_next_autonomous_step_reports_missing_tool_when_branch_has_none` (L180), `test_next_autonomous_step_prefers_patch_rollback_for_rollback_task` (L191), `test_next_autonomous_step_prefers_patch_preview_apply_for_approved_preview_task` (L212), `test_next_autonomous_step_prefers_patch_preview_approve_for_pending_preview_task` (L237), `test_next_autonomous_step_prefers_generated_queue_run_for_generated_session_task` (L262), `test_execute_autonomous_step_passes_generated_session_file_arg` (L287), `test_os_capability_task_uses_structured_capability_request_args` (L313), `test_execute_autonomous_step_stops_when_branch_has_no_tool_assignment` (L348), `test_next_autonomous_step_does_not_wait_when_required_tool_failed` (L364), `test_tree_becomes_complete_after_all_tasks_complete` (L376), `test_run_autonomous_loop_without_executor_is_planning_only` (L386), `test_run_autonomous_loop_stops_when_tools_are_blocked` (L399), `test_execute_autonomous_step_runs_real_tool_and_completes_task` (L412), `test_execute_autonomous_step_marks_failed_tool_state` (L437), `test_blocked_task_blocks_branch_without_becoming_executable` (L462), `test_visual_tree_exposes_current_task_meta_for_blocked_requests` (L474), `test_execute_autonomous_step_patch_preview_apply_uses_preview_meta` (L487), `test_execute_autonomous_step_patch_preview_approve_uses_preview_meta` (L517), `test_execute_autonomous_step_read_not_a_file_marks_failed` (L547), `test_execute_autonomous_step_fail_marker_marks_failed` (L562), `test_execute_autonomous_step_records_structured_judgment_false_ok` (L577), `test_execute_autonomous_step_read_preserves_relative_path` (L605), `test_execute_autonomous_step_ls_not_a_folder_marks_failed` (L619), `test_execute_autonomous_step_ls_log_review_targets_runtime_dir` (L634), `test_execute_autonomous_step_patch_apply_not_a_file_marks_failed` (L650), `test_execute_autonomous_step_test_review_prefers_find_and_uses_test_symbol` (L666), `test_execute_autonomous_step_uses_explicit_task_tool_args` (L690), `test_subconscious_review_judgment_uses_current_branch_id` (L719), `test_execute_autonomous_step_find_no_matches_keeps_task_open` (L745), `test_next_autonomous_step_blocks_when_tree_policy_disallows_tool` (L764), `test_format_tree_snapshot_reports_next_step_and_policy` (L778), `test_run_autonomous_loop_executes_tools_when_callback_provided` (L790), `test_visual_tree_preserves_selected_active_branch_without_running_task` (L805), `test_visual_tree_honors_explicit_task_tool_before_text_guess` (L821), `test_selected_active_branch_persists_across_reload` (L848), `test_visual_tree_does_not_preserve_failed_active_branch` (L870), `test_next_autonomous_step_uses_decision_callback_selection` (L889), `test_next_autonomous_step_rejects_invalid_decision_branch` (L906), `test_next_autonomous_step_rejects_decision_task_mismatch` (L920), `test_sqlite_persistence_reloads_tree_branch_and_task_state` (L941), `test_next_autonomous_step_carries_single_block_target_metadata` (L985), `test_execute_autonomous_step_blocks_scoped_task_without_verification_payload` (L1016), `test_execute_autonomous_step_blocks_scope_expansion_for_scoped_task` (L1046), `test_execute_autonomous_step_completes_verified_scoped_task` (L1076), `test_sqlite_sets_schema_version` (L1108), `test_sqlite_reload_skips_invalid_branch_rows` (L1114), `test_list_visual_trees_prefers_trees_with_branch_history` (L1155), `test_list_visual_trees_omits_archived_trees` (L1173), `test_inspect_tree_includes_branch_notes` (L1203), `test_get_visual_tree_data_includes_branch_notes` (L1216)

### `tests/test_work_tree_decision_adapter.py`

Tests: 6 | Declared lanes: `source_work_tree`

`test_default_state_path_uses_runtime_context` (L33), `test_score_update_success_and_failure` (L38), `test_decision_bias_uses_highest_score` (L49), `test_state_persists_across_instances` (L58), `test_stale_blank_decision_expires_across_instances_without_score` (L68), `test_explicit_flush_expires_stale_pending_without_score` (L97)

### `tests/test_work_tree_operator_hold_service.py`

Tests: 3 | Declared lanes: `source_work_tree`

`test_detects_source_root_operator_judgment_hold` (L7), `test_detects_operator_outbox_meta_hold` (L25), `test_non_operator_blocked_branch_is_not_hold` (L42)

### `tests/test_work_tree_pressure_snapshot_service.py`

Tests: 1 | Declared lanes: `source_work_tree`, `unit`

`test_snapshot_splits_operator_hold_blocked_observing_and_release_stale_ready` (L7)

### `tests/test_work_tree_seeding_service.py`

Tests: 23 | Declared lanes: `source_work_tree`

`test_create_seeded_tree_builds_child_branches_without_text_inferred_tools` (L30), `test_seeded_tree_without_declared_tool_reports_missing_assignment` (L53), `test_llm_decompose_success_uses_llm_steps` (L79), `test_llm_decompose_fallback_on_failure` (L109), `test_llm_decompose_non_system_tool_does_not_infer_from_text` (L129), `test_seeded_tree_tagged_as_system_kind` (L159), `test_visual_payload_includes_kind_and_source` (L179), `test_explicit_duplicate_create_prompt_reuses_similar_active_tree` (L194), `test_work_identity_variations_reuse_single_tree` (L211), `test_work_identity_reuse_across_sessions` (L233), `test_identity_resolution_consistent_across_cli_and_http_sources` (L250), `test_reuse_continues_existing_tree_without_creating_duplicate_tree` (L267), `test_phase4_intent_overlap_strength_strong` (L296), `test_phase4_intent_overlap_strength_partial` (L308), `test_phase4_branching_decision_on_partial_overlap` (L319), `test_phase4_branching_creates_new_branch_under_tree` (L349), `test_phase4_tree_completion_detection` (L379), `test_phase4_completion_signal_detection_is_not_phrase_owned` (L410), `test_phase4_over_continuation_safeguard` (L424), `test_phase4_completed_tree_not_continued` (L444), `test_phase5_decision_record_contains_required_fields` (L473), `test_phase5_failure_new_tree_after_continue_penalizes_continue_score` (L493), `test_phase5_bias_reflects_high_scoring_decision` (L527)

### `tests/test_work_tree_signal_ingestion_service.py`

Tests: 104 | Declared lanes: `source_work_tree`

`test_execution_failure_surfaces_as_autonomy_orchestrator_signal` (L94), `test_repeated_signal_updates_existing_branch_with_evidence` (L152), `test_signal_tree_ingestion_archives_duplicate_signal_trees` (L186), `test_signal_tree_repairs_legacy_policy_to_full_default_tools` (L217), `test_repeated_signal_update_clears_stale_branch_tool_without_explicit_tool` (L255), `test_inactive_subconscious_candidate_retires_without_blocking_truth` (L286), `test_status_snapshot_ingests_autonomy_maintenance_last_error` (L329), `test_autonomy_maintenance_evidence_sequence_reaches_source_root_judgment` (L347), `test_status_snapshot_ingests_runtime_restart_pressure` (L388), `test_status_snapshot_ingests_temporal_pressure` (L407), `test_status_snapshot_does_not_treat_planned_restarts_as_pressure` (L437), `test_status_snapshot_ingests_runtime_restart_provenance_gap` (L459), `test_restart_provenance_judgment_becomes_operator_hold_instead_of_read_loop` (L483), `test_restart_provenance_stale_judgment_rechecks_before_read_loop` (L567), `test_status_snapshot_does_not_ingest_legacy_restart_provenance_gap` (L631), `test_status_snapshot_ingests_storage_watch_pressure` (L654), `test_status_snapshot_ingests_patch_pipeline_governance_gap` (L679), `test_status_snapshot_ingests_missing_edfi_capability_profile` (L698), `test_edfi_profile_branch_holds_when_healthy_without_read_evidence` (L713), `test_edfi_profile_branch_resolves_after_verified_read_evidence` (L733), `test_edfi_profile_branch_does_not_resolve_on_missing_file_read_evidence` (L758), `test_edfi_profile_evidence_loop_e2e` (L780), `test_edfi_profile_sequence_advances_after_profile_read_evidence` (L804), `test_status_snapshot_ingests_autonomy_orchestrator_ack_hold` (L831), `test_autonomy_orchestrator_evidence_sequence_reaches_source_root_judgment` (L852), `test_status_snapshot_ingests_subconscious_status_gap` (L895), `test_status_snapshot_ingests_action_ledger_gap` (L912), `test_branch_why_summary_includes_rationale_owner_and_review_focus` (L929), `test_subconscious_signal_branch_notes_capture_review_focus` (L956), `test_sequence_realigns_when_earlier_evidence_was_no_match` (L988), `test_sequence_realigns_premature_blocked_task_to_judgment_step` (L1048), `test_ingested_branch_notes_include_signal_evidence_lines` (L1111), `test_dependency_unreachable_defaults_to_dead_end_bucket` (L1150), `test_status_snapshot_ingests_first_wave_sources` (L1174), `test_sync_resolves_http_api_error_spike_when_alert_clears` (L1199), `test_status_snapshot_does_not_duplicate_typed_test_profile_alert_as_self_check` (L1208), `test_sync_resolves_stale_generic_self_check_when_typed_branch_owns_alert` (L1239), `test_status_snapshot_ingests_direct_control_runtime_fields` (L1288), `test_status_snapshot_ingests_remaining_owned_source_root_surfaces` (L1321), `test_installer_packaging_gap_routes_to_installer_validation_tool` (L1406), `test_installer_packaging_ready_status_resolves_branch` (L1447), `test_installer_packaging_ready_status_reopens_when_built_from_previous_package` (L1478), `test_operator_control_resolves_from_outbox_truth_when_surface_missing` (L1505), `test_operator_control_ignores_autonomy_internal_outbox_notices` (L1530), `test_operator_outbox_open_work_uses_stable_blocked_branch` (L1545), `test_find_task_contracts_do_not_use_space_joined_paths` (L1578), `test_source_root_sequence_reaches_judgment_after_evidence_tasks` (L1585), `test_active_source_signal_restarts_sequence_after_open_resolution_completion` (L1628), `test_source_root_inventory_exhausted_sequence_becomes_operator_hold` (L1675), `test_source_root_sequence_operator_response_prevents_hold_churn` (L1745), `test_source_root_sequence_routes_failed_evidence_to_judgment` (L1816), `test_source_root_failed_evidence_hold_recovers_after_stale_judgment` (L1886), `test_source_root_judgment_task_does_not_churn_when_operator_reason_is_still_missing` (L1946), `test_self_repair_inventory_alias_reaches_source_root_judgment` (L2005), `test_source_wiring_probe_gap_becomes_work_tree_pressure` (L2061), `test_source_wiring_probe_gap_resolves_when_probe_is_clean` (L2085), `test_status_snapshot_ingests_blocked_generated_queue_pressure` (L2116), `test_status_snapshot_resolves_blocked_generated_queue_pressure_when_actionable` (L2146), `test_status_snapshot_ingests_current_tool_error` (L2176), `test_status_snapshot_resolves_tool_error_when_stale` (L2202), `test_status_snapshot_ingests_os_capability_ledger_issue` (L2226), `test_status_snapshot_resolves_os_capability_ledger_issue_when_capability_runs_clean` (L2274), `test_status_snapshot_ingests_ollama_chat_route_gap` (L2313), `test_status_snapshot_ingests_ollama_model_missing_gap` (L2371), `test_status_snapshot_ingests_llm_reply_error_despite_green_ollama` (L2412), `test_status_snapshot_resolves_model_runtime_gap_when_ollama_contract_clears` (L2448), `test_status_snapshot_ingests_validation_artifact_truth_gap` (L2497), `test_status_snapshot_ingests_missing_validation_artifact_directory_as_missing_evidence` (L2557), `test_sync_status_snapshot_resolves_validation_artifact_truth_gap_when_clear` (L2606), `test_status_snapshot_ingests_ollama_port_owner_mismatch` (L2649), `test_status_snapshot_ingests_requested_voice_dependency_gap` (L2685), `test_status_snapshot_does_not_treat_unrequested_voice_as_failure_or_clearance` (L2717), `test_status_snapshot_resolves_voice_dependency_gap_when_requested_voice_loads` (L2756), `test_status_snapshot_ingests_vision_dependency_gap` (L2798), `test_status_snapshot_resolves_vision_dependency_gap_when_requested_vision_loads` (L2828), `test_status_snapshot_ingests_release_readiness_gap` (L2868), `test_release_readiness_gap_sequences_validation_before_outcome_recording` (L2903), `test_release_source_changed_sequences_to_rebuild_verify` (L2963), `test_status_snapshot_resolves_direct_control_runtime_fields_when_clear` (L3025), `test_status_snapshot_ignores_stale_regression_failure` (L3056), `test_status_snapshot_ingests_memory_health_bootstrap_gap` (L3072), `test_memory_health_signal_advances_finite_evidence_sequence` (L3108), `test_memory_health_updates_stale_blocked_origin_reason` (L3198), `test_memory_health_ready_origin_releases_identity_bootstrap_task` (L3254), `test_status_snapshot_uses_stable_regression_branch_identity` (L3325), `test_sync_status_snapshot_resolves_release_readiness_branch_when_ready` (L3356), `test_reopened_blocked_release_signal_restores_observing_resolution` (L3394), `test_partial_status_snapshot_does_not_resolve_absent_surfaces` (L3431), `test_sync_status_snapshot_resolves_regression_branch_when_stale` (L3463), `test_policy_gates_does_not_treat_missing_allow_domain_count_as_zero` (L3496), `test_looks_like_source_root_file_gap_detects_paths_and_suffixes` (L3503), `test_source_root_gap_evidence_task_uses_read_for_file_paths` (L3508), `test_source_root_gap_evidence_task_uses_find_for_root_ids` (L3513), `test_source_root_inventory_signal_uses_read_for_unclassified_files` (L3518), `test_source_root_inventory_signal_uses_stable_fingerprint_symbol` (L3535), `test_gap_evidence_task_reads_field_value_file_paths` (L3551), `test_source_wiring_probe_gap_evidence_task_finds_symbol_subjects` (L3556), `test_data_pipeline_evidence_task_reads_registry_or_lane_manifest` (L3561), `test_edfi_capability_profile_signal_absent_when_saved_profile_is_healthy` (L3567), `test_quiet_hold_suppresses_ambient_root_closure_signals` (L3591), `test_root_closure_signals_suppressed_during_release_drift` (L3627), `test_sync_status_snapshot_resolves_root_closure_branches_during_release_drift` (L3650), `test_dedupe_signal_branches_retires_duplicate_active_branches` (L3724), `test_sync_status_snapshot_retires_legacy_source_root_source_keys` (L3771)
