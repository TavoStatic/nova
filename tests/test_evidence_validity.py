import unittest

from services.evidence_validity import invalid_tool_result


class TestEvidenceValidity(unittest.TestCase):
    def test_specific_ollama_chat_failures_are_not_valid_evidence(self):
        invalid, reason = invalid_tool_result(
            "chat",
            "(error: Ollama chat failed: connection refused)",
        )

        self.assertTrue(invalid)
        self.assertIn("Ollama chat failed", reason)

    def test_fail_marker_is_not_valid_evidence(self):
        invalid, reason = invalid_tool_result(
            "web_search",
            "[FAIL] Local web search backend is unavailable.",
        )

        self.assertTrue(invalid)
        self.assertIn("[FAIL]", reason)

    def test_no_allowlisted_web_results_is_valid_non_failure_evidence(self):
        invalid, reason = invalid_tool_result(
            "web_search",
            "No allowlisted web results found for that query.\n\nWeb access for nova runtime search dependency probe is limited to these allowlisted sources:",
        )

        self.assertFalse(invalid)
        self.assertEqual(reason, "")

    def test_structured_judgment_false_ok_is_valid_evidence(self):
        invalid, reason = invalid_tool_result(
            "source_root_judgment",
            {
                "ok": False,
                "schema": "nova.source_root_judgment.v1",
                "verdict": "evidence_failed",
                "reason": "evidence_failed",
            },
        )

        self.assertFalse(invalid)
        self.assertEqual(reason, "")

    def test_read_source_with_ok_false_literal_is_valid_evidence(self):
        invalid, reason = invalid_tool_result(
            "read",
            'from __future__ import annotations\n\n    return {\n        "ok": False,\n        "status": "blocked_by_test_guard",\n    }\n',
        )

        self.assertFalse(invalid)
        self.assertEqual(reason, "")

    def test_structured_json_tool_failure_is_not_valid_evidence(self):
        invalid, reason = invalid_tool_result(
            "read",
            '{"ok": false, "reason": "Not a file: routing/context_router.py", "tool_result": "Not a file"}',
        )

        self.assertTrue(invalid)
        self.assertIn("Not a file", reason)


if __name__ == "__main__":
    unittest.main()
