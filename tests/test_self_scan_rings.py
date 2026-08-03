from __future__ import annotations

import unittest

from services.nova_wiring_inventory import (
    DEFAULT_ADVISORY_ACTIONS,
    DEFAULT_PLANNED_TOOLS,
    DEFAULT_SIGNAL_SOURCES,
    WIRING_SURFACES,
    build_root_closure_inventory_payload,
    build_wiring_inventory_payload,
)
from services.self_scan_rings import (
    PROBE_LIVE,
    PROBE_OFFLINE,
    assess_stem_climbability,
    resolve_probe_context,
    run_ring1_map_integrity,
    run_ring2_contract_integrity,
    run_ring3_climb_integrity,
    run_self_scan_rings,
)


def _live_status() -> dict:
    payload: dict = {"health_score": 100, "guard": True, "core": True}
    for surface in WIRING_SURFACES:
        for key in surface.status_keys:
            payload[key] = True
    return payload


class SelfScanRingsTests(unittest.TestCase):
    def test_empty_status_is_offline_probe_context(self) -> None:
        self.assertEqual(resolve_probe_context({}), PROBE_OFFLINE)
        self.assertEqual(resolve_probe_context(None), PROBE_OFFLINE)

    def test_live_markers_select_live_status(self) -> None:
        self.assertEqual(resolve_probe_context({"health_score": 90}), PROBE_LIVE)

    def test_ring2_offline_does_not_storm_status_key_gaps(self) -> None:
        wiring = build_wiring_inventory_payload(
            {},
            signal_sources=DEFAULT_SIGNAL_SOURCES,
            planned_tools=DEFAULT_PLANNED_TOOLS,
            advisory_actions=DEFAULT_ADVISORY_ACTIONS,
            probe_context=PROBE_OFFLINE,
        )
        closure = build_root_closure_inventory_payload(
            {},
            signal_sources=DEFAULT_SIGNAL_SOURCES,
            planned_tools=DEFAULT_PLANNED_TOOLS,
            advisory_actions=DEFAULT_ADVISORY_ACTIONS,
            probe_context=PROBE_OFFLINE,
        )
        self.assertEqual(wiring.get("probe_context"), PROBE_OFFLINE)
        self.assertFalse(wiring.get("status_gaps_scored"))
        self.assertEqual(wiring.get("missing_status_surfaces"), [])
        self.assertEqual(closure.get("missing_status_roots"), [])
        # Offline must not invent a full missing-status gap storm.
        self.assertEqual(wiring.get("gap_count"), 0)

    def test_ring2_live_scores_missing_status_keys(self) -> None:
        wiring = build_wiring_inventory_payload(
            {"health_score": 1},
            signal_sources=DEFAULT_SIGNAL_SOURCES,
            planned_tools=DEFAULT_PLANNED_TOOLS,
            advisory_actions=DEFAULT_ADVISORY_ACTIONS,
            probe_context=PROBE_LIVE,
        )
        self.assertTrue(wiring.get("status_gaps_scored"))
        self.assertGreater(int(wiring.get("gap_count") or 0), 0)

    def test_ring3_unresolvable_args_not_climbable(self) -> None:
        result = assess_stem_climbability(
            tool_name="read",
            tool_args_resolvable=False,
            tool_in_safe_execute=True,
        )
        self.assertFalse(result["climbable"])
        self.assertEqual(result["reason"], "unresolvable_tool_args")

    def test_ring3_failed_tool_not_climbable(self) -> None:
        result = assess_stem_climbability(
            tool_name="read",
            tool_status="failed",
            tool_args_resolvable=True,
            tool_in_safe_execute=True,
        )
        self.assertFalse(result["climbable"])
        self.assertEqual(result["reason"], "tool_failed")

    def test_ring3_queue_assessment(self) -> None:
        ring3 = run_ring3_climb_integrity(
            [
                {
                    "task_id": "t1",
                    "recommended_tool": "read",
                    "tool_args_resolvable": False,
                    "tool_in_safe_execute": True,
                },
                {
                    "task_id": "t2",
                    "recommended_tool": "phase2_audit",
                    "tool_in_safe_execute": True,
                },
            ]
        )
        self.assertEqual(ring3["unclimbable_count"], 1)
        self.assertEqual(ring3["climbable_count"], 1)

    def test_ring1_runs(self) -> None:
        ring1 = run_ring1_map_integrity()
        self.assertEqual(ring1["ring"], 1)
        self.assertIn("findings", ring1)
        # solution_trail and progress helpers should no longer orphan as unclassified.
        unclassified = list((ring1.get("findings") or {}).get("unclassified_source_files") or [])
        self.assertNotIn("services/solution_trail.py", unclassified)
        self.assertNotIn("services/work_tree_task_progress.py", unclassified)

    def test_full_rings_offline(self) -> None:
        payload = run_self_scan_rings({}, findings_queue=[], probe_context=PROBE_OFFLINE)
        self.assertEqual(payload.get("probe_context"), PROBE_OFFLINE)
        self.assertIn("1_map_integrity", payload["rings"])
        self.assertIn("2_contract_integrity", payload["rings"])
        self.assertIn("3_climb_integrity", payload["rings"])
        # Offline ring2 must not invent status-key architecture storms.
        self.assertEqual(
            payload["rings"]["2_contract_integrity"]["findings"].get("status_gaps_scored"),
            False,
        )


if __name__ == "__main__":
    unittest.main()
