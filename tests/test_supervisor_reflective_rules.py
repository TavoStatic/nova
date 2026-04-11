import unittest

from conversation_manager import ConversationSession
from services import supervisor_reflective_rules


class TestSupervisorReflectiveRules(unittest.TestCase):
    def test_reflective_retry_rewrites_to_prior_question(self):
        result = supervisor_reflective_rules.reflective_retry_rule(
            "keep trying your almost there ..",
            "keep trying your almost there ..",
            None,
            3,
            turns=[
                ("user", "what are Gus's favorite colors?"),
                ("assistant", "I don't have Gus's color preferences yet."),
                ("user", "keep trying your almost there .."),
            ],
            phase="rewrite",
        )

        self.assertEqual(result.get("rewrite_text"), "what are Gus's favorite colors?")
        self.assertEqual(result.get("analysis_reason"), "reflective_retry_prior_question")

    def test_apply_correction_returns_handle_action(self):
        result = supervisor_reflective_rules.apply_correction_rule(
            "no, that's wrong",
            "no, that's wrong",
            None,
            1,
            phase="handle",
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("action"), "apply_correction")

    def test_reflective_retry_handles_developer_location_followup(self):
        session = ConversationSession()
        session.set_conversation_state({"kind": "identity_profile", "subject": "developer"})

        result = supervisor_reflective_rules.reflective_retry_rule(
            "if you think for a bit.. you now know gus' locaiton do you not?",
            "if you think for a bit.. you now know gus' locaiton do you not?",
            session,
            1,
            turns=[("user", "who is your creator?")],
            phase="handle",
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("action"), "developer_location")