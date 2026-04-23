import unittest
from pathlib import Path

from services.patch_control import PATCH_CONTROL_SERVICE


class TestPatchControlService(unittest.TestCase):
    def test_patch_preview_list_action_uses_preview_fallback_and_readiness(self):
        ok, msg, extra, detail = PATCH_CONTROL_SERVICE.patch_preview_list_action(
            patch_status_payload_fn=lambda: {"ok": True, "previews_total": 1},
            preview_summaries_fn=lambda limit: [{"name": "preview_a.txt", "status": "eligible", "decision": "pending"}],
            patch_action_readiness_payload_fn=lambda patch: {"default_preview": "preview_a.txt"},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "patch_preview_list_ok")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("previews") or [])[0].get("name"), "preview_a.txt")
        self.assertEqual((extra.get("patch_action_readiness") or {}).get("default_preview"), "preview_a.txt")

    def test_pulse_status_action_returns_rendered_text_and_pending_state(self):
        ok, msg, extra, detail = PATCH_CONTROL_SERVICE.pulse_status_action(
            build_pulse_payload_fn=lambda: {"generated_at": "2026-03-26 23:10:00"},
            render_nova_pulse_fn=lambda pulse: f"Nova Pulse - {pulse['generated_at']}",
            update_now_pending_payload_fn=lambda: {"ok": False, "pending": False},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "pulse_status_ok")
        self.assertEqual(detail, msg)
        self.assertIn("Nova Pulse", extra.get("text", ""))
        self.assertFalse(extra.get("update_now_pending", {}).get("pending", True))

    def test_patch_action_readiness_payload_explains_preview_controls(self):
        with unittest.mock.patch("pathlib.Path.exists", return_value=True):
            payload = PATCH_CONTROL_SERVICE.patch_action_readiness_payload(
                {
                    "enabled": True,
                    "strict_manifest": True,
                    "behavioral_check": True,
                    "tests_available": True,
                    "last_preview_name": "preview_a.txt",
                    "previews": [
                        {"name": "preview_a.txt", "status": "eligible", "decision": "approved"},
                        {"name": "preview_b.txt", "status": "rejected: non-forward revision", "decision": "pending"},
                    ],
                },
                preview_summaries_fn=lambda limit: [],
                show_preview_fn=lambda name: "Patch Preview\nZip: teach_proposal_1.zip\nStatus: eligible" if name == "preview_a.txt" else "Patch Preview\nZip: teach_proposal_2.zip\nStatus: rejected: non-forward revision",
                updates_dir=Path("c:/Nova/updates"),
            )

        approved = ((payload.get("by_preview") or {}).get("preview_a.txt") or {})
        blocked = ((payload.get("by_preview") or {}).get("preview_b.txt") or {})
        self.assertEqual(payload.get("default_preview"), "preview_a.txt")
        self.assertTrue(((approved.get("apply") or {}).get("enabled")))
        self.assertFalse(((blocked.get("apply") or {}).get("enabled")))
        self.assertIn("not eligible", ((blocked.get("apply") or {}).get("reason") or "").lower())

    def test_patch_preview_target_prefers_payload_then_first_preview(self):
        self.assertEqual(
            PATCH_CONTROL_SERVICE.patch_preview_target({"preview": "preview_a.txt"}, [{"name": "preview_b.txt"}]),
            "preview_a.txt",
        )
        self.assertEqual(
            PATCH_CONTROL_SERVICE.patch_preview_target({}, [{"name": "preview_b.txt"}]),
            "preview_b.txt",
        )

    def test_patch_preview_apply_blocks_unapproved_preview(self):
        ok, msg, extra, detail = PATCH_CONTROL_SERVICE.patch_preview_apply(
            {"preview": "preview_a.txt"},
            preview_target_fn=lambda payload: "preview_a.txt",
            preview_entry_fn=lambda target: {"name": target, "status": "eligible", "decision": "pending"},
            patch_control_state_fn=lambda include_readiness=True: {"patch": {"ok": True}},
            show_preview_fn=lambda target: "Patch Preview\nZip: demo.zip",
            updates_dir=Path("c:/Nova/updates"),
            patch_apply_fn=lambda path: "Patch applied",
        )

        self.assertFalse(ok)
        self.assertEqual(msg, "patch_preview_not_approved")
        self.assertIn("must be approved", extra.get("text", ""))
        self.assertEqual(detail, "patch_preview_not_approved:preview_a.txt")

    def test_update_now_confirm_requires_patch_applied_prefix(self):
        ok, msg, extra = PATCH_CONTROL_SERVICE.update_now_confirm(
            "Patch applied: 1 file(s).",
            pending_payload={"pending": False},
            patch_payload={"ok": True},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "update_now_confirm_ok")
        self.assertFalse(extra.get("pending", {}).get("pending", True))

    def test_update_now_confirm_action_uses_payload_token(self):
        seen = {}

        ok, msg, extra, detail = PATCH_CONTROL_SERVICE.update_now_confirm_action(
            {"token": "abcd1234"},
            tool_update_now_confirm_fn=lambda token: seen.update({"token": token}) or "Patch applied: 1 file(s).",
            update_now_pending_payload_fn=lambda: {"pending": False},
            patch_status_payload_fn=lambda: {"ok": True},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "update_now_confirm_ok")
        self.assertEqual(detail, msg)
        self.assertEqual(seen.get("token"), "abcd1234")
        self.assertTrue(extra.get("patch", {}).get("ok"))

    def test_update_now_cancel_action_returns_pending_payload(self):
        ok, msg, extra, detail = PATCH_CONTROL_SERVICE.update_now_cancel_action(
            tool_update_now_cancel_fn=lambda: "Cancelled.",
            update_now_pending_payload_fn=lambda: {"ok": False, "pending": False},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "update_now_cancel_ok")
        self.assertEqual(detail, msg)
        self.assertIn("Cancelled.", extra.get("text", ""))


if __name__ == "__main__":
    unittest.main()