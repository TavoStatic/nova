from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.nova_shell.roles import (
    assignable_roles_for,
    can_assign_role,
    has_permission,
    is_assignable,
    is_static_role,
    resolve_can_assign_role,
    resolve_has_permission,
    resolve_role_exists,
    resolve_role_level,
    resolve_role_summary,
    role_exists,
    role_level,
    role_label,
    role_summary,
)
from services.nova_shell.store import ShellStore


def _make_store() -> ShellStore:
    tmp = tempfile.mkdtemp()
    return ShellStore(db_path=Path(tmp) / "roles_test.db")


def _add_custom_role(store: ShellStore, name: str, level: int, permissions: list[str]) -> None:
    import time, uuid
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    store.create_custom_role({
        "id": str(uuid.uuid4()),
        "name": name,
        "label": name.replace("_", " ").title(),
        "level": level,
        "permissions_json": json.dumps(permissions),
        "created_by": "test",
        "created_at": now,
        "updated_at": now,
    })


class TestStaticRoleExists(unittest.TestCase):
    def test_known_roles(self):
        for r in ["llc_master", "account_admin", "standard_user", "limited_user", "viewer"]:
            self.assertTrue(role_exists(r))

    def test_unknown_role(self):
        self.assertFalse(role_exists("ghost"))

    def test_old_names_gone(self):
        self.assertFalse(role_exists("district_admin"))
        self.assertFalse(role_exists("operator"))
        self.assertFalse(role_exists("analyst"))


class TestIsStaticRole(unittest.TestCase):
    def test_static(self):
        self.assertTrue(is_static_role("llc_master"))
        self.assertTrue(is_static_role("viewer"))

    def test_not_static(self):
        self.assertFalse(is_static_role("custom_role"))


class TestRoleLevel(unittest.TestCase):
    def test_order(self):
        self.assertLess(role_level("llc_master"), role_level("account_admin"))
        self.assertLess(role_level("account_admin"), role_level("standard_user"))
        self.assertLess(role_level("standard_user"), role_level("limited_user"))
        self.assertLess(role_level("limited_user"), role_level("viewer"))

    def test_unknown_raises(self):
        with self.assertRaises(KeyError):
            role_level("ghost")


class TestAssignable(unittest.TestCase):
    def test_llc_master_not_assignable(self):
        self.assertFalse(is_assignable("llc_master"))

    def test_others_assignable(self):
        for r in ["account_admin", "standard_user", "limited_user", "viewer"]:
            self.assertTrue(is_assignable(r))


class TestCanAssignRole(unittest.TestCase):
    def test_account_admin_can_assign_below(self):
        self.assertTrue(can_assign_role("account_admin", "standard_user"))
        self.assertTrue(can_assign_role("account_admin", "limited_user"))
        self.assertTrue(can_assign_role("account_admin", "viewer"))

    def test_account_admin_cannot_assign_itself(self):
        self.assertFalse(can_assign_role("account_admin", "account_admin"))

    def test_account_admin_cannot_assign_llc_master(self):
        self.assertFalse(can_assign_role("account_admin", "llc_master"))

    def test_standard_user_cannot_assign(self):
        self.assertFalse(can_assign_role("standard_user", "limited_user"))

    def test_viewer_cannot_assign_anything(self):
        self.assertFalse(can_assign_role("viewer", "viewer"))

    def test_unknown_actor_returns_false(self):
        self.assertFalse(can_assign_role("ghost", "viewer"))


class TestHasPermission(unittest.TestCase):
    def test_llc_master_has_all(self):
        self.assertTrue(has_permission("llc_master", "users.create"))
        self.assertTrue(has_permission("llc_master", "backpacks.develop"))
        self.assertTrue(has_permission("llc_master", "system.config"))

    def test_account_admin_has_users(self):
        self.assertTrue(has_permission("account_admin", "users.create"))
        self.assertTrue(has_permission("account_admin", "backpacks.install"))
        self.assertTrue(has_permission("account_admin", "audit.read"))
        self.assertTrue(has_permission("account_admin", "custom_roles.manage"))

    def test_account_admin_no_develop(self):
        self.assertFalse(has_permission("account_admin", "backpacks.develop"))
        self.assertFalse(has_permission("account_admin", "system.config"))

    def test_standard_user_limited(self):
        self.assertTrue(has_permission("standard_user", "backpacks.run"))
        self.assertTrue(has_permission("standard_user", "backpacks.configure"))
        self.assertFalse(has_permission("standard_user", "users.create"))
        self.assertFalse(has_permission("standard_user", "backpacks.install"))

    def test_limited_user(self):
        self.assertTrue(has_permission("limited_user", "backpacks.run"))
        self.assertFalse(has_permission("limited_user", "backpacks.configure"))
        self.assertFalse(has_permission("limited_user", "data.export"))

    def test_viewer_minimal(self):
        self.assertTrue(has_permission("viewer", "system.status"))
        self.assertFalse(has_permission("viewer", "data.read"))

    def test_unknown_role_returns_false(self):
        self.assertFalse(has_permission("ghost", "system.status"))


class TestAssignableRolesFor(unittest.TestCase):
    def test_account_admin_can_assign_three_static(self):
        roles = assignable_roles_for("account_admin")
        self.assertIn("standard_user", roles)
        self.assertIn("limited_user", roles)
        self.assertIn("viewer", roles)
        self.assertNotIn("account_admin", roles)
        self.assertNotIn("llc_master", roles)

    def test_standard_user_empty(self):
        self.assertEqual(assignable_roles_for("standard_user"), [])

    def test_viewer_empty(self):
        self.assertEqual(assignable_roles_for("viewer"), [])


class TestRoleSummary(unittest.TestCase):
    def test_ordered_by_level(self):
        summary = role_summary()
        levels = [r["level"] for r in summary]
        self.assertEqual(levels, sorted(levels))

    def test_has_all_roles(self):
        names = {r["role"] for r in role_summary()}
        self.assertIn("llc_master", names)
        self.assertIn("account_admin", names)
        self.assertIn("standard_user", names)
        self.assertIn("limited_user", names)


class TestResolveWithCustomRoles(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()
        _add_custom_role(self.store, "data_entry", level=2, permissions=["data.read", "backpacks.run"])

    def test_resolve_role_exists_custom(self):
        self.assertTrue(resolve_role_exists("data_entry", self.store))

    def test_resolve_role_exists_unknown(self):
        self.assertFalse(resolve_role_exists("ghost", self.store))

    def test_resolve_role_level_custom(self):
        self.assertEqual(resolve_role_level("data_entry", self.store), 2)

    def test_resolve_has_permission_custom(self):
        self.assertTrue(resolve_has_permission("data_entry", "data.read", self.store))
        self.assertTrue(resolve_has_permission("data_entry", "backpacks.run", self.store))
        self.assertFalse(resolve_has_permission("data_entry", "users.create", self.store))

    def test_account_admin_can_assign_custom(self):
        self.assertTrue(resolve_can_assign_role("account_admin", "data_entry", self.store))

    def test_standard_user_cannot_assign_custom(self):
        self.assertFalse(resolve_can_assign_role("standard_user", "data_entry", self.store))

    def test_resolve_role_summary_includes_custom(self):
        summary = resolve_role_summary(self.store)
        names = [r["role"] for r in summary]
        self.assertIn("data_entry", names)
        custom = next(r for r in summary if r["role"] == "data_entry")
        self.assertTrue(custom["custom"])

    def test_resolve_without_store_ignores_custom(self):
        self.assertFalse(resolve_role_exists("data_entry"))
        self.assertFalse(resolve_has_permission("data_entry", "data.read"))


if __name__ == "__main__":
    unittest.main()
