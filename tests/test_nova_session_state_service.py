import unittest

from conversation_manager import ConversationSession
from services import nova_session_state


class TestNovaSessionStateService(unittest.TestCase):
    def test_apply_reply_session_updates_sets_pending_action_from_meta(self):
        session = ConversationSession()

        next_state = nova_session_state.apply_reply_session_updates(
            session,
            meta={
                "planner_decision": "grounded_lookup",
                "tool": "web_research",
                "tool_args": {"query": "student_data"},
                "tool_result": "Grounded",
                "pending_action": {"tool": "followup"},
            },
        )

        self.assertIsNone(next_state)
        self.assertEqual(session.pending_action, {"tool": "followup"})
        self.assertIsNone(session.retrieval_state())
        self.assertEqual(session.conversation_state["kind"], "last_tool_evidence")
        self.assertEqual(session.conversation_state["tool"], "web_research")
        self.assertEqual(session.conversation_state["tool_result"], "Grounded")

    def test_apply_reply_session_updates_clears_pending_when_meta_has_none(self):
        session = ConversationSession(conversation_state={"kind": "identity_profile", "subject": "developer"})
        session.set_pending_action({"tool": "followup"})

        next_state = nova_session_state.apply_reply_session_updates(
            session,
            meta={
                "planner_decision": "deterministic",
                "tool": "",
                "tool_args": {},
                "tool_result": "",
            },
        )

        self.assertIsNone(next_state)
        self.assertIsNone(session.pending_action)
        self.assertIsNone(session.conversation_state)


if __name__ == "__main__":
    unittest.main()

