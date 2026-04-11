from __future__ import annotations


class NovaHttpGetRoutesService:
    """Own GET-side HTTP chat-history and control API route orchestration."""

    @staticmethod
    def handle_basic_route_request(
        path: str,
        *,
        handler,
        control_login_enabled_fn,
        control_page_gate_fn,
        ollama_api_up_fn,
        chat_model_fn,
        memory_enabled_fn,
        chat_login_enabled_fn,
        index_html: str,
        control_login_html: str,
        control_html: str,
        control_css_path,
        control_js_path,
    ) -> dict | None:
        if path == "/":
            return {"kind": "text", "code": 200, "body": index_html}
        if path == "/static/control.css":
            return {"kind": "file", "code": 200, "path": control_css_path, "content_type": "text/css; charset=utf-8"}
        if path == "/static/control.js":
            return {"kind": "file", "code": 200, "path": control_js_path, "content_type": "application/javascript; charset=utf-8"}
        if path == "/control/login":
            if not control_login_enabled_fn():
                return {"kind": "json", "code": 404, "body": {"ok": False, "error": "control_login_disabled"}}
            ok_page, reason_page = control_page_gate_fn(handler)
            if not ok_page and reason_page != "control_login_required":
                return {"kind": "json", "code": 403, "body": {"ok": False, "error": reason_page}}
            return {"kind": "text", "code": 200, "body": control_login_html}
        if path == "/control":
            ok_page, reason_page = control_page_gate_fn(handler)
            if not ok_page:
                if reason_page == "control_login_required":
                    return {"kind": "text", "code": 200, "body": control_login_html}
                return {"kind": "json", "code": 403, "body": {"ok": False, "error": reason_page}}
            return {"kind": "text", "code": 200, "body": control_html}
        if path == "/api/health":
            return {
                "kind": "json",
                "code": 200,
                "body": {
                    "ok": True,
                    "ollama_api_up": bool(ollama_api_up_fn()),
                    "chat_model": chat_model_fn(),
                    "memory_enabled": bool(memory_enabled_fn()),
                    "chat_login_enabled": bool(chat_login_enabled_fn()),
                },
            }
        return None

    @staticmethod
    def handle_chat_history_request(
        *,
        handler,
        qs: dict,
        chat_login_auth_fn,
        normalize_user_id_fn,
        request_user_id_fn,
        assert_session_owner_fn,
        get_session_turns_fn,
        max_stored_turns_per_session: int,
    ) -> tuple[int, dict]:
        ok_chat, chat_user = chat_login_auth_fn(handler)
        if not ok_chat:
            return 403, {"ok": False, "error": chat_user}

        session_id = str((qs.get("session_id") or [""])[0]).strip()
        user_id = normalize_user_id_fn(chat_user) or request_user_id_fn(handler, qs)
        ok_owner, reason_owner = assert_session_owner_fn(session_id, user_id, allow_bind=False)
        if not ok_owner:
            return 403, {"ok": False, "error": reason_owner, "session_id": session_id}

        turns = get_session_turns_fn(session_id)
        return 200, {
            "ok": True,
            "session_id": session_id,
            "turns": [{"role": role, "text": text} for role, text in turns[-max(1, int(max_stored_turns_per_session)):]],
        }

    @staticmethod
    def handle_control_api_request(
        path: str,
        *,
        qs: dict,
        control_auth_fn,
        cached_control_status_payload_fn,
        control_policy_payload_fn,
        metrics_payload_fn,
        session_summaries_fn,
        test_session_report_summaries_fn,
        available_test_session_definitions_fn,
    ) -> tuple[int, dict] | None:
        if path not in {
            "/api/control/status",
            "/api/control/policy",
            "/api/control/metrics",
            "/api/control/sessions",
            "/api/control/test-sessions",
        }:
            return None

        ok, reason = control_auth_fn(qs)
        if not ok:
            return 403, {"ok": False, "error": reason}

        if path == "/api/control/status":
            return 200, cached_control_status_payload_fn()
        if path == "/api/control/policy":
            return 200, control_policy_payload_fn()
        if path == "/api/control/metrics":
            return 200, metrics_payload_fn()
        if path == "/api/control/sessions":
            return 200, {"ok": True, "sessions": session_summaries_fn(80)}
        return 200, {
            "ok": True,
            "reports": test_session_report_summaries_fn(24),
            "definitions": available_test_session_definitions_fn(80),
        }


HTTP_GET_ROUTES_SERVICE = NovaHttpGetRoutesService()