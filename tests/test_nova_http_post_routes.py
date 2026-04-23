import unittest

from services.nova_http_post_routes import HTTP_POST_ROUTES_SERVICE


class TestNovaHttpPostRoutesService(unittest.TestCase):
    def test_handle_basic_post_route_returns_header_response_for_chat_login(self):
        result = HTTP_POST_ROUTES_SERVICE.handle_basic_post_route(
            "/api/chat/login",
            handler=object(),
            qs={},
            payload={"username": "gus", "password": "secret"},
            control_login_action_fn=lambda payload: (200, payload, {}),
            control_logout_action_fn=lambda handler: (200, {"ok": True}, {}),
            chat_login_action_fn=lambda payload: (200, {"ok": True, "user_id": payload.get("username")}, {"Set-Cookie": "nova_chat_session=x"}),
            chat_logout_action_fn=lambda handler: (200, {"ok": True}, {}),
            control_auth_fn=lambda handler, qs: (True, ""),
            control_action_fn=lambda action, payload: (True, action, {}),
        )

        self.assertEqual(
            result,
            {"kind": "with_headers", "code": 200, "body": {"ok": True, "user_id": "gus"}, "headers": {"Set-Cookie": "nova_chat_session=x"}},
        )

    def test_handle_basic_post_route_enforces_control_auth_for_actions(self):
        result = HTTP_POST_ROUTES_SERVICE.handle_basic_post_route(
            "/api/control/action",
            handler=object(),
            qs={},
            payload={"action": "refresh_status"},
            control_login_action_fn=lambda payload: (200, payload, {}),
            control_logout_action_fn=lambda handler: (200, {"ok": True}, {}),
            chat_login_action_fn=lambda payload: (200, payload, {}),
            chat_logout_action_fn=lambda handler: (200, {"ok": True}, {}),
            control_auth_fn=lambda handler, qs: (False, "denied"),
            control_action_fn=lambda action, payload: (True, action, {}),
        )

        self.assertEqual(result, {"kind": "json", "code": 403, "body": {"ok": False, "error": "denied"}})

    def test_handle_basic_post_route_shapes_control_action_payload(self):
        result = HTTP_POST_ROUTES_SERVICE.handle_basic_post_route(
            "/api/control/action",
            handler=object(),
            qs={},
            payload={"action": "refresh_status"},
            control_login_action_fn=lambda payload: (200, payload, {}),
            control_logout_action_fn=lambda handler: (200, {"ok": True}, {}),
            chat_login_action_fn=lambda payload: (200, payload, {}),
            chat_logout_action_fn=lambda handler: (200, {"ok": True}, {}),
            control_auth_fn=lambda handler, qs: (True, ""),
            control_action_fn=lambda action, payload: (True, "refresh_ok", {"status": "fresh"}),
        )

        self.assertEqual(result, {"kind": "json", "code": 200, "body": {"ok": True, "message": "refresh_ok", "status": "fresh"}})