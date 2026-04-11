from __future__ import annotations


class SessionAdminService:
    """Own session deletion and chat-user admin orchestration outside the HTTP layer."""

    @staticmethod
    def delete_session(
        session_id: str,
        *,
        session_lock,
        delete_session_fn,
        session_turns,
        session_owners,
        state_manager,
        persist_callback,
        on_session_end,
    ) -> tuple[bool, str]:
        with session_lock:
            return delete_session_fn(
                session_id,
                session_turns=session_turns,
                session_owners=session_owners,
                state_manager=state_manager,
                persist_callback=persist_callback,
                on_session_end=on_session_end,
            )

    @staticmethod
    def chat_auth_payload(*, chat_users_fn, chat_auth_source_fn, chat_users_path_fn) -> dict:
        users = chat_users_fn()
        return {
            "enabled": bool(users),
            "source": chat_auth_source_fn(),
            "count": len(users),
            "users": sorted(users.keys()),
            "managed_path": str(chat_users_path_fn()),
        }

    @staticmethod
    def chat_user_upsert(username: str, password: str, *, normalize_user_id_fn, chat_users_fn, save_managed_chat_users_fn) -> tuple[bool, str]:
        user = normalize_user_id_fn(username)
        pwd = str(password or "")
        if not user:
            return False, "username_required"
        if not pwd:
            return False, "password_required"
        users = dict(chat_users_fn())
        users[user] = pwd
        save_managed_chat_users_fn(users)
        return True, f"chat_user_saved:{user}"

    @staticmethod
    def chat_user_delete(username: str, *, normalize_user_id_fn, chat_users_fn, save_managed_chat_users_fn) -> tuple[bool, str]:
        user = normalize_user_id_fn(username)
        if not user:
            return False, "username_required"
        users = dict(chat_users_fn())
        if user not in users:
            return False, "chat_user_not_found"
        users.pop(user, None)
        save_managed_chat_users_fn(users)
        return True, f"chat_user_deleted:{user}"

    @staticmethod
    def session_delete_action(payload: dict, *, delete_session_fn, session_summaries_fn) -> tuple[bool, str, dict, str]:
        ok, msg = delete_session_fn(str(payload.get("session_id") or ""))
        return ok, msg, {"sessions": session_summaries_fn(80)}, msg

    @staticmethod
    def chat_user_list_action(*, chat_auth_payload_fn) -> tuple[bool, str, dict, str]:
        msg = "chat_user_list_ok"
        return True, msg, {"chat_auth": chat_auth_payload_fn()}, msg

    @staticmethod
    def chat_user_upsert_action(payload: dict, *, chat_user_upsert_fn, chat_auth_payload_fn) -> tuple[bool, str, dict, str]:
        ok, msg = chat_user_upsert_fn(str(payload.get("username") or ""), str(payload.get("password") or ""))
        return ok, msg, {"chat_auth": chat_auth_payload_fn()}, msg

    @staticmethod
    def chat_user_delete_action(payload: dict, *, chat_user_delete_fn, chat_auth_payload_fn) -> tuple[bool, str, dict, str]:
        ok, msg = chat_user_delete_fn(str(payload.get("username") or ""))
        return ok, msg, {"chat_auth": chat_auth_payload_fn()}, msg


SESSION_ADMIN_SERVICE = SessionAdminService()