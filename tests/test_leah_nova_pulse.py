from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.leah_nova_pulse import build_leah_nova_pulse, compose_nova_outreach, statement_from_nova_life
from services.nova_http_get_routes import HTTP_GET_ROUTES_SERVICE
from services.nova_http_frontdoor import NOVA_HTTP_FRONTDOOR_SERVICE


class TestLeahNovaPulse(unittest.TestCase):
    def test_pulse_reads_local_runtime_without_control_auth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "core.heartbeat").write_text("ok", encoding="utf-8")
            (root / "core_state.json").write_text(json.dumps({"pid": 123}), encoding="utf-8")
            (root / "autonomy_maintenance_state.json").write_text(
                json.dumps(
                    {
                        "last_generated_queue_run": {
                            "queue_actionable_count": 2,
                            "queue_open_count": 3,
                        }
                    }
                ),
                encoding="utf-8",
            )
            payload = build_leah_nova_pulse(
                runtime_dir=root,
                ollama_up=True,
                chat_model="qwen2.5:7b",
                memory_enabled=True,
            )
            self.assertTrue(payload.get("ok"))
            self.assertEqual(payload.get("surface"), "leah_nova_pulse")
            self.assertTrue(payload.get("core_running"))
            self.assertEqual(payload.get("health_score"), 100)
            self.assertEqual(payload.get("queue_actionable_count"), 2)
            self.assertEqual(payload.get("queue_open_count"), 3)
            self.assertEqual(payload.get("chat_model"), "qwen2.5:7b")

    def test_internal_runtime_facts_do_not_become_chat(self) -> None:
        presence = compose_nova_outreach({"core_running": True, "queue_actionable_count": 0, "work_tree_status": "idle"})
        self.assertEqual(presence.get("kind"), "silent")
        self.assertEqual(presence.get("text") or "", "")
        busy = compose_nova_outreach({"core_running": True, "queue_actionable_count": 2, "work_tree_status": "active"})
        self.assertEqual(busy.get("kind"), "silent")
        self.assertEqual(busy.get("text") or "", "")
        outbox = compose_nova_outreach(
            {"core_running": True, "queue_actionable_count": 0, "work_tree_status": "active"},
            outbox={"latest_open": {"id": "n1", "message": "Guard needs a restart decision."}},
        )
        self.assertEqual(outbox.get("kind"), "attention")
        self.assertEqual(outbox.get("text"), "Guard needs a restart decision.")

    def test_floor_statement_is_not_a_ticket_question(self) -> None:
        line = statement_from_nova_life(
            {"core_running": True, "queue_actionable_count": 0, "work_tree_status": "idle"}
        )
        self.assertTrue(line)
        self.assertFalse(line.endswith("?"))
        self.assertNotIn("would you like", line.lower())
        busy = statement_from_nova_life(
            {"core_running": True, "queue_actionable_count": 0, "work_tree_status": "active"}
        )
        self.assertIn("work", busy.lower())
        self.assertFalse(busy.endswith("?"))

    def test_pulse_marks_core_down_without_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = build_leah_nova_pulse(runtime_dir=Path(tmp), ollama_up=False)
            self.assertFalse(payload.get("core_running"))
            self.assertEqual(payload.get("health_score"), 0)
            self.assertEqual(payload.get("maintenance_scheduler_status"), "inactive")

    def test_get_route_serves_leah_pulse(self) -> None:
        result = HTTP_GET_ROUTES_SERVICE.handle_basic_route_request(
            "/api/leah/pulse",
            handler=object(),
            control_login_enabled_fn=lambda: True,
            control_page_gate_fn=lambda _handler: (True, ""),
            health_payload_fn=lambda: {"ok": True, "source": "health"},
            leah_pulse_payload_fn=lambda: {"ok": True, "surface": "leah_nova_pulse"},
            ollama_api_up_fn=lambda: True,
            chat_model_fn=lambda: "phi",
            memory_enabled_fn=lambda: True,
            chat_login_enabled_fn=lambda: False,
            index_html="index",
            control_login_html="login",
            control_html="control",
        )
        self.assertEqual(
            result,
            {"kind": "json", "code": 200, "body": {"ok": True, "surface": "leah_nova_pulse"}},
        )

    def test_leah_js_reads_nova_pulse_not_control_status(self) -> None:
        script = Path("static/leah.js").read_text(encoding="utf-8")
        self.assertIn("/api/leah/pulse", script)
        self.assertNotIn('controlStatusUrl: "/api/control/status"', script)

    def test_route_contract_lists_leah_pulse(self) -> None:
        contract = NOVA_HTTP_FRONTDOOR_SERVICE.route_contract(
            public_renderers={"/": lambda: "root", "/leah": lambda: "leah"},
            static_routes={},
        )
        self.assertIn("/api/leah/pulse", contract["public_api_get"])


if __name__ == "__main__":
    unittest.main()
