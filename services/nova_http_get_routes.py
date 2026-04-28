from __future__ import annotations


class NovaHttpGetRoutesService:
    """Own GET-side HTTP chat-history and control API route orchestration."""

    @staticmethod
    def _runtime_fn(runtime_scope: dict[str, object], name: str):
        return runtime_scope[name]

    @staticmethod
    def handle_basic_route_request(
        path: str,
        *,
        handler,
        public_renderers: dict[str, callable] | None = None,
        static_routes: dict[str, tuple[object, str]] | None = None,
        control_login_enabled_fn,
        control_page_gate_fn,
        render_control_login_html_fn=None,
        render_control_html_fn=None,
        health_payload_fn=None,
        ollama_api_up_fn=None,
        chat_model_fn=None,
        memory_enabled_fn=None,
        chat_login_enabled_fn=None,
        index_html: str = "",
        control_login_html: str = "",
        control_html: str = "",
        control_css_path=None,
        control_js_path=None,
    ) -> dict | None:
        public_renderers = dict(public_renderers or {})
        static_routes = dict(static_routes or {})
        if not public_renderers and index_html:
            public_renderers["/"] = lambda: index_html
        if not static_routes:
            if control_css_path is not None:
                static_routes["/static/control.css"] = (control_css_path, "text/css; charset=utf-8")
            if control_js_path is not None:
                static_routes["/static/control.js"] = (control_js_path, "application/javascript; charset=utf-8")
        render_control_login_html_fn = render_control_login_html_fn or (lambda: control_login_html)
        render_control_html_fn = render_control_html_fn or (lambda: control_html)
        if health_payload_fn is None:
            health_payload_fn = lambda: {
                "ok": True,
                "ollama_api_up": bool(ollama_api_up_fn()),
                "chat_model": chat_model_fn(),
                "memory_enabled": bool(memory_enabled_fn()),
                "chat_login_enabled": bool(chat_login_enabled_fn()),
            }

        if path in public_renderers:
            return {"kind": "text", "code": 200, "body": public_renderers[path]()}
        if path in static_routes:
            asset_path, content_type = static_routes[path]
            return {"kind": "file", "code": 200, "path": asset_path, "content_type": content_type}
        if path == "/control/login":
            if not control_login_enabled_fn():
                return {"kind": "json", "code": 404, "body": {"ok": False, "error": "control_login_disabled"}}
            ok_page, reason_page = control_page_gate_fn(handler)
            if not ok_page and reason_page != "control_login_required":
                return {"kind": "json", "code": 403, "body": {"ok": False, "error": reason_page}}
            return {"kind": "text", "code": 200, "body": render_control_login_html_fn()}
        if path == "/control":
            ok_page, reason_page = control_page_gate_fn(handler)
            if not ok_page:
                if reason_page == "control_login_required":
                    return {"kind": "text", "code": 200, "body": render_control_login_html_fn()}
                return {"kind": "json", "code": 403, "body": {"ok": False, "error": reason_page}}
            return {"kind": "text", "code": 200, "body": render_control_html_fn()}
        if path == "/api/health":
            return {"kind": "json", "code": 200, "body": health_payload_fn()}
        return None

    @staticmethod
    def handle_chat_history_request(
        path: str,
        *,
        handler,
        qs: dict,
        chat_login_auth_fn,
        normalize_user_id_fn,
        request_user_id_fn,
        assert_session_owner_fn,
        get_session_turns_fn,
        max_stored_turns_per_session: int,
    ) -> tuple[int, dict] | None:
        if path != "/api/chat/history":
            return None

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
    def handle_basic_route_request_from_runtime(
        path: str,
        *,
        handler,
        runtime_scope: dict[str, object],
    ) -> dict | None:
        runtime_fn = NovaHttpGetRoutesService._runtime_fn
        frontdoor_service = runtime_fn(runtime_scope, "NOVA_HTTP_FRONTDOOR_SERVICE")
        return NovaHttpGetRoutesService.handle_basic_route_request(
            path,
            handler=handler,
            public_renderers=frontdoor_service.public_surface_renderers_from_runtime(runtime_scope),
            static_routes=frontdoor_service.static_asset_routes_from_runtime(runtime_scope),
            control_login_enabled_fn=runtime_fn(runtime_scope, "_control_login_enabled"),
            control_page_gate_fn=runtime_fn(runtime_scope, "_control_page_gate"),
            render_control_login_html_fn=runtime_fn(runtime_scope, "_render_control_login_html"),
            render_control_html_fn=runtime_fn(runtime_scope, "_render_control_html"),
            health_payload_fn=runtime_fn(runtime_scope, "_health_payload"),
        )

    @staticmethod
    def handle_chat_history_request_from_runtime(
        *,
        handler,
        qs: dict,
        runtime_scope: dict[str, object],
    ) -> tuple[int, dict]:
        runtime_fn = NovaHttpGetRoutesService._runtime_fn
        result = NovaHttpGetRoutesService.handle_chat_history_request(
            "/api/chat/history",
            handler=handler,
            qs=qs,
            chat_login_auth_fn=runtime_fn(runtime_scope, "_chat_login_auth"),
            normalize_user_id_fn=runtime_fn(runtime_scope, "_normalize_user_id"),
            request_user_id_fn=runtime_fn(runtime_scope, "_request_user_id"),
            assert_session_owner_fn=runtime_fn(runtime_scope, "_assert_session_owner"),
            get_session_turns_fn=runtime_fn(runtime_scope, "_get_session_turns"),
            max_stored_turns_per_session=int(runtime_fn(runtime_scope, "MAX_STORED_TURNS_PER_SESSION")),
        )
        return result or (404, {"ok": False, "error": "not_found"})

    @staticmethod
    def handle_control_api_request(
        path: str,
        *,
        handler=None,
        qs: dict,
        control_auth_fn,
        cached_control_status_payload_fn,
        control_policy_payload_fn,
        metrics_payload_fn,
        work_trees_payload_fn,
        session_summaries_fn,
        test_session_report_summaries_fn,
        available_test_session_definitions_fn,
    ) -> tuple[int, dict] | None:
        if path not in {
            "/api/control/status",
            "/api/control/policy",
            "/api/control/metrics",
            "/api/control/work-trees",
            "/api/control/sessions",
            "/api/control/test-sessions",
        }:
            return None

        if handler is None:
            ok, reason = control_auth_fn(qs)
        else:
            ok, reason = control_auth_fn(handler, qs)
        if not ok:
            return 403, {"ok": False, "error": reason}

        if path == "/api/control/status":
            return 200, cached_control_status_payload_fn()
        if path == "/api/control/policy":
            return 200, control_policy_payload_fn()
        if path == "/api/control/metrics":
            return 200, metrics_payload_fn()
        if path == "/api/control/work-trees":
            return 200, work_trees_payload_fn()
        if path == "/api/control/sessions":
            return 200, {"ok": True, "sessions": session_summaries_fn(80)}
        return 200, {
            "ok": True,
            "reports": test_session_report_summaries_fn(24),
            "definitions": available_test_session_definitions_fn(80),
        }

    @staticmethod
    def handle_control_api_request_from_runtime(
        path: str,
        *,
        handler,
        qs: dict,
        runtime_scope: dict[str, object],
    ) -> tuple[int, dict] | None:
        runtime_fn = NovaHttpGetRoutesService._runtime_fn
        return NovaHttpGetRoutesService.handle_control_api_request(
            path,
            handler=handler,
            qs=qs,
            control_auth_fn=runtime_fn(runtime_scope, "_control_auth"),
            cached_control_status_payload_fn=runtime_fn(runtime_scope, "_cached_control_status_payload"),
            control_policy_payload_fn=runtime_fn(runtime_scope, "_control_policy_payload"),
            metrics_payload_fn=runtime_fn(runtime_scope, "_metrics_payload"),
            work_trees_payload_fn=runtime_fn(runtime_scope, "_work_trees_payload"),
            session_summaries_fn=runtime_fn(runtime_scope, "_session_summaries"),
            test_session_report_summaries_fn=runtime_fn(runtime_scope, "_test_session_report_summaries"),
            available_test_session_definitions_fn=runtime_fn(runtime_scope, "_available_test_session_definitions"),
        )


HTTP_GET_ROUTES_SERVICE = NovaHttpGetRoutesService()
