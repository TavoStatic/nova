import unittest

from services.nova_http_transport import HTTP_TRANSPORT_SERVICE


class _Handler:
    def __init__(self, path: str):
        self.path = path


class _ResponseService:
    def __init__(self):
        self.basic_results = []
        self.post_results = []

    def emit_basic_route_result(self, handler, result, *, record_http_response_fn):
        self.basic_results.append((handler, result, record_http_response_fn))

    def emit_post_result(self, handler, result, *, record_http_response_fn):
        self.post_results.append((handler, result, record_http_response_fn))


class TestNovaHttpTransportService(unittest.TestCase):
    def test_handle_get_request_emits_basic_route_result(self):
        handler = _Handler("/api/health")
        response_service = _ResponseService()
        recorded = []

        HTTP_TRANSPORT_SERVICE.handle_get_request(
            handler,
            parse_request_path_fn=lambda path: (path, {}),
            basic_route_request_fn=lambda path, _handler: {"kind": "json", "code": 200, "body": {"ok": True}} if path == "/api/health" else None,
            chat_history_request_fn=lambda *_args: (200, {"ok": True}),
            control_api_request_fn=lambda *_args: None,
            json_response_fn=lambda *_args: self.fail("json_response_fn should not run when the basic route matches"),
            response_service=response_service,
            record_http_response_fn=recorded.append,
        )

        self.assertEqual(len(response_service.basic_results), 1)
        self.assertIs(response_service.basic_results[0][0], handler)
        self.assertEqual(response_service.basic_results[0][1], {"kind": "json", "code": 200, "body": {"ok": True}})

    def test_handle_get_request_routes_chat_history_through_json_response(self):
        handler = _Handler("/api/chat/history?session_id=s1")
        responses = []

        HTTP_TRANSPORT_SERVICE.handle_get_request(
            handler,
            parse_request_path_fn=lambda _path: ("/api/chat/history", {"session_id": ["s1"]}),
            basic_route_request_fn=lambda *_args: None,
            chat_history_request_fn=lambda _handler, qs: (200, {"ok": True, "session_id": qs["session_id"][0]}),
            control_api_request_fn=lambda *_args: None,
            json_response_fn=lambda _handler, code, payload: responses.append((code, payload)),
            response_service=_ResponseService(),
            record_http_response_fn=lambda _code: None,
        )

        self.assertEqual(responses, [(200, {"ok": True, "session_id": "s1"})])

    def test_handle_get_request_routes_control_api_through_json_response(self):
        handler = _Handler("/api/control/status")
        responses = []

        HTTP_TRANSPORT_SERVICE.handle_get_request(
            handler,
            parse_request_path_fn=lambda _path: ("/api/control/status", {}),
            basic_route_request_fn=lambda *_args: None,
            chat_history_request_fn=lambda *_args: (200, {"ok": True}),
            control_api_request_fn=lambda path, _qs: (200, {"ok": True, "path": path}),
            json_response_fn=lambda _handler, code, payload: responses.append((code, payload)),
            response_service=_ResponseService(),
            record_http_response_fn=lambda _code: None,
        )

        self.assertEqual(responses, [(200, {"ok": True, "path": "/api/control/status"})])

    def test_handle_post_request_dispatches_and_emits_result(self):
        handler = _Handler("/api/chat")
        response_service = _ResponseService()
        recorded = []

        HTTP_TRANSPORT_SERVICE.handle_post_request(
            handler,
            parse_request_path_fn=lambda _path: ("/api/chat", {}),
            dispatch_post_request_fn=lambda _handler, path, _qs: {"kind": "json", "code": 200, "body": {"ok": True, "path": path}},
            response_service=response_service,
            record_http_response_fn=recorded.append,
        )

        self.assertEqual(len(response_service.post_results), 1)
        self.assertIs(response_service.post_results[0][0], handler)
        self.assertEqual(response_service.post_results[0][1], {"kind": "json", "code": 200, "body": {"ok": True, "path": "/api/chat"}})