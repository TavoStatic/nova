from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from services.nova_shell.store import ShellStore
from services.nova_shell.auth import ShellAuth, hash_password, verify_password
from services.nova_shell.admin import ShellAdmin


def _make_stack():
    tmp = tempfile.mkdtemp()
    store = ShellStore(db_path=Path(tmp) / "auth_test.db")
    auth = ShellAuth(store)
    admin = ShellAdmin(store, auth)
    admin.create_first_admin("admin", "SuperSecure1234!", "Admin User")
    return store, auth, admin


class TestPasswordHashing(unittest.TestCase):
    def test_hash_and_verify(self):
        h = hash_password("my_password")
        self.assertTrue(verify_password("my_password", h))
        self.assertFalse(verify_password("wrong", h))

    def test_hash_is_not_plaintext(self):
        h = hash_password("secret")
        self.assertNotEqual(h, "secret")


class TestLoginBasic(unittest.TestCase):
    def setUp(self):
        self.store, self.auth, self.admin = _make_stack()

    def test_valid_login(self):
        result = self.auth.login("admin", "SuperSecure1234!")
        self.assertTrue(result.ok)
        self.assertNotEqual(result.token, "")
        self.assertEqual(result.role, "account_admin")

    def test_wrong_password(self):
        result = self.auth.login("admin", "wrongpassword")
        self.assertFalse(result.ok)
        self.assertEqual(result.token, "")

    def test_unknown_user(self):
        result = self.auth.login("nobody", "whatever")
        self.assertFalse(result.ok)

    def test_inactive_user(self):
        self.store.update_user(
            self.store.get_user_by_username("admin")["id"], {"active": 0}
        )
        result = self.auth.login("admin", "SuperSecure1234!")
        self.assertFalse(result.ok)


class TestSession(unittest.TestCase):
    def setUp(self):
        self.store, self.auth, self.admin = _make_stack()
        self.token = self.auth.login("admin", "SuperSecure1234!").token

    def test_verify_valid_session(self):
        info = self.auth.verify_session(self.token)
        self.assertIsNotNone(info)
        self.assertEqual(info.username, "admin")
        self.assertEqual(info.role, "account_admin")

    def test_verify_bogus_token(self):
        self.assertIsNone(self.auth.verify_session("not_a_real_token"))

    def test_verify_after_logout(self):
        self.auth.logout(self.token)
        self.assertIsNone(self.auth.verify_session(self.token))

    def test_logout_all(self):
        t2 = self.auth.login("admin", "SuperSecure1234!").token
        user_id = self.store.get_user_by_username("admin")["id"]
        self.auth.logout_all(user_id)
        self.assertIsNone(self.auth.verify_session(self.token))
        self.assertIsNone(self.auth.verify_session(t2))


class TestBruteForce(unittest.TestCase):
    def setUp(self):
        self.store, self.auth, self.admin = _make_stack()

    def test_lockout_after_max_attempts(self):
        from services.nova_shell._constants import LOGIN_MAX_ATTEMPTS
        for _ in range(LOGIN_MAX_ATTEMPTS):
            self.auth.login("admin", "badpassword")
        result = self.auth.login("admin", "SuperSecure1234!")
        self.assertFalse(result.ok)
        self.assertIn("locked", result.error.lower())


class TestPermissions(unittest.TestCase):
    def setUp(self):
        self.store, self.auth, self.admin = _make_stack()
        self.token = self.auth.login("admin", "SuperSecure1234!").token

    def test_account_admin_has_users_create(self):
        self.assertTrue(self.auth.check_permission(self.token, "users.create"))

    def test_account_admin_has_audit_read(self):
        self.assertTrue(self.auth.check_permission(self.token, "audit.read"))

    def test_account_admin_no_develop(self):
        self.assertFalse(self.auth.check_permission(self.token, "backpacks.develop"))

    def test_no_permission_on_invalid_token(self):
        self.assertFalse(self.auth.check_permission("bad_token", "system.status"))

    def test_require_permission_raises_on_missing(self):
        self.admin.create_user(self.token, "su1", "StdPass12345!", "standard_user")
        su_token = self.auth.login("su1", "StdPass12345!").token
        with self.assertRaises(PermissionError):
            self.auth.require_permission(su_token, "users.create")

    def test_custom_role_permission_resolves(self):
        import json, uuid, time
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.store.create_custom_role({
            "id": str(uuid.uuid4()),
            "name": "data_clerk",
            "label": "Data Clerk",
            "level": 3,
            "permissions_json": json.dumps(["data.read", "reports.read"]),
            "created_by": "test",
            "created_at": now,
            "updated_at": now,
        })
        self.admin.create_user(self.token, "clerk1", "ClerkPass1234!", "data_clerk")
        clerk_token = self.auth.login("clerk1", "ClerkPass1234!").token
        self.assertTrue(self.auth.check_permission(clerk_token, "data.read"))
        self.assertFalse(self.auth.check_permission(clerk_token, "users.create"))


if __name__ == "__main__":
    unittest.main()
