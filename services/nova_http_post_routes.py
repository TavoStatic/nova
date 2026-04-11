from __future__ import annotations


class NovaHttpPostRoutesService:
    """Own basic POST-side HTTP route orchestration outside the transport handler."""

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


HTTP_POST_ROUTES_SERVICE = NovaHttpPostRoutesService()