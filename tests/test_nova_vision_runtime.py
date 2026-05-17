import unittest
import json
import tempfile
from pathlib import Path
from unittest import mock

from services import nova_vision_runtime


class TestNovaVisionRuntime(unittest.TestCase):
    def test_reports_not_requested_when_policy_keeps_vision_disabled(self):
        payload = nova_vision_runtime.vision_status_payload(
            policy={"tools_enabled": {"screen": False, "camera": False}},
            ollama_health={"ok": True, "server_ok": True, "available_models": ["qwen2.5vl:7b"]},
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "not_requested")
        self.assertFalse(payload["requested"])

    def test_reports_missing_screen_and_camera_modules_when_enabled(self):
        with mock.patch.object(nova_vision_runtime, "_module_available", return_value=False):
            payload = nova_vision_runtime.vision_status_payload(
                policy={
                    "tools_enabled": {"screen": True, "camera": True},
                    "models": {"vision": "qwen2.5vl:7b"},
                },
                ollama_health={"ok": True, "server_ok": True, "available_models": ["qwen2.5vl:7b"]},
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "missing_python_dependency")
        self.assertEqual(payload["missing_modules"], ["requests", "pillow", "mss", "opencv"])

    def test_reports_missing_vision_model_when_ollama_lacks_configured_model(self):
        with mock.patch.object(nova_vision_runtime, "_module_available", return_value=True):
            payload = nova_vision_runtime.vision_status_payload(
                policy={
                    "tools_enabled": {"screen": True, "camera": False},
                    "models": {"vision": "qwen2.5vl:7b"},
                },
                ollama_health={"ok": True, "server_ok": True, "available_models": ["llama3.2:3b"]},
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "vision_model_missing")
        self.assertFalse(payload["vision_model_available"])

    def test_reads_vision_model_from_policy_file_for_helper_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "policy.json").write_text(
                json.dumps({"models": {"vision": "custom-vision:latest"}}),
                encoding="utf-8",
            )

            model = nova_vision_runtime.vision_model_from_policy_file(root)

        self.assertEqual(model, "custom-vision:latest")

    def test_policy_file_helper_falls_back_to_default_model_when_policy_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = nova_vision_runtime.vision_model_from_policy_file(tmp)

        self.assertEqual(model, nova_vision_runtime.DEFAULT_VISION_MODEL)


if __name__ == "__main__":
    unittest.main()
