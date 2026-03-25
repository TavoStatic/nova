from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent
POLICY_PATH = ROOT / "policy.json"
RUNTIME_DIR = ROOT / "runtime"
UPDATES_DIR = ROOT / "updates"
GENERATED_DEFINITIONS_DIR = RUNTIME_DIR / "test_sessions" / "generated_definitions"
PENDING_REVIEW_DIR = RUNTIME_DIR / "test_sessions" / "pending_review"
QUARANTINE_DIR = RUNTIME_DIR / "test_sessions" / "quarantine"
TEST_SESSIONS_DIR = RUNTIME_DIR / "test_sessions"
PREVIEWS_DIR = UPDATES_DIR / "previews"
SNAPSHOTS_DIR = UPDATES_DIR / "snapshots"
KIDNEY_ROOT = RUNTIME_DIR / "kidney"
KIDNEY_ARCHIVE_DIR = KIDNEY_ROOT / "archive"
KIDNEY_SNAPSHOTS_DIR = KIDNEY_ROOT / "snapshots"
KIDNEY_STATUS_PATH = KIDNEY_ROOT / "status.json"
KIDNEY_PROTECT_PATH = KIDNEY_ROOT / "protect_patterns.json"
PROMOTION_AUDIT_PATH = TEST_SESSIONS_DIR / "promotion_audit.jsonl"
DEFAULT_TEMP_MAX_BYTES = 500 * 1024 * 1024
_MANIFEST_NAMES = {"generated_manifest.json", "latest_manifest.json"}
_PROTECTED_TEST_SESSION_DIRS = {
    "generated_definitions",
    "pending_review",
    "quarantine",
}


def _load_policy() -> dict[str, Any]:
    try:
        payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def policy_kidney() -> dict[str, Any]:
    raw = _load_policy().get("kidney") or {}
    cfg = dict(raw if isinstance(raw, dict) else {})
    cfg.setdefault("enabled", True)
    cfg.setdefault("mode", "observe")
    cfg.setdefault("definition_max_age_days", 7)
    cfg.setdefault("definition_novelty_min", 0.4)
    cfg.setdefault("quarantine_max_age_hours", 48)
    cfg.setdefault("preview_max_age_days", 3)
    cfg.setdefault("snapshot_max_age_days", 30)
    cfg.setdefault("temp_max_age_days", 14)
    cfg.setdefault("temp_max_total_mb", 500)
    cfg.setdefault("protect_patterns", [])
    return cfg


def _now_ts() -> float:
    return time.time()


def _age_seconds(path: Path, now: float | None = None) -> float:
    reference = float(now if now is not None else _now_ts())
    try:
        return max(0.0, reference - float(path.stat().st_mtime))
    except Exception:
        return 0.0


def _load_json(path: Path, default: Any) -> Any:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return payload if isinstance(payload, type(default)) else default


def _load_protect_patterns() -> list[str]:
    stored = _load_json(KIDNEY_PROTECT_PATH, [])
    cfg = list(policy_kidney().get("protect_patterns") or [])
    merged: list[str] = []
    for value in cfg + stored:
        pattern = str(value or "").strip().lower()
        if pattern and pattern not in merged:
            merged.append(pattern)
    return merged


def add_protect_pattern(pattern: str) -> str:
    normalized = str(pattern or "").strip().lower()
    if not normalized:
        return "Usage: kidney protect <pattern>"
    patterns = _load_protect_patterns()
    if normalized in patterns:
        return f"Kidney protect pattern already active: {normalized}"
    patterns.append(normalized)
    KIDNEY_PROTECT_PATH.parent.mkdir(parents=True, exist_ok=True)
    KIDNEY_PROTECT_PATH.write_text(json.dumps(patterns, ensure_ascii=True, indent=2), encoding="utf-8")
    return f"Kidney protect pattern added: {normalized}"


def _is_protected(path: Path, patterns: list[str]) -> bool:
    low = str(path).lower()
    return any(pattern in low for pattern in patterns)


def _load_latest_audit_by_file() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not PROMOTION_AUDIT_PATH.exists():
        return out
    for line in PROMOTION_AUDIT_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        file_name = str(row.get("file") or "").strip()
        if file_name:
            out[file_name] = row
    return out


def _path_size_bytes(path: Path) -> int:
    try:
        if path.is_file():
            return int(path.stat().st_size)
        total = 0
        for child in path.rglob("*"):
            if child.is_file():
                total += int(child.stat().st_size)
        return total
    except Exception:
        return 0


def _build_candidate(path: Path, category: str, action: str, reason: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "path": str(path),
        "name": path.name,
        "category": category,
        "action": action,
        "reason": reason,
        "size_bytes": _path_size_bytes(path),
        "age_seconds": _age_seconds(path),
    }
    if isinstance(extra, dict):
        payload.update(extra)
    return payload


def scan_candidates() -> list[dict[str, Any]]:
    cfg = policy_kidney()
    now = _now_ts()
    protect_patterns = _load_protect_patterns()
    audit = _load_latest_audit_by_file()
    out: list[dict[str, Any]] = []

    definition_max_age = float(cfg.get("definition_max_age_days", 7) or 7) * 86400.0
    novelty_min = float(cfg.get("definition_novelty_min", 0.4) or 0.4)
    for path in sorted(GENERATED_DEFINITIONS_DIR.glob("*.json")) if GENERATED_DEFINITIONS_DIR.exists() else []:
        if path.name in _MANIFEST_NAMES or _is_protected(path, protect_patterns):
            continue
        age = _age_seconds(path, now)
        audit_row = audit.get(path.name) or {}
        metrics = dict(audit_row.get("metrics") or {}) if isinstance(audit_row.get("metrics"), dict) else {}
        novelty = metrics.get("novelty")
        reason = ""
        if age > definition_max_age:
            reason = f"definition_age_days>{cfg.get('definition_max_age_days', 7)}"
        elif novelty is not None and float(novelty or 0.0) < novelty_min:
            reason = f"definition_novelty<{novelty_min:.2f}"
        if reason:
            out.append(_build_candidate(path, "old_definition", "archive", reason, extra={"novelty": novelty}))

    quarantine_max_age = float(cfg.get("quarantine_max_age_hours", 48) or 48) * 3600.0
    demote_threshold = 0.90
    for root_name, root in (("pending_review", PENDING_REVIEW_DIR), ("quarantine", QUARANTINE_DIR)):
        for path in sorted(root.glob("*.json")) if root.exists() else []:
            if _is_protected(path, protect_patterns):
                continue
            age = _age_seconds(path, now)
            audit_row = audit.get(path.name) or {}
            metrics = dict(audit_row.get("metrics") or {}) if isinstance(audit_row.get("metrics"), dict) else {}
            fallback = metrics.get("fallback_overuse")
            status = str(audit_row.get("status") or "")
            reason = ""
            if age > quarantine_max_age:
                reason = f"{root_name}_age_limit"
            elif fallback is not None and float(fallback or 0.0) > demote_threshold:
                reason = f"fallback_overuse>{demote_threshold:.2f}"
            elif status in {"observed_review", "quarantined"} and age > quarantine_max_age:
                reason = f"stale_{status}"
            if reason:
                out.append(_build_candidate(path, "quarantined_waste", "delete", reason, extra={"fallback_overuse": fallback, "audit_status": status}))

    preview_max_age = float(cfg.get("preview_max_age_days", 3) or 3) * 86400.0
    for path in sorted(PREVIEWS_DIR.glob("*.txt")) if PREVIEWS_DIR.exists() else []:
        if _is_protected(path, protect_patterns):
            continue
        age = _age_seconds(path, now)
        if age <= preview_max_age:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        if "Status: eligible" in text:
            continue
        out.append(_build_candidate(path, "preview_junk", "delete", "preview_stale_not_eligible"))

    snapshot_max_age = float(cfg.get("snapshot_max_age_days", 30) or 30) * 86400.0
    for path in sorted(SNAPSHOTS_DIR.glob("snapshot_*.zip")) if SNAPSHOTS_DIR.exists() else []:
        if _is_protected(path, protect_patterns):
            continue
        if _age_seconds(path, now) > snapshot_max_age:
            out.append(_build_candidate(path, "stale_snapshot", "delete", "snapshot_age_limit"))
    for path in sorted(RUNTIME_DIR.glob("core_state*.json")) if RUNTIME_DIR.exists() else []:
        if path.name == "core_state.json" or _is_protected(path, protect_patterns):
            continue
        if _age_seconds(path, now) > snapshot_max_age:
            out.append(_build_candidate(path, "stale_snapshot", "delete", "core_state_backup_age_limit"))

    temp_max_age = float(cfg.get("temp_max_age_days", 14) or 14) * 86400.0
    temp_candidates: list[dict[str, Any]] = []
    if TEST_SESSIONS_DIR.exists():
        for path in sorted(TEST_SESSIONS_DIR.iterdir()):
            if path.name in _PROTECTED_TEST_SESSION_DIRS or _is_protected(path, protect_patterns):
                continue
            if _age_seconds(path, now) > temp_max_age:
                temp_candidates.append(_build_candidate(path, "temp_bloat", "delete", "test_session_run_age_limit"))
    for path in sorted(RUNTIME_DIR.glob("*.txt")) if RUNTIME_DIR.exists() else []:
        if _is_protected(path, protect_patterns):
            continue
        if _age_seconds(path, now) > temp_max_age:
            temp_candidates.append(_build_candidate(path, "temp_bloat", "delete", "runtime_text_age_limit"))
    if (RUNTIME_DIR / "tmp_probe").exists() and not _is_protected(RUNTIME_DIR / "tmp_probe", protect_patterns):
        if _age_seconds(RUNTIME_DIR / "tmp_probe", now) > temp_max_age:
            temp_candidates.append(_build_candidate(RUNTIME_DIR / "tmp_probe", "temp_bloat", "delete", "tmp_probe_age_limit"))

    size_cap = int(float(cfg.get("temp_max_total_mb", 500) or 500) * 1024 * 1024)
    total_temp_size = sum(int(item.get("size_bytes", 0) or 0) for item in temp_candidates)
    if total_temp_size > size_cap:
        deficit = total_temp_size - size_cap
        running = 0
        for item in sorted(temp_candidates, key=lambda row: (float(row.get("age_seconds", 0.0) or 0.0), int(row.get("size_bytes", 0) or 0)), reverse=True):
            item["reason"] = item.get("reason") or "temp_total_size_limit"
            running += int(item.get("size_bytes", 0) or 0)
            if running >= deficit:
                break
    out.extend(temp_candidates)
    return out


def _snapshot_paths(candidates: list[dict[str, Any]]) -> str:
    KIDNEY_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = KIDNEY_SNAPSHOTS_DIR / f"kidney_{time.strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(snapshot_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in candidates:
            source = Path(str(item.get("path") or ""))
            if not source.exists():
                continue
            if source.is_file():
                zf.write(source, arcname=source.name)
                continue
            for child in source.rglob("*"):
                if child.is_file():
                    try:
                        arc = f"{source.name}/{child.relative_to(source)}"
                        zf.write(child, arcname=arc)
                    except Exception:
                        continue
    return str(snapshot_path)


def _archive_target_for(path: Path) -> Path:
    KIDNEY_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamped_name = f"{path.stem}_{time.strftime('%Y%m%d_%H%M%S')}{path.suffix}"
    return KIDNEY_ARCHIVE_DIR / stamped_name


def _apply_candidate(item: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(item.get("path") or ""))
    action = str(item.get("action") or "").strip().lower()
    result = dict(item)
    if not path.exists():
        result["result"] = "missing"
        return result
    try:
        if action == "archive":
            target = _archive_target_for(path)
            shutil.move(str(path), str(target))
            result["target_path"] = str(target)
            result["result"] = "archived"
            return result
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        result["result"] = "deleted"
    except Exception as exc:
        result["result"] = f"error:{exc}"
    return result


def run_kidney(*, dry_run: bool = False, logger: Callable[[str], None] | None = None) -> dict[str, Any]:
    cfg = policy_kidney()
    mode = str(cfg.get("mode") or "observe").strip().lower() or "observe"
    enabled = bool(cfg.get("enabled", True))
    candidates = scan_candidates()
    summary = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "enabled": enabled,
        "mode": mode,
        "dry_run": bool(dry_run),
        "protect_patterns": _load_protect_patterns(),
        "candidate_count": len(candidates),
        "archive_count": sum(1 for item in candidates if str(item.get("action") or "") == "archive"),
        "delete_count": sum(1 for item in candidates if str(item.get("action") or "") == "delete"),
        "candidates": candidates,
        "snapshot_path": "",
        "applied": [],
    }
    if logger is not None:
        logger(f"mode={mode} dry_run={bool(dry_run)} candidates={len(candidates)}")
    if not enabled or dry_run or mode != "enforce" or not candidates:
        KIDNEY_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        KIDNEY_STATUS_PATH.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
        return summary

    summary["snapshot_path"] = _snapshot_paths(candidates)
    if logger is not None:
        logger(f"snapshot={summary['snapshot_path']}")
    applied = [_apply_candidate(item) for item in candidates]
    summary["applied"] = applied
    KIDNEY_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    KIDNEY_STATUS_PATH.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    for item in applied:
        if logger is not None:
            logger(f"{item.get('result')} {item.get('category')} {item.get('name')} reason={item.get('reason')}")
    return summary


def render_status() -> str:
    summary = _load_json(KIDNEY_STATUS_PATH, {})
    current = run_kidney(dry_run=True)
    lines = [
        "Kidney status:",
        f"- enabled: {bool(current.get('enabled'))}",
        f"- mode: {current.get('mode')}",
        f"- protect patterns: {', '.join(current.get('protect_patterns') or []) or 'none'}",
        f"- current candidates: {int(current.get('candidate_count', 0) or 0)}",
        f"- current archive candidates: {int(current.get('archive_count', 0) or 0)}",
        f"- current delete candidates: {int(current.get('delete_count', 0) or 0)}",
    ]
    if isinstance(summary, dict) and summary:
        lines.append(f"- last run: {str(summary.get('ts') or 'unknown')}")
        lines.append(f"- last snapshot: {str(summary.get('snapshot_path') or 'none')}")
    preview = current.get("candidates") or []
    if preview:
        lines.append("- next candidates:")
        for item in preview[:5]:
            lines.append(
                f"  {item.get('action')} {item.get('category')} {item.get('name')}"
                f" ({item.get('reason')})"
            )
    return "\n".join(lines)


def render_run(*, dry_run: bool) -> str:
    summary = run_kidney(dry_run=dry_run)
    label = "dry-run" if dry_run else f"mode={summary.get('mode')}"
    lines = [
        f"Kidney {label}: {int(summary.get('candidate_count', 0) or 0)} candidate(s)",
        f"archive={int(summary.get('archive_count', 0) or 0)} delete={int(summary.get('delete_count', 0) or 0)}",
    ]
    if summary.get("snapshot_path"):
        lines.append(f"snapshot={summary.get('snapshot_path')}")
    for item in list(summary.get("applied") or [])[:10]:
        lines.append(f"- {item.get('result')} {item.get('name')} ({item.get('reason')})")
    if not summary.get("applied"):
        for item in list(summary.get("candidates") or [])[:10]:
            lines.append(f"- {item.get('action')} {item.get('name')} ({item.get('reason')})")
    return "\n".join(lines)