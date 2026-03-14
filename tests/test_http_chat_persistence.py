import tempfile
import unittest
from pathlib import Path

import nova_http


class TestHttpChatPersistence(unittest.TestCase):
    def setUp(self):
        self.orig_store = nova_http.SESSION_STORE_PATH
        self.orig_turns = dict(nova_http.SESSION_TURNS)

    def tearDown(self):
        nova_http.SESSION_STORE_PATH = self.orig_store
        nova_http.SESSION_TURNS.clear()
        nova_http.SESSION_TURNS.update(self.orig_turns)

    def test_persist_and_load_sessions_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "http_chat_sessions.json"
            nova_http.SESSION_STORE_PATH = store
            nova_http.SESSION_TURNS.clear()

            nova_http._append_session_turn("abc123", "user", "hello")
            nova_http._append_session_turn("abc123", "assistant", "hi there")

            self.assertTrue(store.exists())

            nova_http.SESSION_TURNS.clear()
            nova_http._load_persisted_sessions()

            turns = nova_http._get_session_turns("abc123")
            self.assertEqual(
                turns,
                [("user", "hello"), ("assistant", "hi there")],
            )


if __name__ == "__main__":
    unittest.main()
