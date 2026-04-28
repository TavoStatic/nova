import unittest

from services.nova_http_request_binding import HTTP_REQUEST_BINDING_SERVICE


class _FakeAttachmentContext:
    def __init__(self):
        self.ingested = []
        self.remembered = []

    def ingest_items(self, session_id, user_id, items):
        self.ingested.append((session_id, user_id, list(items)))
        return [
            {
                "name": "note.txt",
                "original_name": "note.txt",
                "path": r"C:\Nova\runtime\leah_uploads\note.txt",
                "mime": "text/plain",
                "source": "upload",
                "bytes": 12,
            }
        ]

    def remember_session_context(self, session_id, items, *, stage):
        self.remembered.append((session_id, list(items), stage))

    def recent_session_context(self, session_id):
        return [], ""

    def maybe_answer_attachment_turn(self, message, attachments, *, recent_items=None, recent_stage=""):
        del recent_items, recent_stage
        if message == "can you read it?":
            return "Yes. I can read it directly."
        return None

    def compose_chat_message(self, message, attachments):
        return f"{message}\nATTACHMENTS={len(list(attachments or []))}"


class TestNovaHttpRequestBindingService(unittest.TestCase):
    def test_handle_chat_request_generates_session_and_invalidates_cache(self):
        invalidations = []

        code, payload = HTTP_REQUEST_BINDING_SERVICE.handle_chat_request(
            handler=object(),
            qs={},
            payload={"message": "hi nova", "user_id": "runner"},
            chat_login_auth_fn=lambda _handler: (True, "runner"),
            normalize_user_id_fn=lambda user: str(user or "").strip(),
            request_user_id_fn=lambda *_args, **_kwargs: "runner",
            assert_session_owner_fn=lambda *_args, **_kwargs: (True, "owner_bound"),
            process_chat_fn=lambda session_id, message, user_id="": f"{session_id}:{message}:{user_id}",
            invalidate_control_status_cache_fn=lambda: invalidations.append("invalidated"),
            token_hex_fn=lambda _size: "abc12345",
        )

        self.assertEqual(code, 200)
        self.assertEqual(payload.get("session_id"), "abc12345")
        self.assertEqual(payload.get("reply"), "abc12345:hi nova:runner")
        self.assertEqual(invalidations, ["invalidated"])

    def test_handle_resume_request_invalidates_only_when_resumed(self):
        invalidations = []

        code, payload = HTTP_REQUEST_BINDING_SERVICE.handle_resume_request(
            handler=object(),
            qs={},
            payload={"session_id": "resume-123", "user_id": "runner"},
            chat_login_auth_fn=lambda _handler: (True, "runner"),
            normalize_user_id_fn=lambda user: str(user or "").strip(),
            request_user_id_fn=lambda *_args, **_kwargs: "runner",
            assert_session_owner_fn=lambda *_args, **_kwargs: (True, "owner_bound"),
            resume_last_pending_turn_fn=lambda session_id, user_id="": {"ok": True, "resumed": True, "session_id": session_id, "user_id": user_id},
            invalidate_control_status_cache_fn=lambda: invalidations.append("invalidated"),
        )

        self.assertEqual(code, 200)
        self.assertTrue(payload.get("resumed"))
        self.assertEqual(payload.get("session_id"), "resume-123")
        self.assertEqual(payload.get("user_id"), "runner")
        self.assertEqual(invalidations, ["invalidated"])

    def test_handle_upload_request_stages_items(self):
        attachment_context = _FakeAttachmentContext()

        code, payload = HTTP_REQUEST_BINDING_SERVICE.handle_upload_request(
            handler=object(),
            qs={},
            payload={"items": [{"name": "note.txt", "content_b64": "aGVsbG8="}]},
            chat_login_auth_fn=lambda _handler: (True, "runner"),
            normalize_user_id_fn=lambda user: str(user or "").strip(),
            request_user_id_fn=lambda *_args, **_kwargs: "runner",
            assert_session_owner_fn=lambda *_args, **_kwargs: (True, "owner_bound"),
            token_hex_fn=lambda _size: "upload123",
            attachment_context_service=attachment_context,
        )

        self.assertEqual(code, 200)
        self.assertEqual(payload.get("session_id"), "upload123")
        self.assertEqual(len(payload.get("items") or []), 1)
        self.assertEqual(attachment_context.remembered[0][2], "staged")

    def test_handle_upload_request_from_runtime_resolves_scope(self):
        attachment_context = _FakeAttachmentContext()

        code, payload = HTTP_REQUEST_BINDING_SERVICE.handle_upload_request_from_runtime(
            handler=object(),
            qs={},
            payload={"items": [{"name": "note.txt", "content_b64": "aGVsbG8="}]},
            runtime_scope={
                "_chat_login_auth": lambda _handler: (True, "runner"),
                "_normalize_user_id": lambda user: str(user or "").strip(),
                "_request_user_id": lambda *_args, **_kwargs: "runner",
                "_assert_session_owner": lambda *_args, **_kwargs: (True, "owner_bound"),
                "secrets": type("_Secrets", (), {"token_hex": staticmethod(lambda _size: "upload123")})(),
                "LEAH_FRONTDOOR_SERVICE": attachment_context,
            },
        )

        self.assertEqual(code, 200)
        self.assertEqual(payload.get("session_id"), "upload123")
        self.assertEqual(attachment_context.remembered[0][2], "staged")

    def test_handle_chat_request_direct_attachment_reply_uses_attachment_context(self):
        invalidations = []
        appended_turns = []
        attachment_context = _FakeAttachmentContext()

        code, payload = HTTP_REQUEST_BINDING_SERVICE.handle_chat_request(
            handler=object(),
            qs={},
            payload={
                "message": "can you read it?",
                "session_id": "attach123",
                "user_id": "runner",
                "attachments": [{"name": "note.txt", "path": r"C:\Nova\runtime\leah_uploads\note.txt"}],
            },
            chat_login_auth_fn=lambda _handler: (True, "runner"),
            normalize_user_id_fn=lambda user: str(user or "").strip(),
            request_user_id_fn=lambda *_args, **_kwargs: "runner",
            assert_session_owner_fn=lambda *_args, **_kwargs: (True, "owner_bound"),
            process_chat_fn=lambda *_args, **_kwargs: "should not run",
            invalidate_control_status_cache_fn=lambda: invalidations.append("invalidated"),
            token_hex_fn=lambda _size: "unused",
            attachment_context_service=attachment_context,
            append_session_turn_fn=lambda session_id, role, text: appended_turns.append((session_id, role, text)),
        )

        self.assertEqual(code, 200)
        self.assertEqual(payload.get("reply"), "Yes. I can read it directly.")
        self.assertEqual(invalidations, ["invalidated"])
        self.assertEqual(
            appended_turns,
            [
                ("attach123", "user", "can you read it?"),
                ("attach123", "assistant", "Yes. I can read it directly."),
            ],
        )
        self.assertEqual(attachment_context.remembered[0][2], "handoff")

    def test_handle_chat_request_from_runtime_resolves_scope(self):
        invalidations = []

        code, payload = HTTP_REQUEST_BINDING_SERVICE.handle_chat_request_from_runtime(
            handler=object(),
            qs={},
            payload={"message": "hi nova", "user_id": "runner"},
            runtime_scope={
                "_chat_login_auth": lambda _handler: (True, "runner"),
                "_normalize_user_id": lambda user: str(user or "").strip(),
                "_request_user_id": lambda *_args, **_kwargs: "runner",
                "_assert_session_owner": lambda *_args, **_kwargs: (True, "owner_bound"),
                "process_chat": lambda session_id, message, user_id="": f"{session_id}:{message}:{user_id}",
                "_invalidate_control_status_cache": lambda: invalidations.append("invalidated"),
                "LEAH_FRONTDOOR_SERVICE": _FakeAttachmentContext(),
                "_append_session_turn": lambda *_args, **_kwargs: None,
            },
        )

        self.assertEqual(code, 200)
        self.assertEqual(payload.get("reply"), f"{payload.get('session_id')}:hi nova:runner")
        self.assertEqual(invalidations, ["invalidated"])


if __name__ == "__main__":
    unittest.main()
