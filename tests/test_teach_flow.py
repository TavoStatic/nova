import json
import re
import shutil
import json
import re
import shutil
import unittest
from pathlib import Path
import nova_core

UPDATES = Path(nova_core.UPDATES_DIR)
TEACH_DIR = UPDATES / "teaching"
EX_FILE = TEACH_DIR / "examples.jsonl"


class TestTeachFlow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            if TEACH_DIR.exists():
                shutil.rmtree(TEACH_DIR)
        except Exception:
            pass

    @classmethod
    def tearDownClass(cls):
        try:
            if TEACH_DIR.exists():
                shutil.rmtree(TEACH_DIR)
        except Exception:
            pass

    def test_teach_store_example_and_file(self):
        ok = nova_core._teach_store_example("orig text", "corrected reply", user="tester")
        self.assertEqual(ok, "OK")
        self.assertTrue(EX_FILE.exists())
        lines = EX_FILE.read_text(encoding="utf-8").strip().splitlines()
        self.assertGreaterEqual(len(lines), 1)
        j = json.loads(lines[-1])
        self.assertEqual(j.get("orig"), "orig text")
        self.assertEqual(j.get("corr"), "corrected reply")
        self.assertEqual(j.get("user"), "tester")

    def test_teach_propose_creates_zip(self):
        # ensure at least one example exists
        nova_core._teach_store_example("orig for propose", "corr for propose", user="tester")
        out = nova_core._teach_propose_patch("test proposal")
        m = re.search(r"teach_proposal_\d{8}_\d{6}\.zip", out)
        self.assertIsNotNone(m, f"No proposal zip mentioned in: {out}")
        fn = UPDATES / m.group(0)
        self.assertTrue(fn.exists())
        try:
            fn.unlink()
        except Exception:
            pass
