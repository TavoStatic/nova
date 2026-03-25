import json
import tempfile
import unittest
from pathlib import Path

from subconscious_runner import (
    build_generated_session_definitions,
    build_unattended_report,
    main,
    select_live_scenario_families,
    write_generated_session_definitions,
    write_report_bundle,
)
from subconscious_live_simulator import simulate_live_families


class TestSubconsciousRunner(unittest.TestCase):
    def test_select_live_scenario_families_filters_requested_family(self):
        families = select_live_scenario_families(["fulfillment-fallthrough-family"])

        self.assertEqual(len(families), 1)
        self.assertEqual(getattr(families[0], "family_id", None), "fulfillment-fallthrough-family")

    def test_select_live_scenario_families_rejects_unknown_family(self):
        with self.assertRaises(ValueError):
            select_live_scenario_families(["missing-family"])

    def test_build_unattended_report_accumulates_priorities(self):
        families = select_live_scenario_families(["fulfillment-fallthrough-family", "repeated-weak-pressure-family"])
        results = simulate_live_families(families)

        report = build_unattended_report(results, label="overnight")

        self.assertEqual(report["label"], "overnight")
        self.assertEqual(report["totals"]["family_count"], 2)
        self.assertGreater(report["totals"]["training_priority_count"], 0)
        by_id = {item["family_id"]: item for item in report["families"]}
        self.assertIn("fulfillment-fallthrough-family", by_id)
        self.assertTrue(by_id["fulfillment-fallthrough-family"]["training_priorities"])

    def test_write_report_bundle_writes_json_markdown_and_latest(self):
        families = select_live_scenario_families(["repeated-weak-pressure-family"])
        report = build_unattended_report(simulate_live_families(families), label="away-run")

        with tempfile.TemporaryDirectory() as tmp:
            paths = write_report_bundle(report, output_root=Path(tmp), stamp="20260306_120000")

            report_json = Path(paths["report_json"])
            latest_json = Path(paths["latest_json"])
            summary_markdown = Path(paths["summary_markdown"])
            latest_markdown = Path(paths["latest_markdown"])

            self.assertTrue(report_json.exists())
            self.assertTrue(latest_json.exists())
            self.assertTrue(summary_markdown.exists())
            self.assertTrue(latest_markdown.exists())
            payload = json.loads(report_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["label"], "away-run")
            self.assertIn("repeated-weak-pressure-family", summary_markdown.read_text(encoding="utf-8"))

    def test_generated_session_definitions_cover_prioritized_family_scenarios(self):
        families = select_live_scenario_families(["fulfillment-fallthrough-family"])
        report = build_unattended_report(simulate_live_families(families), label="overnight")

        generated = build_generated_session_definitions(report)

        self.assertTrue(generated)
        payload = dict(generated[0]["payload"])
        self.assertEqual(payload.get("source"), "subconscious_generated")
        self.assertEqual(payload.get("family_id"), "fulfillment-fallthrough-family")
        self.assertTrue(payload.get("messages"))
        self.assertTrue(payload.get("training_priorities"))

    def test_write_generated_session_definitions_writes_manifest_and_payloads(self):
        families = select_live_scenario_families(["fulfillment-fallthrough-family"])
        report = build_unattended_report(simulate_live_families(families), label="overnight")

        with tempfile.TemporaryDirectory() as tmp:
            paths = write_generated_session_definitions(report, output_root=Path(tmp))

            manifest_path = Path(paths["manifest"])
            latest_manifest_path = Path(paths["latest_manifest"])
            self.assertTrue(manifest_path.exists())
            self.assertTrue(latest_manifest_path.exists())
            self.assertGreater(paths["definition_count"], 0)
            session_path = Path(paths["files"][0])
            payload = json.loads(session_path.read_text(encoding="utf-8"))
            self.assertEqual(payload.get("source"), "subconscious_generated")
            self.assertTrue(payload.get("messages"))

    def test_main_runs_and_writes_requested_family_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            generated_dir = Path(tmp) / "generated_defs"
            with unittest.mock.patch(
                "subconscious_runner.evaluate_generated_definitions",
                return_value={
                    "evaluated_count": 1,
                    "observed_count": 1,
                    "pending_review_count": 0,
                    "promoted_count": 0,
                    "quarantined_count": 0,
                },
            ) as evaluate_mock:
                exit_code = main([
                    "--output-dir",
                    tmp,
                    "--generated-output-dir",
                    str(generated_dir),
                    "--label",
                    "overnight",
                    "--family",
                    "fulfillment-fallthrough-family",
                ])

            self.assertEqual(exit_code, 0)
            latest_json = Path(tmp) / "latest.json"
            latest_md = Path(tmp) / "latest.md"
            self.assertTrue(latest_json.exists())
            self.assertTrue(latest_md.exists())
            self.assertTrue((generated_dir / "latest_manifest.json").exists())
            payload = json.loads(latest_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["totals"]["family_count"], 1)
            self.assertEqual(payload["families"][0]["family_id"], "fulfillment-fallthrough-family")
            evaluate_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()