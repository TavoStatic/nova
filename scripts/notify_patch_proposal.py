"""Notify about a saved patch preview.

Usage:
  python scripts/notify_patch_proposal.py [path/to/preview.txt]

Behavior:
- If a file path is provided, use it; otherwise pick the newest file under `updates/previews/`.
- If the `gh` CLI is available and authenticated, create a new issue with the preview contents.
- Otherwise, print the preview path and instructions the user can paste into GitHub.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
PREVIEWS = ROOT / "updates" / "previews"


def find_latest_preview() -> Path | None:
    if not PREVIEWS.exists():
        return None
    files = sorted(PREVIEWS.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def gh_available() -> bool:
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def create_issue(title: str, body: str) -> bool:
    try:
        p = subprocess.run(["gh", "issue", "create", "--title", title, "--body", body], capture_output=True, text=True)
        if p.returncode == 0:
            print("Created GitHub issue:")
            print(p.stdout)
            return True
        else:
            print("gh failed:", p.stderr)
            return False
    except Exception as e:
        print("gh invocation failed:", e)
        return False


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    preview_path = Path(arg) if arg else find_latest_preview()
    if not preview_path or not preview_path.exists():
        print("No preview file found. Generate a patch preview first; previews live in updates/previews/.")
        sys.exit(1)

    title = f"Patch preview: {preview_path.name}"
    body = preview_path.read_text(encoding="utf-8")

    if gh_available():
        ok = create_issue(title, body)
        if not ok:
            print("Failed to create issue via gh. You can manually create an issue with the following content:\n")
            print("---\n")
            print(body)
            print("---\n")
            print(f"Preview file: {preview_path}")
            sys.exit(1)
    else:
        print("gh CLI not available. To post this preview to GitHub, run:\n")
        print(f"  gh issue create --title \"{title}\" --body-file {preview_path}\n")
        print("Or paste the preview contents into a new issue.\n")
        print(f"Preview file: {preview_path}")


if __name__ == '__main__':
    main()
