from pathlib import Path
import unittest

from pipelines.registry import PipelineRegistry


DATA_SOURCES_ROOT = Path(__file__).resolve().parents[1] / "data_sources"
SIS_TEST_ACTIVE = (DATA_SOURCES_ROOT / "sis_test" / "pipeline.json").exists()
INSTALL_PROFILE_LANES = ("sis_test",)
INSTALL_PROFILE_INACTIVE_BEHAVIOR = "skip_when_absent"


@unittest.skipUnless(SIS_TEST_ACTIVE, "sis_test pipeline is not active in this install")
class TestPipelineRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = PipelineRegistry(DATA_SOURCES_ROOT)

    def test_discovers_sis_test_pipeline(self):
        summaries = self.registry.list_summaries()
        pipeline_ids = [item["pipeline_id"] for item in summaries]
        self.assertIn("sis_test", pipeline_ids)

    def test_instantiates_sis_test_connector(self):
        pipeline = self.registry.instantiate("sis_test")
        self.assertEqual(pipeline.manifest.pipeline_id, "sis_test")
        self.assertTrue(pipeline.manifest.read_only)
        self.assertIn("student_lookup", pipeline.load_query_templates())
        self.assertIn("schema_inventory", pipeline.load_query_templates())
        self.assertTrue(str(pipeline.manifest.population_definitions_path).endswith("population_definitions.json"))
        self.assertTrue(str(pipeline.manifest.vendor_dictionary_path).endswith("vendor_dictionary_index.json"))
        self.assertTrue(str(pipeline.manifest.predefined_reports_path).endswith("predefined_reports_index.json"))


if __name__ == "__main__":
    unittest.main()
