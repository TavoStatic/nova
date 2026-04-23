from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path


class ChatIdentityService:
    """Own chat auth persistence, password verification, and cookie-backed login state."""

    @staticmethod
    def chat_users_path(runtime_dir: Path) -> Path:
        return Path(runtime_dir) / "chat_users.json"

    @staticmethod
    def chat_auth_source(*, chat_users_path: Path, environ=None) -> str:
        env = environ if environ is not None else os.environ
        if Path(chat_users_path).exists():
            return "managed_file"
        if str(env.get("NOVA_CHAT_USERS_JSON") or "").strip():
            return "env_json"
        if str(env.get("NOVA_CHAT_USER") or "").strip() and str(env.get("NOVA_CHAT_PASS") or "").strip():
            return "env_pair"
        return "disabled"

    @staticmethod
    def hash_chat_password(password: str, *, iterations: int) -> dict:
        pwd = str(password or "")
        salt = os.urandom(16).hex()
        digest = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), bytes.fromhex(salt), max(1, int(iterations))).hex()
        return {"salt": salt, "hash": digest, "iterations": max(1, int(iterations))}

    def save_managed_chat_users(
        self,
        users: dict,
        *,
        normalize_user_id_fn,
        chat_users_path: Path,
        iterations: int,
    ) -> None:
        payload: dict[str, dict] = {}
        for raw_user, value in dict(users or {}).items():
            user = normalize_user_id_fn(str(raw_user or ""))
            if not user:
                continue
            if isinstance(value, dict):
                salt_hex = str(value.get("salt") or "").strip().lower()
                hash_hex = str(value.get("hash") or "").strip().lower()
                current_iterations = int(value.get("iterations") or iterations)
                if salt_hex and hash_hex:
                    payload[user] = {"salt": salt_hex, "hash": hash_hex, "iterations": max(1, current_iterations)}
                    continue
            payload[user] = self.hash_chat_password(str(value or ""), iterations=iterations)
        chat_path = Path(chat_users_path)
        chat_path.parent.mkdir(parents=True, exist_ok=True)
        chat_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    @staticmethod
    def chat_users(*, chat_users_path: Path, normalize_user_id_fn, environ=None) -> dict:
        env = environ if environ is not None else os.environ
        managed_path = Path(chat_users_path)
        if managed_path.exists():
            try:
                data = json.loads(managed_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            out: dict = {}
            if isinstance(data, dict):
                for raw_user, value in data.items():
                    user = normalize_user_id_fn(str(raw_user or ""))
                    if user:
                        out[user] = value
            return out

        env_json = str(env.get("NOVA_CHAT_USERS_JSON") or "").strip()
        if env_json:
            try:
                data = json.loads(env_json)
            except Exception:
                data = {}
            out: dict = {}
            if isinstance(data, dict):
                for raw_user, value in data.items():
                    user = normalize_user_id_fn(str(raw_user or ""))
                    if user:
                        out[user] = value
            return out

        env_user = normalize_user_id_fn(str(env.get("NOVA_CHAT_USER") or ""))
        env_pass = str(env.get("NOVA_CHAT_PASS") or "")
        if env_user and env_pass:
            return {env_user: env_pass}
        return {}

    @staticmethod
    def chat_password_matches(expected, pwd: str, *, iterations_default: int) -> bool:
        if isinstance(expected, dict):
            salt_hex = str(expected.get("salt") or "").strip().lower()
            hash_hex = str(expected.get("hash") or "").strip().lower()
            iterations = int(expected.get("iterations") or iterations_default)
            if not salt_hex or not hash_hex:
                return False
            try:
                candidate = hashlib.pbkdf2_hmac("sha256", str(pwd or "").encode("utf-8"), bytes.fromhex(salt_hex), max(1, iterations)).hex()
            except Exception:
                return False
            return secrets.compare_digest(candidate, hash_hex)
        return secrets.compare_digest(str(expected or ""), str(pwd or ""))

    @staticmethod
    def chat_login_enabled(*, chat_users_fn) -> bool:
        return bool(chat_users_fn())

    @staticmethod
    def prune_chat_sessions(*, chat_sessions: dict, now_fn=time.time) -> None:
        now = now_fn()
        stale = [sid for sid, (_user, exp) in chat_sessions.items() if exp <= now]
        for sid in stale:
            chat_sessions.pop(sid, None)

    @staticmethod
    def new_chat_session(
        user_id: str,
        *,
        chat_sessions: dict,
        normalize_user_id_fn,
        ttl_seconds: int,
        token_hex_fn=secrets.token_hex,
        now_fn=time.time,
    ) -> str:
        sid = token_hex_fn(24)
        chat_sessions[sid] = (normalize_user_id_fn(user_id), now_fn() + ttl_seconds)
        return sid

    @staticmethod
    def clear_chat_session(handler, *, chat_sessions: dict, parse_cookie_map_fn) -> None:
        sid = (parse_cookie_map_fn(handler).get("nova_chat_session") or "").strip()
        if sid:
            chat_sessions.pop(sid, None)

    def chat_login_auth(
        self,
        handler,
        *,
        chat_login_enabled_fn,
        prune_chat_sessions_fn,
        parse_cookie_map_fn,
        chat_sessions: dict,
        now_fn=time.time,
    ) -> tuple[bool, str]:
        if not chat_login_enabled_fn():
            return True, ""

        prune_chat_sessions_fn()
        cookies = parse_cookie_map_fn(handler)
        sid = (cookies.get("nova_chat_session") or "").strip()
        if sid:
            info = chat_sessions.get(sid)
            if info and info[1] > now_fn():
                return True, str(info[0] or "")
        return False, "chat_login_required"

    @staticmethod
    def chat_login_action(
        payload: dict,
        *,
        chat_login_enabled_fn,
        chat_users_fn,
        normalize_user_id_fn,
        chat_password_matches_fn,
        new_chat_session_fn,
    ) -> tuple[int, dict, dict]:
        if not chat_login_enabled_fn():
            return 400, {"ok": False, "error": "chat_login_disabled"}, {}

        users = chat_users_fn()
        username = normalize_user_id_fn(str(payload.get("username") or ""))
        pwd = str(payload.get("password") or "")
        expected = users.get(username, "")
        if username and expected and chat_password_matches_fn(expected, pwd):
            sid = new_chat_session_fn(username)
            return 200, {"ok": True, "message": "login_ok", "user_id": username}, {
                "Set-Cookie": f"nova_chat_session={sid}; Path=/; HttpOnly; SameSite=Strict"
            }
        return 403, {"ok": False, "error": "invalid_credentials"}, {}

    @staticmethod
    def chat_logout_action(handler, *, clear_chat_session_fn) -> tuple[int, dict, dict]:
        clear_chat_session_fn(handler)
        return 200, {"ok": True, "message": "logout_ok"}, {
            "Set-Cookie": "nova_chat_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
        }


CHAT_IDENTITY_SERVICE = ChatIdentityService()