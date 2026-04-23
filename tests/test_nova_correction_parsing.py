import unittest

from services import nova_correction_parsing


def _normalize_turn_text(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


class TestNovaCorrectionParsing(unittest.TestCase):
    def test_parse_correction_extracts_quoted_replacement(self):
        parsed = nova_correction_parsing.parse_correction("no, say 'My name is Nova.' instead")
        self.assertEqual(parsed, "My name is Nova.")

    def test_pending_replacement_text_rejects_questions(self):
        self.assertFalse(
            nova_correction_parsing.looks_like_pending_replacement_text(
                "what do you think it is nova ?",
                normalize_turn_text=_normalize_turn_text,
            )
        )

    def test_authoritative_correction_text_prefers_short_declarative_identity(self):
        out = nova_correction_parsing.extract_authoritative_correction_text("my name is Gus and that is final")
        self.assertEqual(out, "my name is Gus and that is final")

    def test_safe_eval_arithmetic_expression_handles_basic_math(self):
        self.assertEqual(nova_correction_parsing.safe_eval_arithmetic_expression("2 + 3 * 4"), 14.0)


if __name__ == "__main__":
    unittest.main()