from __future__ import annotations

import os
import secrets
import time


CONTROL_LOCAL_ONLY_REASON = "control_local_only_set_NOVA_CONTROL_TOKEN"


def _try_shell_login(payload: dict, totp_code: str = "", recovery_code: str = ""):
    """
    Attempt Nova Shell login. Returns (token, error_str) or (None, None) if Shell inactive.
    Caller decides what to do on None/None (fall back to env-var path).
    """
    try:
        from services.nova_shell_control_bridge import shell_login, shell_is_active
        if not shell_is_active():
            return None, None
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "").strip()
        result = shell_login(username, password, totp_code=totp_code,
                             recovery_code=recovery_code)
        if result is None:
            return None, None
        if result.ok:
            return result.token, None
        # Distinguish 2FA-required vs bad credentials
        if result.totp_required:
            return None, "totp_required"
        return None, result.error or "invalid_credentials"
    except Exception:
        return None, None


def _try_shell_verify(token: str):
    """Returns ShellSessionInfo or None (Shell inactive or token invalid)."""
    if not token:
        return None
    try:
        from services.nova_shell_control_bridge import shell_verify_session
        return shell_verify_session(token)
    except Exception:
        return None


def _try_shell_logout(token: str) -> None:
    if not token:
        return
    try:
        from services.nova_shell_control_bridge import shell_logout
        shell_logout(token)
    except Exception:
        pass


class ControlAuthService:
    """Own control login/session gating helpers outside the HTTP transport layer.

    Auth priority:
      1. Nova Shell (when DB exists and has at least one active user)
      2. Env-var fallback: NOVA_CONTROL_USER + NOVA_CONTROL_PASS

    The cookie name `nova_control_session` is used in both paths.
    Under Nova Shell the cookie value is a 64-char Shell token;
    under env-var auth it is a 48-char secrets.token_hex(24).
    """

    @staticmethod
    def control_login_enabled(*, environ=None) -> bool:
        # Active when Shell has users OR env vars are set.
        try:
            from services.nova_shell_control_bridge import shell_is_active
            if shell_is_active():
                return True
        except Exception:
            pass
        env = environ if environ is not None else os.environ
        user = str(env.get("NOVA_CONTROL_USER") or "").strip()
        password = str(env.get("NOVA_CONTROL_PASS") or "").strip()
        return bool(user and password)

    @staticmethod
    def prune_control_sessions(*, control_sessions: dict, now_fn=time.time) -> None:
        now = now_fn()
        stale = [sid for sid, exp in control_sessions.items() if exp <= now]
        for sid in stale:
            control_sessions.pop(sid, None)

    def control_login_auth(
        self,
        handler,
        *,
        control_login_enabled_fn,
        prune_control_sessions_fn,
        parse_cookie_map_fn,
        control_sessions: dict,
        now_fn=time.time,
    ) -> tuple[bool, str]:
        if not control_login_enabled_fn():
            return True, ""

        cookies = parse_cookie_map_fn(handler)
        token = str(cookies.get("nova_control_session") or "").strip()

        # ── Path 1: Nova Shell session verification ───────────────────────
        if token:
            info = _try_shell_verify(token)
            if info is not None:
                return True, ""

        # ── Path 2: Legacy in-memory session dict ─────────────────────────
        prune_control_sessions_fn()
        if token and control_sessions.get(token, 0) > now_fn():
            return True, ""

        return False, "control_login_required"

    def control_page_gate(
        self,
        handler,
        *,
        dev_mode_enabled_fn,
        control_login_auth_fn,
        is_local_client_fn,
        environ=None,
    ) -> tuple[bool, str]:
        env = environ if environ is not None else os.environ
        if dev_mode_enabled_fn():
            return True, ""

        ok_login, reason_login = control_login_auth_fn(handler)
        if not ok_login:
            return False, reason_login

        expected = str(env.get("NOVA_CONTROL_TOKEN") or "").strip()
        if expected:
            return True, ""
        if is_local_client_fn(handler):
            return True, ""
        return False, CONTROL_LOCAL_ONLY_REASON

    def control_api_auth(
        self,
        handler,
        qs: dict,
        *,
        control_login_auth_fn,
        is_local_client_fn,
        request_control_key_fn,
        environ=None,
        compare_digest_fn=secrets.compare_digest,
    ) -> tuple[bool, str]:
        env = environ if environ is not None else os.environ
        ok_login, reason_login = control_login_auth_fn(handler)
        if not ok_login:
            return False, reason_login

        expected = str(env.get("NOVA_CONTROL_TOKEN") or "").strip()
        if expected:
            got = request_control_key_fn(handler, qs)
            if got and compare_digest_fn(got, expected):
                return True, ""
            return False, "control_auth_failed"

        if is_local_client_fn(handler):
            return True, ""
        return False, CONTROL_LOCAL_ONLY_REASON

    @staticmethod
    def new_control_session(
        *,
        control_sessions: dict,
        ttl_seconds: int,
        token_hex_fn=secrets.token_hex,
        now_fn=time.time,
    ) -> str:
        sid = token_hex_fn(24)
        control_sessions[sid] = now_fn() + ttl_seconds
        return sid

    @staticmethod
    def clear_control_session(handler, *, control_sessions: dict,
                               parse_cookie_map_fn) -> None:
        sid = str(parse_cookie_map_fn(handler).get("nova_control_session") or "").strip()
        if sid:
            _try_shell_logout(sid)          # revoke Shell session if active
            control_sessions.pop(sid, None) # prune legacy dict (no-op if Shell token)

    @staticmethod
    def control_login_action(
        payload: dict,
        *,
        control_login_enabled_fn,
        new_control_session_fn,
        environ=None,
        compare_digest_fn=secrets.compare_digest,
    ) -> tuple[int, dict, dict]:
        if not control_login_enabled_fn():
            return 400, {"ok": False, "error": "control_login_disabled"}, {}

        totp_code = str(payload.get("totp_code") or "").strip()
        recovery_code = str(payload.get("recovery_code") or "").strip()

        # ── Path 1: Nova Shell auth ───────────────────────────────────────
        shell_token, shell_error = _try_shell_login(payload, totp_code, recovery_code)
        if shell_error == "totp_required":
            return 401, {"ok": False, "error": "totp_required",
                         "message": "2FA code required"}, {}
        if shell_token is not None:
            return 200, {"ok": True, "message": "login_ok", "auth": "nova_shell"}, {
                "Set-Cookie": (
                    f"nova_control_session={shell_token}; "
                    "Path=/; HttpOnly; SameSite=Strict"
                )
            }
        if shell_error and shell_error not in ("", "invalid_credentials"):
            # Shell was active but returned a specific error (locked, inactive, etc.)
            return 403, {"ok": False, "error": shell_error}, {}

        # ── Path 2: Env-var fallback ──────────────────────────────────────
        env = environ if environ is not None else os.environ
        user_expected = str(env.get("NOVA_CONTROL_USER") or "").strip()
        pass_expected = str(env.get("NOVA_CONTROL_PASS") or "").strip()
        user = str(payload.get("username") or "").strip()
        pwd = str(payload.get("password") or "").strip()
        if (user and pwd
                and user_expected and pass_expected
                and compare_digest_fn(user, user_expected)
                and compare_digest_fn(pwd, pass_expected)):
            sid = new_control_session_fn()
            return 200, {"ok": True, "message": "login_ok", "auth": "env_var"}, {
                "Set-Cookie": (
                    f"nova_control_session={sid}; "
                    "Path=/; HttpOnly; SameSite=Strict"
                )
            }

        return 403, {"ok": False, "error": "invalid_credentials"}, {}

    @staticmethod
    def control_logout_action(
        handler, *, clear_control_session_fn
    ) -> tuple[int, dict, dict]:
        clear_control_session_fn(handler)
        return 200, {"ok": True, "message": "logout_ok"}, {
            "Set-Cookie": (
                "nova_control_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
            )
        }


CONTROL_AUTH_SERVICE = ControlAuthService()
