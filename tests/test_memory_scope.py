import tempfile
import unittest
from pathlib import Path

import memory


class TestMemoryScope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig_db_path = memory.DB_PATH
        self.orig_embed = memory.embed
        self.orig_connect = memory.connect
        memory.DB_PATH = Path(self.tmp.name) / "memory_scope.sqlite"

        def fake_embed(text: str):
            low = (text or "").lower()
            return [
                1.0 if "otter" in low else 0.0,
                1.0 if "shared" in low else 0.0,
                1.0 if "alpha" in low else 0.0,
                1.0,
            ]

        memory.embed = fake_embed
        memory.reset()

    def tearDown(self):
        memory.DB_PATH = self.orig_db_path
        memory.embed = self.orig_embed
        memory.connect = self.orig_connect
        self.tmp.cleanup()

    def test_connections_close_when_embed_raises(self):
        closed = []

        class DummyConnection:
            def execute(self, *_args, **_kwargs):
                return self

            def fetchall(self):
                return []

            def commit(self):
                return None

            def close(self):
                closed.append(True)

        memory.connect = lambda: DummyConnection()
        memory.embed = lambda _text: (_ for _ in ()).throw(RuntimeError("embed_failed"))

        with self.assertRaises(RuntimeError):
            memory.add_memory("fact", "typed", "otter", user="userA", scope="private")
        self.assertEqual(len(closed), 1)

        with self.assertRaises(RuntimeError):
            memory.recall("otter", user="userA", scope="private")
        self.assertEqual(len(closed), 2)

        with self.assertRaises(RuntimeError):
            memory.recall_explain("otter", user="userA", scope="private")
        self.assertEqual(len(closed), 3)

    def test_private_scope_requires_user(self):
        with self.assertRaises(RuntimeError):
            memory.add_memory("fact", "typed", "otter private note", user="", scope="private")

    def test_private_scope_isolated_per_user(self):
        memory.add_memory("fact", "typed", "otter alpha private note", user="userA", scope="private")
        memory.add_memory("fact", "typed", "otter beta private note", user="userB", scope="private")

        out_a = memory.recall_explain("otter", user="userA", scope="private")
        out_b = memory.recall_explain("otter", user="userB", scope="private")

        self.assertEqual(len(out_a["results"]), 1)
        self.assertIn("alpha", out_a["results"][0]["preview"].lower())
        self.assertEqual(len(out_b["results"]), 1)
        self.assertIn("beta", out_b["results"][0]["preview"].lower())

    def test_hybrid_scope_includes_private_and_shared(self):
        memory.add_memory("fact", "typed", "otter alpha private note", user="userA", scope="private")
        memory.add_memory("fact", "typed", "shared otter handbook", user="", scope="shared")

        out = memory.recall_explain("otter", user="userA", scope="hybrid")
        previews = "\n".join(item["preview"].lower() for item in out["results"])

        self.assertIn("alpha private note", previews)
        self.assertIn("shared otter handbook", previews)

    def test_shared_scope_only_reads_shared_records(self):
        memory.add_memory("fact", "typed", "shared otter handbook", user="", scope="shared")
        memory.add_memory("fact", "typed", "otter alpha private note", user="userA", scope="private")

        out = memory.recall_explain("otter", user="userA", scope="shared")
        previews = [item["preview"].lower() for item in out["results"]]

        self.assertEqual(len(previews), 1)
        self.assertIn("shared otter handbook", previews[0])


if __name__ == "__main__":
    unittest.main()