import unittest

from services.nova_control_action_dispatcher import (
    NOVA_CONTROL_ACTION_DISPATCHER,
    autonomy_advisory_action_catalog,
    autonomy_advisory_action_types,
    is_autonomy_advisory_action,
)


class _PatchControlService:
    @staticmethod
    def patch_preview_target(payload, previews):
        return {}


class _Core:
    @staticmethod
    def patch_status_payload():
        return {"ok": True}

    @staticmethod
    def patch_preview_summaries(limit):
        return []

    @staticmethod
    def show_preview(target):
        return {"ok": True}

    @staticmethod
    def approve_preview(target, note=""):
        return True

    @staticmethod
    def reject_preview(target, note=""):
        return True

    @staticmethod
    def patch_apply(*args, **kwargs):
        return {"ok": True}

    @staticmethod
    def inspect_environment():
        return {"status": "ok"}

    @staticmethod
    def format_report(data):
        return f"report:{data.get('status')}"

    @staticmethod
    def policy_audit(limit):
        return "audit"


def _ok_action(payload):
    return True, "refresh_ok", {"status": "fresh"}, "refresh_ok"


def _runtime_scope(events):
    return {
        "nova_core": _Core(),
        "PATCH_CONTROL_SERVICE": _PatchControlService(),
        "_patch_action_readiness_payload": lambda patch: {"ready": True},
        "_refresh_status_action": _ok_action,
        "_device_location_update_action": _ok_action,
        "_device_location_clear_action": _ok_action,
        "_patch_preview_list_action": _ok_action,
        "_pulse_status_action": _ok_action,
        "_update_now_dry_run_action": _ok_action,
        "_update_now_confirm_action": _ok_action,
        "_update_now_cancel_action": _ok_action,
        "_runtime_artifact_show_action": _ok_action,
        "_guard_control_action": _ok_action,
        "_core_runtime_action": _ok_action,
        "_autonomy_runtime_action": _ok_action,
        "_test_session_run_action": _ok_action,
        "_generated_pack_run_action": _ok_action,
        "_generated_queue_run_next_action": _ok_action,
        "_generated_queue_investigate_action": _ok_action,
        "_patch_queue_run_next_action": _ok_action,
        "_active_work_tree_run_next_action": _ok_action,
        "_real_world_task_create_action": _ok_action,
        "_backend_command_list_action": _ok_action,
        "_backend_command_run_action": _ok_action,
        "_operator_prompt_action": lambda payload: (True, "prompt_ok", {}, "prompt_ok", payload),
        "_operator_outbox_respond_action": _ok_action,
        "_operator_outbox_status_action": _ok_action,
        "_session_delete_action": _ok_action,
        "_policy_allow_action": _ok_action,
        "_policy_remove_action": _ok_action,
        "_web_mode_action": _ok_action,
        "_memory_scope_set_action": _ok_action,
        "_server_side_settings_action": _ok_action,
        "_search_provider_action": _ok_action,
        "_search_provider_toggle_action": _ok_action,
        "_search_endpoint_set_action": _ok_action,
        "_search_provider_priority_set_action": _ok_action,
        "_search_endpoint_probe_action": _ok_action,
        "_chat_user_list_action": _ok_action,
        "_chat_user_upsert_action": _ok_action,
        "_chat_user_delete_action": _ok_action,
        "_pipeline_note_append_action": _ok_action,
        "_pipeline_create_action": _ok_action,
        "_pipeline_start_action": _ok_action,
        "_pipeline_pause_action": _ok_action,
        "_pipeline_update_action": _ok_action,
        "_pipeline_population_upsert_action": _ok_action,
        "_pipeline_archive_action": _ok_action,
        "_pipeline_query_preview_action": _ok_action,
        "_pipeline_query_run_action": _ok_action,
        "_self_check_action": _ok_action,
        "_codegen_run_action": _ok_action,
        "_leah_build_run_next_action": _ok_action,
        "_export_capabilities_snapshot": lambda: (True, "export_ok", {}),
        "_export_ledger_summary_action": lambda payload: (True, "ledger_ok", {}),
        "_export_diagnostics_bundle_action": lambda payload: (True, "bundle_ok", {}),
        "_tail_log_action": lambda payload: (True, "tail_ok", {}),
        "_metrics_action": lambda payload: (True, "metrics_ok", {}),
        "_record_control_action_event": lambda act, status, detail, payload: events.append((act, status, detail)),
        "_invalidate_control_status_cache": lambda: events.append(("invalidate", "ok", "")),
    }


class TestNovaControlActionDispatcher(unittest.TestCase):
    def test_dispatch_control_action_from_runtime_resolves_runtime_hooks(self):
        events = []
        ok, msg, extra = NOVA_CONTROL_ACTION_DISPATCHER.dispatch_control_action_from_runtime(
            "refresh_status",
            {"action": "refresh_status"},
            patch_control_service=_PatchControlService(),
            updates_dir="C:/Nova/updates",
            runtime_scope=_runtime_scope(events),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "refresh_ok")
        self.assertEqual(extra.get("status"), "fresh")
        self.assertEqual(events, [("refresh_status", "ok", "refresh_ok")])

    def test_autonomy_advisory_catalog_is_dispatcher_owned_and_routable(self):
        catalog = autonomy_advisory_action_catalog()
        self.assertEqual(tuple(catalog), autonomy_advisory_action_types())
        self.assertTrue(catalog)

        for action_type, metadata in catalog.items():
            with self.subTest(action_type=action_type):
                self.assertTrue(is_autonomy_advisory_action(action_type))
                self.assertIn("target_kind", metadata)
                self.assertIn("preconditions", metadata)
                self.assertIn("expected_effect", metadata)
                events = []
                ok, msg, _extra = NOVA_CONTROL_ACTION_DISPATCHER.dispatch_control_action_from_runtime(
                    action_type,
                    {"action": action_type},
                    patch_control_service=_PatchControlService(),
                    updates_dir="C:/Nova/updates",
                    runtime_scope=_runtime_scope(events),
                )
                self.assertTrue(ok)
                self.assertNotEqual(msg, "unknown_action")
                self.assertIn((action_type, "ok", "refresh_ok"), events)

    def test_dispatches_operator_outbox_response_and_seen_actions(self):
        events = []
        for action_type in ("operator_outbox_respond", "operator_outbox_seen"):
            with self.subTest(action_type=action_type):
                ok, msg, _extra = NOVA_CONTROL_ACTION_DISPATCHER.dispatch_control_action_from_runtime(
                    action_type,
                    {"action": action_type, "event_id": "notice-1", "message": "operator evidence"},
                    patch_control_service=_PatchControlService(),
                    updates_dir="C:/Nova/updates",
                    runtime_scope=_runtime_scope(events),
                )
                self.assertTrue(ok)
                self.assertEqual(msg, "refresh_ok")
        self.assertIn(("operator_outbox_respond", "ok", "refresh_ok"), events)
        self.assertIn(("operator_outbox_seen", "ok", "refresh_ok"), events)


if __name__ == "__main__":
    unittest.main()
