from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.edfi.config import CAPABILITY_SCHEMA
from services.edfi.profile_evidence import (
    DEFAULT_PROFILE_EVIDENCE_PATH,
    EXPECTED_BISD_LEA_ID,
    EXPECTED_BISD_RESOURCE_COUNT,
    audit_runtime_profile_contract,
    build_capability_profile_evidence,
    capability_profile_payload_valid,
    profile_read_evidence_valid,
)


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


class TestEdFiProfileEvidence(unittest.TestCase):
    def test_build_evidence_from_saved_profile_without_api(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "runtime" / "edfi"
            profiles = runtime / "profiles"
            profiles.mkdir(parents=True)
            profile = _healthy_profile_payload()
            (profiles / "district-main.json").write_text(json.dumps(profile), encoding="utf-8")
            with mock.patch("services.edfi.profile_evidence.profile_path", return_value=profiles / "district-main.json"), mock.patch(
                "services.edfi.profile_evidence.load_capability_profile",
                return_value=profile,
            ):
                evidence = build_capability_profile_evidence("district-main", now_fn=lambda: 1700000100)

        self.assertTrue(evidence["ok"])
        self.assertEqual(evidence["status"], "ok")
        self.assertTrue(evidence["present"])
        self.assertTrue(evidence["auth_ok"])
        self.assertEqual(evidence["resource_count"], EXPECTED_BISD_RESOURCE_COUNT)
        self.assertEqual(evidence["discovered_at"], 1700000000)
        self.assertEqual(evidence["profile_age_sec"], 100)
        self.assertFalse(evidence["live_api_required"])
        self.assertEqual(evidence["evidence_source"], "saved_capability_profile")

    def test_missing_profile_reports_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing_path = Path(td) / "district-main.json"
            with mock.patch("services.edfi.profile_evidence.profile_path", return_value=missing_path), mock.patch(
                "services.edfi.profile_evidence.load_capability_profile",
                return_value={},
            ):
                evidence = build_capability_profile_evidence("district-main")

        self.assertFalse(evidence["ok"])
        self.assertEqual(evidence["status"], "missing")
        self.assertFalse(evidence["present"])
        self.assertEqual(evidence["issue_count"], 1)
        self.assertEqual(evidence["issues"][0]["code"], "edfi_profile_missing")
        self.assertNotIn("sync_status", evidence)

    def test_healthy_profile_without_cursor_state_omits_sync_status(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "runtime" / "edfi"
            profiles = runtime / "profiles"
            profiles.mkdir(parents=True)
            profile = _healthy_profile_payload()
            (profiles / "district-main.json").write_text(json.dumps(profile), encoding="utf-8")
            with mock.patch("services.edfi.profile_evidence.profile_path", return_value=profiles / "district-main.json"), mock.patch(
                "services.edfi.profile_evidence.load_capability_profile",
                return_value=profile,
            ), mock.patch(
                "services.edfi.profile_evidence.load_sync_state",
                return_value={},
            ):
                evidence = build_capability_profile_evidence("district-main", now_fn=lambda: 1700000100)

        self.assertTrue(evidence["ok"])
        self.assertNotIn("sync_status", evidence)

    def test_saved_change_cursors_attach_optional_sync_status_without_affecting_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "runtime" / "edfi"
            profiles = runtime / "profiles"
            profiles.mkdir(parents=True)
            profile = _healthy_profile_payload()
            (profiles / "district-main.json").write_text(json.dumps(profile), encoding="utf-8")
            sync_state = {
                "connection_id": "district-main",
                "updated_at": 1700000200,
                "resources": {
                    "ed-fi/schools": {
                        "last_change_version": 44,
                        "last_sync_at": 1700000190,
                        "last_pull_mechanism": "data_api_min_change_version",
                        "last_item_count": 3,
                    }
                },
            }
            with mock.patch("services.edfi.profile_evidence.profile_path", return_value=profiles / "district-main.json"), mock.patch(
                "services.edfi.profile_evidence.load_capability_profile",
                return_value=profile,
            ):
                evidence = build_capability_profile_evidence(
                    "district-main",
                    now_fn=lambda: 1700000300,
                    sync_state_override=sync_state,
                )

        self.assertTrue(evidence["ok"])
        sync_status = evidence.get("sync_status")
        self.assertIsInstance(sync_status, dict)
        self.assertTrue(sync_status.get("present"))
        self.assertEqual(sync_status.get("evidence_source"), "saved_change_cursors")
        self.assertEqual(sync_status.get("cursor_evidence_path"), "runtime/edfi/change_cursors/district-main.json")
        self.assertEqual(sync_status.get("updated_at"), 1700000200)
        self.assertEqual(sync_status.get("resource_cursor_count"), 1)
        schools = sync_status.get("resource_cursors", {}).get("ed-fi/schools", {})
        self.assertEqual(schools.get("last_change_version"), 44)
        self.assertEqual(schools.get("last_sync_at"), 1700000190)
        self.assertEqual(schools.get("last_pull_mechanism"), "data_api_min_change_version")
        self.assertEqual(schools.get("last_item_count"), 3)

    def test_capability_profile_payload_valid_requires_auth_resources_and_timestamp(self) -> None:
        ok, reason = capability_profile_payload_valid(_healthy_profile_payload())
        self.assertTrue(ok)
        self.assertEqual(reason, "")

        invalid = dict(_healthy_profile_payload())
        invalid["auth"] = {"ok": False}
        ok, reason = capability_profile_payload_valid(invalid)
        self.assertFalse(ok)
        self.assertEqual(reason, "profile_auth_not_ok")

        invalid = dict(_healthy_profile_payload())
        invalid["discovery"] = {"ok": True, "resource_count": 0, "resources": []}
        ok, reason = capability_profile_payload_valid(invalid)
        self.assertFalse(ok)
        self.assertEqual(reason, "profile_resources_insufficient")

    def test_profile_read_evidence_valid_accepts_saved_profile_read(self) -> None:
        row = {
            "tool_name": "read",
            "tool_args": [DEFAULT_PROFILE_EVIDENCE_PATH],
            "result_text": json.dumps(_healthy_profile_payload()),
        }
        self.assertTrue(profile_read_evidence_valid(row))

    def test_profile_read_evidence_valid_rejects_missing_file_read(self) -> None:
        row = {
            "tool_name": "read",
            "tool_args": [DEFAULT_PROFILE_EVIDENCE_PATH],
            "result_text": "file not found: runtime/edfi/profiles/district-main.json",
        }
        self.assertFalse(profile_read_evidence_valid(row))

    def test_profile_read_evidence_valid_rejects_wrong_path(self) -> None:
        row = {
            "tool_name": "read",
            "tool_args": ["services/edfi/profile_evidence.py"],
            "result_text": json.dumps(_healthy_profile_payload()),
        }
        self.assertFalse(profile_read_evidence_valid(row))

    def test_audit_runtime_profile_contract_checks_bisd_contract(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            profiles = root / "profiles"
            connections = root / "connections" / "district-main"
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
            ), mock.patch("services.edfi.profile_evidence.load_connection_config", return_value=conn):
                audit = audit_runtime_profile_contract("district-main")

        self.assertTrue(audit["ok"])
        self.assertTrue(all(audit["checks"].values()))
        self.assertEqual(audit["district_lea_id"], EXPECTED_BISD_LEA_ID)
        self.assertEqual(audit["resource_count"], EXPECTED_BISD_RESOURCE_COUNT)
        self.assertEqual(audit["evidence_source"], "saved_capability_profile")

    def test_audit_runtime_profile_contract_fails_on_lea_or_resource_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            profiles = root / "profiles"
            connections = root / "connections" / "district-main"
            profiles.mkdir(parents=True)
            connections.mkdir(parents=True)
            profile = _healthy_profile_payload()
            profile["discovery"]["resource_count"] = 12
            (profiles / "district-main.json").write_text(json.dumps(profile), encoding="utf-8")
            (connections / "local_config.json").write_text(
                json.dumps({"connection_id": "district-main", "district_lea_id": "331001"}),
                encoding="utf-8",
            )
            conn = mock.Mock(district_lea_id="331001")
            with mock.patch("services.edfi.profile_evidence.profile_path", return_value=profiles / "district-main.json"), mock.patch(
                "services.edfi.profile_evidence.load_capability_profile",
                return_value=profile,
            ), mock.patch("services.edfi.profile_evidence.load_connection_config", return_value=conn):
                audit = audit_runtime_profile_contract("district-main")

        self.assertFalse(audit["ok"])
        self.assertFalse(audit["checks"]["profile_resource_count_ok"])
        self.assertFalse(audit["checks"]["district_lea_id_ok"])


class TestEdFiRuntimeProfileOnDisk(unittest.TestCase):
    def test_live_runtime_profile_matches_bisd_contract_when_present(self) -> None:
        from services.nova_runtime_context import resolve_base_dir

        live_runtime_root = resolve_base_dir() / "runtime"
        live_profile = live_runtime_root / "edfi" / "profiles" / "district-main.json"
        if not live_profile.exists():
            self.skipTest("live runtime profile not present on this machine")
        audit = audit_runtime_profile_contract("district-main", runtime_root=live_runtime_root)
        self.assertTrue(audit["ok"], audit.get("issues"))
        self.assertEqual(audit["district_lea_id"], EXPECTED_BISD_LEA_ID)
        self.assertEqual(audit["resource_count"], EXPECTED_BISD_RESOURCE_COUNT)
        self.assertGreater(int(audit["discovered_at"] or 0), 0)
        self.assertEqual(audit["evidence_source"], "saved_capability_profile")

        evidence = build_capability_profile_evidence("district-main", path_override=live_profile)
        if (live_runtime_root / "edfi" / "change_cursors" / "district-main.json").exists():
            self.assertIn("sync_status", evidence)
            self.assertTrue(evidence["sync_status"].get("present"))


if __name__ == "__main__":
    unittest.main()