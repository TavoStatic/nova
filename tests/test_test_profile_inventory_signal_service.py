import unittest

from services.work_tree_signal_ingestion import _test_profile_inventory_signal_from_status


class TestProfileInventorySignalService(unittest.TestCase):
    def test_signal_reports_validation_profile_gap(self):
        signal = _test_profile_inventory_signal_from_status({
            "test_profile_inventory_ok": False,
            "test_profile_profile_gap_count": 2,
            "test_profile_outside_curated_count": 1,
            "test_profile_install_profile_inactive_count": 1,
            "test_profile_inventory": {
                "gap_tests": [
                    {
                        "path": "tests/test_data_pipeline_registry_service.py",
                        "profile_class": "install_profile_inactive",
                    }
                ]
            },
        })

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal["source"], "test_profile_inventory")
        self.assertEqual(signal["signal_class"], "governance_pressure")
        self.assertEqual(signal["fingerprint"]["error"], "inactive_install_profile_tests")
        self.assertEqual(signal["payload"]["profile_gap_count"], 2)

    def test_signal_clears_when_profile_inventory_is_clean(self):
        signal = _test_profile_inventory_signal_from_status({
            "test_profile_inventory_ok": True,
            "test_profile_profile_gap_count": 0,
            "test_profile_inventory": {"ok": True, "profile_gap_count": 0},
        })

        self.assertIsNone(signal)

    def test_source_observed_tests_create_profile_drift_signal_without_becoming_gaps(self):
        signal = _test_profile_inventory_signal_from_status({
            "test_profile_inventory_ok": False,
            "test_profile_profile_gap_count": 0,
            "test_profile_profile_drift_count": 12,
            "test_profile_source_observed_count": 12,
            "test_profile_inventory": {
                "ok": False,
                "profile_gap_count": 0,
                "profile_drift_count": 12,
                "source_observed_count": 12,
                "profile_drift_tests": [
                    {
                        "path": "tests/test_new_autonomy_surface.py",
                        "profile_class": "source_observed",
                    }
                ],
            },
        })

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal["fingerprint"]["error"], "source_observed_tests_outside_validation_profile")
        self.assertEqual(signal["payload"]["profile_gap_count"], 0)
        self.assertEqual(signal["payload"]["profile_drift_count"], 12)
        self.assertEqual(signal["payload"]["profile_drift_tests"][0]["path"], "tests/test_new_autonomy_surface.py")


if __name__ == "__main__":
    unittest.main()
