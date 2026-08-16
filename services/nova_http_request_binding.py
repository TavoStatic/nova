from __future__ import annotations

import secrets


class NovaHttpRequestBindingService:
    """Own HTTP chat request/session binding outside the transport handler."""

    @staticmethod
    def _runtime_fn(runtime_scope: dict[str, object], name: str):
        return runtime_scope[name]

    @staticmethod
    def _normalize_attachment_items(items) -> list[dict]:
        return [dict(item or {}) for item in list(items or []) if isinstance(item, dict)]

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
        attachment_context_service=None,
        append_session_turn_fn=None,
        memory_recall_service=None,
    ) -> tuple[int, dict]:
        ok_chat, chat_user = chat_login_auth_fn(handler)
        if not ok_chat:
            return 403, {"ok": False, "error": chat_user}

        message = str(payload.get("message") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        user_id = normalize_user_id_fn(chat_user) or request_user_id_fn(handler, qs, payload)
        attachments = NovaHttpRequestBindingService._normalize_attachment_items(payload.get("attachments"))
        if not session_id:
            session_id = token_hex_fn(8)

        if not message and not attachments:
            return 400, {"ok": False, "error": "message_required", "session_id": session_id}

        ok_owner, reason_owner = assert_session_owner_fn(session_id, user_id, allow_bind=True)
        if not ok_owner:
            return 403, {"ok": False, "error": reason_owner, "session_id": session_id}

        if attachments and attachment_context_service is not None:
            attachment_context_service.remember_session_context(session_id, attachments, stage="handoff")
            message = attachment_context_service.compose_chat_message(message, attachments)
        elif attachment_context_service is not None:
            # No live attachments in this turn — recover staged context from the store.
            # This is the post-navigation path: browser JS staged list is empty but the
            # server-side store still holds what the operator uploaded before navigating away.
            try:
                recovered_items, _stage = attachment_context_service.recent_session_context(session_id)
                if recovered_items:
                    message = attachment_context_service.compose_chat_message(message, recovered_items)
            except Exception:
                pass  # store failure must never break a chat turn

        if memory_recall_service is not None:
            try:
                recall_ctx = memory_recall_service.recall_for_turn(message)
                message = memory_recall_service.inject_into_message(message, recall_ctx)
            except Exception:
                pass  # recall failure must never break a chat turn

        try:
            reply = process_chat_fn(session_id, message, user_id=user_id)
        except Exception as exc:
            return 500, {"ok": False, "session_id": session_id, "error": f"chat_failed: {exc}"}

        invalidate_control_status_cache_fn()
        return 200, {"ok": True, "session_id": session_id, "reply": reply}

    @staticmethod
    def handle_upload_request(
        *,
        handler,
        qs: dict,
        payload: dict,
        chat_login_auth_fn,
        normalize_user_id_fn,
        request_user_id_fn,
        assert_session_owner_fn,
        token_hex_fn,
        attachment_context_service,
    ) -> tuple[int, dict]:
        ok_chat, chat_user = chat_login_auth_fn(handler)
        if not ok_chat:
            return 403, {"ok": False, "error": chat_user}

        session_id = str(payload.get("session_id") or "").strip() or token_hex_fn(8)
        user_id = normalize_user_id_fn(chat_user) or request_user_id_fn(handler, qs, payload)
        ok_owner, reason_owner = assert_session_owner_fn(session_id, user_id, allow_bind=True)
        if not ok_owner:
            return 403, {"ok": False, "error": reason_owner, "session_id": session_id}

        items = NovaHttpRequestBindingService._normalize_attachment_items(payload.get("items"))
        if not items:
            return 400, {"ok": False, "error": "items_required", "session_id": session_id}

        stored = attachment_context_service.ingest_items(session_id, user_id, items)
        if not stored:
            return 400, {"ok": False, "error": "items_rejected", "session_id": session_id}

        attachment_context_service.remember_session_context(session_id, stored, stage="staged")
        return 200, {"ok": True, "session_id": session_id, "items": stored}

    @staticmethod
    def handle_upload_request_from_runtime(
        *,
        handler,
        qs: dict,
        payload: dict,
        runtime_scope: dict[str, object],
    ) -> tuple[int, dict]:
        runtime_fn = NovaHttpRequestBindingService._runtime_fn
        return NovaHttpRequestBindingService.handle_upload_request(
            handler=handler,
            qs=qs,
            payload=payload,
            chat_login_auth_fn=runtime_fn(runtime_scope, "_chat_login_auth"),
            normalize_user_id_fn=runtime_fn(runtime_scope, "_normalize_user_id"),
            request_user_id_fn=runtime_fn(runtime_scope, "_request_user_id"),
            assert_session_owner_fn=runtime_fn(runtime_scope, "_assert_session_owner"),
            token_hex_fn=runtime_fn(runtime_scope, "secrets").token_hex,
            attachment_context_service=runtime_fn(runtime_scope, "LEAH_FRONTDOOR_SERVICE"),
        )

    @staticmethod
    def handle_resume_request_from_runtime(
        *,
        handler,
        qs: dict,
        payload: dict,
        runtime_scope: dict[str, object],
    ) -> tuple[int, dict]:
        runtime_fn = NovaHttpRequestBindingService._runtime_fn
        return NovaHttpRequestBindingService.handle_resume_request(
            handler=handler,
            qs=qs,
            payload=payload,
            chat_login_auth_fn=runtime_fn(runtime_scope, "_chat_login_auth"),
            normalize_user_id_fn=runtime_fn(runtime_scope, "_normalize_user_id"),
            request_user_id_fn=runtime_fn(runtime_scope, "_request_user_id"),
            assert_session_owner_fn=runtime_fn(runtime_scope, "_assert_session_owner"),
            resume_last_pending_turn_fn=runtime_fn(runtime_scope, "resume_last_pending_turn"),
            invalidate_control_status_cache_fn=runtime_fn(runtime_scope, "_invalidate_control_status_cache"),
        )

    @staticmethod
    def handle_chat_request_from_runtime(
        *,
        handler,
        qs: dict,
        payload: dict,
        runtime_scope: dict[str, object],
    ) -> tuple[int, dict]:
        runtime_fn = NovaHttpRequestBindingService._runtime_fn
        return NovaHttpRequestBindingService.handle_chat_request(
            handler=handler,
            qs=qs,
            payload=payload,
            chat_login_auth_fn=runtime_fn(runtime_scope, "_chat_login_auth"),
            normalize_user_id_fn=runtime_fn(runtime_scope, "_normalize_user_id"),
            request_user_id_fn=runtime_fn(runtime_scope, "_request_user_id"),
            assert_session_owner_fn=runtime_fn(runtime_scope, "_assert_session_owner"),
            process_chat_fn=runtime_fn(runtime_scope, "process_chat"),
            invalidate_control_status_cache_fn=runtime_fn(runtime_scope, "_invalidate_control_status_cache"),
            token_hex_fn=secrets.token_hex,
            attachment_context_service=runtime_fn(runtime_scope, "LEAH_FRONTDOOR_SERVICE"),
            append_session_turn_fn=runtime_fn(runtime_scope, "_append_session_turn"),
            memory_recall_service=runtime_fn(runtime_scope, "LEAH_MEMORY_RECALL_SERVICE"),
        )


HTTP_REQUEST_BINDING_SERVICE = NovaHttpRequestBindingService()
