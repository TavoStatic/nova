import os
import json
import shutil
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
OLLAMA_BASE = "http://127.0.0.1:11434"
TAGS = f"{OLLAMA_BASE}/api/tags"

def ok(msg): print(f"[OK]   {msg}")
def warn(msg): print(f"[WARN] {msg}")
def fail(msg): print(f"[FAIL] {msg}")

def main():
    print("Nova Diagnostics\n")

    # Disk
    try:
        usage = shutil.disk_usage(str(ROOT))
        free_gb = usage.free / (1024**3)
        ok(f"Disk free under {ROOT}: {free_gb:.2f} GB") if free_gb >= 2 else warn(f"Disk free under {ROOT}: {free_gb:.2f} GB (low)")
    except Exception as e:
        warn(f"Disk check skipped: {e}")

    # venv python
    venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    ok(f"venv python found: {venv_py}") if venv_py.exists() else fail(f"venv python missing: {venv_py}")

    # core script
    core = ROOT / "nova_core.py"
    ok(f"nova_core.py found: {core}") if core.exists() else fail(f"nova_core.py missing: {core}")

    # Ollama
    try:
        r = requests.get(TAGS, timeout=2)
        if r.status_code == 200:
            ok("Ollama API up")
            data = r.json()
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            if models:
                ok(f"Ollama models: {', '.join(models[:8])}" + (" ..." if len(models) > 8 else ""))
            else:
                warn("Ollama returned no models (pull a model?)")
        else:
            fail(f"Ollama API responded: HTTP {r.status_code}")
    except Exception as e:
        fail(f"Ollama API down: {e}")

    # Memory folder
    mem_dir = ROOT / "memory"
    if mem_dir.exists():
        ok(f"Memory dir exists: {mem_dir}")
    else:
        warn(f"Memory dir missing (optional): {mem_dir}")

    # Logs folder
    log_dir = ROOT / "logs"
    if log_dir.exists():
        ok(f"Logs dir exists: {log_dir}")
    else:
        warn(f"Logs dir missing (guard will create it): {log_dir}")

    print("\nDone.")

if __name__ == "__main__":
    main()