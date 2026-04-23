"""Repository hygiene guard for tracked source boundaries.

This script fails when tracked files include runtime/operator artifacts
or oversized non-LFS blobs that should not live in normal source tracking.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


FORBIDDEN_PREFIXES = (
    "runtime/",
    "logs/",
    "memory/",
    "updates/",
    "knowledge/web/",
    ".venv/",
    ".ci_venv/",
)

FORBIDDEN_EXACT = {
    "LAST_SESSION.json",
    "RESUME_HERE.txt",
    "nova_memory.sqlite",
}

FORBIDDEN_EXTENSIONS = {
    ".log",
    ".jsonl",
    ".sqlite",
    ".db",
    ".pyc",
    ".pyo",
}

MAX_TRACKED_FILE_BYTES = 50 * 1024 * 1024


def _run(cmd: list[str]) -> str:
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    return out.decode("utf-8", errors="replace")


def tracked_files() -> list[str]:
    raw = _run(["git", "ls-files", "-z"])
    return [item for item in raw.split("\x00") if item]


def is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(256)
    except OSError:
        return False
    return b"version https://git-lfs.github.com/spec/v1" in head


def is_lfs_tracked(rel_path: str) -> bool:
    try:
        output = _run(["git", "check-attr", "filter", "--", rel_path])
    except Exception:
        return False
    return output.strip().endswith(": lfs")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    size_violations: list[str] = []

    for rel in tracked_files():
        normalized = rel.replace("\\", "/")
        leaf = Path(normalized).name

        if any(normalized.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            violations.append(f"forbidden tracked prefix: {normalized}")

        if normalized in FORBIDDEN_EXACT:
            violations.append(f"forbidden tracked path: {normalized}")

        if "__pycache__/" in f"/{normalized}/":
            violations.append(f"forbidden cache path: {normalized}")

        suffix = Path(leaf).suffix.lower()
        if suffix in FORBIDDEN_EXTENSIONS:
            violations.append(f"forbidden tracked extension ({suffix}): {normalized}")

        abs_path = repo_root / normalized
        if not abs_path.exists():
            continue
        size = abs_path.stat().st_size
        if size > MAX_TRACKED_FILE_BYTES and not is_lfs_pointer(abs_path) and not is_lfs_tracked(normalized):
            size_mb = size / (1024 * 1024)
            size_violations.append(f"oversized tracked blob ({size_mb:.2f} MB): {normalized}")

    if violations or size_violations:
        print("repo_hygiene_check: FAIL")
        for row in violations:
            print(f"- {row}")
        for row in size_violations:
            print(f"- {row}")
        return 1

    print("repo_hygiene_check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
