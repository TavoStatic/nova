import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "smoke_e2e.py"
SPEC = importlib.util.spec_from_file_location("nova_smoke_e2e_script", SCRIPT_PATH)
SMOKE_E2E = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(SMOKE_E2E)


class TestSmokeE2EScript(unittest.TestCase):
    def test_main_runs_preflight_then_unit_before_optional_memory_check(self):
        commands = []

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(SMOKE_E2E, "ROOT", root), \
                 patch.object(SMOKE_E2E, "run_cmd", side_effect=lambda cmd, cwd=SMOKE_E2E.ROOT, timeout=600: commands.append(cmd) or (0, "ok")):
                code = SMOKE_E2E.main()

        self.assertEqual(code, 0)
        self.assertGreaterEqual(len(commands), 2)
        self.assertEqual(commands[0], [SMOKE_E2E.PY, str(root / "run_regression.py"), "preflight"])
        self.assertEqual(commands[1], [SMOKE_E2E.PY, str(root / "run_regression.py"), "unit"])


if __name__ == "__main__":
    unittest.main()