from __future__ import annotations


class NovaHttpTransportService:
    """Own high-level HTTP GET/POST orchestration once route and response services exist."""

    @staticmethod
    def handle_get_request(
        handler,
        *,
        parse_request_path_fn,
        basic_route_request_fn,
        chat_history_request_fn,
        control_api_request_fn,
        json_response_fn,
        response_service,
        record_http_response_fn,
    ) -> None:
        path, qs = parse_request_path_fn(handler.path)

        basic_get_result = basic_route_request_fn(path, handler)
        if basic_get_result is not None:
            response_service.emit_basic_route_result(
                handler,
                basic_get_result,
                record_http_response_fn=record_http_response_fn,
            )
            return

        if path == "/api/chat/history":
            code, response_payload = chat_history_request_fn(handler, qs)
            json_response_fn(handler, code, response_payload)
            return

        control_get_result = control_api_request_fn(path, qs)
        if control_get_result is not None:
            code, response_payload = control_get_result
            json_response_fn(handler, code, response_payload)
            return

        json_response_fn(handler, 404, {"ok": False, "error": "not_found"})

    @staticmethod
    def handle_post_request(
        handler,
        *,
        parse_request_path_fn,
        dispatch_post_request_fn,
        response_service,
        record_http_response_fn,
    ) -> None:
        path, qs = parse_request_path_fn(handler.path)
        post_result = dispatch_post_request_fn(handler, path, qs)
        response_service.emit_post_result(
            handler,
            post_result,
            record_http_response_fn=record_http_response_fn,
        )


HTTP_TRANSPORT_SERVICE = NovaHttpTransportService()