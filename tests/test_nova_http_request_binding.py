import unittest

from services.nova_http_request_binding import HTTP_REQUEST_BINDING_SERVICE


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


if __name__ == "__main__":
    unittest.main()