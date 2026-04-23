from __future__ import annotations

import os
import secrets
import time


class ControlAuthService:
    """Own control login/session gating helpers outside the HTTP transport layer."""

    @staticmethod
    def control_login_enabled(*, environ=None) -> bool:
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

        prune_control_sessions_fn()
        cookies = parse_cookie_map_fn(handler)
        sid = str(cookies.get("nova_control_session") or "").strip()
        if sid and control_sessions.get(sid, 0) > now_fn():
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
        return False, "control_local_only_set_NOVA_CONTROL_TOKEN"

    @staticmethod
    def new_control_session(*, control_sessions: dict, ttl_seconds: int, token_hex_fn=secrets.token_hex, now_fn=time.time) -> str:
        sid = token_hex_fn(24)
        control_sessions[sid] = now_fn() + ttl_seconds
        return sid

    @staticmethod
    def clear_control_session(handler, *, control_sessions: dict, parse_cookie_map_fn) -> None:
        sid = str(parse_cookie_map_fn(handler).get("nova_control_session") or "").strip()
        if sid:
            control_sessions.pop(sid, None)

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

        env = environ if environ is not None else os.environ
        user_expected = str(env.get("NOVA_CONTROL_USER") or "").strip()
        pass_expected = str(env.get("NOVA_CONTROL_PASS") or "").strip()
        user = str(payload.get("username") or "").strip()
        pwd = str(payload.get("password") or "").strip()
        if user and pwd and compare_digest_fn(user, user_expected) and compare_digest_fn(pwd, pass_expected):
            sid = new_control_session_fn()
            return 200, {"ok": True, "message": "login_ok"}, {
                "Set-Cookie": f"nova_control_session={sid}; Path=/; HttpOnly; SameSite=Strict"
            }
        return 403, {"ok": False, "error": "invalid_credentials"}, {}

    @staticmethod
    def control_logout_action(handler, *, clear_control_session_fn) -> tuple[int, dict, dict]:
        clear_control_session_fn(handler)
        return 200, {"ok": True, "message": "logout_ok"}, {
            "Set-Cookie": "nova_control_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
        }


CONTROL_AUTH_SERVICE = ControlAuthService()