import json
import tempfile
import time
import unittest
from pathlib import Path

import kidney
import nova_core


class TestKidney(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.orig_policy_path = nova_core.POLICY_PATH
        self.orig_kidney_policy_path = kidney.POLICY_PATH
        self.orig_runtime_dir = kidney.RUNTIME_DIR
        self.orig_updates_dir = kidney.UPDATES_DIR
        self.orig_generated_dir = kidney.GENERATED_DEFINITIONS_DIR
        self.orig_promoted_dir = kidney.PROMOTED_DEFINITIONS_DIR
        self.orig_pending_dir = kidney.PENDING_REVIEW_DIR
        self.orig_quarantine_dir = kidney.QUARANTINE_DIR
        self.orig_test_sessions_dir = kidney.TEST_SESSIONS_DIR
        self.orig_previews_dir = kidney.PREVIEWS_DIR
        self.orig_snapshots_dir = kidney.SNAPSHOTS_DIR
        self.orig_kidney_root = kidney.KIDNEY_ROOT
        self.orig_archive_dir = kidney.KIDNEY_ARCHIVE_DIR
        self.orig_kidney_snapshots_dir = kidney.KIDNEY_SNAPSHOTS_DIR
        self.orig_kidney_status_path = kidney.KIDNEY_STATUS_PATH
        self.orig_kidney_protect_path = kidney.KIDNEY_PROTECT_PATH
        self.orig_kidney_retired_path = kidney.KIDNEY_RETIRED_DEFINITIONS_PATH
        self.orig_promotion_audit_path = kidney.PROMOTION_AUDIT_PATH

        policy_path = self.base / "policy.json"
        runtime_dir = self.base / "runtime"
        updates_dir = self.base / "updates"
        test_sessions_dir = runtime_dir / "test_sessions"
        kidney_root = runtime_dir / "kidney"

        nova_core.POLICY_PATH = policy_path
        kidney.POLICY_PATH = policy_path
        kidney.RUNTIME_DIR = runtime_dir
        kidney.UPDATES_DIR = updates_dir
        kidney.GENERATED_DEFINITIONS_DIR = test_sessions_dir / "generated_definitions"
        kidney.PROMOTED_DEFINITIONS_DIR = test_sessions_dir / "promoted"
        kidney.PENDING_REVIEW_DIR = test_sessions_dir / "pending_review"
        kidney.QUARANTINE_DIR = test_sessions_dir / "quarantine"
        kidney.TEST_SESSIONS_DIR = test_sessions_dir
        kidney.PREVIEWS_DIR = updates_dir / "previews"
        kidney.SNAPSHOTS_DIR = updates_dir / "snapshots"
        kidney.KIDNEY_ROOT = kidney_root
        kidney.KIDNEY_ARCHIVE_DIR = kidney_root / "archive"
        kidney.KIDNEY_SNAPSHOTS_DIR = kidney_root / "snapshots"
        kidney.KIDNEY_STATUS_PATH = kidney_root / "status.json"
        kidney.KIDNEY_PROTECT_PATH = kidney_root / "protect_patterns.json"
        kidney.KIDNEY_RETIRED_DEFINITIONS_PATH = kidney_root / "retired_generated_definitions.json"
        kidney.PROMOTION_AUDIT_PATH = test_sessions_dir / "promotion_audit.jsonl"

        self._write_policy({"enabled": True, "mode": "observe"})

    def tearDown(self):
        nova_core.POLICY_PATH = self.orig_policy_path
        kidney.POLICY_PATH = self.orig_kidney_policy_path
        kidney.RUNTIME_DIR = self.orig_runtime_dir
        kidney.UPDATES_DIR = self.orig_updates_dir
        kidney.GENERATED_DEFINITIONS_DIR = self.orig_generated_dir
        kidney.PROMOTED_DEFINITIONS_DIR = self.orig_promoted_dir
        kidney.PENDING_REVIEW_DIR = self.orig_pending_dir
        kidney.QUARANTINE_DIR = self.orig_quarantine_dir
        kidney.TEST_SESSIONS_DIR = self.orig_test_sessions_dir
        kidney.PREVIEWS_DIR = self.orig_previews_dir
        kidney.SNAPSHOTS_DIR = self.orig_snapshots_dir
        kidney.KIDNEY_ROOT = self.orig_kidney_root
        kidney.KIDNEY_ARCHIVE_DIR = self.orig_archive_dir
        kidney.KIDNEY_SNAPSHOTS_DIR = self.orig_kidney_snapshots_dir
        kidney.KIDNEY_STATUS_PATH = self.orig_kidney_status_path
        kidney.KIDNEY_PROTECT_PATH = self.orig_kidney_protect_path
        kidney.KIDNEY_RETIRED_DEFINITIONS_PATH = self.orig_kidney_retired_path
        kidney.PROMOTION_AUDIT_PATH = self.orig_promotion_audit_path
        self.tmp.cleanup()

    def _write_policy(self, kidney_cfg: dict):
        kidney.POLICY_PATH.write_text(
            json.dumps(
                {
                    "allowed_root": str(self.base),
                    "tools_enabled": {"web": False},
                    "web": {"enabled": False, "allow_domains": []},
                    "kidney": kidney_cfg,
                }
            ),
            encoding="utf-8",
        )

    def _touch_old(self, path: Path, age_seconds: float):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("x", encoding="utf-8")
        ts = time.time() - age_seconds
        if path.is_file():
            path.touch()
            Path(path).chmod(0o666)
        import os
        os.utime(path, (ts, ts))

    def test_add_protect_pattern_persists(self):
        out = kidney.add_protect_pattern("builder_mode")

        self.assertIn("added", out.lower())
        stored = json.loads(kidney.KIDNEY_PROTECT_PATH.read_text(encoding="utf-8"))
        self.assertIn("builder_mode", stored)

    def test_scan_candidates_flags_old_low_novelty_definition(self):
        target = kidney.GENERATED_DEFINITIONS_DIR / "candidate.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"messages": ["run patch now"]}), encoding="utf-8")
        self._touch_old(target, 8 * 86400)
        kidney.PROMOTION_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        kidney.PROMOTION_AUDIT_PATH.write_text(
            json.dumps({"file": "candidate.json", "metrics": {"novelty": 0.2}}) + "\n",
            encoding="utf-8",
        )

        candidates = kidney.scan_candidates()

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].get("action"), "archive")

    def test_scan_candidates_flags_nested_generated_definition(self):
        target = kidney.GENERATED_DEFINITIONS_DIR / "real_world" / "candidate.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"messages": ["run patch now"]}), encoding="utf-8")
        self._touch_old(target, 8 * 86400)
        kidney.PROMOTION_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        kidney.PROMOTION_AUDIT_PATH.write_text(
            json.dumps({"file": "candidate.json", "metrics": {"novelty": 0.2}}) + "\n",
            encoding="utf-8",
        )

        candidates = kidney.scan_candidates()

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].get("path"), str(target))
        self.assertEqual(candidates[0].get("action"), "archive")

    def test_run_kidney_enforce_archives_and_deletes(self):
        self._write_policy({"enabled": True, "mode": "enforce", "definition_max_age_days": 7, "quarantine_max_age_hours": 48})

        old_definition = kidney.GENERATED_DEFINITIONS_DIR / "candidate.json"
        old_definition.parent.mkdir(parents=True, exist_ok=True)
        old_definition.write_text(
            json.dumps(
                {
                    "messages": ["run patch now"],
                    "source": "subconscious_generated",
                    "family_id": "patch-routing-fallthrough-family",
                    "variation_id": "candidate",
                }
            ),
            encoding="utf-8",
        )
        self._touch_old(old_definition, 8 * 86400)

        quarantined = kidney.QUARANTINE_DIR / "stale.json"
        quarantined.parent.mkdir(parents=True, exist_ok=True)
        quarantined.write_text(json.dumps({"messages": ["hello"]}), encoding="utf-8")
        self._touch_old(quarantined, 72 * 3600)

        summary = kidney.run_kidney(dry_run=False)

        self.assertEqual(summary.get("mode"), "enforce")
        self.assertTrue(summary.get("snapshot_path"))
        self.assertFalse(old_definition.exists())
        self.assertFalse(quarantined.exists())
        archived = list(kidney.KIDNEY_ARCHIVE_DIR.glob("candidate_*.json"))
        self.assertTrue(archived)
        retired = json.loads(kidney.KIDNEY_RETIRED_DEFINITIONS_PATH.read_text(encoding="utf-8"))
        self.assertIn("candidate.json", retired)
        self.assertEqual((retired.get("candidate.json") or {}).get("reason"), "definition_age_days>7")

    def test_dry_run_does_not_overwrite_live_status(self):
        self._write_policy({"enabled": True, "mode": "enforce", "definition_max_age_days": 7})
        kidney.KIDNEY_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        kidney.KIDNEY_STATUS_PATH.write_text(
            json.dumps({"mode": "enforce", "dry_run": False, "sentinel": "live"}),
            encoding="utf-8",
        )
        old_definition = kidney.GENERATED_DEFINITIONS_DIR / "candidate.json"
        old_definition.parent.mkdir(parents=True, exist_ok=True)
        old_definition.write_text(json.dumps({"messages": ["run patch now"]}), encoding="utf-8")
        self._touch_old(old_definition, 8 * 86400)

        summary = kidney.run_kidney(dry_run=True)

        self.assertTrue(summary.get("dry_run"))
        self.assertEqual(summary.get("status_write"), "suppressed")
        stored = json.loads(kidney.KIDNEY_STATUS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(stored.get("sentinel"), "live")
        self.assertFalse(stored.get("dry_run"))

    def test_dry_run_can_explicitly_write_status_to_isolated_path(self):
        self._write_policy({"enabled": True, "mode": "observe"})

        summary = kidney.run_kidney(dry_run=True, write_status=True)

        stored = json.loads(kidney.KIDNEY_STATUS_PATH.read_text(encoding="utf-8"))
        self.assertTrue(summary.get("dry_run"))
        self.assertTrue(stored.get("dry_run"))
        self.assertEqual(stored.get("status_write"), "live")

    def test_protected_pattern_skips_candidate(self):
        self._write_policy({"enabled": True, "mode": "observe", "protect_patterns": ["builder_mode"]})
        protected = kidney.GENERATED_DEFINITIONS_DIR / "builder_mode_chat.json"
        protected.parent.mkdir(parents=True, exist_ok=True)
        protected.write_text(json.dumps({"messages": ["run patch now"]}), encoding="utf-8")
        self._touch_old(protected, 8 * 86400)

        candidates = kidney.scan_candidates()

        self.assertEqual(candidates, [])

    def test_pending_review_high_fallback_is_retained_until_age_limit(self):
        self._write_policy({"enabled": True, "mode": "observe", "quarantine_max_age_hours": 48})
        pending = kidney.PENDING_REVIEW_DIR / "candidate.json"
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text(json.dumps({"messages": ["review me"]}), encoding="utf-8")
        self._touch_old(pending, 30)
        kidney.PROMOTION_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        kidney.PROMOTION_AUDIT_PATH.write_text(
            json.dumps({
                "file": "candidate.json",
                "status": "pending_review",
                "metrics": {"fallback_overuse": 0.97},
            })
            + "\n",
            encoding="utf-8",
        )

        candidates = kidney.scan_candidates()

        self.assertFalse(any(item.get("name") == "candidate.json" for item in candidates))

    def test_pending_review_marked_quarantined_is_deleted(self):
        self._write_policy({"enabled": True, "mode": "observe", "quarantine_max_age_hours": 48})
        pending = kidney.PENDING_REVIEW_DIR / "candidate.json"
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text(json.dumps({"messages": ["review me"]}), encoding="utf-8")
        self._touch_old(pending, 30)
        kidney.PROMOTION_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        kidney.PROMOTION_AUDIT_PATH.write_text(
            json.dumps({
                "file": "candidate.json",
                "status": "quarantined",
                "metrics": {"fallback_overuse": 0.97},
            })
            + "\n",
            encoding="utf-8",
        )

        candidates = kidney.scan_candidates()

        item = next((row for row in candidates if row.get("name") == "candidate.json"), None)
        self.assertIsNotNone(item)
        self.assertEqual(item.get("action"), "delete")
        self.assertEqual(item.get("reason"), "pending_review_marked_quarantined")

    def test_scan_candidates_flags_excess_snapshot_count_and_size(self):
        self._write_policy(
            {
                "enabled": True,
                "mode": "observe",
                "snapshot_max_age_days": 30,
                "snapshot_max_count": 3,
                "snapshot_max_total_gb": 0.000001,
            }
        )
        kidney.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        snapshots: list[Path] = []
        for idx in range(4):
            path = kidney.SNAPSHOTS_DIR / f"snapshot_20260424_00000{idx}.zip"
            path.write_bytes(b"x" * 4096)
            self._touch_old(path, idx * 60)
            snapshots.append(path)

        candidates = kidney.scan_candidates()

        snapshot_rows = [row for row in candidates if row.get("category") == "stale_snapshot"]
        names = {row.get("name") for row in snapshot_rows}
        self.assertIn(snapshots[1].name, names)
        self.assertIn(snapshots[2].name, names)
        self.assertIn(snapshots[3].name, names)
        self.assertNotIn(snapshots[0].name, names)

    def test_run_kidney_delete_snapshot_removes_sidecar_meta(self):
        self._write_policy(
            {
                "enabled": True,
                "mode": "enforce",
                "snapshot_max_age_days": 30,
                "snapshot_max_count": 1,
                "snapshot_max_total_gb": 1,
            }
        )
        kidney.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        newest = kidney.SNAPSHOTS_DIR / "snapshot_20260424_000001.zip"
        oldest = kidney.SNAPSHOTS_DIR / "snapshot_20260424_000000.zip"
        newest.write_bytes(b"new")
        oldest.write_bytes(b"old")
        newest.with_suffix(".zip.json").write_text("{}", encoding="utf-8")
        oldest.with_suffix(".zip.json").write_text("{}", encoding="utf-8")
        self._touch_old(newest, 0)
        self._touch_old(oldest, 120)

        summary = kidney.run_kidney(dry_run=False)

        self.assertEqual(summary.get("mode"), "enforce")
        self.assertTrue(newest.exists())
        self.assertFalse(oldest.exists())
        self.assertFalse(oldest.with_suffix(".zip.json").exists())

    def test_run_kidney_skips_cleanup_snapshot_for_stale_snapshot_batch(self):
        self._write_policy(
            {
                "enabled": True,
                "mode": "enforce",
                "snapshot_max_age_days": 30,
                "snapshot_max_count": 1,
                "snapshot_max_total_gb": 1,
            }
        )
        kidney.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        newest = kidney.SNAPSHOTS_DIR / "snapshot_20260424_000001.zip"
        oldest = kidney.SNAPSHOTS_DIR / "snapshot_20260424_000000.zip"
        newest.write_bytes(b"new")
        oldest.write_bytes(b"old")
        self._touch_old(newest, 0)
        self._touch_old(oldest, 120)

        summary = kidney.run_kidney(dry_run=False)

        self.assertEqual(summary.get("snapshot_path"), "")
        self.assertEqual(summary.get("snapshot_skipped_reason"), "stale_snapshot_batch")

    def test_run_kidney_prunes_cleanup_snapshots_even_without_candidates(self):
        self._write_policy(
            {
                "enabled": True,
                "mode": "enforce",
                "cleanup_snapshot_max_count": 24,
                "cleanup_snapshot_max_total_mb": 128,
            }
        )
        kidney.KIDNEY_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        snapshots: list[Path] = []
        for idx in range(25):
            path = kidney.KIDNEY_SNAPSHOTS_DIR / f"kidney_20260427_080{idx:02d}.zip"
            path.write_bytes(b"x" * 16)
            self._touch_old(path, idx * 60)
            snapshots.append(path)

        summary = kidney.run_kidney(dry_run=False)

        self.assertEqual(summary.get("candidate_count"), 0)
        self.assertEqual(summary.get("cleanup_snapshot_pruned_count"), 1)
        retained = sorted(p for p in kidney.KIDNEY_SNAPSHOTS_DIR.iterdir() if p.is_file())
        self.assertEqual(len(retained), 24)
        self.assertFalse(snapshots[-1].exists())

    def test_run_kidney_prunes_cleanup_snapshots_after_new_snapshot(self):
        self._write_policy(
            {
                "enabled": True,
                "mode": "enforce",
                "definition_max_age_days": 7,
                "cleanup_snapshot_max_count": 24,
                "cleanup_snapshot_max_total_mb": 128,
            }
        )
        old_definition = kidney.GENERATED_DEFINITIONS_DIR / "candidate.json"
        old_definition.parent.mkdir(parents=True, exist_ok=True)
        old_definition.write_text(json.dumps({"messages": ["run patch now"]}), encoding="utf-8")
        self._touch_old(old_definition, 8 * 86400)
        kidney.KIDNEY_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        for idx in range(24):
            path = kidney.KIDNEY_SNAPSHOTS_DIR / f"kidney_20260426_070{idx:02d}.zip"
            path.write_bytes(b"x" * 16)
            self._touch_old(path, (idx + 1) * 60)

        summary = kidney.run_kidney(dry_run=False)

        self.assertTrue(summary.get("snapshot_path"))
        self.assertEqual(summary.get("cleanup_snapshot_retained_count"), 24)
        retained = sorted(p for p in kidney.KIDNEY_SNAPSHOTS_DIR.iterdir() if p.is_file())
        self.assertEqual(len(retained), 24)

    def test_scan_candidates_ages_out_release_extract_trees(self):
        self._write_policy({"enabled": True, "mode": "observe", "release_extract_max_age_days": 3})
        extract = kidney.RUNTIME_DIR / "validation" / "release" / "_manual_pkg_probe"
        payload = extract / "payload.bin"
        logs = kidney.RUNTIME_DIR / "validation" / "release" / "release_command_logs"
        record = kidney.RUNTIME_DIR / "validation" / "release" / "latest_release_validation.json"
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload.write_bytes(b"x" * 64)
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "run.log").write_text("kept", encoding="utf-8")
        record.write_text("{}", encoding="utf-8")
        self._touch_old(extract, 5 * 86400)

        candidates = kidney.scan_candidates()
        extract_rows = [row for row in candidates if row.get("category") == "release_extract_bloat"]

        self.assertEqual(len(extract_rows), 1)
        self.assertEqual(extract_rows[0].get("name"), "_manual_pkg_probe")
        self.assertEqual(extract_rows[0].get("reason"), "release_extract_age_limit")
        self.assertFalse(any(row.get("name") == "release_command_logs" for row in candidates))
        self.assertFalse(any(row.get("name") == "latest_release_validation.json" for row in candidates))

    def test_scan_candidates_caps_release_extract_total_size(self):
        self._write_policy(
            {
                "enabled": True,
                "mode": "observe",
                "release_extract_max_age_days": 30,
                "release_validation_extract_max_total_mb": 0.003,
            }
        )
        root = kidney.RUNTIME_DIR / "validation" / "release"
        newest = root / "fresh-keep"
        oldest = root / "fresh-drop"
        (newest / "payload.bin").parent.mkdir(parents=True, exist_ok=True)
        (oldest / "payload.bin").parent.mkdir(parents=True, exist_ok=True)
        (newest / "payload.bin").write_bytes(b"n" * 2048)
        (oldest / "payload.bin").write_bytes(b"o" * 2048)
        self._touch_old(newest, 60)
        self._touch_old(oldest, 120)

        candidates = kidney.scan_candidates()
        extract_rows = [row for row in candidates if row.get("category") == "release_extract_bloat"]
        names = {row.get("name") for row in extract_rows}

        self.assertEqual(names, {"fresh-drop"})
        self.assertEqual(extract_rows[0].get("reason"), "release_extract_total_size_limit")

    def test_scan_candidates_does_not_flag_release_package_zips(self):
        self._write_policy({"enabled": True, "mode": "observe", "exports_max_age_days": 1})
        package_dir = kidney.RUNTIME_DIR / "exports" / "release_packages"
        package_dir.mkdir(parents=True, exist_ok=True)
        zip_path = package_dir / "nyo-system-base-rc.zip"
        ledger = package_dir / "release_ledger.jsonl"
        zip_path.write_bytes(b"z" * 128)
        ledger.write_text("{}\n", encoding="utf-8")
        self._touch_old(zip_path, 10 * 86400)
        self._touch_old(ledger, 10 * 86400)

        candidates = kidney.scan_candidates()
        names = {row.get("name") for row in candidates}
        self.assertNotIn("nyo-system-base-rc.zip", names)
        self.assertNotIn("release_ledger.jsonl", names)

    def test_run_kidney_deletes_stale_extract_without_zipping_it(self):
        self._write_policy(
            {
                "enabled": True,
                "mode": "enforce",
                "release_extract_max_age_days": 3,
            }
        )
        extract = kidney.RUNTIME_DIR / "validation" / "release" / "x-old-probe"
        (extract / "payload.bin").parent.mkdir(parents=True, exist_ok=True)
        (extract / "payload.bin").write_bytes(b"x" * 32)
        self._touch_old(extract, 5 * 86400)

        summary = kidney.run_kidney(dry_run=False)

        self.assertFalse(extract.exists())
        self.assertEqual(summary.get("snapshot_path"), "")
        self.assertEqual(summary.get("snapshot_skipped_reason"), "storage_watch_batch")
        applied = list(summary.get("applied") or [])
        self.assertTrue(any(row.get("result") == "deleted" and row.get("name") == "x-old-probe" for row in applied))

    def test_scan_candidates_ages_out_release_stage_trees(self):
        self._write_policy({"enabled": True, "mode": "observe", "release_stage_max_age_days": 3})
        stage = kidney.RUNTIME_DIR / "exports" / "release_packages" / "_stage" / "candidate-a"
        (stage / "payload.bin").parent.mkdir(parents=True, exist_ok=True)
        (stage / "payload.bin").write_bytes(b"y" * 16)
        self._touch_old(stage, 5 * 86400)

        candidates = kidney.scan_candidates()
        stage_rows = [row for row in candidates if row.get("category") == "release_stage_bloat"]

        self.assertEqual(len(stage_rows), 1)
        self.assertEqual(stage_rows[0].get("name"), "candidate-a")
        self.assertEqual(stage_rows[0].get("reason"), "release_stage_age_limit")

    def test_scan_candidates_caps_subconscious_runs_and_keeps_latest_pointers(self):
        self._write_policy(
            {
                "enabled": True,
                "mode": "observe",
                "subconscious_run_max_age_days": 30,
                "subconscious_run_keep_count": 2,
                "subconscious_run_max_flag": 10,
            }
        )
        root = kidney.RUNTIME_DIR / "subconscious_runs"
        root.mkdir(parents=True, exist_ok=True)
        (root / "latest.json").write_text("{}", encoding="utf-8")
        (root / "latest.md").write_text("kept", encoding="utf-8")
        for idx, age in enumerate((30, 120, 240, 360)):
            run_dir = root / f"20260821_00000{idx}_phase1-auto"
            run_dir.mkdir()
            (run_dir / "report.json").write_text("{}", encoding="utf-8")
            self._touch_old(run_dir, age)

        candidates = kidney.scan_candidates()
        run_rows = [row for row in candidates if row.get("category") == "subconscious_run_bloat"]
        names = {row.get("name") for row in run_rows}

        self.assertEqual(len(run_rows), 2)
        self.assertTrue(names.issubset({"20260821_000002_phase1-auto", "20260821_000003_phase1-auto"}))
        self.assertTrue((root / "latest.json").exists())
        self.assertFalse(any(row.get("name") == "latest.json" for row in candidates))

    def test_scan_candidates_ages_out_recovery_quarantine(self):
        self._write_policy(
            {
                "enabled": True,
                "mode": "observe",
                "recovery_quarantine_max_age_days": 14,
                "recovery_quarantine_keep_count": 1,
            }
        )
        old = kidney.RUNTIME_DIR / "recovery_quarantine" / "decontam_20260513_131620"
        old.mkdir(parents=True, exist_ok=True)
        (old / "note.txt").write_text("old", encoding="utf-8")
        self._touch_old(old, 20 * 86400)

        candidates = kidney.scan_candidates()
        rows = [row for row in candidates if row.get("category") == "recovery_quarantine_bloat"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("name"), "decontam_20260513_131620")
        self.assertEqual(rows[0].get("reason"), "recovery_quarantine_age_limit")

    def test_run_kidney_deletes_stale_subconscious_run_without_zipping_it(self):
        self._write_policy(
            {
                "enabled": True,
                "mode": "enforce",
                "subconscious_run_max_age_days": 2,
                "subconscious_run_keep_count": 24,
            }
        )
        run_dir = kidney.RUNTIME_DIR / "subconscious_runs" / "20260101_000000_old"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "report.json").write_text("{}", encoding="utf-8")
        self._touch_old(run_dir, 5 * 86400)
        latest = kidney.RUNTIME_DIR / "subconscious_runs" / "latest.json"
        latest.write_text("{}", encoding="utf-8")

        summary = kidney.run_kidney(dry_run=False)

        self.assertFalse(run_dir.exists())
        self.assertTrue(latest.exists())
        self.assertEqual(summary.get("snapshot_path"), "")
        self.assertEqual(summary.get("snapshot_skipped_reason"), "storage_watch_batch")


if __name__ == "__main__":
    unittest.main()
