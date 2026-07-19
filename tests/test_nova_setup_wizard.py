from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.nova_setup_wizard import (
    SUPPORTED_PYTHON,
    model_present,
    parse_python_version,
    required_ollama_models,
    run_setup_wizard,
    select_supported_python,
)


class TestNovaSetupWizard(unittest.TestCase):
    def test_parse_python_version(self):
        self.assertEqual(parse_python_version("Python 3.12.6"), (3, 12))
        self.assertEqual(parse_python_version("3.14.6"), (3, 14))
        self.assertIsNone(parse_python_version("nope"))

    def test_select_supported_python_prefers_312(self):
        selected = select_supported_python(
            [
                {"ok": True, "supported": False, "command": ["py", "-3.14"], "version": (3, 14)},
                {"ok": True, "supported": True, "command": ["py", "-3.12"], "version": (3, 12)},
            ]
        )
        self.assertEqual(selected["command"], ["py", "-3.12"])
        self.assertEqual(SUPPORTED_PYTHON, (3, 12))

    def test_required_models_from_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "policy.json").write_text(
                json.dumps({"models": {"chat": "qwen2.5:7b", "vision": "qwen2.5vl:7b", "routing": "qwen2.5:7b"}}),
                encoding="utf-8",
            )
            self.assertEqual(required_ollama_models(root), ["qwen2.5:7b", "qwen2.5vl:7b"])

    def test_model_present(self):
        installed = ["qwen2.5:7b", "qwen2.5vl:7b"]
        self.assertTrue(model_present("qwen2.5:7b", installed))
        self.assertFalse(model_present("missing:1b", installed))

    def test_run_setup_wizard_check_only_host_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "requirements.txt").write_text("requests\n", encoding="utf-8")
            (root / "policy.json").write_text(json.dumps({"models": {"chat": "qwen2.5:7b"}}), encoding="utf-8")
            (root / "doctor.py").write_text("print('ok')\n", encoding="utf-8")
            with mock.patch("services.nova_setup_wizard.ensure_python", return_value={"name": "python", "ok": False, "required": True, "action": "check", "detail": "no py", "messages": []}):
                with mock.patch("services.nova_setup_wizard.select_supported_python", return_value=None):
                    report = run_setup_wizard(
                        root,
                        install=False,
                        include_ollama=False,
                        include_models=False,
                        include_webui=False,
                        include_smoke=False,
                    )
            self.assertFalse(report["ok"])
            names = [s["name"] for s in report["steps"]]
            self.assertIn("host", names)
            self.assertIn("python", names)
            self.assertIn("python", report["required_failed"])


if __name__ == "__main__":
    unittest.main()
