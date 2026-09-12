import tempfile
import unittest
from pathlib import Path

from services.regression_lanes import SOURCE_PROFILE_LANES
from services.regression_profile_inventory import build_regression_profile_inventory_payload


class TestRegressionProfileInventoryService(unittest.TestCase):
    def test_inventory_separates_curated_source_observed_and_inactive_install_profile_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "data_sources").mkdir()
            (root / "data_sources" / "__init__.py").write_text("", encoding="utf-8")
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (root / "tests" / "test_curated.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
            (root / "tests" / "test_new_surface.py").write_text("def test_new():\n    assert True\n", encoding="utf-8")
            (root / "tests" / "test_sis_profile.py").write_text(
                "from pathlib import Path\n"
                "import unittest\n"
                "INSTALL_PROFILE_LANES = (\"sis_test\",)\n"
                "INSTALL_PROFILE_INACTIVE_BEHAVIOR = \"skip_when_absent\"\n"
                "@unittest.skipUnless(False, \"sis_test pipeline is not active in this install\")\n"
                "class TestSisProfile(unittest.TestCase):\n"
                "    def test_sis(self):\n"
                "        data_sources_root = Path(__file__).resolve().parents[1] / \"data_sources\"\n"
                "        assert \"sis_test\"\n",
                encoding="utf-8",
            )
            (root / "tests" / "test_stale_sis_profile.py").write_text(
                "from pathlib import Path\n"
                "def test_sis():\n"
                "    data_sources_root = Path(__file__).resolve().parents[1] / \"data_sources\"\n"
                "    assert \"sis_test\"\n",
                encoding="utf-8",
            )

            payload = build_regression_profile_inventory_payload(
                root=root,
                test_lanes={"unit": ["tests.test_curated"]},
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["curated_test_file_count"], 1)
        self.assertEqual(payload["source_observed_count"], 1)
        self.assertEqual(payload["outside_curated_count"], 1)
        self.assertEqual(payload["install_profile_inactive_count"], 1)
        self.assertEqual(payload["install_profile_optional_inactive_count"], 1)
        self.assertEqual(payload["profile_gap_count"], 1)
        self.assertEqual(payload["profile_drift_count"], 2)
        self.assertEqual(payload["profile_attention_count"], 3)
        classes = {item["path"]: item["profile_class"] for item in payload["tests"]}
        self.assertEqual(classes["tests/test_curated.py"], "curated")
        self.assertEqual(classes["tests/test_new_surface.py"], "source_observed")
        self.assertEqual(classes["tests/test_sis_profile.py"], "install_profile_optional_inactive")
        self.assertEqual(classes["tests/test_stale_sis_profile.py"], "install_profile_inactive")
        drift_paths = {item["path"] for item in payload["profile_drift_tests"]}
        self.assertIn("tests/test_new_surface.py", drift_paths)
        self.assertIn("tests/test_stale_sis_profile.py", drift_paths)

    def test_source_observed_tests_are_profile_drift_until_classified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "data_sources").mkdir()
            (root / "data_sources" / "__init__.py").write_text("", encoding="utf-8")
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (root / "tests" / "test_curated.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
            (root / "tests" / "test_new_surface.py").write_text("def test_new():\n    assert True\n", encoding="utf-8")

            payload = build_regression_profile_inventory_payload(
                root=root,
                test_lanes={"unit": ["tests.test_curated"]},
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["profile_gap_count"], 0)
        self.assertEqual(payload["profile_drift_count"], 1)
        self.assertEqual(payload["source_observed_count"], 1)

    def test_source_profile_lanes_classify_current_source_tests(self):
        payload = build_regression_profile_inventory_payload(test_lanes=SOURCE_PROFILE_LANES)

        self.assertEqual(payload["source_observed_count"], 0)
        self.assertEqual(payload["profile_gap_count"], 0)
        self.assertEqual(payload["profile_drift_count"], 0)

    def test_uninstalled_edfi_core_is_not_in_active_source_profile(self):
        payload = build_regression_profile_inventory_payload(test_lanes=SOURCE_PROFILE_LANES)
        by_module = {row["module"]: list(row.get("lanes") or []) for row in payload.get("tests") or []}

        core_modules = {
            "tests.test_edfi_core",
            "tests.test_edfi_core_lifecycle_demo",
            "tests.test_edfi_core_readiness",
            "tests.test_edfi_profile_evidence",
            "tests.test_edfi_change_tracking",
            "tests.test_edfi_district_scope",
            "tests.test_edfi_inventory",
            "tests.test_edfi_resources",
        }
        for module in core_modules:
            row = next(item for item in payload["tests"] if item["module"] == module)
            self.assertEqual(row["profile_class"], "removed_install_surface")
            self.assertEqual(row["lanes"], [])
        self.assertNotIn("source_edfi_core", SOURCE_PROFILE_LANES)
        self.assertNotIn("source_data_lane_data_connector", SOURCE_PROFILE_LANES)


if __name__ == "__main__":
    unittest.main()
