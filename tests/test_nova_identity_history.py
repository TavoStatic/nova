import unittest

from services import nova_identity_history


class TestNovaIdentityHistory(unittest.TestCase):
    def test_execute_identity_history_outcome_supports_runtime_scope_hook_resolution(self):
        reply, next_state, outcome = nova_identity_history.execute_identity_history_outcome(
            {"identity_history_kind": "name_origin", "subject": "self"},
            {"kind": "identity_profile", "subject": "self"},
            "why that name?",
            runtime_scope={
                "_normalize_turn_text": lambda text: text.lower().strip(),
                "_speaker_matches_developer": lambda: False,
                "_make_conversation_state": lambda kind, **data: {"kind": kind, **data},
                "hard_answer": lambda _text: "",
                "_developer_profile_reply": lambda **_kwargs: "profile reply",
                "_developer_identity_followup_reply": lambda **_kwargs: "developer identity reply",
                "_identity_name_followup_reply": lambda subject: f"name followup for {subject}",
                "_identity_profile_followup_reply": lambda subject, **_kwargs: f"profile followup for {subject}",
                "_classify_name_origin_outcome": lambda payload: {"reply_text": "origin story", "kind": "story_known"},
                "render_reply": lambda payload: str(payload.get("reply_text") or ""),
            },
        )

        self.assertEqual(reply, "name followup for self")
        self.assertEqual(next_state, {"kind": "identity_profile", "subject": "self"})
        self.assertEqual(outcome.get("reply_contract"), "identity_history.name_origin")


if __name__ == "__main__":
    unittest.main()
