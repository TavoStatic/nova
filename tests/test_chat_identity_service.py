import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from services.chat_identity import CHAT_IDENTITY_SERVICE


class TestChatIdentityService(unittest.TestCase):
    def test_chat_users_reads_managed_file_with_normalized_names(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "chat_users.json"
            path.write_text('{"Alice Smith":{"salt":"aa","hash":"bb","iterations":1}}', encoding="utf-8")

            payload = CHAT_IDENTITY_SERVICE.chat_users(
                chat_users_path=path,
                normalize_user_id_fn=lambda value: value.replace(" ", ""),
                environ={},
            )

        self.assertIn("AliceSmith", payload)
        self.assertEqual(payload["AliceSmith"]["hash"], "bb")

    def test_new_chat_session_and_login_auth_use_session_store(self):
        sessions = {}
        sid = CHAT_IDENTITY_SERVICE.new_chat_session(
            "Alice Smith",
            chat_sessions=sessions,
            normalize_user_id_fn=lambda value: value.replace(" ", ""),
            ttl_seconds=60,
            token_hex_fn=lambda size: "abc123",
            now_fn=lambda: 100.0,
        )

        handler = SimpleNamespace(headers={"Cookie": f"nova_chat_session={sid}"})
        ok, user = CHAT_IDENTITY_SERVICE.chat_login_auth(
            handler,
            chat_login_enabled_fn=lambda: True,
            prune_chat_sessions_fn=lambda: None,
            parse_cookie_map_fn=lambda current: {"nova_chat_session": "abc123"},
            chat_sessions=sessions,
            now_fn=lambda: 120.0,
        )

        self.assertEqual(sid, "abc123")
        self.assertTrue(ok)
        self.assertEqual(user, "AliceSmith")

    def test_save_managed_chat_users_hashes_plaintext_passwords(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "chat_users.json"
            CHAT_IDENTITY_SERVICE.save_managed_chat_users(
                {"Alice Smith": "secret"},
                normalize_user_id_fn=lambda value: value.replace(" ", ""),
                chat_users_path=path,
                iterations=10,
            )

            saved = path.read_text(encoding="utf-8")

        self.assertIn("AliceSmith", saved)
        self.assertNotIn("secret", saved)

    def test_chat_login_action_returns_cookie_and_user_id(self):
        code, payload, headers = CHAT_IDENTITY_SERVICE.chat_login_action(
            {"username": "Alice Smith", "password": "secret"},
            chat_login_enabled_fn=lambda: True,
            chat_users_fn=lambda: {"AliceSmith": {"hash": "x"}},
            normalize_user_id_fn=lambda value: value.replace(" ", ""),
            chat_password_matches_fn=lambda expected, pwd: expected == {"hash": "x"} and pwd == "secret",
            new_chat_session_fn=lambda user_id: f"session-for-{user_id}",
        )

        self.assertEqual(code, 200)
        self.assertEqual(payload, {"ok": True, "message": "login_ok", "user_id": "AliceSmith"})
        self.assertIn("nova_chat_session=session-for-AliceSmith", headers.get("Set-Cookie", ""))

    def test_chat_login_action_rejects_invalid_credentials(self):
        code, payload, headers = CHAT_IDENTITY_SERVICE.chat_login_action(
            {"username": "Alice", "password": "wrong"},
            chat_login_enabled_fn=lambda: True,
            chat_users_fn=lambda: {"Alice": "secret"},
            normalize_user_id_fn=lambda value: value,
            chat_password_matches_fn=lambda expected, pwd: False,
            new_chat_session_fn=lambda user_id: "unused",
        )

        self.assertEqual(code, 403)
        self.assertEqual(payload, {"ok": False, "error": "invalid_credentials"})
        self.assertEqual(headers, {})

    def test_chat_logout_action_clears_session_and_returns_cookie_header(self):
        cleared = []
        code, payload, headers = CHAT_IDENTITY_SERVICE.chat_logout_action(
            object(),
            clear_chat_session_fn=lambda handler: cleared.append(handler),
        )

        self.assertEqual(code, 200)
        self.assertEqual(payload, {"ok": True, "message": "logout_ok"})
        self.assertEqual(len(cleared), 1)
        self.assertIn("Max-Age=0", headers.get("Set-Cookie", ""))


if __name__ == "__main__":
    unittest.main()