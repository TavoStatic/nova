import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
POLICY_PATH = BASE_DIR / "policy.json"


def load_allowed_root() -> Path:
    try:
        if POLICY_PATH.exists():
            data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
            root = data.get("allowed_root")
            if root:
                return Path(root).resolve()
    except Exception:
        pass
    return BASE_DIR


# ✅ Allowed root (scoped access)
ALLOWED_ROOT = load_allowed_root()

def is_within_allowed(path: Path) -> bool:
    try:
        path.resolve().relative_to(ALLOWED_ROOT)
        return True
    except Exception:
        return False

def safe_path(user_path: str) -> Path:
    p = Path(user_path)
    if not p.is_absolute():
        p = (ALLOWED_ROOT / p)
    p = p.resolve()

    if not is_within_allowed(p):
        raise PermissionError(f"Denied: path is outside allowed root: {ALLOWED_ROOT}")
    return p

def cmd_read(args: list[str]) -> int:
    if not args:
        print("Usage: agent.py read <relative_or_full_path_inside_allowed_root>")
        return 2

    p = safe_path(args[0])

    if not p.exists() or not p.is_file():
        print(f"Not a file: {p}")
        return 2

    # Keep it simple: treat as text; if it's binary, you'll see decode issues
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"Failed to read: {p}\n{e}")
        return 1

    print(f"--- BEGIN FILE: {p} ---\n")
    print(text)
    print(f"\n--- END FILE: {p} ---")
    return 0

def cmd_find(args: list[str]) -> int:
    if not args:
        print('Usage: agent.py find "<keyword>" [subfolder_relative_to_allowed_root]')
        return 2

    keyword = args[0].lower()
    start = ALLOWED_ROOT if len(args) == 1 else safe_path(args[1])

    if not start.exists() or not start.is_dir():
        print(f"Not a folder: {start}")
        return 2

    # File types worth searching by default
    exts = {".txt", ".md", ".log", ".json", ".xml", ".csv", ".ini", ".conf", ".php", ".js", ".ts", ".css", ".html", ".htm", ".py", ".sql"}

    hits = []
    for root, _, files in os.walk(start):
        for name in files:
            p = Path(root) / name
            if p.suffix.lower() not in exts:
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if keyword in content.lower():
                hits.append(str(p))

    if not hits:
        print("No matches found.")
        return 0

    print("Matches:")
    for h in hits[:200]:
        print(h)
    if len(hits) > 200:
        print(f"...and {len(hits) - 200} more")
    return 0

def cmd_ls(args: list[str]) -> int:
    target = ALLOWED_ROOT if not args else safe_path(args[0])
    if not target.exists() or not target.is_dir():
        print(f"Not a folder: {target}")
        return 2

    for p in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        kind = "DIR " if p.is_dir() else "FILE"
        print(f"{kind}  {p.name}")
    return 0

def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: agent.py <ls|read|find> ...")
        return 2

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    if cmd == "ls":
        return cmd_ls(args)
    if cmd == "read":
        return cmd_read(args)
    if cmd == "find":
        return cmd_find(args)

    print(f"Unknown command: {cmd}")
    return 2

if __name__ == "__main__":
    raise SystemExit(main())