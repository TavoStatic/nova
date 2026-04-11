from __future__ import annotations

import json
from pathlib import Path


class NovaHttpResponsesService:
    """Own HTTP response emission once routing/dispatch have already decided the payload."""

    @staticmethod
    def json_response_with_headers(
        handler,
        code: int,
        payload: dict,
        *,
        record_http_response_fn,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            handler.send_header(key, value)
        handler.end_headers()
        handler.wfile.write(body)
        record_http_response_fn(code)

    def json_response(self, handler, code: int, payload: dict, *, record_http_response_fn) -> None:
        self.json_response_with_headers(
            handler,
            code,
            payload,
            record_http_response_fn=record_http_response_fn,
        )

    @staticmethod
    def text_response(handler, code: int, text: str, *, record_http_response_fn) -> None:
        body = text.encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)
        record_http_response_fn(code)

    def file_response(
        self,
        handler,
        code: int,
        path: Path,
        content_type: str,
        *,
        record_http_response_fn,
    ) -> None:
        try:
            body = Path(path).read_bytes()
        except Exception as exc:
            self.json_response(
                handler,
                404,
                {"ok": False, "error": f"asset_not_found:{Path(path).name}:{exc}"},
                record_http_response_fn=record_http_response_fn,
            )
            return
        handler.send_response(code)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)
        record_http_response_fn(code)

    def emit_basic_route_result(self, handler, result: dict, *, record_http_response_fn) -> None:
        payload = dict(result or {})
        kind = str(payload.get("kind") or "json").strip().lower() or "json"
        code = int(payload.get("code", 200) or 200)
        if kind == "text":
            self.text_response(
                handler,
                code,
                str(payload.get("body") or ""),
                record_http_response_fn=record_http_response_fn,
            )
            return
        if kind == "file":
            self.file_response(
                handler,
                code,
                payload.get("path"),
                str(payload.get("content_type") or "text/plain; charset=utf-8"),
                record_http_response_fn=record_http_response_fn,
            )
            return
        self.json_response(
            handler,
            code,
            payload.get("body") or {},
            record_http_response_fn=record_http_response_fn,
        )

    def emit_post_result(self, handler, result: dict, *, record_http_response_fn) -> None:
        payload = dict(result or {})
        kind = str(payload.get("kind") or "json").strip().lower() or "json"
        code = int(payload.get("code", 200) or 200)
        if kind == "with_headers":
            self.json_response_with_headers(
                handler,
                code,
                payload.get("body") or {},
                record_http_response_fn=record_http_response_fn,
                headers=payload.get("headers") or {},
            )
            return
        self.json_response(
            handler,
            code,
            payload.get("body") or {},
            record_http_response_fn=record_http_response_fn,
        )


HTTP_RESPONSE_SERVICE = NovaHttpResponsesService()