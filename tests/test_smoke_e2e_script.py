import importlib.util
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "smoke_e2e.py"
SPEC = importlib.util.spec_from_file_location("nova_smoke_e2e_script", SCRIPT_PATH)
SMOKE_E2E = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(SMOKE_E2E)


WORK_TMP_ROOT = Path(__file__).resolve().parents[1] / "runtime" / "pytest_temp"


def _workspace_case_dir(prefix: str) -> Path:
    WORK_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_TMP_ROOT / f"{prefix}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestSmokeE2EScript(unittest.TestCase):
    def test_main_runs_unit_before_optional_memory_check(self):
        commands = []

        root = _workspace_case_dir("smoke_e2e_script")
        try:
            with patch.object(SMOKE_E2E, "ROOT", root), \
                 patch.object(SMOKE_E2E, "run_cmd", side_effect=lambda cmd, cwd=SMOKE_E2E.ROOT, timeout=600: commands.append(cmd) or (0, "ok")):
                code = SMOKE_E2E.main()
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(code, 0)
        self.assertGreaterEqual(len(commands), 1)
        self.assertEqual(commands[0], [SMOKE_E2E.PY, "-m", "unittest", "discover", "-v"])


if __name__ == "__main__":
    unittest.main()
