from __future__ import annotations

from services.nova_runtime_hooks import resolve_runtime_hooks


_CONTROL_ACTION_RUNTIME_HOOKS = {
    "patch_status_payload_fn": "_unused_runtime_factory",
    "patch_preview_summaries_fn": "_unused_runtime_factory",
    "patch_action_readiness_payload_fn": "_patch_action_readiness_payload",
    "patch_preview_target_fn": "_unused_runtime_factory",
    "show_preview_fn": "_unused_runtime_factory",
    "approve_preview_fn": "_unused_runtime_factory",
    "reject_preview_fn": "_unused_runtime_factory",
    "patch_apply_fn": "_unused_runtime_factory",
    "refresh_status_action_fn": "_refresh_status_action",
    "device_location_update_action_fn": "_device_location_update_action",
    "device_location_clear_action_fn": "_device_location_clear_action",
    "patch_preview_list_action_fn": "_patch_preview_list_action",
    "pulse_status_action_fn": "_pulse_status_action",
    "update_now_dry_run_action_fn": "_update_now_dry_run_action",
    "update_now_confirm_action_fn": "_update_now_confirm_action",
    "update_now_cancel_action_fn": "_update_now_cancel_action",
    "runtime_artifact_show_action_fn": "_runtime_artifact_show_action",
    "guard_control_action_fn": "_guard_control_action",
    "core_runtime_action_fn": "_core_runtime_action",
    "autonomy_runtime_action_fn": "_autonomy_runtime_action",
    "test_session_run_action_fn": "_test_session_run_action",
    "generated_pack_run_action_fn": "_generated_pack_run_action",
    "generated_queue_run_next_action_fn": "_generated_queue_run_next_action",
    "generated_queue_investigate_action_fn": "_generated_queue_investigate_action",
    "real_world_task_create_action_fn": "_real_world_task_create_action",
    "backend_command_list_action_fn": "_backend_command_list_action",
    "backend_command_run_action_fn": "_backend_command_run_action",
    "operator_prompt_action_fn": "_operator_prompt_action",
    "session_delete_action_fn": "_session_delete_action",
    "policy_allow_action_fn": "_policy_allow_action",
    "policy_remove_action_fn": "_policy_remove_action",
    "web_mode_action_fn": "_web_mode_action",
    "memory_scope_set_action_fn": "_memory_scope_set_action",
    "search_provider_action_fn": "_search_provider_action",
    "search_provider_toggle_action_fn": "_search_provider_toggle_action",
    "search_endpoint_set_action_fn": "_search_endpoint_set_action",
    "search_provider_priority_set_action_fn": "_search_provider_priority_set_action",
    "search_endpoint_probe_action_fn": "_search_endpoint_probe_action",
    "chat_user_list_action_fn": "_chat_user_list_action",
    "chat_user_upsert_action_fn": "_chat_user_upsert_action",
    "chat_user_delete_action_fn": "_chat_user_delete_action",
    "pipeline_note_append_action_fn": "_pipeline_note_append_action",
    "pipeline_create_action_fn": "_pipeline_create_action",
    "pipeline_start_action_fn": "_pipeline_start_action",
    "pipeline_pause_action_fn": "_pipeline_pause_action",
    "pipeline_update_action_fn": "_pipeline_update_action",
    "pipeline_population_upsert_action_fn": "_pipeline_population_upsert_action",
    "pipeline_archive_action_fn": "_pipeline_archive_action",
    "self_check_action_fn": "_self_check_action",
    "export_capabilities_snapshot_fn": "_export_capabilities_snapshot",
    "export_ledger_summary_action_fn": "_export_ledger_summary_action",
    "export_diagnostics_bundle_action_fn": "_export_diagnostics_bundle_action",
    "tail_log_action_fn": "_tail_log_action",
    "metrics_action_fn": "_metrics_action",
    "inspect_environment_fn": "_unused_runtime_factory",
    "format_report_fn": "_unused_runtime_factory",
    "policy_audit_fn": "_unused_runtime_factory",
    "record_control_action_event_fn": "_record_control_action_event",
    "invalidate_control_status_cache_fn": "_invalidate_control_status_cache",
}


class NovaControlActionDispatcher:
    """Own the complete control action dispatch ladder outside the HTTP transport shell."""

    @staticmethod
    def dispatch_control_action_from_runtime(
        act: str,
        payload: dict,
        *,
        patch_control_service,
        updates_dir,
        runtime_scope,
        explicit_hooks: dict | None = None,
    ) -> tuple[bool, str, dict]:
        runtime_scope = runtime_scope or {}
        hooks = resolve_runtime_hooks(
            _CONTROL_ACTION_RUNTIME_HOOKS,
            explicit_hooks=explicit_hooks or {},
            runtime_scope=runtime_scope,
            factories={
                "patch_status_payload_fn": lambda scope: scope["nova_core"].patch_status_payload,
                "patch_preview_summaries_fn": lambda scope: scope["nova_core"].patch_preview_summaries,
                "patch_preview_target_fn": lambda scope: scope["PATCH_CONTROL_SERVICE"].patch_preview_target,
                "show_preview_fn": lambda scope: scope["nova_core"].show_preview,
                "approve_preview_fn": lambda scope: scope["nova_core"].approve_preview,
                "reject_preview_fn": lambda scope: scope["nova_core"].reject_preview,
                "patch_apply_fn": lambda scope: scope["nova_core"].patch_apply,
                "inspect_environment_fn": lambda scope: scope["nova_core"].inspect_environment,
                "format_report_fn": lambda scope: scope["nova_core"].format_report,
                "policy_audit_fn": lambda scope: scope["nova_core"].policy_audit,
            },
        )
        return NovaControlActionDispatcher.dispatch_control_action(
            act,
            payload,
            patch_control_service=patch_control_service,
            updates_dir=updates_dir,
            **hooks,
        )

    @staticmethod
    def dispatch_control_action(
        act: str,
        payload: dict,
        *,
        patch_control_service,
        patch_status_payload_fn,
        patch_preview_summaries_fn,
        patch_action_readiness_payload_fn,
        patch_preview_target_fn,
        show_preview_fn,
        approve_preview_fn,
        reject_preview_fn,
        patch_apply_fn,
        updates_dir,
        refresh_status_action_fn,
        device_location_update_action_fn,
        device_location_clear_action_fn,
        patch_preview_list_action_fn,
        pulse_status_action_fn,
        update_now_dry_run_action_fn,
        update_now_confirm_action_fn,
        update_now_cancel_action_fn,
        runtime_artifact_show_action_fn,
        guard_control_action_fn,
        core_runtime_action_fn,
        autonomy_runtime_action_fn,
        test_session_run_action_fn,
        generated_pack_run_action_fn,
        generated_queue_run_next_action_fn,
        generated_queue_investigate_action_fn,
        real_world_task_create_action_fn,
        backend_command_list_action_fn,
        backend_command_run_action_fn,
        operator_prompt_action_fn,
        session_delete_action_fn,
        policy_allow_action_fn,
        policy_remove_action_fn,
        web_mode_action_fn,
        memory_scope_set_action_fn,
        search_provider_action_fn,
        search_provider_toggle_action_fn,
        search_endpoint_set_action_fn,
        search_provider_priority_set_action_fn,
        search_endpoint_probe_action_fn,
        chat_user_list_action_fn,
        chat_user_upsert_action_fn,
        chat_user_delete_action_fn,
        pipeline_note_append_action_fn,
        pipeline_create_action_fn,
        pipeline_start_action_fn,
        pipeline_pause_action_fn,
        pipeline_update_action_fn,
        pipeline_population_upsert_action_fn,
        pipeline_archive_action_fn,
        self_check_action_fn,
        export_capabilities_snapshot_fn,
        export_ledger_summary_action_fn,
        export_diagnostics_bundle_action_fn,
        tail_log_action_fn,
        metrics_action_fn,
        inspect_environment_fn,
        format_report_fn,
        policy_audit_fn,
        record_control_action_event_fn,
        invalidate_control_status_cache_fn,
    ) -> tuple[bool, str, dict]:
        """Dispatch control action to appropriate handler and return (ok, msg, extra)."""

        if not act:
            return False, "action_required", {}

        def _patch_control_state(*, include_readiness: bool = True) -> dict:
            """Own patch control state assembly."""
            patch = patch_status_payload_fn()
            previews = list(patch.get("previews") or []) if isinstance(patch.get("previews"), list) else []
            if not previews:
                previews = list(patch_preview_summaries_fn(40) or [])
            readiness_payload = patch_action_readiness_payload_fn(patch) if include_readiness else None
            return patch_control_service.patch_control_state(
                patch,
                previews,
                include_readiness=include_readiness,
                readiness_payload=readiness_payload,
            )

        # DISPATCH LADDER - ALL ACTION ROUTING OWNED BY DISPATCHER
        if act == "refresh_status":
            ok, msg, extra, detail = refresh_status_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "device_location_update":
            ok, msg, extra, detail = device_location_update_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "device_location_clear":
            ok, msg, extra, detail = device_location_clear_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "patch_preview_list":
            ok, msg, extra, detail = patch_preview_list_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "patch_preview_show":
            ok, msg, extra, detail = patch_control_service.patch_preview_show(
                payload,
                preview_target_fn=lambda current_payload: patch_preview_target_fn(current_payload, patch_preview_summaries_fn(40)),
                patch_control_state_fn=_patch_control_state,
                show_preview_fn=show_preview_fn,
            )
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "patch_preview_approve":
            ok, msg, extra, detail = patch_control_service.patch_preview_decision(
                "approve",
                payload,
                preview_target_fn=lambda current_payload: patch_preview_target_fn(current_payload, patch_preview_summaries_fn(40)),
                patch_control_state_fn=_patch_control_state,
                decision_fn=lambda target, note: approve_preview_fn(target, note=note),
            )
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "patch_preview_reject":
            ok, msg, extra, detail = patch_control_service.patch_preview_decision(
                "reject",
                payload,
                preview_target_fn=lambda current_payload: patch_preview_target_fn(current_payload, patch_preview_summaries_fn(40)),
                patch_control_state_fn=_patch_control_state,
                decision_fn=lambda target, note: reject_preview_fn(target, note=note),
            )
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "patch_preview_apply":
            ok, msg, extra, detail = patch_control_service.patch_preview_apply(
                payload,
                preview_target_fn=lambda current_payload: patch_preview_target_fn(current_payload, patch_preview_summaries_fn(40)),
                preview_entry_fn=lambda target: patch_control_service.patch_preview_entry(target, patch_preview_summaries_fn(40)),
                patch_control_state_fn=_patch_control_state,
                show_preview_fn=show_preview_fn,
                updates_dir=updates_dir,
                patch_apply_fn=patch_apply_fn,
            )
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "pulse_status":
            ok, msg, extra, detail = pulse_status_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "update_now_dry_run":
            ok, msg, extra, detail = update_now_dry_run_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "update_now_confirm":
            ok, msg, extra, detail = update_now_confirm_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "update_now_cancel":
            ok, msg, extra, detail = update_now_cancel_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "runtime_artifact_show":
            ok, msg, extra, detail = runtime_artifact_show_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act in {"guard_status", "guard_start", "guard_stop", "guard_restart"}:
            ok, msg, extra, detail = guard_control_action_fn({**payload, "_action": act})
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act in {"nova_start", "core_stop", "core_restart", "webui_restart"}:
            ok, msg, extra, detail = core_runtime_action_fn({**payload, "_action": act})
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act in {"autonomy_maintenance_start", "autonomy_maintenance_stop"}:
            ok, msg, extra, detail = autonomy_runtime_action_fn({**payload, "_action": act})
            if ok:
                invalidate_control_status_cache_fn()
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "test_session_run":
            ok, msg, extra, detail = test_session_run_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "generated_pack_run":
            ok, msg, extra, detail = generated_pack_run_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "generated_queue_run_next":
            ok, msg, extra, detail = generated_queue_run_next_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "generated_queue_investigate":
            ok, msg, extra, detail = generated_queue_investigate_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "real_world_task_create":
            ok, msg, extra, detail = real_world_task_create_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "backend_command_list":
            ok, msg, extra, detail = backend_command_list_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "backend_command_run":
            ok, msg, extra, detail = backend_command_run_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "operator_prompt":
            ok, msg, extra, detail, audit_payload = operator_prompt_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, audit_payload)
            return ok, msg, extra

        if act == "session_delete":
            ok, msg, extra, detail = session_delete_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "policy_allow":
            ok, msg, extra, detail = policy_allow_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "policy_remove":
            ok, msg, extra, detail = policy_remove_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "web_mode":
            ok, msg, extra, detail = web_mode_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "memory_scope_set":
            ok, msg, extra, detail = memory_scope_set_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "search_provider":
            ok, msg, extra, detail = search_provider_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "search_provider_toggle":
            ok, msg, extra, detail = search_provider_toggle_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "search_endpoint_set":
            ok, msg, extra, detail = search_endpoint_set_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "search_provider_priority_set":
            ok, msg, extra, detail = search_provider_priority_set_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "search_endpoint_probe":
            ok, msg, extra, detail = search_endpoint_probe_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "chat_user_list":
            ok, msg, extra, detail = chat_user_list_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "chat_user_upsert":
            ok, msg, extra, detail = chat_user_upsert_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "chat_user_delete":
            ok, msg, extra, detail = chat_user_delete_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "pipeline_note_append":
            ok, msg, extra, detail = pipeline_note_append_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "pipeline_create":
            ok, msg, extra, detail = pipeline_create_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "pipeline_start":
            ok, msg, extra, detail = pipeline_start_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "pipeline_pause":
            ok, msg, extra, detail = pipeline_pause_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "pipeline_update":
            ok, msg, extra, detail = pipeline_update_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "pipeline_population_upsert":
            ok, msg, extra, detail = pipeline_population_upsert_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "pipeline_archive":
            ok, msg, extra, detail = pipeline_archive_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "inspect":
            try:
                data = inspect_environment_fn()
                report = format_report_fn(data)
                record_control_action_event_fn(act, "ok", "inspect_ok", payload)
                return True, "inspect_ok", {"report": report}
            except Exception as e:
                record_control_action_event_fn(act, "fail", str(e), payload)
                return False, f"inspect_failed:{e}", {}

        if act == "policy_audit":
            try:
                text = policy_audit_fn(30)
                record_control_action_event_fn(act, "ok", "policy_audit_ok", payload)
                return True, "policy_audit_ok", {"text": text}
            except Exception as e:
                record_control_action_event_fn(act, "fail", str(e), payload)
                return False, f"policy_audit_failed:{e}", {}

        if act == "tail_log":
            return tail_log_action_fn(payload)

        if act == "metrics":
            return metrics_action_fn(payload)

        if act == "self_check":
            ok, msg, extra, detail = self_check_action_fn(payload)
            record_control_action_event_fn(act, "ok" if ok else "fail", detail, payload)
            return ok, msg, extra

        if act == "export_capabilities":
            ok, msg, extra = export_capabilities_snapshot_fn()
            record_control_action_event_fn(act, "ok" if ok else "fail", msg, payload)
            return ok, msg, extra

        if act == "export_ledger_summary":
            return export_ledger_summary_action_fn(payload)

        if act == "export_diagnostics_bundle":
            return export_diagnostics_bundle_action_fn(payload)

        record_control_action_event_fn(act, "fail", "unknown_action", payload)
        return False, "unknown_action", {}


NOVA_CONTROL_ACTION_DISPATCHER = NovaControlActionDispatcher()
