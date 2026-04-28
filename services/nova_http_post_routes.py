from __future__ import annotations

from services.nova_http_request_binding import HTTP_REQUEST_BINDING_SERVICE


class NovaHttpPostRoutesService:
    """Own basic POST-side HTTP route orchestration outside the transport handler."""

    @staticmethod
    def _runtime_fn(runtime_scope: dict[str, object], name: str):
        return runtime_scope[name]

    @staticmethod
    def handle_basic_post_route(
        path: str,
        *,
        handler,
        qs: dict,
        payload: dict,
        control_login_action_fn,
        control_logout_action_fn,
        chat_login_action_fn,
        chat_logout_action_fn,
        chat_upload_action_fn=None,
        control_auth_fn,
        control_action_fn,
    ) -> dict | None:
        if path == "/api/control/login":
            code, response_payload, response_headers = control_login_action_fn(payload)
            return {"kind": "with_headers", "code": code, "body": response_payload, "headers": response_headers}

        if path == "/api/control/logout":
            code, response_payload, response_headers = control_logout_action_fn(handler)
            return {"kind": "with_headers", "code": code, "body": response_payload, "headers": response_headers}

        if path == "/api/chat/login":
            code, response_payload, response_headers = chat_login_action_fn(payload)
            return {"kind": "with_headers", "code": code, "body": response_payload, "headers": response_headers}

        if path == "/api/chat/logout":
            code, response_payload, response_headers = chat_logout_action_fn(handler)
            return {"kind": "with_headers", "code": code, "body": response_payload, "headers": response_headers}

        if path == "/api/chat/upload":
            if chat_upload_action_fn is None:
                return {"kind": "json", "code": 501, "body": {"ok": False, "error": "chat_upload_unavailable"}}
            code, response_payload = chat_upload_action_fn(handler, qs, payload)
            return {"kind": "json", "code": code, "body": response_payload}

        if path != "/api/control/action":
            return None

        ok, reason = control_auth_fn(handler, qs)
        if not ok:
            return {"kind": "json", "code": 403, "body": {"ok": False, "error": reason}}

        success, msg, extra = control_action_fn(str(payload.get("action") or ""), payload)
        code = 200 if success else 400
        body = {"ok": bool(success), "message": msg}
        if extra:
            body.update(extra)
        return {"kind": "json", "code": code, "body": body}

    @staticmethod
    def handle_basic_post_route_from_runtime(
        path: str,
        *,
        handler,
        qs: dict,
        payload: dict,
        runtime_scope: dict[str, object],
    ) -> dict | None:
        runtime_fn = NovaHttpPostRoutesService._runtime_fn
        return NovaHttpPostRoutesService.handle_basic_post_route(
            path,
            handler=handler,
            qs=qs,
            payload=payload,
            control_login_action_fn=runtime_fn(runtime_scope, "_control_login_action"),
            control_logout_action_fn=runtime_fn(runtime_scope, "_control_logout_action"),
            chat_login_action_fn=runtime_fn(runtime_scope, "_chat_login_action"),
            chat_logout_action_fn=runtime_fn(runtime_scope, "_chat_logout_action"),
            chat_upload_action_fn=lambda handler_, qs_, payload_: HTTP_REQUEST_BINDING_SERVICE.handle_upload_request_from_runtime(
                handler=handler_,
                qs=qs_,
                payload=payload_,
                runtime_scope=runtime_scope,
            ),
            control_auth_fn=runtime_fn(runtime_scope, "_control_auth"),
            control_action_fn=runtime_fn(runtime_scope, "_control_action"),
        )


HTTP_POST_ROUTES_SERVICE = NovaHttpPostRoutesService()
