import tempfile
import unittest
from pathlib import Path

import memory


class TestMemoryPinnedPriority(unittest.TestCase):
    def setUp(self):
        self.orig_db_path = memory.DB_PATH
        self.orig_embed = memory.embed
        self.tmp = tempfile.TemporaryDirectory()
        memory.DB_PATH = Path(self.tmp.name) / "test_memory.sqlite"

        def fake_embed(text: str):
            t = (text or "").lower()
            if "query-token" in t:
                return [1.0, 0.0]
            if "normal-fact" in t:
                return [0.74, 0.67]
            if "pinned-fact" in t:
                return [0.66, 0.75]
            return [0.0, 1.0]

        memory.embed = fake_embed

    def tearDown(self):
        memory.DB_PATH = self.orig_db_path
        memory.embed = self.orig_embed
        self.tmp.cleanup()

    def test_pinned_fact_is_ranked_above_non_pinned(self):
        memory.add_memory("note", "chat", "normal-fact alpha", user="tester", scope="private")
        memory.add_memory("fact", "pinned", "pinned-fact alpha", user="tester", scope="private")

        hits = memory.recall("query-token alpha", top_k=2, min_score=0.0, user="tester", scope="private")
        self.assertGreaterEqual(len(hits), 2)
        self.assertEqual(hits[0][3], "pinned")

    def test_pinned_fact_can_pass_threshold_with_boost(self):
        memory.add_memory("note", "chat", "normal-fact beta", user="tester", scope="private")
        memory.add_memory("fact", "pinned", "pinned-fact beta", user="tester", scope="private")

        hits = memory.recall("query-token beta", top_k=5, min_score=0.78, user="tester", scope="private")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][3], "pinned")


if __name__ == "__main__":
    unittest.main()
