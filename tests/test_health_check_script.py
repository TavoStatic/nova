import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "health_check.py"
SPEC = importlib.util.spec_from_file_location("nova_health_check_script", SCRIPT_PATH)
HEALTH_CHECK = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(HEALTH_CHECK)


class TestHealthCheckScript(unittest.TestCase):
    def test_suite_command_targets_preflight_lane_runner(self):
        command = HEALTH_CHECK._suite_command()

        self.assertEqual(
            command,
            [
                HEALTH_CHECK.sys.executable,
                str(HEALTH_CHECK.WORKSPACE_ROOT / "run_regression.py"),
                "preflight",
            ],
        )


if __name__ == "__main__":
    unittest.main()