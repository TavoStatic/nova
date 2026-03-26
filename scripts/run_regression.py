#!/usr/bin/env python3
"""Compact regression runner for Nova.

Runs a fast, deterministic set of checks used before handoff or restart tests.
Exit code is non-zero if any step fails.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
PY = str(Path(sys.executable).resolve())


def run_step(name: str, cmd: list[str]) -> int:
    print(f"\n=== {name} ===")
    print("$ " + " ".join(cmd))
    process = subprocess.run(cmd, cwd=str(BASE))
    if process.returncode != 0:
        print(f"[FAIL] {name} (exit={process.returncode})")
    else:
        print(f"[OK] {name}")
    return process.returncode


def main() -> int:
    regression_tests = [
        "tests.test_memory_scope",
        "tests.test_memory_capture.TestMemoryCapture.test_mem_add_and_recall",
        "tests.test_http_identity_chat.TestHttpIdentityChat.test_http_pending_correction_flow",
        "tests.test_http_identity_chat.TestHttpIdentityChat.test_http_queue_status_runs_direct_tool_and_records_ledger",
        "tests.test_http_identity_chat.TestHttpIdentityChat.test_http_queue_status_followup_uses_structured_tool_state",
        "tests.test_http_identity_chat.TestHttpIdentityChat.test_http_queue_status_report_and_seam_followups_use_structured_state",
        "tests.test_nova_http.TestNovaHttpProfile.test_creator_query_uses_hard_answer_before_grounded_lookup",
        "tests.test_regression_contracts",
        "tests.test_http_resume_pending",
        "tests.test_run_test_session",
        "tests.test_tool_registry",
        "tests.test_policy_commands",
    ]

    steps = [
        (
            "Python compile check",
            [
                PY,
                "-m",
                "py_compile",
                "nova_core.py",
                "nova_http.py",
                "memory.py",
                "conversation_manager.py",
                "planner_decision.py",
                "action_planner.py",
            ],
        ),
        (
            "Focused unit tests",
            [PY, "-m", "unittest", "-q", *regression_tests],
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