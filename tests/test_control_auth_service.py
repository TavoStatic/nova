import unittest
from types import SimpleNamespace

from services.control_auth import CONTROL_AUTH_SERVICE


class TestControlAuthService(unittest.TestCase):
    def test_control_login_enabled_reads_env_pair(self):
        self.assertTrue(CONTROL_AUTH_SERVICE.control_login_enabled(environ={"NOVA_CONTROL_USER": "admin", "NOVA_CONTROL_PASS": "secret"}))
        self.assertFalse(CONTROL_AUTH_SERVICE.control_login_enabled(environ={"NOVA_CONTROL_USER": "admin", "NOVA_CONTROL_PASS": ""}))

    def test_new_control_session_and_login_auth_use_cookie_store(self):
        sessions = {}
        sid = CONTROL_AUTH_SERVICE.new_control_session(
            control_sessions=sessions,
            ttl_seconds=60,
            token_hex_fn=lambda size: "controlsid",
            now_fn=lambda: 100.0,
        )

        handler = SimpleNamespace(headers={"Cookie": f"nova_control_session={sid}"})
        ok, reason = CONTROL_AUTH_SERVICE.control_login_auth(
            handler,
            control_login_enabled_fn=lambda: True,
            prune_control_sessions_fn=lambda: None,
            parse_cookie_map_fn=lambda current: {"nova_control_session": "controlsid"},
            control_sessions=sessions,
            now_fn=lambda: 120.0,
        )

        self.assertEqual(sid, "controlsid")
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_control_page_gate_blocks_remote_without_token(self):
        ok, reason = CONTROL_AUTH_SERVICE.control_page_gate(
            object(),
            dev_mode_enabled_fn=lambda: False,
            control_login_auth_fn=lambda handler: (True, ""),
            is_local_client_fn=lambda handler: False,
            environ={},
        )

        self.assertFalse(ok)
        self.assertEqual(reason, "control_local_only_set_NOVA_CONTROL_TOKEN")

    def test_control_login_action_returns_cookie_header_on_success(self):
        code, payload, headers = CONTROL_AUTH_SERVICE.control_login_action(
            {"username": "admin", "password": "secret"},
            control_login_enabled_fn=lambda: True,
            new_control_session_fn=lambda: "session123",
            environ={"NOVA_CONTROL_USER": "admin", "NOVA_CONTROL_PASS": "secret"},
        )

        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("login_ok", payload["message"])
        self.assertIn("nova_control_session=session123", headers.get("Set-Cookie", ""))

    def test_control_login_action_rejects_bad_credentials(self):
        code, payload, headers = CONTROL_AUTH_SERVICE.control_login_action(
            {"username": "admin", "password": "wrong"},
            control_login_enabled_fn=lambda: True,
            new_control_session_fn=lambda: "session123",
            environ={"NOVA_CONTROL_USER": "admin", "NOVA_CONTROL_PASS": "secret"},
        )

        self.assertEqual(code, 403)
        self.assertEqual(payload, {"ok": False, "error": "invalid_credentials"})
        self.assertEqual(headers, {})

    def test_control_logout_action_clears_session_and_returns_cookie_header(self):
        cleared = []
        code, payload, headers = CONTROL_AUTH_SERVICE.control_logout_action(
            object(),
            clear_control_session_fn=lambda handler: cleared.append(handler),
        )

        self.assertEqual(code, 200)
        self.assertEqual(payload, {"ok": True, "message": "logout_ok"})
        self.assertEqual(len(cleared), 1)
        self.assertIn("Max-Age=0", headers.get("Set-Cookie", ""))


if __name__ == "__main__":
    unittest.main()