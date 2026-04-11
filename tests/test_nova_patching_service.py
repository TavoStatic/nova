import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from services import nova_patching


class TestNovaPatchingService(unittest.TestCase):
    def test_read_patch_manifest_reads_valid_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            zip_path = Path(td) / "patch.zip"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("nova_patch.json", json.dumps({"patch_revision": 3, "min_base_revision": 1}))

            manifest, error = nova_patching.read_patch_manifest(zip_path, patch_manifest_name="nova_patch.json")

        self.assertIsNone(error)
        self.assertEqual(manifest, {"patch_revision": 3, "min_base_revision": 1})

    def test_patch_preview_summaries_merges_decision_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            updates_dir = Path(td)
            previews = updates_dir / "previews"
            previews.mkdir(parents=True, exist_ok=True)
            preview = previews / "preview_a.txt"
            preview.write_text(
                "Patch Preview\nZip: teach_proposal_1.zip\nPatch revision: 5\nMin base revision: 4\nStatus: eligible\n\nAdded files:\n- examples.jsonl\n- nova_patch.json\n\nDiff summary:\n- No text diffs available or all changes are binary/non-text\n",
                encoding="utf-8",
            )

            summaries = nova_patching.patch_preview_summaries(
                updates_dir=updates_dir,
                read_approvals_fn=lambda: [{"preview": "preview_a.txt", "decision": "approved"}],
                limit=10,
            )

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["decision"], "approved")
        self.assertEqual(summaries[0]["status"], "eligible")
        self.assertEqual(summaries[0]["preview_kind"], "teach_proposal")
        self.assertEqual(summaries[0]["patch_revision"], "5")

    def test_compact_preview_review_queue_collapses_duplicate_pending_and_approved_families(self):
        queue = nova_patching.compact_preview_review_queue(
            [
                {
                    "name": "preview_new_pending.txt",
                    "decision": "pending",
                    "status": "eligible",
                    "family_signature": "family-a",
                    "mtime": 3,
                },
                {
                    "name": "preview_old_pending.txt",
                    "decision": "pending",
                    "status": "eligible",
                    "family_signature": "family-a",
                    "mtime": 2,
                },
                {
                    "name": "preview_new_approved.txt",
                    "decision": "approved",
                    "status": "eligible",
                    "family_signature": "family-b",
                    "mtime": 1,
                },
                {
                    "name": "preview_old_approved.txt",
                    "decision": "approved",
                    "status": "eligible",
                    "family_signature": "family-b",
                    "mtime": 0,
                },
            ],
            limit=10,
        )

        rows = queue.get("review_previews") or []
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].get("name"), "preview_new_pending.txt")
        self.assertEqual(rows[0].get("collapsed_count"), 1)
        self.assertEqual(rows[1].get("name"), "preview_new_approved.txt")
        self.assertEqual(rows[1].get("collapsed_count"), 1)
        self.assertEqual(queue.get("pending_superseded"), 1)
        self.assertEqual(queue.get("approved_superseded"), 1)

    def test_patch_status_payload_exposes_compacted_review_queue(self):
        with tempfile.TemporaryDirectory() as td:
            base_dir = Path(td)
            updates_dir = base_dir / "updates"
            previews = updates_dir / "previews"
            previews.mkdir(parents=True, exist_ok=True)
            (previews / "preview_new_pending.txt").write_text(
                "Patch Preview\nZip: autonomy_micro_patch_a.zip\nPatch revision: 5\nMin base revision: 4\nStatus: eligible\n\nAdded files:\n- nova_patch.json\n\nSkipped files:\n- runtime/test_sessions/promoted/a.json\n\nDiff summary:\n- No text diffs available or all changes are binary/non-text\n",
                encoding="utf-8",
            )
            (previews / "preview_old_pending.txt").write_text(
                "Patch Preview\nZip: autonomy_micro_patch_b.zip\nPatch revision: 5\nMin base revision: 4\nStatus: eligible\n\nAdded files:\n- nova_patch.json\n\nSkipped files:\n- runtime/test_sessions/promoted/a.json\n\nDiff summary:\n- No text diffs available or all changes are binary/non-text\n",
                encoding="utf-8",
            )
            (previews / "preview_approved.txt").write_text(
                "Patch Preview\nZip: teach_proposal_1.zip\nPatch revision: 5\nMin base revision: 4\nStatus: eligible\n\nAdded files:\n- examples.jsonl\n- nova_patch.json\n\nDiff summary:\n- No text diffs available or all changes are binary/non-text\n",
                encoding="utf-8",
            )

            payload = nova_patching.patch_status_payload(
                base_dir=base_dir,
                updates_dir=updates_dir,
                read_approvals_fn=lambda: [{"preview": "preview_approved.txt", "decision": "approved"}],
                read_patch_revision_fn=lambda: 4,
                read_patch_log_tail_line_fn=lambda: "quiet",
                policy_patch_fn=lambda: {"enabled": True, "strict_manifest": True, "behavioral_check": True, "behavioral_check_timeout_sec": 600},
                patch_preview_summaries_fn=lambda limit: nova_patching.patch_preview_summaries(
                    updates_dir=updates_dir,
                    read_approvals_fn=lambda: [{"preview": "preview_approved.txt", "decision": "approved"}],
                    limit=limit,
                ),
            )

        self.assertEqual(payload.get("previews_pending"), 2)
        self.assertEqual(payload.get("review_previews_pending_distinct"), 1)
        self.assertEqual(payload.get("review_previews_pending_superseded"), 1)
        self.assertEqual(payload.get("review_previews_approved_distinct"), 1)
        review_previews = payload.get("review_previews") or []
        review_names = [item.get("name") for item in review_previews]
        pending_rows = [item for item in review_previews if item.get("decision") == "pending"]
        self.assertEqual(len(pending_rows), 1)
        self.assertIn(pending_rows[0].get("name"), {"preview_new_pending.txt", "preview_old_pending.txt"})
        self.assertEqual(pending_rows[0].get("collapsed_count"), 1)
        self.assertIn("preview_approved.txt", review_names)

    def test_patch_preview_summaries_marks_orphaned_preview_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            updates_dir = Path(td)
            previews = updates_dir / "previews"
            previews.mkdir(parents=True, exist_ok=True)
            preview = previews / "preview_orphan.txt"
            preview.write_text(
                "Patch Preview\nZip: missing_bundle.zip\nPatch revision: 5\nMin base revision: 4\nStatus: eligible\n\nAdded files:\n- nova_patch.json\n\nDiff summary:\n- No text diffs available or all changes are binary/non-text\n",
                encoding="utf-8",
            )

            summaries = nova_patching.patch_preview_summaries(
                updates_dir=updates_dir,
                read_approvals_fn=lambda: [],
                limit=10,
            )

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].get("artifact_state"), "orphaned")
        self.assertFalse(summaries[0].get("zip_exists"))
        self.assertIn("missing patch zip", summaries[0].get("artifact_reason") or "")

    def test_bulk_reject_orphaned_previews_records_rejections(self):
        with tempfile.TemporaryDirectory() as td:
            updates_dir = Path(td)
            previews = updates_dir / "previews"
            previews.mkdir(parents=True, exist_ok=True)
            (previews / "preview_orphan.txt").write_text(
                "Patch Preview\nZip: missing_bundle.zip\nStatus: eligible\n",
                encoding="utf-8",
            )
            seen = []

            result = nova_patching.bulk_reject_orphaned_previews(
                updates_dir=updates_dir,
                read_approvals_fn=lambda: [],
                record_approval_fn=lambda preview, decision, **kwargs: seen.append((preview, decision, kwargs.get("note"))) or True,
                get_active_user_fn=lambda: "gus",
                note="clean invalid artifacts",
            )

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("count"), 1)
        self.assertEqual(seen[0][1], "rejected")
        self.assertIn("clean invalid artifacts", seen[0][2] or "")

    def test_bulk_archive_superseded_previews_moves_hidden_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            updates_dir = Path(td)
            previews = updates_dir / "previews"
            previews.mkdir(parents=True, exist_ok=True)
            newer = previews / "preview_new.txt"
            older = previews / "preview_old.txt"
            newer.write_text(
                "Patch Preview\nZip: teach_proposal_a.zip\nPatch revision: 5\nMin base revision: 4\nStatus: eligible\n\nAdded files:\n- examples.jsonl\n- nova_patch.json\n\nDiff summary:\n- No text diffs available or all changes are binary/non-text\n",
                encoding="utf-8",
            )
            older.write_text(
                "Patch Preview\nZip: teach_proposal_b.zip\nPatch revision: 5\nMin base revision: 4\nStatus: eligible\n\nAdded files:\n- examples.jsonl\n- nova_patch.json\n\nDiff summary:\n- No text diffs available or all changes are binary/non-text\n",
                encoding="utf-8",
            )

            result = nova_patching.bulk_archive_superseded_previews(
                updates_dir=updates_dir,
                read_approvals_fn=lambda: [],
            )

            archive_dir = updates_dir / "previews" / "archive"
            self.assertTrue(result.get("ok"))
            self.assertEqual(result.get("count"), 1)
            remaining = list(previews.glob("*.txt"))
            self.assertEqual(len(remaining), 1)
            self.assertTrue(any(path.name.startswith("preview_") for path in archive_dir.iterdir()))


if __name__ == "__main__":
    unittest.main()