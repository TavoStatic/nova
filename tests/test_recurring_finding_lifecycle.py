import unittest

from services.recurring_finding_lifecycle import (
    BRANCH_LIFECYCLE_KEY,
    KEY_FINDING,
    KEY_PRIOR_SATISFACTION_FINGERPRINT,
    KEY_PRIOR_SATISFACTION_STATUS,
    KEY_REOPENED_REASON,
    KEY_SATISFACTION_FINGERPRINT,
    KEY_SATISFACTION_STATUS,
    KEY_VERSION,
    REOPEN_ACTIVE_SIGNAL,
    REOPEN_RECURRING_PRESSURE,
    STATUS_OPEN,
    STATUS_SATISFIED,
    bump_branch_reopen,
    classify_existing_item,
    classify_task_meta,
    DECISION_ACTIVE_UPDATE,
    fingerprint_from_parts,
    finding_key_from_meta,
    initial_task_meta,
    read_branch_lifecycle,
    read_task_state,
    reopen_task_meta,
    stamp_branch_satisfied,
    stamp_satisfaction,
    summarize_feed_pressure,
    task_finding_key,
    update_open_fingerprint,
)


class TestRecurringFindingLifecycle(unittest.TestCase):
    def test_initial_task_meta_sets_open_version_one(self):
        meta = initial_task_meta(finding_key="order-1", satisfaction_fingerprint="fp-1")

        self.assertEqual(meta[KEY_FINDING], "order-1")
        self.assertEqual(meta[KEY_VERSION], 1)
        self.assertEqual(meta[KEY_SATISFACTION_STATUS], STATUS_OPEN)
        self.assertEqual(meta[KEY_SATISFACTION_FINGERPRINT], "fp-1")

    def test_stamp_satisfaction_records_completion(self):
        meta = stamp_satisfaction(
            {KEY_FINDING: "order-1"},
            satisfaction_fingerprint="fp-1",
            completion_action="removed_unused_wrapper",
        )

        self.assertEqual(meta[KEY_SATISFACTION_STATUS], STATUS_SATISFIED)
        self.assertEqual(meta[KEY_SATISFACTION_FINGERPRINT], "fp-1")
        self.assertEqual(meta["recurring_finding_completion_action"], "removed_unused_wrapper")
        self.assertTrue(meta["recurring_finding_satisfied_at"])

    def test_reopen_task_meta_versions_and_preserves_prior(self):
        prior = stamp_satisfaction(
            initial_task_meta(finding_key="order-1", satisfaction_fingerprint="fp-1"),
            satisfaction_fingerprint="fp-1",
            completion_action="removed_unused_wrapper",
        )
        reopened = reopen_task_meta(
            prior,
            finding_key="order-1",
            satisfaction_fingerprint="fp-1",
            reason=REOPEN_RECURRING_PRESSURE,
        )

        self.assertEqual(reopened[KEY_VERSION], 2)
        self.assertEqual(reopened[KEY_SATISFACTION_STATUS], STATUS_OPEN)
        self.assertEqual(reopened[KEY_REOPENED_REASON], REOPEN_RECURRING_PRESSURE)
        self.assertEqual(reopened[KEY_PRIOR_SATISFACTION_FINGERPRINT], "fp-1")
        self.assertEqual(reopened[KEY_PRIOR_SATISFACTION_STATUS], STATUS_SATISFIED)

    def test_read_task_state_supports_legacy_core_thinning_aliases(self):
        state = read_task_state(
            {
                "core_thinning_order_id": "order-legacy",
                "core_thinning_order_version": 3,
                "core_thinning_satisfaction_status": STATUS_SATISFIED,
            }
        )

        self.assertEqual(state[KEY_FINDING], "order-legacy")
        self.assertEqual(state[KEY_VERSION], 3)
        self.assertEqual(state[KEY_SATISFACTION_STATUS], STATUS_SATISFIED)
        self.assertEqual(finding_key_from_meta({"core_thinning_order_id": "order-legacy"}), "order-legacy")

    def test_classify_existing_item_covers_reopen_and_satisfaction(self):
        self.assertEqual(
            classify_existing_item(
                item_status="complete",
                finding_key="a",
                active_finding_keys={"a"},
            ),
            "reopen",
        )
        self.assertEqual(
            classify_existing_item(
                item_status="complete",
                finding_key="a",
                active_finding_keys=set(),
            ),
            "satisfied",
        )
        self.assertEqual(
            classify_existing_item(
                item_status="open",
                finding_key="a",
                active_finding_keys={"a"},
            ),
            "active",
        )
        self.assertEqual(
            classify_existing_item(
                item_status="open",
                finding_key="a",
                active_finding_keys=set(),
            ),
            "inactive_resolve",
        )

    def test_branch_lifecycle_bumps_version_on_reopen(self):
        payload = bump_branch_reopen(
            {"source_key": "signal:release"},
            finding_key="signal:release",
            reason=REOPEN_ACTIVE_SIGNAL,
        )
        lifecycle = read_branch_lifecycle(payload)

        self.assertEqual(lifecycle[KEY_FINDING], "signal:release")
        self.assertEqual(lifecycle[KEY_VERSION], 1)
        self.assertEqual(lifecycle[KEY_REOPENED_REASON], REOPEN_ACTIVE_SIGNAL)
        self.assertIn(BRANCH_LIFECYCLE_KEY, payload)

        payload = bump_branch_reopen(payload, finding_key="signal:release", reason=REOPEN_ACTIVE_SIGNAL)
        lifecycle = read_branch_lifecycle(payload)
        self.assertEqual(lifecycle[KEY_VERSION], 2)

    def test_order_satisfaction_fingerprint_ignores_http_line_and_reason_drift(self):
        from services.core_thinning import _order_satisfaction_key, stamp_core_thinning_task_satisfaction

        order = {
            "kind": "http_surface_candidate",
            "reason": (
                "chat_sessions still has 81 non-shim lines across 12 substantive functions "
                "inside nova_http.py; map this remaining cluster before extraction."
            ),
            "target": {
                "file": "C:/NOVA/nova_http.py",
                "name": "http:chat_sessions:1",
                "theme": "chat_sessions",
                "cluster": 1,
                "start_line": 359,
                "end_line": 441,
                "line_count": 83,
                "function_count": 5,
            },
        }
        drifted = {
            **order,
            "reason": "chat_sessions still has 42 non-shim lines across 5 substantive functions inside nova_http.py.",
            "target": {
                **dict(order["target"]),
                "name": "http:chat_sessions:2",
                "cluster": 2,
                "start_line": 545,
                "end_line": 767,
                "line_count": 223,
                "function_count": 19,
            },
        }
        feed_fingerprint = _order_satisfaction_key(order)
        self.assertEqual(feed_fingerprint, _order_satisfaction_key(drifted))
        task = type("Task", (), {})()
        task.meta = {
            "kind": order["kind"],
            "target": dict(order["target"]),
        }
        stamp_core_thinning_task_satisfaction(task, {"ok": True, "action": "witnessed_http_extraction_boundary"})
        matched = str((task.meta or {}).get("recurring_finding_satisfaction_fingerprint") or "")
        self.assertEqual(matched, feed_fingerprint)

    def test_classify_task_meta_does_not_reopen_completed_http_extract(self):
        meta = stamp_satisfaction(
            initial_task_meta(finding_key="order-extract", satisfaction_fingerprint="fp-extract"),
            satisfaction_fingerprint="fp-extract",
            completion_action="operator_do_not_retry",
        )
        meta["kind"] = "http_surface_extract"
        self.assertEqual(
            classify_task_meta(
                meta=meta,
                item_status="complete",
                active_finding_keys={"order-extract"},
                current_fingerprint="fp-extract-drifted",
            ),
            "satisfied",
        )

    def test_classify_task_meta_reopens_extract_without_stage_closure(self):
        meta = initial_task_meta(finding_key="order-extract", satisfaction_fingerprint="fp-extract")
        meta["kind"] = "http_surface_extract"
        self.assertEqual(
            classify_task_meta(
                meta=meta,
                item_status="complete",
                active_finding_keys={"order-extract"},
                current_fingerprint="fp-extract",
            ),
            "reopen",
        )

    def test_classify_task_meta_closes_witnessed_http_mapping_stage(self):
        meta = stamp_satisfaction(
            initial_task_meta(finding_key="order-http", satisfaction_fingerprint="fp-http"),
            satisfaction_fingerprint="fp-http",
            completion_action="witnessed_http_extraction_boundary",
        )
        self.assertEqual(
            classify_task_meta(
                meta=meta,
                item_status="complete",
                active_finding_keys={"order-http"},
                current_fingerprint="fp-http",
            ),
            "satisfied",
        )

    def test_classify_task_meta_closes_legacy_mapped_http_alias_as_mapping_stage(self):
        meta = stamp_satisfaction(
            initial_task_meta(finding_key="order-http", satisfaction_fingerprint="fp-http"),
            satisfaction_fingerprint="fp-http",
            completion_action="mapped_http_extraction_boundary",
        )
        self.assertEqual(
            classify_task_meta(
                meta=meta,
                item_status="complete",
                active_finding_keys={"order-http"},
                current_fingerprint="fp-http",
            ),
            "satisfied",
        )

    def test_classify_task_meta_reopens_wrapper_when_source_still_reports_it(self):
        meta = stamp_satisfaction(
            initial_task_meta(finding_key="order-wrap", satisfaction_fingerprint="fp-old"),
            satisfaction_fingerprint="fp-new",
            completion_action="removed_unused_wrapper",
        )
        self.assertEqual(
            classify_task_meta(
                meta=meta,
                item_status="complete",
                active_finding_keys={"order-wrap"},
                current_fingerprint="fp-new",
            ),
            "reopen",
        )

    def test_classify_task_meta_detects_fingerprint_update(self):
        meta = initial_task_meta(finding_key="order-1", satisfaction_fingerprint="fp-old")
        self.assertEqual(
            classify_task_meta(
                meta=meta,
                item_status="open",
                active_finding_keys={"order-1"},
                current_fingerprint="fp-new",
            ),
            DECISION_ACTIVE_UPDATE,
        )

    def test_stamp_branch_satisfied_records_branch_completion(self):
        payload = stamp_branch_satisfied({"source_key": "patch:1"}, completion_action="patch_queue_retired")
        lifecycle = read_branch_lifecycle(payload)
        self.assertEqual(lifecycle[KEY_SATISFACTION_STATUS], STATUS_SATISFIED)
        self.assertEqual(lifecycle["recurring_finding_completion_action"], "patch_queue_retired")

    def test_summarize_feed_pressure_surfaces_executable_gap(self):
        summary = summarize_feed_pressure(
            pressure_count=8,
            feed_result={"executable_count": 0, "reopened_count": 0, "status": "deduped"},
        )
        self.assertEqual(summary.get("lifecycle_gap"), "pressure_without_executable_work")
        self.assertFalse(summary.get("pressure_backed_by_executable"))

    def test_summarize_feed_pressure_treats_productive_closure_as_resolved(self):
        summary = summarize_feed_pressure(
            pressure_count=8,
            feed_result={
                "executable_count": 0,
                "reopened_count": 0,
                "satisfied_active_count": 8,
                "status": "deduped",
            },
        )
        self.assertEqual(summary.get("unresolved_pressure_count"), 0)
        self.assertFalse(summary.get("lifecycle_gap"))
        self.assertTrue(summary.get("pressure_backed_by_executable"))

    def test_update_open_fingerprint_marks_material_change(self):
        meta = update_open_fingerprint(
            initial_task_meta(finding_key="order-1", satisfaction_fingerprint="fp-old"),
            satisfaction_fingerprint="fp-new",
        )
        self.assertEqual(meta[KEY_SATISFACTION_FINGERPRINT], "fp-new")
        self.assertEqual(meta[KEY_SATISFACTION_STATUS], STATUS_OPEN)
        self.assertEqual(meta[KEY_PRIOR_SATISFACTION_FINGERPRINT], "fp-old")

    def test_task_finding_key_composes_branch_and_title(self):
        self.assertEqual(task_finding_key(branch_finding_key="signal:release", task_title="Read status"), "signal:release:Read status")

    def test_fingerprint_from_parts_is_stable_slug(self):
        first = fingerprint_from_parts(["Wrapper", "nova_core.py", "render"])
        second = fingerprint_from_parts(["wrapper", "nova_core.py", "render"])
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[a-z0-9-]+$")