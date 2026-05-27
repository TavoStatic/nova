from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.validation_artifact_truth import ValidationArtifactTruthService


class TestValidationArtifactTruthService(unittest.TestCase):
    def test_missing_validation_action_directory_is_unknown_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            (runtime_dir / "regression_status.json").write_text(
                json.dumps({
                    "generated_at": "2026-05-15 00:08:43",
                    "status": "OK",
                    "returncode": 0,
                    "source": "scripts/run_regression.py",
                }),
                encoding="utf-8",
            )

            payload = ValidationArtifactTruthService().payload(
                runtime_dir=runtime_dir,
                regression_status_path=runtime_dir / "regression_status.json",
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "validation_actions_missing")
        self.assertEqual(payload["truth_state"], "unknown")
        self.assertTrue(payload["missing_artifact"])
        self.assertEqual(payload["action_count"], 0)
        self.assertEqual(payload["latest_regression_status"], "OK")

    def test_detects_llm_failure_hidden_under_green_regression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            action_dir = runtime_dir / "validation" / "actions"
            action_dir.mkdir(parents=True)
            (runtime_dir / "regression_status.json").write_text(
                json.dumps({
                    "generated_at": "2026-05-15 00:08:43",
                    "status": "OK",
                    "returncode": 0,
                    "source": "scripts/run_regression.py",
                }),
                encoding="utf-8",
            )
            (action_dir / "2026-05-15_00-08-13_435_643dfb19.json").write_text(
                json.dumps({
                    "ts": "2026-05-15 00:08:13",
                    "session_id": "s5_correction_followup_http",
                    "user_input": "what is tsds?",
                    "planner_decision": "llm_fallback",
                    "route_trace": [
                        {"stage": "input", "outcome": "received"},
                        {"stage": "llm_call", "outcome": "started"},
                        {"stage": "finalize", "outcome": "llm_fallback"},
                    ],
                    "final_answer": "(error: LLM service unavailable)",
                }),
                encoding="utf-8",
            )

            payload = ValidationArtifactTruthService().payload(
                runtime_dir=runtime_dir,
                regression_status_path=runtime_dir / "regression_status.json",
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "llm_unavailable_in_green_regression")
        self.assertEqual(payload["current_window_failure_count"], 1)
        self.assertEqual(payload["current_window_llm_unavailable_count"], 1)
        self.assertTrue(payload["hidden_by_green_regression"])
        self.assertEqual(payload["latest_failure"]["failure_kind"], "llm_service_unavailable")
        self.assertIn("llm_call:started", payload["latest_failure"]["route_summary"])

    def test_older_validation_failure_does_not_taint_latest_regression_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            action_dir = runtime_dir / "validation" / "actions"
            action_dir.mkdir(parents=True)
            (runtime_dir / "regression_status.json").write_text(
                json.dumps({
                    "generated_at": "2026-05-15 04:08:43",
                    "status": "OK",
                    "returncode": 0,
                }),
                encoding="utf-8",
            )
            (action_dir / "2026-05-15_00-08-13_435_643dfb19.json").write_text(
                json.dumps({
                    "ts": "2026-05-15 00:08:13",
                    "planner_decision": "llm_fallback",
                    "route_trace": [{"stage": "llm_call", "outcome": "started"}],
                    "final_answer": "(error: LLM service unavailable)",
                }),
                encoding="utf-8",
            )

            payload = ValidationArtifactTruthService().payload(
                runtime_dir=runtime_dir,
                regression_status_path=runtime_dir / "regression_status.json",
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["failure_count"], 1)
        self.assertEqual(payload["current_window_failure_count"], 0)
        self.assertFalse(payload["hidden_by_green_regression"])
        self.assertEqual(payload["latest_failure"], {})
        self.assertEqual(payload["latest_historical_failure"]["failure_kind"], "llm_service_unavailable")

    def test_detects_specific_ollama_chat_failure_as_llm_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            action_dir = runtime_dir / "validation" / "actions"
            action_dir.mkdir(parents=True)
            (runtime_dir / "regression_status.json").write_text(
                json.dumps({
                    "generated_at": "2026-05-15 00:08:43",
                    "status": "OK",
                    "returncode": 0,
                }),
                encoding="utf-8",
            )
            (action_dir / "2026-05-15_00-08-13_435_643dfb19.json").write_text(
                json.dumps({
                    "ts": "2026-05-15 00:08:13",
                    "planner_decision": "llm_fallback",
                    "route_trace": [{"stage": "llm_call", "outcome": "started"}],
                    "final_answer": "(error: Ollama chat API unavailable: /api/chat returned 404)",
                }),
                encoding="utf-8",
            )

            payload = ValidationArtifactTruthService().payload(
                runtime_dir=runtime_dir,
                regression_status_path=runtime_dir / "regression_status.json",
            )

        self.assertEqual(payload["status"], "llm_unavailable_in_green_regression")
        self.assertEqual(payload["latest_failure"]["failure_kind"], "llm_service_unavailable")
        self.assertEqual(payload["current_window_llm_unavailable_count"], 1)


if __name__ == "__main__":
    unittest.main()
