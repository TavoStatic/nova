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


if __name__ == "__main__":
    unittest.main()
