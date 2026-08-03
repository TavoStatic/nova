from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.nova_shell.store import ShellStore


def _make_store() -> ShellStore:
    tmp = tempfile.mkdtemp()
    return ShellStore(db_path=Path(tmp) / "test_shell.db")


def _user(username: str = "alice", role: str = "operator") -> dict:
    import time
    import uuid
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "id": str(uuid.uuid4()),
        "username": username,
        "display_name": username.title(),
        "role": role,
        "password_hash": "hash_placeholder",
        "totp_secret": None,
        "totp_enabled": 0,
        "recovery_codes_json": "[]",
        "active": 1,
        "created_at": now,
        "updated_at": now,
    }


def _session(user_id: str, token: str = "tok1", role: str = "operator") -> dict:
    import time
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    future = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
    return {
        "token": token,
        "user_id": user_id,
        "role": role,
        "created_at": now,
        "expires_at": future,
        "last_seen": now,
    }


class TestShellStoreUsers(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()

    def test_create_and_get_user(self):
        u = _user()
        self.store.create_user(u)
        result = self.store.get_user_by_username(u["username"])
        self.assertIsNotNone(result)
        self.assertEqual(result["username"], u["username"])

    def test_get_unknown_user_returns_none(self):
        self.assertIsNone(self.store.get_user_by_username("nobody"))

    def test_get_user_by_id(self):
        u = _user()
        self.store.create_user(u)
        result = self.store.get_user_by_id(u["id"])
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], u["id"])

    def test_update_user(self):
        u = _user()
        self.store.create_user(u)
        self.store.update_user(u["id"], {"display_name": "Alice Updated"})
        result = self.store.get_user_by_id(u["id"])
        self.assertEqual(result["display_name"], "Alice Updated")

    def test_record_and_clear_failed_logins(self):
        u = _user()
        self.store.create_user(u)
        self.store.record_failed_login(u["id"])
        self.store.record_failed_login(u["id"])
        result = self.store.get_user_by_id(u["id"])
        self.assertEqual(result["failed_attempts"], 2)
        self.store.clear_failed_logins(u["id"])
        result = self.store.get_user_by_id(u["id"])
        self.assertEqual(result["failed_attempts"], 0)
        self.assertIsNone(result["locked_until"])

    def test_list_users(self):
        self.store.create_user(_user("alice"))
        self.store.create_user(_user("bob"))
        users = self.store.list_users()
        self.assertEqual(len(users), 2)


class TestShellStoreSessions(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()
        self.user = _user()
        self.store.create_user(self.user)

    def test_create_and_get_session(self):
        s = _session(self.user["id"])
        self.store.create_session(s)
        result = self.store.get_session(s["token"])
        self.assertIsNotNone(result)
        self.assertEqual(result["token"], s["token"])
        self.assertEqual(result["revoked"], 0)

    def test_revoke_session(self):
        s = _session(self.user["id"])
        self.store.create_session(s)
        self.store.revoke_session(s["token"])
        result = self.store.get_session(s["token"])
        self.assertEqual(result["revoked"], 1)

    def test_count_active_sessions(self):
        self.store.create_session(_session(self.user["id"], token="t1"))
        self.store.create_session(_session(self.user["id"], token="t2"))
        self.assertEqual(self.store.count_active_sessions(self.user["id"]), 2)
        self.store.revoke_session("t1")
        self.assertEqual(self.store.count_active_sessions(self.user["id"]), 1)

    def test_evict_oldest_session(self):
        import time
        self.store.create_session(_session(self.user["id"], token="old"))
        time.sleep(0.01)
        self.store.create_session(_session(self.user["id"], token="new"))
        self.assertEqual(self.store.count_active_sessions(self.user["id"]), 2)
        self.store.evict_oldest_session(self.user["id"])
        self.assertEqual(self.store.count_active_sessions(self.user["id"]), 1)
        remaining = self.store.get_session("new")
        self.assertEqual(remaining["revoked"], 0)


class TestShellStoreAudit(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()

    def test_audit_log_entry(self):
        self.store.audit("login_ok", user_id="u1", username="alice", detail="test")
        log = self.store.get_audit_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["action"], "login_ok")
        self.assertEqual(log[0]["username"], "alice")
        self.assertEqual(log[0]["ok"], 1)

    def test_audit_log_failure(self):
        self.store.audit("login_fail", username="bad_actor", ok=False)
        log = self.store.get_audit_log()
        self.assertEqual(log[0]["ok"], 0)


if __name__ == "__main__":
    unittest.main()
