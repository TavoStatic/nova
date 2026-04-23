from __future__ import annotations


class NovaHttpRequestBindingService:
    """Own HTTP chat request/session binding outside the transport handler."""

    @staticmethod
    def handle_resume_request(
        *,
        handler,
        qs: dict,
        payload: dict,
        chat_login_auth_fn,
        normalize_user_id_fn,
        request_user_id_fn,
        assert_session_owner_fn,
        resume_last_pending_turn_fn,
        invalidate_control_status_cache_fn,
    ) -> tuple[int, dict]:
        ok_chat, chat_user = chat_login_auth_fn(handler)
        if not ok_chat:
            return 403, {"ok": False, "error": chat_user}

        session_id = str(payload.get("session_id") or "").strip()
        user_id = normalize_user_id_fn(chat_user) or request_user_id_fn(handler, qs, payload)
        ok_owner, reason_owner = assert_session_owner_fn(session_id, user_id, allow_bind=False)
        if not ok_owner:
            return 403, {"ok": False, "error": reason_owner, "session_id": session_id}

        response_payload = resume_last_pending_turn_fn(session_id, user_id=user_id)
        code = 200 if response_payload.get("ok") else 400
        if response_payload.get("ok") and response_payload.get("resumed"):
            invalidate_control_status_cache_fn()
        return code, response_payload

    @staticmethod
    def handle_chat_request(
        *,
        handler,
        qs: dict,
        payload: dict,
        chat_login_auth_fn,
        normalize_user_id_fn,
        request_user_id_fn,
        assert_session_owner_fn,
        process_chat_fn,
        invalidate_control_status_cache_fn,
        token_hex_fn,
    ) -> tuple[int, dict]:
        ok_chat, chat_user = chat_login_auth_fn(handler)
        if not ok_chat:
            return 403, {"ok": False, "error": chat_user}

        message = str(payload.get("message") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        user_id = normalize_user_id_fn(chat_user) or request_user_id_fn(handler, qs, payload)
        if not session_id:
            session_id = token_hex_fn(8)

        if not message:
            return 400, {"ok": False, "error": "message_required", "session_id": session_id}

        ok_owner, reason_owner = assert_session_owner_fn(session_id, user_id, allow_bind=True)
        if not ok_owner:
            return 403, {"ok": False, "error": reason_owner, "session_id": session_id}

        try:
            reply = process_chat_fn(session_id, message, user_id=user_id)
        except Exception as exc:
            return 500, {"ok": False, "session_id": session_id, "error": f"chat_failed: {exc}"}

        invalidate_control_status_cache_fn()
        return 200, {"ok": True, "session_id": session_id, "reply": reply}


HTTP_REQUEST_BINDING_SERVICE = NovaHttpRequestBindingService()