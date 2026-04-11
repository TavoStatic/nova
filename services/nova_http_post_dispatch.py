from __future__ import annotations

import json


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


HTTP_POST_DISPATCH_SERVICE = NovaHttpPostDispatchService()