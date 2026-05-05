import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_regression.py"
SPEC = importlib.util.spec_from_file_location("nova_run_regression_script", SCRIPT_PATH)
RUN_REGRESSION = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(RUN_REGRESSION)


class TestRunRegressionScript(unittest.TestCase):
    def test_resolve_requested_lanes_defaults_to_unit(self):
        args = RUN_REGRESSION.parse_args([])

        self.assertEqual(RUN_REGRESSION.resolve_requested_lanes(args), ["unit"])

    def test_resolve_requested_lanes_expands_all(self):
        args = RUN_REGRESSION.parse_args(["--lane", "all"])

        self.assertEqual(
            RUN_REGRESSION.resolve_requested_lanes(args),
            ["unit", "behavior", "integration"],
        )

    def test_main_runs_selected_lane(self):
        lane_calls = []

        with patch.object(RUN_REGRESSION, "run_step", return_value=0), \
             patch.object(RUN_REGRESSION, "write_regression_status") as status_mock, \
             patch.object(
                 RUN_REGRESSION,
                 "run_test_lane",
                 side_effect=lambda lane, verbosity=1: lane_calls.append((lane, verbosity)) or 0,
             ):
            code = RUN_REGRESSION.main(["behavior", "--verbosity", "2"])

        self.assertEqual(code, 0)
        self.assertEqual(lane_calls, [("behavior", 2)])
        status_mock.assert_called_once()

    def test_main_lists_available_lanes(self):
        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            code = RUN_REGRESSION.main(["--list-lanes"])

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("Available test lanes:", output)
        self.assertIn("- unit:", output)
        self.assertIn("- behavior:", output)
        self.assertIn("- integration:", output)

    def test_write_regression_status_records_validation_marker(self):
        marker = Path("C:/Nova/runtime/_test_tmp") / "regression_status_test.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        try:
            with patch.object(RUN_REGRESSION, "REGRESSION_STATUS_FILE", marker):
                RUN_REGRESSION.write_regression_status(status="OK", lanes=["unit"], returncode=0)

            payload = json.loads(marker.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["lanes"], ["unit"])
            self.assertEqual(payload["returncode"], 0)
            self.assertEqual(payload["source"], "scripts/run_regression.py")
        finally:
            try:
                marker.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
