import unittest

from services import nova_reply_contracts


class TestNovaReplyContracts(unittest.TestCase):
    def test_truthful_limit_reply_does_not_split_mixed_request(self):
        reply = nova_reply_contracts.truthful_limit_reply(
            "weather and also who created you",
            normalize_turn_text_fn=lambda text: text.lower().strip(),
            looks_like_mixed_info_request_turn_fn=lambda text: " and " in text,
            is_explicit_request_fn=lambda _text: False,
        )

        self.assertNotIn("split", reply.lower())
        self.assertIn("missing context", reply.lower())

    def test_truthful_limit_reply_uses_grounded_source_guidance_for_request(self):
        reply = nova_reply_contracts.truthful_limit_reply(
            "can you verify this?",
            normalize_turn_text_fn=lambda text: text.lower().strip(),
            looks_like_mixed_info_request_turn_fn=lambda _text: False,
            is_explicit_request_fn=lambda _text: True,
        )

        self.assertIn("grounded source", reply.lower())
        self.assertIn("missing context", reply.lower())


if __name__ == "__main__":
    unittest.main()
