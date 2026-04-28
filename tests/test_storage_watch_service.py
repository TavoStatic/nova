import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from services.storage_watch import STORAGE_WATCH_SERVICE


class TestStorageWatchService(unittest.TestCase):
    def test_snapshot_reports_warn_when_kidney_count_exceeds_limit(self):
        with TemporaryDirectory() as td:
            base_dir = Path(td)
            runtime_dir = base_dir / "runtime"
            patch_dir = base_dir / "updates" / "snapshots"
            kidney_dir = runtime_dir / "kidney" / "snapshots"
            patch_dir.mkdir(parents=True, exist_ok=True)
            kidney_dir.mkdir(parents=True, exist_ok=True)

            for idx in range(2):
                (patch_dir / f"snapshot_{idx}.zip").write_bytes(b"x" * 128)
            for idx in range(25):
                (kidney_dir / f"kidney_{idx}.zip").write_bytes(b"y" * 64)

            payload = STORAGE_WATCH_SERVICE.snapshot(
                base_dir=base_dir,
                runtime_dir=runtime_dir,
                kidney_config={"cleanup_snapshot_max_count": 24, "cleanup_snapshot_max_total_mb": 128},
            )

        self.assertEqual(payload.get("status"), "warn")
        self.assertEqual(payload.get("patch_snapshot_count"), 2)
        self.assertEqual(payload.get("kidney_snapshot_count"), 25)
        self.assertIn("kidney cleanup snapshots", payload.get("note", ""))


if __name__ == "__main__":
    unittest.main()
