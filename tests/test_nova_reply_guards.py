import unittest

from services import nova_reply_guards


class TestNovaReplyGuards(unittest.TestCase):
    def test_self_correct_reply_does_not_rewrite_content_claims(self):
        corrected, changed, reason = nova_reply_guards.self_correct_reply(
            "what are your abilities?",
            "I can autonomously enhance myself and self-sustain.",
            is_capability_query_fn=lambda text: "abilities" in text,
            describe_capabilities_fn=lambda: "Deterministic capability summary.",
        )

        self.assertFalse(changed)
        self.assertEqual(reason, "")
        self.assertEqual(corrected, "I can autonomously enhance myself and self-sustain.")

    def test_apply_claim_gate_removes_unsupported_risky_claims(self):
        gated, changed, reason = nova_reply_guards.apply_claim_gate(
            "Your creator is Gustavo Uribe. I can smell coffee in the room with Gus.",
            evidence_text="Developer full name: Gustavo Uribe",
            sentence_supported_by_evidence_fn=lambda sentence, evidence, tool: nova_reply_guards.sentence_supported_by_evidence(
                sentence,
                evidence,
                tool,
                is_risky_claim_sentence_fn=nova_reply_guards.is_risky_claim_sentence,
                content_tokens_fn=nova_reply_guards.content_tokens,
            ),
            truthful_limit_reply_fn=lambda *_args, **_kwargs: "Limit reply.",
        )

        self.assertTrue(changed)
        self.assertEqual(reason, "unsupported_claim_removed")
        self.assertIn("gustavo uribe", gated.lower())
        self.assertNotIn("smell coffee", gated.lower())


if __name__ == "__main__":
    unittest.main()
