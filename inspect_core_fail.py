#!/usr/bin/env python3
"""Inspect runtime/core.fail and core_state.json for quick diagnostics."""
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
RUNTIME = BASE / "runtime"
FAIL = RUNTIME / "core.fail"
STATE = RUNTIME / "core_state.json"

def main():
    out = {}
    if FAIL.exists():
        try:
            out['core_fail'] = json.loads(FAIL.read_text(encoding='utf-8'))
        except Exception:
            out['core_fail'] = FAIL.read_text(encoding='utf-8')
    else:
        out['core_fail'] = None

    if STATE.exists():
        try:
            out['core_state'] = json.loads(STATE.read_text(encoding='utf-8'))
        except Exception:
            out['core_state'] = STATE.read_text(encoding='utf-8')
    else:
        out['core_state'] = None

    print(json.dumps(out, indent=2))
    return 0

if __name__ == '__main__':
    sys.exit(main())
