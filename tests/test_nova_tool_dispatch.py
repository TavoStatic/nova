import unittest

from services import nova_tool_dispatch


class TestNovaToolDispatchService(unittest.TestCase):
    def test_execute_planned_action_from_runtime_builds_tool_map_from_scope(self):
        runtime_scope = {
            "resolve_current_device_coords": lambda: None,
            "tool_weather": lambda value: value,
            "get_saved_location_text": lambda: "",
            "_coords_from_saved_location": lambda: None,
            "_need_confirmed_location_message": lambda: "need location",
            "set_location_coords": lambda value: f"set:{value}",
            "tool_find": lambda *args: ("find", args),
            "tool_ls": lambda *args: ("ls", args),
            "tool_queue_status": lambda *args: ("queue_status", args),
            "tool_phase2_audit": lambda *args: ("phase2_audit", args),
            "tool_nova_pulse": lambda *args: ("pulse", args),
            "tool_nova_self_status": lambda *args: ("self_status", args),
            "tool_core_health_brief": lambda *args: ("core_health", args),
            "tool_core_thinning": lambda *args: ("core_thinning", args),
            "tool_patch_preview_approve": lambda *args: ("patch_preview_approve", args),
            "patch_apply": lambda *args: ("patch_apply", args),
            "tool_patch_preview_apply": lambda *args: ("patch_preview_apply", args),
            "patch_rollback": lambda *args: ("patch_rollback", args),
            "tool_read": lambda *args: ("read", args),
            "tool_system_check": lambda *args: ("system_check", args),
            "tool_update_now": lambda *args: ("update_now", args),
            "tool_update_now_confirm": lambda *args: ("update_now_confirm", args),
            "tool_update_now_cancel": lambda *args: ("update_now_cancel", args),
            "tool_web_search": lambda *args: ("web_search", args),
            "tool_web_research": lambda *args: ("web_research", args),
            "tool_web_gather": lambda *args: ("web_gather", args),
            "tool_wikipedia_lookup": lambda *args: ("wikipedia_lookup", args),
            "tool_stackexchange_search": lambda *args: ("stackexchange_search", args),
            "tool_health": lambda *args: ("health", args),
        }

        out = nova_tool_dispatch.execute_planned_action_from_runtime(
            "system_check",
            runtime_scope=runtime_scope,
        )

        self.assertEqual(out, ("system_check", ()))

    def test_weather_current_location_prefers_live_coords(self):
        out = nova_tool_dispatch.execute_planned_action(
            "weather_current_location",
            resolve_current_device_coords_fn=lambda: (25.9, -97.5),
            tool_weather_fn=lambda value: f"weather:{value}",
            get_saved_location_text_fn=lambda: "Brownsville, TX",
            coords_from_saved_location_fn=lambda: (1.0, 2.0),
            need_confirmed_location_message_fn=lambda: "need location",
            set_location_coords_fn=lambda value: f"set:{value}",
            tool_map={},
        )

        self.assertEqual(out, "weather:25.9,-97.5")

    def test_location_coords_routes_to_setter(self):
        out = nova_tool_dispatch.execute_planned_action(
            "location_coords",
            ["25.9,-97.5"],
            resolve_current_device_coords_fn=lambda: None,
            tool_weather_fn=lambda value: value,
            get_saved_location_text_fn=lambda: "",
            coords_from_saved_location_fn=lambda: None,
            need_confirmed_location_message_fn=lambda: "need location",
            set_location_coords_fn=lambda value: f"set:{value}",
            tool_map={},
        )

        self.assertEqual(out, "set:25.9,-97.5")

    def test_unknown_tool_returns_error_payload(self):
        out = nova_tool_dispatch.execute_planned_action(
            "missing_tool",
            resolve_current_device_coords_fn=lambda: None,
            tool_weather_fn=lambda value: value,
            get_saved_location_text_fn=lambda: "",
            coords_from_saved_location_fn=lambda: None,
            need_confirmed_location_message_fn=lambda: "need location",
            set_location_coords_fn=lambda value: value,
            tool_map={},
        )

        self.assertFalse(out["ok"])
        self.assertIn("Unknown planned tool", out["error"])


if __name__ == "__main__":
    unittest.main()
