from __future__ import annotations

import argparse
import json
import subprocess
import time
import zipfile
from pathlib import Path

import kidney
import nova_core
from nova_safety_envelope import select_patch_candidate_definition_paths


ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
STATE_FILE = ROOT / "runtime" / "autonomy_maintenance_state.json"
MAINT_LOG = ROOT / "runtime" / "autonomy_maintenance.log"
LATEST_SUBCONSCIOUS = ROOT / "runtime" / "subconscious_runs" / "latest.json"
GENERATED_DEFS = ROOT / "runtime" / "test_sessions" / "generated_definitions"
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
            zf.write(source, arcname=f"tests/sessions/{source.name}")
        zf.writestr("nova_patch.json", json.dumps(manifest, ensure_ascii=True, indent=2))

    state["last_micro_patch_zip"] = str(zip_path)
    return zip_path


def _auto_apply_if_eligible(zip_path: Path) -> str:
    preview_out = nova_core.patch_preview(str(zip_path), write_report=True)
    if "Status: eligible" not in str(preview_out):
        return f"preview_not_eligible: {str(preview_out).strip()[:300]}"

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

    regression_status = _run_daily_regression_if_due(state)
    _append_log(regression_status)

    _save_state(state)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nova Phase 1 autonomy maintenance")
    parser.add_argument("--once", action="store_true", help="Run one maintenance cycle")
    args = parser.parse_args(argv)
    if args.once:
        return run_once()
    return run_once()


if __name__ == "__main__":
    raise SystemExit(main())
