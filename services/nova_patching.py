from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable, Optional, Tuple


def log_patch(msg: str, *, updates_dir: Path, snapshots_dir: Path, patch_log: Path) -> None:
    updates_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {msg}\n"
    patch_log.write_text(
        patch_log.read_text(encoding="utf-8") + line if patch_log.exists() else line,
        encoding="utf-8",
    )


def read_patch_revision(patch_revision_file: Path) -> int:
    try:
        if not patch_revision_file.exists():
            return 0
        data = json.loads(patch_revision_file.read_text(encoding="utf-8"))
        return int(data.get("revision", 0) or 0)
    except Exception:
        return 0


def write_patch_revision(revision: int, source: str, *, updates_dir: Path, patch_revision_file: Path) -> None:
    updates_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "revision": int(revision),
        "source": source,
        "ts": time.time(),
    }
    patch_revision_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def snapshot_meta_path(snapshot_zip: Path) -> Path:
    return snapshot_zip.with_suffix(snapshot_zip.suffix + ".json")


def write_snapshot_meta(snapshot_zip: Path, base_revision: int, *, snapshot_meta_path_fn: Callable[[Path], Path]) -> None:
    meta = {
        "snapshot": snapshot_zip.name,
        "base_revision": int(base_revision),
        "ts": time.time(),
    }
    snapshot_meta_path_fn(snapshot_zip).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def read_snapshot_meta(snapshot_zip: Path, *, snapshot_meta_path_fn: Callable[[Path], Path]) -> Optional[dict]:
    path = snapshot_meta_path_fn(snapshot_zip)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def snapshot_current(
    *,
    base_dir: Path,
    snapshots_dir: Path,
    write_snapshot_meta_fn: Callable[[Path, int], None],
    read_patch_revision_fn: Callable[[], int],
    log_patch_fn: Callable[[str], None],
) -> Path:
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    snap = snapshots_dir / f"snapshot_{ts}.zip"
    skip_dirs = {".venv", "runtime", "logs", "models", "updates", "__pycache__", "knowledge"}
    with zipfile.ZipFile(snap, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in base_dir.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(base_dir)
            if rel.parts and rel.parts[0] in skip_dirs:
                continue
            if "__pycache__" in rel.parts:
                continue
            archive.write(path, arcname=str(rel))
    write_snapshot_meta_fn(snap, read_patch_revision_fn())
    log_patch_fn(f"SNAPSHOT {snap.name}")
    return snap


def overlay_zip(zip_path: Path, *, base_dir: Path, patch_manifest_name: str) -> int:
    allowed_ext = {".py", ".json", ".md", ".txt", ".ps1", ".cmd"}
    blocked_prefix = {".git/", ".venv/", "runtime/", "logs/", "models/"}
    count = 0
    with zipfile.ZipFile(zip_path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/").lstrip("/")
            if name == patch_manifest_name:
                continue
            if any(name.startswith(prefix) for prefix in blocked_prefix):
                continue
            if Path(name).suffix.lower() not in allowed_ext:
                continue
            out = base_dir / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(archive.read(info))
            count += 1
    return count


def py_compile_check(*, python_path: str, base_dir: Path) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(
            [python_path, "-m", "compileall", str(base_dir)],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return proc.returncode == 0, output.strip()
    except Exception as exc:
        return False, str(exc)


def last_nonempty_line(text: str) -> str:
    for line in reversed(str(text or "").splitlines()):
        clean = str(line or "").strip()
        if clean:
            return clean
    return ""


def read_patch_manifest(zip_path: Path, *, patch_manifest_name: str) -> tuple[Optional[dict], Optional[str]]:
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            if patch_manifest_name not in archive.namelist():
                return None, None
            raw = archive.read(patch_manifest_name)
    except zipfile.BadZipFile:
        return None, "invalid patch zip."
    except Exception as exc:
        return None, f"failed to read {patch_manifest_name}: {exc}"

    try:
        manifest = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return None, f"{patch_manifest_name} must be UTF-8 JSON."
    except json.JSONDecodeError:
        return None, f"{patch_manifest_name} is not valid JSON."

    if not isinstance(manifest, dict):
        return None, f"{patch_manifest_name} must contain a JSON object."
    return manifest, None


def behavioral_check_command(*, base_dir: Path, python_path: str) -> list[str]:
    runner = base_dir / "run_regression.py"
    if runner.exists():
        return [python_path, str(runner), "behavior"]
    return [python_path, "-m", "unittest", "discover", "-s", "tests", "-f"]


def behavioral_check(
    *,
    base_dir: Path,
    timeout_sec: Optional[int],
    policy_patch_fn: Callable[[], dict],
    behavioral_check_command_fn: Callable[[Path], list[str]],
) -> dict:
    workspace = Path(base_dir)
    tests_dir = workspace / "tests"
    timeout_value = timeout_sec
    if timeout_value is None:
        timeout_value = int(policy_patch_fn().get("behavioral_check_timeout_sec", 600) or 600)
    timeout_value = max(1, int(timeout_value))
    command = behavioral_check_command_fn(workspace)

    if not tests_dir.exists():
        return {
            "ok": True,
            "ran": False,
            "skipped": True,
            "summary": "behavioral check skipped: tests directory not found",
            "output": "",
            "command": list(command),
            "cwd": str(workspace),
            "timeout_sec": timeout_value,
        }

    try:
        proc = subprocess.run(
            command,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout_value,
        )
        output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
        summary = last_nonempty_line(output) or f"exit:{proc.returncode}"
        return {
            "ok": proc.returncode == 0,
            "ran": True,
            "skipped": False,
            "summary": summary,
            "output": output,
            "command": list(command),
            "cwd": str(workspace),
            "timeout_sec": timeout_value,
        }
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") + ("\n" + exc.stderr if exc.stderr else "")).strip()
        return {
            "ok": False,
            "ran": True,
            "skipped": False,
            "summary": f"behavioral check timed out after {timeout_value}s",
            "output": output,
            "command": list(command),
            "cwd": str(workspace),
            "timeout_sec": timeout_value,
        }
    except Exception as exc:
        return {
            "ok": False,
            "ran": False,
            "skipped": False,
            "summary": f"behavioral check failed to start: {exc}",
            "output": str(exc),
            "command": list(command),
            "cwd": str(workspace),
            "timeout_sec": timeout_value,
        }


def read_patch_log_tail_line(*, patch_log: Path) -> str:
    try:
        if not patch_log.exists():
            return ""
        return last_nonempty_line(patch_log.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return ""


def preview_status_from_report(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.lower().startswith("status:"):
                return str(line.split(":", 1)[1] or "").strip()
    except Exception:
        return ""
    return ""


def preview_report_files(*, updates_dir: Path) -> list[Path]:
    previews = updates_dir / "previews"
    if not previews.exists():
        return []
    return sorted(previews.glob("*.txt"), key=lambda path: path.stat().st_mtime, reverse=True)


def preview_archive_dir(*, updates_dir: Path) -> Path:
    return updates_dir / "previews" / "archive"


def resolve_preview_report_path(path_or_name: str, *, updates_dir: Path) -> Path:
    path = Path(path_or_name)
    if not path.is_absolute():
        path = updates_dir / "previews" / path_or_name
    return path


def _preview_report_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _preview_line_value(text: str, prefix: str) -> str:
    for line in str(text or "").splitlines():
        if line.lower().startswith(prefix.lower()):
            return str(line.split(":", 1)[1] or "").strip()
    return ""


def _preview_section_items(text: str, header: str, next_headers: tuple[str, ...]) -> list[str]:
    lines = str(text or "").splitlines()
    capture = False
    out: list[str] = []
    normalized_headers = {str(item or "").strip().lower() for item in next_headers}
    header_text = str(header or "").strip().lower()
    for line in lines:
        stripped = str(line or "").strip()
        lowered = stripped.lower()
        if not capture:
            if lowered == header_text:
                capture = True
            continue
        if not stripped:
            continue
        if lowered in normalized_headers:
            break
        if stripped.startswith("-"):
            item = stripped[1:].strip()
            if item:
                out.append(item)
    return out


def preview_report_summary(path: Path) -> dict:
    text = _preview_report_text(path)
    zip_name = _preview_line_value(text, "Zip:")
    patch_revision = _preview_line_value(text, "Patch revision:")
    min_base_revision = _preview_line_value(text, "Min base revision:")
    status = _preview_line_value(text, "Status:")
    added_files = _preview_section_items(text, "added files:", ("skipped files:", "diff summary:"))
    skipped_files = _preview_section_items(text, "skipped files:", ("diff summary:",))
    zip_lower = str(zip_name or "").strip().lower()
    if zip_lower.startswith("autonomy_micro_patch_"):
        preview_kind = "autonomy_micro_patch"
    elif zip_lower.startswith("teach_proposal_"):
        preview_kind = "teach_proposal"
    else:
        preview_kind = Path(zip_name).stem if zip_name else path.stem
    signature = json.dumps(
        {
            "kind": preview_kind,
            "patch_revision": str(patch_revision or "").strip(),
            "min_base_revision": str(min_base_revision or "").strip(),
            "added_files": sorted(added_files),
            "skipped_files": sorted(skipped_files),
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    return {
        "zip_name": zip_name,
        "patch_revision": patch_revision,
        "min_base_revision": min_base_revision,
        "status": status,
        "added_files": added_files,
        "skipped_files": skipped_files,
        "preview_kind": preview_kind,
        "family_signature": signature,
    }


def compact_preview_review_queue(previews: list[dict], *, limit: int = 40) -> dict:
    ordered = list(previews or [])
    review_rows: list[dict] = []
    seen: dict[tuple[str, str], dict] = {}
    pending_distinct = 0
    pending_superseded = 0
    approved_distinct = 0
    approved_superseded = 0
    orphaned_distinct = 0

    for item in ordered:
        decision = str(item.get("decision") or "pending").strip().lower() or "pending"
        status = str(item.get("status") or "").strip().lower()
        if decision == "rejected":
            continue
        if not status.startswith("eligible"):
            continue
        family_signature = str(item.get("family_signature") or "").strip()
        family_key = (decision, family_signature or str(item.get("name") or ""))
        existing = seen.get(family_key)
        if existing is None:
            row = dict(item)
            row["collapsed_count"] = 0
            row["review_bucket"] = decision
            seen[family_key] = row
            review_rows.append(row)
            if str(row.get("artifact_state") or "").strip().lower() == "orphaned":
                orphaned_distinct += 1
            if decision == "approved":
                approved_distinct += 1
            else:
                pending_distinct += 1
        else:
            existing["collapsed_count"] = int(existing.get("collapsed_count", 0) or 0) + 1
            if decision == "approved":
                approved_superseded += 1
            else:
                pending_superseded += 1

    return {
        "review_previews": review_rows[: max(0, int(limit or 0))],
        "review_previews_total": len(review_rows),
        "pending_distinct": pending_distinct,
        "pending_superseded": pending_superseded,
        "approved_distinct": approved_distinct,
        "approved_superseded": approved_superseded,
        "orphaned_distinct": orphaned_distinct,
    }


def patch_preview_summaries(*, updates_dir: Path, read_approvals_fn: Callable[[], list[dict]], limit: int = 40) -> list[dict]:
    try:
        files = preview_report_files(updates_dir=updates_dir)
        approval_map: dict[str, dict] = {}
        for item in read_approvals_fn():
            if not isinstance(item, dict):
                continue
            preview = str(item.get("preview") or "").strip()
            if preview:
                approval_map[preview] = item
                approval_map[Path(preview).name] = item
        summaries = []
        for preview in files[: max(0, int(limit or 0))]:
            approval = approval_map.get(str(preview)) or approval_map.get(preview.name) or {}
            report = preview_report_summary(preview)
            zip_name = str(report.get("zip_name") or "").strip()
            zip_path = updates_dir / zip_name if zip_name else None
            zip_exists = bool(zip_path and zip_path.exists())
            artifact_state = "ok"
            artifact_reason = ""
            if not zip_name:
                artifact_state = "orphaned"
                artifact_reason = "Preview report does not contain a resolvable patch zip."
            elif not zip_exists:
                artifact_state = "orphaned"
                artifact_reason = f"Preview references a missing patch zip: {zip_name}"
            summaries.append(
                {
                    "name": preview.name,
                    "path": str(preview),
                    "status": str(report.get("status") or preview_status_from_report(preview)),
                    "decision": str(approval.get("decision") or "pending"),
                    "mtime": int(preview.stat().st_mtime),
                    "zip_name": zip_name,
                    "zip_exists": zip_exists,
                    "zip_path": str(zip_path) if zip_path else "",
                    "artifact_state": artifact_state,
                    "artifact_reason": artifact_reason,
                    "patch_revision": str(report.get("patch_revision") or ""),
                    "min_base_revision": str(report.get("min_base_revision") or ""),
                    "added_files": list(report.get("added_files") or []),
                    "skipped_files": list(report.get("skipped_files") or []),
                    "preview_kind": str(report.get("preview_kind") or ""),
                    "family_signature": str(report.get("family_signature") or ""),
                }
            )
        return summaries
    except Exception:
        return []


def patch_status_payload(
    *,
    base_dir: Path,
    updates_dir: Path,
    read_approvals_fn: Callable[[], list[dict]],
    read_patch_revision_fn: Callable[[], int],
    read_patch_log_tail_line_fn: Callable[[], str],
    policy_patch_fn: Callable[[], dict],
    patch_preview_summaries_fn: Callable[[int], list[dict]],
) -> dict:
    try:
        cfg = policy_patch_fn()
        files = preview_report_files(updates_dir=updates_dir)
        approval_map: dict[str, dict] = {}
        for item in read_approvals_fn():
            if not isinstance(item, dict):
                continue
            preview = str(item.get("preview") or "").strip()
            if preview:
                approval_map[preview] = item
                approval_map[Path(preview).name] = item

        previews_pending = 0
        previews_approved = 0
        previews_rejected = 0
        previews_eligible = 0
        previews_approved_eligible = 0
        previews_orphaned = 0
        last_preview_name = ""
        last_preview_status = ""
        last_preview_decision = ""

        if files:
            last_preview_name = files[0].name
            last_preview_status = preview_status_from_report(files[0])
            last_preview_decision = str((approval_map.get(str(files[0])) or approval_map.get(files[0].name) or {}).get("decision") or "pending")

        for preview in files:
            decision = str((approval_map.get(str(preview)) or approval_map.get(preview.name) or {}).get("decision") or "pending").strip().lower()
            status_text = preview_status_from_report(preview)
            report = preview_report_summary(preview)
            zip_name = str(report.get("zip_name") or "").strip()
            zip_exists = bool(zip_name) and (updates_dir / zip_name).exists()
            if not zip_name or not zip_exists:
                previews_orphaned += 1
            if status_text.lower().startswith("eligible"):
                previews_eligible += 1
            if decision == "approved":
                previews_approved += 1
                if status_text.lower().startswith("eligible"):
                    previews_approved_eligible += 1
            elif decision == "rejected":
                previews_rejected += 1
            else:
                previews_pending += 1

        tests_available = (base_dir / "tests").exists()
        behavioral_check_enabled = bool(cfg.get("behavioral_check", True))
        pipeline_ready = bool(cfg.get("enabled", True)) and bool(cfg.get("strict_manifest", True)) and behavioral_check_enabled and bool(tests_available)
        compact = compact_preview_review_queue(patch_preview_summaries_fn(max(200, len(files))), limit=40)

        return {
            "ok": True,
            "enabled": bool(cfg.get("enabled", True)),
            "strict_manifest": bool(cfg.get("strict_manifest", True)),
            "allow_force": bool(cfg.get("allow_force", False)),
            "behavioral_check": behavioral_check_enabled,
            "behavioral_check_timeout_sec": int(cfg.get("behavioral_check_timeout_sec", 600) or 600),
            "tests_available": bool(tests_available),
            "pipeline_ready": pipeline_ready,
            "current_revision": read_patch_revision_fn(),
            "previews_total": len(files),
            "previews_pending": previews_pending,
            "previews_approved": previews_approved,
            "previews_rejected": previews_rejected,
            "previews_eligible": previews_eligible,
            "previews_approved_eligible": previews_approved_eligible,
            "previews_orphaned": previews_orphaned,
            "last_preview_name": last_preview_name,
            "last_preview_status": last_preview_status,
            "last_preview_decision": last_preview_decision,
            "last_patch_log_line": read_patch_log_tail_line_fn(),
            "previews": patch_preview_summaries_fn(40),
            "review_previews": list(compact.get("review_previews") or []),
            "review_previews_total": int(compact.get("review_previews_total", 0) or 0),
            "review_previews_pending_distinct": int(compact.get("pending_distinct", 0) or 0),
            "review_previews_pending_superseded": int(compact.get("pending_superseded", 0) or 0),
            "review_previews_approved_distinct": int(compact.get("approved_distinct", 0) or 0),
            "review_previews_approved_superseded": int(compact.get("approved_superseded", 0) or 0),
            "review_previews_orphaned": int(compact.get("orphaned_distinct", 0) or 0),
            "review_previews_superseded_total": int((compact.get("pending_superseded", 0) or 0) + (compact.get("approved_superseded", 0) or 0)),
            "ready_for_validated_apply": pipeline_ready and previews_approved_eligible > 0,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def archive_preview_report(path_or_name: str, *, updates_dir: Path) -> dict:
    path = resolve_preview_report_path(path_or_name, updates_dir=updates_dir)
    if not path.exists():
        return {"ok": False, "error": f"Preview not found: {path}", "source": str(path)}
    archive_dir = preview_archive_dir(updates_dir=updates_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / path.name
    if target.exists():
        target = archive_dir / f"{path.stem}_{time.strftime('%Y%m%d_%H%M%S')}{path.suffix}"
    path.replace(target)
    return {"ok": True, "source": str(path), "archived": str(target), "name": target.name}


def bulk_reject_orphaned_previews(
    *,
    updates_dir: Path,
    read_approvals_fn: Callable[[], list[dict]],
    record_approval_fn: Callable[..., bool],
    get_active_user_fn: Callable[[], Optional[str]],
    note: str = "",
) -> dict:
    previews = patch_preview_summaries(updates_dir=updates_dir, read_approvals_fn=read_approvals_fn, limit=max(5000, len(preview_report_files(updates_dir=updates_dir))))
    targets = [
        item for item in previews
        if str(item.get("artifact_state") or "").strip().lower() == "orphaned"
        and str(item.get("decision") or "pending").strip().lower() != "rejected"
    ]
    rejected: list[str] = []
    failed: list[str] = []
    reason = str(note or "").strip() or "bulk orphan rejection: preview references a missing patch artifact"
    for item in targets:
        preview_path = str(item.get("path") or item.get("name") or "").strip()
        if not preview_path:
            continue
        ok = record_approval_fn(preview_path, "rejected", user=get_active_user_fn(), note=reason)
        if ok:
            rejected.append(str(item.get("name") or preview_path))
        else:
            failed.append(str(item.get("name") or preview_path))
    return {
        "ok": not failed,
        "count": len(rejected),
        "rejected": rejected,
        "failed": failed,
        "skipped": max(0, len(previews) - len(targets)),
    }


def bulk_archive_superseded_previews(*, updates_dir: Path, read_approvals_fn: Callable[[], list[dict]]) -> dict:
    previews = patch_preview_summaries(updates_dir=updates_dir, read_approvals_fn=read_approvals_fn, limit=max(5000, len(preview_report_files(updates_dir=updates_dir))))
    seen: set[tuple[str, str]] = set()
    archived: list[str] = []
    failed: list[str] = []
    for item in previews:
        decision = str(item.get("decision") or "pending").strip().lower() or "pending"
        status = str(item.get("status") or "").strip().lower()
        if decision == "rejected" or not status.startswith("eligible"):
            continue
        family_signature = str(item.get("family_signature") or "").strip()
        family_key = (decision, family_signature or str(item.get("name") or ""))
        if family_key not in seen:
            seen.add(family_key)
            continue
        result = archive_preview_report(str(item.get("path") or item.get("name") or ""), updates_dir=updates_dir)
        if result.get("ok"):
            archived.append(str(item.get("name") or ""))
        else:
            failed.append(str(item.get("name") or ""))
    return {
        "ok": not failed,
        "count": len(archived),
        "archived": archived,
        "failed": failed,
        "archive_dir": str(preview_archive_dir(updates_dir=updates_dir)),
    }


def patch_reject_message(
    reason: str,
    *,
    strict_manifest: bool,
    current_revision: int,
    incoming_revision: Optional[int],
    required_base_revision: Optional[int],
) -> str:
    incoming_text = str(incoming_revision) if incoming_revision is not None else "missing"
    required_base_text = str(required_base_revision) if required_base_revision is not None else "not specified"
    strict_text = "on" if strict_manifest else "off"
    return (
        f"Patch rejected: {reason}\n"
        f"- incoming revision: {incoming_text}\n"
        f"- current revision: {current_revision}\n"
        f"- required base: {required_base_text}\n"
        f"- current base: {current_revision}\n"
        f"- strict mode: {strict_text}"
    )


def patch_apply(
    zip_path: str,
    *,
    force: bool = False,
    safe_path_fn: Callable[[str], Path],
    policy_patch_fn: Callable[[], dict],
    read_patch_revision_fn: Callable[[], int],
    read_patch_manifest_fn: Callable[[Path], tuple[Optional[dict], Optional[str]]],
    log_patch_fn: Callable[[str], None],
    patch_reject_message_fn: Callable[..., str],
    read_approvals_fn: Callable[[], list[dict]],
    patch_preview_fn: Callable[[str, bool], str],
    snapshot_current_fn: Callable[[], Path],
    overlay_zip_fn: Callable[[Path], int],
    py_compile_check_fn: Callable[[], Tuple[bool, str]],
    patch_rollback_fn: Callable[[Optional[str]], str],
    behavioral_check_fn: Callable[..., dict],
    write_patch_revision_fn: Callable[[int, str], None],
    patch_manifest_name: str,
) -> str:
    zip_file = safe_path_fn(zip_path) if not Path(zip_path).is_absolute() else Path(zip_path)
    if not zip_file.exists() or not zip_file.is_file():
        return f"Not a file: {zip_file}"

    try:
        preview_out = patch_preview_fn(str(zip_file), True)
        if not force and "Status: eligible" not in preview_out:
            strict_manifest = bool(policy_patch_fn().get("strict_manifest", True))
            current_revision = read_patch_revision_fn()
            manifest, manifest_err = read_patch_manifest_fn(zip_file)
            if manifest_err:
                log_patch_fn(f"APPLY_REJECT invalid_manifest {zip_file.name} err={manifest_err}")
                return patch_reject_message_fn(
                    manifest_err,
                    strict_manifest=strict_manifest,
                    current_revision=current_revision,
                    incoming_revision=None,
                    required_base_revision=None,
                )

            try:
                incoming_rev = int(manifest.get("patch_revision", 0) or 0)
            except Exception:
                incoming_rev = None
            try:
                min_base = int(manifest.get("min_base_revision", 0) or 0)
            except Exception:
                min_base = None

            if incoming_rev is not None and incoming_rev <= current_revision:
                log_patch_fn(f"APPLY_REJECT downgrade current={current_revision} next={incoming_rev} zip={zip_file.name}")
                return patch_reject_message_fn(
                    "non-forward revision (downgrade blocked).",
                    strict_manifest=strict_manifest,
                    current_revision=current_revision,
                    incoming_revision=incoming_rev,
                    required_base_revision=min_base,
                )

            if min_base is not None and current_revision < min_base:
                log_patch_fn(f"APPLY_REJECT base_too_old current={current_revision} min_base={min_base} zip={zip_file.name}")
                return patch_reject_message_fn(
                    "incompatible base state.",
                    strict_manifest=strict_manifest,
                    current_revision=current_revision,
                    incoming_revision=incoming_rev,
                    required_base_revision=min_base,
                )

            match = re.search(r"Preview written:\s*(.+)$", preview_out, flags=re.M)
            if match:
                preview_path = match.group(1).strip()
                approved = False
                for approval in read_approvals_fn():
                    if str(preview_path) == str(approval.get("preview")) and approval.get("decision") == "approved":
                        approved = True
                        break
                if not approved:
                    return (
                        f"Patch rejected: preview check failed. A preview was generated at {preview_path} and requires local approval before applying.\n\nPreview output:\n{preview_out}\n\n"
                        "Approve with: patch approve <preview_filename>\nOr re-run with --force to override."
                    )

            return (
                f"Patch rejected: preview check failed.\n\nPreview output:\n{preview_out}\n\n"
                "If you really want to apply anyway, re-run with: patch apply <zip_path> --force"
            )
    except Exception:
        if not force:
            return "Patch preview failed; aborting apply. Use --force to override."

    strict_manifest = bool(policy_patch_fn().get("strict_manifest", True))
    current_revision = read_patch_revision_fn()
    manifest, manifest_err = read_patch_manifest_fn(zip_file)
    if manifest_err:
        log_patch_fn(f"APPLY_REJECT invalid_manifest {zip_file.name} err={manifest_err}")
        return patch_reject_message_fn(
            manifest_err,
            strict_manifest=strict_manifest,
            current_revision=current_revision,
            incoming_revision=None,
            required_base_revision=None,
        )

    next_revision = None
    if manifest is None:
        if strict_manifest:
            log_patch_fn(f"APPLY_REJECT missing_manifest {zip_file.name}")
            return patch_reject_message_fn(
                f"missing {patch_manifest_name}. Include patch_revision > current revision.",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=None,
                required_base_revision=None,
            )
    else:
        try:
            next_revision = int(manifest.get("patch_revision", 0) or 0)
        except Exception:
            log_patch_fn(f"APPLY_REJECT bad_revision {zip_file.name}")
            return patch_reject_message_fn(
                "manifest field 'patch_revision' must be an integer.",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=None,
                required_base_revision=None,
            )

        try:
            min_base = int(manifest.get("min_base_revision", 0) or 0)
        except Exception:
            log_patch_fn(f"APPLY_REJECT bad_min_base {zip_file.name}")
            return patch_reject_message_fn(
                "manifest field 'min_base_revision' must be an integer when provided.",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=next_revision,
                required_base_revision=None,
            )

        if next_revision <= current_revision:
            log_patch_fn(f"APPLY_REJECT downgrade current={current_revision} next={next_revision} zip={zip_file.name}")
            return patch_reject_message_fn(
                "non-forward revision (downgrade blocked).",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=next_revision,
                required_base_revision=min_base,
            )
        if current_revision < min_base:
            log_patch_fn(f"APPLY_REJECT base_too_old current={current_revision} min_base={min_base} zip={zip_file.name}")
            return patch_reject_message_fn(
                "incompatible base state.",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=next_revision,
                required_base_revision=min_base,
            )

    snap = snapshot_current_fn()
    log_patch_fn(f"APPLY {zip_file.name} current_rev={current_revision} next_rev={next_revision if next_revision is not None else 'unversioned'}")

    count = overlay_zip_fn(zip_file)
    if count == 0:
        log_patch_fn("APPLY no files overlayed")
        return "Patch zip contained no eligible files to apply."

    ok_compile, compile_output = py_compile_check_fn()
    if not ok_compile:
        log_patch_fn("COMPILE_FAIL -> rollback")
        patch_rollback_fn(str(snap))
        return "Patch applied, but compile check failed. Rolled back.\n\nCompile output:\n" + compile_output[-3500:]

    patch_cfg = policy_patch_fn()
    behavioral_enabled = bool(patch_cfg.get("behavioral_check", True))
    behavior_result = {
        "ok": True,
        "ran": False,
        "skipped": True,
        "summary": "behavioral check disabled by policy",
        "output": "",
    }
    if behavioral_enabled:
        behavior_result = behavioral_check_fn(timeout_sec=int(patch_cfg.get("behavioral_check_timeout_sec", 600) or 600))
        if not bool(behavior_result.get("ok")):
            summary = str(behavior_result.get("summary") or "behavioral check failed")
            log_patch_fn(f"BEHAVIOR_FAIL {summary} -> rollback")
            patch_rollback_fn(str(snap))
            output = str(behavior_result.get("output") or "").strip()
            msg = "Patch applied, but behavioral check failed. Rolled back.\n\nBehavioral summary:\n" + summary
            if output:
                msg += "\n\nBehavioral output:\n" + output[-3500:]
            return msg
        if bool(behavior_result.get("skipped")):
            log_patch_fn(f"BEHAVIOR_SKIP {str(behavior_result.get('summary') or '').strip()}")
        else:
            log_patch_fn(f"BEHAVIOR_OK {str(behavior_result.get('summary') or '').strip()}")
    else:
        log_patch_fn("BEHAVIOR_SKIP disabled_by_policy")

    if next_revision is not None:
        write_patch_revision_fn(next_revision, zip_file.name)

    log_patch_fn(f"APPLY_OK files={count}")
    rev_msg = f" Revision: {next_revision}." if next_revision is not None else ""
    behavior_msg = (
        f" Behavioral check OK ({str(behavior_result.get('summary') or 'passed')})."
        if behavioral_enabled
        else " Behavioral check skipped by policy."
    )
    return f"Patch applied: {count} file(s). Compile check OK.{behavior_msg} Snapshot: {snap.name}.{rev_msg}"


def patch_rollback(
    snapshot_zip: Optional[str] = None,
    *,
    base_dir: Path,
    snapshots_dir: Path,
    log_patch_fn: Callable[[str], None],
    read_snapshot_meta_fn: Callable[[Path], Optional[dict]],
    write_patch_revision_fn: Callable[[int, str], None],
    py_compile_check_fn: Callable[[], Tuple[bool, str]],
) -> str:
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    snaps = sorted(snapshots_dir.glob("snapshot_*.zip"), key=lambda path: path.name, reverse=True)
    if snapshot_zip:
        snap = Path(snapshot_zip)
        if not snap.is_absolute():
            snap = snapshots_dir / snapshot_zip
    else:
        snap = snaps[0] if snaps else None

    if not snap or not snap.exists():
        return "No snapshot found to rollback."

    log_patch_fn(f"ROLLBACK {snap.name}")
    with zipfile.ZipFile(snap, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            out = base_dir / info.filename
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(archive.read(info))

    meta = read_snapshot_meta_fn(snap)
    if meta and "revision" in meta:
        try:
            write_patch_revision_fn(int(meta.get("revision", 0) or 0), f"rollback:{snap.name}")
        except Exception:
            pass

    ok_compile, compile_output = py_compile_check_fn()
    if not ok_compile:
        return "Rollback completed, but compile check still failing.\n\nCompile output:\n" + compile_output[-3500:]
    return f"Rollback completed from snapshot: {snap.name}"


def patch_preview(
    zip_path: str,
    *,
    write_report: bool = False,
    safe_path_fn: Callable[[str], Path],
    base_dir: Path,
    updates_dir: Path,
    read_patch_manifest_fn: Callable[[Path], tuple[Optional[dict], Optional[str]]],
    read_patch_revision_fn: Callable[[], int],
) -> str:
    zip_file = safe_path_fn(zip_path) if not Path(zip_path).is_absolute() else Path(zip_path)
    if not zip_file.exists() or not zip_file.is_file():
        return f"Not found: {zip_file}"

    manifest, manifest_err = read_patch_manifest_fn(zip_file)
    if manifest_err:
        manifest = None

    current_revision = read_patch_revision_fn()
    patch_rev = None
    min_base = None
    try:
        if manifest:
            patch_rev = int(manifest.get("patch_revision", 0) or 0)
            min_base = int(manifest.get("min_base_revision", 0) or 0)
    except Exception:
        pass

    skip_prefixes = (".git/", "runtime/", "logs/", "updates/", "piper/", "models/", "pkgconfig/")
    text_ext = {".py", ".md", ".txt", ".json", ".rst", ".yaml", ".yml", ".ini", ".cfg", ".html", ".css", ".js", ".csv"}

    added: list[str] = []
    changed: list[str] = []
    skipped: list[str] = []
    diffs: dict[str, str] = {}

    with tempfile.TemporaryDirectory() as tmp_dir:
        with zipfile.ZipFile(zip_file, "r") as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            for member in members:
                filename = member.filename.replace("\\", "/")
                if any(filename.startswith(prefix) for prefix in skip_prefixes):
                    skipped.append(filename)
                    continue

                target = base_dir / filename
                try:
                    archive.extract(member, path=tmp_dir)
                except Exception:
                    skipped.append(filename)
                    continue

                src = Path(tmp_dir) / filename
                if not src.exists():
                    skipped.append(filename)
                    continue

                if target.exists():
                    try:
                        if src.suffix.lower() in text_ext:
                            old = target.read_text(encoding="utf-8", errors="ignore").splitlines()
                            new = src.read_text(encoding="utf-8", errors="ignore").splitlines()
                            if old != new:
                                changed.append(filename)
                                diff = difflib.unified_diff(old, new, fromfile=str(target), tofile=str(zip_file.name + ":" + filename), lineterm="")
                                diffs[filename] = "\n".join(list(diff)[:400])
                        elif target.read_bytes() != src.read_bytes():
                            changed.append(filename)
                    except Exception:
                        changed.append(filename)
                else:
                    added.append(filename)

    status = "eligible"
    if patch_rev is not None:
        if patch_rev <= current_revision:
            status = "rejected: non-forward revision"
        elif min_base is not None and current_revision < min_base:
            status = "rejected: incompatible base revision"

    lines = [
        "Patch Preview",
        "-------------",
        f"Zip: {zip_file.name}",
        f"Patch revision: {patch_rev if patch_rev is not None else 'unknown'}",
        f"Min base revision: {min_base if min_base is not None else 'not specified'}",
        f"Current revision: {current_revision}",
        f"Status: {status}",
        "",
    ]

    if changed:
        lines.append("Changed files:")
        for item in changed:
            lines.append(f"- {item}")
        lines.append("")

    if added:
        lines.append("Added files:")
        for item in added:
            lines.append(f"- {item}")
        lines.append("")

    if skipped:
        lines.append("Skipped files:")
        for item in skipped[:50]:
            lines.append(f"- {item}")
        if len(skipped) > 50:
            lines.append(f"- ... and {len(skipped) - 50} more")
        lines.append("")

    lines.append("Diff summary:")
    if diffs:
        for filename, diff in diffs.items():
            lines.append(f"- {filename}: modified")
            lines.append("```")
            lines.append(diff)
            lines.append("```")
    else:
        lines.append("- No text diffs available or all changes are binary/non-text")

    out = "\n".join(lines)
    if write_report:
        try:
            previews = updates_dir / "previews"
            previews.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            report = previews / f"preview_{ts}_{zip_file.name}.txt"
            report.write_text(out, encoding="utf-8")
            out = out + f"\n\nPreview written: {report}"
        except Exception:
            pass
    return out


def approvals_file(*, updates_dir: Path) -> Path:
    path = updates_dir / "approvals.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_approvals(*, approvals_file_fn: Callable[[], Path]) -> list[dict]:
    path = approvals_file_fn()
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return out


def record_approval(
    preview_path: str,
    decision: str,
    *,
    user: Optional[str] = None,
    note: str = "",
    approvals_file_fn: Callable[[], Path],
    get_active_user_fn: Callable[[], Optional[str]],
) -> bool:
    rec = {
        "ts": int(time.time()),
        "preview": str(preview_path),
        "decision": decision,
        "user": user or (get_active_user_fn() or "unknown"),
        "note": note,
    }
    try:
        with open(approvals_file_fn(), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def list_previews(*, updates_dir: Path, read_approvals_fn: Callable[[], list[dict]]) -> str:
    previews = updates_dir / "previews"
    if not previews.exists():
        return "No previews found."
    files = sorted(previews.glob("*.txt"), key=lambda path: path.stat().st_mtime, reverse=True)
    mapping = {item.get("preview"): item for item in read_approvals_fn()}
    lines: list[str] = []
    for path in files:
        status = "pending"
        approval = mapping.get(str(path)) or mapping.get(path.name)
        if approval:
            status = approval.get("decision", "pending")
        lines.append(f"- {path.name}  [{status}]")
    return "\n".join(lines)


def show_preview(path_or_name: str, *, updates_dir: Path) -> str:
    previews = updates_dir / "previews"
    path = Path(path_or_name)
    if not path.is_absolute():
        path = previews / path_or_name
    if not path.exists():
        return f"Preview not found: {path}"
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        return f"Failed to read preview: {exc}"


def approve_preview(
    path_or_name: str,
    *,
    note: str = "",
    updates_dir: Path,
    record_approval_fn: Callable[..., bool],
    get_active_user_fn: Callable[[], Optional[str]],
) -> str:
    previews = updates_dir / "previews"
    path = Path(path_or_name)
    if not path.is_absolute():
        path = previews / path_or_name
    if not path.exists():
        return f"Preview not found: {path}"
    ok = record_approval_fn(str(path), "approved", user=get_active_user_fn(), note=note)
    return "Approved." if ok else "Failed to record approval."


def reject_preview(
    path_or_name: str,
    *,
    note: str = "",
    updates_dir: Path,
    record_approval_fn: Callable[..., bool],
    get_active_user_fn: Callable[[], Optional[str]],
) -> str:
    previews = updates_dir / "previews"
    path = Path(path_or_name)
    if not path.is_absolute():
        path = previews / path_or_name
    if not path.exists():
        return f"Preview not found: {path}"
    ok = record_approval_fn(str(path), "rejected", user=get_active_user_fn(), note=note)
    return "Rejected." if ok else "Failed to record rejection."


def interactive_preview_review(
    preview_path: str,
    *,
    record_approval_fn: Callable[..., bool],
    get_active_user_fn: Callable[[], Optional[str]],
) -> str:
    try:
        path = Path(preview_path)
        if not path.exists():
            return f"Preview not found: {path}"
        text = path.read_text(encoding="utf-8")
        summary = "\n".join(text.splitlines()[:40])
        print("\nProposal review:\n", flush=True)
        print(f"Name: {path.name}")
        match = re.search(r"Patch revision:\s*(.+)$", text, flags=re.M)
        if match:
            print(f"Revision: {match.group(1).strip()}")
        print("Files / diff preview (first lines):")
        print(summary)

        while True:
            try:
                response = input("\nDecision? (approve/reject/view/cancel): ").strip().lower()
            except EOFError:
                return "No interactive input; review aborted."
            if response in {"approve", "a"}:
                ok = record_approval_fn(str(path), "approved", user=get_active_user_fn())
                return "Approved." if ok else "Failed to record approval."
            if response in {"reject", "r"}:
                ok = record_approval_fn(str(path), "rejected", user=get_active_user_fn())
                return "Rejected." if ok else "Failed to record rejection."
            if response in {"view", "v"}:
                print("\n---- Full preview ----\n")
                print(text)
                print("\n---- End preview ----\n")
                continue
            if response in {"cancel", "c", "quit", "q"}:
                return "Review canceled."
            print("Unknown response. Enter 'approve', 'reject', 'view', or 'cancel'.")
    except Exception as exc:
        return f"Interactive review failed: {exc}"


def interactive_patch_review_enabled() -> bool:
    raw = str(os.environ.get("NOVA_INTERACTIVE_PATCH_REVIEW") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}