from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.edfi.inventory import (
    list_resources,
    profile_summary,
    read_preset,
    read_resource,
)


def _profile_patches(tmp: str):
    runtime = Path(tmp) / "runtime" / "edfi"
    profiles = runtime / "profiles"
    connections = runtime / "connections" / "district-main"
    profiles.mkdir(parents=True)
    connections.mkdir(parents=True)
    profile = {
        "schema": "nova.edfi_capability.v1",
        "connection_id": "district-main",
        "base_url": "https://example.org",
        "health": "ok",
        "api_version": "7.1",
        "data_model_version": "4.0.0",
        "discovered_at": 1700000000,
        "auth": {"ok": True},
        "discovery": {
            "resource_count": 4,
            "resources": [
                "ed-fi/schools",
                "ed-fi/students",
                "TX/studentExtensions",
                "ed-fi/studentSchoolAssociations",
            ],
            "namespaces": ["ed-fi", "TX"],
            "metadata_url": "https://example.org/metadata/data/v3/dependencies",
        },
    }
    (profiles / "district-main.json").write_text(json.dumps(profile), encoding="utf-8")
    (connections / "local_config.json").write_text(
        json.dumps(
            {
                "connection_id": "district-main",
                "base_url": "https://example.org",
                "client_id": "id",
                "client_secret": "secret",
            }
        ),
        encoding="utf-8",
    )
    return (
        mock.patch("services.edfi.config.EDFI_RUNTIME_ROOT", runtime),
        mock.patch("services.edfi.config.EDFI_PROFILES_ROOT", profiles),
        mock.patch("services.edfi.config.EDFI_CONNECTIONS_ROOT", connections.parent),
    )


class TestEdFiInventory(unittest.TestCase):
    def test_profile_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2, p3 = _profile_patches(tmp)
            with p1, p2, p3:
                result = profile_summary("district-main")
            self.assertTrue(result["ok"])
            self.assertEqual(result["resource_count"], 4)
            self.assertFalse(result["catalog_truncated"])

    def test_list_resources_filters_query_and_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2, p3 = _profile_patches(tmp)
            with p1, p2, p3:
                tx_only = list_resources("district-main", namespace="TX")
                schoolish = list_resources("district-main", query="school")
            self.assertTrue(tx_only["ok"])
            self.assertEqual(tx_only["total_matches"], 1)
            self.assertEqual(tx_only["resources"], ["TX/studentExtensions"])
            self.assertTrue(schoolish["ok"])
            self.assertEqual(schoolish["total_matches"], 2)

    def test_read_resource_delegates_to_get_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2, p3 = _profile_patches(tmp)
            with p1, p2, p3, mock.patch("services.edfi.inventory.get_page") as get_page:
                get_page.return_value = mock.Mock(
                    ok=True,
                    resource="schools",
                    url="https://example.org/data/v3/schools",
                    offset=0,
                    limit=5,
                    count=1,
                    items=[{"schoolId": "1"}],
                    latency_ms=12,
                    status_code=200,
                    error="",
                    error_code="",
                    rate_limited=False,
                )
                result = read_resource("district-main", "schools", limit=5)
            self.assertTrue(result["ok"])
            self.assertEqual(result["count"], 1)
            get_page.assert_called_once()

    def test_read_preset_tries_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2, p3 = _profile_patches(tmp)
            with p1, p2, p3, mock.patch("services.edfi.inventory.read_resource") as read_resource_mock:
                read_resource_mock.side_effect = [
                    {"ok": False, "error_code": "edfi_not_found"},
                    {"ok": True, "resource": "ed-fi/schools", "count": 2, "items": []},
                ]
                result = read_preset("district-main", "schools", limit=3)
            self.assertTrue(result["ok"])
            self.assertEqual(result["resource"], "ed-fi/schools")
            self.assertEqual(read_resource_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()