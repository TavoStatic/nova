from __future__ import annotations

import json

from services.nova_http_post_routes import HTTP_POST_ROUTES_SERVICE
from services.nova_http_request_binding import HTTP_REQUEST_BINDING_SERVICE


class NovaHttpPostDispatchService:
    """Own POST-side route gating, JSON decode, and high-level dispatch outside the transport shell."""

    @staticmethod
    def handle_post_request(
        *,
        handler,
        path: str,
        qs: dict,
        basic_post_route_fn,
        handle_resume_request_fn,
        handle_chat_request_fn,
    ) -> dict:
        allowed_paths = {
            "/api/chat",
            "/api/chat/resume",
            "/api/chat/login",
            "/api/chat/logout",
            "/api/chat/upload",
            "/api/control/action",
            "/api/control/login",
            "/api/control/logout",
        }
        if path not in allowed_paths:
            return {"kind": "json", "code": 404, "body": {"ok": False, "error": "not_found"}}

        length = int(handler.headers.get("Content-Length", "0") or "0")
        raw = handler.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {"kind": "json", "code": 400, "body": {"ok": False, "error": "invalid_json"}}

        basic_result = basic_post_route_fn(handler, path, qs, payload)
        if basic_result is not None:
            return basic_result

        if path == "/api/chat/resume":
            code, response_payload = handle_resume_request_fn(handler, qs, payload)
            return {"kind": "json", "code": code, "body": response_payload}

        code, response_payload = handle_chat_request_fn(handler, qs, payload)
        return {"kind": "json", "code": code, "body": response_payload}

    @staticmethod
    def handle_post_request_from_runtime(
        *,
        handler,
        path: str,
        qs: dict,
        runtime_scope: dict[str, object],
    ) -> dict:
        return NovaHttpPostDispatchService.handle_post_request(
            handler=handler,
            path=path,
            qs=qs,
            basic_post_route_fn=lambda handler_, path_, qs_, payload_: HTTP_POST_ROUTES_SERVICE.handle_basic_post_route_from_runtime(
                path_,
                handler=handler_,
                qs=qs_,
                payload=payload_,
                runtime_scope=runtime_scope,
            ),
            handle_resume_request_fn=lambda handler_, qs_, payload_: HTTP_REQUEST_BINDING_SERVICE.handle_resume_request_from_runtime(
                handler=handler_,
                qs=qs_,
                payload=payload_,
                runtime_scope=runtime_scope,
            ),
            handle_chat_request_fn=lambda handler_, qs_, payload_: HTTP_REQUEST_BINDING_SERVICE.handle_chat_request_from_runtime(
                handler=handler_,
                qs=qs_,
                payload=payload_,
                runtime_scope=runtime_scope,
            ),
        )


HTTP_POST_DISPATCH_SERVICE = NovaHttpPostDispatchService()
