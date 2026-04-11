from __future__ import annotations

import argparse
import json
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Callable

import kidney
import nova_core
from nova_safety_envelope import select_patch_candidate_definition_paths
from services.test_session_control import TEST_SESSION_CONTROL_SERVICE


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "runtime"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
TEST_SESSIONS_ROOT = RUNTIME_DIR / "test_sessions"
TEST_SESSION_RUNNER_PY = ROOT / "scripts" / "run_test_session.py"
STATE_FILE = RUNTIME_DIR / "autonomy_maintenance_state.json"
MAINT_LOG = RUNTIME_DIR / "autonomy_maintenance.log"
LATEST_SUBCONSCIOUS = RUNTIME_DIR / "subconscious_runs" / "latest.json"
GENERATED_DEFS = TEST_SESSIONS_ROOT / "generated_definitions"
UPDATES_DIR = ROOT / "updates"

AUTO_APPLY_THRESHOLD = 0.90


def _append_log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} | {message}"
    print(line, flush=True)
    MAINT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(MAINT_LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def _run_subconscious_pack() -> tuple[bool, str]:
    label = "phase1_auto"
    cmd = [str(VENV_PY), str(ROOT / "subconscious_runner.py"), "--label", label]
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=900)
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        if proc.returncode != 0:
            return False, output[-2000:]
        return True, output[-2000:]
    except Exception as exc:
        return False, str(exc)


def _available_test_session_definitions(limit: int = 80) -> list[dict]:
    return TEST_SESSION_CONTROL_SERVICE.available_test_session_definitions(
        TEST_SESSION_CONTROL_SERVICE.all_test_session_definition_roots(
            base_dir=ROOT,
            runtime_dir=RUNTIME_DIR,
        ),
        limit=limit,
    )


def _resolve_test_session_definition(session_name: str) -> Path | None:
    return TEST_SESSION_CONTROL_SERVICE.resolve_test_session_definition(
        session_name,
        _available_test_session_definitions(500),
    )


def _test_session_report_summaries(limit: int = 24) -> list[dict]:
    return TEST_SESSION_CONTROL_SERVICE.test_session_report_summaries(TEST_SESSIONS_ROOT, limit=limit)


def _generated_work_queue(limit: int = 24) -> dict:
    definitions = _available_test_session_definitions(500)
    return TEST_SESSION_CONTROL_SERVICE.generated_work_queue(
        definitions,
        _test_session_report_summaries(max(200, len(definitions) * 2)),
        limit=limit,
        runtime_dir=RUNTIME_DIR,
    )


def _run_test_session_definition(session_file: str) -> tuple[bool, str, dict]:
    return TEST_SESSION_CONTROL_SERVICE.run_test_session_definition(
        session_file,
        runner_path=TEST_SESSION_RUNNER_PY,
        venv_python=VENV_PY,
        base_dir=ROOT,
        resolve_definition_fn=_resolve_test_session_definition,
        available_definitions_fn=_available_test_session_definitions,
        report_summaries_fn=_test_session_report_summaries,
        subprocess_run=subprocess.run,
    )


def _run_next_generated_work_queue_item() -> tuple[bool, str, dict]:
    return TEST_SESSION_CONTROL_SERVICE.run_next_generated_work_queue_item(
        generated_work_queue_fn=_generated_work_queue,
        run_test_session_definition_fn=_run_test_session_definition,
    )


def _record_generated_queue_run(state: dict, ok: bool, msg: str, extra: dict | None = None) -> dict:
    selected = dict((extra or {}).get("selected") or {})
    latest_report = dict((extra or {}).get("latest_report") or {})
    work_queue = dict((extra or {}).get("work_queue") or {})
    raw_msg = str(msg or "")
    if raw_msg == "generated_work_queue_clear":
        status = "clear"
    elif raw_msg == "generated_work_queue_blocked":
        status = "blocked"
    else:
        status = "ok" if ok else "failed"
    payload = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "message": str(msg or ""),
        "selected_file": str(selected.get("file") or ""),
        "selected_status": str(selected.get("latest_status") or ""),
        "latest_report_status": str(latest_report.get("status") or ""),
        "latest_report_run_id": str(latest_report.get("run_id") or ""),
        "queue_open_count": int(work_queue.get("open_count", 0) or 0),
        "queue_actionable_count": int(work_queue.get("actionable_count", 0) or 0),
        "queue_count": int(work_queue.get("count", 0) or 0),
    }
    state["last_generated_queue_run"] = payload
    return payload


def _record_worker_cycle(*, cycle: int, interval_sec: int, status: str, code: int | None = None) -> None:
    state = _load_state()
    worker_state = dict(state.get("runtime_worker") or {})
    worker_state["interval_sec"] = max(1, int(interval_sec or 300))
    worker_state["last_cycle"] = max(1, int(cycle or 1))
    worker_state["cycle_count"] = max(int(worker_state.get("cycle_count", 0) or 0), max(1, int(cycle or 1)))
    if status == "running":
        worker_state["last_started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        worker_state["last_cycle_status"] = "running"
    else:
        worker_state["last_completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        worker_state["last_cycle_status"] = str(status or "unknown")
        worker_state["last_cycle_code"] = int(code or 0)
    state["runtime_worker"] = worker_state
    _save_state(state)


def _max_fallback_robustness(report: dict) -> float:
    best = 0.0
    for family in list(report.get("families") or []):
        for item in list(family.get("robust_signals") or []):
            if str(item.get("signal") or "").strip() != "fallback_overuse":
                continue
            try:
                score = float(item.get("robustness_score") or 0.0)
            except Exception:
                score = 0.0
            if score > best:
                best = score
    return best


def _build_micro_patch_zip(state: dict) -> Path | None:
    files = select_patch_candidate_definition_paths(GENERATED_DEFS)
    if not files:
        return None

    current_revision = int(nova_core._read_patch_revision() or 0)
    ts = time.strftime("%Y%m%d_%H%M%S")
    zip_path = UPDATES_DIR / f"autonomy_micro_patch_{ts}.zip"
    manifest = {
        "name": f"autonomy_micro_patch_{ts}",
        "notes": "Auto-generated from fallback_overuse robustness pressure.",
        "patch_revision": current_revision + 1,
        "min_base_revision": current_revision,
    }

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for source in files:
            zf.write(source, arcname=f"runtime/test_sessions/promoted/{source.name}")
        zf.writestr("nova_patch.json", json.dumps(manifest, ensure_ascii=True, indent=2))

    state["last_micro_patch_zip"] = str(zip_path)
    return zip_path


def _auto_apply_if_eligible(zip_path: Path) -> str:
    preview_out = nova_core.patch_preview(str(zip_path), write_report=True)
    if "Status: eligible" not in str(preview_out):
        return f"preview_not_eligible: {str(preview_out).strip()[:300]}"

    if "runtime/test_sessions/promoted/" in str(preview_out):
        return "skipped_generated_definitions_require_review"

    apply_out = nova_core.execute_patch_action("apply", str(zip_path), is_admin=True)
    return str(apply_out or "")


def _run_daily_regression_if_due(state: dict) -> str:
    today = time.strftime("%Y-%m-%d")
    if str(state.get("last_regression_date") or "") == today:
        return "daily_regression_skipped_already_ran"

    cmd = [str(VENV_PY), "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "--buffer"]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=5400)
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    summary = "OK" if proc.returncode == 0 else "FAILED"

    state["last_regression_date"] = today
    state["last_regression_status"] = summary
    state["last_regression_returncode"] = int(proc.returncode)
    state["last_regression_tail"] = output[-2000:]
    return f"daily_regression_{summary.lower()}"


def run_once() -> int:
    state = _load_state()

    ok, pack_out = _run_subconscious_pack()
    _append_log(f"subconscious_pack={'ok' if ok else 'fail'}")
    if not ok:
        state["last_error"] = pack_out
        _save_state(state)
        _append_log(pack_out)
        return 1

    if not LATEST_SUBCONSCIOUS.exists():
        _append_log("latest_subconscious_missing")
        return 1

    report = json.loads(LATEST_SUBCONSCIOUS.read_text(encoding="utf-8"))
    generated_at = str(report.get("generated_at") or "")
    threshold = float(state.get("auto_apply_threshold", AUTO_APPLY_THRESHOLD) or AUTO_APPLY_THRESHOLD)
    fallback_score = _max_fallback_robustness(report)

    state["auto_apply_threshold"] = threshold
    state["last_generated_at"] = generated_at
    state["last_fallback_overuse_score"] = fallback_score

    if fallback_score >= threshold:
        zip_path = _build_micro_patch_zip(state)
        if zip_path is None:
            state["last_auto_apply"] = "skipped_no_generated_defs"
            _append_log("auto_apply_skipped_no_generated_defs")
        else:
            apply_result = _auto_apply_if_eligible(zip_path)
            state["last_auto_apply"] = apply_result[:500]
            _append_log(f"auto_apply_result={apply_result[:200]}")
    else:
        state["last_auto_apply"] = "skipped_threshold"
        _append_log(f"auto_apply_skipped_threshold score={fallback_score:.2f} threshold={threshold:.2f}")

    kidney_summary = kidney.run_kidney(logger=lambda message: _append_log(f"[KIDNEY] {message}"))
    state["last_kidney_status"] = {
        "ts": kidney_summary.get("ts"),
        "mode": kidney_summary.get("mode"),
        "candidate_count": kidney_summary.get("candidate_count"),
        "archive_count": kidney_summary.get("archive_count"),
        "delete_count": kidney_summary.get("delete_count"),
        "snapshot_path": kidney_summary.get("snapshot_path"),
    }

    queue_ok, queue_msg, queue_extra = _run_next_generated_work_queue_item()
    queue_state = _record_generated_queue_run(state, queue_ok, queue_msg, queue_extra)
    _append_log(
        "generated_queue_"
        f"{queue_state.get('status')}"
        f" file={queue_state.get('selected_file') or '-'}"
        f" open={int(queue_state.get('queue_open_count', 0) or 0)}"
    )

    regression_status = _run_daily_regression_if_due(state)
    _append_log(regression_status)

    _save_state(state)
    return 0


def run_worker(
    *,
    interval_sec: int = 300,
    max_cycles: int = 0,
    continue_on_error: bool = True,
    run_once_fn: Callable[[], int] = run_once,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    normalized_interval = max(1, int(interval_sec or 300))
    normalized_max_cycles = max(0, int(max_cycles or 0))
    cycle = 0
    last_code = 0

    while True:
        cycle += 1
        _record_worker_cycle(cycle=cycle, interval_sec=normalized_interval, status="running")
        _append_log(f"worker_cycle_start cycle={cycle}")
        last_code = int(run_once_fn())
        cycle_status = "ok" if last_code == 0 else "failed"
        _record_worker_cycle(cycle=cycle, interval_sec=normalized_interval, status=cycle_status, code=last_code)
        _append_log(f"worker_cycle_end cycle={cycle} code={last_code}")

        if last_code != 0 and not continue_on_error:
            return last_code
        if normalized_max_cycles and cycle >= normalized_max_cycles:
            return last_code
        sleep_fn(float(normalized_interval))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nova Phase 1 autonomy maintenance")
    parser.add_argument("--once", action="store_true", help="Run one maintenance cycle")
    parser.add_argument("--loop", action="store_true", help="Run maintenance continuously")
    parser.add_argument("--interval-sec", type=int, default=300, help="Seconds between maintenance cycles in loop mode")
    parser.add_argument("--max-cycles", type=int, default=0, help="Optional cycle cap for loop mode; 0 means run continuously")
    parser.add_argument("--stop-on-error", action="store_true", help="Exit loop mode after the first failed cycle")
    args = parser.parse_args(argv)
    if args.loop:
        return run_worker(
            interval_sec=args.interval_sec,
            max_cycles=args.max_cycles,
            continue_on_error=not bool(args.stop_on_error),
        )
    if args.once:
        return run_once()
    return run_once()


if __name__ == "__main__":
    raise SystemExit(main())
