import importlib.util
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from services.regression_lanes import COMPACT_REGRESSION_LANES


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_regression.py"
SPEC = importlib.util.spec_from_file_location("nova_run_regression_script", SCRIPT_PATH)
RUN_REGRESSION = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(RUN_REGRESSION)


def _validation_tmp_root() -> Path:
    return Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or RUN_REGRESSION.BASE / "runtime" / "validation") / "_test_tmp"


class TestRunRegressionScript(unittest.TestCase):
    def test_resolve_requested_lanes_defaults_to_unit(self):
        args = RUN_REGRESSION.parse_args([])

        self.assertEqual(RUN_REGRESSION.resolve_requested_lanes(args), ["unit"])

    def test_compact_lane_map_uses_shared_regression_source(self):
        self.assertEqual(RUN_REGRESSION.TEST_LANES, COMPACT_REGRESSION_LANES)

    def test_resolve_requested_lanes_expands_all(self):
        args = RUN_REGRESSION.parse_args(["--lane", "all"])

        self.assertEqual(
            RUN_REGRESSION.resolve_requested_lanes(args),
            ["unit", "behavior", "integration"],
        )

    def test_main_runs_selected_lane(self):
        lane_calls = []

        with patch.object(RUN_REGRESSION, "_acquire_regression_lock", return_value=(True, "")), \
             patch.object(RUN_REGRESSION, "_release_regression_lock"), \
             patch.object(RUN_REGRESSION, "run_step", return_value=0), \
             patch.object(RUN_REGRESSION, "audit_validation_artifacts_after_green_run", return_value={"ok": True, "status": "ok"}), \
             patch.object(RUN_REGRESSION, "write_regression_status") as status_mock, \
             patch.object(
                 RUN_REGRESSION,
                 "run_test_lane",
                 side_effect=lambda lane, verbosity=1: lane_calls.append((lane, verbosity)) or (0, []),
             ):
            code = RUN_REGRESSION.main(["behavior", "--verbosity", "2"])

        self.assertEqual(code, 0)
        self.assertEqual(lane_calls, [("behavior", 2)])
        status_mock.assert_not_called()

    def test_main_passes_with_advisory_when_llm_unavailable_hidden_by_green_regression(self):
        with patch.object(RUN_REGRESSION, "_acquire_regression_lock", return_value=(True, "")), \
             patch.object(RUN_REGRESSION, "_release_regression_lock"), \
             patch.object(RUN_REGRESSION, "run_step", return_value=0), \
             patch.object(RUN_REGRESSION, "run_test_lane", return_value=(0, [])), \
             patch.object(
                 RUN_REGRESSION,
                 "audit_validation_artifacts_after_green_run",
                 return_value={
                     "ok": False,
                     "status": "llm_unavailable_in_green_regression",
                     "current_window_failure_count": 2,
                     "current_window_llm_unavailable_count": 2,
                     "hidden_by_green_regression": True,
                     "latest_failure": {
                         "path": "runtime/validation/actions/bad.json",
                         "failure_kind": "llm_service_unavailable",
                         "final_answer": "(error: LLM service unavailable)",
                     },
                 },
             ), \
             patch.object(RUN_REGRESSION, "write_regression_status") as status_mock:
            code = RUN_REGRESSION.main(["unit"])

        self.assertEqual(code, 0)
        status_mock.assert_not_called()

    def test_main_fails_when_validation_artifacts_disagree_with_non_llm_failures(self):
        with patch.object(RUN_REGRESSION, "_acquire_regression_lock", return_value=(True, "")), \
             patch.object(RUN_REGRESSION, "_release_regression_lock"), \
             patch.object(RUN_REGRESSION, "run_step", return_value=0), \
             patch.object(RUN_REGRESSION, "run_test_lane", return_value=(0, [])), \
             patch.object(
                 RUN_REGRESSION,
                 "audit_validation_artifacts_after_green_run",
                 return_value={
                     "ok": False,
                     "status": "validation_failure_in_green_regression",
                     "current_window_failure_count": 1,
                     "current_window_llm_unavailable_count": 0,
                     "hidden_by_green_regression": True,
                     "latest_failure": {
                         "path": "runtime/validation/actions/bad.json",
                         "failure_kind": "final_answer_error",
                         "final_answer": "(error: planner route failed)",
                     },
                 },
             ), \
             patch.object(RUN_REGRESSION, "write_regression_status") as status_mock:
            code = RUN_REGRESSION.main(["unit"])

        self.assertEqual(code, 1)
        status_mock.assert_called_once()
        kwargs = status_mock.call_args.kwargs
        self.assertEqual(kwargs.get("status"), "FAILED")
        self.assertIn("validation_artifact_truth:validation_failure_in_green_regression", kwargs.get("detail"))

    def test_main_lists_available_lanes(self):
        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            code = RUN_REGRESSION.main(["--list-lanes"])

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("Available test lanes:", output)
        self.assertIn("- unit:", output)
        self.assertIn("- behavior:", output)
        self.assertIn("- integration:", output)

    def test_run_unittest_suite_marks_regression_test_mode(self):
        observed_load = []
        observed_run = []

        class _Result:
            failures = []
            errors = []

            @staticmethod
            def wasSuccessful():
                return True

        class _Loader:
            def loadTestsFromNames(self, test_names):
                observed_load.append(
                    {
                        "test_runner": os.environ.get("NOVA_TEST_RUNNER"),
                        "validation_runtime": os.environ.get("NOVA_VALIDATION_RUNTIME_DIR"),
                        "test_names": list(test_names),
                    }
                )
                return object()

        class _Runner:
            def __init__(self, verbosity=1):
                self.verbosity = verbosity

            def run(self, suite):
                observed_run.append(
                    {
                        "test_runner": os.environ.get("NOVA_TEST_RUNNER"),
                        "validation_runtime": os.environ.get("NOVA_VALIDATION_RUNTIME_DIR"),
                    }
                )
                return _Result()

        with patch.object(RUN_REGRESSION.unittest, "TextTestRunner", _Runner), \
             patch.object(RUN_REGRESSION.unittest, "defaultTestLoader", _Loader()), \
             patch.dict(os.environ, {}, clear=True):
            ok, failed = RUN_REGRESSION.run_unittest_suite(["tests.test_smoke_placeholder"], verbosity=1)
            restored = os.environ.get("NOVA_TEST_RUNNER")
            restored_validation = os.environ.get("NOVA_VALIDATION_RUNTIME_DIR")

        self.assertTrue(ok)
        self.assertEqual(failed, [])
        self.assertEqual(observed_load[0].get("test_runner"), "1")
        self.assertEqual(observed_load[0].get("test_names"), ["tests.test_smoke_placeholder"])
        self.assertEqual(observed_load[0].get("validation_runtime"), str(RUN_REGRESSION.BASE / "runtime" / "validation"))
        self.assertEqual(observed_run[0].get("test_runner"), "1")
        self.assertEqual(observed_run[0].get("validation_runtime"), str(RUN_REGRESSION.BASE / "runtime" / "validation"))
        self.assertIsNone(restored)
        self.assertIsNone(restored_validation)

    def test_write_regression_status_records_validation_marker(self):
        marker = _validation_tmp_root() / "regression_status_test.json"
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
