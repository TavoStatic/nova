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


if __name__ == "__main__":
    unittest.main()
