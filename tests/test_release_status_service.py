import json
import tempfile
import unittest
from pathlib import Path

from services.release_status import RELEASE_STATUS_SERVICE


class TestReleaseStatusService(unittest.TestCase):
    def test_status_payload_summarizes_latest_build_and_promotion(self):
        with tempfile.TemporaryDirectory() as td:
            ledger_path = Path(td) / "release_ledger.jsonl"
            ledger_path.write_text(
                "\n".join([
                    json.dumps({
                        "recorded_at": "2026-03-30T16:09:45.0928881-05:00",
                        "event": "build",
                        "artifact_name": "artifact-a.zip",
                        "artifact_path": "C:/Nova/runtime/exports/release_packages/artifact-a.zip",
                        "artifact_version": "2026.03.30.1",
                        "release_channel": "rc",
                        "release_label": "auto-version-check",
                        "validation_record_seed_path": "C:/Nova/runtime/exports/release_packages/validation_records/artifact-a.md",
                    }),
                    json.dumps({
                        "recorded_at": "2026-03-30T16:12:10.0000000-05:00",
                        "event": "verify",
                        "artifact_name": "artifact-a.zip",
                        "artifact_path": "C:/Nova/runtime/exports/release_packages/artifact-a.zip",
                        "artifact_version": "2026.03.30.1",
                        "release_channel": "rc",
                        "release_label": "auto-version-check",
                        "verification_result": "pass",
                        "verification_target_path": "C:/Nova/runtime/exports/release_packages/artifact-a.zip",
                    }),
                    json.dumps({
                        "recorded_at": "2026-03-30T16:20:20.1321285-05:00",
                        "event": "promotion",
                        "artifact_name": "artifact-a.zip",
                        "artifact_path": "C:/Nova/runtime/exports/release_packages/artifact-a.zip",
                        "artifact_version": "2026.03.30.1",
                        "release_channel": "rc",
                        "release_label": "auto-version-check",
                        "validation_result": "pass-with-notes",
                        "validation_note": "fresh machine pending ollama",
                        "follow_up_owner": "release-ops",
                        "validation_machine": "RC-VM-01",
                    }),
                ]),
                encoding="utf-8",
            )

            payload = RELEASE_STATUS_SERVICE.status_payload(ledger_path, limit=5)

        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("latest_state"), "promoted-pass-with-notes")
        self.assertEqual(payload.get("latest_readiness_state"), "ready-with-notes")
        self.assertTrue(payload.get("latest_ready_to_ship"))
        self.assertEqual(payload.get("latest_version"), "2026.03.30.1")
        self.assertEqual(payload.get("latest_verified_at"), "2026-03-30T16:12:10.0000000-05:00")
        self.assertEqual(payload.get("latest_validation_result"), "pass-with-notes")
        self.assertEqual(payload.get("latest_follow_up_owner"), "release-ops")
        self.assertEqual(payload.get("latest_validation_machine"), "RC-VM-01")
        self.assertEqual(len(payload.get("recent_entries") or []), 3)


if __name__ == "__main__":
    unittest.main()