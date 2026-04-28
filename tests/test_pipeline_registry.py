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


if __name__ == "__main__":
    unittest.main()
