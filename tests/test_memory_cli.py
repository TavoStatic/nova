import subprocess
import sys
import unittest
import tempfile


class TestMemoryCLI(unittest.TestCase):
    def test_add_and_recall(self):
        py = sys.executable
        # add a unique entry
        text = "integration-test-memory: bravo-98765"
        r = subprocess.run([py, "memory.py", "add", "--kind", "test", "--source", "unittest", "--text", text], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("OK", r.stdout)

        # recall it
        r2 = subprocess.run([py, "memory.py", "recall", "--query", "bravo-98765", "--topk", "5", "--minscore", "0"], capture_output=True, text=True)
        self.assertEqual(r2.returncode, 0)
        out = (r2.stdout or "") + (r2.stderr or "")
        self.assertIn("bravo-98765", out)


if __name__ == "__main__":
    unittest.main()
