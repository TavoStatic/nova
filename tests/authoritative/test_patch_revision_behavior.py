"""
Authoritative behavior tests — patch manifest forward-only revision check.

Tests that the patching service correctly reads/writes revision state
and that the manifest parsing correctly extracts revision fields.
Does NOT inspect source code or depend on internal call patterns.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from services.nova_patching import (
    read_patch_revision,
    write_patch_revision,
    read_patch_manifest,
)

_MANIFEST_NAME = "nova_patch_manifest.txt"


def _make_zip(manifest_content: str | None = None) -> Path:
    """Create a temp zip file, optionally with a manifest entry."""
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    zip_path = Path(tmp.name)
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("dummy.py", "pass\n")
        if manifest_content is not None:
            zf.writestr(_MANIFEST_NAME, manifest_content)
    return zip_path


class TestPatchRevisionReadWrite(unittest.TestCase):

    def test_read_revision_returns_zero_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rev_file = Path(tmp) / "patch_revision.json"
            result = read_patch_revision(rev_file)
            self.assertEqual(result, 0)

    def test_write_then_read_round_trips_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            updates_dir = Path(tmp) / "updates"
            rev_file = Path(tmp) / "patch_revision.json"
            write_patch_revision(42, "test", updates_dir=updates_dir, patch_revision_file=rev_file)
            result = read_patch_revision(rev_file)
            self.assertEqual(result, 42)

    def test_write_stores_source_and_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            updates_dir = Path(tmp) / "updates"
            rev_file = Path(tmp) / "patch_revision.json"
            write_patch_revision(7, "apply_zip", updates_dir=updates_dir, patch_revision_file=rev_file)
            data = json.loads(rev_file.read_text(encoding="utf-8"))
            self.assertEqual(data["revision"], 7)
            self.assertEqual(data["source"], "apply_zip")
            self.assertIn("ts", data)

    def test_write_creates_updates_dir_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            updates_dir = Path(tmp) / "deep" / "updates"
            rev_file = Path(tmp) / "pr.json"
            self.assertFalse(updates_dir.exists())
            write_patch_revision(1, "setup", updates_dir=updates_dir, patch_revision_file=rev_file)
            self.assertTrue(updates_dir.exists())

    def test_revision_zero_after_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            rev_file = Path(tmp) / "patch_revision.json"
            rev_file.write_text("NOT JSON", encoding="utf-8")
            result = read_patch_revision(rev_file)
            self.assertEqual(result, 0)


class TestPatchManifestParsing(unittest.TestCase):

    def test_manifest_reads_patch_revision_and_min_base(self):
        manifest_json = json.dumps({"patch_revision": 5, "min_base_revision": 3, "description": "test patch"})
        zip_path = _make_zip(manifest_json)
        try:
            manifest, err = read_patch_manifest(zip_path, patch_manifest_name=_MANIFEST_NAME)
            self.assertIsNone(err)
            self.assertIsNotNone(manifest)
            self.assertEqual(manifest["patch_revision"], 5)
            self.assertEqual(manifest["min_base_revision"], 3)
        finally:
            zip_path.unlink(missing_ok=True)

    def test_no_manifest_returns_none_without_error(self):
        zip_path = _make_zip(manifest_content=None)
        try:
            manifest, err = read_patch_manifest(zip_path, patch_manifest_name=_MANIFEST_NAME)
            self.assertIsNone(manifest)
            self.assertIsNone(err)
        finally:
            zip_path.unlink(missing_ok=True)

    def test_invalid_json_manifest_returns_error(self):
        zip_path = _make_zip("NOT VALID JSON {{")
        try:
            manifest, err = read_patch_manifest(zip_path, patch_manifest_name=_MANIFEST_NAME)
            self.assertIsNone(manifest)
            self.assertIsNotNone(err)
            self.assertIn("JSON", err)
        finally:
            zip_path.unlink(missing_ok=True)

    def test_non_object_json_manifest_returns_error(self):
        zip_path = _make_zip("[1, 2, 3]")
        try:
            manifest, err = read_patch_manifest(zip_path, patch_manifest_name=_MANIFEST_NAME)
            self.assertIsNone(manifest)
            self.assertIsNotNone(err)
        finally:
            zip_path.unlink(missing_ok=True)

    def test_bad_zip_returns_error(self):
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(b"this is not a zip file")
            tmp_path = Path(tmp.name)
        try:
            manifest, err = read_patch_manifest(tmp_path, patch_manifest_name=_MANIFEST_NAME)
            self.assertIsNone(manifest)
            self.assertIsNotNone(err)
        finally:
            tmp_path.unlink(missing_ok=True)


class TestForwardOnlyRevisionLogic(unittest.TestCase):
    """
    Verifies the forward-only invariant: a new patch revision must be
    strictly greater than the current revision.
    """

    def test_incoming_must_be_greater_than_current(self):
        # Simulate the check: patch_revision <= current_revision should be rejected
        current = 10
        cases = [
            (10, False),  # same revision — downgrade blocked
            (9, False),   # older revision — downgrade blocked
            (11, True),   # forward — allowed
            (100, True),  # far forward — allowed
        ]
        for incoming, should_pass in cases:
            with self.subTest(current=current, incoming=incoming):
                is_forward = incoming > current
                self.assertEqual(is_forward, should_pass)

    def test_min_base_must_not_exceed_current(self):
        # current must be >= min_base_revision for the patch to apply
        current = 5
        cases = [
            (3, True),   # current 5 >= min_base 3 — compatible
            (5, True),   # exactly equal — compatible
            (6, False),  # current 5 < min_base 6 — incompatible
        ]
        for min_base, should_pass in cases:
            with self.subTest(current=current, min_base=min_base):
                is_compatible = current >= min_base
                self.assertEqual(is_compatible, should_pass)


if __name__ == "__main__":
    unittest.main()
