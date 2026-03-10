#!/usr/bin/env python3
"""Simple smoke test for Nova workspace.

Checks:
- import `task_engine.analyze_request` and call it with a short prompt (safe, non-destructive)
- import `capabilities.describe_capabilities`
- run `health.py check` as a subprocess and report exit code/output
"""
from pathlib import Path
import subprocess
import sys
import importlib
import os

BASE_DIR = Path(__file__).resolve().parent

def run_health_check():
    # Allow skipping health check in CI or constrained environments
    if os.environ.get("SKIP_HEALTH") or os.environ.get("CI"):
        print("Skipping health.py check (SKIP_HEALTH/CI set).")
        return True

    p = subprocess.run([sys.executable, str(BASE_DIR / "health.py"), "check"], capture_output=True, text=True)
    print("health.py exit:", p.returncode)
    print(p.stdout)
    if p.stderr:
        print("health.py stderr:\n", p.stderr)
    return p.returncode == 0

def import_checks():
    ok = True
    try:
        te = importlib.import_module("task_engine")
        ar = getattr(te, "analyze_request", None)
        print("task_engine.analyze_request:", bool(callable(ar)))
        if callable(ar):
            try:
                res = ar("smoke test: hello")
                print("analyze_request returned type:", type(res))
            except Exception as e:
                print("analyze_request call raised:", e)
                ok = False
    except Exception as e:
        print("Failed importing task_engine:", e)
        ok = False

    try:
        caps = importlib.import_module("capabilities")
        desc = getattr(caps, "describe_capabilities", None)
        print("capabilities.describe_capabilities:", bool(callable(desc)))
        if callable(desc):
            try:
                doc = desc()
                print("describe_capabilities output (truncated):", str(doc)[:400])
            except Exception as e:
                print("describe_capabilities raised:", e)
                ok = False
    except Exception as e:
        print("Failed importing capabilities:", e)
        ok = False

    return ok

def main():
    print("Nova smoke test starting...", flush=True)
    imp_ok = import_checks()
    health_ok = run_health_check()
    if imp_ok and health_ok:
        print("SMOKE TEST: OK")
        sys.exit(0)
    else:
        print("SMOKE TEST: FAILED")
        sys.exit(2)

if __name__ == '__main__':
    main()
