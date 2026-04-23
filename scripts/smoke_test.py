#!/usr/bin/env python3
"""Simple smoke test for Nova workspace.

Checks:
- import `task_engine.analyze_request` and call it with a short prompt (safe, non-destructive)
- import `capabilities.describe_capabilities`
- run `health.py check` in base-package or runtime mode and report exit code/output
"""

import argparse
from pathlib import Path
import importlib
import os
import subprocess
import sys


BASE_DIR = Path(__file__).resolve().parents[1]


def run_health_check(tier: str = "runtime"):
    if os.environ.get("SKIP_HEALTH") or os.environ.get("CI"):
        print("Skipping health.py check (SKIP_HEALTH/CI set).")
        return True

    cmd = [sys.executable, str(BASE_DIR / "health.py"), "check"]
    if tier == "base":
        cmd.append("--skip-ollama")

    process = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    print("health.py exit:", process.returncode)
    print(process.stdout)
    if process.stderr:
        print("health.py stderr:\n", process.stderr)
    return process.returncode == 0


def import_checks():
    ok = True
    try:
        task_engine = importlib.import_module("task_engine")
        analyze_request = getattr(task_engine, "analyze_request", None)
        print("task_engine.analyze_request:", bool(callable(analyze_request)))
        if callable(analyze_request):
            try:
                result = analyze_request("smoke test: hello")
                print("analyze_request returned type:", type(result))
            except Exception as exc:
                print("analyze_request call raised:", exc)
                ok = False
    except Exception as exc:
        print("Failed importing task_engine:", exc)
        ok = False

    try:
        capabilities = importlib.import_module("capabilities")
        describe_capabilities = getattr(capabilities, "describe_capabilities", None)
        print("capabilities.describe_capabilities:", bool(callable(describe_capabilities)))
        if callable(describe_capabilities):
            try:
                document = describe_capabilities()
                print("describe_capabilities output (truncated):", str(document)[:400])
            except Exception as exc:
                print("describe_capabilities raised:", exc)
                ok = False
    except Exception as exc:
        print("Failed importing capabilities:", exc)
        ok = False

    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=["base", "runtime"], default="runtime")
    args = parser.parse_args()

    print("Nova smoke test starting...", flush=True)
    print(f"Smoke tier: {args.tier}", flush=True)
    imports_ok = import_checks()
    health_ok = run_health_check(tier=args.tier)
    if imports_ok and health_ok:
        print(f"SMOKE TEST [{args.tier.upper()}]: OK")
        sys.exit(0)

    print(f"SMOKE TEST [{args.tier.upper()}]: FAILED")
    sys.exit(2)


if __name__ == "__main__":
    main()