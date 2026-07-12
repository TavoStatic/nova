import unittest

from services.work_tree_pressure_snapshot import build_work_tree_pressure_snapshot


class TestWorkTreePressureSnapshotService(unittest.TestCase):
    def test_snapshot_splits_operator_hold_blocked_observing_and_release_stale_ready(self):
        payload = {
            "counts": {
                "total": 1,
                "active": 1,
                "branches": 3,
                "open_tasks": 3,
                "pending": 1,
                "working": 0,
                "blocked": 2,
                "complete": 0,
            },
            "trees": [
                {
                    "nodes": [
                        {
                            "title": "Subconscious candidate repair",
                            "status": "blocked",
                            "resolution_state": "observing",
                            "source_type": "subconscious",
                            "work_class": "candidate_review",
                            "current_task": {"status": "blocked", "title": "Hold for evidence"},
                        },
                        {
                            "title": "Memory bootstrap",
                            "status": "blocked",
                            "resolution_state": "",
                            "source_type": "memory_health",
                            "work_class": "governance_pressure",
                            "source_payload": {
                                "memory_bootstrap_origin": {"status": "pending_operator_confirmation"}
                            },
                            "current_task": {"status": "blocked", "title": "Wait"},
                        },
                        {
                            "title": "Release-stale validation outcome is missing",
                            "status": "ready",
                            "resolution_state": "observing",
                            "source_type": "release_status",
                            "work_class": "release_readiness_gap",
                            "current_task": {"status": "open", "title": "Record release stale judgment"},
                        },
                    ]
                }
            ],
        }

        snapshot = build_work_tree_pressure_snapshot(payload)

        self.assertEqual(snapshot.get("status"), "blocked_observing")
        self.assertEqual(snapshot.get("operator_hold_branch_count"), 1)
        self.assertEqual(snapshot.get("self_repair_blocked_branch_count"), 1)
        self.assertEqual(snapshot.get("self_repair_observing_branch_count"), 2)
        self.assertEqual(snapshot.get("observing_branch_count"), 2)
        self.assertEqual(snapshot.get("blocked_observing_count"), 1)
        self.assertEqual(snapshot.get("latent_root_signal_count"), 1)
        self.assertEqual(snapshot.get("release_stale_ready_count"), 1)


if __name__ == "__main__":
    unittest.main()
