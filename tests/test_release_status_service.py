import json
import os
import tempfile
import unittest
import zipfile
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

    def test_status_payload_filters_by_artifact_kind(self):
        with tempfile.TemporaryDirectory() as td:
            ledger_path = Path(td) / "release_ledger.jsonl"
            ledger_path.write_text(
                "\n".join([
                    json.dumps({
                        "recorded_at": "2026-05-26T10:00:00-05:00",
                        "event": "build",
                        "artifact_kind": "package-zip",
                        "artifact_name": "nova.zip",
                        "artifact_path": "C:/Nova/nova.zip",
                        "artifact_version": "2026.05.26",
                        "release_channel": "rc",
                    }),
                    json.dumps({
                        "recorded_at": "2026-05-26T11:00:00-05:00",
                        "event": "build",
                        "artifact_kind": "windows-installer",
                        "artifact_name": "nova.exe",
                        "artifact_path": "C:/Nova/nova.exe",
                        "artifact_version": "2026.05.26",
                        "release_channel": "rc",
                        "source_package_artifact_path": "C:/Nova/nova.zip",
                    }),
                    json.dumps({
                        "recorded_at": "2026-05-26T11:01:00-05:00",
                        "event": "verify",
                        "artifact_kind": "windows-installer",
                        "artifact_name": "nova.exe",
                        "artifact_path": "C:/Nova/nova.exe",
                        "artifact_version": "2026.05.26",
                        "release_channel": "rc",
                        "verification_result": "pass",
                    }),
                    json.dumps({
                        "recorded_at": "2026-05-26T11:02:00-05:00",
                        "event": "promotion",
                        "artifact_kind": "windows-installer",
                        "artifact_name": "nova.exe",
                        "artifact_path": "C:/Nova/nova.exe",
                        "artifact_version": "2026.05.26",
                        "release_channel": "rc",
                        "validation_result": "pass-with-notes",
                    }),
                ]),
                encoding="utf-8",
            )

            package_payload = RELEASE_STATUS_SERVICE.status_payload(ledger_path)
            installer_payload = RELEASE_STATUS_SERVICE.status_payload(ledger_path, artifact_kind="windows-installer")

        self.assertEqual(package_payload.get("artifact_kind"), "package-zip")
        self.assertEqual(package_payload.get("latest_artifact_name"), "nova.zip")
        self.assertEqual(package_payload.get("latest_readiness_state"), "needs-verification")
        self.assertEqual(installer_payload.get("artifact_kind"), "windows-installer")
        self.assertEqual(installer_payload.get("latest_artifact_name"), "nova.exe")
        self.assertEqual(installer_payload.get("latest_readiness_state"), "ready-with-notes")
        self.assertEqual(installer_payload.get("latest_source_package_artifact_path"), "C:/Nova/nova.zip")
        self.assertEqual(installer_payload.get("latest_source_package_artifact_name"), "nova.zip")

    def test_status_payload_filters_kind_before_recent_display_limit(self):
        with tempfile.TemporaryDirectory() as td:
            ledger_path = Path(td) / "release_ledger.jsonl"
            rows = [
                {
                    "recorded_at": "2026-05-26T10:00:00-05:00",
                    "event": "build",
                    "artifact_kind": "windows-installer",
                    "artifact_name": "nova.exe",
                    "artifact_path": "C:/Nova/nova.exe",
                    "artifact_version": "2026.05.26",
                    "release_channel": "rc",
                },
                {
                    "recorded_at": "2026-05-26T10:01:00-05:00",
                    "event": "verify",
                    "artifact_kind": "windows-installer",
                    "artifact_name": "nova.exe",
                    "artifact_path": "C:/Nova/nova.exe",
                    "artifact_version": "2026.05.26",
                    "release_channel": "rc",
                    "verification_result": "pass",
                },
                {
                    "recorded_at": "2026-05-26T10:02:00-05:00",
                    "event": "promotion",
                    "artifact_kind": "windows-installer",
                    "artifact_name": "nova.exe",
                    "artifact_path": "C:/Nova/nova.exe",
                    "artifact_version": "2026.05.26",
                    "release_channel": "rc",
                    "validation_result": "pass-with-notes",
                },
            ]
            for index in range(20):
                rows.append(
                    {
                        "recorded_at": f"2026-05-26T11:{index:02d}:00-05:00",
                        "event": "verify",
                        "artifact_kind": "package-zip",
                        "artifact_name": f"nova-{index}.zip",
                        "artifact_path": f"C:/Nova/nova-{index}.zip",
                        "artifact_version": f"2026.05.26.{index}",
                        "release_channel": "rc",
                        "verification_result": "pass",
                    }
                )
            ledger_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

            installer_payload = RELEASE_STATUS_SERVICE.status_payload(ledger_path, limit=3, artifact_kind="windows-installer")

        self.assertEqual(installer_payload.get("latest_artifact_name"), "nova.exe")
        self.assertEqual(installer_payload.get("latest_readiness_state"), "ready-with-notes")
        self.assertLessEqual(len(installer_payload.get("recent_entries") or []), 3)

    def test_status_payload_marks_release_stale_when_source_changed_after_build(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger_path = root / "runtime" / "exports" / "release_packages" / "release_ledger.jsonl"
            ledger_path.parent.mkdir(parents=True)
            ledger_path.write_text(
                "\n".join([
                    json.dumps({
                        "recorded_at": "2026-03-30T16:09:45.0928881-05:00",
                        "event": "build",
                        "artifact_name": "artifact-a.zip",
                        "artifact_path": str(ledger_path.parent / "artifact-a.zip"),
                        "artifact_version": "2026.03.30.1",
                        "release_channel": "rc",
                        "release_label": "auto-version-check",
                    }),
                    json.dumps({
                        "recorded_at": "2026-03-30T16:12:10.0000000-05:00",
                        "event": "verify",
                        "artifact_name": "artifact-a.zip",
                        "artifact_path": str(ledger_path.parent / "artifact-a.zip"),
                        "artifact_version": "2026.03.30.1",
                        "release_channel": "rc",
                        "release_label": "auto-version-check",
                        "verification_result": "pass",
                    }),
                ]),
                encoding="utf-8",
            )
            source_file = root / "nova_core.py"
            source_file.write_text("print('changed')\n", encoding="utf-8")
            os.utime(source_file, (1900000000, 1900000000))

            payload = RELEASE_STATUS_SERVICE.status_payload(ledger_path, limit=5, source_root=root)

        self.assertEqual(payload.get("latest_readiness_state"), "source-changed-after-build")
        self.assertFalse(payload.get("latest_ready_to_ship"))
        self.assertTrue(payload.get("latest_artifact_stale"))
        self.assertTrue(payload.get("latest_source_changed_after_build"))
        self.assertIn("nova_core.py", payload.get("latest_source_changed_after_build_sample") or [])

    def test_status_payload_ignores_mtime_only_touch_when_artifact_content_matches(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package_dir = root / "runtime" / "exports" / "release_packages"
            ledger_path = package_dir / "release_ledger.jsonl"
            package_dir.mkdir(parents=True)
            artifact_path = package_dir / "artifact-a.zip"
            source_file = root / "nova_core.py"
            source_file.write_bytes(b"print('same')\n")
            with zipfile.ZipFile(artifact_path, "w") as archive:
                archive.writestr("artifact-a/package_manifest.json", "{}")
                archive.writestr("artifact-a/nova_core.py", b"print('same')\n")
            ledger_path.write_text(
                "\n".join([
                    json.dumps({
                        "recorded_at": "2026-03-30T16:09:45.0928881-05:00",
                        "event": "build",
                        "artifact_name": "artifact-a.zip",
                        "artifact_path": str(artifact_path),
                        "artifact_version": "2026.03.30.1",
                        "release_channel": "rc",
                        "release_label": "auto-version-check",
                    }),
                    json.dumps({
                        "recorded_at": "2026-03-30T16:12:10.0000000-05:00",
                        "event": "verify",
                        "artifact_name": "artifact-a.zip",
                        "artifact_path": str(artifact_path),
                        "artifact_version": "2026.03.30.1",
                        "release_channel": "rc",
                        "release_label": "auto-version-check",
                        "verification_result": "pass",
                    }),
                    json.dumps({
                        "recorded_at": "2026-03-30T16:20:20.0000000-05:00",
                        "event": "promotion",
                        "artifact_name": "artifact-a.zip",
                        "artifact_path": str(artifact_path),
                        "artifact_version": "2026.03.30.1",
                        "release_channel": "rc",
                        "release_label": "auto-version-check",
                        "validation_result": "pass",
                    }),
                ]),
                encoding="utf-8",
            )
            os.utime(source_file, (1900000000, 1900000000))

            payload = RELEASE_STATUS_SERVICE.status_payload(ledger_path, limit=5, source_root=root)

        self.assertEqual(payload.get("latest_readiness_state"), "ready")
        self.assertTrue(payload.get("latest_ready_to_ship"))
        self.assertFalse(payload.get("latest_artifact_stale"))
        self.assertFalse(payload.get("latest_source_changed_after_build"))
        self.assertEqual(payload.get("latest_source_freshness_basis"), "content")
        self.assertEqual(payload.get("latest_source_touched_after_build_count"), 1)
        self.assertEqual(payload.get("latest_source_content_unchanged_after_build_count"), 1)

    def test_status_payload_ignores_local_handoff_dirs_after_build(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger_path = root / "runtime" / "exports" / "release_packages" / "release_ledger.jsonl"
            ledger_path.parent.mkdir(parents=True)
            ledger_path.write_text(
                "\n".join([
                    json.dumps({
                        "recorded_at": "2026-03-30T16:09:45.0928881-05:00",
                        "event": "build",
                        "artifact_name": "artifact-a.zip",
                        "artifact_path": str(ledger_path.parent / "artifact-a.zip"),
                        "artifact_version": "2026.03.30.1",
                        "release_channel": "rc",
                        "release_label": "auto-version-check",
                    }),
                    json.dumps({
                        "recorded_at": "2026-03-30T16:12:10.0000000-05:00",
                        "event": "verify",
                        "artifact_name": "artifact-a.zip",
                        "artifact_path": str(ledger_path.parent / "artifact-a.zip"),
                        "artifact_version": "2026.03.30.1",
                        "release_channel": "rc",
                        "release_label": "auto-version-check",
                        "verification_result": "pass",
                    }),
                ]),
                encoding="utf-8",
            )
            source_file = root / "nova_core.py"
            source_file.write_text("print('stable')\n", encoding="utf-8")
            os.utime(source_file, (1700000000, 1700000000))

            terminals_file = root / "terminals" / "3.txt"
            terminals_file.parent.mkdir(parents=True)
            terminals_file.write_text("pid: 1\n", encoding="utf-8")
            os.utime(terminals_file, (1900000000, 1900000000))

            agent_tools_file = root / "agent-tools" / "probe.json"
            agent_tools_file.parent.mkdir(parents=True)
            agent_tools_file.write_text("{}", encoding="utf-8")
            os.utime(agent_tools_file, (1900000000, 1900000000))

            handoff_file = root / "nova_grok.md"
            handoff_file.write_text("# handoff\n", encoding="utf-8")
            os.utime(handoff_file, (1900000000, 1900000000))

            payload = RELEASE_STATUS_SERVICE.status_payload(ledger_path, limit=5, source_root=root)

        self.assertNotEqual(payload.get("latest_readiness_state"), "source-changed-after-build")
        self.assertFalse(payload.get("latest_source_changed_after_build"))
        self.assertFalse(payload.get("latest_artifact_stale"))
        self.assertNotIn("terminals/3.txt", payload.get("latest_source_changed_after_build_sample") or [])
        self.assertNotIn("agent-tools/probe.json", payload.get("latest_source_changed_after_build_sample") or [])
        self.assertNotIn("nova_grok.md", payload.get("latest_source_changed_after_build_sample") or [])


if __name__ == "__main__":
    unittest.main()
