from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO_SCRIPT = ROOT / "scripts" / "demo_edfi_core_lifecycle.py"


class TestEdFiCoreLifecycleDemo(unittest.TestCase):
    def test_demo_runs_cold_start_to_operational(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(DEMO_SCRIPT), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        self.assertIn('"ready": true', completed.stdout.lower())
        self.assertIn("peims-stub", completed.stdout.lower())
        self.assertIn('"proceed": true', completed.stdout.lower())

    def test_demo_runs_cold_start_under_profile_runner_isolation(self) -> None:
        env = os.environ.copy()
        env["NOVA_TEST_RUNNER"] = "1"
        env["NOVA_VALIDATION_RUNTIME_DIR"] = str(ROOT / "runtime" / "validation")
        completed = subprocess.run(
            [sys.executable, str(DEMO_SCRIPT), "--json"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        self.assertIn('"ready": true', completed.stdout.lower())
        self.assertIn('"proceed": true', completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()