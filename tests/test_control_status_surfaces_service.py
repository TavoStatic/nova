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
            "nova_mission_status": "quiet_hold",
            "nova_mission_owner_verdicts": [
                {"owner": "core_thinning", "ready": False, "blocks_green": False}
            ],
            "nova_mission_owner_blockers": [
                {"owner": "core_thinning", "code": "core_http_thinning_pressure"}
            ],
            "core_thinning_sync": {"status": "ok", "order_count": 3},
            "core_thinning_order_count": 3,
            "guard": {"status": "running"},
            "core": {"status": "running"},
            "webui": {"status": "running"},
            "runtime_summary": {"core": {"status": "running"}},
            "memory_health": {"status": "ok"},
            "work_tree_truth": {"status": "blocked_observing", "open_task_count": 4},
            "work_tree_truth_status": "blocked_observing",
            "work_tree_open_task_count": 4,
            "observation_spine": {"ok": True, "status": "intervening", "finding_code": "REPEATED_UNCHANGED_PATH"},
            "observation_intervening": True,
            "observation_finding_code": "REPEATED_UNCHANGED_PATH",
            "grounded_self_report": {"huge": "payload"},
            "operator_attention_message": "ignore me",
        }

        surfaces = extract_signal_ingestion_surfaces(full)

        self.assertEqual(surfaces.get("status_kind"), "signal_ingestion_surfaces")
        self.assertEqual(surfaces.get("health_score"), 95)
        self.assertEqual(surfaces.get("operator_outbox_open_count"), 1)
        self.assertEqual((surfaces.get("root_closure_inventory") or {}).get("gap_count"), 0)
        self.assertEqual(surfaces.get("nova_mission_status"), "quiet_hold")
        self.assertEqual((surfaces.get("nova_mission_owner_verdicts") or [])[0].get("owner"), "core_thinning")
        self.assertEqual((surfaces.get("nova_mission_owner_blockers") or [])[0].get("code"), "core_http_thinning_pressure")
        self.assertEqual((surfaces.get("core_thinning_sync") or {}).get("order_count"), 3)
        self.assertEqual(surfaces.get("core_thinning_order_count"), 3)
        self.assertEqual((surfaces.get("guard") or {}).get("status"), "running")
        self.assertEqual((surfaces.get("work_tree_truth") or {}).get("open_task_count"), 4)
        self.assertEqual(surfaces.get("work_tree_truth_status"), "blocked_observing")
        self.assertEqual(surfaces.get("work_tree_open_task_count"), 4)
        self.assertEqual((surfaces.get("observation_spine") or {}).get("finding_code"), "REPEATED_UNCHANGED_PATH")
        self.assertTrue(surfaces.get("observation_intervening"))
        self.assertEqual(surfaces.get("observation_finding_code"), "REPEATED_UNCHANGED_PATH")
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
            "nova_mission_status": "validation_required",
            "nova_mission_owner_blockers": [{"owner": "validation", "code": "validation_truth_missing"}],
            "core_thinning_order_count": 4,
            "work_tree_truth_status": "open",
            "work_tree_open_task_count": 2,
        }

        merged = merge_http_supplement_into_local(local, http)

        self.assertEqual((merged.get("root_closure_inventory") or {}).get("gap_count"), 0)
        self.assertEqual(merged.get("operator_outbox_open_count"), 2)
        self.assertEqual(merged.get("alerts"), ["operator_outbox_open"])
        self.assertEqual(merged.get("nova_mission_status"), "validation_required")
        self.assertEqual((merged.get("nova_mission_owner_blockers") or [])[0].get("owner"), "validation")
        self.assertEqual(merged.get("core_thinning_order_count"), 4)
        self.assertEqual(merged.get("work_tree_truth_status"), "open")
        self.assertEqual(merged.get("work_tree_open_task_count"), 2)

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

    def test_merge_http_supplement_prefers_http_root_closure_inventory(self):
        local = {
            "root_closure_inventory": {
                "ok": False,
                "gap_count": 36,
                "gap_roots": ["runtime_core"],
                "roots": [{"root_id": "runtime_core", "ok": False}],
            },
            "root_closure_inventory_ok": False,
            "root_closure_inventory_gap_count": 36,
        }
        http = {
            "root_closure_inventory": {
                "ok": True,
                "gap_count": 0,
                "gap_roots": [],
                "roots": [{"root_id": "runtime_core", "ok": True}],
            },
            "root_closure_inventory_ok": True,
            "root_closure_inventory_gap_count": 0,
        }

        merged = merge_http_supplement_into_local(local, http)

        self.assertTrue(merged.get("root_closure_inventory_ok"))
        self.assertEqual(merged.get("root_closure_inventory_gap_count"), 0)
        self.assertTrue((merged.get("root_closure_inventory") or {}).get("ok"))


if __name__ == "__main__":
    unittest.main()
