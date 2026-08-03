from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "runtime" / "nova_shell" / "nova_shell.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS custom_roles (
    id              TEXT PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,
    label           TEXT NOT NULL,
    level           INTEGER NOT NULL CHECK(level BETWEEN 2 AND 4),
    permissions_json TEXT NOT NULL DEFAULT '[]',
    created_by      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id                  TEXT PRIMARY KEY,
    username            TEXT UNIQUE NOT NULL,
    display_name        TEXT NOT NULL,
    role                TEXT NOT NULL,
    password_hash       TEXT NOT NULL,
    totp_secret         TEXT,
    totp_enabled        INTEGER DEFAULT 0,
    recovery_codes_json TEXT DEFAULT '[]',
    active              INTEGER DEFAULT 1,
    failed_attempts     INTEGER DEFAULT 0,
    locked_until        TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    last_login          TEXT,
    force_password_reset INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    role        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    last_seen   TEXT,
    revoked     INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    user_id     TEXT,
    username    TEXT,
    action      TEXT NOT NULL,
    detail      TEXT,
    ok          INTEGER DEFAULT 1
);
"""


@contextmanager
def _conn(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class ShellStore:
    """SQLite-backed store for nova_shell users, sessions, and audit log."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db = Path(db_path or _DEFAULT_DB_PATH)
        self._init_schema()

    def _init_schema(self) -> None:
        with _conn(self._db) as con:
            con.executescript(_SCHEMA)

    # ── Users ──────────────────────────────────────────────────────────────

    def create_user(self, user: dict[str, Any]) -> None:
        with _conn(self._db) as con:
            con.execute(
                """INSERT INTO users
                   (id, username, display_name, role, password_hash,
                    totp_secret, totp_enabled, recovery_codes_json, active,
                    created_at, updated_at)
                   VALUES (:id, :username, :display_name, :role, :password_hash,
                    :totp_secret, :totp_enabled, :recovery_codes_json, :active,
                    :created_at, :updated_at)""",
                user,
            )

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with _conn(self._db) as con:
            row = con.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        with _conn(self._db) as con:
            row = con.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_users(self) -> list[dict[str, Any]]:
        with _conn(self._db) as con:
            rows = con.execute(
                "SELECT * FROM users ORDER BY role, username"
            ).fetchall()
            return [dict(r) for r in rows]

    def update_user(self, user_id: str, fields: dict[str, Any]) -> None:
        fields = dict(fields)
        fields["updated_at"] = _now()
        cols = ", ".join(f"{k} = :{k}" for k in fields)
        fields["_id"] = user_id
        with _conn(self._db) as con:
            con.execute(f"UPDATE users SET {cols} WHERE id = :_id", fields)

    def record_failed_login(self, user_id: str, locked_until: str | None = None) -> None:
        with _conn(self._db) as con:
            con.execute(
                "UPDATE users SET failed_attempts = failed_attempts + 1, "
                "locked_until = ?, updated_at = ? WHERE id = ?",
                (locked_until, _now(), user_id),
            )

    def clear_failed_logins(self, user_id: str) -> None:
        with _conn(self._db) as con:
            con.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL, "
                "last_login = ?, updated_at = ? WHERE id = ?",
                (_now(), _now(), user_id),
            )

    # ── Sessions ───────────────────────────────────────────────────────────

    def create_session(self, session: dict[str, Any]) -> None:
        with _conn(self._db) as con:
            con.execute(
                """INSERT INTO sessions
                   (token, user_id, role, created_at, expires_at, last_seen)
                   VALUES (:token, :user_id, :role, :created_at, :expires_at, :last_seen)""",
                session,
            )

    def get_session(self, token: str) -> dict[str, Any] | None:
        with _conn(self._db) as con:
            row = con.execute(
                "SELECT * FROM sessions WHERE token = ?", (token,)
            ).fetchone()
            return dict(row) if row else None

    def touch_session(self, token: str) -> None:
        with _conn(self._db) as con:
            con.execute(
                "UPDATE sessions SET last_seen = ? WHERE token = ?",
                (_now(), token),
            )

    def revoke_session(self, token: str) -> None:
        with _conn(self._db) as con:
            con.execute(
                "UPDATE sessions SET revoked = 1 WHERE token = ?", (token,)
            )

    def revoke_all_sessions(self, user_id: str) -> None:
        with _conn(self._db) as con:
            con.execute(
                "UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user_id,)
            )

    def count_active_sessions(self, user_id: str) -> int:
        now = _now()
        with _conn(self._db) as con:
            row = con.execute(
                "SELECT COUNT(*) FROM sessions "
                "WHERE user_id = ? AND revoked = 0 AND expires_at > ?",
                (user_id, now),
            ).fetchone()
            return int(row[0]) if row else 0

    def evict_oldest_session(self, user_id: str) -> None:
        with _conn(self._db) as con:
            con.execute(
                """UPDATE sessions SET revoked = 1 WHERE token = (
                   SELECT token FROM sessions
                   WHERE user_id = ? AND revoked = 0
                   ORDER BY created_at ASC LIMIT 1)""",
                (user_id,),
            )

    # ── Audit ──────────────────────────────────────────────────────────────

    def audit(
        self,
        action: str,
        *,
        user_id: str = "",
        username: str = "",
        detail: str = "",
        ok: bool = True,
    ) -> None:
        with _conn(self._db) as con:
            con.execute(
                "INSERT INTO audit_log (ts, user_id, username, action, detail, ok) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), user_id or None, username or None, action, detail or None, int(ok)),
            )

    def get_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        with _conn(self._db) as con:
            rows = con.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Custom roles ───────────────────────────────────────────────────────────

    def create_custom_role(self, role: dict[str, Any]) -> None:
        with _conn(self._db) as con:
            con.execute(
                """INSERT INTO custom_roles
                   (id, name, label, level, permissions_json, created_by, created_at, updated_at)
                   VALUES (:id, :name, :label, :level, :permissions_json,
                           :created_by, :created_at, :updated_at)""",
                role,
            )

    def get_custom_role_by_name(self, name: str) -> dict[str, Any] | None:
        with _conn(self._db) as con:
            row = con.execute(
                "SELECT * FROM custom_roles WHERE name = ?", (name,)
            ).fetchone()
            return dict(row) if row else None

    def list_custom_roles(self) -> list[dict[str, Any]]:
        with _conn(self._db) as con:
            rows = con.execute(
                "SELECT * FROM custom_roles ORDER BY level, name"
            ).fetchall()
            return [dict(r) for r in rows]

    def update_custom_role(self, name: str, fields: dict[str, Any]) -> None:
        fields = dict(fields)
        fields["updated_at"] = _now()
        cols = ", ".join(f"{k} = :{k}" for k in fields)
        fields["_name"] = name
        with _conn(self._db) as con:
            con.execute(f"UPDATE custom_roles SET {cols} WHERE name = :_name", fields)

    def delete_custom_role(self, name: str) -> None:
        with _conn(self._db) as con:
            con.execute("DELETE FROM custom_roles WHERE name = ?", (name,))

    def count_users_with_role(self, role_name: str) -> int:
        with _conn(self._db) as con:
            row = con.execute(
                "SELECT COUNT(*) FROM users WHERE role = ? AND active = 1", (role_name,)
            ).fetchone()
            return int(row[0]) if row else 0
