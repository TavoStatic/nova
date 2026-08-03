from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.edfi.rate_limit_evidence import (
    evidence_summary,
    extract_rate_limit_headers,
    load_latest_evidence,
    maybe_record_from_response,
    parse_retry_after_seconds,
    record_rate_limit_event,
    record_recovery_if_pending,
    suggested_cooldown_seconds,
)


class TestRateLimitEvidence(unittest.TestCase):
    def test_extract_headers_keeps_rate_fields_drops_auth(self) -> None:
        headers = {
            "Authorization": "Bearer secret",
            "Retry-After": "90",
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "0",
            "Content-Type": "application/json",
            "Date": "Sat, 25 Jul 2026 12:00:00 GMT",
        }
        out = extract_rate_limit_headers(headers)
        self.assertNotIn("Authorization", out)
        self.assertEqual(out.get("Retry-After"), "90")
        self.assertEqual(out.get("X-RateLimit-Limit"), "100")
        self.assertNotIn("Content-Type", out)

    def test_parse_retry_after_seconds(self) -> None:
        self.assertEqual(parse_retry_after_seconds({"Retry-After": "45"}), 45.0)
        self.assertIsNone(parse_retry_after_seconds({}))

    def test_suggested_cooldown_uses_retry_after(self) -> None:
        self.assertEqual(
            suggested_cooldown_seconds({"Retry-After": "120"}, default=60.0),
            120.0,
        )
        self.assertEqual(suggested_cooldown_seconds({}, default=60.0), 60.0)

    def test_record_and_load_latest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch("services.edfi.rate_limit_evidence.EVIDENCE_DIR", root):
                with mock.patch("services.edfi.rate_limit_evidence.LATEST_PATH", root / "latest.json"):
                    with mock.patch(
                        "services.edfi.rate_limit_evidence.EVENTS_PATH",
                        root / "events.jsonl",
                    ):
                        event = record_rate_limit_event(
                            status_code=429,
                            method="GET",
                            url="https://example.test/data/v3/ed-fi/schools?limit=10",
                            error='{ "operation" : "ratelimited" }',
                            error_code="edfi_rate_limited",
                            body={"operation": "ratelimited"},
                            response_headers={"Retry-After": "90", "X-RateLimit-Remaining": "0"},
                            latency_ms=120,
                            connection_id="test",
                            base_url="https://example.test",
                            now_epoch=1_700_000_000.0,
                        )
                        self.assertEqual(event["suggested_cooldown_sec"], 90.0)
                        latest = load_latest_evidence()
                        self.assertIsNotNone(latest)
                        assert latest is not None
                        self.assertEqual(latest["status_code"], 429)
                        self.assertEqual(latest["response_headers"].get("Retry-After"), "90")
                        summary = evidence_summary()
                        self.assertTrue(summary["ok"])
                        self.assertEqual(
                            summary["safety"]["deliberate_flood_probe"],
                            "disabled",
                        )

    def test_recovery_after_rate_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch("services.edfi.rate_limit_evidence.EVIDENCE_DIR", root):
                with mock.patch("services.edfi.rate_limit_evidence.LATEST_PATH", root / "latest.json"):
                    with mock.patch(
                        "services.edfi.rate_limit_evidence.EVENTS_PATH",
                        root / "events.jsonl",
                    ):
                        # Reset module globals via a fresh record
                        import services.edfi.rate_limit_evidence as mod

                        mod._LAST_429_EPOCH = 0.0
                        mod._LAST_429_ID = ""
                        record_rate_limit_event(
                            status_code=429,
                            url="https://example.test/schools",
                            response_headers={"Retry-After": "30"},
                            now_epoch=1000.0,
                        )
                        rec = record_recovery_if_pending(
                            method="GET",
                            url="https://example.test/schools",
                            status_code=200,
                            now_epoch=1075.0,
                        )
                        self.assertIsNotNone(rec)
                        assert rec is not None
                        self.assertEqual(rec["kind"], "recovered_after_rate_limit")
                        self.assertEqual(rec["recovered_after_sec"], 75.0)

    def test_maybe_record_from_response_body_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch("services.edfi.rate_limit_evidence.EVIDENCE_DIR", root):
                with mock.patch("services.edfi.rate_limit_evidence.LATEST_PATH", root / "latest.json"):
                    with mock.patch(
                        "services.edfi.rate_limit_evidence.EVENTS_PATH",
                        root / "events.jsonl",
                    ):
                        event = maybe_record_from_response(
                            status_code=403,
                            method="GET",
                            url="https://example.test/x",
                            error='{ "operation" : "ratelimited" }',
                            body={"operation": "ratelimited"},
                            response_headers={},
                        )
                        self.assertIsNotNone(event)
                        assert event is not None
                        self.assertEqual(event["kind"], "rate_limited")


if __name__ == "__main__":
    unittest.main()
