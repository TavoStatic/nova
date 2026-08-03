from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.nova_shell.store import ShellStore
from services.nova_shell.auth import ShellAuth
from services.nova_shell.admin import ShellAdmin


def _make_stack():
    tmp = tempfile.mkdtemp()
    store = ShellStore(db_path=Path(tmp) / "admin_test.db")
    auth = ShellAuth(store)
    admin = ShellAdmin(store, auth)
    return store, auth, admin


def _bootstrapped():
    store, auth, admin = _make_stack()
    admin.create_first_admin("admin", "AdminPass1234!", "Admin User")
    token = auth.login("admin", "AdminPass1234!").token
    return store, auth, admin, token


class TestFirstAdmin(unittest.TestCase):
    def test_create_first_admin(self):
        _, auth, admin = _make_stack()
        self.assertFalse(admin.first_admin_exists())
        admin.create_first_admin("admin", "AdminPass1234!")
        self.assertTrue(admin.first_admin_exists())

    def test_first_admin_role_is_account_admin(self):
        _, _, admin = _make_stack()
        user = admin.create_first_admin("admin", "AdminPass1234!")
        self.assertEqual(user["role"], "account_admin")

    def test_cannot_create_second_first_admin(self):
        _, _, admin = _make_stack()
        admin.create_first_admin("admin", "AdminPass1234!")
        with self.assertRaises(RuntimeError):
            admin.create_first_admin("admin2", "AdminPass5678!")

    def test_password_too_short_rejected(self):
        _, _, admin = _make_stack()
        with self.assertRaises(ValueError):
            admin.create_first_admin("admin", "short")


class TestCreateUser(unittest.TestCase):
    def setUp(self):
        self.store, self.auth, self.admin, self.token = _bootstrapped()

    def test_create_standard_user(self):
        user = self.admin.create_user(self.token, "su1", "StdPass12345!", "standard_user")
        self.assertEqual(user["role"], "standard_user")
        self.assertNotIn("password_hash", user)

    def test_create_limited_user(self):
        user = self.admin.create_user(self.token, "lu1", "LimPass12345!", "limited_user")
        self.assertEqual(user["role"], "limited_user")

    def test_cannot_create_llc_master(self):
        with self.assertRaises(PermissionError):
            self.admin.create_user(self.token, "hacker", "Pass12345!", "llc_master")

    def test_cannot_create_peer_account_admin(self):
        with self.assertRaises(PermissionError):
            self.admin.create_user(self.token, "admin2", "Pass12345!", "account_admin")

    def test_duplicate_username_raises(self):
        self.admin.create_user(self.token, "dupuser", "DupPass12345!", "standard_user")
        with self.assertRaises(ValueError):
            self.admin.create_user(self.token, "dupuser", "DupPass12345!", "limited_user")

    def test_standard_user_cannot_create_user(self):
        self.admin.create_user(self.token, "su1", "StdPass12345!", "standard_user")
        su_token = self.auth.login("su1", "StdPass12345!").token
        with self.assertRaises(PermissionError):
            self.admin.create_user(su_token, "victim", "Pass12345!", "viewer")

    def test_password_policy_enforced_in_create_user(self):
        with self.assertRaises(ValueError):
            self.admin.create_user(self.token, "weak", "short", "viewer")


class TestSetRole(unittest.TestCase):
    def setUp(self):
        self.store, self.auth, self.admin, self.token = _bootstrapped()
        self.admin.create_user(self.token, "user1", "UserPass1234!", "standard_user")

    def test_demote_to_limited_user(self):
        self.admin.set_role(self.token, "user1", "limited_user")
        user = self.store.get_user_by_username("user1")
        self.assertEqual(user["role"], "limited_user")

    def test_cannot_elevate_to_account_admin(self):
        with self.assertRaises(PermissionError):
            self.admin.set_role(self.token, "user1", "account_admin")

    def test_role_change_revokes_sessions(self):
        u_token = self.auth.login("user1", "UserPass1234!").token
        self.assertIsNotNone(self.auth.verify_session(u_token))
        self.admin.set_role(self.token, "user1", "limited_user")
        self.assertIsNone(self.auth.verify_session(u_token))

    def test_account_admin_cannot_demote_peer(self):
        """Strict rule: account_admin cannot act on another account_admin."""
        # Create second admin via direct store write (bypass the assignable check)
        import time, uuid
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        from services.nova_shell.auth import hash_password
        from services.nova_shell.recovery import codes_to_json, generate_recovery_codes
        _, hashed = generate_recovery_codes()
        self.store.create_user({
            "id": str(uuid.uuid4()),
            "username": "admin2",
            "display_name": "Admin 2",
            "role": "account_admin",
            "password_hash": hash_password("AdminPass5678!"),
            "totp_secret": None,
            "totp_enabled": 0,
            "recovery_codes_json": codes_to_json(hashed),
            "active": 1,
            "created_at": now,
            "updated_at": now,
        })
        with self.assertRaises(PermissionError):
            self.admin.set_role(self.token, "admin2", "standard_user")


class TestDeactivate(unittest.TestCase):
    def setUp(self):
        self.store, self.auth, self.admin, self.token = _bootstrapped()
        self.admin.create_user(self.token, "user1", "UserPass1234!", "standard_user")

    def test_deactivate(self):
        self.admin.deactivate_user(self.token, "user1")
        result = self.auth.login("user1", "UserPass1234!")
        self.assertFalse(result.ok)

    def test_reactivate(self):
        self.admin.deactivate_user(self.token, "user1")
        self.admin.reactivate_user(self.token, "user1")
        result = self.auth.login("user1", "UserPass1234!")
        self.assertTrue(result.ok)

    def test_cannot_deactivate_peer(self):
        import time, uuid
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        from services.nova_shell.auth import hash_password
        from services.nova_shell.recovery import codes_to_json, generate_recovery_codes
        _, hashed = generate_recovery_codes()
        self.store.create_user({
            "id": str(uuid.uuid4()),
            "username": "admin2",
            "display_name": "Admin 2",
            "role": "account_admin",
            "password_hash": hash_password("AdminPass5678!"),
            "totp_secret": None,
            "totp_enabled": 0,
            "recovery_codes_json": codes_to_json(hashed),
            "active": 1,
            "created_at": now,
            "updated_at": now,
        })
        with self.assertRaises(PermissionError):
            self.admin.deactivate_user(self.token, "admin2")


class TestChangePassword(unittest.TestCase):
    def setUp(self):
        self.store, self.auth, self.admin, self.token = _bootstrapped()

    def test_admin_changes_own_password(self):
        self.admin.change_password(self.token, "admin", "NewAdminPass5678!")
        self.assertTrue(self.auth.login("admin", "NewAdminPass5678!").ok)

    def test_admin_resets_user_password(self):
        self.admin.create_user(self.token, "user1", "OldPass1234!", "standard_user")
        self.admin.change_password(self.token, "user1", "NewPass5678!")
        self.assertTrue(self.auth.login("user1", "NewPass5678!").ok)

    def test_short_new_password_rejected(self):
        with self.assertRaises(ValueError):
            self.admin.change_password(self.token, "admin", "short")


class TestCustomRoles(unittest.TestCase):
    def setUp(self):
        self.store, self.auth, self.admin, self.token = _bootstrapped()

    def test_create_custom_role(self):
        role = self.admin.create_custom_role(
            self.token, "data_entry", "Data Entry", level=3,
            permissions=["data.read", "backpacks.run"]
        )
        self.assertEqual(role["name"], "data_entry")
        self.assertEqual(role["level"], 3)

    def test_create_user_with_custom_role(self):
        self.admin.create_custom_role(
            self.token, "data_entry", "Data Entry", level=3,
            permissions=["data.read", "backpacks.run"]
        )
        user = self.admin.create_user(self.token, "clerk1", "ClerkPass1234!", "data_entry")
        self.assertEqual(user["role"], "data_entry")

    def test_custom_role_permissions_work(self):
        self.admin.create_custom_role(
            self.token, "data_entry", "Data Entry", level=3,
            permissions=["data.read", "backpacks.run"]
        )
        self.admin.create_user(self.token, "clerk1", "ClerkPass1234!", "data_entry")
        clerk_token = self.auth.login("clerk1", "ClerkPass1234!").token
        self.assertTrue(self.auth.check_permission(clerk_token, "data.read"))
        self.assertFalse(self.auth.check_permission(clerk_token, "users.create"))

    def test_cannot_grant_llc_only_permission(self):
        with self.assertRaises(ValueError):
            self.admin.create_custom_role(
                self.token, "bad_role", "Bad Role", level=3,
                permissions=["backpacks.develop"]
            )

    def test_cannot_grant_system_config(self):
        with self.assertRaises(ValueError):
            self.admin.create_custom_role(
                self.token, "bad_role2", "Bad Role 2", level=3,
                permissions=["system.config"]
            )

    def test_level_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            self.admin.create_custom_role(
                self.token, "too_high", "Too High", level=1,
                permissions=["data.read"]
            )

    def test_invalid_name_rejected(self):
        with self.assertRaises(ValueError):
            self.admin.create_custom_role(
                self.token, "Bad Name!", "Bad", level=3, permissions=[]
            )

    def test_list_custom_roles(self):
        self.admin.create_custom_role(
            self.token, "role_a", "Role A", level=2, permissions=["data.read"]
        )
        self.admin.create_custom_role(
            self.token, "role_b", "Role B", level=3, permissions=["reports.read"]
        )
        roles = self.admin.list_custom_roles(self.token)
        names = [r["name"] for r in roles]
        self.assertIn("role_a", names)
        self.assertIn("role_b", names)

    def test_update_custom_role(self):
        self.admin.create_custom_role(
            self.token, "my_role", "My Role", level=3, permissions=["data.read"]
        )
        self.admin.update_custom_role(self.token, "my_role", label="Updated Label")
        role = self.store.get_custom_role_by_name("my_role")
        self.assertEqual(role["label"], "Updated Label")

    def test_delete_custom_role_no_users(self):
        self.admin.create_custom_role(
            self.token, "temp_role", "Temp", level=4, permissions=["system.status"]
        )
        self.admin.delete_custom_role(self.token, "temp_role")
        self.assertIsNone(self.store.get_custom_role_by_name("temp_role"))

    def test_delete_blocked_when_users_assigned(self):
        self.admin.create_custom_role(
            self.token, "active_role", "Active", level=3, permissions=["data.read"]
        )
        self.admin.create_user(self.token, "holder", "HolderPass1234!", "active_role")
        with self.assertRaises(RuntimeError):
            self.admin.delete_custom_role(self.token, "active_role")

    def test_standard_user_cannot_manage_custom_roles(self):
        self.admin.create_user(self.token, "su1", "StdPass12345!", "standard_user")
        su_token = self.auth.login("su1", "StdPass12345!").token
        with self.assertRaises(PermissionError):
            self.admin.create_custom_role(
                su_token, "sneaky", "Sneaky", level=4, permissions=[]
            )


class TestRecoveryCodes(unittest.TestCase):
    def setUp(self):
        self.store, self.auth, self.admin, self.token = _bootstrapped()

    def test_regenerate_returns_codes(self):
        codes = self.admin.regenerate_recovery_codes(self.token)
        self.assertEqual(len(codes), 8)
        for code in codes:
            self.assertIn("-", code)

    @unittest.skipUnless(
        __import__("importlib.util", fromlist=["find_spec"]).find_spec("pyotp"),
        "pyotp not installed"
    )
    def test_recovery_code_login(self):
        setup = self.admin.setup_totp(self.token)
        import unittest.mock as mock
        with mock.patch("services.nova_shell.admin.verify_totp", return_value=True):
            self.admin.confirm_totp(self.token, "000000")
        codes = self.admin.regenerate_recovery_codes(self.token)
        self.auth.logout(self.token)
        result = self.auth.login("admin", "AdminPass1234!", recovery_code=codes[0])
        self.assertTrue(result.ok)
        self.auth.logout(result.token)
        result2 = self.auth.login("admin", "AdminPass1234!", recovery_code=codes[0])
        self.assertFalse(result2.ok)


class TestListUsers(unittest.TestCase):
    def setUp(self):
        self.store, self.auth, self.admin, self.token = _bootstrapped()

    def test_list_users_hides_secrets(self):
        self.admin.create_user(self.token, "user1", "UserPass1234!", "viewer")
        users = self.admin.list_users(self.token)
        for u in users:
            self.assertNotIn("password_hash", u)
            self.assertNotIn("totp_secret", u)
            self.assertNotIn("recovery_codes_json", u)


if __name__ == "__main__":
    unittest.main()
