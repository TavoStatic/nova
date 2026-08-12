"""
nova_shell_control_bridge.py
-----------------------------
Bridge between control_auth.py (nova_http.py's auth layer) and Nova Shell.

NOVA_DOC:
  category: subsystem
  authority: active_authority
  last_session: 2026-08-05
  last_agent: claude-cowork
  session_state: current
  next_step: none
  open: none

When Nova Shell is "active" (DB exists and has at least one user), login/session
verification/logout are routed through ShellAuth. When Shell is not active, every
method returns None/False and control_auth falls back to the existing env-var path.

This is deliberately a thin adapter. It does not replace control_auth — it sits
between it and nova_shell so the HTTP layer stays unchanged.

Activation rule:
  Shell is active when:
    1. runtime/nova_shell/nova_shell.db exists on disk AND
    2. at least one active user row exists in the users table

If Shell import fails (argon2-cffi not installed, etc.), the bridge silently
remains inactive and env-var auth continues to work.

NOVA_DOC:
  category: subsystem
  authority: active_authority
  last_session: 2026-08-05
  last_agent: claude-cowork
  session_state: current
  next_step: none
  open: none
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

# Default Shell DB path — mirrors nova_shell/store.py
_SHELL_DB_DEFAULT = (
    Path(__file__).resolve().parents[1] / "runtime" / "nova_shell" / "nova_shell.db"
)

_LOCK = threading.Lock()
_bridge_instance: "_NovaShellBridge | None" = None


# ── Public dataclasses mirroring ShellAuth.LoginResult / SessionInfo ────────

class ShellLoginResult:
    __slots__ = ("ok", "token", "role", "username", "force_password_reset", "error",
                 "totp_required")

    def __init__(
        self,
        *,
        ok: bool,
        token: str = "",
        role: str = "",
        username: str = "",
        force_password_reset: bool = False,
        error: str = "",
        totp_required: bool = False,
    ) -> None:
        self.ok = ok
        self.token = token
        self.role = role
        self.username = username
        self.force_password_reset = force_password_reset
        self.error = error
        self.totp_required = totp_required


class ShellSessionInfo:
    __slots__ = ("token", "user_id", "username", "role", "expires_at")

    def __init__(self, *, token: str, user_id: str, username: str,
                 role: str, expires_at: str) -> None:
        self.token = token
        self.user_id = user_id
        self.username = username
        self.role = role
        self.expires_at = expires_at


# ── Internal bridge ──────────────────────────────────────────────────────────

class _NovaShellBridge:
    """
    Wraps ShellStore + ShellAuth. Instantiated once when Shell is active.
    Thread-safe for the lazy-init path.
    """

    def __init__(self, db_path: Path) -> None:
        from services.nova_shell.store import ShellStore
        from services.nova_shell.auth import ShellAuth
        self._store = ShellStore(db_path)
        self._auth = ShellAuth(self._store)

    def has_active_user(self) -> bool:
        """Return True if at least one active user exists."""
        try:
            users = self._store.list_users()
            return any(u.get("active") for u in users)
        except Exception:
            return False

    def login(
        self,
        username: str,
        password: str,
        totp_code: str = "",
        recovery_code: str = "",
    ) -> ShellLoginResult:
        try:
            result = self._auth.login(username, password, totp_code, recovery_code)
        except Exception as exc:
            return ShellLoginResult(ok=False, error=f"shell_auth_error: {exc}")
        # Detect 2FA-required response (no token, error mentions 2FA)
        totp_req = (
            not result.ok
            and "2FA" in (result.error or "")
        )
        return ShellLoginResult(
            ok=result.ok,
            token=result.token,
            role=result.role,
            username=result.username,
            force_password_reset=result.force_password_reset,
            error=result.error,
            totp_required=totp_req,
        )

    def verify_session_token(self, token: str) -> ShellSessionInfo | None:
        if not token:
            return None
        try:
            info = self._auth.verify_session(token)
        except Exception:
            return None
        if info is None:
            return None
        return ShellSessionInfo(
            token=info.token,
            user_id=info.user_id,
            username=info.username,
            role=info.role,
            expires_at=info.expires_at,
        )

    def logout(self, token: str) -> None:
        if not token:
            return
        try:
            self._auth.logout(token)
        except Exception:
            pass

    def status(self) -> dict[str, Any]:
        try:
            users = self._store.list_users()
            active = [u for u in users if u.get("active")]
        except Exception:
            users, active = [], []
        return {
            "active": True,
            "user_count": len(users),
            "active_user_count": len(active),
        }


# ── Module-level API ─────────────────────────────────────────────────────────

def _get_bridge(db_path: Path | None = None) -> "_NovaShellBridge | None":
    """
    Lazy-init: return the bridge if Shell is available, else None.
    Called on every request that needs auth — cheap after first call.
    """
    global _bridge_instance
    path = Path(db_path or _SHELL_DB_DEFAULT)
    # Fast path: already initialized
    if _bridge_instance is not None:
        return _bridge_instance
    # DB doesn't exist → Shell not set up
    if not path.exists():
        return None
    with _LOCK:
        if _bridge_instance is not None:
            return _bridge_instance
        try:
            bridge = _NovaShellBridge(path)
            if not bridge.has_active_user():
                return None
            _bridge_instance = bridge
        except Exception:
            return None
    return _bridge_instance


def shell_is_active(db_path: Path | None = None) -> bool:
    """True when Shell is initialized and has at least one active user."""
    return _get_bridge(db_path) is not None


def shell_login(
    username: str,
    password: str,
    *,
    totp_code: str = "",
    recovery_code: str = "",
    db_path: Path | None = None,
) -> ShellLoginResult | None:
    """
    Attempt Shell login. Returns None if Shell is not active (caller falls back).
    Returns ShellLoginResult with ok=True/False on credential check.
    """
    bridge = _get_bridge(db_path)
    if bridge is None:
        return None
    return bridge.login(username, password, totp_code, recovery_code)


def shell_verify_session(
    token: str,
    *,
    db_path: Path | None = None,
) -> ShellSessionInfo | None:
    """
    Verify a Shell session token. Returns None if Shell inactive or token invalid.
    """
    bridge = _get_bridge(db_path)
    if bridge is None:
        return None
    return bridge.verify_session_token(token)


def shell_logout(token: str, *, db_path: Path | None = None) -> None:
    """Revoke a Shell session token. Silent no-op if Shell inactive."""
    bridge = _get_bridge(db_path)
    if bridge is not None:
        bridge.logout(token)


def shell_status(db_path: Path | None = None) -> dict[str, Any]:
    """Status blob for diagnostics and http_trust.shell_http_status()."""
    bridge = _get_bridge(db_path)
    if bridge is None:
        return {
            "active": False,
            "reason": "no_db_or_no_active_users",
            "fallback": "env_var_auth",
        }
    return bridge.status()
