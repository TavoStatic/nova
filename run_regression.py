#!/usr/bin/env python3
"""Compact regression runner for Nova.

Runs a fast, deterministic set of checks used before handoff or restart tests.
Exit code is non-zero if any step fails.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parent
PY = str(Path(sys.executable).resolve())


def run_step(name: str, cmd: list[str]) -> int:
    print(f"\n=== {name} ===")
    print("$ " + " ".join(cmd))
    p = subprocess.run(cmd, cwd=str(BASE))
    if p.returncode != 0:
        print(f"[FAIL] {name} (exit={p.returncode})")
    else:
        print(f"[OK] {name}")
    return p.returncode


def main() -> int:
    steps = [
        (
            "Python compile check",
            [PY, "-m", "py_compile", "nova_core.py", "nova_http.py", "memory.py", "health.py", "action_planner.py"],
        ),
        (
            "Focused unit tests",
            [
                PY,
                "-m",
                "unittest",
                "-q",
                "tests/test_action_planner.py",
                "tests/test_health.py",
                "tests/test_patch_guard.py",
                "tests/test_preference_logic.py",
                "tests/test_remember_command.py",
                "tests/test_memory_pinned.py",
                "tests/test_greeting_logic.py",
                "tests/test_policy_commands.py",
                "tests/test_chat_context_command.py",
                "tests/test_core_identity_learning.py",
                "tests/test_weather_behavior.py",
                "tests/test_web_research_continue.py",
                "tests/test_web_search_api.py",
                "tests/test_http_identity_chat.py",
                "tests/test_http_chat_persistence.py",
                "tests/test_http_session_manager.py",
                "tests/test_http_resume_pending.py",
            ],
        ),
    ]

    for name, cmd in steps:
        code = run_step(name, cmd)
        if code != 0:
            return code

    print("\nAll regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
