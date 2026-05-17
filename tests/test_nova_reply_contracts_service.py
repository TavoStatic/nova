import unittest

from services import nova_reply_contracts


class TestNovaReplyContractsService(unittest.TestCase):
    def test_truthful_limit_reply_uses_request_guidance_for_question(self):
        reply = nova_reply_contracts.truthful_limit_reply(
            "what is his favorite food?",
            normalize_turn_text_fn=lambda text: text,
            looks_like_mixed_info_request_turn_fn=lambda text: False,
            is_explicit_request_fn=lambda text: True,
        )
        self.assertIn("don't know", reply.lower())
        self.assertIn("missing context", reply.lower())

    def test_attach_learning_invitation_preserves_existing_suffix(self):
        reply = nova_reply_contracts.attach_learning_invitation(
            "I don't know that based on what I can verify right now, and I don't want to make it up. Give me the missing context or a grounded result, and I can use it in this conversation.",
            truthful_limit=True,
            normalize_turn_text_fn=lambda text: text.lower(),
        )
        self.assertEqual(reply.count("missing context"), 1)

    def test_truthful_limit_outcome_uses_contract(self):
        outcome = nova_reply_contracts.truthful_limit_outcome(
            "what is his favorite food?",
            truthful_limit_reply_fn=lambda text, limitation="cannot_verify": "I don't know that based on what I can verify right now.",
        )
        self.assertEqual(outcome.get("reply_contract"), "turn.truthful_limit")
        self.assertEqual(outcome.get("kind"), "cannot_verify")
        self.assertIn("don't know", str(outcome.get("reply_text") or "").lower())
