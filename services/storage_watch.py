from __future__ import annotations

from pathlib import Path


_MB = 1024 * 1024


class StorageWatchService:
    """Compute storage-watch truth for retained runtime storage surfaces."""

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

    @staticmethod
    def _tree_stats(directory: Path, *, exclude_names: set[str] | None = None) -> tuple[int, int]:
        if not directory.exists():
            return 0, 0
        excluded = set(exclude_names or set())
        count = 0
        total_bytes = 0
        for child in directory.iterdir():
            try:
                if not child.is_dir() or child.name in excluded:
                    continue
                count += 1
                for path in child.rglob("*"):
                    if path.is_file():
                        total_bytes += int(path.stat().st_size or 0)
            except Exception:
                continue
        return count, total_bytes

    @staticmethod
    def _recursive_file_stats(directory: Path) -> tuple[int, int]:
        if not directory.exists():
            return 0, 0
        count = 0
        total_bytes = 0
        for path in directory.rglob("*"):
            try:
                if not path.is_file():
                    continue
                count += 1
                total_bytes += int(path.stat().st_size or 0)
            except Exception:
                continue
        return count, total_bytes

    @staticmethod
    def _zip_stats(directory: Path) -> tuple[int, int]:
        if not directory.exists():
            return 0, 0
        count = 0
        total_bytes = 0
        for path in directory.glob("*.zip"):
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
        release_extract_warn_total_mb = float(cfg.get("release_validation_extract_max_total_mb", 1024) or 1024)
        release_stage_warn_total_mb = float(cfg.get("release_stage_max_total_mb", 256) or 256)
        release_zip_warn_count = int(cfg.get("release_zip_warn_count", 12) or 12)
        release_zip_warn_total_mb = float(cfg.get("release_zip_max_total_mb", 1024) or 1024)
        runtime_warn_total_gb = float(cfg.get("runtime_total_warn_gb", 12) or 12)
        runtime_danger_total_gb = float(cfg.get("runtime_total_danger_gb", 16) or 16)

        patch_dir = Path(base_dir) / "updates" / "snapshots"
        kidney_dir = Path(runtime_dir) / "kidney" / "snapshots"
        release_validation_dir = Path(runtime_dir) / "validation" / "release"
        release_stage_dir = Path(runtime_dir) / "exports" / "release_packages" / "_stage"
        release_package_dir = Path(runtime_dir) / "exports" / "release_packages"
        patch_snapshot_count, patch_snapshot_bytes = self._file_stats(patch_dir)
        kidney_snapshot_count, kidney_snapshot_bytes = self._file_stats(kidney_dir)
        snapshot_bytes = patch_snapshot_bytes + kidney_snapshot_bytes
        release_validation_extract_count, release_validation_extract_bytes = self._tree_stats(
            release_validation_dir,
            exclude_names={"release_command_logs"},
        )
        release_stage_count, release_stage_bytes = self._tree_stats(release_stage_dir)
        release_zip_count, release_zip_bytes = self._zip_stats(release_package_dir)
        watched_total_bytes = snapshot_bytes + release_validation_extract_bytes + release_stage_bytes + release_zip_bytes
        runtime_file_count, runtime_total_bytes = self._recursive_file_stats(Path(runtime_dir))
        total_bytes = max(watched_total_bytes, runtime_total_bytes)

        status = "ok"
        note = "watched storage is within normal limits"
        if kidney_snapshot_count > kidney_warn_count:
            status = "warn"
            note = f"{kidney_snapshot_count} kidney cleanup snapshots retained"
        if patch_snapshot_count > patch_warn_count:
            status = "warn"
            note = f"{patch_snapshot_count} patch rollback snapshots retained"
        if snapshot_bytes > kidney_warn_total_bytes:
            status = "warn"
            note = f"snapshot storage totals {snapshot_bytes / _MB:.1f} MB"
        if release_zip_count > release_zip_warn_count:
            status = "warn"
            note = f"{release_zip_count} release package zip artifacts retained"
        if release_zip_bytes > release_zip_warn_total_mb * _MB:
            status = "warn"
            note = f"release package zip artifacts total {release_zip_bytes / _MB:.1f} MB"
        if release_stage_bytes > release_stage_warn_total_mb * _MB:
            status = "danger"
            note = f"release package stage directories total {release_stage_bytes / _MB:.1f} MB"
        if release_validation_extract_bytes > release_extract_warn_total_mb * _MB:
            status = "danger"
            note = f"release validation extracts total {release_validation_extract_bytes / _MB:.1f} MB"
        if runtime_total_bytes > runtime_warn_total_gb * 1024 * _MB and status != "danger":
            status = "warn"
            note = f"runtime storage totals {runtime_total_bytes / (1024 * _MB):.1f} GB"
        if runtime_total_bytes > runtime_danger_total_gb * 1024 * _MB:
            status = "danger"
            note = f"runtime storage totals {runtime_total_bytes / (1024 * _MB):.1f} GB"

        if (
            kidney_snapshot_count > kidney_warn_count * 2
            or patch_snapshot_count > patch_warn_count * 2
            or snapshot_bytes > kidney_warn_total_bytes * 2
        ):
            status = "danger"
            if snapshot_bytes > kidney_warn_total_bytes * 2:
                note = f"snapshot storage totals {snapshot_bytes / _MB:.1f} MB"
            elif kidney_snapshot_count > kidney_warn_count * 2:
                note = f"{kidney_snapshot_count} kidney cleanup snapshots retained"
            else:
                note = f"{patch_snapshot_count} patch rollback snapshots retained"

        return {
            "status": status,
            "note": note,
            "total_bytes": total_bytes,
            "watched_total_bytes": watched_total_bytes,
            "runtime_file_count": runtime_file_count,
            "runtime_total_bytes": runtime_total_bytes,
            "runtime_warn_total_gb": runtime_warn_total_gb,
            "runtime_danger_total_gb": runtime_danger_total_gb,
            "patch_snapshot_count": patch_snapshot_count,
            "patch_snapshot_bytes": patch_snapshot_bytes,
            "kidney_snapshot_count": kidney_snapshot_count,
            "kidney_snapshot_bytes": kidney_snapshot_bytes,
            "release_validation_extract_count": release_validation_extract_count,
            "release_validation_extract_bytes": release_validation_extract_bytes,
            "release_stage_count": release_stage_count,
            "release_stage_bytes": release_stage_bytes,
            "release_zip_count": release_zip_count,
            "release_zip_bytes": release_zip_bytes,
            "patch_snapshot_warn_count": patch_warn_count,
            "kidney_snapshot_warn_count": kidney_warn_count,
            "kidney_snapshot_warn_total_mb": kidney_warn_total_mb,
            "release_validation_extract_warn_total_mb": release_extract_warn_total_mb,
            "release_stage_warn_total_mb": release_stage_warn_total_mb,
            "release_zip_warn_count": release_zip_warn_count,
            "release_zip_warn_total_mb": release_zip_warn_total_mb,
        }


STORAGE_WATCH_SERVICE = StorageWatchService()
