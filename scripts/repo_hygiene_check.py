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
LFS_POINTER_MARKER = b"version https://git-lfs.github.com/spec/v1"
MAX_POINTER_BLOB_BYTES = 4096


def _run(cmd: list[str], *, cwd: Path | None = None) -> str:
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, cwd=str(cwd) if cwd else None)
    return out.decode("utf-8", errors="replace")


def tracked_files(repo_root: Path | None = None) -> list[str]:
    raw = _run(["git", "ls-files", "-z"], cwd=repo_root)
    return [item for item in raw.split("\x00") if item]


def is_git_work_tree(repo_root: Path | None = None) -> bool:
    try:
        return _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo_root).strip().lower() == "true"
    except Exception:
        return False


def is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(256)
    except OSError:
        return False
    return LFS_POINTER_MARKER in head


def is_lfs_tracked(rel_path: str, repo_root: Path | None = None) -> bool:
    try:
        output = _run(["git", "check-attr", "filter", "--", rel_path], cwd=repo_root)
        if output.strip().endswith(": lfs"):
            return True
    except Exception:
        pass
    # Fallback: parse .gitattributes directly (handles cases where check-attr is unset, e.g. LFS not initialized in env)
    try:
        import fnmatch
        root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
        attr_file = root / ".gitattributes"
        if attr_file.exists():
            norm = rel_path.replace("\\", "/")
            for line in attr_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    pattern = parts[0].strip()
                    attrs = " ".join(parts[1:]).lower()
                    if "lfs" in attrs and (fnmatch.fnmatch(norm, pattern) or fnmatch.fnmatch(norm, f"**/{pattern}") or pattern == norm):
                        return True
    except Exception:
        pass
    return False


def _git_blob_head(spec: str, repo_root: Path | None = None, *, max_bytes: int = 512) -> bytes:
    try:
        size_raw = _run(["git", "cat-file", "-s", spec], cwd=repo_root).strip()
        size = int(size_raw)
    except Exception:
        return b""
    if size <= 0 or size > MAX_POINTER_BLOB_BYTES:
        return b""
    try:
        out = subprocess.check_output(
            ["git", "cat-file", "blob", spec],
            stderr=subprocess.STDOUT,
            cwd=str(repo_root) if repo_root else None,
            timeout=10,
        )
    except Exception:
        return b""
    return out[: max(1, int(max_bytes or 512))]


def is_tracked_lfs_pointer(rel_path: str, repo_root: Path | None = None) -> bool:
    normalized = str(rel_path or "").replace("\\", "/").strip()
    if not normalized:
        return False
    for spec in (f":{normalized}", f"HEAD:{normalized}"):
        if LFS_POINTER_MARKER in _git_blob_head(spec, repo_root):
            return True
    return False


def run_hygiene(repo_root: Path | None = None) -> int:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    if not is_git_work_tree(root):
        print("repo_hygiene_check: SKIP (not a git work tree)")
        return 0

    violations: list[str] = []
    size_violations: list[str] = []

    for rel in tracked_files(root):
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

        abs_path = root / normalized
        if not abs_path.exists():
            continue
        size = abs_path.stat().st_size
        if (
            size > MAX_TRACKED_FILE_BYTES
            and not is_lfs_pointer(abs_path)
            and not is_lfs_tracked(normalized, root)
            and not is_tracked_lfs_pointer(normalized, root)
        ):
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


def main() -> int:
    return run_hygiene()


if __name__ == "__main__":
    sys.exit(main())
