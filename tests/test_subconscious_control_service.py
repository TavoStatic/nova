import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from services.subconscious_control import SUBCONSCIOUS_CONTROL_SERVICE


class TestSubconsciousControlService(unittest.TestCase):
    def test_latest_report_reads_latest_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "latest.json").write_text(json.dumps({"label": "hourly"}, ensure_ascii=True), encoding="utf-8")

            payload = SUBCONSCIOUS_CONTROL_SERVICE.latest_report(root)

        self.assertEqual(payload.get("label"), "hourly")

    def test_status_summary_orders_top_priorities_and_counts_generated_defs(self):
        latest = {
            "generated_at": "2026-03-31 12:00:00",
            "label": "hourly",
            "totals": {
                "family_count": 2,
                "variation_count": 7,
                "training_priority_count": 3,
            },
            "families": [
                {
                    "target_seam": "route_selection",
                    "training_priorities": [
                        {"signal": "fallback_overuse", "urgency": "high", "robustness": 0.8},
                        {"signal": "route_unclear", "urgency": "medium", "robustness": 0.6},
                    ],
                },
                {
                    "target_seam": "memory_capture",
                    "training_priorities": [
                        {"signal": "memory_drop", "urgency": "high", "robustness": 0.9},
                    ],
                },
            ],
        }

        payload = SUBCONSCIOUS_CONTROL_SERVICE.status_summary(
            latest,
            [
                {"file": "saved.json", "origin": "saved"},
                {"file": "generated_a.json", "origin": "generated"},
                {"file": "generated_b.json", "origin": "generated"},
            ],
            Path("runtime/subconscious_runs/latest.json"),
        )

        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("generated_definition_count"), 2)
        self.assertEqual(payload.get("family_count"), 2)
        self.assertEqual([item.get("signal") for item in (payload.get("top_priorities") or [])][:2], ["memory_drop", "fallback_overuse"])
        self.assertEqual((payload.get("top_priorities") or [])[0].get("seam_label"), "memory capture")

    def test_live_summary_surfaces_replan_sessions_and_reason_counts(self):
        session = SimpleNamespace(active_subject=lambda: "identity_profile:developer")
        payload = SUBCONSCIOUS_CONTROL_SERVICE.live_summary(
            limit=5,
            pressure_config={"recent_pressure_window_cap": 12, "weak_signal_thresholds": {"route_fit_weak": 2}},
            session_turns_items=[("s-live", [("user", "how are you doing today ?"), ("assistant", "fine")])],
            session_owner_lookup={"s-live": "operator"},
            session_state_peek_fn=lambda session_id: session if session_id == "s-live" else None,
            get_snapshot_fn=lambda current: {
                "record_window": {"count": 2, "cap": 12},
                "replan_requested": True,
                "replan_reasons": [{"kind": "weak_signal_threshold", "signal": "route_fit_weak", "window_count": 2, "threshold": 2}],
                "active_recent_signals": ["route_fit_weak"],
                "weak_signal_window_counts": {"route_fit_weak": 2},
            },
        )

        self.assertEqual(payload.get("tracked_session_count"), 1)
        self.assertEqual(payload.get("replan_session_count"), 1)
        self.assertEqual((payload.get("pressure_config") or {}).get("weak_signal_thresholds"), {"route_fit_weak": 2})
        self.assertEqual(payload.get("active_reason_counts"), {"route_fit_weak": 1})
        sessions = payload.get("sessions") or []
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].get("session_id"), "s-live")
        self.assertEqual(sessions[0].get("owner"), "operator")
        self.assertEqual(sessions[0].get("last_user"), "how are you doing today ?")


if __name__ == "__main__":
    unittest.main()