"""Start nova_guard with survival check."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
GUARD = ROOT / "nova_guard.py"
LOG = ROOT / "runtime" / "guard_detached.log"

for p in (ROOT / "runtime" / "guard.lock", ROOT / "runtime" / "guard_pid.json", ROOT / "runtime" / "guard.stop"):
    try:
        p.unlink()
    except Exception:
        pass

LOG.write_text("", encoding="utf-8")
fh = open(LOG, "a", encoding="utf-8")
proc = subprocess.Popen(
    [str(PY), "-u", str(GUARD)],
    cwd=str(ROOT),
    stdout=fh,
    stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0),
)
print("spawned", proc.pid)
for i in range(15):
    time.sleep(1)
    code = proc.poll()
    print(f"t={i+1}s alive={code is None} code={code}")
    if code is not None:
        break
print("--- detached log ---")
print(LOG.read_text(encoding="utf-8")[-3000:])
print("--- logs/guard.log tail ---")
glog = ROOT / "logs" / "guard.log"
if glog.exists():
    print("\n".join(glog.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]))
