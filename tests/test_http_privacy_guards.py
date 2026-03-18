import json
import os
import tempfile
import unittest

import nova_http


class _DummyHandler:
    def __init__(self, cookie: str = ""):
        self.headers = {}
        if cookie:
            self.headers["Cookie"] = cookie


class TestHttpPrivacyGuards(unittest.TestCase):
    def setUp(self):
        self.orig_chat_sessions = dict(nova_http.CHAT_SESSIONS)
        self.orig_session_owners = dict(nova_http.SESSION_OWNERS)
        self.orig_env_json = os.environ.get("NOVA_CHAT_USERS_JSON")
        self.orig_env_user = os.environ.get("NOVA_CHAT_USER")
        self.orig_env_pass = os.environ.get("NOVA_CHAT_PASS")
        self.orig_runtime = nova_http.RUNTIME_DIR
        nova_http.CHAT_SESSIONS.clear()
        nova_http.SESSION_OWNERS.clear()

    def tearDown(self):
        nova_http.CHAT_SESSIONS.clear()
        nova_http.CHAT_SESSIONS.update(self.orig_chat_sessions)
        nova_http.SESSION_OWNERS.clear()
        nova_http.SESSION_OWNERS.update(self.orig_session_owners)
        if self.orig_env_json is None:
            os.environ.pop("NOVA_CHAT_USERS_JSON", None)
        else:
            os.environ["NOVA_CHAT_USERS_JSON"] = self.orig_env_json
        if self.orig_env_user is None:
            os.environ.pop("NOVA_CHAT_USER", None)
        else:
            os.environ["NOVA_CHAT_USER"] = self.orig_env_user
        if self.orig_env_pass is None:
            os.environ.pop("NOVA_CHAT_PASS", None)
        else:
            os.environ["NOVA_CHAT_PASS"] = self.orig_env_pass
        nova_http.RUNTIME_DIR = self.orig_runtime

    def test_session_owner_binds_first_user_and_blocks_others(self):
        ok_first, reason_first = nova_http._assert_session_owner("s-1", "userA", allow_bind=True)
        ok_second, reason_second = nova_http._assert_session_owner("s-1", "userC", allow_bind=False)

        self.assertTrue(ok_first)
        self.assertIn(reason_first, {"owner_bound", "ok"})
        self.assertFalse(ok_second)
        self.assertEqual(reason_second, "session_owner_mismatch")

    def test_chat_login_auth_requires_cookie_when_enabled(self):
        os.environ["NOVA_CHAT_USERS_JSON"] = json.dumps({"alice": "secret"})

        ok_none, reason_none = nova_http._chat_login_auth(_DummyHandler())
        self.assertFalse(ok_none)
        self.assertEqual(reason_none, "chat_login_required")

        sid = nova_http._new_chat_session("alice")
        ok_auth, user_auth = nova_http._chat_login_auth(_DummyHandler(f"nova_chat_session={sid}"))
        self.assertTrue(ok_auth)
        self.assertEqual(user_auth, "alice")

    def test_chat_users_supports_json_and_normalizes_usernames(self):
        os.environ["NOVA_CHAT_USERS_JSON"] = json.dumps({"Alice Smith": "pw1", "bob": "pw2"})
        users = nova_http._chat_users()
        self.assertIn("AliceSmith", users)
        self.assertIn("bob", users)
        self.assertEqual(users["bob"], "pw2")

    def test_managed_chat_user_file_hashes_and_verifies_password(self):
        with tempfile.TemporaryDirectory() as td:
            nova_http.RUNTIME_DIR = nova_http.Path(td)

            ok, msg = nova_http._chat_user_upsert("Alice Smith", "secret")

            self.assertTrue(ok)
            self.assertIn("chat_user_saved", msg)
            users = nova_http._chat_users()
            self.assertIn("AliceSmith", users)
            record = users["AliceSmith"]
            self.assertTrue(isinstance(record, dict))
            self.assertNotIn("secret", json.dumps(record))
            self.assertTrue(nova_http._chat_password_matches(record, "secret"))
            self.assertFalse(nova_http._chat_password_matches(record, "wrong"))


if __name__ == "__main__":
    unittest.main()