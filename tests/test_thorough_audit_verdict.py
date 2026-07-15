import unittest

from services.thorough_audit_verdict import build_hard_fail_report, live_closure_hard_fail


class TestThoroughAuditVerdict(unittest.TestCase):
    def test_live_closure_hard_fail_when_gap_roots_without_semantic_live_gaps(self):
        live_closure = {
            "ok": False,
            "gap_count": 33,
            "gap_roots": ["release", "memory_identity"],
            "roots": [
                {"root_id": "release", "live_gaps": [], "ok": False},
                {"root_id": "memory_identity", "live_gaps": [], "ok": False},
            ],
        }
        self.assertTrue(live_closure_hard_fail(live_closure))

    def test_build_hard_fail_report_fails_on_gap_count_not_only_semantic_gaps(self):
        report = build_hard_fail_report(
            profiles={"code_ok": True, "ok": True},
            wiring={"ok": True},
            live_closure={
                "ok": False,
                "gap_count": 3,
                "gap_roots": ["a", "b", "c"],
                "roots": [{"root_id": "a", "live_gaps": []}],
            },
            regression={"failure_active": False},
            mission={"autonomy_blocked": False},
        )
        self.assertTrue(report["hard_fail"])
        self.assertTrue(report["closure_fail"])
        self.assertEqual(report["semantic_live_gap_count"], 0)
        self.assertEqual(report["gap_count"], 3)

    def test_build_hard_fail_report_passes_when_closure_ok(self):
        report = build_hard_fail_report(
            profiles={"code_ok": True, "ok": True},
            wiring={"ok": True},
            live_closure={"ok": True, "gap_count": 0, "gap_roots": [], "roots": []},
            regression={"failure_active": False},
            mission={"autonomy_blocked": False},
        )
        self.assertFalse(report["hard_fail"])


if __name__ == "__main__":
    unittest.main()