#!/usr/bin/env python3
"""Detached per-lane regression worker for Nova.

Runs exactly one regression lane as a background observation and records the
result into the regression truth registry, then republishes the derived
projection. autonomy_maintenance spawns this worker detached (it never waits),
so long lanes are not bounded by the guard-capped maintenance window and FULL
certification stays reachable for cold lanes.

The worker owns the observation: it performs the lane run, writes immutable
registry evidence, and publishes what the collected evidence supports. If the
lane is already running (lock held by a sibling), the worker is a no-op.

All IO paths (truth registry, status projection, lock note, worker log, lane
time budget) are injected via NOVA_REGRESSION_* environment variables by
autonomy_maintenance. NOVA_REGRESSION_RUNNER optionally overrides the lane
runner executable/script (defaults to scripts/run_regression.py); it exists so
the worker can be exercised against a reduced lane runner in verification.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from services.regression_status_projection import project_canonical_status
from services.regression_truth_registry import record_lane_result

REGRESSION_RUNNER = BASE / "scripts" / "run_regression.py"
INNER_PY = str(sys.executable)

_ENV_TRUTHS = "NOVA_REGRESSION_TRUTHS_PATH"
_ENV_STATUS = "NOVA_REGRESSION_STATUS_FILE"
_ENV_LOCK = "NOVA_REGRESSION_LOCK_FILE"
_ENV_MAX_SEC = "NOVA_REGRESSION_MAX_LANE_SECONDS"
_ENV_WORKER_LOG = "NOVA_REGRESSION_WORKER_LOG"
_ENV_RUNNER = "NOVA_REGRESSION_RUNNER"

_INTERNAL_ENV_KEYS = (_ENV_TRUTHS, _ENV_STATUS, _ENV_LOCK, _ENV_MAX_SEC, _ENV_WORKER_LOG, _ENV_RUNNER)

DEFAULT_MAX_LANE_SECONDS = 4 * 60 * 60


def _env_path(name: str, default: Path) -> Path:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return Path(default)
    path = Path(raw).expanduser()
    return path if path.is_absolute() else Path(BASE) / path


def truths_path() -> Path:
    return _env_path(_ENV_TRUTHS, BASE / "runtime" / "regression" / "regression_truth.jsonl")


def status_path() -> Path:
    return _env_path(_ENV_STATUS, BASE / "runtime" / "regression_status.json")


def max_lane_seconds() -> int:
    raw = str(os.environ.get(_ENV_MAX_SEC) or "").strip()
    if not raw:
        return DEFAULT_MAX_LANE_SECONDS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_LANE_SECONDS


def _runner_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in _INTERNAL_ENV_KEYS:
        env.pop(key, None)
    return env


def run_lane(
    lane: str,
    *,
    max_seconds: int,
) -> tuple[str, int, str, float]:
    runner = Path(str(os.environ.get(_ENV_RUNNER) or "")).expanduser()
    if not (runner.is_absolute() and runner.is_file()):
        runner = REGRESSION_RUNNER
    cmd = [INNER_PY, str(runner), lane]
    started_epoch = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(BASE),
            capture_output=True,
            text=True,
            timeout=int(max_seconds),
            env=_runner_env(),
        )
    except subprocess.TimeoutExpired as exc:
        chunks = [str(chunk or "") for chunk in (exc.stdout, exc.stderr)]
        output = "\n".join(chunks).strip()
        return "TIMED_OUT", -1, output, started_epoch
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode == 2 and "already running" in output.lower():
        return "ALREADY_RUNNING", 2, output, started_epoch
    if proc.returncode == 0:
        return "PASS", 0, output, started_epoch
    return "FAILED", int(proc.returncode), output, started_epoch


def publish_projection(*, fingerprint: str) -> dict:
    payload = project_canonical_status(truths_path(), fingerprint)
    try:
        path = status_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))
    except Exception:
        pass
    return payload


def main(argv: list[str] | None = None) -> int:
    args = [str(item) for item in list(sys.argv[1:] if argv is None else argv)]
    if len(args) < 2:
        print("usage: regression_lane_worker.py <lane> <source_fingerprint>")
        return 2
    lane = str(args[0]).strip()
    fingerprint = str(args[1]).strip()
    if not fingerprint:
        print("worker requires a non-empty source_fingerprint argument")
        return 2

    lane_status, returncode, output, started_epoch = run_lane(
        lane,
        max_seconds=max_lane_seconds(),
    )
    if lane_status == "ALREADY_RUNNING":
        print(f"[SKIP] lane {lane} is already running; truth registry left untouched")
        return 0

    record = {
        "lane": lane,
        "source_fingerprint": fingerprint,
        "status": lane_status,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_epoch)),
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_sec": round(max(0.0, time.time() - started_epoch), 1),
        "tests": 0,
        "failures": 0,
        "artifact_log_ref": str(os.environ.get(_ENV_WORKER_LOG) or "").strip(),
    }
    record_errors = record_lane_result(record, truths_path())
    if record_errors:
        print(f"[FAIL] lane={lane} status={lane_status} errors={';'.join(record_errors)}")
        return 0
    publish_projection(fingerprint=fingerprint)
    tail = output[-2000:]
    print(f"[OK] lane={lane} status={lane_status} returncode={returncode}")
    if tail:
        print(tail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())