import os
import json
import shutil
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest import mock

import nova_core
from services import nova_patching


WORK_TMP_ROOT = Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "pytest_temp"


def _workspace_case_dir(prefix: str) -> Path:
    WORK_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_TMP_ROOT / f"{prefix}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestNovaPatchingService(unittest.TestCase):
    def test_parse_scoped_patch_payload_accepts_single_block_payload(self):
        payload = nova_patching.parse_scoped_patch_payload(
            json.dumps(
                {
                    "task_id": "task_1",
                    "target": {
                        "file": "nova_http.py",
                        "function": "process_chat",
                        "block": "routing_supervisor_intent",
                        "start_line": 3200,
                        "end_line": 3350,
                    },
                    "scope": "single_block_only",
                    "verification": {"required": True},
                }
            )
        )

        self.assertEqual(payload.get("task_id"), "task_1")
        self.assertEqual((payload.get("target") or {}).get("file"), "nova_http.py")

    def test_execute_scoped_patch_payload_verifies_required_fragments(self):
        base_dir = _workspace_case_dir("nova_patching_service")
        try:
            target = base_dir / "sample.py"
            target.write_text(
                "def process_chat():\n"
                "    routed_text = 'ok'\n"
                "    if routed_text:\n"
                "        return routed_text\n",
                encoding="utf-8",
            )
            result = nova_patching.execute_scoped_patch_payload(
                {
                    "task_id": "task_1",
                    "task_title": "Scoped verify",
                    "target": {
                        "file": "sample.py",
                        "function": "process_chat",
                        "block": "routing_supervisor_intent",
                        "start_line": 1,
                        "end_line": 4,
                    },
                    "scope": "single_block_only",
                    "verification": {"required_fragments": ["routed_text", "return routed_text"]},
                },
                base_dir=base_dir,
            )
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("scope_ok"))
        self.assertTrue(result.get("verified"))
        self.assertEqual((result.get("verified_target") or {}).get("file"), "sample.py")

    def test_read_patch_manifest_reads_valid_manifest(self):
        base_dir = _workspace_case_dir("nova_patching_service")
        try:
            zip_path = base_dir / "patch.zip"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("nova_patch.json", json.dumps({"patch_revision": 3, "min_base_revision": 1}))

            manifest, error = nova_patching.read_patch_manifest(zip_path, patch_manifest_name="nova_patch.json")
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)

        self.assertIsNone(error)
        self.assertEqual(manifest, {"patch_revision": 3, "min_base_revision": 1})

    def test_snapshot_current_skips_git_and_local_baggage(self):
        base_dir = _workspace_case_dir("nova_patching_service")
        try:
            snapshots_dir = base_dir / "updates" / "snapshots"
            (base_dir / ".git" / "objects" / "aa").mkdir(parents=True, exist_ok=True)
            (base_dir / ".git" / "objects" / "aa" / "blob").write_text("git object", encoding="utf-8")
            (base_dir / ".pytest_cache").mkdir(parents=True, exist_ok=True)
            (base_dir / ".pytest_cache" / "cache.txt").write_text("cache", encoding="utf-8")
            (base_dir / "codex_probe_file.txt").write_text("probe", encoding="utf-8")
            (base_dir / "real_file.txt").write_text("real", encoding="utf-8")

            snapshot = nova_patching.snapshot_current(
                base_dir=base_dir,
                snapshots_dir=snapshots_dir,
                write_snapshot_meta_fn=lambda path, base_revision: nova_patching.write_snapshot_meta(
                    path,
                    base_revision,
                    snapshot_meta_path_fn=nova_patching.snapshot_meta_path,
                ),
                read_patch_revision_fn=lambda: 7,
                log_patch_fn=lambda _msg: None,
            )

            with zipfile.ZipFile(snapshot, "r") as archive:
                names = set(archive.namelist())
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)

        self.assertIn("real_file.txt", names)
        self.assertNotIn(".git/objects/aa/blob", names)
        self.assertNotIn(".pytest_cache/cache.txt", names)
        self.assertNotIn("codex_probe_file.txt", names)

    def test_patch_preview_summaries_merges_decision_by_name(self):
        updates_dir = _workspace_case_dir("nova_patching_service")
        try:
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
        finally:
            shutil.rmtree(updates_dir, ignore_errors=True)

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
        base_dir = _workspace_case_dir("nova_patching_service")
        try:
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
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)

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
        updates_dir = _workspace_case_dir("nova_patching_service")
        try:
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
        finally:
            shutil.rmtree(updates_dir, ignore_errors=True)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].get("artifact_state"), "orphaned")
        self.assertFalse(summaries[0].get("zip_exists"))
        self.assertIn("missing patch zip", summaries[0].get("artifact_reason") or "")

    def test_control_status_patch_fields_expose_review_queue_counts(self):
        payload = nova_patching.control_status_patch_fields(
            patch_summary={
                "ok": True,
                "enabled": True,
                "current_revision": 4,
                "previews_total": 12,
                "previews_pending": 9,
                "previews_approved": 3,
                "previews_orphaned": 2,
                "review_previews_total": 5,
                "review_previews_pending_distinct": 3,
                "review_previews_pending_superseded": 4,
                "review_previews_approved_distinct": 2,
                "review_previews_approved_superseded": 1,
                "review_previews_orphaned": 1,
                "review_previews_superseded_total": 5,
                "previews": [],
            },
            patch_action_readiness={"default_preview": "preview.txt"},
        )

        self.assertEqual(payload.get("patch_previews_total"), 12)
        self.assertEqual(payload.get("patch_previews_orphaned"), 2)
        self.assertEqual(payload.get("patch_review_previews_total"), 5)
        self.assertEqual(payload.get("patch_review_previews_pending_distinct"), 3)
        self.assertEqual(payload.get("patch_review_previews_pending_superseded"), 4)
        self.assertEqual(payload.get("patch_review_previews_approved_distinct"), 2)
        self.assertEqual(payload.get("patch_review_previews_approved_superseded"), 1)
        self.assertEqual(payload.get("patch_review_previews_orphaned"), 1)
        self.assertEqual(payload.get("patch_review_previews_superseded_total"), 5)
        self.assertEqual((payload.get("patch_action_readiness") or {}).get("default_preview"), "preview.txt")

    def test_nova_core_execute_planned_action_supports_patch_preview_apply(self):
        with mock.patch.object(
            nova_core.PATCH_CONTROL_SERVICE,
            "patch_preview_apply",
            return_value=(True, "patch_preview_apply_ok", {"preview": "preview_a.txt", "text": "Patch applied"}, "patch_preview_apply_ok:preview_a.txt"),
        ):
            out = nova_core.execute_planned_action("patch_preview_apply", ["preview_a.txt"])

        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("message"), "patch_preview_apply_ok")
        self.assertEqual(out.get("preview"), "preview_a.txt")

    def test_nova_core_execute_planned_action_supports_patch_preview_approve(self):
        with mock.patch.object(
            nova_core.PATCH_CONTROL_SERVICE,
            "patch_preview_decision",
            return_value=(True, "patch_preview_approve_ok", {"preview": "preview_a.txt", "text": "Approved."}, "patch_preview_approve_ok:preview_a.txt"),
        ):
            out = nova_core.execute_planned_action("patch_preview_approve", ["preview_a.txt"])

        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("message"), "patch_preview_approve_ok")
        self.assertEqual(out.get("preview"), "preview_a.txt")

    def test_nova_core_execute_planned_action_supports_system_check(self):
        with mock.patch.object(nova_core, "tool_system_check", return_value="System check ok.") as mocked:
            out = nova_core.execute_planned_action("system_check")

        mocked.assert_called_once_with()
        self.assertEqual(out, "System check ok.")

    def test_nova_core_execute_planned_action_supports_read(self):
        with mock.patch.object(nova_core, "tool_read", return_value="read ok") as mocked:
            out = nova_core.execute_planned_action("read", ["runtime/autonomy_maintenance.log"])

        mocked.assert_called_once_with("runtime/autonomy_maintenance.log")
        self.assertEqual(out, "read ok")

    def test_nova_core_execute_planned_action_supports_ls(self):
        with mock.patch.object(nova_core, "tool_ls", return_value="ls ok") as mocked:
            out = nova_core.execute_planned_action("ls", ["runtime"])

        mocked.assert_called_once_with("runtime")
        self.assertEqual(out, "ls ok")

    def test_nova_core_execute_planned_action_supports_find(self):
        with mock.patch.object(nova_core, "tool_find", return_value="find ok") as mocked:
            out = nova_core.execute_planned_action("find", ["test_generic_fallback"])

        mocked.assert_called_once_with("test_generic_fallback")
        self.assertEqual(out, "find ok")

    def test_patch_apply_skips_snapshot_when_zip_has_no_real_changes(self):
        base_dir = _workspace_case_dir("nova_patching_service")
        try:
            patch_zip = base_dir / "patch_no_change.zip"
            manifest = {"patch_revision": 4, "min_base_revision": 0}
            (base_dir / "same.txt").write_text("hello", encoding="utf-8")
            with zipfile.ZipFile(patch_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("nova_patch.json", json.dumps(manifest))
                archive.writestr("same.txt", "hello")

            snapshot_mock = mock.Mock(return_value=base_dir / "updates" / "snapshots" / "snap.zip")
            result = nova_patching.patch_apply(
                str(patch_zip),
                force=False,
                safe_path_fn=lambda value: Path(value),
                policy_patch_fn=lambda: {"strict_manifest": True, "behavioral_check": True, "behavioral_check_timeout_sec": 60},
                read_patch_revision_fn=lambda: 3,
                read_patch_manifest_fn=lambda path: nova_patching.read_patch_manifest(path, patch_manifest_name="nova_patch.json"),
                log_patch_fn=lambda _msg: None,
                patch_reject_message_fn=lambda reason, **kwargs: reason,
                patch_preview_fn=lambda _path, _write_report=False: (
                    "Patch Preview\nStatus: eligible\nPreview written: updates/previews/preview_a.txt\n"
                ),
                read_approvals_fn=lambda: [{"preview": "updates/previews/preview_a.txt", "decision": "approved"}],
                snapshot_current_fn=snapshot_mock,
                overlay_zip_fn=lambda _path: 99,
                py_compile_check_fn=lambda: (True, "ok"),
                patch_rollback_fn=lambda _path=None: "rolled back",
                behavioral_check_fn=lambda **kwargs: {"ok": True, "summary": "ok", "output": ""},
                write_patch_revision_fn=lambda revision, source: None,
                patch_manifest_name="nova_patch.json",
                base_dir=base_dir,
            )
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)

        snapshot_mock.assert_not_called()
        self.assertEqual(result, "Patch zip contained no changed eligible files to apply.")

    def test_bulk_reject_orphaned_previews_records_rejections(self):
        updates_dir = _workspace_case_dir("nova_patching_service")
        try:
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
        finally:
            shutil.rmtree(updates_dir, ignore_errors=True)

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("count"), 1)
        self.assertEqual(seen[0][1], "rejected")
        self.assertIn("clean invalid artifacts", seen[0][2] or "")

    def test_bulk_archive_superseded_previews_moves_hidden_duplicates(self):
        updates_dir = _workspace_case_dir("nova_patching_service")
        try:
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
            self.assertGreaterEqual(len(remaining), 1)
            self.assertLessEqual(len(remaining), 2)
            self.assertTrue(any(path.name.startswith("preview_") for path in archive_dir.iterdir()))
        finally:
            shutil.rmtree(updates_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
