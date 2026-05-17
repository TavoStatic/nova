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

    def test_snapshot_reports_release_validation_extract_pressure(self):
        with TemporaryDirectory() as td:
            base_dir = Path(td)
            runtime_dir = base_dir / "runtime"
            extract_dir = runtime_dir / "validation" / "release" / "candidate-a"
            stage_dir = runtime_dir / "exports" / "release_packages" / "_stage" / "candidate-a"
            package_dir = runtime_dir / "exports" / "release_packages"
            extract_dir.mkdir(parents=True)
            stage_dir.mkdir(parents=True)
            package_dir.mkdir(parents=True, exist_ok=True)
            (extract_dir / "payload.bin").write_bytes(b"x" * 2048)
            (stage_dir / "payload.bin").write_bytes(b"y" * 1024)
            (package_dir / "candidate-a.zip").write_bytes(b"z" * 512)

            payload = STORAGE_WATCH_SERVICE.snapshot(
                base_dir=base_dir,
                runtime_dir=runtime_dir,
                kidney_config={
                    "release_validation_extract_max_total_mb": 0.001,
                    "release_stage_max_total_mb": 10,
                    "release_zip_warn_count": 10,
                    "release_zip_max_total_mb": 10,
                },
            )

        self.assertEqual(payload.get("status"), "danger")
        self.assertEqual(payload.get("release_validation_extract_count"), 1)
        self.assertGreater(payload.get("release_validation_extract_bytes"), 0)
        self.assertEqual(payload.get("release_stage_count"), 1)
        self.assertEqual(payload.get("release_zip_count"), 1)
        self.assertIn("release validation extracts", payload.get("note", ""))

    def test_snapshot_reports_full_runtime_storage_pressure(self):
        with TemporaryDirectory() as td:
            base_dir = Path(td)
            runtime_dir = base_dir / "runtime"
            runtime_dir.mkdir(parents=True)
            (runtime_dir / "large.bin").write_bytes(b"x" * 2048)

            payload = STORAGE_WATCH_SERVICE.snapshot(
                base_dir=base_dir,
                runtime_dir=runtime_dir,
                kidney_config={
                    "runtime_total_warn_gb": 0.000001,
                    "runtime_total_danger_gb": 0.000002,
                },
            )

        self.assertEqual(payload.get("status"), "warn")
        self.assertGreater(payload.get("runtime_total_bytes"), 0)
        self.assertGreaterEqual(payload.get("total_bytes"), payload.get("runtime_total_bytes"))
        self.assertIn("runtime storage totals", payload.get("note", ""))


if __name__ == "__main__":
    unittest.main()
