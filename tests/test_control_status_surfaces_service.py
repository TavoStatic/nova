import unittest

from services.control_status_surfaces import (
    derive_surfaces_url,
    extract_signal_ingestion_surfaces,
    merge_http_supplement_into_local,
    release_drift_detected,
)


class TestControlStatusSurfacesService(unittest.TestCase):
    def test_derive_surfaces_url_appends_surfaces_suffix(self):
        self.assertEqual(
            derive_surfaces_url("http://127.0.0.1:8080/api/control/status"),
            "http://127.0.0.1:8080/api/control/status/surfaces",
        )

    def test_extract_signal_ingestion_surfaces_keeps_wiring_keys_only(self):
        full = {
            "ok": True,
            "health_score": 95,
            "operator_outbox_open_count": 1,
            "root_closure_inventory": {"ok": True, "gap_count": 0, "roots": []},
            "grounded_self_report": {"huge": "payload"},
            "operator_attention_message": "ignore me",
        }

        surfaces = extract_signal_ingestion_surfaces(full)

        self.assertEqual(surfaces.get("status_kind"), "signal_ingestion_surfaces")
        self.assertEqual(surfaces.get("health_score"), 95)
        self.assertEqual(surfaces.get("operator_outbox_open_count"), 1)
        self.assertEqual((surfaces.get("root_closure_inventory") or {}).get("gap_count"), 0)
        self.assertNotIn("grounded_self_report", surfaces)
        self.assertNotIn("operator_attention_message", surfaces)

    def test_merge_http_supplement_preserves_local_authoritative_inventory(self):
        local = {
            "root_closure_inventory": {"ok": True, "gap_count": 0, "roots": []},
            "ollama_api_up": True,
        }
        http = {
            "root_closure_inventory": {"ok": False, "gap_count": 9, "roots": [{"root_id": "stale"}]},
            "operator_outbox_open_count": 2,
            "alerts": ["operator_outbox_open"],
        }

        merged = merge_http_supplement_into_local(local, http)

        self.assertEqual((merged.get("root_closure_inventory") or {}).get("gap_count"), 0)
        self.assertEqual(merged.get("operator_outbox_open_count"), 2)
        self.assertEqual(merged.get("alerts"), ["operator_outbox_open"])

    def test_release_drift_detected_matches_source_changed_after_build(self):
        self.assertTrue(
            release_drift_detected({"latest_readiness_state": "source-changed-after-build"})
        )
        self.assertFalse(release_drift_detected({"latest_readiness_state": "ready"}))

    def test_merge_http_supplement_preserves_local_frontdoor_cli_surfaces(self):
        local = {
            "backend_commands": [{"command_id": "regression_gate"}],
            "backend_command_count": 1,
            "frontdoor_cli_status": "ok",
            "cli_http_parity": {"ok": True, "status": "ok"},
        }
        http = {
            "backend_commands": [],
            "backend_command_count": 0,
            "frontdoor_cli_status": "degraded",
            "cli_http_parity": {"ok": False, "status": "degraded"},
            "operator_outbox_open_count": 1,
        }

        merged = merge_http_supplement_into_local(local, http)

        self.assertEqual(merged.get("frontdoor_cli_status"), "ok")
        self.assertTrue((merged.get("cli_http_parity") or {}).get("ok"))
        self.assertEqual(merged.get("backend_command_count"), 1)
        self.assertEqual(merged.get("operator_outbox_open_count"), 1)


if __name__ == "__main__":
    unittest.main()