import json
import shutil
import unittest
from pathlib import Path
import nova_core

UPDATES = Path(nova_core.UPDATES_DIR)
TEACH_DIR = UPDATES / "teaching"
EX_FILE = TEACH_DIR / "examples.jsonl"


class TestIntegrationOverride(unittest.TestCase):

    def setUp(self):
        if TEACH_DIR.exists():
            shutil.rmtree(TEACH_DIR)
        TEACH_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if TEACH_DIR.exists():
            shutil.rmtree(TEACH_DIR)

    def test_apply_override_after_store(self):
        orig = "Hello."
        corr = "Hi Gus."
        # store example
        res = nova_core._teach_store_example(orig, corr, user="tester")
        self.assertEqual(res, "OK")
        # ensure file exists
        self.assertTrue(EX_FILE.exists())
        # apply override
        out = nova_core._apply_reply_overrides(orig)
        self.assertEqual(out, corr)

    def test_parse_correction_and_store(self):
        # simulate last assistant reply and a user correction phrase
        last = "Hello."
        phrase = "no - say 'Hi Gus' instead"
        parsed = nova_core._parse_correction(phrase)
        self.assertEqual(parsed, "Hi Gus")
        # store via helper
        nova_core._teach_store_example(last, parsed, user="tester")
        # verify override
        out = nova_core._apply_reply_overrides(last)
        self.assertEqual(out, "Hi Gus")

    def test_apply_override_does_not_require_embeddings(self):
        orig_embed = None
        had_embed = False
        if nova_core.memory_mod is not None and hasattr(nova_core.memory_mod, "embed"):
            had_embed = True
            orig_embed = nova_core.memory_mod.embed
            nova_core.memory_mod.embed = lambda _text: (_ for _ in ()).throw(AssertionError("embed should not be called"))
        try:
            orig = "Hello."
            corr = "Hi Gus."
            nova_core._teach_store_example(orig, corr, user="tester")
            out = nova_core._apply_reply_overrides(orig)
            self.assertEqual(out, corr)
        finally:
            if had_embed:
                nova_core.memory_mod.embed = orig_embed

    def test_fuzzy_override(self):
        # store an original with punctuation
        orig = "Hello there."
        corr = "Hi Gus."
        nova_core._teach_store_example(orig, corr, user="tester")
        # apply override with slightly different punctuation
        out1 = nova_core._apply_reply_overrides("Hello there")
        out2 = nova_core._apply_reply_overrides("Hello, there!")
        self.assertIn(out1, {corr, orig})
        self.assertIn(out2, {corr, orig})


if __name__ == '__main__':
    unittest.main()
