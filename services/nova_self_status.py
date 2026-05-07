from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any


_FAILURE_RESULTS = {"fail", "failed", "failure", "error", "denied", "blocked"}
_FAILURE_TOKENS = ("fail", "error", "exception", "rollback", "blocked", "degraded", "unavailable", "offline")
_UPDATE_TOKENS = ("update", "patch", "apply", "preview", "approve", "revision", "promotion")


def _compact_text(value: Any, max_chars: int = 220) -> str:
    text = str(value or "").strip()
    return text[:max_chars]


def _event(kind: str, severity: str, title: str, detail: str = "", *, source: str = "", command: str = "") -> dict:
    return {
        "kind": _compact_text(kind, 40) or "status",
        "severity": _compact_text(severity, 24) or "info",
        "title": _compact_text(title, 120) or "Status signal",
        "detail": _compact_text(detail, 260),
        "source": _compact_text(source, 80),
        "command": _compact_text(command, 120),
    }


def read_recent_ops_events(path: Path, *, limit: int = 40) -> list[dict]:
    try:
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []

    events: list[dict] = []
    for line in lines[-max(1, int(limit or 40)):]:
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            events.append(row)
    return events


def _run_git(repo_root: Path, args: list[str], *, subprocess_run=subprocess.run) -> tuple[int, str]:
    try:
        proc = subprocess_run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception as exc:
        return 1, str(exc)
    return int(getattr(proc, "returncode", 1) or 0), str(getattr(proc, "stdout", "") or getattr(proc, "stderr", "") or "")


def build_repo_change_snapshot(repo_root: Path, *, subprocess_run=subprocess.run, max_files: int = 20) -> dict:
    root = Path(repo_root)
    code, status_text = _run_git(root, ["status", "--short"], subprocess_run=subprocess_run)
    if code != 0:
        return {"ok": False, "status": "unknown", "error": _compact_text(status_text, 240), "changed_count": 0, "files": []}

    status_lines = [line for line in status_text.splitlines() if line.strip()]
    if not status_lines:
        return {"ok": True, "status": "clean", "changed_count": 0, "files": [], "insertions": 0, "deletions": 0}

    file_status: dict[str, dict] = {}
    for line in status_lines:
        code_text = line[:2].strip() or line[:2]
        path_text = line[3:].strip() if len(line) > 3 else line.strip()
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1].strip()
        if not path_text:
            continue
        file_status[path_text] = {"path": path_text, "status": code_text, "insertions": 0, "deletions": 0}

    code, numstat_text = _run_git(root, ["diff", "--numstat", "HEAD", "--"], subprocess_run=subprocess_run)
    insertions = 0
    deletions = 0
    if code == 0:
        for line in numstat_text.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            added, removed, path_text = parts[0], parts[1], parts[2]
            if " -> " in path_text:
                path_text = path_text.split(" -> ", 1)[1].strip()
            try:
                added_count = int(added)
            except Exception:
                added_count = 0
            try:
                removed_count = int(removed)
            except Exception:
                removed_count = 0
            insertions += added_count
            deletions += removed_count
            row = file_status.setdefault(path_text, {"path": path_text, "status": "M", "insertions": 0, "deletions": 0})
            row["insertions"] = added_count
            row["deletions"] = removed_count

    files = list(file_status.values())
    files.sort(key=lambda item: str(item.get("path") or ""))
    return {
        "ok": True,
        "status": "dirty",
        "changed_count": len(files),
        "files": files[: max(1, int(max_files or 20))],
        "insertions": insertions,
        "deletions": deletions,
    }


def _ops_status_event(row: dict) -> dict | None:
    category = _compact_text(row.get("category"), 40).lower()
    action = _compact_text(row.get("action"), 80).lower()
    result = _compact_text(row.get("result"), 40).lower()
    detail = _compact_text(row.get("detail"), 260)
    joined = " ".join(part for part in (category, action, result, detail.lower()) if part)

    if result in _FAILURE_RESULTS or any(token in joined for token in _FAILURE_TOKENS):
        title = f"{category or 'runtime'} {action or 'event'} reported {result or 'trouble'}"
        return _event("failure", "failure", title, detail, source="ops_journal", command="health")

    if any(token in joined for token in _UPDATE_TOKENS):
        title = f"{category or 'runtime'} {action or 'event'} moved through {result or 'ok'}"
        return _event("updating", "info", title, detail, source="ops_journal", command="pulse")

    return None


def _repo_change_event(change_snapshot: dict, *, last_regression: str, last_regression_stale: bool) -> dict | None:
    snapshot = dict(change_snapshot or {})
    if str(snapshot.get("status") or "").strip().lower() != "dirty":
        return None
    files = [str((item or {}).get("path") or "").strip() for item in list(snapshot.get("files") or []) if isinstance(item, dict)]
    files = [item for item in files if item]
    changed_count = int(snapshot.get("changed_count", len(files)) or 0)
    insertions = int(snapshot.get("insertions", 0) or 0)
    deletions = int(snapshot.get("deletions", 0) or 0)
    shown = ", ".join(files[:5]) or "tracked files"
    if changed_count > 5:
        shown = f"{shown}, +{changed_count - 5} more"
    validation = "latest regression status is unknown"
    if last_regression:
        validation = f"latest regression is {last_regression.upper()}"
        if last_regression_stale:
            validation = f"{validation} but marked stale"
    severity = "info" if last_regression in {"ok", "pass", "passed"} and not last_regression_stale else "warning"
    detail = f"{changed_count} changed file(s): {shown}. Diff +{insertions}/-{deletions}; {validation}."
    return _event("updating", severity, "Local code changed since last accepted state", detail, source="git_worktree", command="git diff --stat")


def build_self_status_payload(
    *,
    pulse_payload: dict | None = None,
    recent_ops_events: list[dict] | None = None,
    repo_change_snapshot: dict | None = None,
) -> dict:
    pulse = dict(pulse_payload or {})
    events: list[dict] = []

    patch_activity = pulse.get("patch_activity") if isinstance(pulse.get("patch_activity"), dict) else {}
    rollback_count = int(patch_activity.get("rollback_count", 0) or 0)
    behavior_fail_count = int(patch_activity.get("behavior_fail_count", 0) or 0)
    approved_updates = int(pulse.get("approved_eligible_previews", 0) or 0)
    fallback_score = float(pulse.get("last_fallback_overuse_score", 0.0) or 0.0)
    fallback_pressure_active = bool(pulse.get("fallback_pressure_active", fallback_score >= 0.90))
    latest_queue_report_status = _compact_text(pulse.get("last_generated_queue_report_status"), 80).lower()
    last_regression = _compact_text(pulse.get("last_regression_status"), 120).lower()
    last_regression_stale = bool(pulse.get("last_regression_stale", False))

    if not bool(pulse.get("ollama_up", True)):
        events.append(_event("hurting", "failure", "Model runtime is offline", "Ollama is down, so Nova is holding to deterministic paths.", source="pulse", command="health"))
    if not bool(pulse.get("memory_ok", True)):
        events.append(_event("hurting", "warning", "Memory is unavailable", "Memory stats did not come back cleanly.", source="pulse", command="mem stats"))
    if rollback_count > 0:
        events.append(_event("failure", "failure", "Patch rollback pressure is present", f"{rollback_count} rollback(s) were seen in the last 24 hours.", source="patch_log", command="patch list-previews"))
    if behavior_fail_count > 0:
        events.append(_event("failure", "failure", "Behavior checks failed during patch activity", f"{behavior_fail_count} behavior failure(s) were seen in the last 24 hours.", source="patch_log", command="pulse"))
    if fallback_score >= 0.90 and fallback_pressure_active:
        events.append(_event("hurting", "warning", "Fallback pressure is high", f"Fallback overuse score is {fallback_score:.2f}.", source="pulse", command="learning status"))
    elif fallback_score >= 0.90:
        context = f"Latest generated queue report is {latest_queue_report_status or 'informational'}."
        events.append(_event("updating", "info", "Fallback training pressure is being worked", f"Fallback overuse score is {fallback_score:.2f}. {context}", source="pulse", command="learning status"))
    elif not bool(pulse.get("routing_stable", True)):
        events.append(_event("hurting", "warning", "Routing is unsettled", "Nova is staying conservative until routing stabilizes.", source="pulse", command="learning status"))
    if not last_regression_stale and last_regression and any(token in last_regression for token in ("fail", "error", "drift", "blocked")):
        events.append(_event("failure", "failure", "Latest regression is not green", str(pulse.get("last_regression_status") or ""), source="regression", command="run regression"))
    if approved_updates > 0 or bool(pulse.get("ready_for_validated_apply")):
        detail = f"{approved_updates} approved eligible update preview(s) are ready for review."
        update_zip = _compact_text(pulse.get("update_zip_path"), 180)
        if update_zip:
            detail = f"{detail} Latest package: {update_zip}"
        events.append(_event("updating", "info", "Validated update is waiting", detail, source="patch_pipeline", command="update now"))

    repo_event = _repo_change_event(
        dict(repo_change_snapshot or {}),
        last_regression=last_regression,
        last_regression_stale=last_regression_stale,
    )
    if repo_event:
        events.append(repo_event)

    for row in list(recent_ops_events or [])[-20:]:
        if not isinstance(row, dict):
            continue
        status_event = _ops_status_event(row)
        if status_event:
            events.append(status_event)

    severity_rank = {"failure": 3, "warning": 2, "info": 1}
    deduped: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for item in sorted(events, key=lambda event: severity_rank.get(str(event.get("severity")), 0), reverse=True):
        key = (str(item.get("kind") or ""), str(item.get("title") or ""), str(item.get("source") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    if any(event.get("severity") == "failure" for event in deduped):
        level = "failed"
        summary = "Nova has a failure signal that needs attention."
    elif any(event.get("severity") == "warning" for event in deduped):
        level = "hurting"
        summary = "Nova is running, but one or more support surfaces are strained."
    elif any(event.get("kind") == "updating" for event in deduped):
        level = "updating"
        summary = "Nova is stable and has update activity to review."
    else:
        level = "steady"
        summary = "Nova does not see current hurt, failure, or pending update signals."

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "level": level,
        "summary": summary,
        "events": deduped[:12],
        "repo_change": dict(repo_change_snapshot or {}),
    }


def render_self_status(payload: dict | None = None) -> str:
    data = dict(payload or {})
    events = list(data.get("events") or [])
    lines = [
        f"Nova Self Status - {data.get('generated_at') or ''}",
        f"Level: {data.get('level') or 'unknown'}",
        f"Summary: {data.get('summary') or 'No summary available.'}",
    ]
    if not events:
        lines.append("Signals:")
        lines.append("- No current hurt, failure, or update signals.")
        return "\n".join(lines)

    lines.append("Signals:")
    for item in events:
        label = str(item.get("severity") or "info").upper()
        line = f"- [{label}] {item.get('title')}"
        detail = _compact_text(item.get("detail"), 260)
        if detail:
            line = f"{line}: {detail}"
        command = _compact_text(item.get("command"), 120)
        if command:
            line = f"{line} (next: {command})"
        lines.append(line)
    return "\n".join(lines)
