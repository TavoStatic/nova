from __future__ import annotations

from pathlib import Path


_MB = 1024 * 1024


class StorageWatchService:
    """Compute storage-watch truth for patch and kidney snapshot retention."""

    @staticmethod
    def _file_stats(directory: Path) -> tuple[int, int]:
        if not directory.exists():
            return 0, 0
        count = 0
        total_bytes = 0
        for path in directory.iterdir():
            try:
                if not path.is_file():
                    continue
                count += 1
                total_bytes += int(path.stat().st_size or 0)
            except Exception:
                continue
        return count, total_bytes

    def snapshot(self, *, base_dir: Path, runtime_dir: Path, kidney_config: dict | None = None) -> dict:
        cfg = dict(kidney_config or {})
        kidney_warn_count = int(cfg.get("cleanup_snapshot_max_count", 24) or 24)
        kidney_warn_total_mb = float(cfg.get("cleanup_snapshot_max_total_mb", 128) or 128)
        kidney_warn_total_bytes = int(kidney_warn_total_mb * _MB)
        patch_warn_count = int(cfg.get("patch_snapshot_warn_count", 3) or 3)

        patch_dir = Path(base_dir) / "updates" / "snapshots"
        kidney_dir = Path(runtime_dir) / "kidney" / "snapshots"
        patch_snapshot_count, patch_snapshot_bytes = self._file_stats(patch_dir)
        kidney_snapshot_count, kidney_snapshot_bytes = self._file_stats(kidney_dir)
        total_bytes = patch_snapshot_bytes + kidney_snapshot_bytes

        status = "ok"
        note = "snapshot storage is within normal limits"
        if kidney_snapshot_count > kidney_warn_count:
            status = "warn"
            note = f"{kidney_snapshot_count} kidney cleanup snapshots retained"
        if patch_snapshot_count > patch_warn_count:
            status = "warn"
            note = f"{patch_snapshot_count} patch rollback snapshots retained"
        if total_bytes > kidney_warn_total_bytes:
            status = "warn"
            note = f"snapshot storage totals {total_bytes / _MB:.1f} MB"

        if (
            kidney_snapshot_count > kidney_warn_count * 2
            or patch_snapshot_count > patch_warn_count * 2
            or total_bytes > kidney_warn_total_bytes * 2
        ):
            status = "danger"
            if total_bytes > kidney_warn_total_bytes * 2:
                note = f"snapshot storage totals {total_bytes / _MB:.1f} MB"
            elif kidney_snapshot_count > kidney_warn_count * 2:
                note = f"{kidney_snapshot_count} kidney cleanup snapshots retained"
            else:
                note = f"{patch_snapshot_count} patch rollback snapshots retained"

        return {
            "status": status,
            "note": note,
            "total_bytes": total_bytes,
            "patch_snapshot_count": patch_snapshot_count,
            "patch_snapshot_bytes": patch_snapshot_bytes,
            "kidney_snapshot_count": kidney_snapshot_count,
            "kidney_snapshot_bytes": kidney_snapshot_bytes,
            "patch_snapshot_warn_count": patch_warn_count,
            "kidney_snapshot_warn_count": kidney_warn_count,
            "kidney_snapshot_warn_total_mb": kidney_warn_total_mb,
        }


STORAGE_WATCH_SERVICE = StorageWatchService()
