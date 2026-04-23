import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import doctor


class TestDoctorPreflightSeams(unittest.TestCase):
    def _seed_minimal_workspace(self, root: Path, *, forbidden_http: bool) -> None:
        required_files = [
            "nova_guard.py",
            "stop_guard.py",
            "task_engine.py",
            "tts_piper.py",
            "action_planner.py",
            "agent.py",
            "health.py",
        ]
        for rel in required_files:
            (root / rel).write_text("pass\n", encoding="utf-8")

        for rel in ("runtime", "logs", "knowledge", ".venv/Scripts"):
            (root / rel).mkdir(parents=True, exist_ok=True)

        (root / ".venv" / "Scripts" / "python.exe").write_text("", encoding="utf-8")

        policy = {
            "allowed_root": str(root),
            "tools_enabled": {"health": True},
            "models": {"chat": "llama3.1:8b"},
        }
        (root / "policy.json").write_text(json.dumps(policy), encoding="utf-8")

        http_text = (
            "from supervisor import Supervisor\n"
            "def x():\n"
            "    return Supervisor()\n"
            if forbidden_http
            else "from services.control_actions import CONTROL_ACTIONS_SERVICE\n"
            "from services.control_status import CONTROL_STATUS_SERVICE\n"
            "def x():\n"
            "    CONTROL_ACTIONS_SERVICE.build_action_handlers()\n"
            "    CONTROL_ACTIONS_SERVICE.handle_control_action('refresh_status', {}, action_handlers={}, record_control_action_event_fn=lambda *args: None)\n"
            "    return CONTROL_STATUS_SERVICE.control_status_payload()\n"
        )
        (root / "nova_http.py").write_text(http_text, encoding="utf-8")

        core_text = (
            "from services.nova_routing_support import classify_supervisor_bypass as service_classify_supervisor_bypass\n"
            "from services.nova_routing_support import looks_like_open_fallback_turn as service_looks_like_open_fallback_turn\n"
            "def a(text):\n"
            "    return service_classify_supervisor_bypass(text=text)\n"
            "def b(text):\n"
            "    return service_looks_like_open_fallback_turn(text=text)\n"
        )
        (root / "nova_core.py").write_text(core_text, encoding="utf-8")

    def test_run_preflight_includes_seam_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_minimal_workspace(root, forbidden_http=False)

            with mock.patch.object(doctor, "BASE_DIR", root):
                results = doctor.run_preflight()

        names = {item.name for item in results}
        self.assertIn("seam:nova_http_transport_boundary", names)
        self.assertIn("seam:nova_http_control_delegation", names)

    def test_run_preflight_fails_required_when_seam_breaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_minimal_workspace(root, forbidden_http=True)

            with mock.patch.object(doctor, "BASE_DIR", root):
                results = doctor.run_preflight()

        by_name = {item.name: item for item in results}
        seam = by_name["seam:nova_http_transport_boundary"]
        self.assertFalse(seam.ok)
        self.assertTrue(seam.required)


if __name__ == "__main__":
    unittest.main()
