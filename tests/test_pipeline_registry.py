from pathlib import Path
import unittest

from pipelines.registry import PipelineRegistry


class TestPipelineRegistry(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        self.registry = PipelineRegistry(self.repo_root / "data_sources")

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
