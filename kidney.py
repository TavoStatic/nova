from __future__ import annotations

import json
import hashlib
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

from services.nova_runtime_context import GENERATED_DEFINITIONS_DIR
from services.nova_runtime_context import PENDING_REVIEW_DIR
from services.nova_runtime_context import PROMOTED_DEFINITIONS_DIR
from services.nova_runtime_context import PROMOTION_AUDIT_LOG
from services.nova_runtime_context import QUARANTINE_DIR
from services.nova_runtime_context import RUNTIME_DIR
from services.nova_runtime_context import TEST_SESSIONS_DIR
from services.nova_runtime_context import runtime_scope_name
from services.test_session_definitions import iter_definition_files


ROOT = Path(__file__).resolve().parent
POLICY_PATH = ROOT / "policy.json"
UPDATES_DIR = RUNTIME_DIR / "updates" if runtime_scope_name() == "validation" else ROOT / "updates"
PREVIEWS_DIR = UPDATES_DIR / "previews"
SNAPSHOTS_DIR = UPDATES_DIR / "snapshots"
KIDNEY_ROOT = RUNTIME_DIR / "kidney"
KIDNEY_ARCHIVE_DIR = KIDNEY_ROOT / "archive"
KIDNEY_SNAPSHOTS_DIR = KIDNEY_ROOT / "snapshots"
KIDNEY_STATUS_PATH = KIDNEY_ROOT / "status.json"
KIDNEY_PROTECT_PATH = KIDNEY_ROOT / "protect_patterns.json"
KIDNEY_RETIRED_DEFINITIONS_PATH = KIDNEY_ROOT / "retired_generated_definitions.json"
PROMOTION_AUDIT_PATH = PROMOTION_AUDIT_LOG
DEFAULT_TEMP_MAX_BYTES = 500 * 1024 * 1024
_MANIFEST_NAMES = {"generated_manifest.json", "latest_manifest.json"}
_PROTECTED_TEST_SESSION_DIRS = {
    "generated_definitions",
    "promoted",
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
    cfg.setdefault("definition_max_age_days", 2)
    cfg.setdefault("definition_novelty_min", 0.5)
    cfg.setdefault("quarantine_max_age_hours", 12)
    cfg.setdefault("preview_max_age_days", 1)
    cfg.setdefault("snapshot_max_age_days", 5)
    cfg.setdefault("snapshot_max_count", 2)
    cfg.setdefault("snapshot_max_total_gb", 1)
    cfg.setdefault("cleanup_snapshot_max_age_days", 2)
    cfg.setdefault("cleanup_snapshot_max_count", 8)
    cfg.setdefault("cleanup_snapshot_max_total_mb", 32)
    cfg.setdefault("temp_max_age_days", 2)
    cfg.setdefault("temp_max_total_mb", 50)
    cfg.setdefault("protect_patterns", [])
    cfg.setdefault("generated_definition_retire_cooldown_hours", 24)
    cfg.setdefault("exports_max_age_days", 3)
    cfg.setdefault("ledger_max_mb", 20)
    cfg.setdefault("release_extract_max_age_days", 3)
    cfg.setdefault("release_validation_extract_max_total_mb", 1024)
    cfg.setdefault("release_stage_max_age_days", 3)
    cfg.setdefault("release_stage_max_total_mb", 256)
    cfg.setdefault("subconscious_run_max_age_days", 2)
    cfg.setdefault("subconscious_run_keep_count", 24)
    cfg.setdefault("subconscious_run_max_flag", 400)
    cfg.setdefault("recovery_quarantine_max_age_days", 14)
    cfg.setdefault("recovery_quarantine_keep_count", 1)
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


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _load_retired_generated_definition_index(*, now: float | None = None) -> dict[str, dict[str, Any]]:
    stored = _load_json(KIDNEY_RETIRED_DEFINITIONS_PATH, {})
    if not isinstance(stored, dict):
        stored = {}

    cooldown_hours = float(policy_kidney().get("generated_definition_retire_cooldown_hours", 24) or 24)
    cooldown_seconds = max(0.0, cooldown_hours) * 3600.0
    current = float(now if now is not None else _now_ts())
    filtered: dict[str, dict[str, Any]] = {}
    changed = False

    for key, value in stored.items():
        if not isinstance(value, dict):
            changed = True
            continue
        retired_at_ts = float(value.get("retired_at_ts", 0.0) or 0.0)
        if cooldown_seconds > 0.0 and retired_at_ts > 0.0 and (current - retired_at_ts) > cooldown_seconds:
            changed = True
            continue
        filtered[str(key)] = value

    if changed:
        _save_json(KIDNEY_RETIRED_DEFINITIONS_PATH, filtered)
    return filtered


def load_retired_generated_definition_index() -> dict[str, dict[str, Any]]:
    return _load_retired_generated_definition_index()


def _definition_metadata(path: Path) -> dict[str, Any]:
    payload = _load_json(path, {})
    if not isinstance(payload, dict):
        payload = {}
    return {
        "source": str(payload.get("source") or "").strip(),
        "family_id": str(payload.get("family_id") or "").strip(),
        "variation_id": str(payload.get("variation_id") or "").strip(),
        "label": str(payload.get("label") or "").strip(),
    }


def _record_retired_generated_definition(
    path: Path,
    item: dict[str, Any],
    *,
    target_path: str = "",
    now: float | None = None,
) -> None:
    metadata = _definition_metadata(path)
    if metadata.get("source") != "subconscious_generated":
        return

    current = float(now if now is not None else _now_ts())
    index = _load_retired_generated_definition_index(now=current)
    index[path.name] = {
        "file": path.name,
        "fingerprint": _file_fingerprint(path),
        "family_id": metadata.get("family_id") or "",
        "variation_id": metadata.get("variation_id") or "",
        "label": metadata.get("label") or "",
        "source": metadata.get("source") or "",
        "category": str(item.get("category") or "").strip(),
        "action": str(item.get("action") or "").strip(),
        "reason": str(item.get("reason") or "").strip(),
        "retired_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(current)),
        "retired_at_ts": current,
        "source_path": str(path),
        "target_path": str(target_path or ""),
    }
    _save_json(KIDNEY_RETIRED_DEFINITIONS_PATH, index)


def _file_fingerprint(path: Path) -> str:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except Exception:
        return ""


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


_RELEASE_EXTRACT_PROTECT_NAMES = {"release_command_logs"}
_STORAGE_WATCH_DELETE_CATEGORIES = {
    "stale_snapshot",
    "release_extract_bloat",
    "release_stage_bloat",
    "subconscious_run_bloat",
    "recovery_quarantine_bloat",
}


def _flag_watched_dir_bloat(
    out: list[dict[str, Any]],
    *,
    root: Path,
    category: str,
    age_reason: str,
    size_reason: str,
    max_age_seconds: float,
    max_total_bytes: int,
    protect_patterns: list[str],
    now: float,
    protect_names: set[str] | None = None,
    max_count: int = 0,
    count_reason: str = "",
    max_flag: int = 0,
    skip_size: bool = False,
) -> None:
    """Age-out, count-cap, and size-cap directory trees the cycle already watches."""
    if not root.exists():
        return
    protected = set(protect_names or ())
    children = [
        child
        for child in root.iterdir()
        if child.is_dir() and child.name not in protected and not _is_protected(child, protect_patterns)
    ]
    children.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0.0, reverse=True)
    retained_bytes = 0
    retained_count = 0
    pending: list[dict[str, Any]] = []
    for child in children:
        age_seconds = _age_seconds(child, now)
        size_bytes = 0 if skip_size else _path_size_bytes(child)
        reason = ""
        if max_age_seconds > 0.0 and age_seconds > max_age_seconds:
            reason = age_reason
        elif max_count > 0 and retained_count >= max_count:
            reason = count_reason or size_reason
        elif max_total_bytes > 0 and not skip_size and retained_bytes + size_bytes > max_total_bytes:
            reason = size_reason
        else:
            retained_count += 1
            retained_bytes += size_bytes
            continue
        extra = {"size_bytes": size_bytes} if skip_size else None
        pending.append(_build_candidate(child, category, "delete", reason, extra=extra))
    pending.sort(key=lambda row: float(row.get("age_seconds") or 0.0), reverse=True)
    if max_flag > 0:
        pending = pending[:max_flag]
    out.extend(pending)


def scan_candidates() -> list[dict[str, Any]]:
    cfg = policy_kidney()
    now = _now_ts()
    protect_patterns = _load_protect_patterns()
    audit = _load_latest_audit_by_file()
    out: list[dict[str, Any]] = []

    definition_max_age = float(cfg.get("definition_max_age_days", 7) or 7) * 86400.0
    novelty_min = float(cfg.get("definition_novelty_min", 0.4) or 0.4)
    for path in iter_definition_files(GENERATED_DEFINITIONS_DIR):
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

    for path in iter_definition_files(PROMOTED_DEFINITIONS_DIR):
        if path.name in _MANIFEST_NAMES or _is_protected(path, protect_patterns):
            continue
        age = _age_seconds(path, now)
        if age > definition_max_age:
            out.append(_build_candidate(path, "old_promoted_definition", "archive", f"definition_age_days>{cfg.get('definition_max_age_days', 7)}"))

    quarantine_max_age = float(cfg.get("quarantine_max_age_hours", 48) or 48) * 3600.0
    demote_threshold = 0.90
    for root_name, root in (("pending_review", PENDING_REVIEW_DIR), ("quarantine", QUARANTINE_DIR)):
        for path in iter_definition_files(root):
            if _is_protected(path, protect_patterns):
                continue
            age = _age_seconds(path, now)
            audit_row = audit.get(path.name) or {}
            metrics = dict(audit_row.get("metrics") or {}) if isinstance(audit_row.get("metrics"), dict) else {}
            fallback = metrics.get("fallback_overuse")
            status = str(audit_row.get("status") or "")
            reason = ""
            if root_name == "pending_review":
                # Keep pending-review candidates available for operator review.
                # They should only be flushed once stale or if explicitly marked quarantined.
                if status == "quarantined":
                    reason = "pending_review_marked_quarantined"
                elif age > quarantine_max_age:
                    reason = f"{root_name}_age_limit"
                elif status == "observed_review" and age > quarantine_max_age:
                    reason = f"stale_{status}"
            else:
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
    snapshot_max_count = max(1, int(cfg.get("snapshot_max_count", 3) or 3))
    snapshot_max_total_bytes = max(0, int(float(cfg.get("snapshot_max_total_gb", 8) or 8) * 1024 * 1024 * 1024))
    retained_snapshot_count = 0
    retained_snapshot_bytes = 0
    stale_snapshot_paths: set[str] = set()
    snapshot_paths = sorted(
        SNAPSHOTS_DIR.glob("snapshot_*.zip"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    ) if SNAPSHOTS_DIR.exists() else []
    for path in snapshot_paths:
        if _is_protected(path, protect_patterns):
            continue
        age_seconds = _age_seconds(path, now)
        if age_seconds > snapshot_max_age:
            stale_snapshot_paths.add(str(path))
            out.append(_build_candidate(path, "stale_snapshot", "delete", "snapshot_age_limit"))
            continue

        size_bytes = _path_size_bytes(path)
        keep_by_count = retained_snapshot_count < snapshot_max_count
        keep_by_size = (retained_snapshot_count == 0) or (retained_snapshot_bytes + size_bytes <= snapshot_max_total_bytes)
        if keep_by_count and keep_by_size:
            retained_snapshot_count += 1
            retained_snapshot_bytes += size_bytes
            continue

        reason = "snapshot_count_limit"
        if not keep_by_size:
            reason = "snapshot_total_size_limit"
        stale_snapshot_paths.add(str(path))
        out.append(_build_candidate(path, "stale_snapshot", "delete", reason))
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

    # Additional bloat sources for 3GB+ runtime: old exports, large action/ops journals, validation artifacts.
    # Never treat release package identity (zips, ledger, validation records) as disposable bloat —
    # deleting them wiped promotion history and forced false "no-builds" / drift traps.
    export_max_age = float(cfg.get("exports_max_age_days", 3) or 3) * 86400.0
    for pdir in [RUNTIME_DIR / "validation" / "exports", RUNTIME_DIR / "exports"]:
        if pdir.exists():
            for path in sorted(pdir.glob("**/*")):
                if path.is_dir() or _is_protected(path, protect_patterns):
                    continue
                path_low = str(path).replace("\\", "/").lower()
                if "/exports/release_packages/" in path_low or path_low.endswith("/release_ledger.jsonl"):
                    continue
                if _age_seconds(path, now) > export_max_age:
                    out.append(_build_candidate(path, "export_bloat", "delete", "export_age_limit"))

    # Storage watch already reports these trees. Kidney is the organ that should
    # actually remove them. Release zips and the ledger stay identity, not bloat.
    extract_max_age = float(cfg.get("release_extract_max_age_days", 3) or 3) * 86400.0
    extract_max_total = int(float(cfg.get("release_validation_extract_max_total_mb", 1024) or 1024) * 1024 * 1024)
    _flag_watched_dir_bloat(
        out,
        root=RUNTIME_DIR / "validation" / "release",
        category="release_extract_bloat",
        age_reason="release_extract_age_limit",
        size_reason="release_extract_total_size_limit",
        max_age_seconds=extract_max_age,
        max_total_bytes=extract_max_total,
        protect_patterns=protect_patterns,
        now=now,
        protect_names=_RELEASE_EXTRACT_PROTECT_NAMES,
    )
    stage_max_age = float(cfg.get("release_stage_max_age_days", cfg.get("release_extract_max_age_days", 3)) or 3) * 86400.0
    stage_max_total = int(float(cfg.get("release_stage_max_total_mb", 256) or 256) * 1024 * 1024)
    _flag_watched_dir_bloat(
        out,
        root=RUNTIME_DIR / "exports" / "release_packages" / "_stage",
        category="release_stage_bloat",
        age_reason="release_stage_age_limit",
        size_reason="release_stage_total_size_limit",
        max_age_seconds=stage_max_age,
        max_total_bytes=stage_max_total,
        protect_patterns=protect_patterns,
        now=now,
    )
    run_max_age = float(cfg.get("subconscious_run_max_age_days", 2) or 2) * 86400.0
    run_keep = max(0, int(cfg.get("subconscious_run_keep_count", 24) or 24))
    run_flag = max(0, int(cfg.get("subconscious_run_max_flag", 400) or 400))
    _flag_watched_dir_bloat(
        out,
        root=RUNTIME_DIR / "subconscious_runs",
        category="subconscious_run_bloat",
        age_reason="subconscious_run_age_limit",
        size_reason="subconscious_run_count_limit",
        max_age_seconds=run_max_age,
        max_total_bytes=0,
        protect_patterns=protect_patterns,
        now=now,
        max_count=run_keep,
        count_reason="subconscious_run_count_limit",
        max_flag=run_flag,
        skip_size=True,
    )
    quarantine_max_age = float(cfg.get("recovery_quarantine_max_age_days", 14) or 14) * 86400.0
    quarantine_keep = max(0, int(cfg.get("recovery_quarantine_keep_count", 1) or 1))
    _flag_watched_dir_bloat(
        out,
        root=RUNTIME_DIR / "recovery_quarantine",
        category="recovery_quarantine_bloat",
        age_reason="recovery_quarantine_age_limit",
        size_reason="recovery_quarantine_count_limit",
        max_age_seconds=quarantine_max_age,
        max_total_bytes=0,
        protect_patterns=protect_patterns,
        now=now,
        max_count=quarantine_keep,
        count_reason="recovery_quarantine_count_limit",
        max_flag=20,
        skip_size=True,
    )

    ledger_max = int(float(cfg.get("ledger_max_mb", 20) or 20) * 1024 * 1024)
    for ledger_name in ("ops_journal.jsonl", "operator_outbox.jsonl", "control_action_audit.jsonl", "tool_events.jsonl"):
        p = RUNTIME_DIR / "validation" / ledger_name
        if not p.exists():
            p = RUNTIME_DIR / ledger_name
        if p.exists() and not _is_protected(p, protect_patterns):
            try:
                if p.stat().st_size > ledger_max:
                    out.append(_build_candidate(p, "ledger_bloat", "delete", "ledger_size_limit"))
            except Exception:
                pass

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


def _skip_cleanup_snapshot(candidates: list[dict[str, Any]], *, cfg: dict[str, Any]) -> str:
    if not candidates:
        return ""
    if all(
        str(item.get("category") or "") == "stale_snapshot"
        and str(item.get("action") or "") == "delete"
        for item in candidates
    ):
        return "stale_snapshot_batch"
    if all(
        str(item.get("category") or "") in _STORAGE_WATCH_DELETE_CATEGORIES
        and str(item.get("action") or "") == "delete"
        for item in candidates
    ):
        return "storage_watch_batch"
    total_bytes = sum(int(item.get("size_bytes", 0) or 0) for item in candidates)
    max_total_bytes = _cleanup_snapshot_max_total_bytes(cfg)
    if max_total_bytes and total_bytes > max_total_bytes:
        return "cleanup_snapshot_total_size_limit"
    return ""


def _cleanup_snapshot_max_total_bytes(cfg: dict[str, Any]) -> int:
    if "cleanup_snapshot_max_total_mb" in cfg:
        return max(0, int(float(cfg.get("cleanup_snapshot_max_total_mb", 128) or 128) * 1024 * 1024))
    if "cleanup_snapshot_max_total_gb" in cfg:
        return max(0, int(float(cfg.get("cleanup_snapshot_max_total_gb", 4) or 4) * 1024 * 1024 * 1024))
    return 128 * 1024 * 1024


def _prune_cleanup_snapshots(*, cfg: dict[str, Any]) -> dict[str, Any]:
    KIDNEY_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    max_age_seconds = max(0.0, float(cfg.get("cleanup_snapshot_max_age_days", 7) or 7) * 86400.0)
    max_count = max(0, int(cfg.get("cleanup_snapshot_max_count", 24) or 24))
    max_total_bytes = _cleanup_snapshot_max_total_bytes(cfg)
    now = _now_ts()
    snapshot_paths = sorted(
        [path for path in KIDNEY_SNAPSHOTS_DIR.iterdir() if path.is_file()],
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    kept: list[Path] = []
    kept_bytes = 0
    removed: list[str] = []
    for path in snapshot_paths:
        try:
            age_seconds = _age_seconds(path, now)
            size_bytes = int(path.stat().st_size or 0)
        except Exception:
            age_seconds = 0.0
            size_bytes = 0
        keep_by_age = max_age_seconds <= 0.0 or age_seconds <= max_age_seconds
        keep_by_count = max_count <= 0 or len(kept) < max_count
        keep_by_size = max_total_bytes <= 0 or (kept_bytes + size_bytes) <= max_total_bytes
        if keep_by_age and keep_by_count and keep_by_size:
            kept.append(path)
            kept_bytes += size_bytes
            continue
        try:
            path.unlink()
            removed.append(str(path))
        except Exception:
            continue
    return {
        "removed_count": len(removed),
        "removed_paths": removed,
        "retained_count": len(kept),
        "retained_total_bytes": kept_bytes,
        "max_count": max_count,
        "max_total_bytes": max_total_bytes,
    }


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
            _record_retired_generated_definition(path, item, target_path=str(target))
            shutil.move(str(path), str(target))
            result["target_path"] = str(target)
            result["result"] = "archived"
            return result
        _record_retired_generated_definition(path, item)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
            if path.name.startswith("snapshot_") and path.suffix == ".zip":
                meta_path = path.with_suffix(path.suffix + ".json")
                if meta_path.exists():
                    meta_path.unlink()
        result["result"] = "deleted"
    except Exception as exc:
        result["result"] = f"error:{exc}"
    return result


def _write_status_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def run_kidney(
    *,
    dry_run: bool = False,
    logger: Callable[[str], None] | None = None,
    write_status: bool | None = None,
) -> dict[str, Any]:
    cfg = policy_kidney()
    mode = str(cfg.get("mode") or "observe").strip().lower() or "observe"
    enabled = bool(cfg.get("enabled", True))
    candidates = scan_candidates()
    should_write_status = (not bool(dry_run)) if write_status is None else bool(write_status)
    summary = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "enabled": enabled,
        "mode": mode,
        "dry_run": bool(dry_run),
        "status_write": "live" if should_write_status else "suppressed",
        "protect_patterns": _load_protect_patterns(),
        "candidate_count": len(candidates),
        "archive_count": sum(1 for item in candidates if str(item.get("action") or "") == "archive"),
        "delete_count": sum(1 for item in candidates if str(item.get("action") or "") == "delete"),
        "candidates": candidates,
        "snapshot_path": "",
        "snapshot_skipped_reason": "",
        "cleanup_snapshot_pruned_count": 0,
        "cleanup_snapshot_retained_count": 0,
        "applied": [],
    }
    if logger is not None:
        logger(f"mode={mode} dry_run={bool(dry_run)} candidates={len(candidates)}")
    if not enabled or dry_run or mode != "enforce":
        if should_write_status:
            _write_status_payload(KIDNEY_STATUS_PATH, summary)
        return summary
    if candidates:
        snapshot_skip_reason = _skip_cleanup_snapshot(candidates, cfg=cfg)
        if snapshot_skip_reason:
            summary["snapshot_skipped_reason"] = snapshot_skip_reason
            if logger is not None:
                logger(f"snapshot_skipped={snapshot_skip_reason}")
        else:
            summary["snapshot_path"] = _snapshot_paths(candidates)
            if logger is not None:
                logger(f"snapshot={summary['snapshot_path']}")
        applied = [_apply_candidate(item) for item in candidates]
        summary["applied"] = applied
        for item in applied:
            if logger is not None:
                logger(f"{item.get('result')} {item.get('category')} {item.get('name')} reason={item.get('reason')}")
    prune_summary = _prune_cleanup_snapshots(cfg=cfg)
    summary["cleanup_snapshot_pruned_count"] = int(prune_summary.get("removed_count", 0) or 0)
    summary["cleanup_snapshot_retained_count"] = int(prune_summary.get("retained_count", 0) or 0)
    if logger is not None and summary["cleanup_snapshot_pruned_count"] > 0:
        logger(
            "cleanup_snapshot_prune "
            f"removed={summary['cleanup_snapshot_pruned_count']} retained={summary['cleanup_snapshot_retained_count']}"
        )
    if should_write_status:
        _write_status_payload(KIDNEY_STATUS_PATH, summary)
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
