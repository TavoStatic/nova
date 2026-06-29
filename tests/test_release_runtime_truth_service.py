import unittest

from services.release_runtime_truth import (
    build_release_runtime_truth_summary,
    enrich_release_status,
    evaluate_http_model_runtime_probe,
    release_drift_suppresses_closure_signals,
)


class TestReleaseRuntimeTruthService(unittest.TestCase):
    def test_enrich_release_status_marks_expected_drift(self):
        release = enrich_release_status(
            {
                "latest_readiness_state": "source-changed-after-build",
                "latest_source_changed_after_build": True,
                "latest_version": "2026.06.29.1",
                "latest_channel": "rc",
                "latest_label": "push-prep",
            }
        )

        self.assertTrue(release.get("runtime_drift_expected"))
        self.assertTrue(release.get("runtime_drift_tolerated"))
        self.assertEqual(release.get("running_build_identity"), "2026.06.29.1:rc:push-prep")

    def test_release_drift_suppresses_closure_signals(self):
        self.assertTrue(
            release_drift_suppresses_closure_signals(
                {"latest_readiness_state": "source-changed-after-build"}
            )
        )
        self.assertFalse(
            release_drift_suppresses_closure_signals({"latest_readiness_state": "ready"})
        )

    def test_build_release_runtime_truth_summary_exposes_suppression_flag(self):
        truth = build_release_runtime_truth_summary(
            {
                "latest_readiness_state": "source-changed-after-build",
                "latest_source_changed_after_build": True,
            }
        )

        self.assertTrue(truth.get("runtime_drift_expected"))
        self.assertTrue(truth.get("suppress_closure_inventory_signals"))

    def test_evaluate_http_model_runtime_probe_reports_missing_keys(self):
        probe = evaluate_http_model_runtime_probe({"ollama_api_up": True})

        self.assertFalse(probe.get("ok"))
        self.assertIn("ollama_health", probe.get("missing_keys") or [])
        self.assertIn("port_ownership", probe.get("missing_keys") or [])


if __name__ == "__main__":
    unittest.main()