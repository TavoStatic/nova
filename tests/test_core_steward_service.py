import unittest

from services import core_steward


class TestCoreStewardService(unittest.TestCase):
    def test_build_payload_flags_repair_when_required_checks_fail(self):
        payload = core_steward.build_core_steward_payload(
            preflight_checks=[
                {"name": "file:policy.json", "ok": False, "required": True, "info": "missing"},
                {"name": "dir:runtime", "ok": True, "required": True, "info": "ok"},
            ],
            runtime_health={
                "heartbeat": {"ok": False, "info": "missing"},
                "core_state": {"ok": True, "info": "pid=123"},
                "ollama": {"ok": False, "info": "status=503"},
            },
            pulse_payload={"last_fallback_overuse_score": 0.82, "approved_eligible_previews": 1},
            autonomy_maintenance={"runtime_worker": {"last_cycle_status": "stopped", "interval_sec": 300}},
            kidney_summary={"mode": "observe", "candidate_count": 4},
        )

        self.assertEqual(payload.get("level"), "repair")
        self.assertGreaterEqual(len(payload.get("maintenance_queue") or []), 4)
        self.assertIn("file:policy.json", payload.get("doctor", {}).get("required_failed") or [])

    def test_render_core_steward_includes_queue_and_score(self):
        rendered = core_steward.render_core_steward(
            {
                "generated_at": "2026-04-05 12:00:00",
                "score": 91,
                "level": "strong",
                "summary": "core surfaces look stable",
                "doctor": {"required_failed_count": 0},
                "runtime": {
                    "heartbeat": {"ok": True, "info": "age=1s"},
                    "core_state": {"ok": True, "info": "pid=321"},
                    "ollama": {"ok": True, "info": "status=200"},
                },
                "pulse": {"fallback_overuse_score": 0.12},
                "kidney": {"mode": "observe", "candidate_count": 0},
                "autonomy_maintenance": {"worker_status": "running", "interval_sec": 300},
                "maintenance_queue": [
                    {
                        "priority": "low",
                        "title": "Review validated updates",
                        "reason": "1 approved preview is ready.",
                        "command": "update now",
                    }
                ],
            }
        )

        self.assertIn("Core Steward - 2026-04-05 12:00:00", rendered)
        self.assertIn("Strength score: 91/100", rendered)
        self.assertIn("Review validated updates", rendered)

    def test_build_core_steward_gates_blocks_patch_and_release_when_level_is_watch(self):
        gates = core_steward.build_core_steward_gates(
            core_steward={"level": "watch", "summary": "doctor:2 required check(s) failing"},
            patch_summary={"enabled": True, "ready_for_validated_apply": True},
            release_status={"latest_ready_to_ship": True, "latest_readiness_note": "ready"},
        )

        self.assertFalse((gates.get("patch_preview_apply") or {}).get("enabled"))
        self.assertFalse((gates.get("release_promotion") or {}).get("enabled"))
        self.assertIn("Core Steward is watch", (gates.get("patch_preview_apply") or {}).get("reason") or "")

    def test_build_core_steward_gates_allows_release_when_ready_and_strong(self):
        gates = core_steward.build_core_steward_gates(
            core_steward={"level": "strong", "summary": "core surfaces look stable"},
            patch_summary={"enabled": True, "ready_for_validated_apply": True},
            release_status={"latest_ready_to_ship": True, "latest_readiness_note": "ready"},
        )

        self.assertTrue((gates.get("patch_preview_apply") or {}).get("enabled"))
        self.assertTrue((gates.get("release_promotion") or {}).get("enabled"))

    def test_build_payload_keeps_runtime_strong_when_pressure_is_only_training_and_enforced_cleanup(self):
        payload = core_steward.build_core_steward_payload(
            preflight_checks=[
                {"name": "file:policy.json", "ok": True, "required": True, "info": "ok"},
            ],
            runtime_health={
                "heartbeat": {"ok": True, "info": "age=1s"},
                "core_state": {"ok": True, "info": "pid=123"},
                "ollama": {"ok": True, "info": "status=200"},
            },
            pulse_payload={"last_fallback_overuse_score": 0.97, "approved_eligible_previews": 0},
            autonomy_maintenance={
                "runtime_worker": {"last_cycle_status": "ok", "interval_sec": 300},
                "last_generated_queue_run": {"latest_report_status": "warning", "status": "ok"},
            },
            kidney_summary={"mode": "enforce", "candidate_count": 25, "archive_count": 22, "delete_count": 3},
        )

        self.assertEqual(payload.get("score"), 100)
        self.assertEqual(payload.get("level"), "strong")
        self.assertEqual(payload.get("summary"), "core surfaces look stable")
        queue_titles = [item.get("title") for item in (payload.get("maintenance_queue") or [])]
        self.assertIn("Review fallback training pressure", queue_titles)
        self.assertIn("Review cleanup pressure", queue_titles)


if __name__ == "__main__":
    unittest.main()