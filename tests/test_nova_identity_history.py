import unittest

from services import nova_identity_history


class TestNovaIdentityHistory(unittest.TestCase):
    def test_execute_identity_history_outcome_supports_runtime_scope_hook_resolution(self):
        reply, next_state, outcome = nova_identity_history.execute_identity_history_outcome(
            {"identity_history_kind": "name_origin", "subject": "self"},
            {"kind": "identity_profile", "subject": "self"},
            "why that name?",
            normalize_turn_text_fn=lambda text: text.lower().strip(),
            speaker_matches_developer_fn=lambda: False,
            make_conversation_state_fn=lambda kind, **data: {"kind": kind, **data},
            hard_answer_fn=lambda _text: "",
            developer_profile_reply_fn=lambda **_kwargs: "profile reply",
            developer_identity_followup_reply_fn=lambda **_kwargs: "developer identity reply",
            identity_name_followup_reply_fn=lambda subject: f"name followup for {subject}",
            identity_profile_followup_reply_fn=lambda subject, **_kwargs: f"profile followup for {subject}",
            identity_profile_source_boundary_reply_fn=lambda subject: f"source boundary for {subject}",
            classify_name_origin_outcome_fn=lambda payload: {"reply_text": "origin story", "kind": "story_known"},
            render_reply_fn=lambda payload: str(payload.get("reply_text") or ""),
        )

        self.assertEqual(reply, "name followup for self")
        self.assertEqual(next_state, {"kind": "identity_profile", "subject": "self"})
        self.assertEqual(outcome.get("reply_contract"), "identity_history.name_origin")

    def test_execute_identity_history_outcome_handles_profile_source_boundary(self):
        reply, next_state, outcome = nova_identity_history.execute_identity_history_outcome(
            {"identity_history_kind": "source_boundary", "subject": "developer"},
            {"kind": "identity_profile", "subject": "developer"},
            "which parts could be stale or memory-only?",
            normalize_turn_text_fn=lambda text: text.lower().strip(),
            speaker_matches_developer_fn=lambda: False,
            make_conversation_state_fn=lambda kind, **data: {"kind": kind, **data},
            hard_answer_fn=lambda _text: "",
            developer_profile_reply_fn=lambda **_kwargs: "profile reply",
            developer_identity_followup_reply_fn=lambda **_kwargs: "developer identity reply",
            identity_name_followup_reply_fn=lambda subject: f"name followup for {subject}",
            identity_profile_followup_reply_fn=lambda subject, **_kwargs: f"profile followup for {subject}",
            identity_profile_source_boundary_reply_fn=lambda subject: f"source boundary for {subject}",
            classify_name_origin_outcome_fn=lambda payload: {"reply_text": "origin story", "kind": "story_known"},
            render_reply_fn=lambda payload: str(payload.get("reply_text") or ""),
        )

        self.assertEqual(reply, "source boundary for developer")
        self.assertEqual(next_state, {"kind": "identity_profile", "subject": "developer"})
        self.assertEqual(outcome.get("reply_contract"), "identity_history.source_boundary")


if __name__ == "__main__":
    unittest.main()
