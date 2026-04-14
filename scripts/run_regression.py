#!/usr/bin/env python3
"""Compact regression runner for Nova.

Runs a fast, deterministic set of checks used before handoff or restart tests.
Exit code is non-zero if any step fails.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import unittest
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
PY = str(Path(sys.executable).resolve())

COMPILE_TARGETS = [
    "nova_core.py",
    "nova_http.py",
    "memory.py",
    "conversation_manager.py",
    "planner_decision.py",
    "action_planner.py",
]

TEST_LANES: dict[str, list[str]] = {
    "unit": [
        "tests.test_health",
        "tests.test_smoke_test",
        "tests.test_action_planner",
        "tests.test_autonomy_maintenance",
        "tests.test_behavior_metrics_service",
        "tests.test_chat_identity_service",
        "tests.test_control_actions_service",
        "tests.test_control_assets_service",
        "tests.test_control_auth_service",
        "tests.test_control_status_cache_service",
        "tests.test_control_status_service",
        "tests.test_control_telemetry_service",
        "tests.test_fulfillment_flow_service",
        "tests.test_http_session_store",
        "tests.test_http_test_session_helpers",
        "tests.test_identity_memory_service",
        "tests.test_memory_adapter_service",
        "tests.test_memory_scope",
        "tests.test_nova_fulfillment_routing",
        "tests.test_nova_query_classifiers",
        "tests.test_nova_route_probing",
        "tests.test_nova_runtime_context",
        "tests.test_nova_turn_direction",
        "tests.test_ollama_test_guard",
        "tests.test_patch_control_service",
        "tests.test_policy_control_service",
        "tests.test_policy_manager_resolver",
        "tests.test_policy_manager_service",
        "tests.test_regression_contracts",
        "tests.test_release_status_service",
        "tests.test_run_regression",
        "tests.test_run_tools",
        "tests.test_runtime_artifacts_service",
        "tests.test_runtime_control_service",
        "tests.test_runtime_process_state_service",
        "tests.test_runtime_status_service",
        "tests.test_runtime_timeline_service",
        "tests.test_session_admin_service",
        "tests.test_session_state_service",
        "tests.test_smoke_e2e_script",
        "tests.test_smoke_placeholder",
        "tests.test_subconscious_control_service",
        "tests.test_supervisor_intent_rules",
        "tests.test_supervisor_patterns",
        "tests.test_supervisor_probes",
        "tests.test_supervisor_reflective_rules",
        "tests.test_supervisor_registry",
        "tests.test_supervisor_routing_rules",
        "tests.test_test_session_control_service",
        "tests.test_tool_console_service",
        "tests.test_tool_execution_service",
        "tests.test_tool_registry",
        "tests.test_tool_registry_service",
        "tests.test_voice_entrypoints",
        "tests.test_web_research_session_service",
    ],
    "behavior": [
        "tests.test_core_identity_learning",
        "tests.test_http_chat_flow",
        "tests.test_http_identity_chat",
        "tests.test_http_resume_pending",
        "tests.test_http_session_manager",
        "tests.test_nova_core_fulfillment_bridge",
        "tests.test_nova_http",
        "tests.test_policy_commands",
        "tests.test_subconscious_fallback_seams",
        "tests.test_supervisor_ownership_gate",
        "tests.test_weather_behavior",
    ],
    "integration": [
        "tests.test_integration_override",
        "tests.test_memory_capture.TestMemoryCapture.test_mem_add_and_recall",
        "tests.test_memory_cli",
        "tests.test_release_package_scripts",
        "tests.test_run_test_session",
        "tests.test_runtime_recovery",
        "tests.test_subconscious_live_simulator",
        "tests.test_subconscious_runner",
        "tests.test_windows_installer_scripts",
    ],
}


def run_step(name: str, cmd: list[str]) -> int:
    print(f"\n=== {name} ===")
    print("$ " + " ".join(cmd))
    process = subprocess.run(cmd, cwd=str(BASE))
    if process.returncode != 0:
        print(f"[FAIL] {name} (exit={process.returncode})")
    else:
        print(f"[OK] {name}")
    return process.returncode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Nova regression test lanes.")
    parser.add_argument(
        "lane",
        nargs="?",
        choices=[*TEST_LANES.keys(), "all"],
        help="Optional positional lane selector.",
    )
    parser.add_argument(
        "--lane",
        dest="lane_flag",
        choices=[*TEST_LANES.keys(), "all"],
        help="Named lane selector.",
    )
    parser.add_argument(
        "--list-lanes",
        action="store_true",
        help="Print available lanes and exit.",
    )
    parser.add_argument(
        "--verbosity",
        type=int,
        default=1,
        help="unittest runner verbosity for the selected lane(s).",
    )
    return parser.parse_args(argv)


def resolve_requested_lanes(args: argparse.Namespace) -> list[str]:
    requested = args.lane_flag or args.lane or "unit"
    if requested == "all":
        return list(TEST_LANES.keys())
    return [requested]


def print_available_lanes() -> None:
    print("Available test lanes:")
    for lane, test_names in TEST_LANES.items():
        print(f"- {lane}: {len(test_names)} targets")


def run_unittest_suite(test_names: list[str], *, verbosity: int = 1) -> tuple[bool, list[str]]:
    loader = unittest.defaultTestLoader
    suite = loader.loadTestsFromNames(test_names)
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    failed_ids: list[str] = []
    for case, _ in list(result.failures) + list(result.errors):
        try:
            failed_ids.append(case.id())
        except Exception:
            failed_ids.append(str(case))
    return result.wasSuccessful(), failed_ids


def run_test_lane(lane: str, *, verbosity: int = 1) -> int:
    regression_tests = TEST_LANES[lane]
    print(f"\n=== {lane.title()} lane ===")
    print("$ " + " ".join([PY, "-m", "unittest", *regression_tests]))
    ok, failed_ids = run_unittest_suite(regression_tests, verbosity=verbosity)
    if ok:
        print(f"[OK] {lane.title()} lane")
        return 0

    # CI can occasionally fail due transient state; retry once before escalating.
    print(f"\nRetrying {lane} lane once...")
    ok, failed_ids = run_unittest_suite(regression_tests, verbosity=verbosity)
    if ok:
        print(f"[OK] {lane.title()} lane (retry)")
        return 0

    print(f"\n{lane.title()} lane still failing. Rerunning with verbosity for diagnostics...")
    ok, failed_ids = run_unittest_suite(regression_tests, verbosity=2)

    if failed_ids:
        print(f"\nFailing {lane} tests:")
        for test_id in failed_ids:
            print(f"- {test_id}")
            # GitHub Actions annotation format for easier triage.
            print(f"::error::regression_test_failed::{test_id}")
    else:
        print("\n::error::regression_test_failed::unknown_test_failure")

    return 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list_lanes:
        print_available_lanes()
        return 0

    selected_lanes = resolve_requested_lanes(args)
    steps = [
        (
            "Python compile check",
            [
                PY,
                "-m",
                "py_compile",
                *COMPILE_TARGETS,
            ],
        ),
    ]

    for name, cmd in steps:
        code = run_step(name, cmd)
        if code != 0:
            return code

    for lane in selected_lanes:
        code = run_test_lane(lane, verbosity=max(1, int(args.verbosity or 1)))
        if code != 0:
            return code

    print("\nAll selected regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())