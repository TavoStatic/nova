#!/usr/bin/env python3
"""Compact regression runner for Nova.

Runs a fast, deterministic set of checks used before handoff or restart tests.
Exit code is non-zero if any step fails.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
PY = str(Path(sys.executable).resolve())
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
from services.validation_artifact_truth import VALIDATION_ARTIFACT_TRUTH_SERVICE
from services.regression_profile_inventory import build_regression_profile_inventory_payload
from services.regression_lanes import COMPACT_REGRESSION_LANES
from services.regression_lanes import SOURCE_PROFILE_LANES

REGRESSION_STATUS_FILE = BASE / "runtime" / "regression_status.json"
REGRESSION_LOCK_FILE = BASE / "runtime" / "regression.lock"

COMPILE_TARGETS = [
    "nova_core.py",
    "nova_http.py",
    "memory.py",
    "conversation_manager.py",
    "planner_decision.py",
    "action_planner.py",
]

TEST_LANES: dict[str, list[str]] = {
    lane: list(targets)
    for lane, targets in COMPACT_REGRESSION_LANES.items()
}
CANONICAL_REGRESSION_LANES = list(TEST_LANES.keys())
_REGRESSION_LOCK_DEPTH = 0


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
    inventory = build_regression_profile_inventory_payload(root=BASE, test_lanes=SOURCE_PROFILE_LANES)
    print(
        "Validation profile inventory: "
        f"{inventory.get('curated_test_file_count')} curated files, "
        f"{inventory.get('source_observed_count', inventory.get('outside_curated_count'))} source-observed outside compact lanes, "
        f"{inventory.get('install_profile_inactive_count')} stale inactive install-profile tests, "
        f"{inventory.get('install_profile_optional_inactive_count')} optional inactive install-profile tests"
    )


def run_unittest_suite(test_names: list[str], *, verbosity: int = 1) -> tuple[bool, list[str]]:
    previous_test_runner = os.environ.get("NOVA_TEST_RUNNER")
    previous_validation_runtime = os.environ.get("NOVA_VALIDATION_RUNTIME_DIR")
    previous_work_tree_db = os.environ.get("NOVA_WORK_TREE_DB")
    previous_memory_db = os.environ.get("NOVA_MEMORY_DB")
    validation_runtime = BASE / "runtime" / "validation"
    os.environ["NOVA_TEST_RUNNER"] = "1"
    os.environ.setdefault("NOVA_VALIDATION_RUNTIME_DIR", str(validation_runtime))
    os.environ.setdefault("NOVA_WORK_TREE_DB", str(validation_runtime / "_internal" / "work_tree.db"))
    os.environ.setdefault("NOVA_MEMORY_DB", str(validation_runtime / "nova_memory.sqlite"))
    loader = unittest.defaultTestLoader
    try:
        suite = loader.loadTestsFromNames(test_names)
        runner = unittest.TextTestRunner(verbosity=verbosity)
        result = runner.run(suite)
    finally:
        if previous_test_runner is None:
            os.environ.pop("NOVA_TEST_RUNNER", None)
        else:
            os.environ["NOVA_TEST_RUNNER"] = previous_test_runner
        if previous_validation_runtime is None:
            os.environ.pop("NOVA_VALIDATION_RUNTIME_DIR", None)
        else:
            os.environ["NOVA_VALIDATION_RUNTIME_DIR"] = previous_validation_runtime
        if previous_work_tree_db is None:
            os.environ.pop("NOVA_WORK_TREE_DB", None)
        else:
            os.environ["NOVA_WORK_TREE_DB"] = previous_work_tree_db
        if previous_memory_db is None:
            os.environ.pop("NOVA_MEMORY_DB", None)
        else:
            os.environ["NOVA_MEMORY_DB"] = previous_memory_db
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


def _is_canonical_regression_lane_set(lanes: list[str]) -> bool:
    return set(str(lane) for lane in lanes) == set(CANONICAL_REGRESSION_LANES)


def _should_publish_regression_status(*, lanes: list[str], status: str, returncode: int) -> bool:
    if int(returncode or 0) != 0:
        return True
    if str(status or "").strip().upper() != "OK":
        return True
    return _is_canonical_regression_lane_set(lanes)


def write_regression_status(
    *,
    status: str,
    lanes: list[str],
    returncode: int,
    detail: str = "",
    extra: dict | None = None,
) -> None:
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "date": time.strftime("%Y-%m-%d"),
        "status": str(status or "unknown").strip().upper() or "UNKNOWN",
        "lanes": [str(lane) for lane in lanes],
        "returncode": int(returncode),
        "detail": str(detail or "").strip()[:500],
        "source": "scripts/run_regression.py",
    }
    if isinstance(extra, dict):
        payload.update({str(key): value for key, value in extra.items()})
    try:
        REGRESSION_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        REGRESSION_STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception:
        pass


def _validation_artifact_status_extra(payload: dict) -> dict:
    latest_failure = payload.get("latest_failure") if isinstance(payload.get("latest_failure"), dict) else {}
    return {
        "validation_artifact_truth_status": str(payload.get("status") or ""),
        "validation_artifact_truth_ok": bool(payload.get("ok", True)),
        "validation_artifact_failure_count": int(payload.get("current_window_failure_count", 0) or 0),
        "validation_artifact_llm_unavailable_count": int(payload.get("current_window_llm_unavailable_count", 0) or 0),
        "validation_artifact_hidden_by_green_regression": bool(payload.get("hidden_by_green_regression", False)),
        "validation_artifact_latest_failure": {
            "path": str(latest_failure.get("path") or ""),
            "failure_kind": str(latest_failure.get("failure_kind") or ""),
            "final_answer": str(latest_failure.get("final_answer") or "")[:160],
        },
    }


def _regression_profile_status_extra(payload: dict) -> dict:
    gap_tests = [dict(item) for item in list(payload.get("gap_tests") or []) if isinstance(item, dict)]
    profile_drift_tests = [
        dict(item)
        for item in list(payload.get("profile_drift_tests") or [])
        if isinstance(item, dict)
    ]
    return {
        "test_profile_inventory_ok": bool(payload.get("ok", False)),
        "test_profile_profile_gap_count": int(payload.get("profile_gap_count", 0) or 0),
        "test_profile_profile_drift_count": int(payload.get("profile_drift_count", 0) or 0),
        "test_profile_profile_attention_count": int(payload.get("profile_attention_count", 0) or 0),
        "test_profile_curated_target_count": int(payload.get("curated_target_count", 0) or 0),
        "test_profile_curated_test_file_count": int(payload.get("curated_test_file_count", 0) or 0),
        "test_profile_root_test_file_count": int(payload.get("root_test_file_count", 0) or 0),
        "test_profile_all_test_file_count": int(payload.get("all_test_file_count", 0) or 0),
        "test_profile_source_observed_count": int(payload.get("source_observed_count", payload.get("outside_curated_count", 0)) or 0),
        "test_profile_outside_curated_count": int(payload.get("outside_curated_count", 0) or 0),
        "test_profile_install_profile_inactive_count": int(payload.get("install_profile_inactive_count", 0) or 0),
        "test_profile_install_profile_optional_inactive_count": int(payload.get("install_profile_optional_inactive_count", 0) or 0),
        "test_profile_unclassified_count": int(payload.get("unclassified_count", 0) or 0),
        "test_profile_gap_tests": gap_tests[:24],
        "test_profile_profile_drift_tests": profile_drift_tests[:24],
    }


def _pid_alive(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _read_regression_lock() -> dict:
    try:
        payload = json.loads(REGRESSION_LOCK_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _acquire_regression_lock(*, lanes: list[str]) -> tuple[bool, str]:
    global _REGRESSION_LOCK_DEPTH
    REGRESSION_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_regression_lock()
    existing_pid = int(existing.get("pid", 0) or 0)
    if existing_pid == int(os.getpid()) and _REGRESSION_LOCK_DEPTH > 0:
        _REGRESSION_LOCK_DEPTH += 1
        return True, ""
    if existing_pid and _pid_alive(existing_pid):
        owner_lanes = ", ".join(str(item) for item in list(existing.get("lanes") or []))
        started_at = str(existing.get("started_at") or "").strip()
        return False, f"regression already running (pid={existing_pid}, lanes={owner_lanes or 'unknown'}, started_at={started_at or 'unknown'})"
    payload = {
        "pid": os.getpid(),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "started_at_epoch": time.time(),
        "lanes": [str(lane) for lane in lanes],
    }
    REGRESSION_LOCK_FILE.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    _REGRESSION_LOCK_DEPTH = 1
    return True, ""


def _release_regression_lock() -> None:
    global _REGRESSION_LOCK_DEPTH
    if _REGRESSION_LOCK_DEPTH > 1:
        _REGRESSION_LOCK_DEPTH -= 1
        return
    _REGRESSION_LOCK_DEPTH = 0
    existing = _read_regression_lock()
    if int(existing.get("pid", 0) or 0) != int(os.getpid()):
        return
    try:
        REGRESSION_LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def audit_validation_artifacts_after_green_run(*, window_start_epoch: float, window_end_epoch: float) -> dict:
    return VALIDATION_ARTIFACT_TRUTH_SERVICE.payload(
        runtime_dir=BASE / "runtime",
        regression_status_path=REGRESSION_STATUS_FILE,
        limit=2000,
        window_start_epoch=window_start_epoch,
        window_end_epoch=window_end_epoch,
        regression_status_label="OK",
        regression_returncode=0,
        regression_generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list_lanes:
        print_available_lanes()
        return 0

    selected_lanes = resolve_requested_lanes(args)
    acquired, lock_reason = _acquire_regression_lock(lanes=selected_lanes)
    if not acquired:
        print(f"[FAIL] {lock_reason}")
        return 2

    try:
        return _run_regression_main(selected_lanes, args)
    finally:
        _release_regression_lock()


def _run_regression_main(selected_lanes: list[str], args: argparse.Namespace) -> int:
    run_started_epoch = time.time()
    profile_inventory = build_regression_profile_inventory_payload(root=BASE, test_lanes=SOURCE_PROFILE_LANES)
    profile_status_extra = _regression_profile_status_extra(profile_inventory)
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
            write_regression_status(status="FAILED", lanes=selected_lanes, returncode=code, detail=name, extra=profile_status_extra)
            return code

    for lane in selected_lanes:
        code = run_test_lane(lane, verbosity=max(1, int(args.verbosity or 1)))
        if code != 0:
            write_regression_status(status="FAILED", lanes=selected_lanes, returncode=code, detail=f"{lane} lane", extra=profile_status_extra)
            return code

    print("\nAll selected regression checks passed.")
    validation_truth = audit_validation_artifacts_after_green_run(
        window_start_epoch=run_started_epoch,
        window_end_epoch=time.time(),
    )
    if not bool(validation_truth.get("ok", True)):
        status = str(validation_truth.get("status") or "validation_artifact_failure")
        failure_count = int(validation_truth.get("current_window_failure_count", 0) or 0)
        llm_count = int(validation_truth.get("current_window_llm_unavailable_count", 0) or 0)
        detail = f"validation_artifact_truth:{status};failures={failure_count};llm_unavailable={llm_count}"
        print(f"[FAIL] {detail}")
        if _should_publish_regression_status(lanes=selected_lanes, status="FAILED", returncode=1):
            write_regression_status(
                status="FAILED",
                lanes=selected_lanes,
                returncode=1,
                detail=detail,
                extra={**profile_status_extra, **_validation_artifact_status_extra(validation_truth)},
            )
        return 1

    if _should_publish_regression_status(lanes=selected_lanes, status="OK", returncode=0):
        write_regression_status(
            status="OK",
            lanes=selected_lanes,
            returncode=0,
            extra={**profile_status_extra, **_validation_artifact_status_extra(validation_truth)},
        )
    else:
        print("[INFO] Partial regression lane pass did not overwrite canonical regression_status.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
