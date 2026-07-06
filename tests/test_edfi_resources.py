from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from services.edfi.client import EdFiResponse
from services.edfi.resources import (
    DEFAULT_LIMIT_CAP,
    DEFAULT_PAGE_SIZE,
    MAX_LIMIT_CAP,
    MAX_PAGE_SIZE,
    PageResult,
    ResourceReadResult,
    _extract_items,
    get_all,
    get_page,
)


def _mock_client(connection_id: str = "test") -> MagicMock:
    client = MagicMock()
    client.config.connection_id = connection_id
    return client


def _ok_response(items: list, status_code: int = 200, url: str = "") -> EdFiResponse:
    return EdFiResponse(
        ok=True,
        status_code=status_code,
        body=items,
        url=url or "https://example.com/data/v3/ed-fi/schools",
        latency_ms=10,
    )


def _error_response(status_code: int = 500, error_code: str = "edfi_server_error") -> EdFiResponse:
    return EdFiResponse(
        ok=False,
        status_code=status_code,
        body=None,
        error="server error",
        error_code=error_code,
        url="https://example.com/data/v3/ed-fi/schools",
        latency_ms=5,
    )


class TestExtractItems(unittest.TestCase):
    def test_list_body(self):
        self.assertEqual(_extract_items([{"id": 1}, {"id": 2}]), [{"id": 1}, {"id": 2}])

    def test_dict_body_returns_empty(self):
        self.assertEqual(_extract_items({"key": "value"}), [])

    def test_none_body_returns_empty(self):
        self.assertEqual(_extract_items(None), [])

    def test_empty_list(self):
        self.assertEqual(_extract_items([]), [])


class TestGetPage(unittest.TestCase):
    def _patch_audit(self):
        return patch("services.edfi.resources.append_audit_event")

    def test_happy_path_returns_items(self):
        client = _mock_client()
        items = [{"id": "s1"}, {"id": "s2"}]
        client.get.return_value = _ok_response(items)

        with self._patch_audit():
            result = get_page(client, "ed-fi/schools", limit=5, offset=0)

        self.assertTrue(result.ok)
        self.assertEqual(result.count, 2)
        self.assertEqual(result.items, items)
        self.assertEqual(result.limit, 5)
        self.assertEqual(result.offset, 0)
        self.assertFalse(result.rate_limited)
        self.assertEqual(result.error_code, "")

    def test_limit_capped_at_max(self):
        client = _mock_client()
        client.get.return_value = _ok_response([])

        with self._patch_audit():
            result = get_page(client, "ed-fi/schools", limit=9999)

        call_params = client.get.call_args[1]["params"]
        self.assertEqual(call_params["limit"], MAX_PAGE_SIZE)

    def test_offset_passed_through(self):
        client = _mock_client()
        client.get.return_value = _ok_response([])

        with self._patch_audit():
            get_page(client, "ed-fi/schools", limit=10, offset=50)

        call_params = client.get.call_args[1]["params"]
        self.assertEqual(call_params["offset"], 50)

    def test_filter_params_merged(self):
        client = _mock_client()
        client.get.return_value = _ok_response([])

        with self._patch_audit():
            get_page(client, "ed-fi/schools", filter_params={"$filter": "name eq 'X'"})

        call_params = client.get.call_args[1]["params"]
        self.assertIn("$filter", call_params)
        self.assertEqual(call_params["$filter"], "name eq 'X'")

    def test_server_error_returns_not_ok(self):
        client = _mock_client()
        client.get.return_value = _error_response(500, "edfi_server_error")

        with self._patch_audit():
            result = get_page(client, "ed-fi/schools")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "edfi_server_error")
        self.assertEqual(result.count, 0)
        self.assertEqual(result.items, [])

    def test_non_list_response_body_not_ok(self):
        client = _mock_client()
        # Response is ok=True but body is a dict, not a list — unexpected shape.
        client.get.return_value = EdFiResponse(
            ok=True, status_code=200, body={"message": "oops"}, latency_ms=5
        )

        with self._patch_audit():
            result = get_page(client, "ed-fi/schools")

        self.assertFalse(result.ok)
        self.assertEqual(result.items, [])

    def test_429_triggers_backoff_and_retry(self):
        client = _mock_client()
        items = [{"id": "s1"}]
        rate_limited = _error_response(429, "edfi_rate_limited")
        rate_limited = EdFiResponse(
            ok=False, status_code=429, body=None,
            error="rate limited", error_code="edfi_rate_limited",
            url="https://example.com/data/v3/ed-fi/schools", latency_ms=5,
        )
        success = _ok_response(items)
        client.get.side_effect = [rate_limited, success]

        slept: list[float] = []
        with self._patch_audit(), patch("services.edfi.resources.time.sleep", side_effect=slept.append):
            result = get_page(client, "ed-fi/schools", backoff_sec=0.1)

        self.assertTrue(result.ok)
        self.assertEqual(len(slept), 1)
        self.assertAlmostEqual(slept[0], 0.1)
        self.assertEqual(result.items, items)
        self.assertFalse(result.rate_limited)  # second attempt succeeded

    def test_429_both_attempts_fail(self):
        client = _mock_client()
        rate_limited = EdFiResponse(
            ok=False, status_code=429, body=None,
            error="rate limited", error_code="edfi_rate_limited",
            url="https://example.com/data/v3/ed-fi/schools", latency_ms=5,
        )
        client.get.side_effect = [rate_limited, rate_limited]

        with self._patch_audit(), patch("services.edfi.resources.time.sleep"):
            result = get_page(client, "ed-fi/schools", backoff_sec=0.0)

        self.assertFalse(result.ok)
        self.assertTrue(result.rate_limited)

    def test_audit_event_written_when_requested(self):
        client = _mock_client()
        client.get.return_value = _ok_response([{"id": "x"}])

        with patch("services.edfi.resources.append_audit_event") as mock_audit:
            get_page(client, "ed-fi/schools", audit=True)

        mock_audit.assert_called_once()
        event = mock_audit.call_args[0][0]
        self.assertEqual(event["action"], "resource_page")
        self.assertEqual(event["connection_id"], "test")

    def test_no_audit_by_default(self):
        client = _mock_client()
        client.get.return_value = _ok_response([])

        with patch("services.edfi.resources.append_audit_event") as mock_audit:
            get_page(client, "ed-fi/schools")

        mock_audit.assert_not_called()


class TestGetAll(unittest.TestCase):
    def _patch_audit(self):
        return patch("services.edfi.resources.append_audit_event")

    def test_single_page_exhausted(self):
        client = _mock_client()
        items = [{"id": f"s{i}"} for i in range(3)]
        client.get.return_value = _ok_response(items)

        with self._patch_audit():
            result = get_all(client, "ed-fi/schools", page_size=25)

        self.assertTrue(result.ok)
        self.assertEqual(result.total_fetched, 3)
        self.assertEqual(result.pages, 1)
        self.assertFalse(result.truncated)
        self.assertEqual(result.items, items)

    def test_multi_page_fetch(self):
        client = _mock_client()
        page1 = [{"id": f"s{i}"} for i in range(5)]
        page2 = [{"id": f"s{i}"} for i in range(5, 7)]
        client.get.side_effect = [_ok_response(page1), _ok_response(page2)]

        with self._patch_audit():
            result = get_all(client, "ed-fi/schools", page_size=5)

        self.assertTrue(result.ok)
        self.assertEqual(result.total_fetched, 7)
        self.assertEqual(result.pages, 2)
        self.assertFalse(result.truncated)
        self.assertEqual(len(result.items), 7)

    def test_limit_cap_truncation(self):
        client = _mock_client()
        # Each page returns exactly page_size items — infinite if not capped.
        page_items = [{"id": f"s{i}"} for i in range(5)]
        client.get.return_value = _ok_response(page_items)

        with self._patch_audit():
            result = get_all(client, "ed-fi/schools", page_size=5, limit_cap=10)

        self.assertTrue(result.ok)
        self.assertEqual(result.total_fetched, 10)
        self.assertTrue(result.truncated)

    def test_max_limit_cap_enforced(self):
        client = _mock_client()
        client.get.return_value = _ok_response([])

        with self._patch_audit():
            result = get_all(client, "ed-fi/schools", limit_cap=999_999)

        self.assertEqual(result.limit_cap, MAX_LIMIT_CAP)

    def test_first_page_error_returns_not_ok(self):
        client = _mock_client()
        client.get.return_value = _error_response(500, "edfi_server_error")

        with self._patch_audit():
            result = get_all(client, "ed-fi/schools")

        self.assertFalse(result.ok)
        self.assertEqual(result.total_fetched, 0)
        self.assertEqual(result.pages, 1)
        self.assertEqual(result.error_code, "edfi_server_error")

    def test_error_mid_page_stops_and_returns_partial(self):
        client = _mock_client()
        page1 = [{"id": f"s{i}"} for i in range(5)]
        client.get.side_effect = [_ok_response(page1), _error_response(500, "edfi_server_error")]

        with self._patch_audit():
            result = get_all(client, "ed-fi/schools", page_size=5, limit_cap=100)

        self.assertFalse(result.ok)
        self.assertEqual(result.total_fetched, 5)
        self.assertEqual(result.pages, 2)

    def test_audit_event_written(self):
        client = _mock_client()
        client.get.return_value = _ok_response([{"id": "s1"}])

        with patch("services.edfi.resources.append_audit_event") as mock_audit:
            get_all(client, "ed-fi/schools")

        mock_audit.assert_called_once()
        event = mock_audit.call_args[0][0]
        self.assertEqual(event["action"], "resource_read")
        self.assertEqual(event["milestone"], "NOVA-EDFI-002")
        self.assertIn("total_fetched", event)
        self.assertIn("pages", event)
        self.assertIn("truncated", event)

    def test_offset_advances_per_page(self):
        client = _mock_client()
        page1 = [{"id": f"s{i}"} for i in range(5)]
        page2 = [{"id": f"s{i}"} for i in range(5, 8)]
        client.get.side_effect = [_ok_response(page1), _ok_response(page2)]

        with self._patch_audit():
            get_all(client, "ed-fi/schools", page_size=5)

        calls = client.get.call_args_list
        first_params = calls[0][1]["params"]
        second_params = calls[1][1]["params"]
        self.assertEqual(first_params["offset"], 0)
        self.assertEqual(second_params["offset"], 5)


if __name__ == "__main__":
    unittest.main()
