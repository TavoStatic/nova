from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.edfi.change_tracking import (
    fetch_available_change_versions,
    load_sync_state,
    pull_changes_since,
    save_sync_state,
    sync_status,
)
from services.edfi.client import EdFiResponse
from services.edfi.config import ConnectionConfig


def _config() -> ConnectionConfig:
    return ConnectionConfig(
        connection_id="district-main",
        base_url="https://example.edfi.org",
        client_id="id",
        client_secret="secret",
        district_lea_id="31901",
    )


class TestEdFiChangeTracking(unittest.TestCase):
    def test_fetch_available_change_versions_reads_root_manifest(self) -> None:
        client = mock.Mock()
        client.config = _config()
        client.get.side_effect = [
            EdFiResponse(
                ok=True,
                status_code=200,
                body={"urls": {"changeQueries": "https://example.edfi.org/changeQueries/v1/"}},
            ),
            EdFiResponse(
                ok=True,
                status_code=200,
                body={"oldestChangeVersion": 0, "newestChangeVersion": 99},
            ),
        ]

        result = fetch_available_change_versions(client)

        self.assertTrue(result["ok"])
        self.assertEqual(result["oldest_change_version"], 0)
        self.assertEqual(result["newest_change_version"], 99)

    def test_save_and_load_sync_state_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "runtime" / "edfi"
            cursors = runtime / "change_cursors"
            with mock.patch("services.edfi.change_tracking.change_cursor_path") as path_mock:
                target = cursors / "district-main.json"
                path_mock.return_value = target
                save_sync_state(
                    "district-main",
                    {
                        "resources": {
                            "ed-fi/schools": {"last_change_version": 12},
                        }
                    },
                    now_fn=lambda: 1700000000,
                )
                state = load_sync_state("district-main")
            self.assertEqual(state["connection_id"], "district-main")
            self.assertEqual(state["resources"]["ed-fi/schools"]["last_change_version"], 12)

    def test_pull_changes_since_uses_data_api_when_change_query_404(self) -> None:
        with mock.patch("services.edfi.change_tracking.build_client") as build_mock, mock.patch(
            "services.edfi.change_tracking.load_connection_config",
            return_value=_config(),
        ), mock.patch(
            "services.edfi.change_tracking.resolve_change_queries_base",
            return_value=("https://example.edfi.org/changeQueries/v1", "root_manifest"),
        ), mock.patch(
            "services.edfi.change_tracking.resolve_data_management_api",
            return_value="https://example.edfi.org/data/v3",
        ), mock.patch(
            "services.edfi.change_tracking.fetch_available_change_versions",
            return_value={
                "ok": True,
                "oldest_change_version": 0,
                "newest_change_version": 50,
            },
        ), mock.patch(
            "services.edfi.change_tracking.save_sync_state",
            return_value="/tmp/district-main.json",
        ) as save_mock:
            client = mock.Mock()
            build_mock.return_value = client
            client.get.side_effect = [
                EdFiResponse(ok=False, status_code=404, error="not found"),
                EdFiResponse(
                    ok=True,
                    status_code=200,
                    url="https://example.edfi.org/data/v3/ed-fi/schools",
                    body=[{"schoolId": 31901001, "changeVersion": 44, "nameOfInstitution": "Hanna"}],
                ),
            ]
            result = pull_changes_since(
                "district-main",
                resource="ed-fi/schools",
                min_change_version=10,
                limit=5,
                advance_cursor=True,
                now_fn=lambda: 1700000001,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["mechanism"], "data_api_min_change_version")
        self.assertEqual(result["item_count"], 1)
        self.assertTrue(save_mock.called)
        saved_state = save_mock.call_args.args[1]
        self.assertEqual(saved_state["resources"]["ed-fi/schools"]["last_change_version"], 44)

    def test_sync_status_reports_cursor_map(self) -> None:
        with mock.patch(
            "services.edfi.change_tracking.load_connection_config",
            return_value=_config(),
        ), mock.patch(
            "services.edfi.change_tracking.build_client",
            return_value=mock.Mock(),
        ), mock.patch(
            "services.edfi.change_tracking.fetch_available_change_versions",
            return_value={
                "ok": True,
                "oldest_change_version": 0,
                "newest_change_version": 77,
            },
        ), mock.patch(
            "services.edfi.change_tracking.resolve_change_queries_base",
            return_value=("https://example.edfi.org/changeQueries/v1", "root_manifest"),
        ), mock.patch(
            "services.edfi.change_tracking.load_sync_state",
            return_value={"resources": {"ed-fi/schools": {"last_change_version": 12}}},
        ):
            result = sync_status("district-main")

        self.assertTrue(result["ok"])
        self.assertEqual(result["district_lea_id"], "31901")
        self.assertEqual(result["resource_cursors"]["ed-fi/schools"]["last_change_version"], 12)


if __name__ == "__main__":
    unittest.main()