# Nova Code Surface Function Index

Generated from the active source tree on 2026-07-12. This is a mechanical inventory, not a claim that every function is correctly wired.

- Python source files indexed: 281
- Python functions/methods indexed: 3431
- Python classes indexed: 181

- Excluded: `.venv/`, `.git/`, `runtime/`, `tests/`, `agent-tools/`, `terminals/`, caches, and archived data lanes.
- Includes top-level functions, nested functions, class methods, and classes.
- Regenerate after structural code changes; line numbers are snapshots.

## `action_planner.py`

Lines: 28 | Functions/methods: 3 | Classes: 1

Classes: `ActionPlanner` (L9)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `__init__` | `self, config: Optional[dict]=None` | no |
| 13 | `plan` | `self, text: str` | no |
| 17 | `decide_actions` | `text: str, config: Optional[dict]=None` | no |

## `agent.py`

Lines: 134 | Functions/methods: 7 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `load_allowed_root` | `` | no |
| 25 | `is_within_allowed` | `path: Path` | no |
| 32 | `safe_path` | `user_path: str` | no |
| 42 | `cmd_read` | `args: list[str]` | no |
| 65 | `cmd_find` | `args: list[str]` | no |
| 104 | `cmd_ls` | `args: list[str]` | no |
| 115 | `main` | `` | no |

## `autonomy_maintenance.py`

Lines: 6250 | Functions/methods: 215 | Classes: 1

Classes: `_MaintenancePatchControlService` (L2816)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 211 | `_validation_subprocess_env` | `` | no |
| 221 | `_append_log` | `message: str` | no |
| 230 | `_load_state` | `` | no |
| 239 | `_save_state` | `state: dict` | no |
| 244 | `_append_autonomy_orchestrator_ledger` | `row: dict` | no |
| 250 | `_publish_operator_notice_from_autonomy` | `packet: dict, execution: dict` | no |
| 280 | `_publish_operator_notices_from_work_tree` | `work_tree_state: dict` | no |
| 353 | `_safe_int` | `value, default: int=0` | no |
| 360 | `_safe_float` | `value, default: float=0.0` | no |
| 367 | `_guard_health_for_orchestrator` | `` | no |
| 403 | `_preflight_checks_for_orchestrator` | `` | no |
| 412 | `_core_steward_for_orchestrator` | `state: dict, kidney_summary: dict, guard_health: dict \| None=None` | no |
| 437 | `_orchestrator_posture_band` | `core_steward: dict` | no |
| 447 | `_active_work_candidate_tool` | `candidate: dict` | no |
| 452 | `_active_work_candidate_branch` | `candidate: dict` | no |
| 469 | `_work_tree_pressure_truth` | `work_tree_state: dict` | no |
| 497 | `_work_tree_snapshot_for_orchestrator` | `work_tree_state: dict, active_work_candidates: list[dict] \| None=None` | no |
| 548 | `_steward_posture_for_orchestrator` | `core_steward: dict` | no |
| 573 | `_queue_pressure_for_orchestrator` | `generated_queue: dict, state: dict \| None=None` | no |
| 619 | `_nova_http_direct_process_alive` | `process: dict` | no |
| 635 | `_webui_health_for_orchestrator` | `*, bind_port: int=8080` | no |
| 678 | `_operator_webui_port_open` | `bind_port: int=8080` | no |
| 688 | `_probe_operator_webui_health` | `*, attempts: int=3, delay_sec: float=1.5` | no |
| 700 | `_ensure_operator_webui_running` | `state: dict` | no |
| 801 | `_mission_hold_blocks_legacy_execution` | `mission_snapshot: dict \| None` | no |
| 805 | `_mission_hold_blocks_generated_queue` | `mission_snapshot: dict \| None, *, policy_snapshot: dict \| None=None` | no |
| 817 | `_mission_hold_blocks_action` | `action_type: str, mission_snapshot: dict \| None, *, policy_snapshot: dict \| None=None, action_context: dict \| None=None` | no |
| 832 | `_mission_snapshot_for_ingestion` | `state: dict \| None, *, policy_snapshot: dict \| None=None` | no |
| 862 | `_truth_evidence_for_mission` | `state: dict \| None` | no |
| 920 | `_runtime_guard_status_for_orchestrator` | `core_steward: dict, guard_health: dict` | no |
| 947 | `_autonomy_maintenance_for_orchestrator` | `core_steward: dict` | no |
| 964 | `_autonomy_policy_settings` | `` | no |
| 973 | `_temporal_policy_settings` | `` | no |
| 982 | `_temporal_feed_paths` | `settings: dict \| None=None` | no |
| 1001 | `_temporal_feed_for_signal_ingestion` | `state: dict` | no |
| 1020 | `_autonomy_policy_bool` | `settings: dict, *names: str, default: bool=False` | no |
| 1027 | `_autonomy_policy_list` | `settings: dict, name: str, default: list[str]` | no |
| 1034 | `_autonomy_execution_mode` | `settings: dict \| None=None` | no |
| 1042 | `_autonomy_execution_enabled` | `settings: dict \| None=None` | no |
| 1049 | `_legacy_maintenance_execution_enabled` | `settings: dict \| None=None` | no |
| 1057 | `_policy_snapshot_for_orchestrator` | `` | no |
| 1131 | `_latest_subconscious_report_for_triage` | `` | no |
| 1145 | `_triage_runtime_context_for_orchestrator` | `state: dict \| None, generated_queue: dict, kidney_summary: dict \| None` | no |
| 1171 | `_max_score` | `scores: dict, key: str, score: float` | no |
| 1178 | `_triage_signal_from_priority` | `family: dict, priority: dict, runtime_context: dict` | no |
| 1201 | `_subconscious_terminal_no_repair_for_source_key` | `source_key: str` | no |
| 1221 | `_triage_lane_key` | `payload: dict` | no |
| 1229 | `_queue_owner_hints` | `generated_queue: dict` | no |
| 1264 | `_triage_hints_for_orchestrator` | `core_steward: dict, generated_queue: dict, *, latest_report: dict \| None=None, state: dict \| None=None, kidney_summary: dict \| None=None, mission_snapshot: dict \| None=None` | no |
| 1378 | `_subconscious_triage_signals_for_work_tree` | `*, state: dict \| None, generated_queue: dict \| None, latest_report: dict \| None, kidney_summary: dict \| None=None, limit: int=8` | no |
| 1423 | `_wiring_surface_status_keys` | `surface_id: str` | no |
| 1430 | `_probe_local_ollama_health` | `` | no |
| 1447 | `_ollama_status_fields_from_health` | `ollama_health: dict` | no |
| 1470 | `_probe_local_port_ownership` | `` | no |
| 1480 | `_apply_local_runtime_control_surfaces` | `payload: dict, *, only_missing: bool=True` | no |
| 1549 | `_apply_local_model_runtime_status` | `payload: dict, *, only_missing: bool=True` | no |
| 1575 | `_apply_local_frontdoor_cli_surfaces` | `payload: dict, *, only_missing: bool=True` | no |
| 1599 | `_probe_local_http_api_metrics` | `` | no |
| 1611 | `_probe_local_chat_login_enabled` | `` | no |
| 1623 | `_apply_local_operator_control_surfaces` | `payload: dict, *, only_missing: bool=True` | no |
| 1672 | `_apply_local_http_api_control_surfaces` | `payload: dict, *, only_missing: bool=True` | no |
| 1692 | `_apply_local_source_root_status_surfaces` | `payload: dict, *, only_missing: bool=True` | no |
| 1713 | `_apply_root_closure_inventory_surfaces` | `payload: dict, inventory: dict[str, object]` | no |
| 1723 | `_apply_source_root_inventory_surfaces` | `payload: dict, inventory: dict[str, object]` | no |
| 1749 | `_status_payload_missing_root_closure_truth_markers` | `payload: dict` | no |
| 1754 | `_status_payload_uses_thin_local_inventory_probe` | `payload: dict` | no |
| 1761 | `_merge_authoritative_wiring_status_keys` | `payload: dict` | no |
| 1785 | `_last_known_root_closure_inventory_from_state` | `` | no |
| 1800 | `_refresh_root_closure_inventory_surfaces` | `payload: dict, *, preserve_existing: bool=False` | no |
| 1825 | `_apply_layer_maturity_to_status_payload` | `payload: dict` | no |
| 1834 | `_enrich_signal_ingestion_status_payload` | `payload: dict, *, only_missing: bool=True` | no |
| 1851 | `_fetch_control_status_json` | `url: str, *, timeout_sec: float, read_limit: int` | no |
| 1865 | `_invalidate_control_status_caches_lazy` | `` | no |
| 1874 | `_maybe_invalidate_control_status_cache_for_release_drift` | `release_status: dict \| None` | no |
| 1885 | `_live_control_status_payload_http_full` | `fallback_payload: dict` | no |
| 1906 | `_live_control_status_payload_http_surfaces` | `fallback_payload: dict` | no |
| 1927 | `_live_control_status_payload_local_first` | `fallback_payload: dict` | no |
| 1950 | `_live_control_status_payload_for_signal_ingestion` | `fallback_payload: dict` | no |
| 1961 | `_local_dependency_payload_for_signal_ingestion` | `fallback_payload: dict` | no |
| 1967 | `_local_release_status_for_signal_ingestion` | `` | no |
| 1984 | `_probe_http_model_runtime_surfaces` | `` | no |
| 2006 | `_apply_release_runtime_truth_to_status_payload` | `status_payload: dict, *, state: dict \| None=None` | no |
| 2045 | `_validation_artifact_truth_payload_for_signal_ingestion` | `` | no |
| 2086 | `_last_action_context_for_orchestrator` | `state: dict` | no |
| 2114 | `_autonomy_orchestrator_status_for_signal_ingestion` | `state: dict \| None` | no |
| 2175 | `_layer_maturity_snapshot_for_orchestrator` | `state: dict` | no |
| 2187 | `_autonomy_orchestrator_input_envelope` | `*, state: dict, core_steward: dict, work_tree_state: dict, generated_queue: dict, guard_health: dict, active_work_candidates: list[dict] \| None=None, latest_report: dict \| None=None, kidney_summary: dict \| None=None, policy_snapshot: dict \| None=None` | no |
| 2248 | `_refresh_nova_mission_after_signal_ingestion` | `state: dict, *, kidney_summary: dict \| None=None` | yes |
| 2295 | `_run_autonomy_orchestrator_advisory` | `state: dict, kidney_summary: dict` | no |
| 2378 | `_elapsed_sec` | `start: float` | no |
| 2385 | `_subconscious_pack_timeout_sec` | `` | no |
| 2392 | `_run_subconscious_pack` | `` | no |
| 2419 | `_run_temporal_feed_pass` | `state: dict` | no |
| 2560 | `_available_test_session_definitions` | `limit: int=80` | no |
| 2570 | `_resolve_test_session_definition` | `session_name: str` | no |
| 2577 | `_test_session_report_summaries` | `limit: int=24` | no |
| 2581 | `_generated_work_queue` | `limit: int=24` | no |
| 2591 | `_run_test_session_definition` | `session_file: str` | no |
| 2604 | `_run_next_generated_work_queue_item` | `` | no |
| 2611 | `_record_generated_queue_run` | `state: dict, ok: bool, msg: str, extra: dict \| None=None` | no |
| 2645 | `_compact_report_summary` | `report: dict` | no |
| 2654 | `_compact_work_queue_summary` | `work_queue: dict` | no |
| 2685 | `_compact_generated_queue_execution_extra` | `extra: dict \| None` | no |
| 2699 | `_compact_tool_result_summary` | `result: object` | no |
| 2715 | `_compact_work_tree_history` | `history: list[dict] \| None, *, limit: int=8` | no |
| 2740 | `_compact_work_tree_cycle_payload` | `cycle: dict \| None` | no |
| 2762 | `_compact_autonomy_execution_extra` | `action_type: str, extra: dict \| None` | no |
| 2773 | `_compact_autonomy_execution_for_ledger` | `execution: dict \| None` | no |
| 2818 | `patch_control_state` | `*_args, **_kwargs` | no |
| 2822 | `patch_preview_show` | `*_args, **_kwargs` | no |
| 2826 | `patch_preview_decision` | `*_args, **_kwargs` | no |
| 2830 | `patch_preview_apply` | `*_args, **_kwargs` | no |
| 2834 | `patch_preview_entry` | `*_args, **_kwargs` | no |
| 2838 | `_unsupported_control_action` | `payload: dict` | no |
| 2844 | `_maintenance_logical_service_processes` | `script_path: Path, root_pid: int \| None=None` | no |
| 2849 | `_maintenance_cached_logical_service_processes` | `script_path: Path, *, cache_key: str='', max_age_seconds: float=0.0` | no |
| 2859 | `_maintenance_select_logical_process` | `processes: list[dict], *, pid: int \| None=None, create_time: float \| None=None` | no |
| 2868 | `_maintenance_prune_orphaned_guard_artifacts` | `_logical_processes: list[dict], _pid: int \| None, _pid_live: bool` | no |
| 2876 | `_maintenance_heartbeat_age_seconds` | `` | no |
| 2886 | `_maintenance_prune_orphaned_core_artifacts` | `_logical_processes: list[dict], _pid: int \| None, _pid_live: bool, _heartbeat_age: int \| None` | no |
| 2895 | `_maintenance_guard_status_payload` | `` | no |
| 2914 | `_maintenance_core_status_payload` | `` | no |
| 2931 | `_maintenance_webui_status_payload` | `` | no |
| 2935 | `_maintenance_start_guard` | `` | no |
| 2949 | `_maintenance_guard_control_action` | `payload: dict` | no |
| 2963 | `_maintenance_autonomy_maintenance_summary` | `` | no |
| 2967 | `_maintenance_start_autonomy_maintenance_worker` | `` | no |
| 2980 | `_maintenance_autonomy_runtime_action` | `payload: dict` | no |
| 2990 | `_maintenance_pulse_status_action` | `_payload: dict` | no |
| 2999 | `_maintenance_generated_queue_run_next_action` | `_payload: dict` | no |
| 3005 | `_maintenance_generated_queue_investigate_action` | `_payload: dict, state: dict` | no |
| 3035 | `_work_tree_cycle_dispatch_ok` | `status: str` | no |
| 3040 | `_maintenance_patch_queue_run_next_action` | `_payload: dict, state: dict` | no |
| 3051 | `_maintenance_active_work_tree_run_next_action` | `_payload: dict, state: dict` | no |
| 3109 | `_maintenance_codegen_run_action` | `_payload: dict, _state: dict` | yes |
| 3191 | `_dispatch_autonomy_control_action` | `action_type: str, payload: dict, events: list[dict], state: dict \| None=None` | no |
| 3194 | `_record_event` | `act: str, status: str, detail: str, event_payload: dict` | no |
| 3281 | `_execute_autonomy_recommendation` | `state: dict, packet: dict, policy_snapshot: dict` | no |
| 3329 | `_skipped_maintenance_execution_payload` | `state: dict, state_key: str, reason: str, *, tree_count: int=0` | no |
| 3341 | `_orchestrator_executed_lane_cycle` | `packet: dict, action_type: str` | no |
| 3354 | `_patch_queue_work_tree_cycle_for_execution_mode` | `state: dict, *, mission_snapshot: dict \| None, policy_snapshot: dict \| None, legacy_execution_enabled: bool` | no |
| 3382 | `_active_work_tree_cycle_for_execution_mode` | `state: dict, *, mission_snapshot: dict \| None, autonomy_orchestrator: dict \| None, legacy_execution_enabled: bool` | no |
| 3431 | `_runtime_worker_loop_identity_live` | `worker_state: dict` | no |
| 3453 | `_clear_non_loop_runtime_worker_state` | `state: dict, *, timestamp_fn: Callable[[], str] \| None=None` | no |
| 3484 | `_record_worker_cycle` | `*, cycle: int, interval_sec: int, status: str, code: int \| None=None` | no |
| 3512 | `_max_fallback_robustness` | `report: dict` | no |
| 3527 | `_build_micro_patch_zip` | `state: dict` | no |
| 3551 | `_micro_patch_candidates_require_review` | `files: list[Path]` | no |
| 3556 | `_zip_contains_only_promoted_patch_entries` | `zip_path: Path` | no |
| 3573 | `_is_patch_preview_definition_only_noop` | `row: dict` | no |
| 3600 | `_is_patch_preview_stale_noneligible` | `row: dict` | no |
| 3613 | `_auto_apply_if_eligible` | `zip_path: Path` | no |
| 3627 | `_run_daily_regression_if_due` | `state: dict` | no |
| 3657 | `_sync_regression_status_from_file` | `state: dict, *, status_path: Path=REGRESSION_STATUS_FILE` | no |
| 3686 | `_sync_signal_intake_work_tree` | `state: dict, kidney_summary: dict \| None=None, temporal_feed: dict \| None=None` | no |
| 3858 | `_run_patch_queue_cleanup` | `state: dict` | no |
| 3962 | `_reevaluate_pending_review_queue` | `state: dict` | no |
| 3968 | `_patch_queue_execution_policy` | `` | no |
| 3975 | `_patch_queue_timestamp` | `` | no |
| 3979 | `_patch_queue_preview_name` | `row: dict` | no |
| 3983 | `_patch_queue_source_key` | `row: dict` | no |
| 3990 | `_is_patch_preview_apply_ready` | `row: dict` | no |
| 4011 | `_is_patch_preview_auto_approvable` | `row: dict` | no |
| 4048 | `_select_patch_queue_auto_approval_target` | `review_rows: list[dict], current_revision: int` | no |
| 4059 | `_sort_key` | `row: dict` | no |
| 4073 | `_patch_queue_row_mode` | `row: dict` | no |
| 4087 | `_patch_queue_branch_title` | `row: dict` | no |
| 4101 | `_patch_queue_branch_notes` | `row: dict` | no |
| 4141 | `_patch_queue_task_title` | `row: dict` | no |
| 4145 | `_patch_queue_approve_task_title` | `row: dict` | no |
| 4149 | `_patch_queue_review_task_title` | `row: dict` | no |
| 4156 | `_decide_patch_queue_next_step` | `tree_id: str, options: list[dict]` | no |
| 4174 | `_ensure_patch_queue_tree` | `` | no |
| 4206 | `_is_patch_queue_managed_branch` | `tree, branch` | no |
| 4215 | `_find_patch_queue_branch` | `tree_id: str, source_key: str, preview_name: str, *, open_only: bool` | no |
| 4234 | `_complete_open_branch_tasks` | `branch_id: str` | no |
| 4245 | `_apply_patch_queue_branch_state` | `branch, row: dict, *, first_seen: bool, reopen: bool` | no |
| 4363 | `_sync_patch_queue_work_tree` | `state: dict` | no |
| 4485 | `_run_patch_queue_work_tree_cycle` | `state: dict, *, max_steps: int \| None=None` | no |
| 4563 | `_generated_queue_execution_policy` | `` | no |
| 4570 | `_generated_queue_item_file` | `item: dict` | no |
| 4574 | `_generated_queue_source_key` | `item: dict` | no |
| 4581 | `_generated_queue_priority` | `item: dict` | no |
| 4594 | `_generated_queue_branch_title` | `item: dict` | no |
| 4604 | `_generated_queue_branch_notes` | `item: dict` | no |
| 4638 | `_generated_queue_task_title` | `item: dict` | no |
| 4642 | `_ensure_generated_queue_tree` | `` | no |
| 4674 | `_is_generated_queue_managed_branch` | `tree, branch` | no |
| 4683 | `_find_generated_queue_branch` | `tree_id: str, source_key: str, session_file: str, *, open_only: bool` | no |
| 4702 | `_apply_generated_queue_branch_state` | `branch, item: dict, *, first_seen: bool, reopen: bool` | no |
| 4753 | `_sync_generated_queue_work_tree` | `state: dict` | no |
| 4853 | `_execute_generated_queue_planned_action` | `tool: str, args=None` | no |
| 4892 | `_run_generated_queue_work_tree_cycle` | `state: dict` | no |
| 4991 | `_active_work_tree_payload_eligible` | `payload: dict` | no |
| 5002 | `_active_work_tree_payload_matches_target` | `payload: dict, *, branch_target: str='', task_target: str='', tool_target: str=''` | no |
| 5024 | `_resolve_targeted_active_work_candidates` | `*, target_tree_id: str='', target_branch_id: str='', target_task_id: str='', target_tool: str=''` | no |
| 5070 | `_active_work_candidates_for_cycle` | `*, targeted: bool, tree_limit: int, candidate_limit: int, tree_target: str='', branch_target: str='', task_target: str='', tool_target: str=''` | no |
| 5090 | `_active_work_tree_candidates` | `limit: int=ACTIVE_WORK_TREE_MAX_TREES` | no |
| 5108 | `_candidate_uses_tool` | `candidate: dict, tool_name: str` | no |
| 5113 | `_active_work_candidate_context` | `candidate: dict` | no |
| 5124 | `_active_work_context_for_target` | `*, candidates: list[dict], target_branch_id: str='', target_task_id: str=''` | no |
| 5143 | `_mission_allowed_active_work_context` | `mission_snapshot: dict \| None, *, policy_snapshot: dict \| None, candidates: list[dict]` | no |
| 5161 | `_active_work_tree_target_decider` | `target_branch_id: str='', target_task_id: str='', target_tool: str=''` | no |
| 5172 | `_decide` | `_tree_id: str, options: list[dict]` | no |
| 5197 | `_active_work_tree_failure_aware_decider` | `tree_id: str, options: list[dict]` | yes |
| 5233 | `_sync_core_thinning_work_tree` | `state: dict` | no |
| 5266 | `_run_active_work_tree_cycle` | `state: dict, *, max_steps: int \| None=None, max_trees: int \| None=None, target_branch_id: str='', target_task_id: str='', target_tree_id: str='', target_tool: str='', sync_core_thinning: bool=True` | no |
| 5438 | `_retire_legacy_patch_update_trees` | `state: dict` | no |
| 5489 | `_archive_stale_complete_trees` | `state: dict` | no |
| 5534 | `_archive_empty_active_trees` | `state: dict` | no |
| 5570 | `_archive_stale_cli_active_trees` | `state: dict` | no |
| 5620 | `run_once` | `*, worker_loop: bool=False` | no |
| 5623 | `_finish_cycle` | `code: int, reason: str` | no |
| 6198 | `run_worker` | `*, interval_sec: int=300, max_cycles: int=0, continue_on_error: bool=True, run_once_fn: Callable[[], int] \| None=None, sleep_fn: Callable[[float], None]=time.sleep` | no |
| 6230 | `main` | `argv: list[str] \| None=None` | no |

## `camera.py`

Lines: 74 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `webcam_png_bytes` | `cam_index=0` | no |
| 37 | `ask_ollama` | `prompt, img_bytes` | no |

## `capabilities.py`

Lines: 125 | Functions/methods: 9 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 12 | `load_capabilities` | `` | no |
| 19 | `save_capabilities` | `data` | no |
| 24 | `register_capability` | `name, description` | no |
| 31 | `has_capability` | `name` | no |
| 36 | `explain_missing` | `task, required` | no |
| 53 | `list_capabilities` | `` | no |
| 57 | `describe_capabilities` | `` | no |
| 67 | `analyze_task` | `task: str` | no |
| 96 | `describe_runtime_identity` | `assistant_name='Nova'` | no |

## `choice_presenter.py`

Lines: 333 | Functions/methods: 13 | Classes: 1

Classes: `ChoicePresenter` (L206)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 42 | `_is_valid_assessment` | `assessment: FitAssessment` | no |
| 46 | `_model_signature` | `model: FulfillmentModel` | no |
| 58 | `_assessment_rank` | `assessment: FitAssessment` | no |
| 65 | `_dedupe_meaningless_variants` | `models: list[FulfillmentModel], assessments: Mapping[str, FitAssessment]` | no |
| 84 | `_frame_name` | `frame: object` | no |
| 89 | `_frame_scores` | `assessment: FitAssessment` | no |
| 96 | `_append_unique` | `target: list[str], values: list[str]` | no |
| 102 | `_comparative_frame_notes` | `model: FulfillmentModel, assessments: Mapping[str, FitAssessment], peer_models: list[FulfillmentModel]` | no |
| 152 | `_format_dimension_list` | `dimensions: list[str]` | no |
| 162 | `_build_choice_option` | `model: FulfillmentModel, assessment: FitAssessment, peer_models: list[FulfillmentModel], assessments: Mapping[str, FitAssessment], *, recommended: bool` | no |
| 201 | `_base_choice_set_id` | `intent: Intent, current_choice_set: ChoiceSet \| None` | no |
| 215 | `present` | `self, intent: Intent, models: list[FulfillmentModel], assessments: list[FitAssessment], *, current_choice_set: ChoiceSet \| None=None, shared_context: Mapping[str, Any] \| None=None` | yes |
| 311 | `build_choice_set` | `intent: Intent, models: list[FulfillmentModel], assessments: list[FitAssessment], *, current_choice_set: ChoiceSet \| None=None, shared_context: Mapping[str, Any] \| None=None, config: Mapping[str, Any] \| None=None` | yes |

## `conversation_manager.py`

Lines: 175 | Functions/methods: 28 | Classes: 2

Classes: `ConversationSession` (L8), `ConversationManager` (L153)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 23 | `reset_turn_flags` | `self` | no |
| 26 | `active_subject` | `self` | no |
| 34 | `set_conversation_state` | `self, state: Optional[dict]` | no |
| 38 | `_sync_pending_correction_target` | `self` | no |
| 47 | `state_kind` | `self` | no |
| 51 | `retrieval_state` | `self` | no |
| 56 | `set_retrieval_state` | `self, state: Optional[dict]` | no |
| 65 | `apply_state_update` | `self, next_state: Optional[dict], fallback_state: Optional[dict]=None` | no |
| 73 | `set_pending_action` | `self, action: Optional[dict]` | no |
| 76 | `set_pending_correction_target` | `self, target: Optional[str]` | no |
| 79 | `clear_pending_correction_target` | `self` | no |
| 82 | `set_prefer_web_for_data_queries` | `self, enabled: bool` | no |
| 85 | `set_language_mix_spanish_pct` | `self, value: int` | no |
| 92 | `mark_continuation_used` | `self` | no |
| 95 | `set_last_reflection` | `self, reflection: Optional[dict]` | no |
| 98 | `set_active_work_tree_id` | `self, tree_id: Optional[str]` | no |
| 101 | `set_active_work_identity` | `self, identity: Optional[str]` | no |
| 104 | `set_last_work_continuity` | `self, continuity: Optional[str]` | no |
| 107 | `set_last_branch_decision` | `self, decision: Optional[str]` | no |
| 110 | `record_decision` | `self, *, decision_type: str, work_identity_key: str, branch_id: str=''` | no |
| 117 | `set_decision_adapter_bias` | `self, bias: Optional[dict]` | no |
| 120 | `ledger_fields` | `self` | no |
| 129 | `reflection_summary` | `self` | no |
| 154 | `__init__` | `self` | no |
| 157 | `get` | `self, session_id: str` | no |
| 165 | `peek` | `self, session_id: str` | no |
| 169 | `drop` | `self, session_id: str` | no |
| 174 | `clear` | `self` | no |

## `data_sources/__init__.py`

Lines: 1 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `data_sources/edfi_bisd/__init__.py`

Lines: 1 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `data_sources/edfi_bisd/connector.py`

Lines: 362 | Functions/methods: 9 | Classes: 1

Classes: `EdFiBisdPipeline` (L44)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `_load_local_config` | `path: Optional[Path]` | no |
| 25 | `_shape_rows` | `items: list[Any]` | no |
| 47 | `__init__` | `self, manifest: PipelineManifest` | no |
| 53 | `_connection_id` | `self` | no |
| 57 | `_readiness` | `self` | no |
| 87 | `status` | `self` | no |
| 121 | `_next_step` | `self, readiness: Mapping[str, Any]` | no |
| 136 | `_execute_operation` | `self, operation: str, params: Mapping[str, Any], row_limit: int` | no |
| 188 | `safe_query` | `self, operation: str, params: Optional[Mapping[str, Any]]=None, *, row_limit: Optional[int]=None, dry_run: bool=True` | no |

## `diag.py`

Lines: 67 | Functions/methods: 4 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `ok` | `msg` | no |
| 12 | `warn` | `msg` | no |
| 13 | `fail` | `msg` | no |
| 15 | `main` | `` | no |

## `diag_ollama_check.py`

Lines: 24 | Functions/methods: 1 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 5 | `run` | `` | no |

## `doctor.py`

Lines: 231 | Functions/methods: 7 | Classes: 1

Classes: `CheckResult` (L24)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 31 | `_exists_file` | `path: Path` | no |
| 35 | `_exists_dir` | `path: Path` | no |
| 39 | `_default_policy` | `` | no |
| 72 | `apply_lightweight_fixes` | `` | no |
| 97 | `run_preflight` | `` | no |
| 170 | `summarize` | `results: list[CheckResult], quiet: bool=False` | no |
| 191 | `main` | `` | no |

## `dynamic_replanner.py`

Lines: 262 | Functions/methods: 10 | Classes: 1

Classes: `DynamicReplanner` (L158)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 21 | `_model_signature` | `model: FulfillmentModel` | no |
| 33 | `_assessment_rank` | `assessment: FitAssessment \| None` | no |
| 42 | `_is_valid_assessment` | `assessment: FitAssessment \| None` | no |
| 46 | `_resolve_assessments` | `intent: Intent \| None, models: list[FulfillmentModel] \| None, assessments: list[FitAssessment] \| None, replan_context: ReplanContext, shared_context: Mapping[str, Any] \| None, config: Mapping[str, Any]` | no |
| 68 | `_dedupe_models` | `models: list[FulfillmentModel], assessment_by_model: Mapping[str, FitAssessment]` | no |
| 86 | `_rank_models` | `models: list[FulfillmentModel], assessment_by_model: Mapping[str, FitAssessment], previous_selected_model_id: str \| None` | no |
| 102 | `_prune_models_and_assessments` | `models: list[FulfillmentModel] \| None, assessments: list[FitAssessment] \| None, replan_context: ReplanContext, config: Mapping[str, Any]` | no |
| 132 | `_stabilize_selected_path` | `revised_choice_set: ChoiceSet \| None, replan_context: ReplanContext, assessments: list[FitAssessment] \| None` | no |
| 168 | `replan` | `self, replan_context: ReplanContext, *, intent: Intent \| None=None, models: list[FulfillmentModel] \| None=None, assessments: list[FitAssessment] \| None=None, choice_set: ChoiceSet \| None=None, shared_context: Mapping[str, Any] \| None=None` | yes |
| 233 | `replan_state` | `replan_context: ReplanContext, *, intent: Intent \| None=None, models: list[FulfillmentModel] \| None=None, assessments: list[FitAssessment] \| None=None, choice_set: ChoiceSet \| None=None, shared_context: Mapping[str, Any] \| None=None, config: Mapping[str, Any] \| None=None` | yes |

## `env_inspector.py`

Lines: 90 | Functions/methods: 4 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 9 | `check_file` | `path: Path` | no |
| 13 | `load_json` | `path: Path` | no |
| 23 | `inspect_environment` | `` | no |
| 66 | `format_report` | `data` | no |

## `fit_evaluator.py`

Lines: 293 | Functions/methods: 13 | Classes: 1

Classes: `FitEvaluator` (L213)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 21 | `_tokenize` | `parts: list[str]` | no |
| 31 | `_model_terms` | `model: FulfillmentModel` | no |
| 48 | `_intent_terms` | `intent: Intent` | no |
| 60 | `_overlap_score` | `left: set[str], right: set[str]` | no |
| 68 | `_frame_overrides` | `shared_context: Mapping[str, Any] \| None` | no |
| 86 | `_frame_weights` | `intent: Intent, shared_context: Mapping[str, Any] \| None` | no |
| 119 | `_weighted_summary_score` | `frame_scores: dict[str, float], frame_weights: Mapping[str, float]` | no |
| 129 | `_heuristic_frame_scores` | `intent: Intent, model: FulfillmentModel` | no |
| 162 | `_resolved_frame_scores` | `intent: Intent, model: FulfillmentModel, shared_context: Mapping[str, Any] \| None` | no |
| 173 | `_frame_rationale` | `frame_name: str, score: float` | no |
| 183 | `_fit_band` | `frame_scores: dict[str, float]` | no |
| 222 | `evaluate` | `self, intent: Intent, models: list[FulfillmentModel], *, prior_assessments: list[FitAssessment] \| None=None, shared_context: Mapping[str, Any] \| None=None` | yes |
| 274 | `evaluate_model_fit` | `intent: Intent, models: list[FulfillmentModel], *, prior_assessments: list[FitAssessment] \| None=None, shared_context: Mapping[str, Any] \| None=None, config: Mapping[str, Any] \| None=None` | yes |

## `fulfillment_contracts.py`

Lines: 135 | Functions/methods: 0 | Classes: 11

Classes: `FitFrame` (L9), `ChoiceMode` (L17), `CollapseStatus` (L22), `ReplanReason` (L29), `Intent` (L44), `FulfillmentModel` (L58), `FrameScore` (L76), `FitAssessment` (L84), `ChoiceOption` (L100), `ChoiceSet` (L109), `ReplanContext` (L122)

No Python functions or methods.

## `fulfillment_flow_example.py`

Lines: 203 | Functions/methods: 3 | Classes: 3

Classes: `DemoFlowResult` (L21), `DemoIntentInterpreter` (L31), `DemoFulfillmentModelGenerator` (L73)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 34 | `interpret` | `self, raw_input: str, *, current_intent: Intent \| None=None, shared_context: dict[str, object] \| None=None` | no |
| 76 | `generate` | `self, intent: Intent, *, existing_models: list[FulfillmentModel] \| None=None, shared_context: dict[str, object] \| None=None` | no |
| 117 | `run_demo_flow` | `` | no |

## `fulfillment_model_generator.py`

Lines: 175 | Functions/methods: 8 | Classes: 1

Classes: `FulfillmentModelGenerator` (L89)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_unique` | `values: list[str]` | no |
| 26 | `_model_by_id` | `models: list[FulfillmentModel] \| None` | no |
| 30 | `_filtered_existing_models` | `intent: Intent, models: list[FulfillmentModel] \| None` | no |
| 51 | `_dedupe_models_by_path_shape` | `models: list[FulfillmentModel]` | no |
| 63 | `_needs_evidence_first_model` | `intent: Intent` | no |
| 70 | `_build_model` | `intent: Intent, *, model_id: str, label: str, path_shape: str, differentiators: list[str], strengths: list[str], expected_friction: list[str], risks: list[str], information_needs: list[str] \| None=None` | no |
| 99 | `generate` | `self, intent: Intent, *, existing_models: list[FulfillmentModel] \| None=None, shared_context: Mapping[str, Any] \| None=None` | yes |
| 157 | `generate_fulfillment_models` | `intent: Intent, *, existing_models: list[FulfillmentModel] \| None=None, shared_context: Mapping[str, Any] \| None=None, config: Mapping[str, Any] \| None=None` | yes |

## `health.py`

Lines: 308 | Functions/methods: 22 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 34 | `configured_models` | `` | no |
| 45 | `required_ollama_models` | `` | no |
| 53 | `ok` | `msg: str` | no |
| 57 | `warn` | `msg: str` | no |
| 61 | `bad` | `msg: str` | no |
| 65 | `check_heartbeat` | `max_age: int=10` | no |
| 72 | `check_state` | `` | no |
| 86 | `check_ollama` | `timeout: float=1.0` | no |
| 91 | `ollama_health_payload` | `timeout: float=2.0` | no |
| 102 | `tcp_listening` | `host: str='127.0.0.1', port: int=11434, timeout: float=1.0` | no |
| 110 | `ollama_api_up` | `timeout: float=2.0` | no |
| 114 | `ollama_tags` | `` | no |
| 125 | `start_ollama_serve_detached` | `` | no |
| 140 | `kill_ollama` | `` | no |
| 148 | `check_gpu` | `` | no |
| 159 | `check_mic` | `` | no |
| 173 | `check_camera` | `` | no |
| 187 | `check_python_packages` | `` | no |
| 201 | `repair_ollama` | `` | no |
| 226 | `run_check` | `include_ollama: bool=True` | no |
| 253 | `run_diag` | `` | no |
| 291 | `main` | `` | no |

## `http_chat_flow.py`

Lines: 74 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 5 | `prepare_chat_turn` | `*, session_id: str, text: str, session, ledger: dict, append_session_turn: Callable[[str, str, str], list[tuple[str, str]]]` | no |
| 21 | `resume_last_pending_turn` | `session_id: str, user_id: str='', *, get_active_user: Callable[[], str \| None], set_active_user: Callable[[str \| None], None], get_last_session_turn: Callable[[str], tuple[str, str] \| None], get_session_turns: Callable[[str], list[tuple[str, str]]], generate_chat_reply: Callable[[list[tuple[str, str]], str], tuple[str, dict[str, Any]]], append_session_turn: Callable[[str, str, str], list[tuple[str, str]]], invalidate_control_status_cache: Callable[[], None] \| None=None` | no |
| 58 | `resume_last_pending_turn_from_runtime` | `session_id: str, user_id: str='', *, runtime_scope: dict[str, object]` | no |

## `http_session_store.py`

Lines: 214 | Functions/methods: 9 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 12 | `load_persisted_sessions` | `*, store_path: Path, session_turns: SessionTurns, session_owners: SessionOwners, max_stored_turns_per_session: int` | no |
| 56 | `persist_sessions` | `*, runtime_dir: Path, store_path: Path, session_turns: SessionTurns, session_owners: SessionOwners, max_stored_sessions: int, max_stored_turns_per_session: int` | no |
| 88 | `trim_turns` | `turns: List[Tuple[str, str]], *, max_turns: int` | no |
| 94 | `append_session_turn` | `session_id: str, role: str, text: str, *, session_turns: SessionTurns, max_turns: int, persist_callback: Callable[[], None]` | no |
| 110 | `get_session_turns` | `session_id: str, *, session_turns: SessionTurns` | no |
| 114 | `get_last_session_turn` | `session_id: str, *, session_turns: SessionTurns` | no |
| 121 | `session_summaries` | `*, session_turns: SessionTurns, session_owners: SessionOwners, state_manager, limit: int=60` | no |
| 167 | `delete_session` | `session_id: str, *, session_turns: SessionTurns, session_owners: SessionOwners, state_manager, persist_callback: Callable[[], None], on_session_end: Callable[[str, object], None] \| None=None` | no |
| 190 | `assert_session_owner` | `session_id: str, user_id: str, *, session_owners: SessionOwners, normalize_user_id: Callable[[str], str], persist_callback: Callable[[], None], allow_bind: bool=True` | no |

## `http_test_session_helpers.py`

Lines: 100 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 6 | `generated_queue_operator_note` | `item: Mapping[str, Any]` | no |
| 40 | `investigate_generated_work_queue_item` | `*, session_file: str='', session_id: str='', user_id: str='operator', generated_work_queue: Callable[[int], dict], resolve_operator_macro: Callable[[str], Any], render_operator_macro_prompt: Callable[[Any, dict, str], tuple[bool, str, dict[str, str]]], normalize_user_id: Callable[[str], str], assert_session_owner: Callable[[str, str], tuple[bool, str]], process_chat: Callable[[str, str, str], str], session_summaries: Callable[[int], list[dict]]` | no |

## `inspect_core_fail.py`

Lines: 34 | Functions/methods: 1 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 12 | `main` | `` | no |

## `intent_interpreter.py`

Lines: 250 | Functions/methods: 14 | Classes: 1

Classes: `IntentInterpreter` (L170)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 17 | `_normalized_text` | `text: str` | no |
| 21 | `_unique` | `values: list[str]` | no |
| 36 | `_intent_id` | `seed_text: str` | no |
| 41 | `_recent_user_turns` | `shared_context: Mapping[str, Any] \| None` | no |
| 58 | `_looks_like_followup_adjustment` | `text: str` | no |
| 77 | `_initial_achievement_goal` | `raw_input: str, shared_context: Mapping[str, Any] \| None` | no |
| 87 | `_initial_evidence` | `raw_input: str, shared_context: Mapping[str, Any] \| None` | no |
| 98 | `_combined_seed_text` | `raw_input: str, shared_context: Mapping[str, Any] \| None` | no |
| 102 | `_extract_constraints` | `raw_input: str` | no |
| 120 | `_extract_preferences` | `raw_input: str` | no |
| 147 | `_extract_success_criteria` | `raw_input: str` | no |
| 159 | `_extract_unresolved_questions` | `raw_input: str` | no |
| 180 | `interpret` | `self, raw_input: str, *, current_intent: Intent \| None=None, shared_context: Mapping[str, Any] \| None=None` | yes |
| 232 | `interpret_intent` | `raw_input: str, *, current_intent: Intent \| None=None, shared_context: Mapping[str, Any] \| None=None, config: Mapping[str, Any] \| None=None` | yes |

## `kidney.py`

Lines: 656 | Functions/methods: 28 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 44 | `_load_policy` | `` | no |
| 52 | `policy_kidney` | `` | no |
| 74 | `_now_ts` | `` | no |
| 78 | `_age_seconds` | `path: Path, now: float \| None=None` | no |
| 86 | `_load_json` | `path: Path, default: Any` | no |
| 94 | `_load_protect_patterns` | `` | no |
| 105 | `_save_json` | `path: Path, payload: Any` | no |
| 110 | `_load_retired_generated_definition_index` | `*, now: float \| None=None` | no |
| 136 | `load_retired_generated_definition_index` | `` | no |
| 140 | `_definition_metadata` | `path: Path` | no |
| 152 | `_record_retired_generated_definition` | `path: Path, item: dict[str, Any], *, target_path: str='', now: float \| None=None` | no |
| 183 | `_file_fingerprint` | `path: Path` | no |
| 190 | `add_protect_pattern` | `pattern: str` | no |
| 203 | `_is_protected` | `path: Path, patterns: list[str]` | no |
| 208 | `_load_latest_audit_by_file` | `` | no |
| 228 | `_path_size_bytes` | `path: Path` | no |
| 241 | `_build_candidate` | `path: Path, category: str, action: str, reason: str, *, extra: dict[str, Any] \| None=None` | no |
| 256 | `scan_candidates` | `` | no |
| 425 | `_snapshot_paths` | `candidates: list[dict[str, Any]]` | no |
| 446 | `_skip_cleanup_snapshot` | `candidates: list[dict[str, Any]], *, cfg: dict[str, Any]` | no |
| 462 | `_cleanup_snapshot_max_total_bytes` | `cfg: dict[str, Any]` | no |
| 470 | `_prune_cleanup_snapshots` | `*, cfg: dict[str, Any]` | no |
| 513 | `_archive_target_for` | `path: Path` | no |
| 519 | `_apply_candidate` | `item: dict[str, Any]` | no |
| 549 | `_write_status_payload` | `path: Path, payload: dict[str, Any]` | no |
| 554 | `run_kidney` | `*, dry_run: bool=False, logger: Callable[[str], None] \| None=None, write_status: bool \| None=None` | no |
| 616 | `render_status` | `` | no |
| 642 | `render_run` | `*, dry_run: bool` | no |

## `look.py`

Lines: 47 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 14 | `screenshot_png_bytes` | `` | no |
| 23 | `ask_ollama_with_image` | `prompt: str, png_bytes: bytes` | no |

## `look_crop.py`

Lines: 59 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 14 | `screenshot_center_crop_png_bytes` | `crop_w=1400, crop_h=900` | no |
| 31 | `ask_ollama_with_image` | `prompt: str, png_bytes: bytes` | no |

## `memory.py`

Lines: 489 | Functions/methods: 17 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 16 | `_resolve_memory_db_path` | `` | no |
| 43 | `load_policy` | `` | no |
| 46 | `connect` | `` | no |
| 79 | `_normalize_scope` | `scope: str` | no |
| 86 | `_scope_where` | `scope: str, user: Optional[str]` | no |
| 99 | `embed` | `text: str` | no |
| 129 | `vec_to_blob` | `v: List[float]` | no |
| 134 | `blob_to_vec` | `b: bytes` | no |
| 140 | `vec_norm` | `v: List[float]` | no |
| 143 | `cosine` | `a: List[float], b: List[float]` | no |
| 157 | `query_tokens` | `text: str` | no |
| 167 | `add_memory` | `kind: str, source: str, text: str, user: str='', scope: str='shared'` | no |
| 183 | `recall` | `query: str, top_k: int=5, min_score: float=0.25, exclude_sources: Optional[Iterable[str]]=None, exclude_kinds: Optional[Iterable[str]]=None, user: Optional[str]=None, scope: str='shared', debug: bool=False` | no |
| 275 | `recall_explain` | `query: str, top_k: int=5, min_score: float=0.25, exclude_sources: Optional[Iterable[str]]=None, exclude_kinds: Optional[Iterable[str]]=None, user: Optional[str]=None, scope: str='shared'` | no |
| 368 | `reset` | `` | no |
| 373 | `stats` | `scope: str='shared', user: Optional[str]=None` | no |
| 408 | `main` | `` | no |

## `nova_core.py`

Lines: 3798 | Functions/methods: 271 | Classes: 1

Classes: `SubprocessTTS` (L1366)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 264 | `_ensure_voice_deps` | `` | yes |
| 277 | `record_seconds` | `seconds: int=3` | no |
| 288 | `transcribe` | `model, audio_int16` | no |
| 349 | `_policy_manager` | `` | no |
| 353 | `_identity_memory_service` | `` | yes |
| 363 | `_identity_memory_text_allowed` | `kind: str, text: str` | no |
| 367 | `_save_behavior_metrics` | `` | no |
| 374 | `_fulfillment_flow_service` | `` | no |
| 385 | `_fulfillment_route_viability` | `user_text: str, session: object, recent_turns: list[tuple[str, str]], *, pending_action: Optional[dict]=None, semantic_observation: Optional[dict]=None` | no |
| 403 | `_deterministic_route_viability` | `user_text: str, session: object, recent_turns: list[tuple[str, str]], *, pending_action: Optional[dict]=None` | no |
| 426 | `_probe_turn_routes` | `user_text: str, session: object, recent_turns: list[tuple[str, str]], pending_action: Optional[dict]=None, semantic_observation: Optional[dict]=None` | no |
| 452 | `behavior_record_event` | `event: str` | no |
| 456 | `behavior_set_flag` | `name: str, value: object=True, **details` | no |
| 472 | `behavior_get_metrics` | `` | no |
| 476 | `action_ledger_add_step` | `record: Optional[dict], stage: str, outcome: str, detail: str='', **data` | no |
| 487 | `action_ledger_route_summary` | `record_or_trace: Optional[object]` | no |
| 502 | `_recent_action_ledger_records` | `limit: int=20` | no |
| 510 | `_detect_repeated_tool_intent_without_execution` | `records: Optional[list[dict]]=None, limit: int=20` | no |
| 519 | `_top_repeated_correction_class` | `records: Optional[list[dict]]=None, limit: int=20` | no |
| 523 | `_count_routing_overrides_recently` | `records: Optional[list[dict]]=None, limit: int=20` | no |
| 531 | `_record_used_routing_override` | `record: Optional[dict]` | no |
| 535 | `_routing_stable_recently` | `records: Optional[list[dict]]=None, limit: int=20` | no |
| 544 | `_sample_intents_last` | `records: Optional[list[dict]]=None, count: int=5` | no |
| 548 | `_append_self_reflection` | `payload: dict` | no |
| 557 | `_append_health_snapshot` | `payload: dict` | no |
| 566 | `record_health_snapshot` | `*, session_id: str, reflection: Optional[dict], session_end: bool=False` | no |
| 582 | `_recent_self_reflection_rows` | `limit: int=3` | no |
| 602 | `maybe_log_self_reflection` | `*, limit: int=20, every: int=5, records: Optional[list[dict]]=None, total_records: Optional[int]=None, extra_payload: Optional[dict]=None` | no |
| 624 | `build_turn_reflection` | `session_state: ConversationSession, *, entry_point: str, session_id: str, current_decision: dict` | no |
| 656 | `_intent_trace_preview` | `text: str, *, limit: int=120` | no |
| 663 | `_supervisor_result_has_route` | `rule_result: Optional[dict]` | no |
| 668 | `_supervisor_candidate_trace` | `rule_result: Optional[dict]` | no |
| 695 | `_supervisor_phase_record` | `rule_result: Optional[dict], *, phase: str` | no |
| 708 | `_build_routing_decision` | `text: str, *, entry_point: str, intent_result: Optional[dict]=None, handle_result: Optional[dict]=None, final_owner: str='pending', reply_contract: str='', reply_outcome: Optional[dict]=None, turn_acts: Optional[list[str]]=None` | no |
| 733 | `_finalize_routing_decision` | `routing_decision: Optional[dict], *, planner_decision: str='', reply_contract: str='', reply_outcome: Optional[dict]=None, turn_acts: Optional[list[str]]=None` | no |
| 784 | `record_intent_outcome` | `text: str, intent: dict, strategy: dict, *, outcome: str='completed'` | no |
| 805 | `_store_supervisor_correction_record` | `correction_text: str, *, input_source: str, last_assistant: str='', parsed_correction: str=''` | no |
| 823 | `start_action_ledger_record` | `user_input: str, *, channel: str='cli', session_id: str='', input_source: str='typed', active_subject: str=''` | no |
| 841 | `write_action_ledger_record` | `record: dict` | no |
| 847 | `_append_memory_event` | `payload: dict` | no |
| 853 | `_record_memory_event` | `action: str, status: str, *, user: Optional[str]=None, scope: str='private', backend: str='', kind: str='', source: str='', query: str='', reason: str='', error: str='', result_count: Optional[int]=None, duration_ms: Optional[int]=None, lane: str='', mode: str=''` | no |
| 889 | `finalize_action_ledger_record` | `record: dict, *, final_answer: str, planner_decision: str='', tool: str='', tool_args: Optional[dict]=None, tool_result: str='', grounded: Optional[bool]=None, intent: str='', active_subject: str='', continuation_used: Optional[bool]=None, reply_contract: str='', reply_outcome: Optional[dict]=None, routing_decision: Optional[dict]=None, reflection_payload: Optional[dict]=None` | no |
| 926 | `ok` | `msg` | no |
| 927 | `warn` | `msg` | no |
| 928 | `bad` | `msg` | no |
| 931 | `load_policy` | `` | no |
| 935 | `_load_policy_raw` | `` | no |
| 939 | `_save_policy_raw` | `data: dict` | no |
| 943 | `_record_policy_change` | `action: str, target: str, result: str, details: str=''` | no |
| 947 | `policy_models` | `` | no |
| 951 | `policy_memory` | `` | no |
| 955 | `policy_tools_enabled` | `` | no |
| 959 | `_memory_adapter_service` | `` | no |
| 966 | `_tool_execution_service` | `` | no |
| 975 | `build_tool_context` | `*, is_admin: bool=False, extra: Optional[dict]=None` | no |
| 979 | `_tool_error_message` | `tool_name: str, reason: str` | no |
| 983 | `execute_registered_tool` | `tool_name: str, args: dict, *, is_admin: bool=False, extra: Optional[dict]=None` | no |
| 991 | `_research_handlers` | `` | no |
| 1001 | `execute_research_action` | `action: str, value: str` | no |
| 1009 | `_patch_handlers` | `` | no |
| 1021 | `execute_patch_action` | `action: str, value: str='', *, force: bool=False, is_admin: bool=True` | no |
| 1030 | `policy_web` | `` | no |
| 1034 | `policy_patch` | `` | no |
| 1038 | `web_enabled` | `` | no |
| 1042 | `_host_allowed` | `host: str, allow_domains: list[str]` | no |
| 1046 | `web_fetch` | `url: str, save_dir: Path` | no |
| 1057 | `_web_allowlist_message` | `context: str=''` | no |
| 1061 | `_weather_source_host` | `` | no |
| 1065 | `_weather_unavailable_message` | `` | no |
| 1069 | `weather_response_style` | `` | no |
| 1073 | `_format_weather_output` | `label: str, summary: str` | no |
| 1080 | `_runtime_device_backend_provider` | `` | no |
| 1084 | `_coerce_bounded_float` | `value, *, minimum: float, maximum: float` | no |
| 1096 | `_coerce_optional_metric` | `value` | no |
| 1108 | `_normalize_source_timestamp` | `value` | no |
| 1121 | `_format_runtime_coords` | `lat: float, lon: float` | no |
| 1125 | `_device_location_status_payload` | `snapshot: Optional[dict], *, max_age_sec: float=DEVICE_LOCATION_MAX_AGE_SEC` | no |
| 1133 | `runtime_device_location_payload` | `*, max_age_sec: float=DEVICE_LOCATION_MAX_AGE_SEC` | no |
| 1142 | `set_runtime_device_location` | `payload: dict` | no |
| 1151 | `clear_runtime_device_location` | `` | no |
| 1162 | `_resolve_windows_device_coords` | `timeout_sec: float=8.0` | no |
| 1169 | `resolve_current_device_coords` | `*, max_age_sec: float=DEVICE_LOCATION_MAX_AGE_SEC` | no |
| 1193 | `_coords_for_location_hint` | `location: str` | no |
| 1197 | `_coords_from_saved_location` | `` | no |
| 1204 | `get_saved_location_text` | `` | no |
| 1211 | `_make_conversation_state` | `kind: str, **data` | no |
| 1218 | `_conversation_active_subject` | `state: Optional[dict]` | no |
| 1230 | `_normalize_turn_text` | `text: str` | no |
| 1236 | `_provider_name_from_tool` | `tool_name: str` | no |
| 1243 | `_load_generated_queue_payload` | `limit: int=12` | no |
| 1251 | `set_location_coords` | `value: str` | no |
| 1255 | `get_weather_for_location` | `lat: float, lon: float` | no |
| 1259 | `_need_confirmed_location_message` | `` | no |
| 1263 | `tool_weather` | `location: str` | no |
| 1277 | `allowed_root` | `` | no |
| 1282 | `chat_model` | `` | no |
| 1287 | `routing_model` | `` | yes |
| 1294 | `whisper_size` | `` | no |
| 1306 | `atomic_write_json` | `path: Path, data: dict` | no |
| 1313 | `touch` | `path: Path` | no |
| 1318 | `write_core_identity` | `statefile: Path` | no |
| 1329 | `read_core_state` | `statefile: Path` | no |
| 1338 | `set_core_state` | `statefile: Path, key: str, value` | no |
| 1347 | `start_heartbeat` | `heartbeat_file: Path, interval_sec: float=1.0` | no |
| 1350 | `_loop` | `` | no |
| 1367 | `__init__` | `self, python_exe: str, oneshot_script: Path, timeout_sec: float=25.0` | no |
| 1378 | `mem_enabled` | `` | no |
| 1382 | `mem_top_k` | `` | no |
| 1386 | `mem_scope` | `` | no |
| 1390 | `mem_context_top_k` | `` | no |
| 1394 | `mem_min_score` | `` | no |
| 1398 | `mem_exclude_sources` | `` | no |
| 1402 | `mem_store_min_chars` | `` | no |
| 1406 | `mem_store_exclude_patterns` | `` | no |
| 1410 | `mem_store_include_patterns` | `` | no |
| 1414 | `_default_local_user_id` | `` | no |
| 1418 | `_memory_write_user` | `` | no |
| 1431 | `_memory_should_keep_text` | `text: str` | no |
| 1435 | `_memory_kind_store_allowed` | `kind: str` | no |
| 1439 | `_mem_recall_exclude_kinds` | `` | no |
| 1443 | `mem_should_store` | `text: str` | no |
| 1447 | `_memory_runtime_user` | `` | no |
| 1456 | `_format_memory_recall_hits` | `hits` | no |
| 1460 | `mem_stats_payload` | `emit_event: bool=True` | no |
| 1471 | `memory_health_payload` | `update_snapshot: bool=True` | no |
| 1487 | `mem_add` | `kind: str, source: str, text: str` | no |
| 1507 | `mem_recall` | `query: str` | no |
| 1526 | `_prefix_from_earlier_memory` | `reply_text: str` | no |
| 1535 | `_normalize_recent_learning_item` | `kind: str, text: str` | no |
| 1572 | `mem_stats` | `` | no |
| 1605 | `mem_remember_fact` | `text: str` | no |
| 1618 | `load_identity_profile` | `` | no |
| 1628 | `save_identity_profile` | `data: dict` | no |
| 1639 | `_looks_invalid_person_token` | `value: str` | no |
| 1660 | `_sanitize_learned_facts` | `data: dict` | no |
| 1675 | `load_learned_facts` | `` | no |
| 1688 | `save_learned_facts` | `data: dict` | no |
| 1699 | `get_learned_fact` | `key: str, default: str=''` | no |
| 1705 | `build_learning_context_details` | `query: str` | no |
| 1757 | `build_learning_context` | `query: str` | no |
| 1761 | `_render_chat_context` | `turns: list[tuple[str, str]], max_chars: int=1800, current_text: str=''` | no |
| 1783 | `_render_session_state_context` | `*, conversation_state: dict \| None=None, pending_action: dict \| None=None, max_chars: int=1600` | no |
| 1821 | `build_fallback_context_details` | `query: str, turns: list[tuple[str, str]] \| None=None, *, conversation_state: dict \| None=None, pending_action: dict \| None=None, include_state_context: bool=True, include_chat_context: bool=True` | no |
| 1869 | `_extract_urls` | `text: str` | no |
| 1873 | `_strip_invocation_prefix` | `text: str` | no |
| 1877 | `_normalize_domain_input` | `value: str` | no |
| 1881 | `list_allowed_domains` | `` | no |
| 1885 | `policy_allow_domain` | `value: str` | no |
| 1889 | `policy_remove_domain` | `value: str` | no |
| 1893 | `policy_audit` | `limit: int=20` | no |
| 1919 | `web_mode_status` | `` | no |
| 1937 | `set_web_mode` | `mode: str` | no |
| 1944 | `set_memory_scope` | `scope: str` | no |
| 1948 | `get_server_side_settings` | `` | no |
| 1952 | `set_server_side_settings` | `*, mode: str='', frontdoor: str='', frontdoor_base_url: str \| None=None, docker_enabled: bool \| None=None` | no |
| 1968 | `set_mission_settings` | `*, enabled: bool \| None=None, mode: str='', objective: str='', release_stale_ready_is_pressure: bool \| None=None, subconscious_triage_is_pressure: bool \| None=None, generated_queue_backlog_is_pressure: bool \| None=None` | no |
| 1988 | `get_search_provider` | `` | no |
| 1992 | `get_search_provider_priority` | `` | no |
| 1996 | `set_search_provider` | `provider: str` | no |
| 2000 | `set_search_provider_priority` | `priority: str \| list[str]` | no |
| 2004 | `get_search_endpoint` | `` | no |
| 2008 | `set_search_endpoint` | `endpoint: str` | no |
| 2012 | `auto_repair_search_endpoint` | `endpoint: str` | no |
| 2016 | `_resolve_research_provider` | `candidates: list[str], *, default_tool: str='web_research'` | no |
| 2044 | `probe_search_endpoint` | `endpoint: str='', *, timeout: float=2.5, persist_repair: bool=False, candidate_limit: int \| None=None` | no |
| 2063 | `toggle_search_provider` | `` | no |
| 2072 | `is_within_allowed` | `p: Path` | no |
| 2080 | `safe_path` | `user_path: str` | no |
| 2093 | `tcp_listening` | `host='127.0.0.1', port=11434, timeout=1.0` | no |
| 2101 | `_live_ollama_calls_allowed` | `` | no |
| 2111 | `ollama_api_up` | `timeout=2.0` | no |
| 2115 | `ollama_server_up` | `timeout=2.0` | no |
| 2119 | `ollama_health_payload` | `timeout=2.0` | no |
| 2139 | `start_ollama_serve_detached` | `` | no |
| 2154 | `kill_ollama` | `` | no |
| 2158 | `ensure_ollama_boot` | `` | no |
| 2178 | `warm_ollama_chat_model` | `reason: str='startup'` | no |
| 2208 | `warm_ollama_routing_model` | `reason: str='startup'` | yes |
| 2238 | `maybe_run_fulfillment_flow` | `text: str, session, turns, *, pending_action=None, semantic_observation: Optional[dict]=None` | yes |
| 2263 | `ensure_ollama` | `` | no |
| 2280 | `_tokenize` | `q: str` | no |
| 2288 | `kb_active_pack` | `` | no |
| 2298 | `kb_set_active` | `name: Optional[str]` | no |
| 2309 | `kb_list_packs` | `` | no |
| 2323 | `kb_add_zip` | `zip_path: str, pack_name: str` | no |
| 2349 | `_active_knowledge_root` | `` | no |
| 2359 | `kb_search` | `query: str, max_files: int=KB_MAX_FILES, max_chars: int=KB_MAX_CHARS` | no |
| 2371 | `_read_text_safely` | `path: Path` | no |
| 2389 | `_extract_key_lines` | `text: str, max_lines: int=2` | no |
| 2403 | `_topic_tokens` | `text: str` | no |
| 2420 | `_extract_matching_lines` | `text: str, tokens: list[str], max_lines: int=3` | no |
| 2454 | `_is_local_knowledge_topic_query` | `text: str` | no |
| 2459 | `_is_peims_broad_query` | `text: str` | no |
| 2469 | `_log_patch` | `msg: str` | no |
| 2476 | `_read_patch_revision` | `` | no |
| 2486 | `_write_patch_revision` | `revision: int, source: str` | no |
| 2496 | `_snapshot_meta_path` | `snapshot_zip: Path` | no |
| 2500 | `_write_snapshot_meta` | `snapshot_zip: Path, base_revision: int` | no |
| 2509 | `_detached_domain_reply` | `domain_name: str, suggested_query: str` | no |
| 2517 | `_read_snapshot_meta` | `snapshot_zip: Path` | no |
| 2527 | `_snapshot_current` | `` | no |
| 2544 | `_overlay_zip` | `zip_path: Path` | no |
| 2559 | `_py_compile_check` | `` | no |
| 2572 | `_last_nonempty_line` | `text: str` | no |
| 2580 | `_read_patch_manifest` | `zip_path: Path` | no |
| 2604 | `_behavioral_check_command` | `base_dir: Optional[Path]=None` | no |
| 2609 | `_behavioral_check` | `*, base_dir: Optional[Path]=None, timeout_sec: Optional[int]=None` | no |
| 2619 | `_read_patch_log_tail_line` | `` | no |
| 2628 | `patch_preview_summaries` | `limit: int=40` | no |
| 2636 | `patch_status_payload` | `` | no |
| 2648 | `_patch_control_state` | `*, include_readiness: bool=True` | no |
| 2670 | `_patch_reject_message` | `reason: str, *, strict_manifest: bool, current_revision: int, incoming_revision: Optional[int], required_base_revision: Optional[int]` | no |
| 2691 | `patch_apply` | `zip_path: str, force: bool=False` | no |
| 2715 | `patch_rollback` | `snapshot_zip: Optional[str]=None` | no |
| 2727 | `patch_preview` | `zip_path: str, write_report: bool=False` | no |
| 2743 | `_approvals_file` | `` | no |
| 2749 | `_read_approvals` | `` | no |
| 2769 | `_record_approval` | `preview_path: str, decision: str, user: Optional[str]=None, note: str=''` | no |
| 2785 | `list_previews` | `` | no |
| 2802 | `show_preview` | `path_or_name: str` | no |
| 2815 | `approve_preview` | `path_or_name: str, note: str=''` | no |
| 2826 | `reject_preview` | `path_or_name: str, note: str=''` | no |
| 2837 | `interactive_preview_review` | `preview_path: str` | no |
| 2846 | `_interactive_patch_review_enabled` | `` | no |
| 2851 | `_strip_mem_leak` | `reply: str, mem_block: str` | yes |
| 2871 | `format_tool_citation` | `tool: str, tool_output: str` | yes |
| 2887 | `_ensure_reply` | `reply: Optional[str]` | yes |
| 2898 | `_clamp_language_mix` | `value: Any` | no |
| 2905 | `_estimate_spanish_ratio` | `text: str` | yes |
| 2921 | `_auto_adjust_language_mix` | `current_mix: int, user_text: str` | no |
| 2928 | `_language_mix_instruction` | `spanish_pct: int` | no |
| 2949 | `ollama_chat` | `text: str, retrieved_context: str='', language_mix_spanish_pct: int=0, reply_form: str=''` | no |
| 2971 | `_teach_store_example` | `original: str, correction: str, user: Optional[str]=None` | yes |
| 2987 | `_teach_list_examples` | `` | no |
| 3035 | `speak_chunked` | `tts, text: str, max_len: int=220` | no |
| 3042 | `run_tool_py` | `script: str, args=None` | no |
| 3051 | `tool_os_capability` | `request: str='', capability: str='', args: Optional[dict]=None` | no |
| 3093 | `tool_phase2_audit` | `` | no |
| 3106 | `_load_json_file` | `path: Path, default: Any` | no |
| 3116 | `_preview_name_to_zip_path` | `preview_name: str` | no |
| 3130 | `_latest_approved_update_zip` | `patch_payload: Optional[dict]=None` | no |
| 3148 | `build_pulse_payload` | `` | no |
| 3175 | `_latest_memory_health_branch` | `` | no |
| 3192 | `_release_readiness_branch` | `branch_id: str=''` | no |
| 3217 | `tool_memory_bootstrap_judgment` | `` | no |
| 3234 | `tool_memory_bootstrap_confirm` | `assistant_name: str='', developer_name: str='', developer_nickname: str='', confirmed_by: str='operator'` | no |
| 3283 | `tool_memory_identity_bootstrap` | `` | no |
| 3299 | `tool_memory_hygiene` | `dry_run: bool=True` | no |
| 3326 | `tool_subconscious_review_judgment` | `branch_id: str=''` | no |
| 3342 | `tool_source_root_judgment` | `branch_id: str=''` | no |
| 3355 | `tool_release_promotion_judgment` | `branch_id: str=''` | no |
| 3369 | `tool_release_validation_run` | `branch_id: str=''` | no |
| 3391 | `tool_release_record_validation_outcome` | `branch_id: str=''` | no |
| 3405 | `tool_installer_validation_run` | `branch_id: str=''` | no |
| 3418 | `_self_report_control_status_payload` | `` | no |
| 3436 | `_self_report_work_trees_payload` | `limit: int=32` | no |
| 3453 | `_self_report_work_tree_truth` | `work_trees_payload: dict` | no |
| 3466 | `_self_report_local_status_payload` | `work_trees_payload: dict` | no |
| 3506 | `_core_health_runtime_health` | `` | no |
| 3526 | `_core_health_kidney_summary` | `` | no |
| 3536 | `_apply_latest_regression_validation` | `pulse_payload: dict` | no |
| 3555 | `build_core_health_brief_payload` | `` | no |
| 3586 | `tool_release_rebuild_verify` | `label: str='work-tree-rebuild'` | no |
| 3630 | `_read_update_now_pending` | `` | no |
| 3634 | `update_now_pending_payload` | `` | no |
| 3664 | `execute_planned_action` | `tool: str, args=None` | no |
| 3672 | `make_pending_weather_action` | `` | no |
| 3682 | `_weather_current_location_available` | `` | no |
| 3717 | `web_search` | `query: str, save_dir: Path=WEB_CACHE_DIR, max_results: int=5` | no |
| 3764 | `run_loop` | `tts` | no |
| 3771 | `main` | `` | no |

## `nova_guard.py`

Lines: 855 | Functions/methods: 49 | Classes: 1

Classes: `GuardAttempt` (L64)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 83 | `_append_identity` | `targets: list[tuple[int, float]], identity: Optional[tuple[int, float]]` | no |
| 91 | `ts` | `` | no |
| 95 | `log` | `msg: str` | no |
| 103 | `atomic_write_json` | `path: Path, data: dict` | no |
| 110 | `read_json` | `path: Path` | no |
| 119 | `remove_file` | `path: Path` | no |
| 127 | `_normalize_identity_path` | `value: str` | no |
| 134 | `_guard_command_identity` | `` | no |
| 141 | `_cmdline_matches_identity` | `cmdline: list[str], command: dict` | no |
| 152 | `_process_identity` | `pid: int` | no |
| 159 | `_current_guard_identity_payload` | `` | no |
| 172 | `_lock_belongs_to_live_guard` | `data: Optional[dict]` | no |
| 189 | `_write_guard_lock` | `path: Path, payload: dict` | no |
| 194 | `acquire_lock_or_exit` | `` | no |
| 219 | `heartbeat_age_seconds` | `` | no |
| 228 | `is_heartbeat_fresh` | `` | no |
| 233 | `read_core_state` | `` | no |
| 246 | `pid_matches_create_time` | `pid: int, create_time: float` | no |
| 254 | `_process_create_time` | `pid: int` | no |
| 261 | `_sync_attempt_create_time` | `attempt: GuardAttempt` | no |
| 267 | `_attempt_is_alive` | `attempt: GuardAttempt` | no |
| 276 | `_clear_core_runtime_artifacts` | `` | no |
| 281 | `_boot_history` | `` | no |
| 286 | `_derive_boot_timeout_seconds` | `` | no |
| 305 | `_boot_observation_entry` | `attempt: GuardAttempt, *, success: bool, reason: str` | no |
| 351 | `_record_boot_observation` | `attempt: GuardAttempt, *, success: bool, reason: str` | no |
| 371 | `_state_matches_identity` | `state: Optional[dict], pid: Optional[int], create_time: Optional[float]` | no |
| 379 | `_owned_process_identities` | `attempt: GuardAttempt` | no |
| 414 | `_identity_in_process_tree` | `root_identity: tuple[int, float], target_identity: tuple[int, float]` | no |
| 434 | `_adopt_runtime_identity_from_state` | `attempt: GuardAttempt, state: Optional[dict]` | no |
| 463 | `_live_identities` | `identities: list[tuple[int, float]]` | no |
| 467 | `_terminate_identities` | `identities: list[tuple[int, float]]` | no |
| 495 | `_reset_attempt_runtime_fields` | `attempt: GuardAttempt` | no |
| 511 | `spawn_core` | `reason: str` | no |
| 528 | `start_new_attempt` | `attempt: GuardAttempt, reason: str` | no |
| 561 | `_runtime_state_matches_attempt` | `attempt: GuardAttempt, state: Optional[dict]` | no |
| 572 | `_observe_boot_progress` | `attempt: GuardAttempt` | no |
| 589 | `_boot_succeeded` | `attempt: GuardAttempt` | no |
| 593 | `_boot_failed` | `attempt: GuardAttempt` | no |
| 617 | `_runtime_failed` | `attempt: GuardAttempt` | no |
| 646 | `_mark_attempt_failed` | `attempt: GuardAttempt, reason: str` | no |
| 652 | `_resolve_attempt` | `attempt: GuardAttempt` | no |
| 678 | `_schedule_restart_wait` | `attempt: GuardAttempt` | no |
| 697 | `build_initial_attempt` | `` | no |
| 721 | `supervisor_tick` | `attempt: GuardAttempt` | no |
| 759 | `should_stop` | `` | no |
| 763 | `_is_maintenance_already_running` | `` | yes |
| 789 | `_maintenance_tick` | `` | no |
| 826 | `main` | `` | no |

## `nova_http.py`

Lines: 1878 | Functions/methods: 210 | Classes: 2

Classes: `_StatusRuntimeProcessesModule` (L191), `NovaHttpHandler` (L1823)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 126 | `_resolve_venv_python` | `` | no |
| 178 | `_invalidate_control_status_cache` | `` | no |
| 183 | `_load_autonomy_maintenance_state` | `` | no |
| 195 | `logical_service_processes` | `script_path: str \| Path` | no |
| 210 | `select_logical_process` | `processes: list[dict[str, Any]], *, pid: int \| None=None, create_time: float \| None=None` | no |
| 222 | `_status_runtime_processes_module` | `` | no |
| 226 | `_autonomy_maintenance_summary` | `` | no |
| 250 | `_record_control_action_event` | `action: str, result: str, detail: str='', payload: dict \| None=None` | no |
| 261 | `_safe_tail_lines` | `path: Path, n: int=80` | no |
| 265 | `_read_asset_text` | `path: Path` | no |
| 269 | `_asset_version_token` | `path: Path` | no |
| 273 | `_render_control_html` | `` | no |
| 277 | `_render_control_login_html` | `` | no |
| 281 | `_render_leah_html` | `` | no |
| 285 | `_render_runtime_console_html` | `` | no |
| 289 | `http_route_contract` | `` | no |
| 293 | `_control_telemetry_service` | `` | no |
| 297 | `_action_ledger_summary` | `limit: int=60` | no |
| 305 | `_provider_telemetry_payload` | `*, ledger_summary: dict, tool_summary: dict` | no |
| 316 | `_tool_events_summary` | `limit: int=80` | no |
| 320 | `_os_capability_ledger_summary` | `limit: int=80` | no |
| 324 | `_memory_events_summary` | `limit: int=80` | no |
| 328 | `_build_self_check` | `status: dict, policy: dict, metrics: dict` | no |
| 332 | `_export_capabilities_snapshot` | `` | no |
| 336 | `_control_self_check_payload` | `` | no |
| 340 | `_load_persisted_sessions` | `` | no |
| 350 | `_persist_sessions` | `` | no |
| 361 | `_append_session_turn` | `session_id: str, role: str, text: str` | no |
| 373 | `_get_session_turns` | `session_id: str` | no |
| 378 | `_get_last_session_turn` | `session_id: str` | no |
| 383 | `_session_summaries` | `limit: int=60` | no |
| 393 | `_test_sessions_root` | `` | no |
| 397 | `_generated_test_session_definitions_dir` | `` | no |
| 401 | `_test_session_definitions_dir` | `` | no |
| 405 | `_all_test_session_definition_roots` | `` | no |
| 409 | `_available_test_session_definitions` | `limit: int=80` | no |
| 416 | `_resolve_test_session_definition` | `session_name: str` | no |
| 423 | `_subconscious_runs_root` | `` | no |
| 427 | `_operator_macros_path` | `` | no |
| 431 | `_load_operator_macros` | `limit: int=24` | no |
| 435 | `_resolve_operator_macro` | `macro_id: str` | no |
| 439 | `_load_backend_commands` | `limit: int=40` | no |
| 446 | `_resolve_backend_command` | `command_id: str` | no |
| 450 | `_parse_backend_dynamic_args` | `raw: Any` | no |
| 454 | `_run_backend_command` | `command_id: str, payload: dict` | no |
| 465 | `_backend_command_list_action` | `payload: dict` | no |
| 469 | `_backend_command_run_action` | `payload: dict` | no |
| 477 | `_render_operator_macro_prompt` | `macro: Mapping[str, Any], values: Mapping[str, Any] \| None=None, note: str=''` | no |
| 481 | `_operator_prompt_action` | `payload: dict` | no |
| 485 | `_operator_outbox_respond_action` | `payload: dict` | no |
| 501 | `_operator_outbox_status_action` | `payload: dict` | no |
| 516 | `_latest_subconscious_report` | `` | no |
| 520 | `_subconscious_status_summary` | `` | no |
| 528 | `_subconscious_live_summary` | `limit: int=6` | no |
| 541 | `_report_status_label` | `diff_count: int, flagged_probe_count: int` | no |
| 545 | `_test_session_report_summaries` | `limit: int=24` | no |
| 549 | `_run_test_session_definition` | `session_file: str` | no |
| 562 | `_test_session_run_action` | `payload: dict` | no |
| 569 | `_real_world_task_create_action` | `payload: dict` | no |
| 577 | `_delete_session` | `session_id: str` | no |
| 581 | `_parse_request_path` | `raw_path: str` | no |
| 586 | `_request_control_key` | `handler: BaseHTTPRequestHandler, qs: dict` | no |
| 593 | `_is_local_client` | `handler: BaseHTTPRequestHandler` | no |
| 598 | `_normalize_user_id` | `value: str` | no |
| 606 | `_request_user_id` | `handler: BaseHTTPRequestHandler, qs: dict, payload: dict \| None=None` | no |
| 615 | `_assert_session_owner` | `session_id: str, user_id: str, *, allow_bind: bool=True` | no |
| 627 | `_dev_mode_enabled` | `` | no |
| 632 | `_chat_users_path` | `` | no |
| 636 | `_chat_auth_source` | `` | no |
| 640 | `_hash_chat_password` | `password: str, *, iterations: int=CHAT_PASSWORD_HASH_ITERATIONS` | no |
| 644 | `_save_managed_chat_users` | `users: dict` | no |
| 653 | `_chat_users` | `` | no |
| 661 | `_chat_password_matches` | `expected, pwd: str` | no |
| 665 | `_record_http_response` | `code: int` | no |
| 673 | `_parse_cookie_map` | `handler: BaseHTTPRequestHandler` | no |
| 686 | `_control_auth` | `handler: BaseHTTPRequestHandler, qs: dict` | no |
| 696 | `_chat_auth_payload` | `` | no |
| 704 | `_chat_user_upsert` | `username: str, password: str` | no |
| 714 | `_chat_user_delete` | `username: str` | no |
| 723 | `_session_delete_action` | `payload: dict` | no |
| 731 | `_chat_user_list_action` | `payload: dict` | no |
| 735 | `_chat_user_upsert_action` | `payload: dict` | no |
| 743 | `_chat_user_delete_action` | `payload: dict` | no |
| 751 | `_chat_login_enabled` | `` | no |
| 755 | `_prune_chat_sessions` | `` | no |
| 759 | `_new_chat_session` | `user_id: str` | no |
| 770 | `_clear_chat_session` | `handler: BaseHTTPRequestHandler` | no |
| 778 | `_chat_login_auth` | `handler: BaseHTTPRequestHandler` | no |
| 789 | `_chat_login_action` | `payload: dict` | no |
| 800 | `_chat_logout_action` | `handler: BaseHTTPRequestHandler` | no |
| 807 | `_patch_preview_list_action` | `payload: dict` | no |
| 815 | `_pulse_status_action` | `payload: dict` | no |
| 823 | `_patch_queue_run_next_action` | `payload: dict` | no |
| 838 | `_active_work_tree_run_next_action` | `payload: dict` | no |
| 853 | `_codegen_run_action` | `payload: dict` | no |
| 858 | `_leah_build_run_next_action` | `payload: dict` | no |
| 867 | `_temporal_events_list_action` | `payload: dict` | yes |
| 877 | `_temporal_event_save_action` | `payload: dict` | yes |
| 890 | `_temporal_event_delete_action` | `payload: dict` | yes |
| 903 | `_update_now_dry_run_action` | `payload: dict` | no |
| 911 | `_update_now_confirm_action` | `payload: dict` | no |
| 920 | `_update_now_cancel_action` | `payload: dict` | no |
| 927 | `_refresh_status_action` | `payload: dict` | no |
| 931 | `_device_location_update_action` | `payload: dict` | no |
| 939 | `_device_location_clear_action` | `payload: dict` | no |
| 946 | `_self_check_action` | `payload: dict` | no |
| 950 | `_tail_log_action` | `payload: dict` | no |
| 959 | `_metrics_action` | `payload: dict` | no |
| 967 | `_export_ledger_summary_action` | `payload: dict` | no |
| 977 | `_export_diagnostics_bundle_action` | `payload: dict` | no |
| 985 | `_control_login_enabled` | `` | no |
| 989 | `_prune_control_sessions` | `` | no |
| 993 | `_control_login_auth` | `handler: BaseHTTPRequestHandler` | no |
| 1004 | `_control_page_gate` | `handler: BaseHTTPRequestHandler` | no |
| 1014 | `_new_control_session` | `` | no |
| 1023 | `_clear_control_session` | `handler: BaseHTTPRequestHandler` | no |
| 1031 | `_control_login_action` | `payload: dict` | no |
| 1041 | `_control_logout_action` | `handler: BaseHTTPRequestHandler` | no |
| 1048 | `_guard_status_payload` | `include_fallback_scan: bool=True` | no |
| 1055 | `_start_guard` | `` | no |
| 1069 | `_core_status_payload` | `` | no |
| 1081 | `_http_status_payload` | `` | no |
| 1085 | `_runtime_summary_payload` | `guard: dict \| None=None, core: dict \| None=None, webui: dict \| None=None` | no |
| 1093 | `_start_nova_core` | `` | no |
| 1101 | `_stop_guard` | `` | no |
| 1110 | `_detached_creation_flags` | `` | no |
| 1114 | `_schedule_detached_start` | `command: list[str], *, delay_seconds: float=1.5, cwd: Path \| None=None, remove_before_start: list[Path] \| None=None` | no |
| 1133 | `_core_identity_from_runtime` | `` | no |
| 1140 | `_stop_core_owned_process` | `` | no |
| 1149 | `_restart_guard` | `` | no |
| 1164 | `_restart_core` | `` | no |
| 1174 | `_shutdown_http_server_later` | `delay_seconds: float=0.25` | no |
| 1183 | `_restart_webui` | `` | no |
| 1195 | `_start_autonomy_maintenance_worker` | `` | no |
| 1208 | `_stop_autonomy_maintenance_worker` | `` | no |
| 1217 | `_runtime_artifact_show_action` | `payload: dict` | no |
| 1224 | `_guard_control_action` | `payload: dict` | no |
| 1228 | `_core_runtime_action` | `payload: dict` | no |
| 1232 | `_autonomy_runtime_action` | `payload: dict` | no |
| 1236 | `_action_readiness_payload` | `guard: dict, core: dict, webui: dict` | no |
| 1240 | `_append_metrics_snapshot` | `status_payload: dict` | no |
| 1252 | `_metrics_payload` | `` | no |
| 1261 | `_tail_file` | `path: Path, max_lines: int=120` | no |
| 1270 | `_release_ledger_entries` | `limit: int=20` | no |
| 1274 | `_release_entry_matches_build` | `entry: dict, build_entry: dict` | no |
| 1278 | `_release_status_payload` | `limit: int=8` | no |
| 1287 | `_installer_status_payload` | `limit: int=8` | no |
| 1296 | `_coerce_epoch_seconds` | `value` | no |
| 1300 | `_runtime_event` | `action: str, ts_value, source: str, service: str, level: str, title: str, detail: str` | no |
| 1304 | `_runtime_timeline_action_title` | `action: str` | no |
| 1308 | `_runtime_timeline_action_service` | `action: str` | no |
| 1312 | `_runtime_timeline_from_control_audit` | `limit: int` | no |
| 1316 | `_parse_guard_log_line` | `line: str` | no |
| 1320 | `_runtime_timeline_from_guard_log` | `limit: int` | no |
| 1329 | `_runtime_timeline_from_boot_history` | `limit: int` | no |
| 1333 | `_runtime_timeline_payload` | `limit: int=24` | no |
| 1344 | `_file_age_seconds` | `path: Path` | no |
| 1353 | `_safe_json_file` | `path: Path` | no |
| 1362 | `_artifact_status` | `name: str, path: Path` | no |
| 1366 | `_artifact_summary` | `name: str, path: Path` | no |
| 1378 | `_runtime_artifact_definitions` | `` | no |
| 1387 | `_runtime_artifact_service` | `name: str` | no |
| 1391 | `_artifact_content` | `name: str, path: Path, *, max_lines: int=120, max_chars: int=12000` | no |
| 1404 | `_runtime_artifact_detail_payload` | `name: str, *, max_lines: int=120` | no |
| 1417 | `_runtime_artifacts_payload` | `` | no |
| 1426 | `_validation_artifact_truth_payload` | `` | no |
| 1433 | `_runtime_restart_analytics_payload` | `` | no |
| 1441 | `_patch_action_readiness_payload` | `patch_summary: dict \| None=None` | no |
| 1450 | `_latest_runtime_event_for_service` | `timeline_payload: dict \| None, service: str` | no |
| 1454 | `_failure_reason_for_service` | `service: str, payload: dict, timeline_payload: dict \| None=None` | no |
| 1458 | `_runtime_failure_reasons_payload` | `guard: dict, core: dict, webui: dict, timeline_payload: dict \| None=None` | no |
| 1462 | `_port_ownership_payload` | `` | no |
| 1466 | `_heartbeat_age_seconds` | `` | no |
| 1476 | `_storage_watch_summary` | `` | no |
| 1503 | `_artifact_age_seconds` | `path: Path` | no |
| 1512 | `_remove_runtime_artifact` | `path: Path` | no |
| 1520 | `_prune_orphaned_guard_artifacts` | `logical_processes: list[dict], pid: int \| None, pid_live: bool` | no |
| 1529 | `_prune_orphaned_core_artifacts` | `logical_processes: list[dict], pid: int \| None, pid_live: bool, heartbeat_age: int \| None` | no |
| 1544 | `_matches_script_process` | `cmdline: list[str], script_path: Path, cwd: str \| Path \| None=None` | no |
| 1548 | `_snapshot_script_process` | `process: psutil.Process, script_path: Path` | no |
| 1556 | `_logical_leaf_processes` | `matches: list[dict]` | no |
| 1560 | `_cached_logical_service_processes` | `script_path: Path, *, root_pid: int \| None=None, cache_key: str \| None=None, max_age_seconds: float=0.0` | no |
| 1576 | `_logical_service_processes` | `script_path: Path, root_pid: int \| None=None` | no |
| 1586 | `_select_logical_process` | `processes: list[dict], *, pid: int \| None=None, create_time: float \| None=None` | no |
| 1590 | `_runtime_process_note` | `` | no |
| 1600 | `_probe_searxng` | `endpoint: str, timeout: float=SEARXNG_STATUS_TIMEOUT_SEC` | no |
| 1610 | `_control_status_payload` | `` | no |
| 1622 | `_cached_control_status_payload` | `max_age_seconds: float=CONTROL_STATUS_CACHE_TTL_SECONDS` | no |
| 1632 | `_control_status_surfaces_payload` | `` | no |
| 1644 | `_cached_control_status_surfaces_payload` | `max_age_seconds: float=CONTROL_STATUS_SURFACES_CACHE_TTL_SECONDS` | no |
| 1656 | `_work_trees_payload` | `limit: int=32` | no |
| 1663 | `_work_tree_pressure_payload` | `` | no |
| 1667 | `_operator_outbox_summary` | `limit: int=20` | no |
| 1671 | `_control_policy_payload` | `` | no |
| 1684 | `_control_status_suppliers` | `` | no |
| 1688 | `_control_action` | `action: str, payload: dict` | no |
| 1716 | `_health_payload` | `` | no |
| 1730 | `_trim_turns` | `turns: List[Tuple[str, str]]` | no |
| 1734 | `_json_response` | `handler: BaseHTTPRequestHandler, code: int, payload: dict` | no |
| 1743 | `_text_response` | `handler: BaseHTTPRequestHandler, code: int, text: str` | no |
| 1752 | `_file_response` | `handler: BaseHTTPRequestHandler, code: int, path: Path, content_type: str` | no |
| 1762 | `_strip_ui_tip_leak` | `text: str` | no |
| 1776 | `_read_text_safely` | `path: Path` | no |
| 1780 | `_generate_chat_reply` | `turns: List[Tuple[str, str]], text: str, ledger_record: dict \| None=None, pending_action: dict \| None=None, prefer_web_for_data_queries: bool=False, language_mix_spanish_pct: int=0, session=None, ensure_active_work_tree_fn=None` | no |
| 1805 | `process_chat` | `session_id: str, user_text: str, user_id: str=''` | no |
| 1815 | `resume_last_pending_turn` | `session_id: str, user_id: str=''` | no |
| 1826 | `do_GET` | `self` | no |
| 1851 | `do_POST` | `self` | no |
| 1865 | `log_message` | `self, fmt: str, *args` | no |
| 1870 | `main` | `` | no |

## `nova_safety_envelope.py`

Lines: 683 | Functions/methods: 30 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 38 | `policy_safety_envelope` | `` | no |
| 57 | `_definition_files` | `root: Path` | no |
| 61 | `_load_definition` | `path: Path` | no |
| 69 | `_messages` | `payload: dict[str, Any]` | no |
| 76 | `_fingerprint` | `path: Path` | no |
| 80 | `_append_audit` | `entry: dict[str, Any]` | no |
| 86 | `_latest_audit_by_file` | `` | no |
| 107 | `render_status` | `` | no |
| 151 | `_tokenize` | `text: str` | no |
| 155 | `_counter_cosine` | `left: Counter[str], right: Counter[str]` | no |
| 167 | `_shannon_entropy` | `labels: list[str]` | no |
| 181 | `_intent_label` | `message: str` | no |
| 198 | `_shape_label` | `message: str` | no |
| 209 | `_command_density_label` | `message: str` | no |
| 219 | `_diversity_score` | `messages: list[str]` | no |
| 226 | `_pool_similarity` | `path: Path, payload: dict[str, Any]` | no |
| 243 | `_run_replay` | `path: Path` | no |
| 281 | `_run_full_regression` | `` | no |
| 300 | `_family_fallback_score` | `family_id: str` | no |
| 324 | `_family_promoted_count` | `family_id: str` | no |
| 335 | `_family_reviewed_count` | `family_id: str` | no |
| 353 | `_same_path` | `left: Path, right: Path` | no |
| 360 | `_is_managed_review_path` | `path: Path` | no |
| 373 | `_cfg_float` | `cfg: dict[str, Any], key: str, default: float` | no |
| 380 | `_cfg_int` | `cfg: dict[str, Any], key: str, default: int` | no |
| 387 | `evaluate_promotion_contract` | `definition_path: str \| Path, *, run_full_regression: bool=False` | no |
| 524 | `promote_or_quarantine` | `definition_path: str \| Path, *, run_full_regression: bool=False` | no |
| 592 | `reevaluate_pending_reviews` | `*, limit: int \| None=None, run_full_regression: bool=False` | no |
| 633 | `evaluate_generated_definitions` | `paths: list[str] \| list[Path], *, max_candidates: int \| None=None` | no |
| 666 | `select_patch_candidate_definition_paths` | `root: Path \| None=None` | no |

## `nova_stop.py`

Lines: 62 | Functions/methods: 4 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `warn` | `msg` | no |
| 14 | `ok` | `msg` | no |
| 19 | `read_core_identity` | `` | no |
| 23 | `main` | `` | no |

## `pipelines/__init__.py`

Lines: 25 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `pipelines/audit.py`

Lines: 39 | Functions/methods: 2 | Classes: 1

Classes: `PipelineAuditLogger` (L9)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 12 | `__init__` | `self, path: Path` | no |
| 15 | `append` | `self, *, pipeline_id: str, action: str, status: str, detail: str='', data: Optional[Mapping[str, Any]]=None` | no |

## `pipelines/base.py`

Lines: 501 | Functions/methods: 18 | Classes: 2

Classes: `PipelineManifest` (L49), `BaseDataPipeline` (L97)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_read_json_dict` | `path: Path` | no |
| 40 | `_tokens` | `text: str` | no |
| 72 | `summary` | `self` | no |
| 100 | `__init__` | `self, manifest: PipelineManifest` | no |
| 109 | `load_schema_manifest` | `self` | no |
| 114 | `load_query_templates` | `self` | no |
| 125 | `load_field_dictionary` | `self` | no |
| 132 | `load_population_definitions` | `self` | no |
| 139 | `load_vendor_dictionary` | `self` | no |
| 146 | `load_predefined_reports` | `self` | no |
| 153 | `predefined_reports_summary` | `self` | no |
| 166 | `vendor_dictionary_summary` | `self` | no |
| 177 | `search_vendor_dictionary` | `self, query: str, *, limit: int=12` | no |
| 224 | `_vendor_table_match` | `self, table_name: str` | no |
| 248 | `plan_report` | `self, request: str, *, limit: int=8` | no |
| 471 | `schema_probe` | `self` | no |
| 489 | `status` | `self` | no |
| 493 | `safe_query` | `self, operation: str, params: Optional[Mapping[str, Any]]=None, *, row_limit: Optional[int]=None, dry_run: bool=True` | no |

## `pipelines/loaders.py`

Lines: 71 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `_read_json` | `path: Path` | no |
| 19 | `_resolve_path` | `root: Path, relative_path: Optional[str]` | no |
| 26 | `load_pipeline_manifest` | `pipeline_dir: Path` | no |

## `pipelines/privileged_protocol.py`

Lines: 141 | Functions/methods: 13 | Classes: 1

Classes: `PipelineProtocolPaths` (L13)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 20 | `_sanitize_pipeline_id` | `pipeline_id: str` | no |
| 25 | `build_protocol_paths` | `runtime_root: Path, pipeline_id: str` | no |
| 36 | `ensure_protocol_dirs` | `paths: PipelineProtocolPaths` | no |
| 41 | `_write_json` | `path: Path, payload: Mapping[str, Any]` | no |
| 46 | `_read_json` | `path: Path` | no |
| 51 | `submit_request` | `paths: PipelineProtocolPaths, *, pipeline_id: str, operation: str, params: Optional[Mapping[str, Any]]=None, row_limit: Optional[int]=None, requested_by: str='', timeout_sec: int=60` | no |
| 80 | `claim_next_request` | `paths: PipelineProtocolPaths` | no |
| 92 | `load_request` | `path: Path` | no |
| 96 | `response_path` | `paths: PipelineProtocolPaths, request_id: str` | no |
| 100 | `write_response` | `paths: PipelineProtocolPaths, request_id: str, payload: Mapping[str, Any]` | no |
| 111 | `load_response` | `paths: PipelineProtocolPaths, request_id: str` | no |
| 118 | `wait_for_response` | `paths: PipelineProtocolPaths, request_id: str, *, timeout_sec: int=60, poll_interval_sec: float=0.5` | no |
| 134 | `archive_request` | `paths: PipelineProtocolPaths, working_path: Path, *, status: str` | no |

## `pipelines/privileged_worker.py`

Lines: 70 | Functions/methods: 1 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `process_next_privileged_request` | `pipeline_id: str, *, runtime_root: Path, data_sources_root: Optional[Path]=None, execute_fn=None` | no |

## `pipelines/query_guard.py`

Lines: 95 | Functions/methods: 4 | Classes: 2

Classes: `QueryGuardError` (L6), `PipelineQueryGuard` (L28)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `_has_value` | `value: Any` | no |
| 18 | `_normalize_params` | `params: Optional[Mapping[str, Any]]` | no |
| 31 | `__init__` | `self, *, max_rows_default: int=100, max_rows_hard_cap: int=20` | no |
| 35 | `validate` | `self, templates: Mapping[str, Mapping[str, Any]], operation: str, params: Optional[Mapping[str, Any]]=None, *, row_limit: Optional[int]=None` | no |

## `pipelines/registry.py`

Lines: 63 | Functions/methods: 5 | Classes: 1

Classes: `PipelineRegistry` (L13)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 16 | `__init__` | `self, data_sources_root: Path` | no |
| 20 | `discover` | `self, *, refresh: bool=False` | no |
| 38 | `list_summaries` | `self` | no |
| 41 | `get_manifest` | `self, pipeline_id: str` | no |
| 48 | `instantiate` | `self, pipeline_id: str` | no |

## `planner_decision.py`

Lines: 20 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `classify_route` | `turn: TurnUnderstanding` | no |
| 13 | `classify_route_with_context` | `turn: TurnUnderstanding, config: Optional[dict]=None` | no |
| 18 | `decide_turn` | `text: str, config: Optional[dict]=None` | no |

## `routing/__init__.py`

Lines: 8 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `routing/execution_plan.py`

Lines: 15 | Functions/methods: 1 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `choose_execution` | `route: RouteDecision` | no |

## `routing/turn_model.py`

Lines: 23 | Functions/methods: 0 | Classes: 2

Classes: `TurnUnderstanding` (L8), `RouteDecision` (L19)

No Python functions or methods.

## `run.py`

Lines: 67 | Functions/methods: 6 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 6 | `_fallback_chat` | `text: str` | no |
| 24 | `record_seconds` | `seconds=6` | no |
| 27 | `transcribe` | `model, audio_int16` | no |
| 30 | `ask_nova` | `text` | no |
| 33 | `speak` | `text` | no |
| 36 | `main` | `` | no |

## `run_regression.py`

Lines: 9 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `run_tools.py`

Lines: 94 | Functions/methods: 9 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_tool_console_service` | `` | no |
| 19 | `record_seconds` | `seconds=6` | no |
| 23 | `transcribe` | `model, audio_int16` | no |
| 27 | `ask_nova` | `text` | no |
| 31 | `speak` | `text` | no |
| 35 | `list_tools_text` | `` | no |
| 39 | `handle_tools` | `user_text: str` | no |
| 43 | `parse_args` | `argv=None` | no |
| 49 | `main` | `argv=None` | no |

## `scripts/capture_leah_promotion_baseline.py`

Lines: 101 | Functions/methods: 5 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 20 | `_load_policy` | `` | no |
| 27 | `_local_status_payload` | `` | no |
| 36 | `_work_tree_open_summary` | `` | no |
| 52 | `capture_baseline` | `*, output: Path \| None=None` | no |
| 80 | `main` | `` | no |

## `scripts/demo_edfi_core_lifecycle.py`

Lines: 402 | Functions/methods: 14 | Classes: 1

Classes: `_Scene` (L90)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 29 | `_bootstrap_child_process` | `argv: list[str]` | no |
| 46 | `_ensure_import_path` | `` | no |
| 51 | `_healthy_profile_payload` | `*, discovered_at: int` | no |
| 72 | `_status_payload_from_evidence` | `evidence: dict[str, Any]` | no |
| 91 | `__init__` | `self, *, pause_sec: float, emit_json: bool` | no |
| 97 | `beat` | `self, title: str, detail: str, payload: dict[str, Any] \| None=None` | no |
| 117 | `finish` | `self, *, ok: bool` | no |
| 126 | `_write_connection_config` | `runtime_root: Path, *, lea_id: str` | no |
| 145 | `_write_profile` | `runtime_root: Path, profile: dict[str, Any]` | no |
| 153 | `_signal_branches` | `` | no |
| 171 | `demo_domain_consumer_proceeds` | `connection_id: str='district-main'` | yes |
| 203 | `run_demo` | `*, pause_sec: float=0.0, emit_json: bool=False` | no |
| 375 | `_build_parser` | `` | no |
| 393 | `main` | `argv: list[str] \| None=None` | no |

## `scripts/diagnostics/inspect_core_fail.py`

Lines: 38 | Functions/methods: 1 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `main` | `` | no |

## `scripts/diagnostics/list_work_tree_tables.py`

Lines: 19 | Functions/methods: 1 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 5 | `main` | `` | no |

## `scripts/end_to_end_wiring_check.py`

Lines: 44 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `_build_parser` | `` | no |
| 23 | `main` | `argv: list[str] \| None=None` | no |

## `scripts/health_check.py`

Lines: 42 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_suite_command` | `` | no |
| 15 | `check_suite` | `` | no |
| 32 | `main` | `` | no |

## `scripts/nova_server_side.py`

Lines: 66 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 17 | `_build_parser` | `` | no |
| 33 | `_status_payload` | `timeout_sec: float` | no |
| 38 | `main` | `argv: list[str] \| None=None` | no |

## `scripts/operator_cli.py`

Lines: 229 | Functions/methods: 8 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 20 | `_headers` | `control_key: str` | no |
| 28 | `_parse_macro_values` | `items: list[str] \| None` | no |
| 42 | `_send_operator_prompt` | `base_url: str, control_key: str, session_id: str, user_id: str, message: str, *, macro_id: str='', macro_values: dict[str, str] \| None=None, source: str='cli'` | no |
| 73 | `_load_operator_macros` | `` | no |
| 106 | `_resolve_operator_macro` | `macro_id: str` | no |
| 116 | `_print_reply` | `payload: dict[str, Any]` | no |
| 123 | `_build_parser` | `` | no |
| 137 | `main` | `argv: list[str] \| None=None` | no |

## `scripts/pipeline_worker.py`

Lines: 50 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 16 | `build_parser` | `` | no |
| 26 | `main` | `` | no |

## `scripts/release_clean_check.py`

Lines: 65 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 14 | `_build_parser` | `` | no |
| 36 | `main` | `argv: list[str] \| None=None` | no |

## `scripts/repo_hygiene_check.py`

Lines: 186 | Functions/methods: 9 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 45 | `_run` | `cmd: list[str], *, cwd: Path \| None=None` | no |
| 50 | `tracked_files` | `repo_root: Path \| None=None` | no |
| 55 | `is_git_work_tree` | `repo_root: Path \| None=None` | no |
| 62 | `is_lfs_pointer` | `path: Path` | no |
| 71 | `is_lfs_tracked` | `rel_path: str, repo_root: Path \| None=None` | no |
| 100 | `_git_blob_head` | `spec: str, repo_root: Path \| None=None, *, max_bytes: int=512` | no |
| 120 | `is_tracked_lfs_pointer` | `rel_path: str, repo_root: Path \| None=None` | no |
| 130 | `run_hygiene` | `repo_root: Path \| None=None` | no |
| 181 | `main` | `` | no |

## `scripts/reverse_proxy_frontdoor.py`

Lines: 47 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 16 | `_build_parser` | `` | no |
| 25 | `main` | `argv: list[str] \| None=None` | no |

## `scripts/run_edfi_explore.py`

Lines: 112 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `_build_parser` | `` | no |
| 58 | `main` | `argv: list[str] \| None=None` | no |

## `scripts/run_edfi_profile.py`

Lines: 61 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `_build_parser` | `` | no |
| 36 | `main` | `argv: list[str] \| None=None` | no |

## `scripts/run_regression.py`

Lines: 418 | Functions/methods: 18 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 49 | `run_step` | `name: str, cmd: list[str]` | no |
| 60 | `parse_args` | `argv: list[str] \| None=None` | no |
| 88 | `resolve_requested_lanes` | `args: argparse.Namespace` | no |
| 95 | `print_available_lanes` | `` | no |
| 109 | `run_unittest_suite` | `test_names: list[str], *, verbosity: int=1` | no |
| 150 | `run_test_lane` | `lane: str, *, verbosity: int=1` | no |
| 181 | `_is_canonical_regression_lane_set` | `lanes: list[str]` | no |
| 185 | `_should_publish_regression_status` | `*, lanes: list[str], status: str, returncode: int` | no |
| 193 | `write_regression_status` | `*, status: str, lanes: list[str], returncode: int, detail: str='', extra: dict \| None=None` | no |
| 219 | `_validation_artifact_status_extra` | `payload: dict` | no |
| 235 | `_regression_profile_status_extra` | `payload: dict` | no |
| 261 | `_pid_alive` | `pid: int` | no |
| 279 | `_read_regression_lock` | `` | no |
| 287 | `_acquire_regression_lock` | `*, lanes: list[str]` | no |
| 310 | `_release_regression_lock` | `` | no |
| 325 | `audit_validation_artifacts_after_green_run` | `*, window_start_epoch: float, window_end_epoch: float` | no |
| 338 | `main` | `argv: list[str] \| None=None` | no |
| 356 | `_run_regression_main` | `selected_lanes: list[str], args: argparse.Namespace` | no |

## `scripts/run_sock.py`

Lines: 184 | Functions/methods: 5 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 33 | `_bar` | `label: str, value: str, width: int=16` | no |
| 37 | `_model_line` | `role: str, current: str, recommended: str, changed: bool, rationale: str` | no |
| 44 | `format_report` | `report: SockReport` | no |
| 124 | `_format_warm_validation` | `report: SockReport` | no |
| 150 | `main` | `` | no |

## `scripts/run_test_session.py`

Lines: 681 | Functions/methods: 33 | Classes: 1

Classes: `_SilentTTS` (L58)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 59 | `start` | `self` | no |
| 62 | `stop` | `self` | no |
| 65 | `say` | `self, _text: str` | no |
| 69 | `_mode_label` | `mode: str` | no |
| 77 | `_parse_compare_modes` | `value: Any` | no |
| 92 | `load_session` | `session_name: str` | no |
| 138 | `_read_jsonl` | `path: Path` | no |
| 155 | `_read_ledger_rows` | `action_dir: Path` | no |
| 169 | `_normalize_text` | `value: Any` | no |
| 173 | `_normalize_saved_artifact_text` | `text: str` | no |
| 180 | `_assistant_compare_text` | `value: Any` | no |
| 188 | `_canonical_fact_answer` | `value: Any` | no |
| 207 | `_canonical_route_summary` | `value: Any` | no |
| 217 | `_is_question_like` | `text: str` | no |
| 221 | `_assistant_equivalent` | `cli_turn: dict[str, Any], http_turn: dict[str, Any]` | no |
| 235 | `_preview_value` | `value: Any, *, limit: int=180` | no |
| 244 | `_probe_lines` | `turn: dict[str, Any]` | no |
| 256 | `_flagged_probe_lines` | `turns: list[dict[str, Any]]` | no |
| 266 | `_runtime_failure_kind` | `turn: dict[str, Any]` | no |
| 278 | `_runtime_failure_lines` | `mode: str, turns: list[dict[str, Any]]` | no |
| 297 | `_turn_record` | `index: int, user_text: str, assistant_text: str, ledger: dict[str, Any] \| None, reflection: dict[str, Any] \| None` | no |
| 316 | `_isolated_runner_state` | `mode_dir: Path` | no |
| 408 | `run_cli_session` | `messages: list[str], mode_dir: Path` | no |
| 434 | `run_http_session` | `messages: list[str], mode_dir: Path` | no |
| 459 | `run_run_tools_session` | `messages: list[str], mode_dir: Path` | no |
| 483 | `_run_mode_session` | `mode: str, messages: list[str], mode_dir: Path` | no |
| 494 | `_issue_values` | `left_mode: str, right_mode: str, left_value: Any, right_value: Any` | no |
| 503 | `compare_sessions` | `left_result: dict[str, Any], right_result: dict[str, Any]` | no |
| 560 | `_write_report` | `run_dir: Path, session_meta: dict[str, Any], left_result: dict[str, Any], right_result: dict[str, Any], comparison: dict[str, Any]` | no |
| 591 | `_print_drift_details` | `diffs: list[dict[str, Any]], *, left_mode: str, right_mode: str, left_label: str, right_label: str` | no |
| 603 | `_print_summary` | `session_meta: dict[str, Any], comparison: dict[str, Any], report_path: Path` | no |
| 649 | `_comparison_failed` | `comparison: dict[str, Any]` | no |
| 659 | `main` | `` | no |

## `scripts/run_time.py`

Lines: 48 | Functions/methods: 1 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `main` | `` | no |

## `scripts/smoke_e2e.py`

Lines: 66 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 18 | `run_cmd` | `cmd, cwd=ROOT, timeout=600` | no |
| 29 | `main` | `` | no |

## `scripts/smoke_test.py`

Lines: 97 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 23 | `run_health_check` | `tier: str='runtime'` | no |
| 44 | `import_checks` | `` | no |
| 79 | `main` | `` | no |

## `scripts/start_webui_detached.py`

Lines: 61 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `_creation_flags` | `` | no |
| 20 | `main` | `` | no |

## `scripts/validate_release_package.py`

Lines: 64 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 17 | `_build_parser` | `` | no |
| 33 | `main` | `argv: list[str] \| None=None` | no |

## `services/autonomy_execution_gate.py`

Lines: 262 | Functions/methods: 13 | Classes: 1

Classes: `AutonomyExecutionGateService` (L38)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 14 | `_as_dict` | `value: Any` | no |
| 18 | `_as_list` | `value: Any` | no |
| 22 | `_safe_text` | `value: Any, limit: int=160` | no |
| 27 | `_as_float` | `value: Any, default: float=0.0` | no |
| 34 | `_action_set` | `value: Any` | no |
| 42 | `_policy_mode` | `policy_snapshot: dict[str, Any]` | no |
| 49 | `_execute_enabled` | `policy_snapshot: dict[str, Any]` | no |
| 57 | `_execute_allowed_actions` | `policy_snapshot: dict[str, Any], mode: str` | no |
| 66 | `_execute_allowed_action_groups` | `policy_snapshot: dict[str, Any], mode: str` | no |
| 75 | `_action_groups` | `action_type: str, action: dict[str, Any]` | no |
| 85 | `_primary_action_group` | `action_type: str, action: dict[str, Any]` | no |
| 93 | `evaluate` | `self, decision_packet: dict[str, Any], policy_snapshot: dict[str, Any], *, last_execution_context: dict[str, Any] \| None=None` | no |
| 237 | `_result` | `allow_execute: bool, status: str, mode: str, checks: dict[str, str], refusal_reasons: list[str], explain_text: str` | no |

## `services/autonomy_orchestrator.py`

Lines: 1550 | Functions/methods: 47 | Classes: 1

Classes: `AutonomyOrchestratorService` (L132)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 59 | `_as_dict` | `value: Any` | no |
| 63 | `_as_list` | `value: Any` | no |
| 67 | `_as_int` | `value: Any, default: int=0` | no |
| 74 | `_as_float` | `value: Any, default: float=0.0` | no |
| 81 | `_as_bool_or_none` | `value: Any` | no |
| 94 | `_clamp_float` | `value: Any, default: float=0.0` | no |
| 103 | `_safe_text` | `value: Any, limit: int=220` | no |
| 107 | `_utc_now_text` | `` | no |
| 111 | `_compact_value` | `value: Any, *, depth: int=0` | no |
| 135 | `__init__` | `self, *, posture_threshold: int=85` | no |
| 146 | `_legacy_decision` | `decision_type: str` | no |
| 150 | `_spec_decision` | `decision: str` | no |
| 154 | `_legacy_action` | `action: dict[str, Any] \| None` | no |
| 180 | `_freshness_sec` | `payload: dict[str, Any]` | no |
| 186 | `_source_present` | `envelope: dict[str, Any], key: str` | no |
| 190 | `_posture_band` | `steward_posture: dict[str, Any]` | no |
| 203 | `_mission_hold_active` | `mission: dict[str, Any]` | no |
| 212 | `_mission_green_hold_active` | `mission: dict[str, Any]` | no |
| 216 | `_mission_hold_refusal_reasons` | `mission: dict[str, Any]` | no |
| 236 | `_mission_blocks_advisory_action` | `action_type: str, evidence: dict[str, Any], *, action_context: dict[str, Any] \| None=None` | no |
| 250 | `_pressure_band` | `queue_pressure: dict[str, Any]` | no |
| 261 | `_runtime_summary` | `runtime_guard_status: dict[str, Any]` | no |
| 274 | `_correlation_ids` | `input_envelope: dict[str, Any]` | no |
| 293 | `_remember_decision` | `self, decision: dict[str, Any]` | no |
| 301 | `get_last_decision` | `self` | no |
| 304 | `get_decision_history` | `self, limit: int=20, filters: dict[str, Any] \| None=None` | no |
| 319 | `set_mode` | `self, mode: str, policy_snapshot: dict[str, Any] \| None=None` | no |
| 335 | `get_health` | `self` | no |
| 348 | `_contract_evidence` | `self, input_envelope: dict[str, Any], *, created_at_utc: str` | no |
| 573 | `_top_triage_candidate` | `triage: dict[str, Any], *, lane: str \| None=None` | no |
| 585 | `_triage_focus_text` | `candidate: dict[str, Any]` | no |
| 598 | `_triage_pressure_for_action` | `action_type: str, evidence: dict[str, Any]` | no |
| 627 | `_contract_conflicts` | `evidence: dict[str, Any]` | no |
| 649 | `_contract_action` | `action_type: str, *, reason_code: str, target_id: str \| None=None, expected_effect: str \| None=None` | no |
| 673 | `_contract_active_work_tree_count` | `work_tree: dict[str, Any]` | no |
| 698 | `_contract_candidate_actions` | `self, evidence: dict[str, Any]` | no |
| 974 | `_score_contract_candidate` | `candidate: dict[str, Any], evidence: dict[str, Any]` | no |
| 1020 | `_policy_allowed_actions` | `policy: dict[str, Any]` | no |
| 1030 | `_consider_contract_candidates` | `self, candidates: list[dict[str, Any]], evidence: dict[str, Any]` | no |
| 1092 | `_contract_decide` | `self, *, evidence: dict[str, Any], candidates_considered: list[dict[str, Any]]` | no |
| 1277 | `_contract_ledger_row` | `self, *, decision: dict[str, Any], candidates_considered: list[dict[str, Any]]` | no |
| 1335 | `evaluate_next_action` | `self, input_envelope: dict[str, Any], *, record_ledger_fn: Callable[[dict[str, Any]], Any] \| None=None` | no |
| 1431 | `_runtime_ok` | `section: dict[str, Any]` | no |
| 1444 | `_guard_state` | `guard_health: dict[str, Any]` | no |
| 1470 | `_queue_summary` | `queue_pressure: dict[str, Any]` | no |
| 1486 | `_work_tree_summary` | `work_tree_state: dict[str, Any]` | no |
| 1522 | `_ownership_summary` | `ownership_hints: Any, queue_pressure: dict[str, Any]` | no |

## `services/autonomy_orchestrator_ledger.py`

Lines: 214 | Functions/methods: 14 | Classes: 1

Classes: `AutonomyOrchestratorLedgerService` (L30)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `_safe_text` | `value: Any, limit: int=220` | no |
| 12 | `_as_int` | `value: Any, default: int=0` | no |
| 19 | `_as_dict` | `value: Any` | no |
| 34 | `recent_rows` | `ledger_path: Path, *, limit: int=80` | no |
| 56 | `_row_decision` | `row: dict[str, Any]` | no |
| 64 | `_row_action` | `row: dict[str, Any]` | no |
| 76 | `_row_rejection_reasons` | `row: dict[str, Any]` | no |
| 87 | `_row_reason` | `row: dict[str, Any]` | no |
| 91 | `_row_ts` | `row: dict[str, Any]` | no |
| 95 | `_row_execution_result` | `row: dict[str, Any]` | no |
| 100 | `_row_execution_action_type` | `row: dict[str, Any]` | no |
| 105 | `_recommendation_key` | `row: dict[str, Any]` | no |
| 113 | `_weak_posture` | `row: dict[str, Any]` | no |
| 124 | `summary` | `self, ledger_path: Path, *, limit: int=80` | no |

## `services/behavior_metrics.py`

Lines: 67 | Functions/methods: 5 | Classes: 1

Classes: `BehaviorMetricsStore` (L22)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 23 | `__init__` | `self, metrics_file: Path, initial: dict \| None=None` | no |
| 29 | `save` | `self` | no |
| 38 | `record_event` | `self, event: str` | no |
| 48 | `snapshot` | `self` | no |
| 51 | `update_from_reflection` | `self, payload: dict, count_total: int` | yes |

## `services/capabilities_gap_detector.py`

Lines: 122 | Functions/methods: 4 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 14 | `_load_capabilities_json` | `base_dir: Path=None` | yes |
| 29 | `_load_capabilities_roadmap` | `base_dir: Path=None` | yes |
| 44 | `detect_capability_gaps` | `base_dir: Path=None` | yes |
| 86 | `enhance_status_with_capability_gaps` | `status_payload: dict[str, Any], base_dir: Path=None` | yes |

## `services/chat_identity.py`

Lines: 198 | Functions/methods: 13 | Classes: 1

Classes: `ChatIdentityService` (L11)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `chat_users_path` | `runtime_dir: Path` | no |
| 19 | `chat_auth_source` | `*, chat_users_path: Path, environ=None` | no |
| 30 | `hash_chat_password` | `password: str, *, iterations: int` | no |
| 36 | `save_managed_chat_users` | `self, users: dict, *, normalize_user_id_fn, chat_users_path: Path, iterations: int` | no |
| 62 | `chat_users` | `*, chat_users_path: Path, normalize_user_id_fn, environ=None` | no |
| 99 | `chat_password_matches` | `expected, pwd: str, *, iterations_default: int` | no |
| 114 | `chat_login_enabled` | `*, chat_users_fn` | no |
| 118 | `prune_chat_sessions` | `*, chat_sessions: dict, now_fn=time.time` | no |
| 125 | `new_chat_session` | `user_id: str, *, chat_sessions: dict, normalize_user_id_fn, ttl_seconds: int, token_hex_fn=secrets.token_hex, now_fn=time.time` | no |
| 139 | `clear_chat_session` | `handler, *, chat_sessions: dict, parse_cookie_map_fn` | no |
| 144 | `chat_login_auth` | `self, handler, *, chat_login_enabled_fn, prune_chat_sessions_fn, parse_cookie_map_fn, chat_sessions: dict, now_fn=time.time` | no |
| 167 | `chat_login_action` | `payload: dict, *, chat_login_enabled_fn, chat_users_fn, normalize_user_id_fn, chat_password_matches_fn, new_chat_session_fn` | no |
| 191 | `chat_logout_action` | `handler, *, clear_chat_session_fn` | no |

## `services/codegen_memory_recorder.py`

Lines: 348 | Functions/methods: 13 | Classes: 1

Classes: `CodegenMemoryRecorderService` (L306)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 40 | `_get_memory_store_path` | `` | yes |
| 48 | `_compute_spec_hash` | `spec_string: str` | yes |
| 53 | `record_generated_pattern` | `capability_name: str, spec_string: str, generated_code: str, test_code: str, language: str='python', tool_version: str='1.0', model_used: str='qwen2.5:7b'` | yes |
| 116 | `lookup_patterns_by_capability` | `capability_name: str, limit: int=5` | yes |
| 154 | `lookup_patterns_by_spec` | `spec_string: str, capability_name: Optional[str]=None, limit: int=3` | yes |
| 194 | `_extract_code_patterns` | `code: str, language: str` | yes |
| 227 | `_extract_test_patterns` | `test_code: str, language: str` | yes |
| 263 | `build_memory_injection_context` | `capability_name: str, spec_string: str` | yes |
| 289 | `_format_pattern_context` | `match_type: str, pattern: Dict[str, Any]` | yes |
| 310 | `record_pattern` | `capability_name: str, spec_string: str, generated_code: str, test_code: str, language: str='python', tool_version: str='1.0', model_used: str='qwen2.5:7b'` | yes |
| 331 | `lookup_by_capability` | `capability_name: str, limit: int=5` | yes |
| 336 | `lookup_by_spec` | `spec_string: str, capability_name: Optional[str]=None, limit: int=3` | yes |
| 343 | `get_memory_injection_context` | `capability_name: str, spec_string: str` | yes |

## `services/codegen_patch_bridge.py`

Lines: 231 | Functions/methods: 4 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 16 | `validate_codegen_preview` | `payload: object` | yes |
| 68 | `_generate_test_file` | `spec_name: str, artifact_path: str, artifact_kind: str` | yes |
| 94 | `bridge_codegen_to_patch` | `preview_payload: dict[str, Any], *, codegen_id: str='', operator_id: str=''` | yes |
| 192 | `format_bridge_summary` | `preview_payload: dict[str, Any], patch_artifact: dict[str, Any]` | yes |

## `services/control_actions.py`

Lines: 43 | Functions/methods: 4 | Classes: 1

Classes: `ControlActionsService` (L4)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `refresh_status_action` | `*, control_status_payload_fn` | no |
| 13 | `device_location_update_action` | `payload: dict, *, set_runtime_device_location_fn, invalidate_control_status_cache_fn` | no |
| 25 | `device_location_clear_action` | `*, clear_runtime_device_location_fn, invalidate_control_status_cache_fn` | no |
| 36 | `self_check_action` | `*, control_self_check_payload_fn` | no |

## `services/control_assets.py`

Lines: 36 | Functions/methods: 3 | Classes: 1

Classes: `ControlAssetsService` (L7)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `read_asset_text` | `path: Path` | no |
| 18 | `asset_version_token` | `path: Path` | no |
| 29 | `render_control_html` | `self, template_path: Path, css_path: Path, js_path: Path` | no |

## `services/control_auth.py`

Lines: 143 | Functions/methods: 9 | Classes: 1

Classes: `ControlAuthService` (L11)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `control_login_enabled` | `*, environ=None` | no |
| 22 | `prune_control_sessions` | `*, control_sessions: dict, now_fn=time.time` | no |
| 28 | `control_login_auth` | `self, handler, *, control_login_enabled_fn, prune_control_sessions_fn, parse_cookie_map_fn, control_sessions: dict, now_fn=time.time` | no |
| 48 | `control_page_gate` | `self, handler, *, dev_mode_enabled_fn, control_login_auth_fn, is_local_client_fn, environ=None` | no |
| 72 | `control_api_auth` | `self, handler, qs: dict, *, control_login_auth_fn, is_local_client_fn, request_control_key_fn, environ=None, compare_digest_fn=secrets.compare_digest` | no |
| 100 | `new_control_session` | `*, control_sessions: dict, ttl_seconds: int, token_hex_fn=secrets.token_hex, now_fn=time.time` | no |
| 106 | `clear_control_session` | `handler, *, control_sessions: dict, parse_cookie_map_fn` | no |
| 112 | `control_login_action` | `payload: dict, *, control_login_enabled_fn, new_control_session_fn, environ=None, compare_digest_fn=secrets.compare_digest` | no |
| 136 | `control_logout_action` | `handler, *, clear_control_session_fn` | no |

## `services/control_login_frontdoor.py`

Lines: 89 | Functions/methods: 1 | Classes: 1

Classes: `ControlLoginFrontdoorService` (L4)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `render_html` | `` | no |

## `services/control_pipelines.py`

Lines: 549 | Functions/methods: 20 | Classes: 1

Classes: `ControlPipelinesService` (L10)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 14 | `_pipeline_dir` | `data_sources_root: Path, pipeline_id: str` | no |
| 19 | `_safe_pipeline_id` | `value: str` | no |
| 25 | `_safe_population_key` | `value: str` | no |
| 30 | `lane_control_path` | `*, data_sources_root: Path, pipeline_id: str` | no |
| 34 | `lane_state` | `*, data_sources_root: Path, pipeline_id: str` | no |
| 54 | `_write_lane_state` | `*, data_sources_root: Path, pipeline_id: str, enabled: bool, reason: str='', now_fn: Callable[[], float]=time.time` | no |
| 76 | `payload` | `*, data_sources_root: Path, list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]], get_pipeline_status_fn: Callable[..., dict[str, Any]], get_pipeline_schema_probe_fn: Callable[..., dict[str, Any]], selected_pipeline_id: str=''` | no |
| 121 | `intake_path` | `*, data_sources_root: Path, pipeline_id: str` | no |
| 125 | `population_definitions_path` | `*, data_sources_root: Path, pipeline_id: str` | no |
| 129 | `intake_summary` | `*, data_sources_root: Path, pipeline_id: str, limit: int=12` | no |
| 152 | `append_note` | `payload: Mapping[str, Any], *, data_sources_root: Path, list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]], now_fn: Callable[[], float]=time.time` | no |
| 185 | `upsert_population_definition` | `payload: Mapping[str, Any], *, data_sources_root: Path, list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]], now_fn: Callable[[], float]=time.time` | no |
| 259 | `create_lane` | `payload: Mapping[str, Any], *, data_sources_root: Path, list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]], now_fn: Callable[[], float]=time.time` | no |
| 348 | `set_enabled` | `payload: Mapping[str, Any], *, data_sources_root: Path, list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]], enabled: bool, now_fn: Callable[[], float]=time.time` | no |
| 373 | `update_lane_metadata` | `payload: Mapping[str, Any], *, data_sources_root: Path, list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]], now_fn: Callable[[], float]=time.time` | no |
| 424 | `_query_params` | `payload: Mapping[str, Any]` | no |
| 429 | `run_query_preview` | `payload: Mapping[str, Any], *, data_sources_root: Path, list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]], preview_pipeline_query_fn: Callable[..., dict[str, Any]]` | no |
| 452 | `run_query_live` | `payload: Mapping[str, Any], *, data_sources_root: Path, list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]], run_pipeline_query_fn: Callable[..., dict[str, Any]]` | no |
| 474 | `_run_query` | `payload: Mapping[str, Any], *, data_sources_root: Path, list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]], execute_fn: Callable[[str, str, dict[str, Any], Optional[int]], dict[str, Any]], live: bool` | no |
| 525 | `archive_lane` | `payload: Mapping[str, Any], *, data_sources_root: Path, list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]], now_fn: Callable[[], float]=time.time` | no |

## `services/control_status.py`

Lines: 1601 | Functions/methods: 6 | Classes: 1

Classes: `ControlStatusService` (L29)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 33 | `_clean_provider_value` | `value` | no |
| 40 | `_os_capability_control_payload` | `summary: dict \| None, operator_outbox: dict \| None=None` | no |
| 130 | `runtime_supplier_fns_from_scope` | `runtime_scope: dict[str, object]` | no |
| 177 | `runtime_status_payload` | `self, *, core_module, session_turns, metrics_totals: tuple[int, int], supplier_fns: dict[str, object] \| None=None, lightweight: bool=False` | no |
| 408 | `runtime_signal_ingestion_surfaces_payload` | `self, *, core_module, session_turns, metrics_totals: tuple[int, int], supplier_fns: dict[str, object] \| None=None` | no |
| 692 | `status_payload` | `*, policy: dict, provider: str, endpoint: str, searx_ok, searx_note: str, search_provider_priority: list, provider_telemetry: dict, ollama_api_up: bool, chat_model: str, memory_enabled: bool, subconscious_summary: dict, subconscious_live_summary: dict, generated_work_queue: dict, autonomy_maintenance: dict, operator_macros: list, backend_commands: list, frontdoor_cli_status: str='', cli_http_parity: dict \| None=None, memory_scope: str, web_enabled: bool, allow_domains_count: int, process_counting_mode: str, runtime_process_note: str, heartbeat_age_sec, active_http_sessions: int, chat_login_enabled: bool, chat_auth_source: str, chat_users_count: int, guard_status: dict, core_status: dict, webui_status: dict, runtime_summary: dict, timeline_payload: dict, runtime_artifacts: dict, runtime_restart_analytics: dict, runtime_failures: dict, live_tracking: dict, action_readiness: dict, release_status: dict, memory_stats: dict, memory_summary: dict, tool_summary: dict, ledger_summary: dict, patch_summary: dict, patch_action_readiness: dict, pulse_payload: dict, update_now_pending: dict, requests_total: int, errors_total: int, os_capability_summary: dict \| None=None, validation_artifact_truth: dict \| None=None, storage_watch_summary: dict \| None=None, work_trees_payload: dict \| None=None, operator_outbox: dict \| None=None, ollama_health: dict \| None=None, voice_status: dict \| None=None, vision_status: dict \| None=None, port_ownership: dict \| None=None, data_pipelines: dict \| None=None, edfi_capability_profile: dict \| None=None, edfi_core_readiness: dict \| None=None, installer_status: dict \| None=None` | no |

## `services/control_status_cache.py`

Lines: 34 | Functions/methods: 2 | Classes: 1

Classes: `ControlStatusCacheService` (L4)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `invalidate` | `cache: dict, *, lock` | no |
| 14 | `cached_payload` | `cache: dict, *, lock, max_age_seconds: float, monotonic_fn, compute_payload_fn` | no |

## `services/control_status_surfaces.py`

Lines: 501 | Functions/methods: 7 | Classes: 1

Classes: `ControlStatusSurfacesService` (L495)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 400 | `signal_ingestion_top_level_keys` | `` | no |
| 408 | `derive_surfaces_url` | `status_url: str` | no |
| 425 | `extract_signal_ingestion_surfaces` | `payload: dict[str, Any]` | no |
| 442 | `_local_closure_inventory_authoritative` | `merged: dict[str, Any], *, inventory_key: str, ok_key: str, gap_count_key: str` | no |
| 457 | `merge_http_supplement_into_local` | `local_payload: dict[str, Any], http_payload: dict[str, Any]` | no |
| 489 | `release_drift_detected` | `release_status: Any` | no |
| 497 | `build_surfaces_payload` | `full_payload: dict[str, Any]` | no |

## `services/control_telemetry.py`

Lines: 724 | Functions/methods: 19 | Classes: 1

Classes: `ControlTelemetryService` (L9)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 12 | `__init__` | `self, *, list_capabilities_fn: Callable[[], dict]` | no |
| 16 | `_clean_provider_value` | `value: Any` | no |
| 22 | `action_ledger_summary` | `self, action_ledger_dir: Path, route_summary_fn: Callable[[dict], str], limit: int=60` | no |
| 73 | `tool_events_summary` | `self, events_log: Path, limit: int=80` | no |
| 161 | `memory_events_summary` | `self, events_log: Path, limit: int=80` | no |
| 223 | `record_control_action_event` | `runtime_dir: Path, control_audit_log: Path, action: str, result: str, detail: str='', payload: dict \| None=None` | no |
| 254 | `safe_tail_lines` | `path: Path, *, tail_file_fn, n: int=80` | no |
| 258 | `export_capabilities_snapshot` | `self, export_dir: Path, *, strftime_fn=time.strftime` | no |
| 277 | `provider_telemetry_payload` | `*, ledger_summary: dict, tool_summary: dict, search_provider_priority_fn: Callable[[], list[str] \| tuple[str, ...] \| Any], provider_name_from_tool_fn: Callable[[str], str], recent_action_ledger_records_fn: Callable[..., list[dict] \| Any], policy_web_fn: Callable[[], dict]` | no |
| 334 | `append_metrics_snapshot` | `status_payload: dict, *, metrics_lock, http_requests_total: int, http_errors_total: int, metrics_series: list[dict], metrics_max_points: int, now_fn=time.time` | no |
| 358 | `metrics_payload` | `*, metrics_lock, http_requests_total: int, http_errors_total: int, metrics_series: list[dict]` | no |
| 368 | `tail_log_action` | `payload: dict, *, log_dir: Path, tail_file_fn, record_control_action_event_fn` | no |
| 384 | `metrics_action` | `payload: dict, *, metrics_payload_fn, record_control_action_event_fn` | no |
| 390 | `export_ledger_summary_action` | `payload: dict, *, export_dir: Path, action_ledger_summary_fn, record_control_action_event_fn, strftime_fn=time.strftime` | no |
| 413 | `export_diagnostics_bundle_action` | `self, payload: dict, *, runtime_dir: Path, log_dir: Path, control_status_payload_fn, control_policy_payload_fn, metrics_payload_fn, build_self_check_fn, behavior_get_metrics_fn, action_ledger_summary_fn, tool_events_summary_fn, safe_tail_lines_fn, record_control_action_event_fn, now_fn=time.time` | no |
| 461 | `export_diagnostics_bundle_action_from_runtime` | `self, payload: dict, *, runtime_scope: dict[str, object], core_module` | no |
| 484 | `build_self_check` | `self, status: dict, policy: dict, metrics: dict` | no |
| 488 | `add_check` | `name: str, ok: bool, detail: str=''` | no |
| 491 | `safe_int` | `value, default: int=0` | no |

## `services/control_work_trees.py`

Lines: 231 | Functions/methods: 9 | Classes: 1

Classes: `ControlWorkTreesService` (L6)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `_branch_total` | `tree_payload: dict` | no |
| 15 | `_semantic_family_key` | `self, tree_payload: dict` | no |
| 45 | `_priority_tree` | `self, tree_payload: dict` | no |
| 52 | `_dedupe_key` | `self, tree_payload: dict` | no |
| 68 | `_dedupe_visible_trees` | `self, items: list[dict]` | no |
| 83 | `_compact_value` | `value, *, depth: int=0, max_depth: int=3` | no |
| 110 | `_compact_tree_payload` | `self, tree_payload: dict` | no |
| 139 | `payload` | `self, *, list_visual_trees_fn, limit: int=32` | no |
| 208 | `pressure_payload` | `self, *, work_tree_module` | no |

## `services/core_health_brief.py`

Lines: 412 | Functions/methods: 15 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 24 | `_compact` | `value: Any, max_chars: int=220` | no |
| 29 | `_slug` | `value: Any` | no |
| 36 | `_priority_rank` | `priority: str` | no |
| 43 | `_tool_from_command` | `command: str, title: str=''` | no |
| 64 | `_order` | `*, source: str, priority: str, title: str, reason: str, command: str='', recommended_tool: str='', target: dict[str, object] \| None=None` | no |
| 91 | `_is_training_pressure_advisory` | `*, title: str, reason: str, command: str, source: str=''` | no |
| 100 | `_is_enforced_cleanup_advisory` | `*, title: str, reason: str, command: str, source: str=''` | no |
| 109 | `_is_advisory_order` | `order: dict[str, object]` | no |
| 117 | `build_core_health_brief` | `*, core_steward: dict \| None=None, self_status: dict \| None=None, runtime_summary: dict \| None=None, runtime_artifacts: dict \| None=None, pipeline_summary: dict \| None=None` | yes |
| 250 | `write_core_health_brief` | `path: Path, brief: dict[str, object]` | no |
| 255 | `render_core_health_brief` | `brief: dict \| None=None, *, feed_result: dict \| None=None` | no |
| 296 | `_status_value` | `value: Any` | no |
| 300 | `_active_core_health_tree` | `work_tree_module` | no |
| 313 | `_resolve_stale_core_health_tasks` | `work_tree_module, tree, active_order_ids: set[str]` | no |
| 326 | `feed_core_health_brief_to_work_tree` | `brief: dict[str, object], *, work_tree_module` | yes |

## `services/core_seam_guard.py`

Lines: 128 | Functions/methods: 2 | Classes: 1

Classes: `CoreSeamGuardService` (L6)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 46 | `_read_text` | `path: Path` | no |
| 52 | `run_checks` | `self, base_dir: Path` | no |

## `services/core_steward.py`

Lines: 345 | Functions/methods: 7 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `_check_name` | `item: Any` | no |
| 16 | `_check_ok` | `item: Any` | no |
| 22 | `_check_required` | `item: Any` | no |
| 28 | `_queue_item` | `priority: str, title: str, reason: str, command: str` | no |
| 37 | `build_core_steward_payload` | `*, preflight_checks: list[Any], runtime_health: dict, pulse_payload: dict, autonomy_maintenance: dict, kidney_summary: dict` | no |
| 257 | `build_core_steward_gates` | `*, core_steward: dict \| None, patch_summary: dict \| None=None, release_status: dict \| None=None` | no |
| 309 | `render_core_steward` | `payload: dict \| None=None` | no |

## `services/core_steward_contracts.py`

Lines: 4 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `services/core_thinning.py`

Lines: 810 | Functions/methods: 27 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 23 | `_protected_public_wrapper_names` | `` | no |
| 40 | `_slug` | `value: Any` | no |
| 45 | `_status_value` | `value: Any` | no |
| 49 | `_priority_rank` | `value: Any` | no |
| 53 | `_branch_priority` | `value: Any` | no |
| 57 | `_target_semantic_key` | `kind: Any, target: dict[str, object] \| None` | no |
| 67 | `_function_span` | `node: ast.AST` | no |
| 73 | `_called_name` | `call: ast.Call` | no |
| 89 | `_return_call_name` | `node: ast.AST` | no |
| 95 | `_is_service_wrapper` | `node: ast.FunctionDef \| ast.AsyncFunctionDef` | no |
| 105 | `_function_bounds` | `node: ast.FunctionDef \| ast.AsyncFunctionDef` | no |
| 111 | `_functions_named` | `tree: ast.AST, name: str` | no |
| 122 | `_http_surface_theme` | `name: str` | no |
| 143 | `_http_surface_candidates` | `path: Path, functions: list[dict[str, object]], *, limit: int=8` | no |
| 200 | `_runtime_hook_reference_names` | `paths: list[Path]` | no |
| 239 | `_order` | `*, kind: str, title: str, reason: str, target: dict[str, object], priority: str='medium'` | no |
| 252 | `_core_paths` | `core_path: Path \| list[Path] \| tuple[Path, ...]` | no |
| 258 | `_analyze_core_file` | `path: Path, *, large_function_threshold: int, wrapper_limit: int, protected_wrapper_names: set[str] \| None=None` | no |
| 377 | `build_core_thinning_brief` | `core_path: Path \| list[Path] \| tuple[Path, ...], *, large_function_threshold: int=160, wrapper_limit: int=12` | no |
| 415 | `build_core_thinning_owner_verdict` | `brief: dict[str, object] \| None, *, feed_result: dict[str, object] \| None=None` | yes |
| 474 | `render_core_thinning_brief` | `brief: dict \| None=None, *, feed_result: dict \| None=None` | no |
| 515 | `_target_from_payload` | `payload: str \| dict[str, object]` | no |
| 527 | `_name_reference_count` | `tree: ast.AST, name: str` | no |
| 531 | `_name_reference_counts` | `tree: ast.AST, names: set[str]` | no |
| 541 | `execute_core_thinning_order` | `payload: str \| dict[str, object], *, python_executable: str \| None=None` | yes |
| 671 | `_active_core_thinning_tree` | `work_tree_module` | no |
| 681 | `feed_core_thinning_brief_to_work_tree` | `brief: dict[str, object], *, work_tree_module` | no |

## `services/data_pipeline_registry.py`

Lines: 126 | Functions/methods: 10 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `_lane_control_state` | `pipeline_id: str, *, data_sources_root: Optional[Path]=None` | no |
| 31 | `_lane_paused_result` | `pipeline_id: str, operation: str` | no |
| 41 | `build_pipeline_registry` | `data_sources_root: Optional[Path]=None` | no |
| 45 | `list_pipeline_summaries` | `data_sources_root: Optional[Path]=None` | no |
| 53 | `get_pipeline_status` | `pipeline_id: str, *, data_sources_root: Optional[Path]=None` | no |
| 63 | `get_pipeline_schema_probe` | `pipeline_id: str, *, data_sources_root: Optional[Path]=None` | no |
| 72 | `search_pipeline_vendor_dictionary` | `pipeline_id: str, query: str, *, limit: int=12, data_sources_root: Optional[Path]=None` | no |
| 86 | `plan_pipeline_report` | `pipeline_id: str, request: str, *, limit: int=8, data_sources_root: Optional[Path]=None` | no |
| 100 | `preview_pipeline_query` | `pipeline_id: str, operation: str, params: Optional[Mapping[str, Any]]=None, *, row_limit: Optional[int]=None, dry_run: bool=True, data_sources_root: Optional[Path]=None` | no |
| 115 | `run_pipeline_query` | `pipeline_id: str, operation: str, params: Optional[Mapping[str, Any]]=None, *, row_limit: Optional[int]=None, data_sources_root: Optional[Path]=None` | no |

## `services/decision_pipeline.py`

Lines: 120 | Functions/methods: 6 | Classes: 2

Classes: `RegisteredStage` (L64), `StageRegistry` (L70)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `_clean_trace_data` | `raw: dict[str, Any]` | no |
| 49 | `make_trace_entry` | `stage: str, result: str, detail: str='', **data: Any` | no |
| 71 | `__init__` | `self` | no |
| 74 | `register` | `self, name: str, *, priority: int, handler: StageHandler` | no |
| 81 | `ordered` | `self` | no |
| 85 | `run_registered_stages` | `registry: StageRegistry, context: dict[str, Any] \| None=None` | no |

## `services/edfi/__init__.py`

Lines: 221 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 66 | `run_self_profile` | `*, connection_id: str, base_url: str='', client_id: str='', client_secret: str='', save_config: bool=True, now_fn: Callable[[], float]=time.time` | yes |
| 201 | `_resolve_config` | `*, connection_id: str, base_url: str, client_id: str, client_secret: str` | no |

## `services/edfi/auth.py`

Lines: 170 | Functions/methods: 6 | Classes: 2

Classes: `AuthResult` (L14), `EdFiAuthService` (L27)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 30 | `__init__` | `self, *, session: requests.Session \| None=None` | no |
| 34 | `fetch_token` | `self, config: ConnectionConfig, *, now_fn: Callable[[], float]=time.time` | no |
| 116 | `_request_token` | `self, config: ConnectionConfig, token_endpoint: str, *, use_basic_auth: bool \| None=None` | no |
| 139 | `get_authorization_header` | `self, config: ConnectionConfig, *, force_refresh: bool=False, now_fn: Callable[[], float]=time.time` | no |
| 163 | `_compact_error` | `text: str, *, limit: int=220` | no |
| 168 | `_looks_like_invalid_client_auth` | `text: str` | no |

## `services/edfi/change_tracking.py`

Lines: 427 | Functions/methods: 16 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 26 | `_safe_int` | `value: Any, default: int=0` | no |
| 33 | `_normalize_resource` | `resource: str` | no |
| 45 | `_load_json_dict` | `path` | no |
| 55 | `_root_manifest` | `client: EdFiClient` | no |
| 61 | `resolve_change_queries_base` | `client: EdFiClient` | no |
| 70 | `resolve_data_management_api` | `client: EdFiClient` | no |
| 76 | `fetch_available_change_versions` | `client: EdFiClient` | no |
| 112 | `load_sync_state` | `connection_id: str` | no |
| 116 | `save_sync_state` | `connection_id: str, state: Mapping[str, Any] \| None=None, *, now_fn: Callable[[], float]=time.time` | no |
| 132 | `_resource_state` | `state: dict[str, Any], resource: str` | no |
| 138 | `_max_item_change_version` | `items: list[Any]` | no |
| 149 | `sync_status` | `connection_id: str` | no |
| 188 | `_attempt_change_query_pull` | `client: EdFiClient, *, change_base: str, resource: str, min_change_version: int, limit: int, offset: int` | no |
| 219 | `_attempt_data_api_pull` | `client: EdFiClient, *, data_api: str, resource: str, min_change_version: int, limit: int, offset: int` | no |
| 253 | `_district_filter_items` | `items: list[Any], *, district_lea_id: str` | no |
| 273 | `pull_changes_since` | `connection_id: str, *, resource: str='ed-fi/schools', min_change_version: int \| None=None, limit: int=25, offset: int=0, advance_cursor: bool=False, now_fn: Callable[[], float]=time.time` | no |

## `services/edfi/client.py`

Lines: 157 | Functions/methods: 8 | Classes: 2

Classes: `EdFiResponse` (L15), `EdFiClient` (L27)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 30 | `__init__` | `self, config: ConnectionConfig, *, auth_service: EdFiAuthService \| None=None, session: requests.Session \| None=None` | no |
| 41 | `authenticate` | `self, *, force_refresh: bool=False` | no |
| 45 | `request` | `self, method: str, url: str, *, params: dict[str, Any] \| None=None, json_body: dict[str, Any] \| None=None, retry_auth: bool=True` | no |
| 120 | `get` | `self, url_or_resource: str, *, params: dict[str, Any] \| None=None` | no |
| 124 | `test_connection` | `self` | no |
| 140 | `_resolve_url` | `config: ConnectionConfig, url_or_resource: str` | no |
| 147 | `_parse_json` | `response: requests.Response` | no |
| 156 | `_compact_text` | `text: str, *, limit: int=220` | no |

## `services/edfi/config.py`

Lines: 227 | Functions/methods: 23 | Classes: 2

Classes: `ConnectionConfig` (L24), `TokenCacheEntry` (L68)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 39 | `normalized_base_url` | `self` | no |
| 42 | `token_url` | `self` | no |
| 45 | `metadata_url` | `self` | no |
| 48 | `sample_resource_url` | `self` | no |
| 51 | `resource_url` | `self, resource: str` | no |
| 55 | `ssl_verify` | `self` | no |
| 61 | `to_public_dict` | `self` | no |
| 74 | `valid` | `self, *, now: float \| None=None` | no |
| 79 | `_path` | `value: str` | no |
| 86 | `_safe_connection_id` | `connection_id: str` | no |
| 93 | `connection_dir` | `connection_id: str` | no |
| 97 | `connection_config_path` | `connection_id: str` | no |
| 101 | `profile_path` | `connection_id: str` | no |
| 105 | `ensure_runtime_dirs` | `` | no |
| 112 | `change_cursor_path` | `connection_id: str` | no |
| 116 | `_load_json_dict` | `path: Path` | no |
| 130 | `validate_connection_payload` | `data: dict[str, Any], *, connection_id: str=''` | no |
| 164 | `load_connection_config` | `connection_id: str` | no |
| 174 | `connection_config_from_dict` | `data: dict[str, Any], *, connection_id: str=''` | no |
| 200 | `save_connection_config` | `config: ConnectionConfig` | no |
| 209 | `save_capability_profile` | `connection_id: str, profile: dict[str, Any]` | no |
| 216 | `load_capability_profile` | `connection_id: str` | no |
| 220 | `runtime_roots` | `` | no |

## `services/edfi/core_readiness.py`

Lines: 125 | Functions/methods: 6 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 17 | `_work_tree_signal_ingestion_source` | `` | no |
| 25 | `_inventory_declared` | `` | no |
| 29 | `_evidence_loop_ready` | `` | no |
| 43 | `_issue_messages` | `issues: list[Any]` | no |
| 59 | `_next_recommended_slice` | `*, profile_ok: bool, inventory_declared: bool, evidence_loop_ready: bool, district_facts_ok: bool` | no |
| 77 | `read_edfi_core_readiness` | `connection_id: str=DEFAULT_CONNECTION_ID` | yes |

## `services/edfi/diagnostics.py`

Lines: 140 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 14 | `build_health_payload` | `config: ConnectionConfig, *, auth: AuthResult, discovery: DiscoveryResult, profile_path: str='', now_fn: Callable[[], float]=time.time` | no |
| 106 | `build_config_error_health` | `*, connection_id: str, error_code: str, detail: str='', validation_errors: list[dict[str, str]] \| None=None, now_fn: Callable[[], float]=time.time` | no |
| 130 | `append_audit_event` | `event: dict[str, Any], *, audit_log_path: Path \| None=None` | no |

## `services/edfi/discovery.py`

Lines: 317 | Functions/methods: 13 | Classes: 1

Classes: `DiscoveryResult` (L17)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 36 | `discover_metadata` | `client: EdFiClient` | no |
| 77 | `build_capability_profile` | `config: ConnectionConfig, discovery: DiscoveryResult, *, auth_summary: dict[str, Any], health: dict[str, Any], now_fn: Callable[[], float]=time.time` | no |
| 113 | `discover_and_save_profile` | `client: EdFiClient, *, auth_summary: dict[str, Any], health: dict[str, Any], now_fn: Callable[[], float]=time.time` | no |
| 132 | `_discovery_stages` | `discovery: DiscoveryResult, config: ConnectionConfig` | no |
| 158 | `_discover_from_root_manifest` | `client: EdFiClient, primary_metadata: EdFiResponse` | no |
| 207 | `_resource_names_from_dependencies` | `body: Any` | no |
| 223 | `_namespaces_from_resource_paths` | `resources: list[str]` | no |
| 235 | `_data_model_version_from_manifest` | `manifest: dict[str, Any]` | no |
| 247 | `_pick_sample_resource_path` | `resources: list[str], preferred: str` | no |
| 260 | `_join_data_api_url` | `data_api: str, resource_path: str` | no |
| 266 | `_parse_metadata_body` | `body: Any` | no |
| 290 | `_resource_names` | `raw: Any` | no |
| 307 | `_namespace_names` | `raw: Any` | no |

## `services/edfi/district_scope.py`

Lines: 76 | Functions/methods: 6 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `normalize_district_lea_id` | `value: Any` | no |
| 15 | `district_lea_filter_clause` | `resource: str, lea_id: Any` | yes |
| 27 | `merge_filter_params` | `filter_params: dict[str, Any] \| None, clause: str \| None` | no |
| 39 | `uses_client_side_district_filter` | `base_url: str` | yes |
| 44 | `item_matches_district` | `item: Any, lea_id: Any` | no |
| 75 | `district_filter_strategy` | `base_url: str` | no |

## `services/edfi/errors.py`

Lines: 69 | Functions/methods: 5 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `classify_http_status` | `status_code: int` | no |
| 25 | `classify_request_exception` | `exc: BaseException` | no |
| 46 | `issue_from_error` | `*, severity: str, code: str, detail: str` | no |
| 54 | `config_validation_issues` | `errors: list[dict[str, str]]` | no |
| 58 | `empty_health_shell` | `*, connection_id: str='', base_url: str=''` | no |

## `services/edfi/inventory.py`

Lines: 358 | Functions/methods: 10 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 37 | `build_client` | `connection_id: str` | no |
| 44 | `profile_summary` | `connection_id: str` | no |
| 77 | `refresh_resource_catalog` | `connection_id: str` | no |
| 128 | `list_resources` | `connection_id: str, *, query: str='', namespace: str='', limit: int=50, offset: int=0, refresh: bool=False` | no |
| 183 | `read_resource` | `connection_id: str, resource: str, *, limit: int=DEFAULT_PAGE_SIZE, offset: int=0, filter_params: dict[str, Any] \| None=None, apply_district_scope: bool=True` | no |
| 268 | `read_preset` | `connection_id: str, preset: str, *, limit: int=DEFAULT_PAGE_SIZE, offset: int=0, apply_district_scope: bool=True` | no |
| 310 | `_safe_int` | `value: Any` | no |
| 317 | `_resolve_resource_name` | `resource: str` | no |
| 327 | `_resource_names` | `discovery: dict[str, Any]` | no |
| 342 | `_filter_resources` | `resources: list[str], *, query: str, namespace: str` | no |

## `services/edfi/profile_evidence.py`

Lines: 387 | Functions/methods: 12 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 19 | `_relative_profile_path` | `connection_id: str` | no |
| 24 | `_relative_change_cursor_path` | `connection_id: str` | no |
| 29 | `_safe_int` | `value: Any, default: int=0` | no |
| 36 | `_summarize_saved_sync_state` | `state: dict[str, Any], *, connection_id: str` | yes |
| 67 | `_normalize_evidence_path` | `value: Any` | no |
| 71 | `_parse_tool_args_json` | `raw: Any` | no |
| 86 | `extract_profile_from_read_result` | `result: Any` | no |
| 110 | `capability_profile_payload_valid` | `payload: dict[str, Any], *, require_auth_ok: bool=True, min_resource_count: int=1` | no |
| 135 | `profile_read_evidence_valid` | `row: dict[str, Any], *, expected_path: str=DEFAULT_PROFILE_EVIDENCE_PATH` | no |
| 158 | `audit_runtime_profile_contract` | `connection_id: str=DEFAULT_CONNECTION_ID, *, expected_lea_id: str=EXPECTED_BISD_LEA_ID, expected_resource_count: int=EXPECTED_BISD_RESOURCE_COUNT, runtime_root: Any \| None=None` | yes |
| 252 | `build_capability_profile_evidence` | `connection_id: str=DEFAULT_CONNECTION_ID, *, now_fn: Callable[[], float]=time.time, profile_override: dict[str, Any] \| None=None, path_override: Path \| str \| None=None, sync_state_override: dict[str, Any] \| None=None` | yes |
| 365 | `get_district_layer_facts` | `connection_id: str=DEFAULT_CONNECTION_ID` | yes |

## `services/edfi/resources.py`

Lines: 325 | Functions/methods: 4 | Classes: 2

Classes: `PageResult` (L25), `ResourceReadResult` (L43)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 56 | `get_page` | `client: EdFiClient, resource: str, *, limit: int=DEFAULT_PAGE_SIZE, offset: int=0, filter_params: dict[str, Any] \| None=None, backoff_sec: float=_DEFAULT_BACKOFF_SEC, audit: bool=False` | yes |
| 124 | `get_district_scoped_page` | `client: EdFiClient, resource: str, *, district_lea_id: Any, limit: int=DEFAULT_PAGE_SIZE, offset: int=0, backoff_sec: float=_DEFAULT_BACKOFF_SEC, audit: bool=False, max_scan_records: int=MAX_DISTRICT_SCAN_RECORDS` | yes |
| 233 | `get_all` | `client: EdFiClient, resource: str, *, page_size: int=DEFAULT_PAGE_SIZE, limit_cap: int=DEFAULT_LIMIT_CAP, filter_params: dict[str, Any] \| None=None, backoff_sec: float=_DEFAULT_BACKOFF_SEC` | yes |
| 322 | `_extract_items` | `body: Any` | no |

## `services/end_to_end_wiring.py`

Lines: 746 | Functions/methods: 26 | Classes: 1

Classes: `_SyntheticCoreModule` (L257)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 77 | `_check` | `name: str, ok: bool, detail: str, *, required: bool=True, data: dict[str, Any] \| None=None` | no |
| 87 | `_read_text` | `path: Path` | no |
| 91 | `_default_runner` | `name: str, command: Sequence[str], cwd: Path, timeout_sec: int` | no |
| 120 | `_frontdoor_checks` | `root: Path` | no |
| 149 | `_release_clean_checks` | `root: Path` | no |
| 171 | `_import_checks` | `root: Path` | no |
| 185 | `_pipeline_checks` | `root: Path` | no |
| 261 | `load_policy` | `` | no |
| 274 | `mem_stats_payload` | `*, emit_event: bool=False` | no |
| 279 | `patch_status_payload` | `` | no |
| 293 | `build_pulse_payload` | `` | no |
| 306 | `update_now_pending_payload` | `` | no |
| 310 | `ollama_health_payload` | `` | no |
| 329 | `voice_status_payload` | `` | no |
| 340 | `vision_status_payload` | `**_kwargs` | no |
| 352 | `get_search_provider_priority` | `` | no |
| 356 | `chat_model` | `` | no |
| 360 | `mem_enabled` | `` | no |
| 364 | `runtime_device_location_payload` | `` | no |
| 368 | `_synthetic_control_status_payload` | `` | no |
| 499 | `_latest_release_clean_check` | `root: Path` | no |
| 536 | `_health_check` | `root: Path, runner: CommandRunner, python_executable: str, timeout_sec: int` | no |
| 555 | `_autonomy_log_check` | `root: Path, *, max_age_sec: int=3600` | no |
| 568 | `_source_wiring_inventory_checks` | `root: Path` | no |
| 679 | `_source_root_inventory_checks` | `root: Path` | no |
| 710 | `run_end_to_end_wiring_check` | `*, root: Path \| None=None, include_runtime: bool=True, python_executable: str \| None=None, command_runner: CommandRunner \| None=None, timeout_sec: int=60` | no |

## `services/evidence_validity.py`

Lines: 106 | Functions/methods: 4 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 49 | `_is_structured_judgment_result` | `tool_name: str, result: dict[str, Any]` | no |
| 56 | `_parse_structured_tool_result` | `text_raw: str` | no |
| 71 | `invalid_tool_result` | `tool_name: str, result: Any` | yes |
| 102 | `evidence_result_valid` | `row: dict[str, Any]` | no |

## `services/frontdoor_cli_parity.py`

Lines: 184 | Functions/methods: 7 | Classes: 1

Classes: `FrontdoorCliParityService` (L167)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 20 | `_read_text` | `path: Path` | no |
| 26 | `_frontdoor_entry_checks` | `root: Path` | no |
| 48 | `_deck_entry_checks` | `root: Path, backend_commands: list[dict]` | no |
| 77 | `_http_backend_action_checks` | `` | no |
| 91 | `_derive_frontdoor_cli_status` | `*, backend_commands: Any, frontdoor_checks_ok: bool, deck_entries_ok: bool, http_actions_present: bool` | no |
| 107 | `build_frontdoor_cli_surfaces` | `*, root: Path, backend_commands: list[dict] \| None=None, limit: int=40, load_backend_commands_fn: Callable[[int], list[dict]] \| None=None` | no |
| 169 | `build_surfaces` | `*, root: Path, backend_commands: list[dict] \| None=None, limit: int=40, load_backend_commands_fn: Callable[[int], list[dict]] \| None=None` | no |

## `services/fulfillment_flow.py`

Lines: 247 | Functions/methods: 6 | Classes: 1

Classes: `FulfillmentFlowService` (L30)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 7 | `_load_fulfillment_dependencies` | `` | no |
| 31 | `__init__` | `self, *, probe_turn_routes_fn, update_subconscious_state_fn, session_state_service` | no |
| 42 | `should_attempt_fulfillment_flow` | `self, user_text: str, session: object, recent_turns: list[tuple[str, str]], *, pending_action: Optional[dict]=None, semantic_observation: Optional[dict]=None` | no |
| 68 | `build_fulfillment_state` | `intent: object, models: list[object], assessments: list[object], choice_set: object` | no |
| 82 | `render_fulfillment_reply` | `choice_set: object` | no |
| 116 | `maybe_run_fulfillment_flow` | `self, user_text: str, session: object, recent_turns: list[tuple[str, str]], *, pending_action: Optional[dict]=None, semantic_observation: Optional[dict]=None` | no |

## `services/generated_work_queue_snapshot.py`

Lines: 35 | Functions/methods: 1 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `generated_work_queue_payload` | `limit: int=24, *, base_dir: Path \| None=None, runtime_dir: Path \| None=None` | no |

## `services/identity_memory.py`

Lines: 54 | Functions/methods: 3 | Classes: 1

Classes: `IdentityMemoryService` (L11)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 22 | `__init__` | `self, normalize_text_fn=None` | no |
| 26 | `_default_normalize_text` | `text: str` | yes |
| 30 | `is_identity_memory_text_allowed` | `self, kind: str, text: str` | yes |

## `services/installer_validation.py`

Lines: 279 | Functions/methods: 10 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 22 | `_tail` | `text: str, limit: int=12000` | no |
| 28 | `_safe_fragment` | `value: str` | no |
| 33 | `_command_log_paths` | `name: str, log_root: Path` | no |
| 39 | `_read_text_tail` | `path: Path, limit: int=12000` | no |
| 46 | `_default_command_runner` | `name: str, command: Sequence[str], cwd: Path, timeout_sec: int, *, log_root: Path \| None=None` | no |
| 103 | `_step_failed` | `step: dict[str, Any] \| None` | no |
| 107 | `_info_value` | `stdout: str, label: str` | no |
| 118 | `_write_report` | `report: dict[str, Any], report_path: Path \| None=None` | no |
| 124 | `run_installer_validation` | `*, repo_root: Path \| str=ROOT, package_artifact_path: str='', compiler_path: str='', promote_result: str='pass-with-notes', promotion_note: str='automated installer file/provenance validation; guided install flow not independently proven', command_runner: CommandRunner \| None=None` | no |
| 257 | `render_installer_validation_report` | `report: dict[str, Any]` | no |

## `services/layer_maturity_policy.py`

Lines: 361 | Functions/methods: 18 | Classes: 1

Classes: `LayerMaturityPolicyService` (L347)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 41 | `_clean_mode` | `value: Any` | no |
| 46 | `_normalize_capability_names` | `values: Any` | no |
| 60 | `normalize_layer_policy` | `policy: dict[str, Any] \| None` | no |
| 75 | `layer_for_capability` | `capability_name: str` | no |
| 80 | `_root_closure_by_id` | `status_payload: dict[str, Any]` | no |
| 96 | `evaluate_core_gate` | `status_payload: dict[str, Any]` | no |
| 126 | `_leah_prerequisite_roots_ok` | `capability_name: str, status_payload: dict[str, Any]` | no |
| 141 | `next_leah_capability_in_sequence` | `gaps: list[str], *, promoted_capabilities: list[str] \| None=None, registered_capabilities: set[str] \| None=None` | no |
| 169 | `capability_action_block_reason` | `capability_name: str, *, policy: dict[str, Any] \| None, status_payload: dict[str, Any] \| None=None` | no |
| 218 | `capability_action_allowed` | `capability_name: str, *, policy: dict[str, Any] \| None, status_payload: dict[str, Any] \| None=None` | no |
| 231 | `filter_actionable_capability_gaps` | `gaps: list[str], *, policy: dict[str, Any] \| None, status_payload: dict[str, Any] \| None=None` | no |
| 246 | `build_layer_maturity_summary` | `status_payload: dict[str, Any], *, policy: dict[str, Any] \| None=None` | no |
| 293 | `enrich_status_with_layer_maturity` | `status_payload: dict[str, Any], *, policy: dict[str, Any] \| None=None` | no |
| 310 | `capability_gap_signal_suppressed` | `status_payload: dict[str, Any]` | no |
| 320 | `orchestrator_codegen_action_allowed` | `action_type: str, *, policy: dict[str, Any] \| None, status_payload: dict[str, Any] \| None=None, capability_name: str=''` | no |
| 349 | `normalize_layer_policy` | `policy: dict[str, Any] \| None` | no |
| 353 | `build_summary` | `status_payload: dict[str, Any], *, policy: dict[str, Any] \| None=None` | no |
| 357 | `enrich_status` | `status_payload: dict[str, Any], *, policy: dict[str, Any] \| None=None` | no |

## `services/leah_conversation_continuity.py`

Lines: 73 | Functions/methods: 7 | Classes: 1

Classes: `LeahConversationContinuityStore` (L21)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 16 | `_safe_session_id` | `session_id: str` | no |
| 24 | `__init__` | `self, *, root: Path \| None=None, ttl_seconds: int=30 * 60` | no |
| 28 | `session_path` | `self, session_id: str` | no |
| 31 | `load` | `self, session_id: str, *, now: float \| None=None` | no |
| 51 | `save` | `self, session_id: str, payload: dict[str, Any]` | no |
| 65 | `clear` | `self, session_id: str` | no |
| 72 | `capability_registration` | `` | no |

## `services/leah_fast_chat.py`

Lines: 21 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 6 | `leah_fast_chat_enabled` | `policy: dict[str, Any] \| None, *, input_source: str` | no |
| 14 | `load_leah_fast_chat_from_core` | `core` | no |

## `services/leah_frontdoor.py`

Lines: 298 | Functions/methods: 13 | Classes: 1

Classes: `LeahFrontdoorService` (L11)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 34 | `__init__` | `self, *, asset_service: Any, template_path_provider: Callable[[], Path], css_path_provider: Callable[[], Path], js_path_provider: Callable[[], Path], fx_js_path_provider: Callable[[], Path] \| None=None, upload_root_provider: Callable[[], Path], upload_max_items: int=6, upload_max_bytes: int=8 * 1024 * 1024, context_ttl_seconds: int=30 * 60, continuity_store: Any \| None=None` | no |
| 60 | `render_html` | `self` | no |
| 75 | `clear_session_context` | `self` | no |
| 78 | `_safe_filename` | `self, name: str, *, mime: str='', source: str=''` | no |
| 89 | `_session_upload_dir` | `self, session_id: str` | no |
| 95 | `ingest_items` | `self, session_id: str, user_id: str, items: list[dict]` | no |
| 131 | `compose_chat_message` | `self, message: str, attachments: list[dict]` | no |
| 160 | `_prune_session_context` | `self, *, now: float \| None=None` | no |
| 170 | `remember_session_context` | `self, session_id: str, items: list[dict], *, stage: str` | no |
| 188 | `recent_session_context` | `self, session_id: str` | no |
| 210 | `_attachment_intent` | `self, message: str, attachments: list[dict]` | no |
| 239 | `_text_preview` | `self, path_text: str` | no |
| 257 | `maybe_answer_attachment_turn` | `self, message: str, attachments: list[dict], *, recent_items: list[dict] \| None=None, recent_stage: str=''` | no |

## `services/memory_adapter.py`

Lines: 213 | Functions/methods: 20 | Classes: 1

Classes: `MemoryAdapterService` (L11)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 14 | `__init__` | `self, *, policy_memory_getter: Callable[[], dict], active_user_getter: Callable[[], Optional[str]]` | no |
| 23 | `mem_enabled` | `self` | no |
| 26 | `mem_top_k` | `self` | no |
| 32 | `mem_scope` | `self` | no |
| 38 | `mem_context_top_k` | `self` | no |
| 45 | `mem_min_score` | `self` | no |
| 51 | `mem_exclude_sources` | `self` | no |
| 55 | `mem_store_min_chars` | `self` | no |
| 61 | `mem_store_exclude_patterns` | `self` | no |
| 70 | `mem_store_include_patterns` | `self` | no |
| 79 | `mem_retention_policy` | `self` | no |
| 82 | `mem_recall_exclude_kinds` | `self` | no |
| 85 | `memory_kind_store_allowed` | `self, kind: str` | no |
| 97 | `default_local_user_id` | `` | no |
| 108 | `memory_write_user` | `self` | no |
| 120 | `memory_runtime_user` | `self` | no |
| 128 | `memory_should_keep_text` | `self, text: str` | no |
| 169 | `mem_should_store` | `self, text: str` | no |
| 173 | `format_memory_recall_hits` | `self, hits` | no |
| 198 | `_format_recall_text` | `kind: str, text: str` | no |

## `services/memory_bootstrap_contracts.py`

Lines: 3 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `services/memory_bootstrap_judgment.py`

Lines: 166 | Functions/methods: 4 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 9 | `_issue_codes` | `memory_health: dict[str, Any]` | no |
| 21 | `_evidence_tools` | `evidence_rows: list[dict[str, Any]]` | no |
| 34 | `build_memory_bootstrap_judgment` | `*, memory_enabled: bool, memory_health: dict[str, Any], identity_file: Path, learned_facts_file: Path, memory_events_log: Path, branch_payload: dict[str, Any], evidence_rows: list[dict[str, Any]]` | no |
| 136 | `render_memory_bootstrap_judgment` | `judgment: dict[str, Any]` | no |

## `services/memory_bootstrap_origin.py`

Lines: 313 | Functions/methods: 11 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 29 | `_compact` | `value: Any, max_chars: int=220` | no |
| 34 | `_issue` | `severity: str, code: str, detail: str, *, path: Path \| None=None` | no |
| 45 | `_default_slot_payload` | `slot: str` | no |
| 53 | `default_pending_origin_contract` | `*, created_by: str='codex_root_repair', now_fn: Callable[[], float]=time.time` | no |
| 75 | `write_origin_contract` | `path: Path, payload: dict[str, object]` | no |
| 83 | `_clean_slot_value` | `slot_key: str, raw_value: Any` | no |
| 94 | `_load_json_dict` | `path: Path` | no |
| 104 | `_slot_rows` | `raw_slots: Any` | no |
| 123 | `_raw_origin_contract` | `path: Path, *, now_fn: Callable[[], float]=time.time` | no |
| 133 | `confirm_origin_contract` | `path: Path, slot_values: dict[str, Any], *, confirmed_by: str='operator', evidence: str='', now_fn: Callable[[], float]=time.time` | yes |
| 218 | `load_origin_contract` | `path: Path` | no |

## `services/memory_health.py`

Lines: 424 | Functions/methods: 11 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `_compact` | `value: Any, max_chars: int=220` | no |
| 18 | `_issue` | `severity: str, code: str, detail: str, *, path: Path \| None=None` | no |
| 29 | `_tmp_path` | `path: Path` | no |
| 36 | `_load_json_dict` | `path: Path` | no |
| 46 | `_json_file_health` | `path: Path, *, label: str` | no |
| 85 | `_tail_jsonl_lines` | `path: Path, *, max_lines: int=40, max_bytes: int=65536` | no |
| 100 | `_jsonl_log_health` | `path: Path, *, label: str` | no |
| 181 | `_sqlite_memory_health` | `db_path: Path` | no |
| 238 | `_load_snapshot` | `path: Path` | no |
| 248 | `_write_snapshot` | `path: Path, payload: dict[str, object]` | no |
| 256 | `build_memory_health_payload` | `*, memory_db_path: Path, learned_facts_file: Path, identity_file: Path, bootstrap_origin_file: Path \| None=None, memory_events_log: Path \| None=None, snapshot_file: Path \| None=None, update_snapshot: bool=False, memory_enabled: bool \| None=None, memory_retention_policy: dict[str, object] \| None=None, now_fn: Callable[[], float]=time.time` | no |

## `services/memory_identity_bootstrap.py`

Lines: 189 | Functions/methods: 6 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 12 | `_text` | `value: Any, limit: int=220` | no |
| 16 | `_slot_values` | `origin_contract: dict[str, Any]` | no |
| 28 | `_ready_origin` | `origin_contract: dict[str, Any]` | no |
| 48 | `build_identity_bootstrap_preview` | `origin_contract: dict[str, Any]` | no |
| 64 | `apply_identity_bootstrap` | `*, origin_contract: dict[str, Any], identity_file: Path, learned_facts_file: Path, load_identity_profile_fn: Callable[[], dict], save_identity_profile_fn: Callable[[dict], None], load_learned_facts_fn: Callable[[], dict], save_learned_facts_fn: Callable[[dict], None], mem_add_fn: Callable[[str, str, str], object] \| None=None, record_memory_event_fn: Callable[..., None] \| None=None, now_fn: Callable[[], float]=time.time` | no |
| 168 | `render_identity_bootstrap_result` | `result: dict[str, Any]` | no |

## `services/memory_retention.py`

Lines: 289 | Functions/methods: 7 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 22 | `_normalize_kind_list` | `values: Any, *, fallback: tuple[str, ...]` | no |
| 36 | `parse_retention_policy` | `memory_policy: dict[str, Any] \| None` | no |
| 64 | `_kind_counts` | `con: sqlite3.Connection` | no |
| 71 | `evaluate_contamination` | `db_path: Path, *, retention_policy: dict[str, Any] \| None=None` | no |
| 138 | `_append_audit_line` | `path: Path, entry: dict[str, Any]` | no |
| 147 | `apply_memory_hygiene` | `db_path: Path, *, retention_policy: dict[str, Any] \| None=None, dry_run: bool=True, audit_log_path: Path \| None=None, now_fn: Callable[[], float]=time.time` | no |
| 263 | `render_memory_hygiene_result` | `result: dict[str, Any]` | no |

## `services/memory_routing.py`

Lines: 79 | Functions/methods: 4 | Classes: 2

Classes: `MemoryRecallPlan` (L8), `MemoryRoutingService` (L15)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 31 | `_normalize_purpose` | `purpose: str` | no |
| 35 | `infer_purpose` | `self, query: str` | no |
| 38 | `session_priority_active` | `self, *, conversation_state: Optional[dict]=None, pending_action: Optional[dict]=None` | no |
| 55 | `plan_durable_recall` | `self, query: str, *, purpose: str='general', conversation_state: Optional[dict]=None, pending_action: Optional[dict]=None` | no |

## `services/nova_action_ledger.py`

Lines: 220 | Functions/methods: 4 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 24 | `start_action_ledger_record` | `user_input: str, *, channel: str='cli', session_id: str='', input_source: str='typed', active_subject: str='', action_ledger_add_step_fn: Callable[..., None]` | no |
| 64 | `write_action_ledger_record` | `record: dict, *, action_ledger_dir: Path` | no |
| 101 | `finalize_action_ledger_record` | `record: dict, *, final_answer: str, planner_decision: str='', tool: str='', tool_args: Optional[dict]=None, tool_result: str='', grounded: Optional[bool]=None, intent: str='', active_subject: str='', continuation_used: Optional[bool]=None, reply_contract: str='', reply_outcome: Optional[dict]=None, routing_decision: Optional[dict]=None, reflection_payload: Optional[dict]=None, provider_name_from_tool_fn: Callable[[str], str], finalize_routing_decision_fn: Callable[..., Optional[dict]], action_ledger_add_step_fn: Callable[..., None], action_ledger_route_summary_fn: Callable[[object], str], write_action_ledger_record_fn: Callable[[dict], Optional[Path]], recent_action_ledger_records_fn: Callable[[int], list[dict]], maybe_log_self_reflection_fn: Callable[..., dict]` | no |
| 180 | `finalize_action_ledger_record_from_runtime` | `record: dict, *, final_answer: str, planner_decision: str='', tool: str='', tool_args: Optional[dict]=None, tool_result: str='', grounded: Optional[bool]=None, intent: str='', active_subject: str='', continuation_used: Optional[bool]=None, reply_contract: str='', reply_outcome: Optional[dict]=None, routing_decision: Optional[dict]=None, reflection_payload: Optional[dict]=None, runtime_scope: Optional[Mapping[str, Any]]=None, **explicit_hooks` | no |

## `services/nova_action_ledger_helpers.py`

Lines: 336 | Functions/methods: 13 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 18 | `action_ledger_add_step` | `record: dict \| None, stage: str, outcome: str, detail: str='', **data` | no |
| 76 | `action_ledger_route_summary` | `record_or_trace: object \| None` | no |
| 98 | `recent_action_ledger_records` | `action_ledger_dir: Path, limit: int=20` | no |
| 116 | `latest_action_ledger_record` | `action_ledger_dir: Path` | no |
| 129 | `action_history_reply` | `action_ledger_dir: Path, *, action_ledger_route_summary_fn` | no |
| 153 | `record_completed_tool_execution` | `record: dict` | no |
| 171 | `record_requested_tool_clarification` | `record: dict` | no |
| 193 | `detect_repeated_tool_intent_without_execution` | `action_ledger_dir: Path, *, records: list[dict] \| None=None, limit: int=20, tool_intent_labels: dict[str, str] \| None=None` | no |
| 243 | `top_repeated_correction_class` | `action_ledger_dir: Path, *, records: list[dict] \| None=None, limit: int=20` | no |
| 270 | `count_routing_overrides_recently` | `action_ledger_dir: Path, *, records: list[dict] \| None=None, limit: int=20` | no |
| 293 | `record_used_routing_override` | `record: dict \| None` | no |
| 307 | `routing_stable_recently` | `action_ledger_dir: Path, *, records: list[dict] \| None=None, limit: int=20, tool_intent_labels: dict[str, str] \| None=None` | no |
| 323 | `sample_intents_last` | `action_ledger_dir: Path, *, records: list[dict] \| None=None, count: int=5` | no |

## `services/nova_calendar_ingestion.py`

Lines: 516 | Functions/methods: 18 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `_unfold_ics_lines` | `text: str` | no |
| 29 | `_parse_dt_parts` | `token: str` | no |
| 39 | `_dt_from_ics` | `value: str, tzid: str=''` | yes |
| 76 | `_parse_rrule` | `rrule_text: str` | yes |
| 87 | `_expand_rrule` | `dtstart: datetime, dtend: datetime \| None, rrule_text: str, *, now: datetime \| None=None` | yes |
| 162 | `_sidecar_path` | `ics_path: Path` | yes |
| 167 | `load_sidecar_enrichment` | `ics_path: str \| Path` | yes |
| 184 | `save_sidecar_enrichment` | `ics_path: str \| Path, enrichment: dict[str, dict[str, Any]]` | yes |
| 194 | `_parse_ics_event` | `lines: list[str]` | no |
| 231 | `_dt_to_ics` | `dt: datetime \| None` | yes |
| 240 | `_fold_ics_line` | `line: str` | yes |
| 250 | `serialize_events_to_ics` | `events: list[dict[str, Any]], *, prodid: str='-//NOVA//Temporal Calendar//EN'` | yes |
| 311 | `parse_ics_text` | `ics_text: str, *, source: str='ics', enrichment: dict[str, dict[str, Any]] \| None=None, now: datetime \| None=None` | yes |
| 374 | `parse_ics_file` | `path: str \| Path, *, source: str='ics', now: datetime \| None=None` | yes |
| 393 | `normalize_calendar_event` | `record: dict[str, Any], *, source: str='ics'` | no |
| 401 | `read_calendar_events` | `ics_path: str \| Path` | yes |
| 446 | `write_calendar_event` | `ics_path: str \| Path, event: dict[str, Any]` | yes |
| 491 | `delete_calendar_event` | `ics_path: str \| Path, uid: str` | yes |

## `services/nova_cli_delivery.py`

Lines: 94 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `apply_cli_outcome_to_ledger` | `*, pending_action_ledger: dict \| None, outcome: dict, default_planner_decision: str, update_reply_fields: bool=False, coerce_grounded: bool=False` | no |
| 37 | `apply_cli_handled_outcome` | `*, pending_action_ledger: dict \| None, outcome: dict, default_planner_decision: str, session_turns: list[tuple[str, str]], print_fn: Callable[..., None], speak_chunked_fn: Callable[[str], None], say_done_fn: Callable[[str], None], update_reply_fields: bool=False, coerce_grounded: bool=False, clear_pending_action_fn: Callable[[], None] \| None=None, sync_pending_conversation_tracking_fn: Callable[[], None] \| None=None` | no |
| 74 | `emit_cli_reply_outcome` | `*, reply_text: str, planner_decision: str, session_turns: list[tuple[str, str]], print_fn: Callable[..., None], speak_chunked_fn: Callable[[str], None], say_done_fn: Callable[[str], None]` | no |

## `services/nova_cli_loop.py`

Lines: 415 | Functions/methods: 14 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 22 | `run_loop` | `tts, *, core: object` | no |
| 26 | `_ensure_whisper_loaded` | `` | no |
| 42 | `_background_warmup` | `` | no |
| 66 | `_set_pending_action` | `value: Optional[dict]` | no |
| 71 | `_set_conversation_state` | `value: Optional[dict]` | no |
| 76 | `_set_prefer_web_for_data_queries` | `value: bool` | no |
| 81 | `_set_language_mix_spanish_pct` | `value: int` | no |
| 86 | `_build_fallback_context_details` | `text: str, turns: list[tuple[str, str]]` | no |
| 98 | `_sync_pending_conversation_tracking` | `` | no |
| 108 | `_ensure_active_work_tree` | `seed_text: str` | no |
| 176 | `_trace` | `stage: str, outcome: str, detail: str='', **data` | no |
| 181 | `_apply_sequence_result` | `final: str, meta: dict` | no |
| 211 | `_flush_pending_action_ledger` | `` | no |
| 340 | `_normalize_sequence_reply` | `reply: str` | no |

## `services/nova_cli_sequence.py`

Lines: 113 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 6 | `execute_cli_sequence` | `*, execute_reply_sequence_fn: Callable[..., tuple[str, dict]], **kwargs` | no |
| 16 | `normalize_sequence_reply` | `reply: str, *, ensure_reply_fn: Callable[[str], str]` | no |
| 27 | `apply_sequence_result` | `*, final: str, meta: dict, pending_action_ledger: Optional[dict], merge_route_evidence_fn: Callable[[dict \| None, dict \| None], dict \| None], set_pending_action_fn: Callable[[Optional[dict]], None], session_state, apply_reply_runtime_effects_fn: Callable[..., dict], apply_reply_session_updates_fn: Callable[..., None], sync_pending_conversation_tracking_fn: Callable[[], None], trace_fn: Callable[..., None], emit_cli_reply_outcome_fn: Callable[..., dict], behavior_record_event_fn: Callable[..., None], extract_urls_fn: Callable[[str], list[str]], session_turns: list[tuple[str, str]] \| None=None, recent_tool_context: str, recent_web_urls: list[str]` | no |

## `services/nova_control_action_dispatcher.py`

Lines: 719 | Functions/methods: 9 | Classes: 1

Classes: `NovaControlActionDispatcher` (L225)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 134 | `autonomy_advisory_action_catalog` | `` | no |
| 144 | `autonomy_advisory_action_types` | `` | no |
| 148 | `is_autonomy_advisory_action` | `action_type: str` | no |
| 229 | `autonomy_advisory_action_catalog` | `` | no |
| 233 | `autonomy_advisory_action_types` | `` | no |
| 237 | `is_autonomy_advisory_action` | `action_type: str` | no |
| 241 | `dispatch_control_action_from_runtime` | `act: str, payload: dict, *, patch_control_service, updates_dir, runtime_scope, explicit_hooks: dict \| None=None` | no |
| 278 | `dispatch_control_action` | `act: str, payload: dict, *, patch_control_service, patch_status_payload_fn, patch_preview_summaries_fn, patch_action_readiness_payload_fn, patch_preview_target_fn, show_preview_fn, approve_preview_fn, reject_preview_fn, patch_apply_fn, updates_dir, refresh_status_action_fn, device_location_update_action_fn, device_location_clear_action_fn, patch_preview_list_action_fn, pulse_status_action_fn, update_now_dry_run_action_fn, update_now_confirm_action_fn, update_now_cancel_action_fn, runtime_artifact_show_action_fn, guard_control_action_fn, core_runtime_action_fn, autonomy_runtime_action_fn, test_session_run_action_fn, generated_pack_run_action_fn, generated_queue_run_next_action_fn, generated_queue_investigate_action_fn, patch_queue_run_next_action_fn, active_work_tree_run_next_action_fn, codegen_run_action_fn, leah_build_run_next_action_fn, real_world_task_create_action_fn, backend_command_list_action_fn, backend_command_run_action_fn, operator_prompt_action_fn, operator_outbox_respond_action_fn, operator_outbox_status_action_fn, session_delete_action_fn, policy_allow_action_fn, policy_remove_action_fn, web_mode_action_fn, memory_scope_set_action_fn, server_side_settings_action_fn, mission_settings_action_fn, search_provider_action_fn, search_provider_toggle_action_fn, search_endpoint_set_action_fn, search_provider_priority_set_action_fn, search_endpoint_probe_action_fn, chat_user_list_action_fn, chat_user_upsert_action_fn, chat_user_delete_action_fn, pipeline_note_append_action_fn, pipeline_create_action_fn, pipeline_start_action_fn, pipeline_pause_action_fn, pipeline_update_action_fn, pipeline_population_upsert_action_fn, pipeline_archive_action_fn, pipeline_query_preview_action_fn, pipeline_query_run_action_fn, self_check_action_fn, export_capabilities_snapshot_fn, export_ledger_summary_action_fn, export_diagnostics_bundle_action_fn, tail_log_action_fn, metrics_action_fn, inspect_environment_fn, format_report_fn, policy_audit_fn, record_control_action_event_fn, invalidate_control_status_cache_fn` | yes |
| 359 | `_patch_control_state` | `*, include_readiness: bool=True` | yes |

## `services/nova_fallback_flow.py`

Lines: 340 | Functions/methods: 13 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 14 | `_conversation_can_be_complete_without_task` | `packet` | no |
| 20 | `_reply_form` | `packet` | no |
| 26 | `_semantic_status` | `packet` | no |
| 33 | `_tool_evidence_context` | `tool, tool_result, *, limit=2500` | no |
| 43 | `_conversation_generation_context` | `fallback_context, packet` | no |
| 69 | `_remove_trailing_question` | `reply` | no |
| 77 | `_complete_thoughts` | `text` | no |
| 95 | `_is_question_thought` | `text` | no |
| 100 | `_shape_conversation_scoped_reply` | `reply` | no |
| 114 | `_render_intent_strategy_context` | `turn_intent, response_strategy` | no |
| 145 | `build_fallback_context` | `*, text, turns, build_fallback_context_details_fn, action_ledger_add_step, pending_action=None, semantic_tool_observation=None, planner_decision='', tool='', tool_result='', turn_intent=None, response_strategy=None` | no |
| 213 | `prepare_fallback_flow` | `*, text, turns, build_fallback_context_details_fn, action_ledger_add_step, pending_action=None, semantic_tool_observation=None, planner_decision='', tool='', tool_result='', turn_intent=None, response_strategy=None` | no |
| 248 | `finalize_llm_fallback_reply` | `*, text, raw_user_text, input_source, retrieved_context, language_mix_spanish_pct, ollama_chat_fn, mem_enabled_fn, mem_should_store_fn, mem_add_fn, strip_mem_leak_fn, behavior_record_event_fn, action_ledger_add_step, preprocess_reply_fn=None, ensure_reply_fn, intent_evidence_packet=None, fallback_context=None, leah_fast_chat: bool=False` | no |

## `services/nova_fulfillment_routing.py`

Lines: 60 | Functions/methods: 1 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 6 | `evaluate_fulfillment_route_viability` | `user_text: str, session: object, recent_turns: list[tuple[str, str]], *, pending_action: Optional[dict]=None, get_fulfillment_state_fn: Callable[[object], object \| None], semantic_observation: Optional[dict]=None` | no |

## `services/nova_grounded_self_report.py`

Lines: 470 | Functions/methods: 21 | Classes: 2

Classes: `TroubleItem` (L33), `NovaGroundedSelfReportService` (L39)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `_as_dict` | `value: Any` | no |
| 17 | `_as_list` | `value: Any` | no |
| 21 | `_truthy` | `value: Any` | no |
| 25 | `_text` | `value: Any, default: str='unknown'` | no |
| 42 | `build_payload` | `self, status_payload: dict[str, Any] \| None, work_trees_payload: dict[str, Any] \| None=None` | no |
| 124 | `render` | `self, mode: str, payload: dict[str, Any]` | no |
| 132 | `build_operator_attention` | `self, payload: dict[str, Any]` | no |
| 162 | `render_source_unavailable` | `self, mode: str, error: str` | no |
| 169 | `_trouble_items` | `self, *, status: dict[str, Any], release: dict[str, Any], memory: dict[str, Any], ollama: dict[str, Any], alerts: list[str], work_item: dict[str, Any]` | no |
| 259 | `_cleared_work_tree_source_keys` | `self, status: dict[str, Any]` | no |
| 283 | `_component_running` | `self, value: Any` | no |
| 295 | `_node_is_cleared` | `self, node: dict[str, Any], cleared_source_keys: set[str]` | no |
| 299 | `_filtered_open_task_count` | `self, payload: dict[str, Any], *, cleared_source_keys: set[str]` | no |
| 322 | `_first_open_work_item` | `self, payload: dict[str, Any], *, cleared_source_keys: set[str] \| None=None` | no |
| 357 | `_service_state` | `self, value: Any` | no |
| 369 | `_render_health` | `self, payload: dict[str, Any]` | no |
| 385 | `_render_trouble` | `self, payload: dict[str, Any]` | no |
| 403 | `_render_internals` | `self, payload: dict[str, Any]` | no |
| 441 | `_work_tree_line` | `self, payload: dict[str, Any]` | no |
| 458 | `_trouble_summary` | `self, payload: dict[str, Any]` | no |
| 463 | `_alert_line` | `self, payload: dict[str, Any]` | no |

## `services/nova_http_chat_runtime.py`

Lines: 191 | Functions/methods: 5 | Classes: 1

Classes: `NovaHttpChatRuntimeService` (L7)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_runtime_fn` | `runtime_scope: dict[str, object], name: str` | no |
| 14 | `process_chat` | `self, session_id: str, user_text: str, *, user_id: str='', core_module, session_state_manager, turn_finalization_service, http_chat_flow_module, append_session_turn_fn, generate_chat_reply_fn, invalidate_control_status_cache_fn` | no |
| 40 | `_ensure_active_work_tree` | `seed_text: str` | no |
| 112 | `_finalize_flow_reply` | `flow_result: dict` | no |
| 168 | `process_chat_from_runtime` | `self, session_id: str, user_text: str, *, user_id: str='', core_module, runtime_scope: dict[str, object]` | no |

## `services/nova_http_frontdoor.py`

Lines: 192 | Functions/methods: 10 | Classes: 1

Classes: `NovaHttpFrontdoorService` (L9)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `_runtime_fn` | `runtime_scope: dict[str, object], name: str` | no |
| 17 | `public_surface_renderers` | `*, runtime_console_renderer: Callable[[], str], leah_renderer: Callable[[], str]` | no |
| 28 | `static_asset_routes` | `*, control_css_path: Path, control_js_path: Path, leah_css_path: Path, leah_js_path: Path, leah_fx_js_path: Path` | no |
| 45 | `public_surface_renderers_from_runtime` | `runtime_scope: dict[str, object]` | no |
| 55 | `static_asset_routes_from_runtime` | `runtime_scope: dict[str, object]` | no |
| 68 | `route_contract` | `*, public_renderers: dict[str, Callable[[], str]], static_routes: dict[str, tuple[Path, str]]` | no |
| 104 | `route_contract_from_runtime` | `runtime_scope: dict[str, object]` | no |
| 111 | `startup_banner_lines` | `*, host: str, port: int, dev_mode_enabled: bool, control_token_enabled: bool, control_login_enabled: bool` | no |
| 138 | `parse_args` | `argv: list[str] \| None=None` | no |
| 145 | `serve_from_runtime` | `runtime_scope: dict[str, object], *, handler_class, argv: list[str] \| None=None, print_fn=print` | no |

## `services/nova_http_generated_work.py`

Lines: 90 | Functions/methods: 5 | Classes: 1

Classes: `NovaHttpGeneratedWorkService` (L6)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `_runtime_value` | `runtime_scope: Mapping[str, Any], name: str` | no |
| 14 | `run_generated_test_session_pack_from_runtime` | `cls, runtime_scope: Mapping[str, Any], limit: int=12, *, mode: str='recent'` | no |
| 32 | `run_next_generated_work_queue_item_from_runtime` | `cls, runtime_scope: Mapping[str, Any]` | no |
| 40 | `investigate_generated_work_queue_item_from_runtime` | `cls, runtime_scope: Mapping[str, Any], session_file: str='', *, session_id: str='', user_id: str='operator'` | no |
| 64 | `action_hooks_from_runtime` | `cls, runtime_scope: Mapping[str, Any]` | no |

## `services/nova_http_get_routes.py`

Lines: 255 | Functions/methods: 7 | Classes: 1

Classes: `NovaHttpGetRoutesService` (L7)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_runtime_fn` | `runtime_scope: dict[str, object], name: str` | no |
| 15 | `handle_basic_route_request` | `path: str, *, handler, public_renderers: dict[str, callable] \| None=None, static_routes: dict[str, tuple[object, str]] \| None=None, control_login_enabled_fn, control_page_gate_fn, render_control_login_html_fn=None, render_control_html_fn=None, health_payload_fn=None, ollama_api_up_fn=None, chat_model_fn=None, memory_enabled_fn=None, chat_login_enabled_fn=None, index_html: str='', control_login_html: str='', control_html: str='', control_css_path=None, control_js_path=None` | no |
| 80 | `handle_chat_history_request` | `path: str, *, handler, qs: dict, chat_login_auth_fn, normalize_user_id_fn, request_user_id_fn, assert_session_owner_fn, get_session_turns_fn, max_stored_turns_per_session: int` | no |
| 113 | `handle_basic_route_request_from_runtime` | `path: str, *, handler, runtime_scope: dict[str, object]` | no |
| 134 | `handle_chat_history_request_from_runtime` | `*, handler, qs: dict, runtime_scope: dict[str, object]` | no |
| 155 | `handle_control_api_request` | `path: str, *, handler=None, qs: dict, control_auth_fn, cached_control_status_payload_fn, cached_control_status_surfaces_payload_fn=None, control_policy_payload_fn, metrics_payload_fn, work_trees_payload_fn, session_summaries_fn, test_session_report_summaries_fn, available_test_session_definitions_fn, control_pipelines_payload_fn=None` | no |
| 221 | `handle_control_api_request_from_runtime` | `path: str, *, handler, qs: dict, runtime_scope: dict[str, object]` | no |

## `services/nova_http_pipeline_control.py`

Lines: 92 | Functions/methods: 3 | Classes: 1

Classes: `NovaHttpPipelineControlService` (L7)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_runtime_value` | `runtime_scope: Mapping[str, Any], name: str` | no |
| 15 | `payload_from_runtime` | `cls, runtime_scope: Mapping[str, Any], *, selected_pipeline_id: str=''` | no |
| 32 | `action_hooks_from_runtime` | `cls, runtime_scope: Mapping[str, Any]` | no |

## `services/nova_http_policy_search.py`

Lines: 86 | Functions/methods: 3 | Classes: 1

Classes: `NovaHttpPolicySearchService` (L8)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 12 | `_runtime_value` | `runtime_scope: Mapping[str, Any], name: str` | no |
| 16 | `action_hooks_from_runtime` | `cls, runtime_scope: Mapping[str, Any]` | no |
| 22 | `_probe` | `endpoint: str` | no |

## `services/nova_http_post_dispatch.py`

Lines: 87 | Functions/methods: 2 | Classes: 1

Classes: `NovaHttpPostDispatchService` (L9)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `handle_post_request` | `*, handler, path: str, qs: dict, basic_post_route_fn, handle_resume_request_fn, handle_chat_request_fn` | no |
| 54 | `handle_post_request_from_runtime` | `*, handler, path: str, qs: dict, runtime_scope: dict[str, object]` | no |

## `services/nova_http_post_routes.py`

Lines: 94 | Functions/methods: 3 | Classes: 1

Classes: `NovaHttpPostRoutesService` (L6)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `_runtime_fn` | `runtime_scope: dict[str, object], name: str` | no |
| 14 | `handle_basic_post_route` | `path: str, *, handler, qs: dict, payload: dict, control_login_action_fn, control_logout_action_fn, chat_login_action_fn, chat_logout_action_fn, chat_upload_action_fn=None, control_auth_fn, control_action_fn` | no |
| 65 | `handle_basic_post_route_from_runtime` | `path: str, *, handler, qs: dict, payload: dict, runtime_scope: dict[str, object]` | no |

## `services/nova_http_request_binding.py`

Lines: 209 | Functions/methods: 8 | Classes: 1

Classes: `NovaHttpRequestBindingService` (L6)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `_runtime_fn` | `runtime_scope: dict[str, object], name: str` | no |
| 14 | `_normalize_attachment_items` | `items` | no |
| 18 | `handle_resume_request` | `*, handler, qs: dict, payload: dict, chat_login_auth_fn, normalize_user_id_fn, request_user_id_fn, assert_session_owner_fn, resume_last_pending_turn_fn, invalidate_control_status_cache_fn` | no |
| 47 | `handle_chat_request` | `*, handler, qs: dict, payload: dict, chat_login_auth_fn, normalize_user_id_fn, request_user_id_fn, assert_session_owner_fn, process_chat_fn, invalidate_control_status_cache_fn, token_hex_fn, attachment_context_service=None, append_session_turn_fn=None` | no |
| 109 | `handle_upload_request` | `*, handler, qs: dict, payload: dict, chat_login_auth_fn, normalize_user_id_fn, request_user_id_fn, assert_session_owner_fn, token_hex_fn, attachment_context_service` | no |
| 143 | `handle_upload_request_from_runtime` | `*, handler, qs: dict, payload: dict, runtime_scope: dict[str, object]` | no |
| 164 | `handle_resume_request_from_runtime` | `*, handler, qs: dict, payload: dict, runtime_scope: dict[str, object]` | no |
| 185 | `handle_chat_request_from_runtime` | `*, handler, qs: dict, payload: dict, runtime_scope: dict[str, object]` | no |

## `services/nova_http_responses.py`

Lines: 125 | Functions/methods: 6 | Classes: 1

Classes: `NovaHttpResponsesService` (L7)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `json_response_with_headers` | `handler, code: int, payload: dict, *, record_http_response_fn, headers: dict[str, str] \| None=None` | no |
| 30 | `json_response` | `self, handler, code: int, payload: dict, *, record_http_response_fn` | no |
| 39 | `text_response` | `handler, code: int, text: str, *, record_http_response_fn` | no |
| 49 | `file_response` | `self, handler, code: int, path: Path, content_type: str, *, record_http_response_fn` | no |
| 76 | `emit_basic_route_result` | `self, handler, result: dict, *, record_http_response_fn` | no |
| 104 | `emit_post_result` | `self, handler, result: dict, *, record_http_response_fn` | no |

## `services/nova_http_transport.py`

Lines: 61 | Functions/methods: 2 | Classes: 1

Classes: `NovaHttpTransportService` (L4)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `handle_get_request` | `handler, *, parse_request_path_fn, basic_route_request_fn, chat_history_request_fn, control_api_request_fn, json_response_fn, response_service, record_http_response_fn` | no |
| 44 | `handle_post_request` | `handler, *, parse_request_path_fn, dispatch_post_request_fn, response_service, record_http_response_fn` | no |

## `services/nova_http_turn_finalization.py`

Lines: 225 | Functions/methods: 5 | Classes: 1

Classes: `NovaHttpTurnFinalizationService` (L14)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 7 | `session_reply_for_context` | `reply_text: str, *, planner_decision: str=''` | no |
| 18 | `finalize_http_reply` | `reply_text: str, *, session, session_id: str, user_input: str, ledger: dict, routing_decision: dict \| None, build_turn_reflection_fn, finalize_action_ledger_record_fn, finalize_routing_decision_fn, action_ledger_route_summary_fn, planner_decision: str='deterministic', tool: str='', tool_args: dict \| None=None, tool_result: str='', grounded: bool \| None=None, intent: str='', reply_contract: str='', reply_outcome: dict \| None=None` | no |
| 90 | `finalize_flow_reply` | `self, flow_result: dict, *, session, session_id: str, user_input: str, ledger: dict, routing_decision: dict \| None, append_session_turn_fn, build_turn_reflection_fn, finalize_action_ledger_record_fn, finalize_routing_decision_fn, action_ledger_route_summary_fn` | no |
| 132 | `finalize_reply_sequence_result` | `self, reply_text: str, *, session, session_id: str, user_input: str, ledger: dict, routing_decision: dict \| None, meta: dict \| None, append_session_turn_fn, behavior_record_event_fn, build_turn_reflection_fn, finalize_action_ledger_record_fn, finalize_routing_decision_fn, action_ledger_route_summary_fn` | no |
| 183 | `apply_reply_outcome` | `*, session, meta: dict \| None, behavior_record_event_fn` | no |

## `services/nova_intent_understanding.py`

Lines: 327 | Functions/methods: 7 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 66 | `classify_turn_intent` | `text, turns, *, live_ollama_calls_allowed_fn, chat_model_fn, ollama_base, requests_post_fn=None` | no |
| 123 | `select_response_strategy` | `intent, *, tool_data_available=False, data_confirms_claim=None` | no |
| 186 | `record_intent_outcome` | `text, intent, strategy, *, outcome='completed', mem_add_fn=None, ingest_signal_fn=None` | no |
| 230 | `_is_gap_outcome` | `strategy, outcome` | no |
| 237 | `_build_intent_gap_signal` | `domain, level, strat, outcome, user_text` | no |
| 272 | `_default_intent` | `` | no |
| 282 | `_parse_intent` | `raw` | no |

## `services/nova_inventory_labels.py`

Lines: 33 | Functions/methods: 1 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 32 | `shared_inventory_label` | `surface_id: str` | no |

## `services/nova_knowledge_packs.py`

Lines: 313 | Functions/methods: 12 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 9 | `tokenize` | `query: str` | no |
| 17 | `kb_active_pack` | `active_pack_file: Path` | no |
| 27 | `kb_set_active` | `name: Optional[str], *, knowledge_root: Path, packs_dir: Path, active_pack_file: Path` | no |
| 44 | `kb_list_packs` | `packs_dir: Path, *, kb_active_pack_fn: Callable[[], Optional[str]]` | no |
| 62 | `kb_add_zip` | `zip_path: str, pack_name: str, *, packs_dir: Path, safe_path_fn: Callable[[str], Path]` | no |
| 94 | `active_knowledge_root` | `packs_dir: Path, *, kb_active_pack_fn: Callable[[], Optional[str]]` | no |
| 108 | `kb_search` | `query: str, *, packs_dir: Path, kb_active_pack_fn: Callable[[], Optional[str]], tokenize_fn: Callable[[str], list[str]], max_files: int, max_chars: int` | no |
| 171 | `read_text_safely` | `path: Path` | no |
| 189 | `extract_key_lines` | `text: str, *, max_lines: int=2` | no |
| 203 | `topic_tokens` | `text: str` | no |
| 220 | `extract_matching_lines` | `text: str, tokens: list[str], *, max_lines: int=3` | no |
| 245 | `build_local_topic_digest_answer` | `query_text: str, *, packs_dir: Path, base_dir: Path, active_knowledge_root_fn: Callable[[], Optional[Path]], topic_tokens_fn: Callable[[str], list[str]], read_text_safely_fn: Callable[[Path], str], extract_matching_lines_fn: Callable[[str, list[str]], list[str]], max_files: int=4, max_points: int=10` | no |

## `services/nova_location_weather.py`

Lines: 589 | Functions/methods: 27 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 32 | `weather_source_host` | `*, policy_web_fn: Callable[[], dict]` | no |
| 41 | `weather_unavailable_message` | `` | no |
| 49 | `weather_response_style` | `*, policy_web_fn: Callable[[], dict]` | no |
| 59 | `format_weather_output` | `label: str, summary: str, *, weather_response_style_fn: Callable[[], str]` | no |
| 83 | `runtime_device_backend_provider` | `` | no |
| 110 | `coerce_bounded_float` | `value, *, minimum: float, maximum: float` | no |
| 122 | `coerce_optional_metric` | `value` | no |
| 134 | `normalize_source_timestamp` | `value` | no |
| 147 | `format_runtime_coords` | `lat: float, lon: float` | no |
| 151 | `distance_meters` | `lat1: float, lon1: float, lat2: float, lon2: float` | no |
| 164 | `location_label_for_coords` | `lat: float, lon: float` | no |
| 174 | `live_device_location_summary` | `*, runtime_device_location_payload_fn: Optional[Callable[[], dict]]=None, resolve_current_device_coords_fn: Optional[Callable[[], object]]=None, allow_stale: bool=False` | no |
| 212 | `device_location_status_payload` | `snapshot: Optional[dict], *, max_age_sec: float=DEVICE_LOCATION_MAX_AGE_SEC, runtime_device_backend_provider_fn: Callable[[], dict]` | no |
| 275 | `runtime_device_location_payload` | `*, device_location_file, max_age_sec: float=DEVICE_LOCATION_MAX_AGE_SEC, device_location_status_payload_fn: Callable[..., dict], runtime_device_backend_provider_fn: Callable[[], dict]` | no |
| 297 | `set_runtime_device_location` | `payload: dict, *, device_location_file, atomic_write_json_fn: Callable[[object, dict], None], runtime_device_location_payload_fn: Callable[..., dict]` | no |
| 330 | `clear_runtime_device_location` | `*, device_location_file, runtime_device_location_payload_fn: Callable[..., dict]` | no |
| 345 | `resolve_windows_device_coords` | `timeout_sec: float=8.0, *, runtime_device_backend_provider_fn: Callable[[], dict]` | no |
| 358 | `async _read_position` | `` | no |
| 396 | `resolve_current_device_coords` | `*, max_age_sec: float=DEVICE_LOCATION_MAX_AGE_SEC, runtime_device_location_payload_fn: Callable[..., dict], resolve_windows_device_coords_fn: Callable[..., Optional[dict]], set_runtime_device_location_fn: Callable[[dict], tuple[bool, str, dict]]` | no |
| 415 | `parse_lat_lon` | `text: str` | no |
| 429 | `coords_for_location_hint` | `location: str` | no |
| 443 | `coords_from_saved_location` | `*, read_core_state_fn: Callable[[object], dict], default_statefile` | no |
| 462 | `get_saved_location_text` | `*, read_core_state_fn: Callable[[object], dict], default_statefile` | no |
| 478 | `set_location_coords` | `value: str, *, set_core_state_fn: Callable[[object, str, object], None], default_statefile` | no |
| 495 | `get_weather_for_location` | `lat: float, lon: float` | no |
| 525 | `need_confirmed_location_message` | `` | no |
| 529 | `tool_weather` | `location: str, *, policy_tools_enabled_fn: Callable[[], dict], web_enabled_fn: Callable[[], bool], weather_source_host_fn: Callable[[], Optional[str]], weather_unavailable_message_fn: Callable[[], str], coords_for_location_hint_fn: Callable[[str], Optional[tuple[float, float]]], need_confirmed_location_message_fn: Callable[[], str], get_weather_for_location_fn: Callable[[float, float], str], format_weather_output_fn: Callable[[str, str], str]` | no |

## `services/nova_memory_events.py`

Lines: 56 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 9 | `append_memory_event` | `payload: dict, *, memory_events_log: Path` | no |
| 18 | `record_memory_event` | `action: str, status: str, *, user: Optional[str]=None, scope: str='private', backend: str='', kind: str='', source: str='', query: str='', reason: str='', error: str='', lane: str='', result_count: Optional[int]=None, duration_ms: Optional[int]=None, mode: str='', append_memory_event_fn` | no |

## `services/nova_memory_learning.py`

Lines: 1125 | Functions/methods: 31 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 14 | `mem_stats_payload` | `*, emit_event: bool=True, mem_enabled_fn: Callable[[], bool], memory_mod: Any, memory_runtime_user_fn: Callable[[], Optional[str]], mem_scope_fn: Callable[[], str], record_memory_event_fn: Callable[..., None]` | no |
| 68 | `mem_add` | `kind: str, source: str, text: str, *, mem_enabled_fn: Callable[[], bool], identity_memory_text_allowed_fn: Callable[[str, str], bool], record_memory_event_fn: Callable[..., None], mem_scope_fn: Callable[[], str], memory_should_keep_text_fn: Callable[[str], tuple[bool, str]], memory_kind_store_allowed_fn: Callable[[str], tuple[bool, str]] \| None=None, memory_write_user_fn: Callable[[], Optional[str]], memory_mod: Any, mem_min_score_fn: Callable[[], float], python_path: str, base_dir: Path` | no |
| 169 | `_normalize_duplicate_text` | `value: str` | no |
| 229 | `mem_recall` | `query: str, *, mem_enabled_fn: Callable[[], bool], memory_recall_plan_fn: Callable[..., Any] \| None=None, memory_runtime_user_fn: Callable[[], Optional[str]], memory_mod: Any, mem_context_top_k_fn: Callable[[], int], mem_min_score_fn: Callable[[], float], mem_exclude_sources_fn: Callable[[], list[str]], mem_recall_exclude_kinds_fn: Callable[[], list[str]] \| None=None, mem_scope_fn: Callable[[], str], format_memory_recall_hits_fn: Callable[[Any], str], record_memory_event_fn: Callable[..., None], python_path: str, base_dir: Path, purpose: str='general', conversation_state: Optional[dict]=None, pending_action: Optional[dict]=None` | no |
| 374 | `prefix_from_earlier_memory` | `reply_text: str` | no |
| 383 | `normalize_recent_learning_item` | `kind: str, text: str` | no |
| 407 | `mem_get_recent_learned` | `limit: int=5, *, mem_enabled_fn: Callable[[], bool], memory_mod: Any, memory_runtime_user_fn: Callable[[], Optional[str]], mem_scope_fn: Callable[[], str], normalize_recent_learning_item_fn: Callable[[str, str], str], load_learned_facts_fn: Callable[[], dict], memory_read_plan_fn: Callable[..., Any] \| None=None, record_memory_event_fn: Callable[..., None] \| None=None` | no |
| 522 | `mem_stats` | `*, mem_stats_payload_fn: Callable[..., dict], memory_mod: Any, python_path: str, base_dir: Path` | no |
| 541 | `mem_audit` | `query: str, *, memory_runtime_user_fn: Callable[[], Optional[str]], memory_mod: Any, mem_context_top_k_fn: Callable[[], int], mem_min_score_fn: Callable[[], float], mem_exclude_sources_fn: Callable[[], list[str]], mem_recall_exclude_kinds_fn: Callable[[], list[str]] \| None=None, mem_scope_fn: Callable[[], str], record_memory_event_fn: Callable[..., None], python_path: str, base_dir: Path` | no |
| 629 | `mem_remember_fact` | `text: str, *, mem_enabled_fn: Callable[[], bool], mem_add_fn: Callable[[str, str, str], None]` | no |
| 642 | `load_identity_profile` | `identity_file: Path` | no |
| 650 | `save_identity_profile` | `data: dict, *, memory_dir: Path, identity_file: Path` | no |
| 661 | `looks_invalid_person_token` | `value: str` | no |
| 682 | `sanitize_learned_facts` | `data: dict` | no |
| 696 | `_tmp_json_path` | `path: Path` | no |
| 703 | `load_json_dict_with_tmp_fallback` | `path: Path` | yes |
| 720 | `load_learned_facts` | `*, learned_facts_file: Path, save_learned_facts_fn: Callable[[dict], None]` | no |
| 733 | `save_learned_facts` | `data: dict, *, memory_dir: Path, learned_facts_file: Path` | no |
| 744 | `clean_fact_value` | `raw: str, max_words: int=4` | no |
| 753 | `title_name` | `value: str` | no |
| 760 | `learn_from_user_correction` | `text: str, *, load_learned_facts_fn: Callable[[], dict], get_learned_fact_fn: Callable[[str, str], str], save_learned_facts_fn: Callable[[dict], None], set_active_user_fn: Callable[[str], None], mem_enabled_fn: Callable[[], bool], mem_add_fn: Callable[[str, str, str], None]` | no |
| 882 | `get_learned_fact` | `key: str, default: str='', *, load_learned_facts_fn: Callable[[], dict]` | no |
| 888 | `speaker_matches_developer` | `*, get_active_user_fn: Callable[[], Optional[str]], get_learned_fact_fn: Callable[[str, str], str]` | no |
| 902 | `learn_self_identity_binding` | `text: str, *, set_active_user_fn: Callable[[str], None], get_learned_fact_fn: Callable[[str, str], str]` | no |
| 935 | `learn_contextual_self_facts` | `text: str, *, input_source: str='typed', speaker_matches_developer_fn: Callable[[], bool], extract_color_preferences_from_text_fn: Callable[[str], list[str]], mem_enabled_fn: Callable[[], bool], mem_add_fn: Callable[[str, str, str], None]` | no |
| 963 | `remember_name_origin` | `story_text: str, *, load_identity_profile_fn: Callable[[], dict], save_identity_profile_fn: Callable[[dict], None], mem_enabled_fn: Callable[[], bool], mem_add_fn: Callable[[str, str, str], None]` | no |
| 989 | `get_name_origin_story` | `*, load_identity_profile_fn: Callable[[], dict], mem_recall_fn: Callable[[str], str]` | no |
| 1016 | `identity_context_for_prompt` | `*, load_identity_profile_fn: Callable[[], dict], load_learned_facts_fn: Callable[[], dict]` | no |
| 1051 | `extract_name_origin_teach_text` | `text: str` | no |
| 1086 | `build_learning_context_details` | `query: str, *, kb_search_fn: Callable[[str], str], mem_recall_fn: Callable[[str], str]` | no |
| 1120 | `build_learning_context` | `query: str, *, build_learning_context_details_fn: Callable[[str], dict]` | no |

## `services/nova_mission.py`

Lines: 681 | Functions/methods: 24 | Classes: 1

Classes: `NovaMissionService` (L47)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 9 | `_as_dict` | `value: Any` | no |
| 13 | `_as_list` | `value: Any` | no |
| 17 | `_as_int` | `value: Any, default: int=0` | no |
| 24 | `_as_bool` | `value: Any, default: bool=False` | no |
| 37 | `_text` | `value: Any, limit: int=220` | no |
| 41 | `_normalize_action_names` | `values: Any` | no |
| 144 | `_mission_policy` | `policy_snapshot: dict \| None` | no |
| 161 | `execution_contract` | `cls, policy_snapshot: dict \| None` | no |
| 179 | `_blocker_codes` | `cls, values: Any` | no |
| 191 | `_blocker_records` | `cls, values: Any` | no |
| 213 | `active_work_evidence_current` | `cls, mission_snapshot: dict \| None` | no |
| 231 | `_base_evidence_pillars_current` | `cls, mission_snapshot: dict \| None` | no |
| 249 | `_mission_green_blocker_records` | `cls, mission_snapshot: dict \| None` | no |
| 257 | `_mission_green_blocker_pairs` | `cls, mission_snapshot: dict \| None` | no |
| 268 | `_release_drift_is_core_gate_only` | `cls, mission_snapshot: dict \| None` | no |
| 298 | `generated_queue_validation_allowed_during_hold` | `cls, mission_snapshot: dict \| None` | no |
| 324 | `active_work_tool_allowed_during_hold` | `cls, tool: str, mission_snapshot: dict \| None` | no |
| 347 | `hold_blocks_legacy_execution` | `cls, mission_snapshot: dict \| None` | no |
| 357 | `hold_blocks_action` | `cls, action_type: str, *, mission_snapshot: dict \| None, policy_snapshot: dict \| None=None, action_context: dict \| None=None` | no |
| 388 | `ingestion_suppresses_ambient_governance` | `cls, mission_snapshot: dict \| None, policy_snapshot: dict \| None=None` | no |
| 398 | `_release_stale_ready_count` | `work_tree_snapshot: dict \| None` | no |
| 420 | `_evaluate_truth_gate` | `cls, *, truth_evidence: dict \| None, queue: dict, policy: dict` | no |
| 434 | `append_history` | `cls, state: dict \| None, mission_snapshot: dict \| None, *, limit: int=48` | no |
| 474 | `build_snapshot` | `self, *, work_tree_snapshot: dict \| None, steward_posture: dict \| None, queue_pressure: dict \| None, runtime_guard_status: dict \| None, triage_hints: dict \| None, policy_snapshot: dict \| None, truth_evidence: dict \| None=None` | no |

## `services/nova_mission_owner_verdicts.py`

Lines: 407 | Functions/methods: 15 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `_as_dict` | `value: Any` | no |
| 12 | `_as_list` | `value: Any` | no |
| 16 | `_as_int` | `value: Any, default: int=0` | no |
| 23 | `_as_bool` | `value: Any, default: bool=False` | no |
| 36 | `_text` | `value: Any, limit: int=220` | no |
| 40 | `_regression_status_current` | `*, status_label: str, stale: bool` | no |
| 49 | `_validation_truth_fresh` | `validation: dict` | no |
| 66 | `_release_truth_current` | `*, release_truth: dict, release_status: dict` | no |
| 88 | `_blocker` | `owner: str, code: str, *, detail: str='', source: str=''` | no |
| 97 | `_verdict` | `owner: str, *, ready: bool, source: str, blockers: list[dict[str, Any]] \| None=None, summary: str='', evidence: dict[str, Any] \| None=None, blocks_green: bool=True` | no |
| 124 | `_normalize_owner_verdicts` | `values: Any` | no |
| 164 | `_owner_blockers` | `owner_verdicts: list[dict[str, Any]]` | no |
| 184 | `_legacy_blocker_codes` | `owner_verdicts: list[dict[str, Any]]` | no |
| 196 | `_core_gate_from_owner` | `evidence: dict` | no |
| 211 | `build_mission_truth_gate` | `*, truth_evidence: dict \| None, queue: dict, policy: dict` | no |

## `services/nova_ollama_chat.py`

Lines: 174 | Functions/methods: 6 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 49 | `_system_prompt` | `*, casual: bool, reply_form: str=''` | no |
| 66 | `_response_status` | `exc: Exception` | no |
| 74 | `_response_text` | `exc: Exception` | no |
| 86 | `_model_missing_error` | `exc: Exception, model: str` | no |
| 91 | `_chat_failure_reply` | `exc: Exception, model: str` | no |
| 105 | `ollama_chat` | `text: str, retrieved_context: str='', language_mix_spanish_pct: int=0, reply_form: str='', *, live_ollama_calls_allowed_fn: Callable[[], bool], ensure_ollama_fn: Callable[[], object], language_mix_instruction_fn: Callable[[int], str], chat_model_fn: Callable[[], str], requests_post_fn: Callable[..., object], ollama_base: str, ollama_req_timeout: float, warn_fn: Callable[[str], None], kill_ollama_fn: Callable[[], object], start_ollama_serve_detached_fn: Callable[[], object], sleep_fn: Callable[[float], None], env: dict[str, str]` | no |

## `services/nova_operational_identity.py`

Lines: 46 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 21 | `_clean` | `value: object, limit: int=220` | no |
| 26 | `operational_identity_context_for_prompt` | `*, load_capabilities_fn: Callable[[], dict]` | no |

## `services/nova_patching.py`

Lines: 1582 | Functions/methods: 48 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 37 | `snapshot_should_skip_relpath` | `rel: Path` | no |
| 53 | `parse_scoped_patch_payload` | `value: object` | no |
| 73 | `execute_scoped_patch_payload` | `payload: dict[str, object], *, base_dir: Path` | no |
| 152 | `log_patch` | `msg: str, *, updates_dir: Path, snapshots_dir: Path, patch_log: Path` | no |
| 162 | `read_patch_revision` | `patch_revision_file: Path` | no |
| 172 | `write_patch_revision` | `revision: int, source: str, *, updates_dir: Path, patch_revision_file: Path` | no |
| 182 | `snapshot_meta_path` | `snapshot_zip: Path` | no |
| 186 | `write_snapshot_meta` | `snapshot_zip: Path, base_revision: int, *, snapshot_meta_path_fn: Callable[[Path], Path]` | no |
| 195 | `read_snapshot_meta` | `snapshot_zip: Path, *, snapshot_meta_path_fn: Callable[[Path], Path]` | no |
| 205 | `snapshot_current` | `*, base_dir: Path, snapshots_dir: Path, write_snapshot_meta_fn: Callable[[Path, int], None], read_patch_revision_fn: Callable[[], int], log_patch_fn: Callable[[str], None]` | no |
| 229 | `overlay_change_candidates` | `zip_path: Path, *, base_dir: Path, patch_manifest_name: str` | no |
| 256 | `overlay_zip` | `zip_path: Path, *, base_dir: Path, patch_manifest_name: str` | no |
| 266 | `py_compile_check` | `*, python_path: str, base_dir: Path` | no |
| 280 | `last_nonempty_line` | `text: str` | no |
| 288 | `read_patch_manifest` | `zip_path: Path, *, patch_manifest_name: str` | no |
| 311 | `behavioral_check_command` | `*, base_dir: Path, python_path: str` | no |
| 318 | `behavioral_check` | `*, base_dir: Path, timeout_sec: Optional[int], policy_patch_fn: Callable[[], dict], behavioral_check_command_fn: Callable[[Path], list[str]]` | no |
| 390 | `read_patch_log_tail_line` | `*, patch_log: Path` | no |
| 399 | `preview_status_from_report` | `path: Path` | no |
| 409 | `preview_report_files` | `*, updates_dir: Path` | no |
| 416 | `preview_archive_dir` | `*, updates_dir: Path` | no |
| 420 | `resolve_preview_report_path` | `path_or_name: str, *, updates_dir: Path` | no |
| 427 | `_preview_report_text` | `path: Path` | no |
| 434 | `_preview_line_value` | `text: str, prefix: str` | no |
| 441 | `_preview_section_items` | `text: str, header: str, next_headers: tuple[str, ...]` | no |
| 465 | `preview_report_summary` | `path: Path` | no |
| 503 | `compact_preview_review_queue` | `previews: list[dict], *, limit: int=40` | no |
| 553 | `patch_preview_summaries` | `*, updates_dir: Path, read_approvals_fn: Callable[[], list[dict]], limit: int=40` | no |
| 604 | `patch_status_payload` | `*, base_dir: Path, updates_dir: Path, read_approvals_fn: Callable[[], list[dict]], read_patch_revision_fn: Callable[[], int], read_patch_log_tail_line_fn: Callable[[], str], policy_patch_fn: Callable[[], dict], patch_preview_summaries_fn: Callable[[int], list[dict]]` | no |
| 701 | `control_status_patch_fields` | `*, patch_summary: dict, patch_action_readiness: dict` | no |
| 737 | `archive_preview_report` | `path_or_name: str, *, updates_dir: Path` | no |
| 760 | `bulk_reject_orphaned_previews` | `*, updates_dir: Path, read_approvals_fn: Callable[[], list[dict]], record_approval_fn: Callable[..., bool], get_active_user_fn: Callable[[], Optional[str]], note: str=''` | no |
| 795 | `bulk_archive_superseded_previews` | `*, updates_dir: Path, read_approvals_fn: Callable[[], list[dict]]` | no |
| 824 | `patch_reject_message` | `reason: str, *, strict_manifest: bool, current_revision: int, incoming_revision: Optional[int], required_base_revision: Optional[int]` | no |
| 845 | `patch_apply` | `zip_path: str, *, force: bool=False, safe_path_fn: Callable[[str], Path], policy_patch_fn: Callable[[], dict], read_patch_revision_fn: Callable[[], int], read_patch_manifest_fn: Callable[[Path], tuple[Optional[dict], Optional[str]]], log_patch_fn: Callable[[str], None], patch_reject_message_fn: Callable[..., str], read_approvals_fn: Callable[[], list[dict]], patch_preview_fn: Callable[[str, bool], str], snapshot_current_fn: Callable[[], Path], overlay_zip_fn: Callable[[Path], int], py_compile_check_fn: Callable[[], Tuple[bool, str]], patch_rollback_fn: Callable[[Optional[str]], str], behavioral_check_fn: Callable[..., dict], write_patch_revision_fn: Callable[[int, str], None], patch_manifest_name: str, base_dir: Path` | no |
| 1091 | `patch_rollback` | `snapshot_zip: Optional[str]=None, *, base_dir: Path, snapshots_dir: Path, log_patch_fn: Callable[[str], None], read_snapshot_meta_fn: Callable[[Path], Optional[dict]], write_patch_revision_fn: Callable[[int, str], None], py_compile_check_fn: Callable[[], Tuple[bool, str]]` | no |
| 1135 | `patch_preview` | `zip_path: str, *, write_report: bool=False, safe_path_fn: Callable[[str], Path], base_dir: Path, updates_dir: Path, read_patch_manifest_fn: Callable[[Path], tuple[Optional[dict], Optional[str]]], read_patch_revision_fn: Callable[[], int]` | no |
| 1272 | `approvals_file` | `*, updates_dir: Path` | no |
| 1278 | `read_approvals` | `*, approvals_file_fn: Callable[[], Path]` | no |
| 1298 | `record_approval` | `preview_path: str, decision: str, *, user: Optional[str]=None, note: str='', approvals_file_fn: Callable[[], Path], get_active_user_fn: Callable[[], Optional[str]]` | no |
| 1322 | `list_previews` | `*, updates_dir: Path, read_approvals_fn: Callable[[], list[dict]]` | no |
| 1338 | `show_preview` | `path_or_name: str, *, updates_dir: Path` | no |
| 1351 | `approve_preview` | `path_or_name: str, *, note: str='', updates_dir: Path, record_approval_fn: Callable[..., bool], get_active_user_fn: Callable[[], Optional[str]]` | no |
| 1369 | `reject_preview` | `path_or_name: str, *, note: str='', updates_dir: Path, record_approval_fn: Callable[..., bool], get_active_user_fn: Callable[[], Optional[str]]` | no |
| 1387 | `interactive_preview_review` | `preview_path: str, *, record_approval_fn: Callable[..., bool], get_active_user_fn: Callable[[], Optional[str]]` | no |
| 1430 | `teach_propose_patch` | `description: str, *, updates_dir: Path, read_patch_revision_fn: Callable[[], int], patch_manifest_name: str, patch_preview_fn: Callable[..., str], interactive_patch_review_enabled_fn: Callable[[], bool], interactive_preview_review_fn: Callable[[str], str]` | no |
| 1500 | `teach_autoapply_proposal` | `zip_path: str, apply_live: bool=False, *, updates_dir: Path, base_dir: Path, patch_preview_fn: Callable[..., str], behavioral_check_fn: Callable[..., dict], patch_apply_fn: Callable[[str], str]` | no |
| 1580 | `interactive_patch_review_enabled` | `` | no |

## `services/nova_pipeline_tools.py`

Lines: 439 | Functions/methods: 10 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `parse_pipeline_params` | `tokens: list[str]` | no |
| 22 | `parse_pipeline_command` | `command_text: str` | no |
| 88 | `render_pipeline_help` | `` | no |
| 102 | `render_pipeline_list` | `summaries: list[dict[str, Any]]` | no |
| 116 | `render_pipeline_status` | `status: Mapping[str, Any]` | no |
| 158 | `render_pipeline_schema` | `probe: Mapping[str, Any]` | no |
| 205 | `render_pipeline_dictionary_search` | `result: Mapping[str, Any]` | no |
| 233 | `render_pipeline_report_plan` | `result: Mapping[str, Any]` | no |
| 327 | `render_pipeline_query_result` | `result: Mapping[str, Any], *, live_requested: bool=False` | no |
| 366 | `handle_pipeline_command` | `command_text: str, *, data_sources_root: Path, list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]], get_pipeline_status_fn: Callable[..., dict[str, Any]], get_pipeline_schema_probe_fn: Callable[..., dict[str, Any]], preview_pipeline_query_fn: Callable[..., dict[str, Any]], run_privileged_pipeline_query_fn: Callable[..., dict[str, Any]], search_pipeline_vendor_dictionary_fn: Callable[..., dict[str, Any]] \| None=None, plan_pipeline_report_fn: Callable[..., dict[str, Any]] \| None=None` | no |

## `services/nova_planner_contract.py`

Lines: 729 | Functions/methods: 24 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `_active_work_tree_id` | `*, pending_action: dict \| None, session` | no |
| 22 | `_active_work_identity` | `*, pending_action: dict \| None, session` | no |
| 31 | `_format_work_tree_reply` | `step: dict \| None` | no |
| 71 | `_parse_system_check_payload` | `tool_output: str` | no |
| 79 | `_system_check_rows` | `payload: dict` | no |
| 97 | `_render_system_check_reply` | `tool_output: str` | no |
| 126 | `build_planner_config` | `*, turns: list[tuple[str, str]], pending_action: dict \| None, prefer_web_for_data_queries: bool` | no |
| 139 | `_route_evidence` | `*, owner: str, action_type: str, tool: str=''` | no |
| 150 | `_actions_from_semantic_tool_intent` | `intent: dict \| None` | no |
| 162 | `_floatish` | `value, default: float=0.0` | no |
| 169 | `_heuristic_semantic_tool_intent` | `text: str` | yes |
| 231 | `_semantic_tool_intent_has_authority` | `intent: dict \| None` | no |
| 249 | `_classify_semantic_tool_actions` | `*, text: str, turns: list[tuple[str, str]], pending_action: dict \| None, turn_acts: list[str] \| None=None, core, trace: Callable[..., None], semantic_tool_observer_fn: Callable[[dict], None] \| None=None` | no |
| 280 | `_observe` | `status: str, payload: dict \| None=None` | no |
| 344 | `_handle_semantic_work_tree_action` | `*, action: dict, text: str, pending_action: dict \| None, session, core, trace: Callable[..., None], normalize_reply: Callable[[str], str], ensure_active_work_tree_fn: Callable[[str], str] \| None=None` | no |
| 437 | `_weather_location_available` | `core` | no |
| 447 | `_pending_weather_action` | `core` | no |
| 459 | `_intent_continues_same_tool_evidence` | `intent: dict \| None, tool: str` | no |
| 468 | `_session_has_tool_evidence` | `session, tool: str, *, semantic_intent: dict \| None=None` | no |
| 481 | `merge_route_evidence` | `routing_decision: dict \| None, meta: dict \| None` | no |
| 492 | `maybe_handle_planner_sequence` | `*, text: str, turns: list[tuple[str, str]], pending_action: dict \| None, turn_acts: list[str] \| None=None, prefer_web_for_data_queries: bool, session, core, trace: Callable[..., None], normalize_reply: Callable[[str], str], ensure_active_work_tree_fn: Callable[[str], str] \| None=None, work_tree_seed_source: str='', work_tree_seed_mode: str='', semantic_tool_observer_fn: Callable[[dict], None] \| None=None` | no |
| 512 | `_planner_elapsed_ms` | `` | no |
| 515 | `_record_tool_timing` | `tool_name: str, duration_ms: int` | no |
| 520 | `_return_with_timing` | `reply: str, meta: dict` | no |

## `services/nova_pulse.py`

Lines: 374 | Functions/methods: 10 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_count_definition_files` | `root: Path` | no |
| 15 | `_promotion_audit_summary` | `*, promotion_audit_log: Path, generated_definitions_dir: Path, promoted_definitions_dir: Path, pending_review_dir: Path, quarantine_dir: Path` | no |
| 64 | `_parse_log_timestamp` | `ts_text: str` | no |
| 71 | `_patch_activity_summary` | `*, patch_log: Path, read_patch_log_tail_line_fn: Callable[[], str], window_hours: int=24` | no |
| 113 | `_pulse_level` | `ollama_up: bool, routing_stable: bool, fallback_score: float, rollback_count: int` | no |
| 121 | `_pulse_mood` | `ollama_up: bool, routing_stable: bool, promoted_delta: int, fallback_score: float, rollback_count: int` | no |
| 133 | `build_pulse_payload` | `*, promotion_audit_log: Path, generated_definitions_dir: Path, promoted_definitions_dir: Path, pending_review_dir: Path, quarantine_dir: Path, behavior_metrics_file: Path, autonomy_maintenance_file: Path, pulse_snapshot_file: Path, patch_log: Path, load_json_file_fn: Callable[[Path, Any], Any], patch_status_payload_fn: Callable[[], dict], read_patch_log_tail_line_fn: Callable[[], str], ollama_api_up_fn: Callable[[], bool], mem_stats_payload_fn: Callable[..., dict], kidney_summary_fn: Callable[[], dict], safety_policy_fn: Callable[[], dict], latest_approved_update_zip_fn: Callable[[Optional[dict]], Optional[Path]], generated_work_queue_fn: Optional[Callable[[int], dict]]=None, memory_health_payload_fn: Optional[Callable[[], dict]]=None` | no |
| 292 | `write_pulse_snapshot` | `payload: dict, *, pulse_snapshot_file: Path` | no |
| 307 | `render_nova_pulse` | `payload: Optional[dict]=None, *, build_pulse_payload_fn: Optional[Callable[[], dict]]=None` | no |
| 366 | `tool_nova_pulse` | `*, build_pulse_payload_fn: Callable[[], dict], write_pulse_snapshot_fn: Callable[[dict], None], render_nova_pulse_fn: Callable[[dict], str]` | no |

## `services/nova_reflection_health.py`

Lines: 384 | Functions/methods: 13 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 9 | `_runtime_hook` | `runtime_scope: Optional[Mapping[str, object]], name: str, default=None` | no |
| 15 | `detect_repeated_tool_intent_without_execution` | `*, records: Optional[list[dict]]=None, limit: int=20, recent_action_ledger_records_fn: Callable[[int], list[dict]], tool_intent_labels: dict[str, str], record_requested_tool_clarification_fn: Callable[[dict], bool], record_completed_tool_execution_fn: Callable[[dict], bool]` | no |
| 66 | `top_repeated_correction_class` | `*, records: Optional[list[dict]]=None, limit: int=20, recent_action_ledger_records_fn: Callable[[int], list[dict]]` | no |
| 93 | `count_routing_overrides_recently` | `*, records: Optional[list[dict]]=None, limit: int=20, recent_action_ledger_records_fn: Callable[[int], list[dict]]` | no |
| 116 | `record_used_routing_override` | `record: Optional[dict]` | no |
| 130 | `routing_stable_recently` | `*, records: Optional[list[dict]]=None, limit: int=20, detect_repeated_tool_intent_without_execution_fn: Callable[..., dict]` | no |
| 140 | `sample_intents_last` | `*, records: Optional[list[dict]]=None, count: int=5, recent_action_ledger_records_fn: Callable[[int], list[dict]]` | no |
| 156 | `append_self_reflection` | `payload: dict, *, self_reflection_log: Path` | no |
| 165 | `append_health_snapshot` | `payload: dict, *, health_log: Path` | no |
| 174 | `record_health_snapshot` | `*, session_id: str, reflection: Optional[dict], session_end: bool=False, append_health_snapshot_fn: Callable[[dict], None]` | no |
| 196 | `recent_self_reflection_rows` | `*, limit: int=3, self_reflection_log: Path` | no |
| 216 | `maybe_log_self_reflection` | `*, limit: int=20, every: int=5, records: Optional[list[dict]]=None, total_records: Optional[int]=None, extra_payload: Optional[dict]=None, runtime_scope: Optional[Mapping[str, object]]=None, recent_action_ledger_records_fn: Optional[Callable[[int], list[dict]]]=None, detect_repeated_tool_intent_without_execution_fn: Optional[Callable[..., dict]]=None, top_repeated_correction_class_fn: Optional[Callable[..., dict]]=None, routing_stable_recently_fn: Optional[Callable[..., bool]]=None, count_routing_overrides_recently_fn: Optional[Callable[..., int]]=None, record_used_routing_override_fn: Optional[Callable[[Optional[dict]], bool]]=None, sample_intents_last_fn: Optional[Callable[..., list[str]]]=None, provider_name_from_tool_fn: Optional[Callable[[str], str]]=None, append_self_reflection_fn: Optional[Callable[[dict], None]]=None, record_health_snapshot_fn: Optional[Callable[..., None]]=None, behavior_metrics_update_from_reflection_fn: Optional[Callable[[dict, int], None]]=None` | no |
| 331 | `build_turn_reflection` | `session_state, *, entry_point: str, session_id: str, current_decision: dict, runtime_scope: Optional[Mapping[str, object]]=None, subconscious_service=None, supervisor=None, recent_action_ledger_records_fn: Optional[Callable[[int], list[dict]]]=None, recent_self_reflection_rows_fn: Optional[Callable[[int], list[dict]]]=None, build_training_backlog_summary_fn: Optional[Callable[[dict], dict \| None]]=None, build_robust_weakness_summary_fn: Optional[Callable[[object], dict \| None]]=None` | no |

## `services/nova_reply_context_contract.py`

Lines: 4 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `services/nova_reply_runtime.py`

Lines: 39 | Functions/methods: 1 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 6 | `apply_reply_runtime_effects` | `*, planner_decision: str, tool: str, tool_result: str, final_reply: str='', active_state: Optional[dict]=None, behavior_record_event_fn: Callable[[str], None], extract_urls_fn: Callable[[str], list[str]]` | no |

## `services/nova_reply_sequence.py`

Lines: 385 | Functions/methods: 12 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_runtime_fn` | `runtime_scope: dict[str, object], name: str` | no |
| 15 | `execute_reply_sequence_from_runtime` | `*, turns: list[tuple[str, str]], text: str, pending_action: dict \| None, turn_acts: list[str] \| None=None, prefer_web_for_data_queries: bool, language_mix_spanish_pct: int, session, trace: Callable[..., None], normalize_reply: Callable[[str], str], ensure_reply: Callable[[str], str], core, runtime_scope: dict[str, object], stop_before_llm_fallback: bool=False, ensure_active_work_tree_fn: Callable[[str], str] \| None=None, work_tree_seed_source: str='', work_tree_seed_mode: str='', input_source: str='typed'` | no |
| 57 | `execute_http_reply_sequence_from_runtime` | `*, turns: list[tuple[str, str]], text: str, ledger_record: dict \| None, pending_action: dict \| None, prefer_web_for_data_queries: bool, language_mix_spanish_pct: int, session, ensure_reply: Callable[[str], str], core, runtime_scope: dict[str, object], ensure_active_work_tree_fn: Callable[[str], str] \| None=None` | no |
| 71 | `_trace` | `stage: str, outcome: str, detail: str='', **data` | no |
| 74 | `_normalize_reply` | `reply_text: str` | no |
| 101 | `execute_reply_sequence` | `*, turns: list[tuple[str, str]], text: str, pending_action: dict \| None, turn_acts: list[str] \| None=None, prefer_web_for_data_queries: bool, language_mix_spanish_pct: int, session, trace: Callable[..., None], normalize_reply: Callable[[str], str], ensure_reply: Callable[[str], str], core, ensure_active_work_tree_fn: Callable[[str], str] \| None=None, work_tree_seed_source: str='', work_tree_seed_mode: str='', input_source: str='typed', stop_before_llm_fallback: bool=False` | no |
| 128 | `_merge_timing` | `meta: dict \| None` | no |
| 136 | `_complete_return` | `reply: str, meta: dict, *, record_high_latency: bool` | no |
| 156 | `_timed_return` | `reply: str, meta: dict` | no |
| 159 | `_break_fallback_loop` | `reply_text: str, meta: dict` | no |
| 163 | `_build_fallback_context_details` | `user_text: str, session_turns: list[tuple[str, str]]` | no |
| 211 | `_observe_semantic_tool` | `payload: dict` | no |

## `services/nova_root_inventory.py`

Lines: 652 | Functions/methods: 7 | Classes: 1

Classes: `SourceRoot` (L12)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 364 | `source_root_ids` | `` | no |
| 368 | `_repo_root` | `root: Path \| None=None` | no |
| 372 | `_clean_set` | `values: Iterable[str] \| None` | no |
| 376 | `_default_wiring_surface_ids` | `` | no |
| 385 | `_relative_code_files` | `repo_root: Path` | no |
| 413 | `_coverage_root_for_path` | `path: str` | no |
| 583 | `build_source_root_inventory_payload` | `root: Path \| None=None, *, wiring_surface_ids: Iterable[str] \| None=None` | no |

## `services/nova_route_probing.py`

Lines: 127 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 6 | `evaluate_deterministic_route_viability` | `user_text: str, session: object, recent_turns: list[tuple[str, str]], *, pending_action: Optional[dict]=None, evaluate_rules_fn: Callable[..., dict], supervisor_result_has_route_fn: Callable[[Optional[dict]], bool], planner_decide_turn_fn: Optional[Callable[..., list[dict]]]=None` | no |
| 96 | `build_probe_turn_routes` | `user_text: str, deterministic: dict, fulfillment: dict` | no |

## `services/nova_routing_helpers.py`

Lines: 62 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 7 | `strip_invocation_prefix` | `text: str` | yes |
| 34 | `resolve_research_provider` | `candidates: list[str], *, default_tool: str='web_research', get_search_provider_priority_fn: Callable[[], list[str]], provider_name_from_tool_fn: Callable[[str], str]` | no |

## `services/nova_routing_support.py`

Lines: 490 | Functions/methods: 14 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 122 | `intent_trace_preview` | `text: str, *, limit: int=120` | no |
| 129 | `supervisor_result_has_route` | `rule_result: Optional[dict]` | no |
| 134 | `supervisor_candidate_trace` | `rule_result: Optional[dict]` | no |
| 156 | `supervisor_phase_record` | `rule_result: Optional[dict], *, phase: str, supervisor_result_has_route_fn: Callable[[Optional[dict]], bool], supervisor_candidate_trace_fn: Callable[[Optional[dict]], list[dict]]` | no |
| 175 | `build_routing_decision` | `text: str, *, entry_point: str, intent_result: Optional[dict]=None, handle_result: Optional[dict]=None, final_owner: str='pending', reply_contract: str='', reply_outcome: Optional[dict]=None, turn_acts: Optional[list[str]]=None, intent_trace_preview_fn: Callable[[str], str] \| None=None, supervisor_phase_record_fn: Callable[..., dict] \| None=None, runtime_scope: Optional[dict[str, object]]=None` | no |
| 217 | `finalize_routing_decision` | `routing_decision: Optional[dict], *, planner_decision: str='', reply_contract: str='', reply_outcome: Optional[dict]=None, turn_acts: Optional[list[str]]=None` | no |
| 260 | `llm_classify_routing_intent` | `text: str, turns: Optional[list[tuple[str, str]]]=None, *, pending_action: Optional[dict]=None, return_none_payload: bool=False, live_ollama_calls_allowed_fn: Callable[[], bool], chat_model_fn: Callable[[], str], routing_model_fn: Optional[Callable[[], str]]=None, ollama_base: str, get_saved_location_text_fn: Callable[[], str], requests_post_fn: Callable[..., object] \| None=None` | no |
| 339 | `_coerce_evidence_need` | `value: object, *, default: str='unknown'` | no |
| 346 | `_coerce_answer_target` | `value: object, *, default: str='unknown'` | no |
| 353 | `_coerce_confidence` | `value: object` | no |
| 361 | `_coerce_none_payload` | `parsed: dict[str, object], *, reason: str=''` | no |
| 379 | `_parse_intent_payload` | `raw: str` | no |
| 402 | `_first_structured_url` | `text: str` | no |
| 407 | `_coerce_tool_intent_payload` | `content: str, *, user_text: str, return_none_payload: bool=False` | no |

## `services/nova_runtime_context.py`

Lines: 128 | Functions/methods: 9 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `set_active_user` | `name: Optional[str]` | no |
| 20 | `get_active_user` | `` | no |
| 25 | `resolve_base_dir` | `` | no |
| 31 | `_truthy` | `value: object` | no |
| 35 | `_path_from_env` | `value: str, *, base_dir: Path` | no |
| 40 | `_looks_like_test_process` | `argv=None` | no |
| 46 | `runtime_scope_name` | `environ=None, argv=None` | no |
| 51 | `resolve_runtime_dir` | `base_dir: Path \| None=None, environ=None, argv=None` | yes |
| 74 | `resolve_python_executable` | `base_dir: Path` | no |

## `services/nova_runtime_hooks.py`

Lines: 33 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 6 | `resolve_runtime_hooks` | `hook_map: Mapping[str, str], *, explicit_hooks: Mapping[str, Any], runtime_scope: Optional[Mapping[str, Any]]=None, factories: Optional[Mapping[str, Callable[[Mapping[str, Any]], Any]]]=None` | no |
| 27 | `_noop` | `*a, **k` | no |

## `services/nova_scheduler.py`

Lines: 80 | Functions/methods: 7 | Classes: 1

Classes: `NovaSchedulerService` (L23)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 7 | `_load_apscheduler_backend` | `` | no |
| 33 | `_build_scheduler` | `self` | no |
| 51 | `scheduler` | `self` | no |
| 56 | `start` | `self` | no |
| 63 | `shutdown` | `self, wait: bool=True` | no |
| 69 | `add_job` | `self, func: Callable[..., Any], trigger: str, **kwargs: Any` | no |
| 75 | `job_ids` | `self` | no |

## `services/nova_search_endpoint.py`

Lines: 138 | Functions/methods: 6 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `normalize_search_endpoint` | `endpoint: str` | no |
| 24 | `search_endpoint_candidates` | `endpoint: str` | no |
| 28 | `_append` | `value: str` | no |
| 56 | `is_local_search_endpoint` | `endpoint: str` | no |
| 61 | `stable_probe_error` | `exc: Exception \| str` | no |
| 67 | `probe_search_endpoint` | `endpoint: str='', *, timeout: float=2.5, persist_repair: bool=False, candidate_limit: int \| None=None, get_search_endpoint_fn: Callable[[], str], auto_repair_search_endpoint_fn: Callable[[str], str], requests_get_fn: Callable[..., object]` | no |

## `services/nova_self_evidence_reply.py`

Lines: 152 | Functions/methods: 6 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_clean` | `value: object, *, limit: int=260` | no |
| 18 | `_semantic_evidence_need` | `packet: dict[str, Any] \| None` | no |
| 37 | `_identity_facts` | `context: str` | no |
| 54 | `_identity_authority` | `context: str` | no |
| 62 | `_operational_parts` | `context: str` | no |
| 82 | `maybe_build_self_evidence_reply` | `*, fallback_context: dict[str, Any] \| None, intent_evidence_packet: dict[str, Any] \| None` | no |

## `services/nova_self_status.py`

Lines: 294 | Functions/methods: 9 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `_compact_text` | `value: Any, max_chars: int=220` | no |
| 20 | `_event` | `kind: str, severity: str, title: str, detail: str='', *, source: str='', command: str=''` | no |
| 31 | `read_recent_ops_events` | `path: Path, *, limit: int=40` | no |
| 50 | `_run_git` | `repo_root: Path, args: list[str], *, subprocess_run=subprocess.run` | no |
| 64 | `build_repo_change_snapshot` | `repo_root: Path, *, subprocess_run=subprocess.run, max_files: int=20` | no |
| 121 | `_ops_status_event` | `row: dict` | no |
| 139 | `_repo_change_event` | `change_snapshot: dict, *, last_regression: str, last_regression_stale: bool` | no |
| 161 | `build_self_status_payload` | `*, pulse_payload: dict \| None=None, recent_ops_events: list[dict] \| None=None, repo_change_snapshot: dict \| None=None` | no |
| 270 | `render_self_status` | `payload: dict \| None=None` | no |

## `services/nova_service_builders.py`

Lines: 34 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `build_policy_manager` | `policy_path: Path, policy_audit_log: Path, base_dir: Path` | no |
| 15 | `build_identity_memory_service` | `*, normalize_text_fn: Callable[[str], str]` | no |
| 24 | `build_fulfillment_flow_service` | `*, probe_turn_routes_fn: Callable[..., Any], update_subconscious_state_fn: Callable[..., Any], session_state_service: type` | no |

## `services/nova_session_state.py`

Lines: 33 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 4 | `_last_tool_evidence_state` | `payload: dict` | no |
| 24 | `apply_reply_session_updates` | `session, *, meta: dict \| None` | no |

## `services/nova_temporal_service.py`

Lines: 318 | Functions/methods: 20 | Classes: 3

Classes: `TemporalEvent` (L76), `TemporalPressure` (L123), `NovaTemporalService` (L248)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `_utc_now` | `` | no |
| 14 | `_clamp` | `value: float, minimum: float=0.0, maximum: float=1.0` | no |
| 18 | `_normalize_signal` | `value: Any` | no |
| 30 | `_serialize_dt` | `value: datetime \| None` | no |
| 38 | `_parse_datetime` | `value: Any` | no |
| 64 | `_confidence_to_score` | `label: str` | no |
| 90 | `from_payload` | `cls, payload: dict[str, Any], *, source: str='ics'` | no |
| 106 | `to_dict` | `self` | no |
| 140 | `_proximity_band_and_score` | `days_until_start: float \| None` | no |
| 158 | `_choose_output_path` | `final_score: float, proximity_band: str` | no |
| 166 | `from_event` | `cls, event: TemporalEvent, *, now: datetime \| None=None` | no |
| 229 | `to_dict` | `self` | no |
| 251 | `__init__` | `self, *, work_tree_threshold: float=75.0, outbox_threshold: float=45.0` | no |
| 255 | `assess` | `self, event: TemporalEvent, *, now: datetime \| None=None` | no |
| 268 | `assess_many` | `self, events: list[TemporalEvent], *, now: datetime \| None=None` | no |
| 271 | `route_pressure` | `self, pressure: TemporalPressure` | no |
| 278 | `build_work_tree_item` | `self, pressure: TemporalPressure` | no |
| 291 | `build_outbox_message` | `self, pressure: TemporalPressure` | no |
| 303 | `build_silent_job` | `self, pressure: TemporalPressure` | no |
| 316 | `build_temporal_pressure` | `event_like: dict[str, Any] \| TemporalEvent, *, now: datetime \| None=None` | no |

## `services/nova_tool_dispatch.py`

Lines: 198 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 112 | `_planned_tool_map` | `runtime_scope: Mapping[str, Any]` | no |
| 126 | `execute_planned_action` | `tool: str, args=None, *, resolve_current_device_coords_fn: Callable[[], Optional[tuple[float, float]]], tool_weather_fn: Callable[[str], str], get_saved_location_text_fn: Callable[[], str], coords_from_saved_location_fn: Callable[[], Optional[tuple[float, float]]], need_confirmed_location_message_fn: Callable[[], str], set_location_coords_fn: Callable[[str], str], tool_map: dict[str, Callable[..., object]]` | no |
| 180 | `execute_planned_action_from_runtime` | `tool: str, args=None, *, runtime_scope: Optional[Mapping[str, Any]]=None, **explicit_hooks` | no |

## `services/nova_tool_policy.py`

Lines: 179 | Functions/methods: 6 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `research_handlers` | `*, tool_web_fetch_fn: Callable[..., object], tool_web_search_fn: Callable[..., object], tool_web_research_fn: Callable[..., object], tool_web_gather_fn: Callable[..., object], tool_wikipedia_lookup_fn: Callable[..., object], tool_stackexchange_search_fn: Callable[..., object]` | no |
| 32 | `execute_research_action` | `action: str, value: str, *, execute_registered_tool_fn: Callable[..., str], research_handlers_fn: Callable[[], dict[str, object]]` | no |
| 46 | `patch_handlers` | `*, patch_preview_fn: Callable[..., object], list_previews_fn: Callable[[], object], show_preview_fn: Callable[..., object], approve_preview_fn: Callable[..., object], reject_preview_fn: Callable[..., object], patch_apply_fn: Callable[..., object], patch_rollback_fn: Callable[..., object]` | no |
| 67 | `execute_patch_action` | `action: str, value: str='', *, force: bool=False, is_admin: bool=True, execute_registered_tool_fn: Callable[..., str], patch_handlers_fn: Callable[[], dict[str, object]]` | no |
| 84 | `web_allowlist_message` | `context: str='', *, policy_web_fn: Callable[[], dict]` | no |
| 112 | `web_fetch` | `url: str, save_dir: Path, *, web_enabled_fn: Callable[[], bool], policy_web_fn: Callable[[], dict], host_allowed_fn: Callable[[str, list[str]], bool]` | no |

## `services/nova_turn_intent_trace.py`

Lines: 241 | Functions/methods: 10 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `_compact_text` | `value: object, *, limit: int=700` | no |
| 20 | `_normal_turns` | `turns: object` | no |
| 34 | `_previous_assistant_turn` | `turns: list[tuple[str, str]], current_text: str` | no |
| 46 | `_last_assistant_repeats_earlier_assistant` | `turns: list[tuple[str, str]], current_text: str` | no |
| 62 | `_safe_confidence` | `payload: dict[str, Any]` | no |
| 70 | `_semantic_tool_observation` | `payload: object` | no |
| 96 | `_semantic_conversation_scope` | `semantic_observation: dict[str, Any]` | no |
| 104 | `build_turn_intent_evidence_packet` | `*, text: str, turns: list[tuple[str, str]] \| None, pending_action: dict \| None=None, fallback_context: dict \| None=None, semantic_tool_observation: dict \| None=None, planner_decision: str='', tool: str='', tool_result: str=''` | no |
| 189 | `render_turn_intent_evidence_packet` | `packet: dict[str, Any] \| None` | no |
| 236 | `attach_turn_intent_evidence_packet` | `retrieved_context: str, packet: dict[str, Any] \| None` | no |

## `services/nova_update_now.py`

Lines: 152 | Functions/methods: 10 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 12 | `read_update_now_pending` | `pending_file: Path, *, load_json_file_fn: Callable[[Path, object], object]` | no |
| 16 | `write_update_now_pending` | `pending_file: Path, payload: dict` | no |
| 24 | `clear_update_now_pending` | `pending_file: Path` | no |
| 32 | `update_now_pending_payload` | `pending_file: Path, *, read_pending_fn: Callable[[], dict]` | no |
| 46 | `build_update_now_token` | `zip_path: Path` | no |
| 51 | `extract_preview_status` | `preview_text: str` | no |
| 56 | `extract_preview_zip` | `preview_text: str` | no |
| 61 | `tool_update_now` | `*, patch_status_payload_fn: Callable[[], dict], latest_approved_update_zip_fn: Callable[[Optional[dict]], Optional[Path]], patch_preview_fn: Callable[..., str], clear_pending_fn: Callable[[], None], write_pending_fn: Callable[[dict], None], build_token_fn: Callable[[Path], str]=build_update_now_token` | no |
| 106 | `tool_update_now_confirm` | `token: str='', *, read_pending_fn: Callable[[], dict], clear_pending_fn: Callable[[], None], patch_status_payload_fn: Callable[[], dict], latest_approved_update_zip_fn: Callable[[Optional[dict]], Optional[Path]], execute_patch_action_fn: Callable[..., str]` | no |
| 147 | `tool_update_now_cancel` | `*, read_pending_fn: Callable[[], dict], clear_pending_fn: Callable[[], None]` | no |

## `services/nova_vision_runtime.py`

Lines: 112 | Functions/methods: 5 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 19 | `_module_available` | `import_name: str` | no |
| 26 | `_available_models` | `ollama_health: dict[str, Any]` | no |
| 35 | `vision_model_from_policy` | `policy: dict[str, Any] \| None=None` | no |
| 41 | `vision_model_from_policy_file` | `base_dir: str \| Path \| None=None` | no |
| 51 | `vision_status_payload` | `*, policy: dict[str, Any] \| None=None, ollama_health: dict[str, Any] \| None=None` | no |

## `services/nova_voice_runtime.py`

Lines: 541 | Functions/methods: 24 | Classes: 1

Classes: `SubprocessTTS` (L469)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `_as_int` | `value: Any` | no |
| 20 | `_is_virtual_input_name` | `name: str` | no |
| 35 | `_is_generic_wrapper_input_name` | `name: str` | no |
| 46 | `_input_device_score` | `item: tuple[int, dict]` | no |
| 66 | `_enumerate_input_devices` | `sd` | no |
| 80 | `_default_input_index` | `sd` | no |
| 90 | `_resolve_input_device` | `sd, preferred: Any` | no |
| 122 | `_ordered_input_candidates` | `sd, preferred: Any, runtime_scope: MutableMapping[str, Any]` | no |
| 131 | `_push` | `idx: int` | no |
| 164 | `_chunk_peak_abs` | `chunk: Any` | no |
| 190 | `_concat_audio_chunks` | `chunks: list[Any], runtime_scope: MutableMapping[str, Any]` | no |
| 204 | `_downmix_to_mono` | `audio: Any, runtime_scope: MutableMapping[str, Any]` | yes |
| 228 | `_segments_indicate_no_usable_speech` | `segment_list: list[Any]` | no |
| 249 | `ensure_voice_deps` | `runtime_scope: MutableMapping[str, Any], *, import_voice_modules_fn: Callable[[], tuple[object, object, object]] \| None=None` | yes |
| 290 | `voice_status_payload` | `runtime_scope: MutableMapping[str, Any]` | no |
| 331 | `record_seconds` | `seconds: int=3, *, ensure_voice_deps_fn: Callable[[], bool], runtime_scope: MutableMapping[str, Any], sample_rate: int, channels: int, preferred_input_device: Any='', print_fn: Callable[..., None]=print` | no |
| 353 | `_apply_selected` | `idx: int, dev: dict` | no |
| 442 | `transcribe` | `model, audio_int16, *, ensure_voice_deps_fn: Callable[[], bool], runtime_scope: MutableMapping[str, Any], sample_rate: int` | no |
| 472 | `__init__` | `self, python_exe: str, oneshot_script, timeout_sec: float=25.0, *, warn_fn: Callable[[str], None]` | no |
| 488 | `start` | `self` | no |
| 491 | `stop` | `self` | no |
| 495 | `say` | `self, text: str` | no |
| 499 | `_run` | `self` | no |
| 527 | `speak_chunked` | `tts: SubprocessTTS, text: str, max_len: int=220` | no |

## `services/nova_web_contracts.py`

Lines: 3 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `services/nova_web_tools.py`

Lines: 1183 | Functions/methods: 35 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 16 | `_provider_request_headers` | `token: str=''` | no |
| 27 | `_clean_html_text` | `value: str` | no |
| 32 | `_prioritize_research_domains` | `domains: list[str], query_tokens: list[str]` | no |
| 35 | `_domain_score` | `domain: str` | no |
| 53 | `_query_seed_urls_for_domain` | `domain: str, query_tokens: list[str], max_candidates: int=12` | no |
| 75 | `_add` | `url: str` | no |
| 110 | `scan_candidate_urls_for_query` | `urls: list[str], query_tokens: list[str], max_pages: int, min_score: float=3.0, *, requests_get_fn: Callable[..., Any], expand_research_terms_fn: Callable[[list[str]], list[str]], extract_text_from_html_content_fn: Callable[[str, int], str], score_research_hit_fn: Callable[..., float]` | no |
| 123 | `_url_candidate_score` | `u: str` | no |
| 171 | `extract_urls` | `text: str` | no |
| 182 | `decode_search_href` | `href: str` | no |
| 194 | `extract_text_from_path` | `path: Path, max_chars: int=2000` | no |
| 210 | `extract_text_from_html_content` | `raw_html: str, max_chars: int=2000` | no |
| 219 | `extract_same_host_links` | `raw_html: str, base_url: str, host: str` | no |
| 246 | `expand_research_terms` | `tokens: list[str]` | no |
| 259 | `score_research_hit` | `url: str, text: str, terms: list[str], primary_tokens: Optional[list[str]]=None` | no |
| 292 | `crawl_domain_for_query` | `start_url: str, query_tokens: list[str], max_pages: int, max_depth: int, *, requests_get_fn: Callable[..., Any], expand_research_terms_fn: Callable[[list[str]], list[str]], extract_text_from_html_content_fn: Callable[[str, int], str], score_research_hit_fn: Callable[..., float], extract_same_host_links_fn: Callable[[str, str, str], list[str]]` | no |
| 345 | `seed_urls_for_domain` | `domain: str, query_tokens: list[str], max_seed: int=30, *, fetch_sitemap_urls_fn: Callable[[str, int], list[str]], expand_research_terms_fn: Callable[[list[str]], list[str]]` | no |
| 384 | `looks_like_code_discovery_query` | `text: str` | no |
| 414 | `host_label` | `url: str` | no |
| 421 | `summary_from_gather_output` | `raw: str` | no |
| 432 | `is_weak_grounded_snippet` | `value: str` | no |
| 447 | `build_grounded_answer` | `query_text: str, *, max_sources: int=2, tool_web_research_fn: Callable[[str], str], tool_web_gather_fn: Callable[[str], str]` | no |
| 487 | `fetch_sitemap_urls` | `domain: str, limit: int=80, *, requests_get_fn: Callable[..., Any], host_allowed_fn: Callable[[str, list[str]], bool]` | no |
| 542 | `tool_web_fetch` | `url: str, *, explain_missing_fn: Callable[[str, list[str]], str], policy_tools_enabled_fn: Callable[[], dict], web_fetch_fn: Callable[[str], dict], web_allowlist_message_fn: Callable[[str], str]` | no |
| 567 | `tool_wikipedia_lookup` | `query: str, *, explain_missing_fn: Callable[[str, list[str]], str], policy_tools_enabled_fn: Callable[[], dict], web_enabled_fn: Callable[[], bool], requests_get_fn: Callable[..., Any]` | no |
| 644 | `tool_stackexchange_search` | `query: str, *, explain_missing_fn: Callable[[str, list[str]], str], policy_tools_enabled_fn: Callable[[], dict], web_enabled_fn: Callable[[], bool], policy_web_fn: Callable[[], dict], requests_get_fn: Callable[..., Any], env: dict[str, str]` | no |
| 713 | `tool_web_search` | `query: str, *, explain_missing_fn: Callable[[str, list[str]], str], policy_tools_enabled_fn: Callable[[], dict], web_enabled_fn: Callable[[], bool], policy_web_fn: Callable[[], dict], host_allowed_fn: Callable[[str, list[str]], bool], decode_search_href_fn: Callable[[str], str], probe_search_endpoint_fn: Callable[..., dict], web_allowlist_message_fn: Callable[[str], str], requests_get_fn: Callable[..., Any]` | no |
| 744 | `_search_via_api` | `query_text: str, domains: list[str], max_results: int=5` | no |
| 822 | `_local_search_backend_message` | `api_err: object` | no |
| 837 | `_search_via_html` | `query_text: str, domains: list[str], max_results: int=5` | no |
| 912 | `tool_web_gather` | `url: str, *, explain_missing_fn: Callable[[str, list[str]], str], policy_tools_enabled_fn: Callable[[], dict], web_fetch_fn: Callable[[str], dict], web_allowlist_message_fn: Callable[[str], str], extract_text_from_path_fn: Callable[[Path, int], str]` | no |
| 960 | `tool_web_research` | `query: str, *, continue_mode: bool=False, explain_missing_fn: Callable[[str, list[str]], str], policy_tools_enabled_fn: Callable[[], dict], web_enabled_fn: Callable[[], bool], policy_web_fn: Callable[[], dict], tokenize_fn: Callable[[str], list[str]], fetch_sitemap_urls_fn: Callable[[str, int], list[str]], scan_candidate_urls_for_query_fn: Callable[[list[str], list[str], int, float], list[tuple[float, str, str]]], seed_urls_for_domain_fn: Callable[[str, list[str], int], list[str]], crawl_domain_for_query_fn: Callable[[str, list[str], int, int], list[tuple[float, str, str]]], session_store: WebResearchSessionStore` | no |
| 1041 | `_extend_hits` | `rows: list[tuple[float, str, str]]` | no |
| 1123 | `web_search` | `query: str, save_dir: Path, *, requests_post_fn: Callable[..., Any], max_results: int=5` | no |
| 1166 | `tool_search` | `query: str, *, explain_missing_fn: Callable[[str, list[str]], str], policy_tools_enabled_fn: Callable[[], dict], web_search_fn: Callable[[str, Path, int], dict], web_cache_dir: Path` | no |

## `services/nova_wiring_inventory.py`

Lines: 1239 | Functions/methods: 10 | Classes: 1

Classes: `WiringSurface` (L12)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 598 | `_clean_set` | `values: Iterable[str] \| None` | no |
| 602 | `_read_source` | `repo_root: Path, relative_path: str` | no |
| 612 | `_literal_string_sequence` | `source: str, constant_names: Iterable[str]` | no |
| 650 | `_literal_dict_string_values` | `source: str, key_name: str` | no |
| 674 | `build_source_wiring_probe_payload` | `*, root: str \| Path \| None=None` | yes |
| 850 | `build_wiring_inventory_payload` | `status_payload: dict[str, Any] \| None=None, *, signal_sources: Iterable[str] \| None=None, planned_tools: Iterable[str] \| None=None, advisory_actions: Iterable[str] \| None=None` | no |
| 925 | `build_root_closure_inventory_payload` | `status_payload: dict[str, Any] \| None=None, *, root: str \| Path \| None=None, signal_sources: Iterable[str] \| None=None, planned_tools: Iterable[str] \| None=None, advisory_actions: Iterable[str] \| None=None` | yes |
| 1047 | `_closure_depth` | `row: dict[str, Any]` | no |
| 1069 | `build_self_repair_closure_inventory_payload` | `status_payload: dict[str, Any] \| None=None, *, root: str \| Path \| None=None, signal_sources: Iterable[str] \| None=None, planned_tools: Iterable[str] \| None=None, advisory_actions: Iterable[str] \| None=None, executable_tools: Iterable[str] \| None=None, executable_actions: Iterable[str] \| None=None, evidence_paths: Iterable[str] \| None=None, judgment_paths: Iterable[str] \| None=None, closure_paths: Iterable[str] \| None=None, operator_outbox_paths: Iterable[str] \| None=None, owned_root_routes: Iterable[str] \| None=None` | yes |
| 1238 | `wiring_surface_ids` | `` | no |

## `services/ollama_health.py`

Lines: 168 | Functions/methods: 5 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 6 | `_status_code` | `response: Any` | no |
| 13 | `_json_payload` | `response: Any` | no |
| 21 | `_available_models` | `tags_payload: dict[str, Any]` | no |
| 33 | `_version_from_payload` | `version_payload: dict[str, Any]` | no |
| 37 | `build_ollama_health_payload` | `*, requests_get_fn: Callable[..., Any], requests_post_fn: Callable[..., Any], ollama_base: str, chat_model: str='', timeout: float=2.0, live_calls_allowed: bool=True` | no |

## `services/operator_control.py`

Lines: 328 | Functions/methods: 14 | Classes: 1

Classes: `OperatorControlService` (L10)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 14 | `_runtime_fn` | `runtime_scope: dict[str, object], name: str` | no |
| 18 | `operator_macros_path` | `base_dir: Path` | no |
| 22 | `backend_command_deck_path` | `base_dir: Path` | no |
| 26 | `backend_command_list_action` | `*, load_backend_commands_fn` | no |
| 31 | `backend_command_run_action` | `payload: dict, *, load_backend_commands_fn, run_backend_command_fn` | no |
| 39 | `operator_prompt_action` | `payload: dict, *, resolve_operator_macro_fn, render_operator_macro_prompt_fn, load_operator_macros_fn, normalize_user_id_fn, assert_session_owner_fn, process_chat_fn, session_summaries_fn, token_hex_fn` | no |
| 99 | `operator_prompt_action_from_runtime` | `payload: dict, *, runtime_scope: dict[str, object]` | no |
| 113 | `load_operator_macros` | `self, path: Path, limit: int=24` | no |
| 163 | `resolve_operator_macro` | `self, macro_id: str, macros: list[dict]` | no |
| 173 | `render_operator_macro_prompt` | `macro: Mapping[str, Any], values: Mapping[str, Any] \| None=None, note: str=''` | no |
| 201 | `load_backend_commands` | `self, path: Path, limit: int=40` | no |
| 242 | `resolve_backend_command` | `self, command_id: str, commands: list[dict]` | no |
| 252 | `parse_backend_dynamic_args` | `raw: Any` | no |
| 264 | `run_backend_command` | `self, command_id: str, payload: dict, *, commands: list[dict], python_bin: Path, base_dir: Path, subprocess_run=subprocess.run` | no |

## `services/operator_outbox.py`

Lines: 1382 | Functions/methods: 41 | Classes: 1

Classes: `OperatorOutboxService` (L124)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `_safe_text` | `value: Any, limit: int=500` | no |
| 14 | `_safe_dict` | `value: Any` | no |
| 18 | `_safe_list` | `value: Any` | no |
| 22 | `_safe_set` | `value: Any` | no |
| 40 | `_autonomy_internal_wait_reason` | `reason: str` | no |
| 49 | `_operator_notice_is_internal_wait` | `event: dict[str, Any]` | no |
| 71 | `_operator_actionable_open_events` | `events: list[dict[str, Any]]` | no |
| 101 | `_safe_status` | `value: Any, default: str='new'` | no |
| 106 | `_compact` | `value: Any, *, depth: int=0` | no |
| 133 | `_normalize_event` | `item: dict[str, Any]` | no |
| 150 | `_small_list` | `value: Any, *, limit: int=8` | no |
| 158 | `_task_projection` | `task: Any` | no |
| 172 | `_next_step_projection` | `cls, next_step: Any` | no |
| 186 | `_work_tree_notice_payload` | `cls, *, tree_id: str, tree_title: str, branch_id: str, branch_title: str, task_id: str, task_title: str, request_kind: str, next_step: Any=None, task: Any=None, extra: dict[str, Any] \| None=None` | no |
| 230 | `_summary_payload` | `self, event: dict[str, Any]` | no |
| 274 | `_summary_response` | `response: dict[str, Any]` | no |
| 288 | `_summary_event` | `self, event: dict[str, Any]` | no |
| 324 | `_load_events` | `self, path: Path` | no |
| 344 | `_write_events` | `path: Path, rows: list[dict[str, Any]]` | no |
| 352 | `read_events` | `self, path: Path, *, after_id: str='', limit: int=20` | no |
| 359 | `summary` | `self, path: Path, *, limit: int=5` | no |
| 402 | `append_notice` | `self, path: Path, *, source: str, severity: str, title: str, message: str, dedupe_key: str='', audience: str='operator', payload: dict[str, Any] \| None=None, dedupe_window_sec: int=1800, max_events: int=200, now_fn: Callable[[], float] \| None=None, uuid_fn: Callable[[], str] \| None=None` | no |
| 472 | `blocked_work_dedupe_key` | `*, tree_id: str, branch_id: str, blocked_reason: str` | no |
| 479 | `work_tree_target_from_event` | `event: dict[str, Any]` | no |
| 507 | `_record_response_in_work_tree` | `self, event: dict[str, Any], response: dict[str, Any], *, resolution: str, work_tree_module: Any=None` | no |
| 575 | `set_notice_status` | `self, path: Path, *, event_id: str, status: str, note: str='', now_fn: Callable[[], float] \| None=None` | no |
| 608 | `reconcile_work_tree_notices` | `self, path: Path, *, active_notices: list[dict[str, Any]] \| None=None, now_fn: Callable[[], float] \| None=None` | yes |
| 665 | `_branch_exists` | `work_tree_module: Any, branch_id: str` | no |
| 683 | `reconcile_source_root_judgment_notices` | `self, path: Path, *, work_tree_state: dict[str, Any] \| None=None, work_tree_module: Any=None, now_fn: Callable[[], float] \| None=None` | yes |
| 745 | `reconcile_stale_open_notices` | `self, path: Path, *, max_age_days: int=7, now_fn: Callable[[], float] \| None=None` | yes |
| 776 | `reconcile_duplicate_source_notices` | `self, path: Path, *, now_fn: Callable[[], float] \| None=None` | yes |
| 829 | `reconcile_autonomy_notices` | `self, path: Path, *, active_notices: list[dict[str, Any]] \| None=None, now_fn: Callable[[], float] \| None=None` | yes |
| 866 | `reconcile_os_capability_notices` | `self, path: Path, *, capability: str, cleared_reasons: list[str] \| tuple[str, ...] \| set[str] \| None=None, now_fn: Callable[[], float] \| None=None` | yes |
| 911 | `respond_to_notice` | `self, path: Path, *, event_id: str, message: str, responder: str='operator', resolution: str='evidence_only', response_payload: dict[str, Any] \| None=None, work_tree_module: Any=None, now_fn: Callable[[], float] \| None=None, uuid_fn: Callable[[], str] \| None=None` | no |
| 984 | `_work_tree_trees` | `work_tree_state: Any` | no |
| 994 | `_blocked_request_kind` | `reason: str, node: dict[str, Any]` | no |
| 1013 | `_blocked_message` | `kind: str, branch_title: str, task_title: str, reason: str, source: str` | no |
| 1038 | `_is_operator_control_mirror_node` | `node: dict[str, Any]` | no |
| 1044 | `notices_from_work_tree_state` | `self, work_tree_state: Any, *, executable_tools: list[str] \| tuple[str, ...] \| set[str] \| None=None, limit: int=12` | yes |
| 1061 | `add` | `notice: dict[str, Any]` | no |
| 1307 | `notice_from_autonomy` | `self, packet: dict[str, Any], execution: dict[str, Any]` | no |

## `services/ops_journal.py`

Lines: 123 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 16 | `_append_this_is_nova_entry` | `workspace_root: Path, entry: dict` | no |
| 61 | `_this_is_nova_workspace_root` | `runtime_dir: Path` | no |
| 73 | `append_ops_event` | `runtime_dir: Path, *, category: str, action: str, result: str, detail: str='', payload: dict \| None=None, journal_name: str='ops_journal.jsonl'` | yes |

## `services/os_capability_operator_outbox.py`

Lines: 177 | Functions/methods: 9 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 12 | `_safe_text` | `value: Any, limit: int=500` | no |
| 16 | `_safe_dict` | `value: Any` | no |
| 20 | `_safe_list` | `value: Any` | no |
| 24 | `_compact` | `value: Any, *, depth: int=0` | no |
| 42 | `_stable_hash` | `value: Any` | no |
| 47 | `_detail_from_row` | `row: dict[str, Any]` | no |
| 60 | `_message_for` | `reason: str, capability: str, detail: str` | no |
| 85 | `build_os_capability_notice` | `result: dict[str, Any], *, context: dict[str, Any] \| None=None` | no |
| 145 | `publish_os_capability_notice` | `result: dict[str, Any], *, outbox_path: Path \| None=None, context: dict[str, Any] \| None=None, operator_outbox_service: Any=None, now_fn: Any=None, uuid_fn: Any=None` | no |

## `services/os_capability_registry.py`

Lines: 583 | Functions/methods: 17 | Classes: 1

Classes: `OsCapabilityRegistryService` (L62)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 34 | `_safe_text` | `value: Any, limit: int=500` | no |
| 38 | `_safe_dict` | `value: Any` | no |
| 42 | `_safe_list` | `value: Any` | no |
| 46 | `_is_relative_to` | `path: Path, root: Path` | no |
| 54 | `_sha256_file` | `path: Path` | no |
| 65 | `load_registry` | `self, path: Path \| None=None, *, base_dir: Path \| None=None` | no |
| 152 | `resolve_capability` | `self, name: str, path: Path \| None=None, *, base_dir: Path \| None=None` | no |
| 181 | `validate_args` | `self, capability: dict[str, Any], args: dict[str, Any] \| None` | no |
| 231 | `prepare_request` | `self, name: str, args: dict[str, Any] \| None=None, path: Path \| None=None, *, base_dir: Path \| None=None` | no |
| 279 | `verify_capability_hash` | `self, capability: dict[str, Any]` | no |
| 319 | `_normalize_capability` | `self, item: Any, *, base_dir: Path, default_outbox: set[str], index: int` | no |
| 455 | `_has_structural_contract_errors` | `errors: list[str]` | no |
| 466 | `_validate_value` | `self, key: str, value: Any, spec: dict[str, Any]` | no |
| 506 | `_validate_contract_bounds` | `self, capability: dict[str, Any], args: dict[str, Any]` | no |
| 528 | `_invalid_args_result` | `self, capability: dict[str, Any], args: dict[str, Any], errors: list[str]` | no |
| 542 | `_blocked_result` | `self, reason: str, detail: str, *, registry: Any=None, capability: dict[str, Any] \| None=None, errors: list[str] \| None=None` | no |
| 562 | `_should_outbox` | `self, capability: dict[str, Any], reason: str, *, registry: Any=None` | no |

## `services/os_script_controller.py`

Lines: 678 | Functions/methods: 22 | Classes: 1

Classes: `OsScriptControllerService` (L50)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 20 | `_safe_text` | `value: Any, limit: int=1000` | no |
| 24 | `_safe_dict` | `value: Any` | no |
| 28 | `_safe_list` | `value: Any` | no |
| 32 | `_compact` | `value: Any, *, depth: int=0` | no |
| 53 | `execute_capability` | `self, name: str, args: dict[str, Any] \| None=None, *, registry_path: Path \| None=None, ledger_path: Path \| None=None, base_dir: Path \| None=None, registry_service: Any=None, popen_factory: Any=None, powershell_executable: str \| None=None, authority_context: dict[str, Any] \| None=None, now_fn: Any=None, uuid_fn: Any=None` | no |
| 236 | `recent_ledger_rows` | `path: Path \| None=None, *, limit: int=80` | no |
| 255 | `summary` | `self, path: Path \| None=None, *, limit: int=80` | no |
| 277 | `_verify_writes_only_to` | `self, capability: dict[str, Any], run_result: dict[str, Any], base_dir: Path` | no |
| 346 | `_verify_evidence_ok` | `self, capability: dict[str, Any], run_result: dict[str, Any]` | no |
| 386 | `_reported_write_paths` | `payload: dict[str, Any]` | no |
| 410 | `_authority_result` | `capability: dict[str, Any], authority_context: dict[str, Any] \| None=None` | no |
| 452 | `_build_command` | `self, capability: dict[str, Any], args: dict[str, Any], base_dir: Path, *, powershell_executable: str \| None=None` | no |
| 513 | `_run_process` | `self, command: list[str], *, cwd: Path, timeout_ms: int, popen_factory: Any=None, now_fn: Any=None` | no |
| 579 | `_base_row` | `self, *, request_id: str, started: float, capability_name: str, registry_path: Path, base_dir: Path, args: dict[str, Any], prepared: dict[str, Any]` | no |
| 617 | `_append_ledger` | `path: Path, row: dict[str, Any]` | no |
| 628 | `_request_id` | `started: float, *, uuid_fn: Any=None` | no |
| 633 | `_duration_ms` | `started: float, *, now_fn: Any=None` | no |
| 637 | `_powershell_executable` | `` | no |
| 641 | `_limit_text` | `value: Any, limit: int=MAX_LEDGER_TEXT_CHARS` | no |
| 648 | `_decode_partial` | `value: Any` | no |
| 656 | `_join_output` | `first: Any, second: Any` | no |
| 664 | `_result_from_row` | `row: dict[str, Any], *, ledger: dict[str, Any]` | no |

## `services/patch_control.py`

Lines: 375 | Functions/methods: 15 | Classes: 1

Classes: `PatchControlService` (L7)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `patch_preview_list_action` | `self, *, patch_status_payload_fn: Callable[[], dict], preview_summaries_fn: Callable[[int], list[dict]], patch_action_readiness_payload_fn: Callable[[dict], dict]` | no |
| 31 | `pulse_status_action` | `*, build_pulse_payload_fn: Callable[[], dict], render_nova_pulse_fn: Callable[[dict], str], update_now_pending_payload_fn: Callable[[], dict]` | no |
| 45 | `patch_action_readiness_payload` | `self, patch_summary: dict \| None=None, *, preview_summaries_fn: Callable[[int], list[dict]], show_preview_fn: Callable[[str], str], updates_dir: Path` | no |
| 156 | `patch_preview_target` | `payload: dict, previews: list[dict]` | no |
| 165 | `patch_preview_entry` | `target: str, previews: list[dict]` | no |
| 177 | `patch_control_state` | `patch_payload: dict, previews: list[dict], *, include_readiness: bool=True, readiness_payload: dict \| None=None` | no |
| 198 | `patch_preview_show` | `self, payload: dict, *, preview_target_fn: Callable[[dict], str], patch_control_state_fn: Callable[..., dict], show_preview_fn: Callable[[str], str]` | no |
| 218 | `patch_preview_decision` | `self, action_name: str, payload: dict, *, preview_target_fn: Callable[[dict], str], patch_control_state_fn: Callable[..., dict], decision_fn: Callable[[str, str], str]` | no |
| 241 | `patch_preview_apply` | `self, payload: dict, *, preview_target_fn: Callable[[dict], str], preview_entry_fn: Callable[[str], dict], patch_control_state_fn: Callable[..., dict], show_preview_fn: Callable[[str], str], updates_dir: Path, patch_apply_fn: Callable[[str], str]` | no |
| 304 | `update_now_dry_run` | `text: str, *, pending_payload: dict, patch_payload: dict` | no |
| 314 | `update_now_dry_run_action` | `self, *, tool_update_now_fn: Callable[[], str], update_now_pending_payload_fn: Callable[[], dict], patch_status_payload_fn: Callable[[], dict]` | no |
| 329 | `update_now_confirm` | `text: str, *, pending_payload: dict, patch_payload: dict` | no |
| 339 | `update_now_confirm_action` | `self, payload: dict, *, tool_update_now_confirm_fn: Callable[[str], str], update_now_pending_payload_fn: Callable[[], dict], patch_status_payload_fn: Callable[[], dict]` | no |
| 356 | `update_now_cancel` | `text: str, *, pending_payload: dict` | no |
| 362 | `update_now_cancel_action` | `self, *, tool_update_now_cancel_fn: Callable[[], str], update_now_pending_payload_fn: Callable[[], dict]` | no |

## `services/patch_promotion_memory.py`

Lines: 234 | Functions/methods: 7 | Classes: 1

Classes: `PatchPromotionMemoryService` (L212)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 22 | `_extract_code_from_artifact_manifest` | `manifest: Dict[str, Any]` | yes |
| 51 | `extract_codegen_content_from_patch_zip` | `patch_zip_path: Path, patch_manifest: Dict[str, Any]` | yes |
| 106 | `record_patch_promotion_to_memory` | `patch_artifact_record: Dict[str, Any], patch_zip_path: Optional[Path]=None` | yes |
| 191 | `inject_memory_context_into_codegen_prompt` | `spec_name: str, spec_purpose: str` | yes |
| 216 | `record_promotion` | `patch_artifact_record: Dict[str, Any], patch_zip_path: Optional[Path]=None` | yes |
| 224 | `get_memory_injection` | `spec_name: str, spec_purpose: str` | yes |
| 229 | `extract_codegen_from_zip` | `patch_zip_path: Path, manifest: Dict[str, Any]` | yes |

## `services/pipeline_privileged_bridge.py`

Lines: 89 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `queue_privileged_pipeline_query` | `pipeline_id: str, operation: str, params: Optional[Mapping[str, Any]]=None, *, row_limit: Optional[int]=None, requested_by: str='', timeout_sec: int=60, runtime_root: Optional[Path]=None` | no |
| 37 | `wait_for_privileged_pipeline_query` | `pipeline_id: str, request_id: str, *, timeout_sec: int=60, poll_interval_sec: float=0.5, runtime_root: Optional[Path]=None` | no |
| 54 | `run_privileged_pipeline_query` | `pipeline_id: str, operation: str, params: Optional[Mapping[str, Any]]=None, *, row_limit: Optional[int]=None, requested_by: str='', timeout_sec: int=60, poll_interval_sec: float=0.5, runtime_root: Optional[Path]=None` | no |

## `services/policy_control.py`

Lines: 187 | Functions/methods: 12 | Classes: 1

Classes: `PolicyControlService` (L4)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `policy_allow_action` | `payload: dict, *, policy_allow_domain_fn` | no |
| 14 | `policy_remove_action` | `payload: dict, *, policy_remove_domain_fn` | no |
| 20 | `web_mode_action` | `payload: dict, *, set_web_mode_fn` | no |
| 26 | `memory_scope_set_action` | `payload: dict, *, set_memory_scope_fn, control_policy_payload_fn, invalidate_control_status_cache_fn` | no |
| 41 | `mission_settings_action` | `payload: dict, *, set_mission_settings_fn, control_policy_payload_fn, invalidate_control_status_cache_fn` | no |
| 59 | `_bool_field` | `name: str` | no |
| 85 | `server_side_settings_action` | `payload: dict, *, set_server_side_settings_fn, control_policy_payload_fn, invalidate_control_status_cache_fn` | no |
| 122 | `search_provider_action` | `payload: dict, *, set_search_provider_fn, control_policy_payload_fn, invalidate_control_status_cache_fn` | no |
| 137 | `search_endpoint_set_action` | `payload: dict, *, set_search_endpoint_fn, control_policy_payload_fn, invalidate_control_status_cache_fn` | no |
| 152 | `search_provider_priority_set_action` | `payload: dict, *, set_search_provider_priority_fn, control_policy_payload_fn, invalidate_control_status_cache_fn` | no |
| 168 | `search_endpoint_probe_action` | `payload: dict, *, probe_search_endpoint_fn` | no |
| 176 | `search_provider_toggle_action` | `*, toggle_search_provider_fn, control_policy_payload_fn, invalidate_control_status_cache_fn` | no |

## `services/policy_manager.py`

Lines: 758 | Functions/methods: 31 | Classes: 1

Classes: `PolicyManager` (L84)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 43 | `_search_endpoint_parts` | `endpoint: str` | no |
| 67 | `_same_local_search_endpoint_contract` | `current: str, candidate: str` | no |
| 87 | `__init__` | `self, policy_file: Path, audit_log_file: Path, base_dir: Path` | no |
| 93 | `load_policy` | `self` | yes |
| 208 | `_load_raw` | `self` | yes |
| 212 | `_save_raw` | `self, data: dict` | yes |
| 223 | `record_change` | `self, action: str, target: str, result: str, details: str='', user: str \| None=None` | yes |
| 240 | `get_models` | `self` | yes |
| 245 | `get_memory` | `self` | yes |
| 250 | `get_tools_enabled` | `self` | yes |
| 255 | `get_web` | `self` | yes |
| 260 | `get_patch` | `self` | yes |
| 265 | `get_server_side` | `self` | yes |
| 282 | `is_web_enabled` | `self` | yes |
| 287 | `host_allowed` | `self, host: str, allow_domains: list[str]` | yes |
| 298 | `normalize_domain_input` | `self, value: str` | yes |
| 325 | `list_allowed_domains` | `self` | yes |
| 336 | `allow_domain` | `self, value: str, user: str \| None=None` | yes |
| 360 | `remove_domain` | `self, value: str, user: str \| None=None` | yes |
| 390 | `set_web_mode` | `self, mode: str, user: str \| None=None` | no |
| 409 | `set_memory_scope` | `self, scope: str, user: str \| None=None` | no |
| 430 | `set_server_side_settings` | `self, *, mode: str='', frontdoor: str='', frontdoor_base_url: str \| None=None, docker_enabled: bool \| None=None, user: str \| None=None` | no |
| 483 | `set_mission_settings` | `self, *, enabled: bool \| None=None, mode: str='', objective: str='', release_stale_ready_is_pressure: bool \| None=None, subconscious_triage_is_pressure: bool \| None=None, generated_queue_backlog_is_pressure: bool \| None=None, user: str \| None=None` | no |
| 551 | `get_search_provider` | `self` | no |
| 557 | `get_search_provider_priority` | `self` | no |
| 581 | `get_search_endpoint` | `self` | no |
| 584 | `set_search_provider` | `self, provider: str, user: str \| None=None` | no |
| 631 | `set_search_provider_priority` | `self, priority: str \| list[str], user: str \| None=None` | no |
| 673 | `set_search_endpoint` | `self, endpoint: str, user: str \| None=None` | no |
| 703 | `auto_repair_search_endpoint` | `self, endpoint: str, user: str \| None=None` | no |
| 723 | `audit` | `self, limit: int=20` | yes |

## `services/port_ownership.py`

Lines: 164 | Functions/methods: 4 | Classes: 1

Classes: `PortOwnershipService` (L24)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 28 | `_addr_payload` | `laddr: Any` | no |
| 40 | `_process_payload` | `psutil_module: Any, pid: int \| None` | no |
| 65 | `_owner_matches` | `owner: dict[str, Any], spec: dict[str, Any]` | no |
| 88 | `payload` | `self, *, psutil_module: Any, service_specs: list[dict[str, Any]] \| None=None` | no |

## `services/regression_lanes.py`

Lines: 265 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `services/regression_profile_inventory.py`

Lines: 247 | Functions/methods: 10 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 9 | `_repo_root` | `root: Path \| None=None` | no |
| 13 | `_clean_text` | `value: object` | no |
| 17 | `_target_module_name` | `target: str, *, root: Path` | no |
| 30 | `_module_name_for_path` | `path: Path, *, root: Path` | no |
| 35 | `_discover_test_files` | `root: Path` | no |
| 48 | `_active_pipeline_ids` | `root: Path` | no |
| 55 | `_missing_install_lanes` | `path: Path, text: str, active_pipeline_ids: set[str]` | no |
| 65 | `_optional_inactive_install_lanes` | `text: str, missing_lanes: list[str]` | no |
| 80 | `_surface_hint` | `path: Path` | no |
| 116 | `build_regression_profile_inventory_payload` | `*, root: Path \| None=None, test_lanes: Mapping[str, list[str]] \| None=None` | no |

## `services/release_clean.py`

Lines: 324 | Functions/methods: 12 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 19 | `_tail` | `text: str, limit: int=12000` | no |
| 25 | `_default_command_runner` | `name: str, command: Sequence[str], cwd: Path, timeout_sec: int` | no |
| 65 | `_latest_release_zip` | `package_dir: Path` | no |
| 78 | `_artifact_from_build_stdout` | `stdout: str, repo_root: Path` | no |
| 91 | `_validation_record_from_build_stdout` | `stdout: str, repo_root: Path` | no |
| 104 | `_step_ok` | `step: dict[str, Any]` | no |
| 108 | `_run_step` | `steps: list[dict[str, Any]], runner: CommandRunner, name: str, command: Sequence[str], cwd: Path, timeout_sec: int` | no |
| 121 | `_parse_readiness` | `stdout: str` | no |
| 131 | `_readiness_state` | `readiness: dict[str, Any]` | no |
| 138 | `_write_report` | `report: dict[str, Any], report_path: Path` | no |
| 143 | `_public_step` | `step: dict[str, Any]` | no |
| 151 | `run_release_clean` | `*, root: Path \| None=None, label: str='release-clean', python_executable: str \| None=None, run_regression: bool=True, promote: bool=True, timeout_sec: int=1800, command_runner: CommandRunner \| None=None` | yes |

## `services/release_promotion_judgment.py`

Lines: 313 | Functions/methods: 8 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 41 | `_clean_text` | `value: Any` | no |
| 45 | `_field_key` | `value: Any` | no |
| 51 | `_field_value_is_missing` | `value: Any` | no |
| 56 | `_read_validation_record_fields` | `record_path: Path` | no |
| 93 | `release_validation_record_payload` | `record_path: str \| Path, *, release_status: dict[str, Any] \| None=None` | no |
| 169 | `_evidence_tools` | `evidence_rows: list[dict[str, Any]]` | no |
| 184 | `build_release_promotion_judgment` | `*, release_status: dict[str, Any], branch_payload: dict[str, Any] \| None=None, evidence_rows: list[dict[str, Any]] \| None=None, branch_id: str=''` | no |
| 287 | `render_release_promotion_judgment` | `judgment: dict[str, Any]` | no |

## `services/release_runtime_truth.py`

Lines: 132 | Functions/methods: 9 | Classes: 1

Classes: `ReleaseRuntimeTruthService` (L106)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 18 | `running_build_identity` | `release_status: dict[str, Any]` | no |
| 34 | `enrich_release_status` | `release_status: dict[str, Any]` | no |
| 48 | `build_release_runtime_truth_summary` | `release_status: dict[str, Any]` | no |
| 65 | `release_drift_suppresses_closure_signals` | `release_status: dict[str, Any], *, runtime_truth: dict[str, Any] \| None=None` | no |
| 77 | `evaluate_http_model_runtime_probe` | `http_payload: dict[str, Any], *, required_keys: tuple[str, ...]=MODEL_RUNTIME_HTTP_PROBE_KEYS` | no |
| 108 | `enrich_release_status` | `release_status: dict[str, Any]` | no |
| 112 | `build_runtime_truth_summary` | `release_status: dict[str, Any]` | no |
| 116 | `release_drift_suppresses_closure_signals` | `release_status: dict[str, Any], *, runtime_truth: dict[str, Any] \| None=None` | no |
| 124 | `evaluate_http_model_runtime_probe` | `http_payload: dict[str, Any], *, required_keys: tuple[str, ...]=MODEL_RUNTIME_HTTP_PROBE_KEYS` | no |

## `services/release_status.py`

Lines: 448 | Functions/methods: 13 | Classes: 1

Classes: `ReleaseStatusService` (L153)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 49 | `_entry_artifact_kind` | `entry: dict` | no |
| 54 | `_parse_recorded_at_epoch` | `value: str` | no |
| 67 | `_source_rel` | `path: Path, root: Path` | no |
| 74 | `_is_source_candidate` | `path: Path, root: Path` | no |
| 90 | `_is_excluded_source_dir` | `path: Path, root: Path` | no |
| 100 | `_iter_source_candidates` | `root: Path` | no |
| 113 | `_sha256_file` | `path: Path` | no |
| 121 | `_zip_relative_name` | `name: str` | no |
| 131 | `_artifact_hashes_for_paths` | `artifact_path: Path, relative_paths: set[str]` | no |
| 157 | `ledger_entries` | `ledger_path: Path, limit: int=20` | no |
| 179 | `entry_matches_build` | `entry: dict, build_entry: dict` | no |
| 194 | `source_freshness_payload` | `self, source_root: Path, build_recorded_at: str, *, artifact_path: Path \| None=None` | no |
| 273 | `status_payload` | `self, ledger_path: Path, limit: int=8, source_root: Path \| None=None, *, artifact_kind: str='package-zip'` | no |

## `services/release_validation.py`

Lines: 722 | Functions/methods: 26 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 34 | `_tail` | `text: str, limit: int=12000` | no |
| 40 | `_read_text_tail` | `path: Path, limit: int=12000` | no |
| 47 | `_terminate_process_tree` | `pid: int` | no |
| 69 | `_command_log_paths` | `name: str, log_root: Path` | no |
| 76 | `_default_command_runner` | `name: str, command: Sequence[str], cwd: Path, timeout_sec: int, *, log_root: Path \| None=None` | no |
| 133 | `_default_http_get` | `url: str, timeout_sec: float` | no |
| 139 | `_safe_fragment` | `value: str` | no |
| 144 | `_remove_inside` | `parent: Path, target: Path` | no |
| 155 | `_safe_zip_parts` | `name: str` | no |
| 166 | `_strip_prefix` | `parts: tuple[str, ...], prefix: tuple[str, ...]` | no |
| 172 | `_prepare_package_root` | `artifact_path: Path, work_root: Path` | no |
| 225 | `_pick_local_port` | `` | no |
| 231 | `_step_value` | `step: dict[str, Any] \| None` | no |
| 242 | `_step_failed` | `step: dict[str, Any] \| None` | no |
| 246 | `_step_passed` | `step: dict[str, Any] \| None` | no |
| 250 | `_nova_run_probe_command` | `nova_cmd: Path, *, exercise_turn: bool=False` | no |
| 273 | `_parse_regression_generated_at` | `payload: dict[str, Any]` | no |
| 285 | `_load_regression_status` | `path: Path` | no |
| 293 | `_regression_status_gate` | `*, status_path: Path, max_age_sec: int=REGRESSION_STATUS_MAX_AGE_SEC, now_epoch: float \| None=None` | no |
| 339 | `_write_json_report` | `report: dict[str, Any], path: Path` | no |
| 344 | `_write_validation_record` | `record_path: Path, *, artifact_path: Path, artifact_version: str, release_channel: str, release_label: str, version_source: str, ledger_path: str, manifest_reviewed: str, machine_name: str, windows_version: str, python_source: str, ollama_expected: str, step_values: dict[str, str], result: str, blocking_issues: list[str], nonblocking_issues: list[str], regression_gate: dict[str, Any], follow_up_owner: str` | no |
| 433 | `run_release_validation` | `*, repo_root: Path \| None=None, artifact_path: str \| Path, record_path: str \| Path, artifact_version: str='', release_channel: str='rc', release_label: str='', version_source: str='', ledger_path: str='', include_runtime: bool=False, timeout_sec: int=1800, command_runner: CommandRunner \| None=None, http_get: HttpGet \| None=None, work_root: Path \| None=None, keep_extract: bool=False, regression_status_path: str \| Path \| None=None, regression_max_age_sec: int=REGRESSION_STATUS_MAX_AGE_SEC` | no |
| 461 | `runner` | `name: str, command: Sequence[str], cwd: Path, timeout_sec: int` | no |
| 638 | `render_release_validation_report` | `report: dict[str, Any]` | no |
| 660 | `record_release_validation_outcome` | `*, repo_root: Path \| None=None, record_path: str \| Path, release_status: dict[str, Any], command_runner: CommandRunner \| None=None` | no |
| 708 | `render_release_outcome_recording` | `report: dict[str, Any]` | no |

## `services/release_validation_contracts.py`

Lines: 3 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `services/runtime_analytics.py`

Lines: 349 | Functions/methods: 10 | Classes: 1

Classes: `RuntimeAnalyticsService` (L11)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 19 | `restart_analytics_payload` | `self, *, boot_history_path: Path, guard_log_path: Path \| None=None, now: int \| None=None` | yes |
| 96 | `_failure_events_from_guard_log` | `path: Path \| None` | no |
| 121 | `_entry_origin` | `item: dict` | no |
| 124 | `_entry_action` | `item: dict` | no |
| 131 | `_entry_planned` | `item: dict` | no |
| 139 | `_entry_provenance_complete` | `item: dict` | no |
| 149 | `_entry_restart_cause_reason` | `item: dict` | no |
| 172 | `_entry_is_pressure` | `item: dict` | no |
| 189 | `_count_since` | `window_seconds: int` | no |
| 193 | `_count_matching_since` | `window_seconds: int, predicate` | no |

## `services/runtime_artifacts.py`

Lines: 250 | Functions/methods: 9 | Classes: 1

Classes: `RuntimeArtifactsService` (L6)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 24 | `canonical_artifact_name` | `cls, name: str` | no |
| 30 | `artifact_id` | `cls, name: str` | no |
| 35 | `artifact_definitions` | `*, runtime_dir: Path, guard_boot_history_path: Path, control_audit_log: Path, guard_log_path: Path` | no |
| 47 | `artifact_service` | `name: str` | no |
| 58 | `artifact_status` | `name: str, path: Path, *, file_age_seconds_fn` | no |
| 71 | `artifact_summary` | `self, name: str, path: Path, *, safe_json_file_fn, tail_file_fn, safe_tail_lines_fn, file_age_seconds_fn, json_module` | no |
| 139 | `artifact_content` | `self, name: str, path: Path, *, max_lines: int, max_chars: int, safe_tail_lines_fn, tail_file_fn, file_age_seconds_fn, json_module` | no |
| 167 | `detail_payload` | `self, name: str, *, definitions: list[tuple[str, Path, str]], runtime_timeline_payload_fn, artifact_summary_fn, artifact_status_fn, artifact_content_fn, file_age_seconds_fn, max_lines: int=120` | no |
| 220 | `payload` | `self, definitions: list[tuple[str, Path, str]], *, artifact_summary_fn, artifact_status_fn, file_age_seconds_fn` | no |

## `services/runtime_console_frontdoor.py`

Lines: 391 | Functions/methods: 1 | Classes: 1

Classes: `RuntimeConsoleFrontdoorService` (L4)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `render_html` | `` | no |

## `services/runtime_control.py`

Lines: 797 | Functions/methods: 36 | Classes: 1

Classes: `RuntimeControlService` (L13)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 17 | `_runtime_fn` | `runtime_scope: dict[str, object], name: str` | no |
| 21 | `_write_restart_intent` | `*, restart_intent_path: Path \| None, restart_provenance_service, source: str, action: str, reason: str, replace: bool=True` | no |
| 45 | `autonomy_maintenance_summary` | `self, *, state_payload: dict, maintenance_py: Path, runtime_processes_module, strftime_fn=time.strftime` | no |
| 242 | `runtime_artifact_show_action` | `payload: dict, *, runtime_artifact_detail_payload_fn` | no |
| 250 | `guard_status_action` | `*, guard_status_payload_fn` | no |
| 255 | `guard_start_action` | `*, start_guard_fn, guard_status_payload_fn` | no |
| 260 | `guard_stop_action` | `*, stop_guard_fn, guard_status_payload_fn` | no |
| 265 | `guard_restart_action` | `*, restart_guard_fn, guard_status_payload_fn, core_status_payload_fn` | no |
| 270 | `nova_start_action` | `*, start_nova_core_fn, core_status_payload_fn` | no |
| 275 | `core_stop_action` | `*, stop_core_owned_process_fn, guard_status_payload_fn, core_status_payload_fn` | no |
| 280 | `core_restart_action` | `*, restart_core_fn, guard_status_payload_fn, core_status_payload_fn` | no |
| 285 | `webui_restart_action` | `*, restart_webui_fn, http_status_payload_fn` | no |
| 290 | `autonomy_maintenance_start_action` | `*, start_autonomy_maintenance_worker_fn, autonomy_maintenance_summary_fn` | no |
| 299 | `autonomy_maintenance_stop_action` | `*, stop_autonomy_maintenance_worker_fn, autonomy_maintenance_summary_fn` | no |
| 307 | `guard_control_action_from_runtime` | `self, payload: dict, *, runtime_scope: dict[str, object]` | no |
| 336 | `core_runtime_action_from_runtime` | `self, payload: dict, *, runtime_scope: dict[str, object]` | no |
| 367 | `autonomy_runtime_action_from_runtime` | `self, payload: dict, *, runtime_scope: dict[str, object]` | no |
| 387 | `_coerce_identity_pid` | `value` | no |
| 395 | `_is_autonomy_worker_process` | `process: dict` | no |
| 402 | `_autonomy_worker_processes` | `cls, processes: list[dict]` | no |
| 410 | `_autonomy_cycle_processes` | `cls, processes: list[dict]` | no |
| 417 | `autonomy_maintenance_identity_from_state` | `self, *, state_path: Path` | no |
| 429 | `detached_creation_flags` | `*, os_name: str=os.name, subprocess_module=subprocess` | no |
| 438 | `start_guard` | `self, *, venv_python: Path, guard_py: Path, runtime_dir: Path, base_dir: Path, guard_status_fn, restart_intent_path: Path \| None=None, restart_provenance_service=None, subprocess_module=subprocess, os_name: str=os.name` | no |
| 491 | `start_autonomy_maintenance_worker` | `self, *, venv_python: Path, maintenance_py: Path, state_path: Path, base_dir: Path, interval_sec: int, runtime_processes_module, subprocess_module=subprocess, os_name: str=os.name` | no |
| 528 | `start_nova_core` | `*, core_py: Path, core_status_fn, start_guard_fn` | no |
| 543 | `stop_guard` | `*, venv_python: Path, stop_guard_py: Path, base_dir: Path, subprocess_run=subprocess.run` | no |
| 563 | `schedule_detached_start` | `self, command: list[str], *, venv_python: Path, base_dir: Path, delay_seconds: float=1.5, cwd: Path \| None=None, remove_before_start: list[Path] \| None=None, subprocess_module=subprocess, os_name: str=os.name` | no |
| 608 | `core_identity_from_runtime` | `*, runtime_dir: Path, runtime_processes_module` | no |
| 612 | `stop_core_owned_process` | `self, *, runtime_dir: Path, core_py: Path, runtime_processes_module, psutil_module=psutil` | no |
| 644 | `stop_autonomy_maintenance_worker` | `self, *, state_path: Path, maintenance_py: Path, runtime_processes_module, psutil_module=psutil` | no |
| 674 | `restart_guard` | `*, venv_python: Path, guard_py: Path, base_dir: Path, guard_status_fn, core_status_fn, stop_guard_fn, schedule_detached_start_fn, start_guard_fn, restart_intent_path: Path \| None=None, restart_provenance_service=None` | no |
| 723 | `restart_core` | `*, guard_status_fn, stop_core_owned_process_fn, start_guard_fn, restart_intent_path: Path \| None=None, restart_provenance_service=None` | no |
| 754 | `shutdown_http_server_later` | `http_server, delay_seconds: float=0.25, *, threading_module=threading, time_module=time` | no |
| 764 | `_shutdown` | `` | no |
| 775 | `restart_webui` | `*, venv_python: Path, http_py: Path, bind_host: str, bind_port: int, base_dir: Path, schedule_detached_start_fn, shutdown_http_server_later_fn` | no |

## `services/runtime_heartbeat.py`

Lines: 146 | Functions/methods: 10 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 16 | `heartbeat_status_path` | `heartbeat_file: Path` | no |
| 20 | `heartbeat_log_path` | `heartbeat_file: Path` | no |
| 24 | `_ts` | `` | no |
| 28 | `_atomic_write_json` | `path: Path, data: dict` | no |
| 35 | `_append_log_line` | `path: Path, message: str` | no |
| 41 | `read_heartbeat_status` | `path: Path` | no |
| 51 | `_write_heartbeat_file` | `path: Path` | no |
| 56 | `heartbeat_write_once` | `heartbeat_file: Path, *, interval_sec: float=HEARTBEAT_INTERVAL_SECONDS, status_file: Path \| None=None, log_file: Path \| None=None, state: dict \| None=None, write_fn: Callable[[Path], None]=_write_heartbeat_file` | no |
| 119 | `start_heartbeat` | `heartbeat_file: Path, interval_sec: float=HEARTBEAT_INTERVAL_SECONDS, *, status_file: Path \| None=None, log_file: Path \| None=None` | no |
| 132 | `_loop` | `` | no |

## `services/runtime_process_state.py`

Lines: 245 | Functions/methods: 12 | Classes: 1

Classes: `RuntimeProcessStateService` (L7)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_runtime_fn` | `runtime_scope: dict[str, object], name: str` | no |
| 15 | `matches_script_process` | `cmdline: list[str], script_path: Path, cwd: str \| Path \| None=None` | no |
| 28 | `snapshot_script_process` | `self, process, script_path: Path, *, matches_script_process_fn=None` | no |
| 52 | `logical_leaf_processes` | `matches: list[dict]` | no |
| 66 | `logical_service_processes` | `self, script_path: Path, *, root_pid: int \| None=None, psutil_module, snapshot_script_process_fn=None, logical_leaf_processes_fn=None` | no |
| 122 | `cached_logical_service_processes` | `self, script_path: Path, *, root_pid: int \| None=None, cache_key: str \| None=None, max_age_seconds: float=0.0, process_scan_cache: dict, monotonic_fn, logical_service_processes_fn` | no |
| 147 | `cached_logical_service_processes_from_runtime` | `self, script_path: Path, *, runtime_scope: dict[str, object], root_pid: int \| None=None, cache_key: str \| None=None, max_age_seconds: float=0.0` | no |
| 168 | `select_logical_process` | `processes: list[dict], *, pid: int \| None=None, create_time: float \| None=None` | no |
| 182 | `prune_orphaned_guard_artifacts` | `logical_processes: list[dict], pid: int \| None, pid_live: bool, *, runtime_dir: Path, artifact_age_seconds_fn, remove_runtime_artifact_fn` | no |
| 194 | `prune_orphaned_guard_artifacts_from_runtime` | `logical_processes: list[dict], pid: int \| None, pid_live: bool, *, runtime_scope: dict[str, object]` | no |
| 212 | `prune_orphaned_core_artifacts` | `logical_processes: list[dict], pid: int \| None, pid_live: bool, heartbeat_age: int \| None, *, runtime_dir: Path, artifact_age_seconds_fn, remove_runtime_artifact_fn` | no |
| 225 | `prune_orphaned_core_artifacts_from_runtime` | `logical_processes: list[dict], pid: int \| None, pid_live: bool, heartbeat_age: int \| None, *, runtime_scope: dict[str, object]` | no |

## `services/runtime_restart_provenance.py`

Lines: 112 | Functions/methods: 5 | Classes: 1

Classes: `RuntimeRestartProvenanceService` (L10)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 16 | `_atomic_write_json` | `path: Path, payload: dict[str, Any]` | no |
| 22 | `build_intent` | `self, *, source: str, action: str, reason: str, requested_by: str='operator', planned: bool=True, ttl_seconds: int \| None=None, now: float \| None=None` | no |
| 49 | `read_pending_intent` | `self, path: Path, *, now: float \| None=None` | no |
| 61 | `write_pending_intent` | `self, path: Path, *, source: str, action: str, reason: str, requested_by: str='operator', planned: bool=True, ttl_seconds: int \| None=None, replace: bool=True, now: float \| None=None` | no |
| 98 | `consume_pending_intent` | `self, path: Path, *, now: float \| None=None` | no |

## `services/runtime_status.py`

Lines: 367 | Functions/methods: 10 | Classes: 1

Classes: `RuntimeStatusService` (L7)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_runtime_fn` | `runtime_scope: dict[str, object], name: str` | no |
| 15 | `guard_status_payload` | `*, runtime_dir: Path, guard_py: Path, include_fallback_scan: bool, pid_exists_fn, cached_logical_service_processes_fn, logical_service_processes_fn, prune_orphaned_guard_artifacts_fn, select_logical_process_fn, process_scan_cache_ttl_seconds: float` | no |
| 104 | `guard_status_payload_from_runtime` | `runtime_scope: dict[str, object], *, include_fallback_scan: bool=True` | no |
| 123 | `core_status_payload` | `*, runtime_dir: Path, core_py: Path, pid_exists_fn, heartbeat_age_seconds_fn, logical_service_processes_fn, prune_orphaned_core_artifacts_fn, select_logical_process_fn` | no |
| 200 | `http_status_payload` | `*, getpid_fn, process_fn` | no |
| 216 | `runtime_summary_payload` | `guard: dict \| None=None, core: dict \| None=None, webui: dict \| None=None` | no |
| 246 | `action_readiness_payload` | `guard: dict, core: dict, webui: dict` | no |
| 284 | `latest_runtime_event_for_service` | `timeline_payload: dict \| None, service: str` | no |
| 294 | `failure_reason_for_service` | `self, service: str, payload: dict, timeline_payload: dict \| None=None` | no |
| 359 | `runtime_failure_reasons_payload` | `self, guard: dict, core: dict, webui: dict, timeline_payload: dict \| None=None` | no |

## `services/runtime_timeline.py`

Lines: 328 | Functions/methods: 11 | Classes: 1

Classes: `RuntimeTimelineService` (L7)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_guard_recovery_anchor_ts` | `events: list[dict]` | no |
| 32 | `prune_stale_guard_recovery_noise` | `self, events: list[dict]` | no |
| 56 | `coerce_epoch_seconds` | `value` | no |
| 68 | `runtime_event` | `self, action: str, ts_value, source: str, service: str, level: str, title: str, detail: str` | no |
| 84 | `action_title` | `action: str` | no |
| 89 | `action_service` | `action: str` | no |
| 103 | `from_control_audit` | `self, control_audit_log, limit: int` | no |
| 158 | `parse_guard_log_line` | `self, line: str, *, time_module` | no |
| 260 | `from_guard_log` | `self, guard_log_path, limit: int, *, safe_tail_lines_fn, time_module` | no |
| 268 | `from_boot_history` | `self, boot_history_path, limit: int` | no |
| 303 | `payload` | `self, *, limit: int=24, control_audit_log, guard_log_path, boot_history_path, safe_tail_lines_fn, time_module` | no |

## `services/schedule_registry.py`

Lines: 231 | Functions/methods: 2 | Classes: 1

Classes: `ScheduledTask` (L40)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 155 | `get_task` | `name: str` | yes |
| 164 | `get_schedule_status` | `maintenance_state: dict \| None=None` | yes |

## `services/server_side_runtime.py`

Lines: 148 | Functions/methods: 4 | Classes: 1

Classes: `ServerSideRuntimeService` (L9)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `_normalize_settings` | `server_side: dict \| None` | no |
| 34 | `_probe_url` | `url: str, timeout_sec: float` | no |
| 49 | `status_payload` | `self, server_side: dict \| None, *, direct_base_url: str='http://127.0.0.1:8080', timeout_sec: float=2.5` | no |
| 123 | `render_apache_reverse_proxy_vhost` | `*, server_name: str='localhost', listen_port: int=80, upstream_url: str='http://127.0.0.1:8080'` | no |

## `services/session_admin.py`

Lines: 108 | Functions/methods: 10 | Classes: 1

Classes: `SessionAdminService` (L4)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `_runtime_fn` | `runtime_scope: dict[str, object], name: str` | no |
| 12 | `delete_session` | `session_id: str, *, session_lock, delete_session_fn, session_turns, session_owners, state_manager, persist_callback, on_session_end` | no |
| 34 | `delete_session_from_runtime` | `session_id: str, *, runtime_scope: dict[str, object], core_module` | no |
| 52 | `chat_auth_payload` | `*, chat_users_fn, chat_auth_source_fn, chat_users_path_fn` | no |
| 63 | `chat_user_upsert` | `username: str, password: str, *, normalize_user_id_fn, chat_users_fn, save_managed_chat_users_fn` | no |
| 76 | `chat_user_delete` | `username: str, *, normalize_user_id_fn, chat_users_fn, save_managed_chat_users_fn` | no |
| 88 | `session_delete_action` | `payload: dict, *, delete_session_fn, session_summaries_fn` | no |
| 93 | `chat_user_list_action` | `*, chat_auth_payload_fn` | no |
| 98 | `chat_user_upsert_action` | `payload: dict, *, chat_user_upsert_fn, chat_auth_payload_fn` | no |
| 103 | `chat_user_delete_action` | `payload: dict, *, chat_user_delete_fn, chat_auth_payload_fn` | no |

## `services/session_state.py`

Lines: 201 | Functions/methods: 9 | Classes: 2

Classes: `SubconsciousState` (L12), `SessionStateService` (L21)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 25 | `_recent_signal_counts` | `records: list[object]` | no |
| 35 | `_weak_signal_thresholds` | `subconscious_charter: dict, weak_crack_signals: set[str]` | no |
| 48 | `get_subconscious_pressure_config` | `subconscious_charter: dict, max_pressure_records: int` | no |
| 66 | `get_fulfillment_state` | `session: object` | yes |
| 72 | `set_fulfillment_state` | `session: object, state: Optional[dict]` | yes |
| 80 | `get_subconscious_state` | `session: object` | yes |
| 86 | `set_subconscious_state` | `session: object, state: Optional[SubconsciousState]` | yes |
| 94 | `get_subconscious_snapshot` | `session: object, subconscious_charter: dict, max_pressure_records: int` | yes |
| 143 | `update_subconscious_state` | `session: object, probe_result: dict, subconscious_charter: dict, max_pressure_records: int, *, chosen_route: Optional[str]=None` | yes |

## `services/sock_service.py`

Lines: 731 | Functions/methods: 29 | Classes: 6

Classes: `HardwareProfile` (L39), `ModelRecommendation` (L53), `OllamaInventory` (L62), `PolicyDiff` (L69), `WarmResult` (L76), `SockReport` (L84)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 97 | `_run_ps` | `script: str, timeout: int=12` | yes |
| 117 | `_ps_json` | `script: str, timeout: int=12` | yes |
| 130 | `_detect_cpu_windows` | `` | no |
| 140 | `_detect_ram_windows` | `` | no |
| 153 | `_find_nvidia_smi` | `` | yes |
| 168 | `_detect_gpu_windows` | `` | yes |
| 219 | `_detect_npu_windows` | `cpu_name: str` | yes |
| 244 | `_detect_cpu_fallback` | `` | no |
| 255 | `_detect_ram_fallback` | `` | no |
| 263 | `_detect_gpu_fallback` | `` | no |
| 288 | `scan_hardware` | `_run_ps_fn: Any=None` | no |
| 332 | `scan_ollama` | `ollama_base: str=OLLAMA_BASE, requests_get_fn: Any=None` | no |
| 368 | `_vram_estimate` | `model: str` | yes |
| 382 | `_effective_chat_vram` | `vram_gb: float, chat: str` | yes |
| 398 | `_is_stable_pair` | `chat: str, routing: str, vram_gb: float` | yes |
| 422 | `_chat_model` | `vram_gb: float, ram_gb: float` | no |
| 442 | `_routing_model` | `vram_gb: float, ram_gb: float` | no |
| 452 | `_routing_safe_for_pair` | `vram_gb: float, ram_gb: float, chat_name: str` | yes |
| 482 | `_vision_model` | `vram_gb: float` | no |
| 488 | `_stt_size` | `cpu_cores: int, ram_gb: float` | no |
| 496 | `recommend_models` | `hw: HardwareProfile` | no |
| 517 | `_read_policy` | `policy_path: Path=POLICY_PATH` | no |
| 524 | `build_diff` | `rec: ModelRecommendation, policy_path: Path=POLICY_PATH` | no |
| 542 | `apply_policy` | `rec: ModelRecommendation, policy_path: Path=POLICY_PATH` | no |
| 557 | `_fill_missing` | `inventory: OllamaInventory, rec: ModelRecommendation` | no |
| 576 | `_warm_single` | `model: str, ollama_base: str, timeout: float, requests_post_fn: Any=None` | no |
| 619 | `validate_concurrent_warm` | `rec: ModelRecommendation, ollama_base: str=OLLAMA_BASE, requests_post_fn: Any=None, routing_threshold_sec: float=_WARM_ROUTING_THRESHOLD_SEC, chat_threshold_sec: float=_WARM_CHAT_THRESHOLD_SEC` | yes |
| 652 | `run_sock` | `apply: bool=False, validate: bool=False, policy_path: Path=POLICY_PATH, ollama_base: str=OLLAMA_BASE, requests_get_fn: Any=None, requests_post_fn: Any=None` | no |
| 702 | `get_sock_status_keys` | `` | yes |

## `services/source_root_judgment.py`

Lines: 320 | Functions/methods: 16 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 21 | `_safe_text` | `value: Any, limit: int=600` | no |
| 25 | `_safe_dict` | `value: Any` | no |
| 29 | `_safe_list` | `value: Any` | no |
| 33 | `_safe_int` | `value: Any, default: int=0` | no |
| 40 | `_compact` | `value: Any, *, depth: int=0` | no |
| 58 | `_stable_hash` | `value: Any` | no |
| 63 | `_task_status` | `task: Any` | no |
| 67 | `_branch_status` | `branch: Any` | no |
| 71 | `_evidence_tools` | `evidence_rows: list[dict[str, Any]]` | no |
| 80 | `_looks_like_failed_evidence` | `row: dict[str, Any]` | no |
| 84 | `_has_specialized_judgment` | `evidence_rows: list[dict[str, Any]]` | no |
| 88 | `_restart_provenance_operator_reason` | `source_type: str, work_class: str, source_payload: dict[str, Any]` | no |
| 107 | `build_source_root_judgment` | `branch_id: str, *, work_tree_module: Any=None` | no |
| 226 | `build_source_root_operator_notice` | `judgment: dict[str, Any]` | no |
| 267 | `publish_source_root_operator_notice` | `judgment: dict[str, Any], *, outbox_path: Path \| None=None, operator_outbox_service: Any=None, now_fn: Any=None, uuid_fn: Any=None` | no |
| 301 | `render_source_root_judgment` | `judgment: dict[str, Any]` | no |

## `services/storage_watch.py`

Lines: 182 | Functions/methods: 5 | Classes: 1

Classes: `StorageWatchService` (L9)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `_file_stats` | `directory: Path` | no |
| 29 | `_tree_stats` | `directory: Path, *, exclude_names: set[str] \| None=None` | no |
| 48 | `_recursive_file_stats` | `directory: Path` | no |
| 64 | `_zip_stats` | `directory: Path` | no |
| 79 | `snapshot` | `self, *, base_dir: Path, runtime_dir: Path, kidney_config: dict \| None=None` | no |

## `services/subconscious_control.py`

Lines: 134 | Functions/methods: 4 | Classes: 1

Classes: `SubconsciousControlService` (L12)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 7 | `_seam_label` | `value: str` | no |
| 16 | `latest_report` | `runs_root: Path` | no |
| 27 | `status_summary` | `latest: dict, definitions: list[dict], latest_report_path: Path` | no |
| 68 | `live_summary` | `*, limit: int, pressure_config: dict, session_turns_items: list[tuple[str, list[tuple[str, str]]]], session_owner_lookup, session_state_peek_fn, get_snapshot_fn` | no |

## `services/subconscious_reporting.py`

Lines: 95 | Functions/methods: 5 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 6 | `_summary_value` | `payload: object, key: str` | no |
| 12 | `_seam_label` | `target_seam: str` | no |
| 17 | `build_training_backlog_summary` | `snapshot: dict` | no |
| 46 | `build_robust_weakness_summary` | `family_summary: object` | no |
| 52 | `_extract_items` | `name: str` | no |

## `services/subconscious_review_authority.py`

Lines: 466 | Functions/methods: 9 | Classes: 1

Classes: `SubconsciousReviewAuthorityService` (L65)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 10 | `_runtime_pressure_blocked_reason` | `prefix: str, runtime_pressure: dict[str, Any]` | no |
| 14 | `_default_supervisor_review` | `signal: dict[str, Any], gate: dict[str, Any]` | no |
| 31 | `_default_fulfillment_review` | `signal: dict[str, Any], gate: dict[str, Any]` | no |
| 48 | `_default_route_comparison_review` | `signal: dict[str, Any], gate: dict[str, Any]` | no |
| 69 | `_runtime_pressure` | `signal: dict[str, Any]` | no |
| 103 | `_candidate_backlog` | `signal: dict[str, Any]` | no |
| 127 | `_probe_snapshot` | `signal: dict[str, Any], *, probe_turn_routes_fn: Optional[Callable[..., dict[str, Any]]]=None, session_factory: Optional[Callable[[], object]]=None` | no |
| 155 | `_supervisor_reflection_snapshot` | `signal: dict[str, Any], *, session_factory: Optional[Callable[[], object]]=None, supervisor_process_turn_fn: Optional[Callable[..., dict[str, Any]]]=None` | no |
| 196 | `review_candidate` | `self, signal: dict[str, Any], gate: dict[str, Any], *, fulfillment_review_fn: Optional[Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]]=None, supervisor_review_fn: Optional[Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]]=None, route_review_fn: Optional[Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]]=None, probe_turn_routes_fn: Optional[Callable[..., dict[str, Any]]]=None, session_factory: Optional[Callable[[], object]]=None, evaluate_supervisor_rules_fn: Optional[Callable[..., dict[str, Any]]]=None, supervisor_has_route_fn: Optional[Callable[[dict[str, Any]], bool]]=None, fulfillment_viability_fn: Optional[Callable[..., dict[str, Any]]]=None, supervisor_process_turn_fn: Optional[Callable[..., dict[str, Any]]]=None` | no |

## `services/subconscious_review_judgment.py`

Lines: 419 | Functions/methods: 18 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 23 | `_clean_text` | `value: object` | no |
| 27 | `_lower_text` | `value: object` | no |
| 31 | `_is_invalid_evidence` | `row: dict[str, Any]` | no |
| 38 | `_latest_subconscious_branch` | `work_tree_module: Any` | no |
| 49 | `_branch_by_id` | `work_tree_module: Any, branch_id: str` | no |
| 59 | `_evidence_task_titles` | `work_tree_module: Any, branch_id: str` | no |
| 72 | `_evidence_label` | `row: dict[str, Any], task_titles: dict[str, str]` | no |
| 83 | `_evidence_summary` | `*, evidence_rows: list[dict[str, Any]], task_titles: dict[str, str], target_seam: str, signal_name: str` | no |
| 124 | `_evidence_tools` | `evidence_rows: list[dict[str, Any]]` | no |
| 137 | `_gate_from_payload` | `payload: dict[str, Any]` | no |
| 151 | `_classification` | `*, gate: dict[str, Any], evidence: dict[str, Any], authority: dict[str, Any]` | no |
| 192 | `_next_work` | `*, verdict: str, classification: str, target_seam: str, signal_name: str, preferred_owner: str, evidence: dict[str, Any]` | no |
| 220 | `is_no_owner_root_repair_judgment` | `judgment: dict[str, Any]` | no |
| 226 | `_parse_rendered_judgment` | `result_text: str` | no |
| 243 | `parse_subconscious_review_judgment_result` | `result: object` | no |
| 262 | `latest_subconscious_review_judgment_for_branch` | `work_tree_module: Any, branch_id: str` | no |
| 280 | `build_subconscious_review_judgment` | `*, branch_id: str='', work_tree_module: Any, review_authority_service: Any=SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE, probe_turn_routes_fn: Any=None, session_factory: Any=None, evaluate_supervisor_rules_fn: Any=None, supervisor_has_route_fn: Any=None, fulfillment_viability_fn: Any=None, supervisor_process_turn_fn: Any=None` | no |
| 395 | `render_subconscious_review_judgment` | `judgment: dict[str, Any]` | no |

## `services/subconscious_runtime.py`

Lines: 49 | Functions/methods: 4 | Classes: 1

Classes: `ConfiguredSubconsciousService` (L12)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `__init__` | `self, subconscious_charter: dict` | no |
| 20 | `get_snapshot` | `self, session: object` | no |
| 27 | `update_state` | `self, session: object, probe_result: dict, *, chosen_route: Optional[str]=None` | no |
| 42 | `pressure_config` | `self` | no |

## `services/subconscious_work_tree_triage.py`

Lines: 613 | Functions/methods: 10 | Classes: 1

Classes: `SubconsciousWorkTreeTriageService` (L83)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 25 | `_fallback_review_context_for_source` | `source_key: str` | no |
| 87 | `_scenario_review_context` | `family_id: str, signal_name: str, suggested_test_name: str, variation_results: list[dict[str, Any]] \| None` | no |
| 153 | `_review_context` | `cls, signal_name: str, target_seam: str, *, family_id: str='', suggested_test_name: str='', variation_results: list[dict[str, Any]] \| None=None` | no |
| 231 | `classify_owner` | `self, signal_name: str, target_seam: str` | no |
| 291 | `_review_contract` | `preferred_owner: str, route_hint: str` | no |
| 303 | `_family_review_guidance` | `*, family_id: str, target_seam: str, signal_name: str, suggested_test_name: str, preferred_owner: str` | no |
| 413 | `_evidence_sequence` | `*, target_seam: str, signal_name: str` | no |
| 448 | `build_signal` | `self, *, family_id: str, target_seam: str, signal_name: str, suggested_test_name: str, rationale: str, urgency: str, robustness: float, variation_results: list[dict[str, Any]] \| None=None, runtime_context: dict[str, Any] \| None=None` | no |
| 565 | `review_gate` | `self, signal: dict[str, Any]` | no |
| 574 | `_decision` | `approved: bool, status: str, reason: str` | no |

## `services/supervisor_authority.py`

Lines: 123 | Functions/methods: 4 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 14 | `default_rule_handlers` | `` | no |
| 18 | `result_is_explicitly_owned` | `rule_name: str, result: dict[str, Any], *, phase: str` | no |
| 35 | `register_rule` | `rules: list[dict[str, Any]], name: str, rule: Callable[..., dict[str, Any]], *, priority: int=100, phases: tuple[str, ...]=('handle',)` | no |
| 54 | `evaluate_rules` | `rules: list[dict[str, Any]], user_text: str, *, manager: Any=None, turns: Optional[list[tuple[str, str]]]=None, phase: str='handle', entry_point: str=''` | no |

## `services/supervisor_patterns.py`

Lines: 9 | Functions/methods: 1 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 6 | `normalize_text` | `text: str` | no |

## `services/supervisor_probes.py`

Lines: 255 | Functions/methods: 14 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `status_line` | `name: str, status: str, message: str` | no |
| 14 | `normalize_decision` | `entry_point: str, session_id: str, session_summary: dict, current_decision: dict, *, normalize_text_fn: Callable[[str], str]` | no |
| 54 | `recent_issue_names` | `recent_reflections: list[dict]` | no |
| 77 | `suggest_hardening` | `issue: str` | no |
| 92 | `looks_like_identity_location_turn` | `current: dict` | no |
| 109 | `looks_like_suspicious_fallback` | `current: dict` | no |
| 133 | `build_suggestions` | `context: dict, findings: list[dict]` | no |
| 148 | `probe_entrypoint_parity` | `context: dict` | no |
| 164 | `probe_continuation_drop` | `context: dict` | no |
| 178 | `probe_pending_action_leak` | `context: dict` | no |
| 190 | `probe_override_consistency` | `context: dict` | no |
| 203 | `probe_thin_answer_frequency` | `context: dict` | no |
| 228 | `probe_identity_location_route` | `context: dict` | no |
| 238 | `probe_rule_coverage` | `context: dict` | no |

## `services/supervisor_registry.py`

Lines: 4 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `services/supervisor_runtime.py`

Lines: 18 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `services/test_session_control.py`

Lines: 685 | Functions/methods: 31 | Classes: 1

Classes: `TestSessionControlService` (L14)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 18 | `test_sessions_root` | `runtime_dir: Path` | no |
| 21 | `generated_test_session_definitions_dir` | `self, runtime_dir: Path` | no |
| 25 | `test_session_definitions_dir` | `base_dir: Path` | no |
| 29 | `_iter_definition_files` | `root: Path` | no |
| 33 | `_relative_definition_name` | `path: Path, root: Path` | no |
| 37 | `_normalize_session_lookup` | `value: str` | no |
| 41 | `_candidate_report_keys` | `session_path: str` | no |
| 59 | `_slugify_task_id` | `value: str` | no |
| 65 | `_file_fingerprint` | `path: Path` | no |
| 72 | `_latest_audit_by_file` | `runtime_dir: Path` | no |
| 96 | `all_test_session_definition_roots` | `self, *, base_dir: Path, runtime_dir: Path` | no |
| 103 | `test_session_run_action` | `payload: dict, *, run_test_session_definition_fn` | no |
| 109 | `generated_pack_run_action` | `payload: dict, *, run_generated_test_session_pack_fn` | no |
| 117 | `generated_queue_run_next_action` | `*, run_next_generated_work_queue_item_fn` | no |
| 122 | `generated_queue_investigate_action` | `payload: dict, *, investigate_generated_work_queue_item_fn` | no |
| 131 | `generated_queue_operator_note` | `item: dict` | no |
| 135 | `investigate_generated_work_queue_item` | `session_file: str='', *, session_id: str='', user_id: str='operator', generated_work_queue_fn, resolve_operator_macro_fn, render_operator_macro_prompt_fn, normalize_user_id_fn, assert_session_owner_fn, process_chat_fn, session_summaries_fn` | no |
| 162 | `available_test_session_definitions` | `definition_roots: list[tuple[Path, str]], limit: int=80` | no |
| 199 | `resolve_test_session_definition` | `session_name: str, definitions: list[dict]` | no |
| 221 | `generated_definition_priority_tuple` | `item: dict` | no |
| 234 | `generated_work_queue_status_rank` | `status: str` | no |
| 245 | `report_status_label` | `diff_count: int, flagged_probe_count: int, runtime_failure_count: int=0` | no |
| 254 | `test_session_report_summaries` | `self, test_sessions_root: Path, limit: int=24` | no |
| 264 | `_sort_key` | `path: Path` | no |
| 353 | `latest_generated_report_by_file` | `self, reports: list[dict], limit: int=200` | no |
| 365 | `create_real_world_task_definition` | `self, payload: dict, *, runtime_dir: Path, available_definitions_fn` | no |
| 435 | `real_world_task_create_action` | `self, payload: dict, *, runtime_dir: Path, available_definitions_fn` | no |
| 449 | `generated_work_queue` | `self, definitions: list[dict], reports: list[dict], limit: int=24, runtime_dir: Path \| None=None` | no |
| 550 | `run_test_session_definition` | `self, session_file: str, *, runner_path: Path, venv_python: Path, base_dir: Path, resolve_definition_fn, available_definitions_fn, report_summaries_fn, subprocess_run=subprocess.run, timeout_sec: int=180` | no |
| 598 | `run_generated_test_session_pack` | `self, limit: int=12, *, mode: str='recent', available_definitions_fn, run_test_session_definition_fn, report_summaries_fn, generated_work_queue_fn` | no |
| 649 | `run_next_generated_work_queue_item` | `self, *, generated_work_queue_fn, run_test_session_definition_fn` | no |

## `services/test_session_definitions.py`

Lines: 36 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 9 | `iter_definition_files` | `root: Path` | yes |
| 28 | `count_definition_files` | `root: Path` | no |
| 32 | `relative_definition_name` | `path: Path, root: Path` | no |

## `services/tool_console.py`

Lines: 90 | Functions/methods: 4 | Classes: 1

Classes: `ToolConsoleService` (L35)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 38 | `__init__` | `self, *, decide_turn_fn: Callable[[str], list], execute_planned_action_fn: Callable[[str, list], object], describe_tools_fn: Callable[[], str], direct_tools: list[str] \| None=None` | no |
| 52 | `coerce_output` | `value` | no |
| 59 | `list_tools_text` | `self` | no |
| 69 | `handle_tools` | `self, user_text: str, *, emit_status: Callable[[str], None] \| None=None` | no |

## `services/tool_execution.py`

Lines: 70 | Functions/methods: 4 | Classes: 1

Classes: `ToolExecutionService` (L10)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 13 | `__init__` | `self, *, policy_loader: Callable[[], dict], active_user_getter: Callable[[], Optional[str]], base_dir: Path, registry_service: Any` | no |
| 26 | `build_tool_context` | `self, *, is_admin: bool=False, extra: Optional[dict]=None` | no |
| 41 | `tool_error_message` | `tool_name: str, reason: str` | no |
| 55 | `execute_registered_tool` | `self, tool_name: str, args: dict, *, is_admin: bool=False, extra: Optional[dict]=None` | no |

## `services/tool_execution_contracts.py`

Lines: 3 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `services/tool_registry.py`

Lines: 208 | Functions/methods: 9 | Classes: 2

Classes: `ToolInvocationEvent` (L20), `ToolRegistryService` (L63)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 38 | `to_dict` | `self` | yes |
| 66 | `__init__` | `self, registry: ToolRegistry, manifest_path: Path, events_log_path: Path` | yes |
| 80 | `get_manifest` | `self` | yes |
| 102 | `invalidate_manifest_cache` | `self` | yes |
| 106 | `_append_event` | `self, event: ToolInvocationEvent` | yes |
| 120 | `run_tool` | `self, name: str, args: dict[str, Any], context: ToolContext` | yes |
| 198 | `list_tools` | `self` | yes |
| 202 | `describe_tools` | `self` | yes |
| 206 | `get_tool` | `self, name: str` | yes |

## `services/validation_artifact_truth.py`

Lines: 306 | Functions/methods: 9 | Classes: 1

Classes: `ValidationArtifactTruthService` (L114)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 22 | `_safe_int` | `value: Any, default: int=0` | no |
| 29 | `_safe_read_json` | `path: Path` | no |
| 36 | `_parse_timestamp` | `value: Any` | no |
| 49 | `_artifact_timestamp` | `path: Path, record: dict[str, Any]` | no |
| 62 | `_compact_route_summary` | `record: dict[str, Any]` | no |
| 69 | `_failure_kind` | `record: dict[str, Any]` | no |
| 85 | `_compact_failure` | `path: Path, record: dict[str, Any], failure_kind: str, observed_at_epoch: float` | no |
| 107 | `_load_regression_status` | `path: Path \| None` | no |
| 117 | `payload` | `self, *, runtime_dir: Path, regression_status_path: Path \| None=None, limit: int=400, window_before_regression_sec: int=1800, window_after_regression_sec: int=300, window_start_epoch: float \| None=None, window_end_epoch: float \| None=None, regression_status_label: str \| None=None, regression_returncode: int \| None=None, regression_generated_at: str \| None=None` | no |

## `services/voice_interaction.py`

Lines: 100 | Functions/methods: 9 | Classes: 1

Classes: `VoiceInteractionService` (L33)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 20 | `_policy_whisper_size` | `policy_path: Path=POLICY_PATH` | no |
| 29 | `_voice_runtime_not_bound` | `*_args: Any, **_kwargs: Any` | no |
| 36 | `__init__` | `self, *, speaker_factory=None, whisper_model_cls=None, whisper_size_fn: Callable[[], str] \| None=None, record_seconds_fn: Callable[[int], Any] \| None=None, transcribe_fn: Callable[[Any, Any], str] \| None=None, chat_fn: Callable[[str, str, str], str] \| None=None, fallback_chat_fn: Callable[[str], str] \| None=None` | no |
| 55 | `whisper_size` | `self` | no |
| 58 | `load_whisper` | `self, *, device: str='cpu', compute_type: str='int8', size: str \| None=None` | no |
| 64 | `record_seconds` | `self, seconds: int=6` | no |
| 67 | `transcribe` | `self, model, audio_int16` | no |
| 70 | `chat` | `self, text: str, *, session_id: str='', user_id: str=''` | no |
| 91 | `speak` | `self, text: str, *, rate: int=175` | no |

## `services/web_research_session.py`

Lines: 80 | Functions/methods: 11 | Classes: 2

Classes: `WebResearchPage` (L7), `WebResearchSessionStore` (L15)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 18 | `__init__` | `self` | no |
| 24 | `query` | `self` | no |
| 28 | `results` | `self` | no |
| 32 | `cursor` | `self` | no |
| 35 | `result_count` | `self` | no |
| 38 | `has_results` | `self` | no |
| 41 | `set_results` | `self, query: str, rows: list[tuple[float, str, str]]` | no |
| 46 | `set_state` | `self, query: str, rows: list[tuple[float, str, str]], cursor: int=0` | no |
| 51 | `next_page` | `self, max_results: int` | no |
| 74 | `remaining_count` | `self` | no |
| 77 | `clear` | `self` | no |

## `services/work_tree_decision_adapter.py`

Lines: 417 | Functions/methods: 21 | Classes: 3

Classes: `WorkTreeDecisionOutcome` (L19), `IdentityDecisionScores` (L50), `WorkTreeDecisionAdapter` (L137)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 22 | `__init__` | `self, *, decision_type: str, work_identity_key: str, timestamp: float=0.0, branch_id: str='', outcome: str='', outcome_timestamp: float=0.0` | no |
| 39 | `to_dict` | `self` | no |
| 53 | `__init__` | `self, *, work_identity_key: str` | no |
| 62 | `record_outcome` | `self, *, decision_type: str, outcome: str` | yes |
| 88 | `apply_decay` | `self, *, decay_factor: float=0.99, age_seconds: int=86400` | yes |
| 108 | `get_bias` | `self` | yes |
| 124 | `to_dict` | `self` | no |
| 140 | `__init__` | `self, *, state_path: Optional[Path]=None, stale_success_seconds: float=5 * 60` | no |
| 151 | `_canonical_decision_type` | `decision_type: str` | no |
| 163 | `_save_state` | `self` | no |
| 173 | `_load_state` | `self` | no |
| 217 | `record_decision` | `self, *, decision_type: str, work_identity_key: str, branch_id: str='', timestamp: float=0.0` | yes |
| 246 | `record_outcome` | `self, *, work_identity_key: str, decision_type: str, outcome: str` | yes |
| 280 | `_close_stale_successes_locked` | `self, *, now_ts: float` | yes |
| 305 | `flush_stale_pending_successes` | `self, *, now_ts: float=0.0` | yes |
| 313 | `get_bias_for_identity` | `self, *, work_identity_key: str` | yes |
| 329 | `apply_bias_to_probability` | `self, *, work_identity_key: str, decision_type: str, base_probability: float=0.5` | yes |
| 371 | `get_scores_for_identity` | `self, *, work_identity_key: str` | yes |
| 381 | `get_recent_decisions` | `self, *, limit: int=10, work_identity_key: str=''` | yes |
| 390 | `reset_state` | `self, *, clear_persistence: bool=False` | yes |
| 404 | `get_adapter_state` | `self` | yes |

## `services/work_tree_operator_hold.py`

Lines: 70 | Functions/methods: 3 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 23 | `_as_dict` | `value: Any` | no |
| 27 | `_text` | `value: Any, limit: int=240` | no |
| 31 | `node_is_operator_hold` | `node: dict[str, Any] \| None` | no |

## `services/work_tree_pressure_snapshot.py`

Lines: 260 | Functions/methods: 12 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 8 | `_as_dict` | `value: Any` | no |
| 12 | `_as_list` | `value: Any` | no |
| 16 | `_as_int` | `value: Any, default: int=0` | no |
| 23 | `_text` | `value: Any, limit: int=240` | no |
| 27 | `_enum_value` | `value: Any` | no |
| 31 | `_branch_total` | `tree_payload: dict` | no |
| 39 | `_current_task_payload` | `tasks: list[Any]` | no |
| 62 | `_node_from_branch` | `branch: Any, current_task: dict` | no |
| 77 | `_release_stale_ready_node` | `node: dict` | no |
| 94 | `_pressure_from_nodes` | `*, counts: dict, nodes: list[dict], total_trees: int, active_trees: int, stale_count: int=0, oldest_open_age_min: int=0, branches: list[dict] \| None=None` | no |
| 183 | `build_work_tree_pressure_snapshot` | `work_trees_payload: dict \| None, *, branches: list[dict] \| None=None` | no |
| 213 | `build_work_tree_pressure_snapshot_from_module` | `work_tree_module: Any` | no |

## `services/work_tree_seeding.py`

Lines: 1185 | Functions/methods: 43 | Classes: 1

Classes: `WorkTreeSeedingService` (L57)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 70 | `__init__` | `self` | no |
| 75 | `_normalize_intake_text` | `text: str` | no |
| 82 | `_identity_terms` | `cls, text: str, *, limit: int=10` | no |
| 87 | `build_work_identity_key` | `cls, text: str` | yes |
| 104 | `_work_identity_label` | `cls, text: str` | no |
| 111 | `_tree_identity_key` | `tree` | no |
| 118 | `_tree_status_value` | `tree` | no |
| 122 | `_find_tree_by_identity_key` | `self, *, work_tree_module, work_identity_key: str, preferred_tree_id: str=''` | no |
| 166 | `_looks_like_followup_continuation` | `cls, message: str` | no |
| 170 | `should_continue_active_identity` | `cls, *, message: str, active_work_identity: str=''` | no |
| 178 | `_terms` | `identity_key: str` | no |
| 198 | `_keywords` | `cls, text: str` | no |
| 208 | `_title_similarity` | `cls, candidate_title: str, requested_title: str` | no |
| 223 | `_extract_creation_intent_seed` | `text: str` | no |
| 230 | `_tree_is_recent_or_active` | `tree, *, now_epoch: float, recent_seconds: int` | no |
| 243 | `_find_similar_existing_tree_id` | `self, *, work_tree_module, title_seed: str, similarity_threshold: float=0.62, recent_seconds: int=12 * 3600` | no |
| 276 | `_mark_reuse` | `self, *, tree_id: str, request_text: str` | no |
| 284 | `_mark_new` | `self, *, tree_id: str, request_text: str` | no |
| 292 | `_ensure_tree_identity_meta` | `self, *, work_tree_module, tree_id: str, work_identity_key: str, identity_intent: str, source: str, user_id: str` | no |
| 327 | `_append_continuation_if_needed` | `self, *, work_tree_module, tree_id: str, request_text: str` | no |
| 383 | `_get_intent_overlap_strength` | `self, *, active_work_identity: str, new_work_identity: str` | yes |
| 393 | `_terms` | `identity_key: str` | no |
| 422 | `_should_branch_instead_of_continue` | `self, *, active_tree_id: str, message: str, active_work_identity: str, new_work_identity: str, work_tree_module` | yes |
| 446 | `_tree_is_complete` | `self, *, work_tree_module, tree_id: str` | yes |
| 486 | `_detect_completion_signals` | `self, *, message: str` | no |
| 489 | `_mark_tree_complete` | `self, *, work_tree_module, tree_id: str, reason: str='completion_detected'` | yes |
| 518 | `should_prevent_over_continuation` | `self, *, active_work_identity: str, new_message: str, active_tree_id: str='', work_tree_module=None` | yes |
| 548 | `_apply_adaptive_bias_to_continue` | `self, *, work_identity_key: str, should_continue: bool, message: str, active_work_identity: str` | yes |
| 586 | `_apply_adaptive_bias_to_branch` | `self, *, work_identity_key: str, should_branch: bool, overlap_strength: str` | yes |
| 615 | `_root_branch_id_for_tree` | `*, work_tree_module, tree_id: str` | no |
| 622 | `_branch_count_for_tree` | `*, work_tree_module, tree_id: str` | no |
| 632 | `_flush_pending_successes` | `self, *, now_ts: float` | no |
| 644 | `_record_work_decision` | `self, *, work_identity_key: str, decision_type: str, tree_id: str, branch_id: str, branch_count: int, immediate_success: bool=False, failure_identity_key: str=''` | no |
| 726 | `resolve_seeded_tree` | `self, *, work_tree_module, title_seed: str, source: str, user_id: str='', nova_core_module=None, active_tree_id: str='', active_work_identity: str=''` | no |
| 1003 | `consume_reuse_note` | `self, *, tree_id: str, request_text: str, max_age_seconds: int=120` | no |
| 1025 | `_llm_decompose` | `task_text: str, *, nova_core_module=None` | yes |
| 1083 | `looks_like_explicit_work_tree_request` | `message: str` | no |
| 1087 | `should_seed_system_work_tree` | `*, message: str, source: str='', operator_mode: str=''` | yes |
| 1096 | `_split_steps` | `message: str, *, limit: int=4` | no |
| 1121 | `_infer_tool` | `step_text: str` | no |
| 1125 | `_allowed_tools` | `preferred_tool: str` | no |
| 1156 | `_step_branch_title` | `index: int, step_text: str` | no |
| 1162 | `create_seeded_tree` | `self, *, work_tree_module, title_seed: str, source: str, user_id: str='', nova_core_module=None, active_tree_id: str='', active_work_identity: str=''` | no |

## `services/work_tree_signal_ingestion.py`

Lines: 6929 | Functions/methods: 180 | Classes: 1

Classes: `WorkTreeSignalIngestionService` (L5000)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 133 | `_strip_inactive_resolution_notes` | `notes: str` | yes |
| 143 | `_same_artifact_path` | `left: Any, right: Any` | no |
| 149 | `_port_ownership_for` | `status_payload: dict[str, Any], port: int` | no |
| 156 | `_model_runtime_model` | `status_payload: dict[str, Any], ollama_health: dict[str, Any]` | no |
| 165 | `_model_runtime_verify_request` | `status_payload: dict[str, Any], ollama_health: dict[str, Any], *, probe_chat: bool` | no |
| 187 | `_model_runtime_port_request` | `` | no |
| 191 | `_model_runtime_task_sequence` | `status_payload: dict[str, Any], ollama_health: dict[str, Any], *, probe_chat: bool, inspect_port_first: bool=False, include_action_ledger: bool=False` | no |
| 237 | `_as_int` | `value: Any, default: int=0` | no |
| 244 | `_memory_health_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 377 | `_control_status_dependency_signals` | `status_payload: dict[str, Any]` | no |
| 427 | `_model_runtime_dependency_signals` | `status_payload: dict[str, Any]` | no |
| 569 | `_voice_status_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 634 | `_vision_status_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 699 | `_component_running` | `component: Any` | no |
| 714 | `_control_status_runtime_signals` | `status_payload: dict[str, Any]` | no |
| 769 | `_control_status_maintenance_signals` | `status_payload: dict[str, Any]` | no |
| 813 | `_autonomy_maintenance_error_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 880 | `_runtime_failure_reason_signals_from_status` | `status_payload: dict[str, Any]` | no |
| 918 | `_runtime_restart_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 986 | `_runtime_restart_provenance_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1034 | `_storage_watch_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1073 | `_temporal_pressure_signal_from_status` | `status_payload: dict[str, Any]` | yes |
| 1163 | `_patch_pipeline_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1218 | `_data_pipeline_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1325 | `_status_word` | `value: Any` | no |
| 1329 | `_status_is_bad` | `value: Any` | no |
| 1334 | `_route_trace_issue_steps` | `trace: Any, *, stage_terms: set[str] \| None=None` | no |
| 1362 | `_read_source_task` | `title: str, path: str` | no |
| 1371 | `_find_source_task` | `title: str, pattern: str, scope: str='services tests'` | no |
| 1380 | `_task_tools` | `item: dict[str, Any]` | no |
| 1392 | `_source_root_judgment_task` | `` | no |
| 1400 | `_append_source_root_judgment_task` | `source: str, signal: dict[str, Any]` | no |
| 1435 | `_frontdoor_cli_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1473 | `_operator_outbox_actionable_open_count` | `status_payload: dict[str, Any]` | no |
| 1483 | `_operator_control_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1533 | `_policy_gates_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1589 | `_session_identity_auth_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1632 | `_identity_profile_answers_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1687 | `_conversation_routing_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1736 | `_supervisor_fulfillment_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1777 | `_reply_quality_contracts_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1817 | `_retrieval_knowledge_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1856 | `_weather_location_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1901 | `_installer_packaging_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 1970 | `_tts_audio_output_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 2010 | `_safety_envelope_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 2057 | `_metrics_ops_journal_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 2096 | `_core_steward_reflection_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 2141 | `_wiring_inventory_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 2220 | `_looks_like_source_root_file_gap` | `gap: str` | no |
| 2230 | `_gap_subject` | `gap: str` | no |
| 2238 | `_gap_evidence_task` | `gap: str, *, read_title: str='Read gap evidence from the repository', find_title: str='Find missing wiring references for the gap'` | no |
| 2260 | `_source_root_gap_evidence_task` | `first_gap: str` | no |
| 2268 | `_source_wiring_probe_gap_evidence_task` | `first_gap: str` | no |
| 2276 | `_edfi_capability_profile_evidence_task` | `profile_path: str` | no |
| 2286 | `_edfi_capability_profile_primary_read_item` | `` | no |
| 2294 | `_edfi_capability_profile_read_evidence_satisfied` | `branch_id: str, *, expected_path: str=''` | no |
| 2332 | `_hold_edfi_capability_profile_branch_until_read_evidence` | `*, branch: Any, note: str, now: datetime` | no |
| 2400 | `_edfi_capability_profile_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 2526 | `_has_edfi_core_surface` | `status_payload: dict[str, Any]` | no |
| 2537 | `_edfi_core_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 2573 | `_has_data_lane_edfi_bisd_surface` | `status_payload: dict[str, Any]` | no |
| 2582 | `_data_lane_edfi_bisd_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 2623 | `_data_pipeline_evidence_task` | `blocked_rows: list[dict[str, Any]]` | no |
| 2642 | `_source_root_inventory_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 2714 | `_source_wiring_probe_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 2787 | `_release_runtime_truth_from_status` | `status_payload: dict[str, Any]` | no |
| 2792 | `_release_drift_suppresses_closure_signals` | `status_payload: dict[str, Any]` | no |
| 2800 | `_mission_suppresses_ambient_governance_ingest` | `status_payload: dict[str, Any]` | no |
| 2811 | `_root_closure_inventory_signals_from_status` | `status_payload: dict[str, Any]` | no |
| 2922 | `_self_repair_closure_inventory_signals_from_status` | `status_payload: dict[str, Any]` | no |
| 3006 | `_autonomy_orchestrator_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 3102 | `_subconscious_status_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 3157 | `_action_ledger_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 3188 | `_os_capability_ledger_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 3304 | `_http_conversation_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 3333 | `_validation_artifact_truth_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 3481 | `_test_profile_inventory_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 3632 | `_alert_surface` | `alert: str` | no |
| 3639 | `_self_check_unowned_alerts` | `alerts: list[str], routed_signals: list[dict[str, Any]]` | no |
| 3675 | `_self_check_signal_from_status` | `status_payload: dict[str, Any], routed_signals: list[dict[str, Any]]` | no |
| 3705 | `_self_check_routed_signals_from_status` | `status_payload: dict[str, Any]` | no |
| 3716 | `_has_self_check_surface` | `status_payload: dict[str, Any]` | no |
| 3720 | `_has_dependency_surface` | `status_payload: dict[str, Any]` | no |
| 3730 | `_has_model_runtime_surface` | `status_payload: dict[str, Any]` | no |
| 3749 | `_has_runtime_surface` | `status_payload: dict[str, Any]` | no |
| 3753 | `_has_maintenance_surface` | `status_payload: dict[str, Any]` | no |
| 3757 | `_has_autonomy_maintenance_error_surface` | `status_payload: dict[str, Any]` | no |
| 3767 | `_has_runtime_failures_surface` | `status_payload: dict[str, Any]` | no |
| 3771 | `_has_runtime_restart_surface` | `status_payload: dict[str, Any]` | no |
| 3775 | `_has_storage_watch_surface` | `status_payload: dict[str, Any]` | no |
| 3791 | `_has_patch_pipeline_surface` | `status_payload: dict[str, Any]` | no |
| 3804 | `_has_data_pipeline_surface` | `status_payload: dict[str, Any]` | no |
| 3816 | `_has_edfi_capability_profile_surface` | `status_payload: dict[str, Any]` | no |
| 3829 | `_has_frontdoor_cli_surface` | `status_payload: dict[str, Any]` | no |
| 3833 | `_has_operator_control_surface` | `status_payload: dict[str, Any]` | no |
| 3848 | `_has_policy_gates_surface` | `status_payload: dict[str, Any]` | no |
| 3865 | `_has_session_identity_auth_surface` | `status_payload: dict[str, Any]` | no |
| 3869 | `_has_identity_profile_answers_surface` | `status_payload: dict[str, Any]` | no |
| 3881 | `_has_conversation_routing_surface` | `status_payload: dict[str, Any]` | no |
| 3894 | `_has_supervisor_fulfillment_surface` | `status_payload: dict[str, Any]` | no |
| 3906 | `_has_reply_quality_contracts_surface` | `status_payload: dict[str, Any]` | no |
| 3918 | `_has_retrieval_knowledge_surface` | `status_payload: dict[str, Any]` | no |
| 3932 | `_has_weather_location_surface` | `status_payload: dict[str, Any]` | no |
| 3945 | `_has_installer_packaging_surface` | `status_payload: dict[str, Any]` | no |
| 3956 | `_has_tts_audio_output_surface` | `status_payload: dict[str, Any]` | no |
| 3968 | `_has_safety_envelope_surface` | `status_payload: dict[str, Any]` | no |
| 3982 | `_has_metrics_ops_journal_surface` | `status_payload: dict[str, Any]` | no |
| 3995 | `_has_core_steward_reflection_surface` | `status_payload: dict[str, Any]` | no |
| 4008 | `_has_wiring_inventory_surface` | `status_payload: dict[str, Any]` | no |
| 4019 | `_has_source_root_inventory_surface` | `status_payload: dict[str, Any]` | no |
| 4032 | `_has_source_wiring_probe_surface` | `status_payload: dict[str, Any]` | no |
| 4043 | `_has_root_closure_inventory_surface` | `status_payload: dict[str, Any]` | no |
| 4055 | `_has_self_repair_closure_inventory_surface` | `status_payload: dict[str, Any]` | no |
| 4067 | `_has_autonomy_orchestrator_surface` | `status_payload: dict[str, Any]` | no |
| 4079 | `_has_subconscious_status_surface` | `status_payload: dict[str, Any]` | no |
| 4090 | `_has_action_ledger_surface` | `status_payload: dict[str, Any]` | no |
| 4102 | `_has_os_capability_ledger_surface` | `status_payload: dict[str, Any]` | no |
| 4115 | `_has_http_conversation_surface` | `status_payload: dict[str, Any]` | no |
| 4126 | `_has_validation_artifact_truth_surface` | `status_payload: dict[str, Any]` | no |
| 4139 | `_has_test_profile_inventory_surface` | `status_payload: dict[str, Any]` | no |
| 4156 | `_has_regression_surface` | `status_payload: dict[str, Any]` | no |
| 4161 | `_has_release_surface` | `status_payload: dict[str, Any]` | no |
| 4166 | `_has_memory_surface` | `status_payload: dict[str, Any]` | no |
| 4178 | `_has_generated_queue_surface` | `status_payload: dict[str, Any]` | no |
| 4197 | `_has_voice_surface` | `status_payload: dict[str, Any]` | no |
| 4210 | `_has_vision_surface` | `status_payload: dict[str, Any]` | no |
| 4223 | `_voice_status_reports_clear` | `status_payload: dict[str, Any]` | no |
| 4233 | `_vision_status_reports_clear` | `status_payload: dict[str, Any]` | no |
| 4243 | `_generated_queue_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 4305 | `_has_tool_events_surface` | `status_payload: dict[str, Any]` | no |
| 4319 | `_tool_events_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 4365 | `_release_readiness_signal_from_status` | `status_payload: dict[str, Any]` | no |
| 4549 | `_next_sequence_task` | `branch_id: str, normalized: dict[str, Any]` | no |
| 4563 | `_first_sequence_task` | `normalized: dict[str, Any]` | no |
| 4570 | `_sequence_has_tool` | `normalized: dict[str, Any], tool_name: str` | no |
| 4581 | `_branch_has_failed_execution_evidence` | `branch_id: str` | no |
| 4594 | `_branch_has_failed_evidence` | `branch_id: str` | no |
| 4598 | `_branch_has_source_root_failed_judgment` | `branch_id: str` | no |
| 4609 | `_source_root_judgment_evidence_failed` | `row: dict[str, Any]` | no |
| 4618 | `_is_source_root_failed_evidence_hold_task` | `task: Any` | no |
| 4626 | `_source_root_sequence_operator_hold_satisfied` | `branch_id: str` | no |
| 4649 | `_drop_stale_source_root_judgment_tasks` | `branch_id: str` | no |
| 4676 | `_repair_stale_source_root_read_task` | `branch_id: str, normalized: dict[str, Any]` | no |
| 4729 | `_recover_source_root_failed_evidence_hold` | `branch: Any, normalized: dict[str, Any]` | no |
| 4760 | `_source_root_operator_reason_from_judgment_text` | `text: str` | no |
| 4772 | `_branch_source_root_operator_reason` | `branch_id: str` | no |
| 4788 | `_expected_source_root_operator_reason` | `normalized: dict[str, Any]` | no |
| 4809 | `_source_root_judgment_prerequisites_satisfied` | `branch_id: str, normalized: dict[str, Any]` | no |
| 4820 | `_source_root_sequence_repeats_when_active` | `normalized: dict[str, Any]` | no |
| 4824 | `_restart_completed_source_root_sequence_pass` | `branch_id: str, normalized: dict[str, Any]` | no |
| 4844 | `_sequence_item_expected_tools` | `item: dict[str, Any]` | no |
| 4856 | `_sequence_item_satisfied` | `branch_id: str, item: dict[str, Any]` | no |
| 4890 | `_sequence_evidence_result_valid` | `row: dict[str, Any]` | no |
| 4896 | `_has_capability_manifest_surface` | `status_payload: dict` | no |
| 4908 | `_capability_gap_signal_from_status` | `status_payload: dict` | yes |
| 5007 | `ingest_signal` | `self, signal: dict[str, Any]` | no |
| 5091 | `ingest_status_snapshot` | `self, status_payload: dict[str, Any]` | no |
| 5307 | `sync_status_snapshot` | `self, status_payload: dict[str, Any]` | no |
| 5867 | `_resolve_operator_control_from_outbox_truth` | `self, status_payload: dict[str, Any]` | no |
| 5911 | `dedupe_signal_branches` | `self` | no |
| 5959 | `_branch_recency_key` | `branch: Any` | no |
| 5963 | `_is_live_signal_branch` | `self, branch: Any` | no |
| 5973 | `_retire_signal_branch` | `self, branch: Any, *, note: str, now: datetime` | no |
| 5996 | `_archive_signal_branch` | `self, branch: Any, *, note: str, now: datetime` | no |
| 6019 | `resolve_edfi_capability_profile_branches` | `self, *, reason: str='Saved Ed-Fi capability profile evidence reports a healthy district data layer.'` | no |
| 6095 | `resolve_signal_branches` | `self, *, signal_class: str, source: str='', reason: str='', payload_match: dict[str, Any] \| None=None` | no |
| 6157 | `source_key_for_signal` | `self, signal: dict[str, Any]` | no |
| 6160 | `_preserve_inactive_signal_branch` | `self, *, branch: Any, note: str, now: datetime` | no |
| 6227 | `resolve_inactive_signal_branches` | `self, *, signal_class: str, source: str, active_source_keys: set[str], reason: str='', resolution_mode: str='resolve'` | no |
| 6302 | `_find_signal_tree` | `self` | no |
| 6320 | `_ensure_signal_tree` | `self` | no |
| 6361 | `_find_branch_by_source_key` | `self, tree_id: str, source_key: str, *, open_only: bool` | no |
| 6371 | `_deserves_persisted_work` | `self, normalized: dict[str, Any]` | no |
| 6378 | `_apply_branch_update` | `self, branch, normalized: dict[str, Any], *, reopen: bool, first_seen: bool=False` | no |
| 6789 | `_normalize_signal` | `self, signal: dict[str, Any]` | no |
| 6841 | `_signal_fingerprint_key` | `*, signal_class: str, source: str, title: str, fingerprint: Any, payload: dict[str, Any]` | no |
| 6868 | `_bucket_for_work_class` | `work_class: str` | no |
| 6872 | `_score_for_signal` | `severity: str, actionability: str` | no |
| 6888 | `_branch_why_summary` | `normalized: dict[str, Any]` | no |

## `smoke_test.py`

Lines: 9 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `stop_guard.py`

Lines: 78 | Functions/methods: 4 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 18 | `warn` | `msg` | no |
| 19 | `ok` | `msg` | no |
| 21 | `read_core_identity` | `` | no |
| 27 | `main` | `` | no |

## `subconscious_config.py`

Lines: 121 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `subconscious_live_simulator.py`

Lines: 944 | Functions/methods: 13 | Classes: 6

Classes: `LiveSimulationTurn` (L26), `LiveSimulationScenario` (L35), `LiveSimulationResult` (L44), `LiveSimulationFamily` (L54), `LiveSimulationFamilyResult` (L61), `TrainingPriorityItem` (L75)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 84 | `_route_viable` | `probe: dict, route_name: str` | no |
| 90 | `_should_observe_live_route` | `scenario: LiveSimulationScenario, turn: LiveSimulationTurn` | no |
| 97 | `_observed_live_route` | `scenario: LiveSimulationScenario, turn: LiveSimulationTurn, probe: dict, sim_session: ConversationSession, recent_turns: list[tuple[str, str]], *, pending_action: Optional[dict]=None` | no |
| 133 | `simulate_live_scenario` | `scenario: LiveSimulationScenario, *, session: Optional[ConversationSession]=None` | yes |
| 194 | `_classify_consistency` | `hit_count: int, total_variations: int` | no |
| 204 | `_score_ranked_weakness` | `*, hit_count: int, total_variations: int, noisy_variations: int` | no |
| 236 | `_rank_family_weaknesses` | `*, repeated_signals: list[dict], top_backlog_candidates: list[dict], noise_summary: dict` | no |
| 312 | `build_training_priorities` | `family_result: LiveSimulationFamilyResult \| dict` | yes |
| 382 | `simulate_live_family` | `family: LiveSimulationFamily` | yes |
| 469 | `simulate_live_use` | `scenarios: list[LiveSimulationScenario]` | yes |
| 480 | `simulate_live_families` | `families: list[LiveSimulationFamily]` | yes |
| 488 | `build_default_live_scenarios` | `` | yes |
| 530 | `build_default_live_scenario_families` | `` | yes |

## `subconscious_route_probe.py`

Lines: 111 | Functions/methods: 5 | Classes: 1

Classes: `RoutePressureRecord` (L42)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 19 | `_route_payload` | `probe_result: Mapping[str, Any], route_name: str` | no |
| 25 | `_route_viable` | `probe_result: Mapping[str, Any], route_name: str` | no |
| 29 | `_route_notes` | `probe_result: Mapping[str, Any], route_name: str` | no |
| 34 | `_append_unique` | `target: list[str], values: list[str]` | no |
| 54 | `analyze_route_pressure` | `probe_result: Mapping[str, Any], *, chosen_route: str \| None=None` | yes |

## `subconscious_runner.py`

Lines: 311 | Functions/methods: 11 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 27 | `select_live_scenario_families` | `family_ids: list[str] \| None=None` | no |
| 44 | `_priority_to_dict` | `item: TrainingPriorityItem` | no |
| 48 | `_family_result_to_dict` | `result: object` | no |
| 79 | `build_unattended_report` | `family_results: list[object], *, label: str='default'` | no |
| 99 | `render_markdown_summary` | `report: dict` | no |
| 156 | `_slugify` | `text: str` | no |
| 161 | `_session_definition_filename` | `family_id: str, variation_id: str` | no |
| 165 | `build_generated_session_definitions` | `report: dict` | no |
| 211 | `write_generated_session_definitions` | `report: dict, *, output_root: Path=GENERATED_DEFINITIONS_ROOT` | no |
| 240 | `write_report_bundle` | `report: dict, *, output_root: Path=RUNTIME_ROOT, stamp: str \| None=None` | no |
| 269 | `main` | `argv: list[str] \| None=None` | no |

## `subconscious_training_backlog.py`

Lines: 136 | Functions/methods: 5 | Classes: 2

Classes: `TrainingBacklogItem` (L21), `TrainingBacklog` (L31)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 39 | `_clean_signal_list` | `values: Any` | no |
| 48 | `_clean_crack_counts` | `values: Any` | no |
| 65 | `_clean_record_window` | `values: Any` | no |
| 78 | `_priority_for` | `signal: str, occurrences: int, *, active: bool, replan_requested: bool` | no |
| 88 | `build_training_backlog` | `subconscious_snapshot: Mapping[str, Any]` | no |

## `supervisor.py`

Lines: 223 | Functions/methods: 8 | Classes: 1

Classes: `Supervisor` (L35)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 18 | `_result_is_explicitly_owned` | `rule_name: str, result: dict[str, Any], *, phase: str` | no |
| 36 | `__init__` | `self` | no |
| 49 | `_rule_handlers` | `` | no |
| 52 | `register_rule` | `self, name: str, rule: Callable[..., dict[str, Any]], *, priority: int=100, phases: tuple[str, ...]=('handle',)` | no |
| 69 | `evaluate_rules` | `self, user_text: str, *, manager: Any=None, turns: Optional[list[tuple[str, str]]]=None, phase: str='handle', entry_point: str=''` | no |
| 144 | `reset` | `self` | no |
| 149 | `process_turn` | `self, *, entry_point: str, session_id: str, session_summary: Optional[dict], current_decision: Optional[dict], recent_records: Optional[list[dict]]=None, recent_reflections: Optional[list[dict]]=None` | no |
| 216 | `_remember` | `self, decision: dict` | no |

## `task_engine.py`

Lines: 237 | Functions/methods: 5 | Classes: 1

Classes: `TaskResult` (L6)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 7 | `__init__` | `self, allow_llm=True, message=None` | no |
| 22 | `_looks_like_explicit_web_research` | `text: str` | no |
| 54 | `extract_requirements` | `user_text: str, config: dict \| None=None` | no |
| 61 | `_looks_like_profile_statement` | `text: str` | no |
| 204 | `analyze_request` | `user_text: str, config: dict \| None=None` | no |

## `tools/__init__.py`

Lines: 12 | Functions/methods: 0 | Classes: 0

No Python functions or methods.

## `tools/base_tool.py`

Lines: 60 | Functions/methods: 4 | Classes: 3

Classes: `ToolInvocationError` (L7), `ToolContext` (L12), `NovaTool` (L31)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 20 | `as_dict` | `self` | no |
| 41 | `check_policy` | `self, args: dict[str, Any], context: ToolContext` | no |
| 46 | `run` | `self, args: dict[str, Any], context: ToolContext` | no |
| 49 | `metadata` | `self` | no |

## `tools/codegen_tool.py`

Lines: 192 | Functions/methods: 6 | Classes: 1

Classes: `CodegenTool` (L98)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 17 | `_norm_text` | `value: object` | no |
| 21 | `_safe_path` | `value: object` | no |
| 35 | `_validate_spec` | `spec: dict[str, Any], max_files: int` | no |
| 58 | `_render_preview_content` | `path: str, spec_name: str, spec_purpose: str, kind: str, intent: str` | no |
| 108 | `check_policy` | `self, args: dict[str, Any], context: ToolContext` | no |
| 121 | `run` | `self, args: dict[str, Any], context: ToolContext` | no |

## `tools/edfi_tool.py`

Lines: 73 | Functions/methods: 2 | Classes: 1

Classes: `EdFiExploreTool` (L19)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 15 | `_render` | `payload: dict[str, Any]` | no |
| 29 | `run` | `self, args: dict[str, Any], context: ToolContext` | no |

## `tools/filesystem_tool.py`

Lines: 149 | Functions/methods: 7 | Classes: 1

Classes: `FileSystemTool` (L11)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 39 | `check_policy` | `self, args: dict, context: ToolContext` | no |
| 48 | `_allowed_root` | `self, context: ToolContext` | no |
| 54 | `_safe_path` | `self, user_path: str, context: ToolContext` | no |
| 66 | `_cmd_ls` | `self, args: dict, context: ToolContext` | no |
| 78 | `_cmd_read` | `self, args: dict, context: ToolContext` | no |
| 90 | `_cmd_find` | `self, args: dict, context: ToolContext` | no |
| 141 | `run` | `self, args: dict, context: ToolContext` | no |

## `tools/import_dashboard_reports.py`

Lines: 204 | Functions/methods: 6 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 31 | `_module_name` | `root: Path, path: Path` | no |
| 36 | `_normalize_table` | `table: str` | no |
| 44 | `_scan_file` | `path: Path, known_tables: set[str] \| None=None` | no |
| 85 | `_load_known_tables` | `vendor_dictionary: Path \| None` | no |
| 96 | `build_report_index` | `reports_root: Path, vendor_dictionary: Path \| None=None` | no |
| 185 | `main` | `` | no |

## `tools/import_eschoolplus_data_dictionary.py`

Lines: 142 | Functions/methods: 4 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 20 | `_clean_lines` | `text: str` | no |
| 24 | `_extract_columns` | `section: str` | no |
| 65 | `build_index` | `pdf_path: Path, *, content_start_page: int=31` | no |
| 128 | `main` | `argv: list[str]` | no |

## `tools/os_capability_tool.py`

Lines: 95 | Functions/methods: 4 | Classes: 1

Classes: `OsCapabilityTool` (L40)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 14 | `_safe_dict` | `value: Any` | no |
| 18 | `_parse_request` | `args: dict[str, Any]` | no |
| 50 | `check_policy` | `self, args: dict[str, Any], context: ToolContext` | no |
| 60 | `run` | `self, args: dict[str, Any], context: ToolContext` | no |

## `tools/patch_tool.py`

Lines: 38 | Functions/methods: 2 | Classes: 1

Classes: `PatchTool` (L6)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 16 | `check_policy` | `self, args: dict, context: ToolContext` | no |
| 29 | `run` | `self, args: dict, context: ToolContext` | no |

## `tools/registry.py`

Lines: 513 | Functions/methods: 36 | Classes: 1

Classes: `ToolRegistry` (L79)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 60 | `_load_manifest` | `` | no |
| 70 | `_append_tool_event` | `payload: dict[str, Any]` | no |
| 80 | `__init__` | `self, tools: list[NovaTool]` | no |
| 84 | `get` | `self, name: str` | no |
| 87 | `list_metadata` | `self` | no |
| 100 | `describe` | `self` | no |
| 115 | `run_tool` | `self, name: str, args: dict[str, Any], context: ToolContext` | no |
| 182 | `build_default_registry` | `` | no |
| 196 | `build_core_tool_exports` | `runtime_scope: dict[str, Any]` | no |
| 201 | `tool_ls` | `subfolder: str=''` | no |
| 207 | `tool_read` | `path: str` | no |
| 210 | `tool_find` | `keyword: str, subfolder: str=''` | no |
| 219 | `tool_health` | `` | no |
| 222 | `tool_system_check` | `` | no |
| 225 | `tool_queue_status` | `` | no |
| 228 | `tool_temporal_review` | `payload: str=''` | no |
| 239 | `tool_screen` | `` | no |
| 242 | `tool_camera` | `` | no |
| 245 | `tool_edfi_explore` | `action: str='health', connection_id: str='district-main', resource: str='', limit: int=25, offset: int=0, query: str='', namespace: str=''` | no |
| 267 | `tool_pipeline` | `command_text: str='pipeline help'` | no |
| 280 | `tool_patch_preview_apply` | `preview: str` | no |
| 307 | `tool_patch_preview_approve` | `preview: str` | no |
| 338 | `tool_update_now` | `` | no |
| 348 | `tool_update_now_confirm` | `token: str=''` | no |
| 358 | `tool_update_now_cancel` | `` | no |
| 364 | `tool_nova_pulse` | `` | no |
| 371 | `tool_nova_self_status` | `` | no |
| 380 | `tool_core_health_brief` | `feed: str=''` | no |
| 391 | `tool_core_thinning` | `feed: str=''` | no |
| 405 | `tool_search` | `query: str` | no |
| 414 | `tool_web_fetch` | `url: str` | no |
| 424 | `tool_wikipedia_lookup` | `query: str` | no |
| 433 | `tool_stackexchange_search` | `query: str` | no |
| 444 | `tool_web_search` | `query: str` | no |
| 458 | `tool_web_gather` | `url: str` | no |
| 469 | `tool_web_research` | `query: str, continue_mode: bool=False` | no |

## `tools/research_tool.py`

Lines: 44 | Functions/methods: 2 | Classes: 1

Classes: `ResearchTool` (L6)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 16 | `check_policy` | `self, args: dict, context: ToolContext` | no |
| 26 | `run` | `self, args: dict, context: ToolContext` | no |

## `tools/runtime_processes.py`

Lines: 108 | Functions/methods: 5 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `normalize_identity_path` | `value: str \| Path` | no |
| 21 | `matches_script_process` | `cmdline: list[str] \| tuple[str, ...] \| None, script_path: str \| Path, cwd: str \| Path \| None=None` | no |
| 39 | `logical_service_processes` | `script_path: str \| Path` | no |
| 72 | `select_logical_process` | `processes: list[dict[str, Any]], *, pid: int \| None=None, create_time: float \| None=None` | no |
| 95 | `read_identity_file` | `path: Path` | no |

## `tools/system_tool.py`

Lines: 126 | Functions/methods: 4 | Classes: 1

Classes: `SystemTool` (L73)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 9 | `_completed_text` | `process` | no |
| 13 | `_format_generated_queue_status` | `queue: dict` | no |
| 83 | `check_policy` | `self, args: dict, context: ToolContext` | no |
| 95 | `run` | `self, args: dict, context: ToolContext` | no |

## `tools/temporal_review_tool.py`

Lines: 119 | Functions/methods: 6 | Classes: 1

Classes: `TemporalReviewTool` (L73)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 12 | `_safe_dict` | `value: Any` | no |
| 16 | `_maybe_json` | `value: Any` | no |
| 28 | `_load_input_payload` | `args: dict[str, Any]` | no |
| 53 | `_pressure_from_input` | `item: Any` | no |
| 83 | `check_policy` | `self, args: dict[str, Any], context: ToolContext` | no |
| 92 | `run` | `self, args: dict[str, Any], context: ToolContext` | no |

## `tools/vision_tool.py`

Lines: 61 | Functions/methods: 3 | Classes: 1

Classes: `VisionTool` (L13)

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 9 | `_completed_text` | `process` | no |
| 23 | `check_policy` | `self, args: dict, context: ToolContext` | no |
| 35 | `run` | `self, args: dict, context: ToolContext` | no |

## `tts_piper.py`

Lines: 66 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 16 | `_prefer_windows_sapi` | `` | no |
| 21 | `_fallback_tts` | `message: str` | no |

## `tts_say.py`

Lines: 77 | Functions/methods: 2 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 11 | `_select_preferred_voice` | `engine` | no |
| 39 | `main` | `` | no |

## `voice.py`

Lines: 75 | Functions/methods: 6 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 6 | `_fallback_chat` | `text: str` | no |
| 25 | `record_push_to_talk` | `seconds=6` | no |
| 29 | `transcribe_whisper` | `model, audio_int16` | no |
| 33 | `ask_nova` | `text` | no |
| 37 | `speak` | `text` | no |
| 41 | `main` | `` | no |

## `work_tree.py`

Lines: 2643 | Functions/methods: 115 | Classes: 0

| Line | Function or method | Signature | Docstring |
|---:|---|---|---|
| 29 | `_path_from_env` | `value: str, *, base_dir: Path` | no |
| 34 | `_resolve_initial_db_path` | `` | no |
| 46 | `_runtime_dir_for_db_path` | `db_path: Path` | no |
| 128 | `_now` | `` | no |
| 132 | `_dt` | `value: datetime` | no |
| 136 | `_parse_dt` | `value: str` | no |
| 140 | `_json_dump` | `value: object` | no |
| 144 | `_json_load` | `value: str \| None, default` | no |
| 154 | `_json_list` | `value: str \| None` | no |
| 161 | `_json_dict` | `value: str \| None` | no |
| 168 | `_json_object_dict` | `value: str \| None` | no |
| 181 | `_append_db_guard` | `event: str, detail: str` | no |
| 191 | `_db_journal_path` | `` | no |
| 195 | `_memory_db_target` | `db_path: Path` | no |
| 200 | `_memory_fallback_disk_path` | `db_path: Path, unique: bool=False` | no |
| 211 | `_sync_memory_db_to_disk` | `` | no |
| 245 | `_activate_memory_db_fallback` | `requested_path: Path \| None=None` | no |
| 267 | `_guard_db_header` | `stage: str` | no |
| 290 | `_log_db_access` | `` | no |
| 303 | `_is_retryable_db_error` | `exc: Exception` | no |
| 318 | `_attempt_db_recovery` | `exc: Exception` | no |
| 335 | `_db_connect` | `` | no |
| 367 | `_db_transaction` | `` | no |
| 410 | `_apply_schema_migrations` | `connection: sqlite3.Connection` | no |
| 487 | `_ensure_branch_column` | `name: str, sql_type: str` | no |
| 512 | `_ensure_db` | `` | no |
| 517 | `_clear_in_memory` | `` | no |
| 524 | `_load_persisted_state` | `` | no |
| 600 | `reload_persisted_state` | `` | no |
| 610 | `_set_db_path` | `db_path: str \| Path` | no |
| 633 | `_save_tree_record` | `connection: sqlite3.Connection, tree: WorkTree` | no |
| 652 | `_save_branch_record` | `connection: sqlite3.Connection, branch: Branch` | no |
| 696 | `_save_task_record` | `connection: sqlite3.Connection, task: Task` | no |
| 718 | `_persist_tree_state` | `tree_id: str` | no |
| 739 | `_branch_tasks` | `branch_id: str` | no |
| 745 | `_tree_branches` | `tree_id: str` | no |
| 751 | `_normalize_tool_names` | `value: list[str] \| tuple[str, ...] \| None` | no |
| 763 | `default_tree_allowed_tools` | `` | no |
| 767 | `_tree_policy` | `tree: WorkTree \| None` | no |
| 774 | `_tree_allowed_tools` | `tree: WorkTree \| None` | no |
| 780 | `_tree_requires_explicit_allow` | `tree: WorkTree \| None` | no |
| 785 | `_branch_declared_tools` | `branch: Branch` | no |
| 789 | `_branch_candidate_tool` | `branch: Branch` | no |
| 805 | `_task_declared_tools` | `task: Task \| None` | no |
| 815 | `_task_declared_tools_allowed_by_tree` | `task: Task \| None, tree: WorkTree \| None` | no |
| 820 | `_tool_governance_status` | `tree: WorkTree \| None, branch: Branch, tool_name: str` | no |
| 837 | `_governance_payload` | `tree: WorkTree \| None, branch: Branch, tool_name: str, reason: str` | no |
| 852 | `_blocked_dependencies` | `branch: Branch` | no |
| 862 | `_branch_ancestor_ids` | `branch_id: str` | no |
| 876 | `_refresh_branch_state` | `branch: Branch` | no |
| 918 | `_refresh_tree_state` | `tree_id: str, persist: bool=False` | no |
| 937 | `create_tree` | `title: str, meta: dict[str, object] \| None=None` | no |
| 952 | `create_branch` | `tree_id: str, title: str, bucket: str, parent_branch_id: str \| None=None` | no |
| 973 | `create_task` | `branch_id: str, title: str, meta: dict[str, object] \| None=None` | no |
| 987 | `get_tree` | `tree_id: str` | no |
| 991 | `list_trees` | `` | no |
| 995 | `get_branch` | `branch_id: str` | no |
| 999 | `list_tree_branches` | `tree_id: str` | no |
| 1003 | `list_branch_tasks` | `branch_id: str` | no |
| 1007 | `list_tree_tasks` | `tree_id: str` | no |
| 1013 | `_compact_tool_result_text` | `result: object, *, max_chars: int=8000` | no |
| 1024 | `record_task_evidence` | `*, branch_id: str, task_id: str, tool_name: str, tool_args: list[str] \| None, result: object` | no |
| 1065 | `delete_branch_evidence` | `branch_id: str, *, evidence_ids: list[str] \| None=None, task_id: str \| None=None, only_invalid: bool=False` | no |
| 1114 | `reopen_task` | `task_id: str, *, meta_updates: dict[str, object] \| None=None` | no |
| 1136 | `list_branch_evidence` | `branch_id: str, *, limit: int=20` | no |
| 1170 | `list_visual_trees` | `limit: int \| None=None` | no |
| 1175 | `_list_visual_trees_locked` | `limit: int \| None=None` | no |
| 1214 | `save_tree` | `tree: WorkTree` | no |
| 1221 | `archive_tree` | `tree_id: str, reason: str \| None=None` | no |
| 1270 | `add_branch_to_tree` | `tree_id: str, title: str, bucket: str, parent_branch_id: str \| None=None` | no |
| 1295 | `mark_task_complete` | `task_id: str` | no |
| 1314 | `mark_task_dropped` | `task_id: str, reason: str=''` | no |
| 1337 | `mark_task_blocked` | `task_id: str, reason: str=''` | no |
| 1361 | `update_blocked_task` | `task_id: str, *, title: str='', reason: str=''` | no |
| 1394 | `update_task_meta` | `task_id: str, meta_updates: dict[str, object]` | no |
| 1424 | `next_open_branch` | `tree_id: str` | no |
| 1476 | `initialize_tree` | `title: str, meta: dict[str, object] \| None=None` | no |
| 1502 | `add_task_to_branch` | `branch_id: str, title: str, meta: dict[str, object] \| None=None` | no |
| 1513 | `touch_branch` | `branch_id: str` | no |
| 1522 | `recompute_branch_score` | `branch: Branch` | no |
| 1534 | `is_tree_complete` | `tree_id: str` | no |
| 1549 | `add_dependency` | `branch_id: str, depends_on_branch_id: str` | no |
| 1568 | `is_branch_ready` | `branch_id: str` | no |
| 1577 | `set_branch_tools` | `branch_id: str, required_tools: list[str] \| None=None, allowed_tools: list[str] \| None=None, preferred_tool: str \| None=None` | no |
| 1609 | `set_tree_execution_policy` | `tree_id: str, allowed_tools: list[str] \| None=None, require_explicit_allow: bool=True` | no |
| 1627 | `set_tree_policy` | `tree_id: str, allowed_tools: list[str] \| None=None, require_explicit_allow: bool=True` | no |
| 1635 | `is_tooling_ready` | `branch_id: str` | no |
| 1648 | `_next_open_task` | `branch_id: str` | no |
| 1660 | `_current_visible_task` | `branch_id: str` | no |
| 1674 | `_extract_read_path_from_task_title` | `title: str` | no |
| 1699 | `_extract_ls_path_from_task_title` | `title: str` | no |
| 1715 | `_extract_test_symbol_from_task_title` | `title: str` | no |
| 1730 | `_extract_find_keyword_from_task_title` | `title: str` | no |
| 1757 | `_extract_patch_preview_name` | `task: Task` | no |
| 1774 | `_extract_generated_session_file` | `task: Task` | no |
| 1791 | `_tool_args_for_task` | `tool_name: str, task: Task` | no |
| 1875 | `_scoped_task_target` | `task: Task` | no |
| 1882 | `_is_scoped_stabilization_task` | `task: Task` | no |
| 1888 | `_scoped_target_valid` | `task: Task` | no |
| 1908 | `_is_invalid_tool_result` | `tool_name: str, result: object` | yes |
| 1913 | `_restore_task_after_failed_execution` | `task: Task, branch: Branch` | no |
| 1920 | `_rebalance_branch_tool_for_task` | `branch: Branch, task: Task \| None` | no |
| 1932 | `list_autonomous_options` | `tree_id: str` | no |
| 1974 | `_preview_next_open_branch` | `tree_id: str` | no |
| 1999 | `_preview_recommended_tool` | `tree: WorkTree \| None, branch: Branch, task: Task \| None` | no |
| 2015 | `_preview_next_autonomous_step` | `tree_id: str` | no |
| 2067 | `next_autonomous_step` | `tree_id: str, decide_next_step_fn: DecisionCallback \| None=None` | no |
| 2171 | `execute_autonomous_step` | `tree_id: str, execute_planned_action_fn: Callable[[str, list[str] \| None], object], decide_next_step_fn: DecisionCallback \| None=None` | no |
| 2364 | `run_autonomous_loop` | `tree_id: str, max_steps: int=100, execute_planned_action_fn: Callable[[str, list[str] \| None], object] \| None=None, decide_next_step_fn: DecisionCallback \| None=None` | no |
| 2392 | `get_visual_tree_data` | `tree_id: str` | yes |
| 2398 | `_get_visual_tree_data_locked` | `tree_id: str` | no |
| 2488 | `inspect_tree` | `tree_id: str` | no |
| 2503 | `_branch_summary` | `branch: Branch` | no |
| 2571 | `active_tree_session_summary` | `tree_id: str` | no |
| 2590 | `format_tree_snapshot` | `tree_id: str` | no |

## `work_tree_contracts.py`

Lines: 91 | Functions/methods: 0 | Classes: 7

Classes: `TreeStatus` (L7), `BranchStatus` (L13), `TaskStatus` (L22), `ToolStatus` (L30), `WorkTree` (L38), `Branch` (L49), `Task` (L81)

No Python functions or methods.

## `nova.ps1`

Lines: 1582 | PowerShell functions: 52

`Join-Args` (L65), `Ensure-Python` (L69), `Get-NovaNormalizedPath` (L79), `Test-NovaCommandLineHasPath` (L89), `Get-BootstrapPythonDescription` (L101), `Invoke-NovaNative` (L124), `Invoke-BootstrapPython` (L130), `Invoke-NovaInstall` (L162), `Invoke-NovaPackageBuild` (L242), `Invoke-NovaPackageVerify` (L252), `Invoke-NovaInstallerBuild` (L262), `Invoke-NovaInstallerVerify` (L272), `Invoke-NovaPackageLedger` (L282), `Invoke-NovaInstallerLedger` (L292), `Invoke-NovaPackagePromote` (L302), `Invoke-NovaInstallerPromote` (L312), `Invoke-NovaPackageStatus` (L322), `Invoke-NovaInstallerStatus` (L332), `Invoke-NovaPackageReadiness` (L342), `Invoke-NovaPackageValidate` (L352), `Invoke-NovaReleaseClean` (L362), `Invoke-NovaWiringCheck` (L372), `Invoke-NovaInstallerReadiness` (L382), `Wait-NovaCoreSignal` (L392), `Invoke-NovaSmoke` (L407), `Ensure-Logs` (L455), `Run-Py` (L459), `Run-Ollama` (L471), `Run-DoctorPreflight` (L477), `Test-NovaHttpDirectProcess` (L499), `Get-NovaHttpProcesses` (L508), `Get-NovaProcessFamilyIds` (L516), `Get-NovaScriptProcesses` (L553), `Get-NovaLogicalProcesses` (L567), `Read-NovaIdentityFile` (L581), `Convert-NovaCreationDateToUnixSeconds` (L612), `Convert-NovaDateTimeToUnixSeconds` (L625), `Select-NovaIdentityProcess` (L638), `Select-NovaLogicalProcess` (L666), `Get-NovaHeartbeatAgeSeconds` (L705), `Show-NovaRuntimeStatus` (L716), `Get-NovaHttpLogicalProcesses` (L772), `Test-NovaHttpProcessUsesPort` (L786), `Get-NovaHttpLogicalProcessesOnPort` (L800), `Stop-NovaHttpProcesses` (L808), `Stop-NovaHttpOnPort` (L825), `Test-NovaProcessFamiliesOverlap` (L854), `Stop-NovaHttpExcept` (L861), `Stop-NovaHttpExceptOnPort` (L877), `Wait-NovaHttpStopped` (L897), `Wait-NovaHttpReady` (L921), `Show-Help` (L939)

## `scripts/build_release_package.ps1`

Lines: 426 | PowerShell functions: 3

`Get-SafeArtifactFragment` (L15), `Get-AutoReleaseVersion` (L37), `Remove-StageRelativePath` (L108)

## `scripts/build_windows_installer.ps1`

Lines: 280 | PowerShell functions: 5

`Resolve-WorkingPath` (L17), `Resolve-InstallerArtifact` (L27), `Resolve-InnoCompiler` (L44), `Invoke-InnoCompiler` (L81), `Expand-InstallerPayloadZip` (L92)

## `scripts/installer_hardware_check.ps1`

Lines: 189 | PowerShell functions: 2

`Get-CommandPathOrEmpty` (L6), `Get-PortListenerInfo` (L17)

## `scripts/prepush_gate.ps1`

Lines: 13 | PowerShell functions: 0

No named functions found by the static inventory pattern.

## `scripts/promote_release_package.ps1`

Lines: 204 | PowerShell functions: 2

`Get-RecordField` (L18), `Get-EntryArtifactKind` (L43)

## `scripts/show_release_ledger.ps1`

Lines: 110 | PowerShell functions: 1

`Get-EntryArtifactKind` (L15)

## `scripts/show_release_readiness.ps1`

Lines: 229 | PowerShell functions: 4

`Write-ReadinessPayload` (L11), `Get-ServiceReadinessPayload` (L49), `Get-EntryArtifactKind` (L75), `Test-ReleaseEntryMatchesBuild` (L83)

## `scripts/show_release_status.ps1`

Lines: 117 | PowerShell functions: 1

`Get-EntryArtifactKind` (L11)

## `scripts/verify_release_package.ps1`

Lines: 415 | PowerShell functions: 12

`Resolve-VerificationTarget` (L11), `Normalize-RelativePath` (L35), `Add-CheckResult` (L48), `Get-ZipPayload` (L58), `Get-DirectoryPayload` (L109), `Test-PayloadHasRelativePath` (L135), `Test-PayloadContainsRelativePrefix` (L146), `Test-PayloadContainsPathSegment` (L158), `Test-PayloadContainsLeafPattern` (L172), `Test-PayloadContainsRelativePathPattern` (L186), `Test-PayloadContainsPathSegmentPattern` (L203), `Find-ForbiddenRuntimePath` (L216)

## `scripts/verify_windows_installer.ps1`

Lines: 160 | PowerShell functions: 3

`Get-EntryArtifactKind` (L11), `Resolve-VerificationTarget` (L19), `Add-CheckResult` (L43)

## `static/control.js`

Lines: 5975 | JavaScript named functions: 209

`filteredSessions` (L217), `generatedPriorityRank` (L228), `orderedGeneratedPriorities` (L233), `formatSeamLabel` (L246), `subconsciousSeamBadgeMeta` (L252), `summarizeGeneratedPriority` (L279), `buildGeneratedPriorityTitle` (L291), `resolveOperatorMacroValues` (L304), `telemetryRecentPoints` (L328), `telemetryRates` (L333), `telemetryRolling` (L357), `setTelemetryGraphMode` (L367), `drawTelemetryGrid` (L381), `plotTelemetrySeries` (L394), `drawDependencyLanes` (L416), `renderTelemetryGraph` (L443), `renderOperatorMacroPrompt` (L506), `escapeHtml` (L519), `formatDeviceCoords` (L523), `formatMetric` (L530), `formatAgeSeconds` (L536), `formatCapturedTime` (L545), `haversineMeters` (L551), `liveTrackingBrowserSupported` (L566), `normalizeObservedPosition` (L570), `shouldSyncObservedPosition` (L587), `setLiveTrackingAutoArmEnabled` (L595), `setLiveTrackingButtons` (L600), `renderLiveTrackingMetaCards` (L613), `renderLiveTracking` (L642), `syncLiveTrackingObservation` (L714), `handleLiveTrackingSuccess` (L743), `handleLiveTrackingError` (L759), `startLiveTracking` (L769), `stopLiveTracking` (L796), `clearLiveTracking` (L805), `maybeAutoArmLiveTracking` (L817), `toggleLiveTrackingAutoArm` (L825), `parsePatchPreviewReport` (L846), `renderPatchPreviewSummary` (L890), `setActiveView` (L941), `syncTemporalNavLinkActive` (L953), `visibleViewName` (L971), `syncScheduledTreeView` (L976), `setCenterTab` (L982), `clearCenterTabs` (L1004), `resolveInspectorTabButton` (L1019), `setInspectorTab` (L1030), `focusInspectorTabByOffset` (L1051), `resolveCenterTabButton` (L1068), `focusCenterTabByOffset` (L1079), `getLayerTabContext` (L1096), `resolveLayerTabButton` (L1108), `setLayerTab` (L1120), `focusLayerTabByOffset` (L1142), `controlHeaders` (L1174), `setFeedback` (L1181), `setAction` (L1187), `focusOperatorSession` (L1195), `renderOperatorReply` (L1210), `selectedOperatorOutboxEvent` (L1231), `operatorOutboxEventLabel` (L1236), `operatorOutboxTargetLines` (L1244), `renderOperatorOutbox` (L1257), `setOperatorOutboxStatus` (L1332), `respondOperatorOutbox` (L1346), `syncOperatorAudioButton` (L1372), `syncOperatorMicButton` (L1379), `inferButtonIcon` (L1392), `setActionButtonLabel` (L1428), `decorateActionButtons` (L1441), `speakOperatorReply` (L1454), `initOperatorSpeechRecognition` (L1469), `sendOperatorPrompt` (L1495), `runNextGeneratedQueueItem` (L1530), `investigateNextGeneratedQueueItem` (L1546), `startAutonomyMaintenanceWorker` (L1559), `stopAutonomyMaintenanceWorker` (L1567), `formatStorageBytes` (L1575), `renderMetricGrid` (L1586), `renderSubconscious` (L1687), `renderMatrixTable` (L1811), `renderInspectorList` (L1844), `selectedPipeline` (L1865), `renderPipelineCards` (L1869), `renderPipelineSelect` (L1891), `pipelineQueryTemplateCatalog` (L1930), `collectPipelineQueryParams` (L1937), `renderPipelineQueryParamFields` (L1961), `renderPipelineQueryTable` (L2011), `formatPipelineQueryResult` (L2043), `renderEdfiSyncSummary` (L2080), `renderPipelineQueryControls` (L2104), `executePipelineQuery` (L2157), `renderPipelineDetail` (L2197), `renderPipelines` (L2281), `loadPipelines` (L2292), `patchBadgeClass` (L2300), `renderPatchReadiness` (L2311), `selectedPatchPreviewState` (L2484), `renderPatchActionReadiness` (L2495), `renderPlannerInspector` (L2522), `renderLedgerInspector` (L2531), `runtimeTimelineClass` (L2559), `formatRuntimeEventTime` (L2567), `renderRuntimeTimeline` (L2573), `runtimeBadgeClassForLevel` (L2637), `renderRuntimeFailures` (L2645), `artifactBadgeClass` (L2667), `renderRuntimeArtifacts` (L2676), `renderArtifactDetail` (L2701), `renderReleaseStatus` (L2719), `renderRestartAnalytics` (L2771), `renderTelemetrySummary` (L2820), `telemetryWindowStats` (L2882), `renderTelemetryPressure` (L2912), `selectedSession` (L3000), `selectedTestRun` (L3006), `testRunStatusLabel` (L3011), `testRunBadgeClass` (L3018), `renderSessionState` (L3025), `renderSupervisorInspector` (L3042), `renderOverrideBadges` (L3053), `memoryHealthDetails` (L3068), `storageWatchDetails` (L3139), `renderHealthSummary` (L3158), `compactRouteSummary` (L3176), `shortArtifactName` (L3185), `renderHeroMeta` (L3192), `recommendedCenterTab` (L3201), `recommendedInspectorTab` (L3226), `renderOverviewFocus` (L3234), `missionArray` (L3296), `missionBlockerLine` (L3302), `missionVerdictLine` (L3311), `missionOwnerPressureText` (L3322), `renderCenterMissionBrief` (L3348), `setButtonReadiness` (L3456), `renderActionReadiness` (L3465), `registerRuntimeInspectPayload` (L3487), `runtimeBadgeClassForStatus` (L3494), `runtimeStatusLabel` (L3525), `runtimeSummaryRows` (L3529), `formatRuntimeRawFields` (L3577), `selectRuntimeInspectButton` (L3585), `showRuntimeInspect` (L3594), `renderRuntimeCards` (L3601), `renderRuntimeSummary` (L3636), `formatRuntimeConsole` (L3640), `renderGuardRuntime` (L3644), `renderHeroDeck` (L3648), `renderSessionPreview` (L3686), `renderSessions` (L3731), `renderTestRunPreview` (L3756), `renderTestRuns` (L3851), `renderTestSessionDefinitions` (L3878), `realWorldTaskDefinitions` (L3905), `selectedRealWorldTask` (L3909), `renderRealWorldTaskPreview` (L3914), `renderRealWorldTasks` (L3933), `workTreeStatusClass` (L3959), `workTreeStatusColor` (L3968), `selectedWorkTree` (L3978), `selectedWorkTreeNode` (L3982), `preferredWorkTreeId` (L3993), `formatWorkTreeLabel` (L4005), `renderWorkTreeSelect` (L4015), `renderWorkTreeViewButtons` (L4040), `setWorkTreeViewMode` (L4055), `workTreeNodeVisibleInMode` (L4062), `renderWorkTreeAggregateSummary` (L4073), `renderSelectedWorkTreeSummary` (L4101), `renderWorkTreeInspector` (L4138), `renderTreeSvg` (L4186), `renderSelectedWorkTreeView` (L4297), `renderWorkTrees` (L4315), `renderOperatorMacros` (L4322), `renderBackendCommands` (L4343), `selectedOperatorMacro` (L4377), `renderGovernance` (L4383), `renderTemporalGovernance` (L4475), `_temporalFmt` (L4547), `renderTemporalEventList` (L4560), `loadTemporalEvents` (L4591), `clearTemporalForm` (L4603), `populateTemporalForm` (L4630), `wireTemporalEventManagement` (L4655), `setHealthBadge` (L4730), `drawMetrics` (L4752), `getJson` (L4756), `postAction` (L4763), `fetchWorkTrees` (L4774), `fetchPipelines` (L4791), `fetchBackendCommandsDeck` (L4796), `currentMainViewName` (L4812), `shouldHydrateFullStatus` (L4817), `shouldHydrateSessions` (L4823), `shouldHydrateWorkTrees` (L4827), `shouldHydratePipelines` (L4831), `mergeStatusPayload` (L4835), `renderStatusSpine` (L4840), `renderFullStatusSections` (L4867), `scheduleLiveRefresh` (L4885), `performRefresh` (L4895), `refresh` (L4986), `bindClick` (L5002), `syncShellToggleState` (L5255), `initialControlView` (L5928), `focusTemporalPolicyAnchor` (L5942)

## `static/leah.js`

Lines: 1260 | JavaScript named functions: 46

`makeUserId` (L136), `humanBytes` (L143), `setChip` (L156), `formatWelcomeUser` (L165), `syncSessionLabels` (L177), `syncHeroInputs` (L196), `syncPresence` (L209), `hasImmediateLocalFocus` (L238), `setMood` (L249), `inferMoodFromText` (L260), `syncButtons` (L302), `setTranscript` (L329), `pushActivity` (L335), `setActivityDetail` (L342), `setPulseField` (L347), `setUserFacingStatus` (L352), `setActivityHeadline` (L381), `describeMaintenanceMode` (L387), `updatePulseHeadline` (L396), `updateRuntimePulse` (L422), `addMessage` (L485), `clearReplyPulseTimers` (L498), `setReplyPulseVisual` (L507), `startReplyPulse` (L532), `renderStagedItems` (L557), `speakAssistant` (L612), `ensureChatLogin` (L627), `chatFetch` (L652), `checkHealth` (L693), `refreshRuntimePulse` (L716), `uploadItems` (L735), `fileToBase64` (L777), `stageFiles` (L790), `sendMessage` (L810), `stopCamera` (L895), `toggleCamera` (L913), `captureFrame` (L943), `initSpeechRecognition` (L967), `stopListening` (L1037), `startManualMic` (L1053), `toggleListenMode` (L1070), `loadHistory` (L1095), `resumePendingTurn` (L1116), `resetSession` (L1136), `bindEvents` (L1155), `boot` (L1230)

## `static/leah_fx.js`

Lines: 256 | JavaScript named functions: 7

`createShader` (L136), `clamp` (L189), `parseRgbTriplet` (L193), `syncPalette` (L205), `currentPulseStrength` (L211), `resize` (L217), `render` (L236)
