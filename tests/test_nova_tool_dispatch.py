import unittest

from services import nova_tool_dispatch


class TestNovaToolDispatchService(unittest.TestCase):
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