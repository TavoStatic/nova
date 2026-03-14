import tempfile
import unittest
from pathlib import Path

import nova_http


class TestHttpSessionManager(unittest.TestCase):
    def setUp(self):
        self.orig_store = nova_http.SESSION_STORE_PATH
        self.orig_turns = dict(nova_http.SESSION_TURNS)

    def tearDown(self):
        nova_http.SESSION_STORE_PATH = self.orig_store
        nova_http.SESSION_TURNS.clear()
        nova_http.SESSION_TURNS.update(self.orig_turns)

    def test_session_summaries_and_delete(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "http_chat_sessions.json"
            nova_http.SESSION_STORE_PATH = store
            nova_http.SESSION_TURNS.clear()

            nova_http._append_session_turn("sA", "user", "hello")
            nova_http._append_session_turn("sA", "assistant", "hi")
            nova_http._append_session_turn("sB", "user", "what is status")

            summary = nova_http._session_summaries(10)
            ids = [x.get("session_id") for x in summary]
            self.assertIn("sA", ids)
            self.assertIn("sB", ids)

            ok, msg = nova_http._delete_session("sA")
            self.assertTrue(ok)
            self.assertIn(msg, {"session_deleted", "session_not_found"})
            self.assertEqual(nova_http._get_session_turns("sA"), [])


if __name__ == "__main__":
    unittest.main()
