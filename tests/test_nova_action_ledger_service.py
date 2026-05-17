import os
import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from services import nova_action_ledger
from services.nova_action_ledger import finalize_action_ledger_record_from_runtime
from services.nova_action_ledger import write_action_ledger_record


WORK_TMP_ROOT = Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "pytest_temp"


def _workspace_case_dir(prefix: str) -> Path:
    WORK_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_TMP_ROOT / f"{prefix}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestNovaActionLedgerService(unittest.TestCase):
    def test_finalize_action_ledger_record_from_runtime_uses_scope_hooks(self):
        case_dir = _workspace_case_dir("action_ledger_runtime")
        try:
            written: list[dict] = []
            reflection_calls: list[dict] = []
            runtime_scope = {
                "_provider_name_from_tool": lambda tool: f"provider:{tool}",
                "_finalize_routing_decision": lambda routing_decision, **kwargs: {"path": "runtime"},
                "action_ledger_add_step": lambda record, stage, status, **kwargs: record.setdefault("route_trace", []).append(
                    {"stage": stage, "status": status, **kwargs}
                ),
                "action_ledger_route_summary": lambda record: f"summary:{record.get('planner_decision')}",
                "write_action_ledger_record": lambda record: written.append(dict(record)) or (case_dir / "record.json"),
                "_recent_action_ledger_records": lambda limit=20: [{"planner_decision": "deterministic"}],
                "maybe_log_self_reflection": lambda **kwargs: reflection_calls.append(dict(kwargs)) or {"ok": True},
            }

            out = finalize_action_ledger_record_from_runtime(
                {"user_input": "check queue", "route_trace": []},
                final_answer="done",
                planner_decision="run_tool",
                tool="queue_status",
                reply_contract="queue.status",
                runtime_scope=runtime_scope,
            )

            self.assertEqual(out, case_dir / "record.json")
            self.assertEqual(len(written), 1)
            self.assertEqual(written[0].get("provider_used"), "provider:queue_status")
            self.assertEqual(written[0].get("routing_decision"), {"path": "runtime"})
            self.assertEqual(written[0].get("route_summary"), "summary:run_tool")
            self.assertEqual(len(reflection_calls), 1)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)

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

    def test_write_record_filename_uses_single_clock_sample_for_sorting(self):
        case_dir = _workspace_case_dir("action_ledger_clock")
        try:
            with patch.object(nova_action_ledger.time, "time", side_effect=[1000.987, 1000.988, 1001.003, 1001.004]), \
                 patch.object(nova_action_ledger.time, "time_ns", side_effect=[1000987000000, 1001003000000]):
                first = write_action_ledger_record({"user_input": "first"}, action_ledger_dir=case_dir)
                second = write_action_ledger_record({"user_input": "second"}, action_ledger_dir=case_dir)

            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            paths = sorted(case_dir.glob("*.json"))
            self.assertEqual([path.name for path in paths], [first.name, second.name])
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
