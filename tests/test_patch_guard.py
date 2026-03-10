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


if __name__ == "__main__":
    unittest.main()
