import os
import subprocess
import sys
import unittest
import tempfile
from pathlib import Path
from unittest import mock

import requests

import memory


class TestMemoryCLI(unittest.TestCase):
    def test_offline_embedding_fallback_is_deterministic(self):
        with mock.patch.object(memory.requests, "post", side_effect=requests.ConnectionError("offline")):
            first = memory.embed("offline-memory-check")
            second = memory.embed("offline-memory-check")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 32)
        self.assertGreater(memory.vec_norm(first), 0.0)

    def test_add_and_recall(self):
        py = sys.executable
        with tempfile.TemporaryDirectory() as tmp:
            env = {"NOVA_MEMORY_DB": str(Path(tmp) / "nova_memory_test.sqlite")}
            text = "integration-test-memory: bravo-98765"
            r = subprocess.run(
                [py, "memory.py", "add", "--kind", "test", "--source", "unittest", "--text", text],
                capture_output=True,
                text=True,
                env={**os.environ, **env},
            )
            self.assertEqual(r.returncode, 0)
            self.assertIn("OK", r.stdout)

            r2 = subprocess.run(
                [py, "memory.py", "recall", "--query", "bravo-98765", "--topk", "5", "--minscore", "0"],
                capture_output=True,
                text=True,
                env={**os.environ, **env},
            )
            self.assertEqual(r2.returncode, 0)
            out = (r2.stdout or "") + (r2.stderr or "")
            self.assertIn("bravo-98765", out)


if __name__ == "__main__":
    unittest.main()
