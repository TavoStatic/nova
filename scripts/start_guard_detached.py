from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.runtime_detach import spawn_unattached


def main() -> int:
    python_exe = ROOT / ".venv" / "Scripts" / "python.exe"
    guard_py = ROOT / "nova_guard.py"
    if not python_exe.exists():
        print(f"[FAIL] venv python missing: {python_exe}", file=sys.stderr)
        return 1
    if not guard_py.exists():
        print(f"[FAIL] nova_guard missing: {guard_py}", file=sys.stderr)
        return 1
    ok, pid, detail = spawn_unattached([str(python_exe), str(guard_py)], cwd=ROOT)
    if not ok:
        print(f"[FAIL] unattached guard start failed: {detail}", file=sys.stderr)
        return 1
    print(f"[OK]   guard start {detail} pid={pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
