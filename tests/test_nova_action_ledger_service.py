import json
import shutil
import unittest
import uuid
from pathlib import Path

from services.nova_action_ledger import write_action_ledger_record


WORK_TMP_ROOT = Path(__file__).resolve().parents[1] / "runtime" / "pytest_temp"


def _workspace_case_dir(prefix: str) -> Path:
    WORK_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_TMP_ROOT / f"{prefix}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestNovaActionLedgerService(unittest.TestCase):
    def test_write_action_ledger_record_appends_ops_journal_event(self):
        case_dir = _workspace_case_dir("action_ledger")
        try:
            root = case_dir
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
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
