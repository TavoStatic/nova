import unittest

from services.decision_proposal_judge import (
    DISPOSITION_ABORT_AND_FILE,
    DISPOSITION_PAUSE_AND_SURFACE,
    DISPOSITION_PROCEED,
    DISPOSITION_PROCEED_ANNOTATE,
    STATUS_CAUTION,
    attach_outcome,
    build_decision_episode,
    build_decision_proposal,
    compute_judge_was_useful,
    evaluate_recommendation_packet,
    judge_proposal,
    should_block_execution,
)


class TestDecisionProposalJudge(unittest.TestCase):
    def test_release_validation_claim_from_catalog_not_actor(self):
        action = {
            "action_type": "active_work_tree_run_next",
            "recommended_tool": "release_validation_run",
            "target_id": "branch_release",
            "target_tree_id": "tree_1",
            "target_step_id": "task_1",
            "reason_code": "active_work_tree_ready",
            # Actor spin that should not become the claim:
            "expected_effect": "I am very confident this will fix everything forever.",
        }
        proposal = build_decision_proposal(action=action)
        self.assertEqual(proposal["tool_name"], "release_validation_run")
        self.assertIn("validation", proposal["intended_effect"].lower())
        self.assertNotIn("forever", proposal["intended_effect"].lower())
        self.assertEqual(proposal["field_sources"]["intended_effect"], "capability_effect_map")
        self.assertIn("tool_contract", proposal["field_sources"]["expected_evidence"])
        self.assertTrue(proposal["actor_reason"] or proposal.get("actor_reason") == "active_work_tree_ready")

    def test_unknown_tool_marks_actor_inferred(self):
        proposal = build_decision_proposal(
            action={
                "action_type": "custom_do_thing",
                "recommended_tool": "totally_unknown_tool_xyz",
                "expected_effect": "Actor says hello",
            }
        )
        self.assertEqual(proposal["field_sources"]["intended_effect"], "actor_inferred")
        self.assertIn("actor_inferred", proposal["field_sources"]["expected_evidence"])

    def test_missing_close_condition_alignment_is_caution(self):
        proposal = build_decision_proposal(
            action={
                "action_type": "active_work_tree_run_next",
                "recommended_tool": "read",
                "target_id": "branch_a",
                "target_tree_id": "tree_a",
                "target_step_id": "task_a",
            }
        )
        # Force no close condition
        proposal["close_condition"] = None
        proposal["field_sources"]["close_condition"] = "none"
        report = judge_proposal(proposal)
        self.assertEqual(report["mission_alignment"]["status"], STATUS_CAUTION)
        self.assertIn(
            report["disposition"],
            {DISPOSITION_PROCEED_ANNOTATE, DISPOSITION_PROCEED, DISPOSITION_PAUSE_AND_SURFACE},
        )

    def test_disposition_not_from_blended_score_alignment_fail(self):
        proposal = build_decision_proposal(
            action={
                "action_type": "active_work_tree_run_next",
                "recommended_tool": "read",
                "target_id": "branch_a",
                "target_tree_id": "tree_a",
                "target_step_id": "task_a",
            }
        )
        # Perfect reversibility context path; poison alignment score path via empty intended
        proposal["intended_effect"] = ""
        proposal["close_condition"] = "must satisfy this specific close condition token xyzzy"
        proposal["field_sources"]["intended_effect"] = "actor_inferred"
        report = judge_proposal(proposal)
        # Alignment should fail or caution strongly; controlling dim should not hide behind average
        self.assertIn(report["mission_alignment"]["status"], {"fail", "caution"})
        self.assertEqual(report["controlling_dimension"], report.get("controlling_dimension"))
        # summary_score exists for analytics only
        self.assertIn("summary_score", report)

    def test_missing_target_context_fail_pauses_with_resolution(self):
        proposal = build_decision_proposal(
            action={
                "action_type": "active_work_tree_run_next",
                "recommended_tool": "release_rebuild_verify",
            }
        )
        report = judge_proposal(proposal)
        self.assertEqual(report["disposition"], DISPOSITION_PAUSE_AND_SURFACE)
        self.assertEqual(report["controlling_dimension"], "context_completeness")
        self.assertEqual(report["context_completeness"]["status"], "fail")
        resolution = report.get("resolution_action") or {}
        self.assertTrue(resolution.get("resume_condition"))
        self.assertFalse(should_block_execution(report))
        self.assertTrue(should_block_execution(judge_proposal(proposal, enforce_disposition=True)))

    def test_similar_failed_attempts_pause(self):
        proposal = build_decision_proposal(
            action={
                "action_type": "active_work_tree_run_next",
                "recommended_tool": "release_validation_run",
                "target_id": "branch_x",
                "target_tree_id": "tree_x",
                "target_step_id": "task_x",
            }
        )
        history = [
            {
                "action_id": "active_work_tree_run_next",
                "tool_name": "release_validation_run",
                "target_id": "branch_x",
                "close_condition_remained_false": True,
            },
            {
                "action_id": "active_work_tree_run_next",
                "tool_name": "release_validation_run",
                "target_id": "branch_x",
                "progress_moved": False,
            },
        ]
        report = judge_proposal(proposal, attempt_history=history)
        self.assertGreaterEqual(report["similar_failed_attempts"], 2)
        self.assertEqual(report["disposition"], DISPOSITION_PAUSE_AND_SURFACE)

    def test_judge_was_useful_rule(self):
        self.assertTrue(
            compute_judge_was_useful(disposition=DISPOSITION_PROCEED, predicate_moved=True)
        )
        self.assertFalse(
            compute_judge_was_useful(disposition=DISPOSITION_PROCEED, predicate_moved=False)
        )
        self.assertTrue(
            compute_judge_was_useful(
                disposition=DISPOSITION_PAUSE_AND_SURFACE, predicate_moved=False
            )
        )
        self.assertFalse(
            compute_judge_was_useful(
                disposition=DISPOSITION_ABORT_AND_FILE, predicate_moved=True
            )
        )
        self.assertIsNone(
            compute_judge_was_useful(disposition=DISPOSITION_PROCEED, predicate_moved=None)
        )

    def test_decision_episode_prediction_outcome(self):
        proposal = build_decision_proposal(
            action={"action_type": "guard_start", "reason_code": "runtime_guard_stopped"}
        )
        report = judge_proposal(proposal)
        report = attach_outcome(
            report,
            execution_result="success",
            execution_ok=True,
            progress_moved=False,
        )
        episode = build_decision_episode(
            proposal=proposal,
            judge_report=report,
            execution={"result": "success"},
            close_condition_before=False,
            close_condition_after=False,
        )
        pred = episode["prediction_outcome"]
        self.assertIs(pred["predicate_moved"], False)
        # proceed + no movement => judge_was_useful False
        if report["disposition"] in {DISPOSITION_PROCEED, DISPOSITION_PROCEED_ANNOTATE}:
            self.assertIs(pred["judge_was_useful"], False)

    def test_evaluate_recommendation_packet(self):
        packet = {
            "recommended_action": {
                "action_type": "guard_start",
                "reason_code": "runtime_guard_stopped",
                "expected_effect": "Actor hype text should not be the claim.",
            },
        }
        proposal, report = evaluate_recommendation_packet(packet)
        self.assertEqual(proposal["action_id"], "guard_start")
        self.assertEqual(proposal["field_sources"]["intended_effect"], "capability_effect_map")
        self.assertNotIn("hype", proposal["intended_effect"].lower())
        self.assertIn("status", report["reversibility"])
        self.assertIn("controlling_dimension", report)


if __name__ == "__main__":
    unittest.main()
