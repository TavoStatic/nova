import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import nova_core


class TestPatchGuard(unittest.TestCase):
    def _write_zip(self, zip_path: Path, files: dict[str, str]):
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)

    def _patch_env(self, tmp: Path):
        updates = tmp / "updates"
        snapshots = updates / "snapshots"
        updates.mkdir(parents=True, exist_ok=True)
        snapshots.mkdir(parents=True, exist_ok=True)

        return patch.multiple(
            nova_core,
            BASE_DIR=tmp,
            UPDATES_DIR=updates,
            SNAPSHOTS_DIR=snapshots,
            PATCH_LOG=updates / "patch.log",
            PATCH_REVISION_FILE=updates / "revision.json",
            _log_patch=lambda _msg: None,
        )

    def test_rejects_missing_manifest_in_strict_mode(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            patch_zip = tmp / "patch_no_manifest.zip"
            self._write_zip(patch_zip, {"hello.txt": "world"})

            with self._patch_env(tmp), patch.object(nova_core, "policy_patch", return_value={"strict_manifest": True}):
                result = nova_core.patch_apply(str(patch_zip))

            self.assertIn("Patch rejected", result)
            self.assertIn("incoming revision: missing", result)
            self.assertIn("current revision: 0", result)
            self.assertIn("required base: not specified", result)
            self.assertIn("current base: 0", result)
            self.assertIn("strict mode: on", result)

    def test_rejects_downgrade_revision(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            patch_zip = tmp / "patch_downgrade.zip"
            manifest = {"patch_revision": 2, "min_base_revision": 0}
            self._write_zip(
                patch_zip,
                {
                    "nova_patch.json": json.dumps(manifest),
                    "hello.txt": "world",
                },
            )

            with self._patch_env(tmp), patch.object(nova_core, "policy_patch", return_value={"strict_manifest": True}):
                nova_core._write_patch_revision(3, source="test")
                result = nova_core.patch_apply(str(patch_zip))

            self.assertIn("Patch rejected", result)
            self.assertIn("incoming revision: 2", result)
            self.assertIn("current revision: 3", result)
            self.assertIn("required base: 0", result)
            self.assertIn("current base: 3", result)
            self.assertIn("strict mode: on", result)

    def test_rejects_incompatible_base(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            patch_zip = tmp / "patch_bad_base.zip"
            manifest = {"patch_revision": 5, "min_base_revision": 4}
            self._write_zip(
                patch_zip,
                {
                    "nova_patch.json": json.dumps(manifest),
                    "hello.txt": "world",
                },
            )

            with self._patch_env(tmp), patch.object(nova_core, "policy_patch", return_value={"strict_manifest": True}):
                nova_core._write_patch_revision(2, source="test")
                result = nova_core.patch_apply(str(patch_zip))

            self.assertIn("Patch rejected", result)
            self.assertIn("incoming revision: 5", result)
            self.assertIn("current revision: 2", result)
            self.assertIn("required base: 4", result)
            self.assertIn("current base: 2", result)
            self.assertIn("strict mode: on", result)

    def test_accepts_forward_revision_and_updates_state(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            patch_zip = tmp / "patch_forward.zip"
            snapshot_zip = (tmp / "updates" / "snapshots" / "snapshot_test.zip")
            snapshot_zip.parent.mkdir(parents=True, exist_ok=True)
            snapshot_zip.write_bytes(b"PK\x05\x06" + b"\x00" * 18)

            manifest = {"patch_revision": 4, "min_base_revision": 2}
            self._write_zip(
                patch_zip,
                {
                    "nova_patch.json": json.dumps(manifest),
                    "new_file.txt": "hello",
                },
            )

            with self._patch_env(tmp), \
                patch.object(nova_core, "policy_patch", return_value={"strict_manifest": True}), \
                patch.object(nova_core, "_snapshot_current", return_value=snapshot_zip), \
                patch.object(nova_core, "_py_compile_check", return_value=(True, "ok")):
                nova_core._write_patch_revision(2, source="test")
                result = nova_core.patch_apply(str(patch_zip))

                rev = nova_core._read_patch_revision()

            self.assertIn("Patch applied", result)
            self.assertIn("Revision: 4", result)
            self.assertEqual(rev, 4)
            self.assertTrue((tmp / "new_file.txt").exists())

    def test_behavioral_check_failure_rolls_back_patch(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            original = tmp / "hello.txt"
            original.write_text("before", encoding="utf-8")
            patch_zip = tmp / "patch_behavior_fail.zip"
            snapshot_zip = tmp / "updates" / "snapshots" / "snapshot_test.zip"
            snapshot_zip.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(snapshot_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("hello.txt", "before")

            manifest = {"patch_revision": 2, "min_base_revision": 0}
            self._write_zip(
                patch_zip,
                {
                    "nova_patch.json": json.dumps(manifest),
                    "hello.txt": "after",
                },
            )

            with self._patch_env(tmp), \
                patch.object(nova_core, "policy_patch", return_value={"strict_manifest": True, "behavioral_check": True, "behavioral_check_timeout_sec": 600}), \
                patch.object(nova_core, "_snapshot_current", return_value=snapshot_zip), \
                patch.object(nova_core, "_py_compile_check", return_value=(True, "ok")), \
                patch.object(nova_core, "_behavioral_check", return_value={"ok": False, "summary": "FAILED (failures=1)", "output": "failure"}):
                result = nova_core.patch_apply(str(patch_zip))
                rev_after_rollback = nova_core._read_patch_revision()

            self.assertIn("behavioral check failed", result.lower())
            self.assertIn("Rolled back", result)
            self.assertEqual(original.read_text(encoding="utf-8"), "before")
            self.assertEqual(rev_after_rollback, 0)

    def test_teach_proposal_uses_forward_patch_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            teach_dir = tmp / "updates" / "teaching"
            teach_dir.mkdir(parents=True, exist_ok=True)
            (teach_dir / "examples.jsonl").write_text('{"orig":"hi","corr":"hello"}\n', encoding="utf-8")

            with self._patch_env(tmp):
                result = nova_core._teach_propose_patch("Teach examples proposal")

            self.assertIn("Created proposal", result)
            zips = sorted((tmp / "updates").glob("teach_proposal_*.zip"))
            self.assertTrue(zips)
            with zipfile.ZipFile(zips[-1], "r") as zf:
                manifest = json.loads(zf.read("nova_patch.json").decode("utf-8"))
            self.assertEqual(manifest.get("patch_revision"), 1)
            self.assertEqual(manifest.get("min_base_revision"), 0)

            previews = sorted((tmp / "updates" / "previews").glob("preview_*.txt"))
            self.assertTrue(previews)
            preview_text = previews[-1].read_text(encoding="utf-8")
            self.assertIn("Status: eligible", preview_text)

    def test_patch_status_payload_requires_approved_eligible_preview_for_validated_apply(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            previews_dir = tmp / "updates" / "previews"
            (tmp / "tests").mkdir(parents=True, exist_ok=True)
            previews_dir.mkdir(parents=True, exist_ok=True)
            preview = previews_dir / "preview_a.txt"
            preview.write_text("Patch Preview\nStatus: eligible\n", encoding="utf-8")

            with self._patch_env(tmp), patch.object(
                nova_core,
                "policy_patch",
                return_value={"enabled": True, "strict_manifest": True, "behavioral_check": True, "behavioral_check_timeout_sec": 600},
            ):
                pending_payload = nova_core.patch_status_payload()
                approval_result = nova_core.approve_preview("preview_a.txt", note="safe to promote")
                approved_payload = nova_core.patch_status_payload()

            self.assertEqual(approval_result, "Approved.")
            self.assertTrue(pending_payload.get("pipeline_ready"))
            self.assertEqual(pending_payload.get("previews_eligible"), 1)
            self.assertEqual(pending_payload.get("previews_approved_eligible"), 0)
            self.assertFalse(pending_payload.get("ready_for_validated_apply"))
            self.assertEqual(approved_payload.get("previews_approved_eligible"), 1)
            self.assertTrue(approved_payload.get("ready_for_validated_apply"))


if __name__ == "__main__":
    unittest.main()
