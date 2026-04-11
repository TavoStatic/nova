import json
import tempfile
import unittest
from pathlib import Path

from services.ops_journal import append_ops_event


class TestOpsJournal(unittest.TestCase):
    def test_append_ops_event_writes_jsonl_entry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            append_ops_event(
                root,
                category="control_action",
                action="refresh_status",
                result="ok",
                detail="status_refreshed",
                payload={"session_id": "abc", "count": 2},
            )

            journal = root / "ops_journal.jsonl"
            self.assertTrue(journal.exists())
            lines = journal.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            self.assertEqual(entry.get("category"), "control_action")
            self.assertEqual(entry.get("action"), "refresh_status")
            self.assertEqual(entry.get("result"), "ok")
            self.assertEqual((entry.get("payload") or {}).get("session_id"), "abc")


if __name__ == "__main__":
    unittest.main()
