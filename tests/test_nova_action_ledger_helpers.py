import tempfile
import unittest
from pathlib import Path

from services import nova_action_ledger_helpers


class TestNovaActionLedgerHelpers(unittest.TestCase):
    def test_recent_action_ledger_records_reads_latest_dict_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "001.json").write_text('{"tool": "web_research"}', encoding="utf-8")
            (root / "002.json").write_text('{"tool": "wikipedia_lookup"}', encoding="utf-8")

            records = nova_action_ledger_helpers.recent_action_ledger_records(root, limit=1)

        self.assertEqual(records, [{"tool": "wikipedia_lookup"}])

    def test_latest_action_ledger_record_returns_last_payload(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "001.json").write_text('{"tool": "web_research"}', encoding="utf-8")
            (root / "002.json").write_text('{"tool": "stackexchange_search"}', encoding="utf-8")

            record = nova_action_ledger_helpers.latest_action_ledger_record(root)

        self.assertEqual(record, {"tool": "stackexchange_search"})

    def test_record_completed_tool_execution_detects_tool_execution_step(self):
        record = {"route_trace": [{"stage": "tool_execution", "outcome": "ok"}]}

        self.assertTrue(nova_action_ledger_helpers.record_completed_tool_execution(record))

    def test_record_requested_tool_clarification_detects_pending_location(self):
        record = {"route_trace": [{"stage": "pending_action", "outcome": "awaiting_location"}]}

        self.assertTrue(nova_action_ledger_helpers.record_requested_tool_clarification(record))

    def test_detect_repeated_tool_intent_without_execution_uses_labels(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "001.json").write_text(
                '{"intent": "web_research", "route_trace": [{"stage": "planner", "outcome": "selected"}]}',
                encoding="utf-8",
            )
            (root / "002.json").write_text(
                '{"intent": "web_research", "route_trace": [{"stage": "planner", "outcome": "selected"}]}',
                encoding="utf-8",
            )

            payload = nova_action_ledger_helpers.detect_repeated_tool_intent_without_execution(root)

        self.assertEqual(payload["intent"], "web_research")
        self.assertIn("Web research route selected 2 times", payload["summary"])

    def test_count_unsupported_claim_blocks_recently_counts_claim_gate_and_autonomy_guard(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "001.json").write_text(
                '{"route_trace": [{"stage": "claim_gate", "outcome": "adjusted", "detail": "unsupported"}]}',
                encoding="utf-8",
            )
            (root / "002.json").write_text(
                '{"route_trace": [{"stage": "llm_postprocess", "outcome": "self_corrected", "detail": "autonomy_guard"}]}',
                encoding="utf-8",
            )

            count = nova_action_ledger_helpers.count_unsupported_claim_blocks_recently(root)

        self.assertEqual(count, 2)

    def test_sample_intents_last_returns_unknown_for_blank_intent(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "001.json").write_text('{"intent": "weather_lookup"}', encoding="utf-8")
            (root / "002.json").write_text('{"intent": ""}', encoding="utf-8")

            sample = nova_action_ledger_helpers.sample_intents_last(root, count=2)

        self.assertEqual(sample, ["weather_lookup", "unknown"])


if __name__ == "__main__":
    unittest.main()