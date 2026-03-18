import unittest

from conversation_manager import ConversationManager, ConversationSession


class TestConversationSession(unittest.TestCase):
    def test_active_subject_uses_state_shape(self):
        session = ConversationSession()
        session.set_conversation_state({"kind": "identity_profile", "subject": "developer"})
        self.assertEqual(session.active_subject(), "identity_profile:developer")

    def test_retrieval_state_round_trip(self):
        session = ConversationSession()
        state = {
            "kind": "retrieval",
            "subject": "web_research",
            "query": "peims attendance",
            "top_url": "https://tea.texas.gov/a",
        }
        session.set_retrieval_state(state)
        self.assertEqual(session.state_kind(), "retrieval")
        self.assertEqual(session.retrieval_state(), state)
        self.assertEqual(session.active_subject(), "retrieval:web_research")

    def test_apply_state_update_uses_fallback(self):
        session = ConversationSession()
        fallback = {"kind": "location_recall"}
        session.apply_state_update(None, fallback)
        self.assertEqual(session.conversation_state, fallback)
        session.apply_state_update(None, None)
        self.assertIsNone(session.conversation_state)

    def test_ledger_fields_reflect_continuation(self):
        session = ConversationSession()
        session.set_conversation_state({"kind": "retrieval", "subject": "web_gather"})
        session.mark_continuation_used()
        self.assertEqual(
            session.ledger_fields(),
            {"active_subject": "retrieval:web_gather", "continuation_used": True},
        )


class TestConversationManager(unittest.TestCase):
    def test_get_reuses_session_per_id(self):
        manager = ConversationManager()
        first = manager.get("abc")
        second = manager.get("abc")
        self.assertIs(first, second)

    def test_drop_removes_session(self):
        manager = ConversationManager()
        manager.get("abc").set_prefer_web_for_data_queries(True)
        manager.drop("abc")
        new_session = manager.get("abc")
        self.assertFalse(new_session.prefer_web_for_data_queries)
