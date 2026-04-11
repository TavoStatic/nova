import json
import tempfile
import unittest
from pathlib import Path

from services.nova_action_ledger import write_action_ledger_record


class TestNovaActionLedgerService(unittest.TestCase):
    def test_write_action_ledger_record_appends_ops_journal_event(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger_dir = root / "action_ledger"
            rec = {
                "user_input": "check queue",
                "intent": "system_check",
                "planner_decision": "run_tool",
                "tool": "queue_status",
                "grounded": True,
                "final_answer": "done",
            }

            out = write_action_ledger_record(rec, action_ledger_dir=ledger_dir)
            self.assertIsNotNone(out)
            self.assertTrue(Path(out).exists())

            ops = root / "ops_journal.jsonl"
            self.assertTrue(ops.exists())
            rows = [json.loads(line) for line in ops.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertGreaterEqual(len(rows), 1)
            last = rows[-1]
            self.assertEqual(last.get("category"), "action_ledger")
            self.assertEqual(last.get("action"), "write_record")
            self.assertEqual(last.get("result"), "ok")


if __name__ == "__main__":
    unittest.main()
