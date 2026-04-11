"""Smoke E2E runner for Nova

Runs a minimal CI-style set of checks locally:
 - Run unit tests via `python -m unittest discover -v`
 - Run the memory e2e script `tests/run_memory_e2e.py` if present

Exits with non-zero code on failures and prints a concise report.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run_cmd(cmd, cwd=ROOT, timeout=600):
    try:
        env = os.environ.copy()
        # ensure local repo root is importable
        env["PYTHONPATH"] = str(ROOT)
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, p.stdout + "\n" + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 2, "TIMEOUT"


def main():
    print("Running Nova smoke e2e runner\n")

    results = []

    # 1) Preflight lane
    preflight_cmd = [PY, str(ROOT / "run_regression.py"), "preflight"]
    print("1) Running preflight lane: " + " ".join(preflight_cmd))
    rc, out = run_cmd(preflight_cmd)
    print(out)
    results.append(("preflight", rc))

    # 2) Unit lane
    unit_cmd = [PY, str(ROOT / "run_regression.py"), "unit"]
    print("2) Running unit lane: " + " ".join(unit_cmd))
    rc_unit, out_unit = run_cmd(unit_cmd)
    print(out_unit)
    results.append(("unit", rc_unit))

    # 3) Memory E2E script
    mem_e2e = ROOT / "tests" / "run_memory_e2e.py"
    if mem_e2e.exists():
        print("3) Running memory e2e: tests/run_memory_e2e.py")
        rc2, out2 = run_cmd([PY, str(mem_e2e)])
        print(out2)
        results.append(("memory_e2e", rc2))
    else:
        print("3) No memory e2e script found; skipping")
        results.append(("memory_e2e", 0))

    # Summary
    failed = [name for name, rc in results if rc != 0]
    if not failed:
        print("\nSMOKE E2E: PASS — all checks passed.")
        return 0
    else:
        print("\nSMOKE E2E: FAIL — failed checks:")
        for name, rc in results:
            if rc != 0:
                print(f" - {name}: rc={rc}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
