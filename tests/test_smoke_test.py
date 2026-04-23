import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "smoke_test.py"
SPEC = importlib.util.spec_from_file_location("nova_smoke_test_script", SCRIPT_PATH)
SMOKE_TEST = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(SMOKE_TEST)


class TestSmokeTestScript(unittest.TestCase):
    def test_run_health_check_base_uses_skip_ollama(self):
        result = SimpleNamespace(returncode=0, stdout="{}", stderr="")
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(SMOKE_TEST.subprocess, "run", return_value=result) as run_mock:
            ok = SMOKE_TEST.run_health_check(tier="base")

        self.assertTrue(ok)
        called_cmd = run_mock.call_args.args[0]
        self.assertIn("--skip-ollama", called_cmd)

    def test_run_health_check_runtime_keeps_ollama_requirement(self):
        result = SimpleNamespace(returncode=0, stdout="{}", stderr="")
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(SMOKE_TEST.subprocess, "run", return_value=result) as run_mock:
            ok = SMOKE_TEST.run_health_check(tier="runtime")

        self.assertTrue(ok)
        called_cmd = run_mock.call_args.args[0]
        self.assertNotIn("--skip-ollama", called_cmd)