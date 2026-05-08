from __future__ import annotations

from pathlib import Path


MANIFEST_NAMES = {"generated_manifest.json", "latest_manifest.json"}


def iter_definition_files(root: Path) -> list[Path]:
    """Return all real test-session definition JSON files under root."""
    try:
        source_root = Path(root)
    except Exception:
        return []
    try:
        if not source_root.exists():
            return []
        files = [
            path
            for path in source_root.rglob("*.json")
            if path.is_file() and path.name not in MANIFEST_NAMES
        ]
    except Exception:
        return []
    return sorted(files, key=lambda path: path.as_posix().lower())


def count_definition_files(root: Path) -> int:
    return len(iter_definition_files(root))


def relative_definition_name(path: Path, root: Path) -> str:
    try:
        return Path(path).relative_to(Path(root)).as_posix()
    except Exception:
        return Path(path).name
