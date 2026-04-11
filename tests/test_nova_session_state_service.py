import unittest

from conversation_manager import ConversationSession
from services import nova_session_state


class TestNovaSessionStateService(unittest.TestCase):
    def test_apply_reply_session_updates_sets_pending_and_retrieval_state(self):
        session = ConversationSession()

        next_state = nova_session_state.apply_reply_session_updates(
            session,
            meta={
                "planner_decision": "grounded_lookup",
                "tool": "web_research",
                "tool_args": {"query": "peims"},
                "tool_result": "Grounded",
                "pending_action": {"tool": "followup"},
            },
            routed_text="research peims",
            turns=[],
            fallback_state=None,
            infer_post_reply_conversation_state=lambda *args, **kwargs: {"kind": "retrieval", "subject": "peims"},
        )

        self.assertEqual(next_state, {"kind": "retrieval", "subject": "peims"})
        self.assertEqual(session.pending_action, {"tool": "followup"})
        self.assertEqual(session.retrieval_state(), {"kind": "retrieval", "subject": "peims"})

    def test_apply_reply_session_updates_falls_back_to_regular_state_update(self):
        session = ConversationSession(conversation_state={"kind": "identity_profile", "subject": "developer"})

        next_state = nova_session_state.apply_reply_session_updates(
            session,
            meta={
                "planner_decision": "deterministic",
                "tool": "",
                "tool_args": {},
                "tool_result": "",
            },
            routed_text="who is your developer",
            turns=[],
            fallback_state={"kind": "identity_profile", "subject": "developer"},
            infer_post_reply_conversation_state=lambda *args, **kwargs: None,
        )

        self.assertIsNone(next_state)
        self.assertEqual(session.conversation_state, {"kind": "identity_profile", "subject": "developer"})


if __name__ == "__main__":
    unittest.main()