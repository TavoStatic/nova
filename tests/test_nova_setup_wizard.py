from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.nova_setup_wizard import (
    SUPPORTED_PYTHON,
    acquire_setup_singleton,
    ensure_base_disk_space,
    ensure_model_disk_space,
    ensure_nova_path,
    ensure_sock_policy,
    estimate_model_disk_gb,
    install_disk_budget,
    model_present,
    parse_python_version,
    refresh_windows_path,
    release_setup_singleton,
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
                        register_path=False,
                    )
            self.assertFalse(report["ok"])
            names = [s["name"] for s in report["steps"]]
            self.assertIn("host", names)
            self.assertIn("python", names)
            self.assertIn("python", report["required_failed"])

    def test_ensure_nova_path_writes_shim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nova.cmd").write_text("@echo off\r\necho nova\r\n", encoding="utf-8")
            with mock.patch.dict("os.environ", {"LOCALAPPDATA": str(root / "local")}, clear=False):
                with mock.patch("services.nova_setup_wizard.ensure_user_path_entry", return_value=(True, "added")):
                    with mock.patch("services.nova_setup_wizard.refresh_windows_path", return_value=""):
                        step = ensure_nova_path(root, install=True)
            shim = root / "local" / "Nova" / "bin" / "nova.cmd"
            self.assertTrue(shim.is_file())
            self.assertIn(str(root / "nova.cmd"), shim.read_text(encoding="utf-8"))
            self.assertTrue(step.get("ok"))
            self.assertEqual(step.get("name"), "nova_path")

    def test_refresh_windows_path_sets_environ(self):
        with mock.patch.dict("os.environ", {"PATH": "C:\\old"}, clear=False):
            if os_name_is_windows():
                merged = refresh_windows_path()
                self.assertTrue(merged)
                self.assertTrue(str(__import__("os").environ.get("PATH") or ""))

    def test_estimate_model_disk_gb(self):
        self.assertGreaterEqual(estimate_model_disk_gb("qwen2.5:7b"), 4.0)
        self.assertGreaterEqual(estimate_model_disk_gb("qwen2.5:14b"), 8.0)

    def test_install_disk_budget_includes_libraries(self):
        budget = install_disk_budget(need_python_install=True, need_venv_libraries=True, need_ollama_app=True)
        self.assertGreaterEqual(budget["venv_and_libraries"], 5.0)
        self.assertGreaterEqual(budget["total"], 8.0)

    def test_singleton_blocks_second_acquirer(self):
        # Release any leftover from other tests first.
        release_setup_singleton()
        release_setup_singleton()
        ok1, _ = acquire_setup_singleton()
        self.assertTrue(ok1)
        # Nested acquire in same process is allowed (GUI + wizard).
        ok_nested, detail = acquire_setup_singleton()
        self.assertTrue(ok_nested)
        self.assertIn("nested", detail)
        release_setup_singleton()
        release_setup_singleton()

    def test_ensure_model_disk_space_blocks_when_low(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("services.nova_setup_wizard.free_disk_gb", return_value=2.0):
                with mock.patch("services.nova_setup_wizard.ollama_models_dir", return_value=Path(tmp)):
                    step = ensure_model_disk_space(Path(tmp), ["qwen2.5:7b", "qwen2.5vl:7b"])
        self.assertFalse(step.get("ok"))
        self.assertIn("insufficient disk", str(step.get("detail") or ""))

    def test_ensure_model_disk_space_ok_when_plenty(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("services.nova_setup_wizard.free_disk_gb", return_value=80.0):
                with mock.patch("services.nova_setup_wizard.ollama_models_dir", return_value=Path(tmp)):
                    step = ensure_model_disk_space(Path(tmp), ["llama3.2:3b"])
        self.assertTrue(step.get("ok"))

    def test_ensure_sock_policy_applies_recommendation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "policy.json").write_text(
                json.dumps({"models": {"chat": "qwen2.5:14b", "routing": "qwen2.5:14b", "vision": "qwen2.5vl:14b", "stt_size": "medium"}}),
                encoding="utf-8",
            )
            hw = mock.Mock(ram_gb=16.0, vram_gb=4.0, gpu_name="Test GPU 4GB", cpu_cores=8, storage_free_gb=100.0, detection_notes=[])
            rec = mock.Mock(chat="qwen2.5:7b", routing="qwen2.5:7b", vision="qwen2.5vl:7b", stt_size="small", rationale={"chat": "fits"})
            diff = mock.Mock(changed_keys=["chat", "routing", "vision", "stt_size"])
            with mock.patch("services.sock_service.scan_hardware", return_value=hw):
                with mock.patch("services.sock_service.recommend_models", return_value=rec):
                    with mock.patch("services.sock_service.build_diff", return_value=diff):
                        with mock.patch("services.sock_service.apply_policy") as apply:
                            step = ensure_sock_policy(root, install=True)
                            apply.assert_called_once()
            self.assertTrue(step.get("ok"))
            self.assertEqual(step.get("name"), "sock_hardware")


def os_name_is_windows() -> bool:
    return __import__("os").name == "nt"


if __name__ == "__main__":
    unittest.main()
