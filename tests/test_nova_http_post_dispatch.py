import io
import unittest

from services.nova_http_post_dispatch import HTTP_POST_DISPATCH_SERVICE


class _Handler:
    def __init__(self, body: bytes):
        self.headers = {"Content-Length": str(len(body))}
        self.rfile = io.BytesIO(body)


class TestNovaHttpPostDispatchService(unittest.TestCase):
    def test_handle_post_request_returns_not_found_for_unknown_path(self):
        handler = _Handler(b"{}")

        result = HTTP_POST_DISPATCH_SERVICE.handle_post_request(
            handler=handler,
            path="/api/unknown",
            qs={},
            basic_post_route_fn=lambda *_args: None,
            handle_resume_request_fn=lambda *_args: (200, {"ok": True}),
            handle_chat_request_fn=lambda *_args: (200, {"ok": True}),
        )

        self.assertEqual(result, {"kind": "json", "code": 404, "body": {"ok": False, "error": "not_found"}})

    def test_handle_post_request_returns_invalid_json_error(self):
        handler = _Handler(b"{bad")

        result = HTTP_POST_DISPATCH_SERVICE.handle_post_request(
            handler=handler,
            path="/api/chat",
            qs={},
            basic_post_route_fn=lambda *_args: None,
            handle_resume_request_fn=lambda *_args: (200, {"ok": True}),
            handle_chat_request_fn=lambda *_args: (200, {"ok": True}),
        )

        self.assertEqual(result, {"kind": "json", "code": 400, "body": {"ok": False, "error": "invalid_json"}})

    def test_handle_post_request_dispatches_resume(self):
        handler = _Handler(b'{"session_id":"s1"}')

        result = HTTP_POST_DISPATCH_SERVICE.handle_post_request(
            handler=handler,
            path="/api/chat/resume",
            qs={},
            basic_post_route_fn=lambda *_args: None,
            handle_resume_request_fn=lambda _handler, _qs, payload: (200, {"ok": True, "session_id": payload.get("session_id")}),
            handle_chat_request_fn=lambda *_args: (200, {"ok": True}),
        )

        self.assertEqual(result, {"kind": "json", "code": 200, "body": {"ok": True, "session_id": "s1"}})

    def test_handle_post_request_returns_basic_route_result_when_present(self):
        handler = _Handler(b'{"username":"gus"}')

        result = HTTP_POST_DISPATCH_SERVICE.handle_post_request(
            handler=handler,
            path="/api/chat/login",
            qs={},
            basic_post_route_fn=lambda _handler, path, _qs, payload: {"kind": "with_headers", "code": 200, "body": {"ok": True, "user": payload.get("username")}, "headers": {"Set-Cookie": "x=y"}} if path == "/api/chat/login" else None,
            handle_resume_request_fn=lambda *_args: (200, {"ok": True}),
            handle_chat_request_fn=lambda *_args: (200, {"ok": True}),
        )

        self.assertEqual(result, {"kind": "with_headers", "code": 200, "body": {"ok": True, "user": "gus"}, "headers": {"Set-Cookie": "x=y"}})