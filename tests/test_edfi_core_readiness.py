from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.edfi.config import CAPABILITY_SCHEMA
from services.edfi.core_readiness import CORE_READINESS_MILESTONE, read_edfi_core_readiness
from services.edfi.profile_evidence import EXPECTED_BISD_LEA_ID, EXPECTED_BISD_RESOURCE_COUNT


def _healthy_profile_payload() -> dict:
    return {
        "schema": CAPABILITY_SCHEMA,
        "milestone": "NOVA-EDFI-001",
        "connection_id": "district-main",
        "base_url": "https://odsprod.tea.texas.gov/odsedfiapi2026",
        "health": "ok",
        "discovered_at": 1700000000,
        "auth": {"ok": True, "type": "oauth2_client_credentials"},
        "discovery": {
            "ok": True,
            "resource_count": EXPECTED_BISD_RESOURCE_COUNT,
            "resources": ["ed-fi/schools", "ed-fi/students"],
            "namespaces": ["ed-fi", "TX"],
        },
    }


class TestEdFiCoreReadiness(unittest.TestCase):
    def test_readiness_reports_operational_when_core_contract_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "runtime" / "edfi"
            profiles = runtime / "profiles"
            connections = runtime / "connections" / "district-main"
            profiles.mkdir(parents=True)
            connections.mkdir(parents=True)
            profile = _healthy_profile_payload()
            (profiles / "district-main.json").write_text(json.dumps(profile), encoding="utf-8")
            (connections / "local_config.json").write_text(
                json.dumps({"connection_id": "district-main", "district_lea_id": EXPECTED_BISD_LEA_ID}),
                encoding="utf-8",
            )
            conn = mock.Mock(district_lea_id=EXPECTED_BISD_LEA_ID)
            with mock.patch("services.edfi.profile_evidence.profile_path", return_value=profiles / "district-main.json"), mock.patch(
                "services.edfi.profile_evidence.load_capability_profile",
                return_value=profile,
            ), mock.patch("services.edfi.profile_evidence.load_connection_config", return_value=conn), mock.patch(
                "services.edfi.profile_evidence.load_sync_state",
                return_value={},
            ):
                readiness = read_edfi_core_readiness("district-main")

        self.assertTrue(readiness["ready"])
        self.assertTrue(readiness["profile_ok"])
        self.assertTrue(readiness["inventory_declared"])
        self.assertTrue(readiness["evidence_loop_ready"])
        self.assertTrue(readiness["district_facts_ok"])
        self.assertFalse(readiness["sync_status_present"])
        self.assertEqual(readiness["blocking_issues"], [])
        self.assertEqual(readiness["next_recommended_slice"], "domain-layer-first-consumer")
        self.assertEqual(readiness["milestone"], CORE_READINESS_MILESTONE)

    def test_readiness_reports_blocked_when_profile_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing_path = Path(td) / "district-main.json"
            with mock.patch("services.edfi.profile_evidence.profile_path", return_value=missing_path), mock.patch(
                "services.edfi.profile_evidence.load_capability_profile",
                return_value={},
            ), mock.patch("services.edfi.profile_evidence.load_connection_config", return_value=None), mock.patch(
                "services.edfi.profile_evidence.load_sync_state",
                return_value={},
            ):
                readiness = read_edfi_core_readiness("district-main")

        self.assertFalse(readiness["ready"])
        self.assertFalse(readiness["profile_ok"])
        self.assertTrue(readiness["inventory_declared"])
        self.assertTrue(readiness["evidence_loop_ready"])
        self.assertFalse(readiness["district_facts_ok"])
        self.assertEqual(readiness["next_recommended_slice"], "edfi-profile-refresh")
        self.assertTrue(any("edfi_profile_missing" in item for item in readiness["blocking_issues"]))

    def test_readiness_reports_blocked_when_district_lea_id_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "runtime" / "edfi"
            profiles = runtime / "profiles"
            profiles.mkdir(parents=True)
            profile = _healthy_profile_payload()
            (profiles / "district-main.json").write_text(json.dumps(profile), encoding="utf-8")
            with mock.patch("services.edfi.profile_evidence.profile_path", return_value=profiles / "district-main.json"), mock.patch(
                "services.edfi.profile_evidence.load_capability_profile",
                return_value=profile,
            ), mock.patch("services.edfi.profile_evidence.load_connection_config", return_value=None), mock.patch(
                "services.edfi.profile_evidence.load_sync_state",
                return_value={},
            ):
                readiness = read_edfi_core_readiness("district-main")

        self.assertFalse(readiness["ready"])
        self.assertTrue(readiness["profile_ok"])
        self.assertFalse(readiness["district_facts_ok"])
        self.assertEqual(readiness["next_recommended_slice"], "edfi-connection-config")
        self.assertIn("edfi_district_lea_id_missing", readiness["blocking_issues"])

    def test_readiness_marks_sync_status_present_without_requiring_it(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "runtime" / "edfi"
            profiles = runtime / "profiles"
            connections = runtime / "connections" / "district-main"
            profiles.mkdir(parents=True)
            connections.mkdir(parents=True)
            profile = _healthy_profile_payload()
            (profiles / "district-main.json").write_text(json.dumps(profile), encoding="utf-8")
            (connections / "local_config.json").write_text(
                json.dumps({"connection_id": "district-main", "district_lea_id": EXPECTED_BISD_LEA_ID}),
                encoding="utf-8",
            )
            conn = mock.Mock(district_lea_id=EXPECTED_BISD_LEA_ID)
            sync_state = {
                "connection_id": "district-main",
                "updated_at": 1700000200,
                "resources": {"ed-fi/schools": {"last_change_version": 44}},
            }
            with mock.patch("services.edfi.profile_evidence.profile_path", return_value=profiles / "district-main.json"), mock.patch(
                "services.edfi.profile_evidence.load_capability_profile",
                return_value=profile,
            ), mock.patch("services.edfi.profile_evidence.load_connection_config", return_value=conn), mock.patch(
                "services.edfi.profile_evidence.load_sync_state",
                return_value=sync_state,
            ):
                readiness = read_edfi_core_readiness("district-main")

        self.assertTrue(readiness["ready"])
        self.assertTrue(readiness["sync_status_present"])


class TestEdFiCoreReadinessOnDisk(unittest.TestCase):
    def test_live_runtime_readiness_when_bisd_contract_is_present(self) -> None:
        from services.nova_runtime_context import resolve_base_dir

        live_profile = resolve_base_dir() / "runtime" / "edfi" / "profiles" / "district-main.json"
        if not live_profile.exists():
            self.skipTest("live runtime profile not present on this machine")

        readiness = read_edfi_core_readiness("district-main")
        self.assertTrue(readiness["inventory_declared"], readiness)
        self.assertTrue(readiness["evidence_loop_ready"], readiness)
        self.assertEqual(readiness["milestone"], CORE_READINESS_MILESTONE)


if __name__ == "__main__":
    unittest.main()