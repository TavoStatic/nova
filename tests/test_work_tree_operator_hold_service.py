import unittest

from services.work_tree_operator_hold import node_is_operator_hold


class TestWorkTreeOperatorHold(unittest.TestCase):
    def test_detects_source_root_operator_judgment_hold(self):
        self.assertTrue(
            node_is_operator_hold(
                {
                    "status": "blocked",
                    "source_type": "runtime_control",
                    "work_class": "governance_pressure",
                    "current_task": {
                        "title": "Hold source-root branch for operator judgment",
                        "status": "blocked",
                        "meta": {
                            "blocked_reason": "restart_provenance_operator_attribution_required",
                        },
                    },
                }
            )
        )

    def test_detects_operator_outbox_meta_hold(self):
        self.assertTrue(
            node_is_operator_hold(
                {
                    "status": "blocked",
                    "source_type": "operator_control",
                    "work_class": "operator_requested",
                    "actionability": "blocked",
                    "current_task": {
                        "title": "Wait for operator response or authority assignment on the open outbox item",
                        "status": "blocked",
                        "meta": {"blocked_reason": "operator_response_required"},
                    },
                }
            )
        )

    def test_non_operator_blocked_branch_is_not_hold(self):
        self.assertFalse(
            node_is_operator_hold(
                {
                    "status": "blocked",
                    "source_type": "subconscious",
                    "work_class": "candidate_review",
                    "current_task": {
                        "title": "Investigate route probe",
                        "status": "ready",
                        "meta": {},
                    },
                }
            )
        )


if __name__ == "__main__":
    unittest.main()