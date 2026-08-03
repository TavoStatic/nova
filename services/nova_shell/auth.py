from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.nova_shell._constants import (
    LOGIN_LOCKOUT_MINUTES,
    LOGIN_MAX_ATTEMPTS,
    MAX_SESSIONS_PER_USER,
    SESSION_EXPIRY_HOURS,
)
from services.nova_shell.recovery import (
    codes_from_json,
    codes_to_json,
    verify_and_consume_code,
)
from services.nova_shell.roles import resolve_has_permission
from services.nova_shell.store import ShellStore
from services.nova_shell.totp import verify_totp

try:
    from argon2 import PasswordHasher as _PH
    from argon2.exceptions import VerifyMismatchError as _VME
    _ARGON2_AVAILABLE = True
except ImportError:
    _PH = None  # type: ignore[assignment]
    _VME = Exception
    _ARGON2_AVAILABLE = False

import hashlib


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _now_ts() -> float:
    return time.time()


def _expiry_iso(hours: int = SESSION_EXPIRY_HOURS) -> str:
    import calendar
    ts = _now_ts() + hours * 3600
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _iso_to_ts(iso: str) -> float:
    import calendar
    try:
        return float(calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")))
    except Exception:
        return 0.0


def hash_password(password: str) -> str:
    if _ARGON2_AVAILABLE:
        return _PH().hash(password)
    return "sha256:" + hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith("sha256:"):
        expected = "sha256:" + hashlib.sha256(password.encode()).hexdigest()
        return secrets.compare_digest(expected, stored_hash)
    if _ARGON2_AVAILABLE:
        try:
            return _PH().verify(stored_hash, password)
        except Exception:
            return False
    return False


def _generate_token() -> str:
    return secrets.token_hex(32)


@dataclass
class LoginResult:
    ok: bool
    token: str = ""
    role: str = ""
    user_id: str = ""
    username: str = ""
    force_password_reset: bool = False
    error: str = ""


@dataclass
class SessionInfo:
    token: str
    user_id: str
    username: str
    role: str
    expires_at: str


class ShellAuth:
    """
    Authentication layer for Nova Shell.

    Handles login (password + optional TOTP/recovery), session lifecycle,
    brute-force lockout, and permission checks — including custom roles.
    """

    def __init__(self, store: ShellStore) -> None:
        self._store = store

    # ── Login ──────────────────────────────────────────────────────────────

    def login(
        self,
        username: str,
        password: str,
        totp_code: str = "",
        recovery_code: str = "",
    ) -> LoginResult:
        store = self._store
        user = store.get_user_by_username(username)

        if not user:
            secrets.compare_digest("x", "y")
            store.audit("login_fail", username=username, detail="unknown_user", ok=False)
            return LoginResult(ok=False, error="Invalid credentials.")

        if not user["active"]:
            store.audit("login_fail", username=username, detail="account_inactive", ok=False)
            return LoginResult(ok=False, error="Account is inactive.")

        if user["locked_until"]:
            if _iso_to_ts(user["locked_until"]) > _now_ts():
                store.audit("login_fail", username=username, detail="account_locked", ok=False)
                return LoginResult(ok=False, error="Account is temporarily locked. Try again later.")

        if not verify_password(password, user["password_hash"]):
            attempts = (user["failed_attempts"] or 0) + 1
            locked_until = None
            if attempts >= LOGIN_MAX_ATTEMPTS:
                locked_until = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(_now_ts() + LOGIN_LOCKOUT_MINUTES * 60),
                )
            store.record_failed_login(user["id"], locked_until=locked_until)
            store.audit("login_fail", user_id=user["id"], username=username, detail="bad_password", ok=False)
            return LoginResult(ok=False, error="Invalid credentials.")

        if user["totp_enabled"]:
            if totp_code:
                if not verify_totp(user["totp_secret"], totp_code):
                    store.record_failed_login(user["id"])
                    store.audit("login_fail", user_id=user["id"], username=username, detail="bad_totp", ok=False)
                    return LoginResult(ok=False, error="Invalid 2FA code.")
            elif recovery_code:
                codes = codes_from_json(user["recovery_codes_json"])
                matched, remaining = verify_and_consume_code(recovery_code, codes)
                if not matched:
                    store.record_failed_login(user["id"])
                    store.audit("login_fail", user_id=user["id"], username=username, detail="bad_recovery_code", ok=False)
                    return LoginResult(ok=False, error="Invalid recovery code.")
                store.update_user(user["id"], {"recovery_codes_json": codes_to_json(remaining)})
                store.audit("recovery_code_used", user_id=user["id"], username=username,
                            detail=f"remaining={len(remaining)}")
            else:
                store.audit("login_fail", user_id=user["id"], username=username, detail="2fa_required", ok=False)
                return LoginResult(ok=False, error="2FA code required.")

        store.clear_failed_logins(user["id"])

        if store.count_active_sessions(user["id"]) >= MAX_SESSIONS_PER_USER:
            store.evict_oldest_session(user["id"])

        token = _generate_token()
        now = _now_iso()
        store.create_session({
            "token": token,
            "user_id": user["id"],
            "role": user["role"],
            "created_at": now,
            "expires_at": _expiry_iso(),
            "last_seen": now,
        })

        store.audit("login_ok", user_id=user["id"], username=username)

        return LoginResult(
            ok=True,
            token=token,
            role=user["role"],
            user_id=user["id"],
            username=username,
            force_password_reset=bool(user.get("force_password_reset", 0)),
        )

    # ── Session ────────────────────────────────────────────────────────────

    def verify_session(self, token: str) -> SessionInfo | None:
        if not token:
            return None
        session = self._store.get_session(token)
        if not session or session["revoked"]:
            return None
        if _iso_to_ts(session["expires_at"]) <= _now_ts():
            return None
        user = self._store.get_user_by_id(session["user_id"])
        if not user or not user["active"]:
            return None
        self._store.touch_session(token)
        return SessionInfo(
            token=token,
            user_id=session["user_id"],
            username=user["username"],
            role=session["role"],
            expires_at=session["expires_at"],
        )

    def logout(self, token: str) -> None:
        session = self._store.get_session(token)
        self._store.revoke_session(token)
        if session:
            self._store.audit("logout", user_id=session["user_id"])

    def logout_all(self, user_id: str) -> None:
        self._store.revoke_all_sessions(user_id)
        self._store.audit("logout_all", user_id=user_id)

    # ── Permission ─────────────────────────────────────────────────────────

    def check_permission(self, token: str, permission: str) -> bool:
        """Return True if the session's role grants the requested permission.
        Resolves both static and custom roles."""
        info = self.verify_session(token)
        if not info:
            return False
        return resolve_has_permission(info.role, permission, self._store)

    def require_permission(self, token: str, permission: str) -> SessionInfo:
        """Return SessionInfo or raise PermissionError."""
        info = self.verify_session(token)
        if not info:
            raise PermissionError("Not authenticated.")
        if not resolve_has_permission(info.role, permission, self._store):
            raise PermissionError(f"Permission denied: {permission}")
        return info
