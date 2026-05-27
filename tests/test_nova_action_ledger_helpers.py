import os
import shutil
import unittest
import uuid
from pathlib import Path

from services import nova_action_ledger_helpers


WORK_TMP_ROOT = Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "pytest_temp"


def _workspace_case_dir(prefix: str) -> Path:
    WORK_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_TMP_ROOT / f"{prefix}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestNovaActionLedgerHelpers(unittest.TestCase):
    def test_recent_action_ledger_records_reads_latest_dict_files(self):
        root = _workspace_case_dir("nova_action_ledger_helpers")
        try:
            (root / "001.json").write_text('{"tool": "web_research"}', encoding="utf-8")
            (root / "002.json").write_text('{"tool": "wikipedia_lookup"}', encoding="utf-8")

            records = nova_action_ledger_helpers.recent_action_ledger_records(root, limit=1)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(records, [{"tool": "wikipedia_lookup"}])

    def test_latest_action_ledger_record_returns_last_payload(self):
        root = _workspace_case_dir("nova_action_ledger_helpers")
        try:
            (root / "001.json").write_text('{"tool": "web_research"}', encoding="utf-8")
            (root / "002.json").write_text('{"tool": "stackexchange_search"}', encoding="utf-8")

            record = nova_action_ledger_helpers.latest_action_ledger_record(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(record, {"tool": "stackexchange_search"})

    def test_action_history_reply_formats_last_record(self):
        root = _workspace_case_dir("nova_action_ledger_helpers")
        try:
            (root / "002.json").write_text(
                '{"tool": "stackexchange_search", "planner_decision": "run_tool", "intent": "web_research", "grounded": true, "final_answer": "done"}',
                encoding="utf-8",
            )

            reply = nova_action_ledger_helpers.action_history_reply(
                root,
                action_ledger_route_summary_fn=lambda rec: "planner:run_tool",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertIn("intent=web_research", reply)
        self.assertIn("decision=run_tool", reply)
        self.assertIn("route=planner:run_tool", reply)

    def test_record_completed_tool_execution_detects_tool_execution_step(self):
        record = {"route_trace": [{"stage": "tool_execution", "outcome": "ok"}]}

        self.assertTrue(nova_action_ledger_helpers.record_completed_tool_execution(record))

    def test_record_requested_tool_clarification_detects_pending_location(self):
        record = {"route_trace": [{"stage": "pending_action", "outcome": "awaiting_location"}]}

        self.assertTrue(nova_action_ledger_helpers.record_requested_tool_clarification(record))

    def test_detect_repeated_tool_intent_without_execution_uses_labels(self):
        root = _workspace_case_dir("nova_action_ledger_helpers")
        try:
            (root / "001.json").write_text(
                '{"intent": "web_research", "route_trace": [{"stage": "planner", "outcome": "selected"}]}',
                encoding="utf-8",
            )
            (root / "002.json").write_text(
                '{"intent": "web_research", "route_trace": [{"stage": "planner", "outcome": "selected"}]}',
                encoding="utf-8",
            )

            payload = nova_action_ledger_helpers.detect_repeated_tool_intent_without_execution(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(payload["intent"], "web_research")
        self.assertIn("Web research route selected 2 times", payload["summary"])

    def test_sample_intents_last_returns_unknown_for_blank_intent(self):
        root = _workspace_case_dir("nova_action_ledger_helpers")
        try:
            (root / "001.json").write_text('{"intent": "weather_lookup"}', encoding="utf-8")
            (root / "002.json").write_text('{"intent": ""}', encoding="utf-8")

            sample = nova_action_ledger_helpers.sample_intents_last(root, count=2)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(sample, ["weather_lookup", "unknown"])


if __name__ == "__main__":
    unittest.main()
