import io
import json
import tempfile
import unittest
from pathlib import Path

from services.nova_http_responses import HTTP_RESPONSE_SERVICE


class _Handler:
    def __init__(self):
        self.status_codes = []
        self.headers = []
        self.wfile = io.BytesIO()
        self.ended = False

    def send_response(self, code):
        self.status_codes.append(code)

    def send_header(self, key, value):
        self.headers.append((key, value))

    def end_headers(self):
        self.ended = True


class TestNovaHttpResponsesService(unittest.TestCase):
    def test_json_response_with_headers_writes_payload_and_records_status(self):
        handler = _Handler()
        recorded = []

        HTTP_RESPONSE_SERVICE.json_response_with_headers(
            handler,
            201,
            {"ok": True},
            headers={"Set-Cookie": "x=y"},
            record_http_response_fn=recorded.append,
        )

        self.assertEqual(handler.status_codes, [201])
        self.assertIn(("Set-Cookie", "x=y"), handler.headers)
        self.assertEqual(json.loads(handler.wfile.getvalue().decode("utf-8")), {"ok": True})
        self.assertEqual(recorded, [201])

    def test_file_response_returns_asset_not_found_json_when_missing(self):
        handler = _Handler()
        recorded = []

        HTTP_RESPONSE_SERVICE.file_response(
            handler,
            200,
            Path("missing-asset.css"),
            "text/css; charset=utf-8",
            record_http_response_fn=recorded.append,
        )

        self.assertEqual(handler.status_codes, [404])
        payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
        self.assertFalse(payload.get("ok"))
        self.assertIn("asset_not_found:missing-asset.css", str(payload.get("error") or ""))
        self.assertEqual(recorded, [404])

    def test_emit_post_result_uses_headers_branch(self):
        handler = _Handler()
        recorded = []

        HTTP_RESPONSE_SERVICE.emit_post_result(
            handler,
            {"kind": "with_headers", "code": 200, "body": {"ok": True}, "headers": {"Set-Cookie": "x=y"}},
            record_http_response_fn=recorded.append,
        )

        self.assertEqual(handler.status_codes, [200])
        self.assertIn(("Set-Cookie", "x=y"), handler.headers)
        self.assertEqual(json.loads(handler.wfile.getvalue().decode("utf-8")), {"ok": True})
        self.assertEqual(recorded, [200])

    def test_emit_basic_route_result_handles_text(self):
        handler = _Handler()
        recorded = []

        HTTP_RESPONSE_SERVICE.emit_basic_route_result(
            handler,
            {"kind": "text", "code": 202, "body": "plain text"},
            record_http_response_fn=recorded.append,
        )

        self.assertEqual(handler.status_codes, [202])
        self.assertEqual(handler.wfile.getvalue().decode("utf-8"), "plain text")
        self.assertEqual(recorded, [202])