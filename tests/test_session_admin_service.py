import threading
import unittest

from services.session_admin import SESSION_ADMIN_SERVICE


class TestSessionAdminService(unittest.TestCase):
    def test_session_delete_action_returns_updated_sessions(self):
        ok, msg, extra, detail = SESSION_ADMIN_SERVICE.session_delete_action(
            {"session_id": "sA"},
            delete_session_fn=lambda session_id: (session_id == "sA", "session_deleted"),
            session_summaries_fn=lambda limit: [{"session_id": "sB"}],
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "session_deleted")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("sessions") or [])[0].get("session_id"), "sB")

    def test_chat_user_upsert_hashes_via_save_callback(self):
        saved = {}

        ok, msg = SESSION_ADMIN_SERVICE.chat_user_upsert(
            "Alice Smith",
            "secret",
            normalize_user_id_fn=lambda value: value.replace(" ", ""),
            chat_users_fn=lambda: {},
            save_managed_chat_users_fn=lambda users: saved.update(users),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "chat_user_saved:AliceSmith")
        self.assertEqual(saved.get("AliceSmith"), "secret")

    def test_delete_session_delegates_under_lock(self):
        calls = []
        lock = threading.Lock()

        ok, msg = SESSION_ADMIN_SERVICE.delete_session(
            "sA",
            session_lock=lock,
            delete_session_fn=lambda session_id, **kwargs: calls.append((session_id, sorted(kwargs.keys()))) or (True, "session_deleted"),
            session_turns={},
            session_owners={},
            state_manager=object(),
            persist_callback=lambda: None,
            on_session_end=lambda sid, session: None,
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "session_deleted")
        self.assertEqual(calls[0][0], "sA")
        self.assertIn("persist_callback", calls[0][1])


if __name__ == "__main__":
    unittest.main()