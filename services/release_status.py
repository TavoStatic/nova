from __future__ import annotations

import hashlib
import json
import os
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path

from services.release_promotion_judgment import release_validation_record_payload
from services.release_runtime_truth import enrich_release_status


_SOURCE_EXCLUDED_DIRS = {
    ".git",
    ".github",
    ".ci_venv",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "agent-tools",
    "logs",
    "memory",
    "runtime",
    "terminals",
    "updates",
    # Local operator/tooling trees — not package identity
    "mcps",
    ".vscode",
}

_SOURCE_EXCLUDED_PREFIXES = {
    "knowledge/packs",
    "knowledge/peims",
    "knowledge/web",
}

_SOURCE_EXCLUDED_FILES = {
    "LAST_SESSION.json",
    "RESUME_HERE.txt",
    "This_is_nova",
    "tests_to_review.txt",
    "full_suite_out.txt",
    "runtime_full_suite_out.txt",
    "discovery_results_phase_i.txt",
    "nova_memory.sqlite",
    "nova_grok.md",
    "codex_audit.txt",
    "start_nova.cmd",
}


def _entry_artifact_kind(entry: dict) -> str:
    kind = str((entry or {}).get("artifact_kind") or "").strip()
    return kind or "package-zip"


def _parse_recorded_at_epoch(value: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    text = re.sub(r"(\.\d{6})\d+([+-]\d\d:\d\d)$", r"\1\2", text)
    try:
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


def _source_rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except Exception:
        return path.as_posix()


def _is_source_candidate(path: Path, root: Path) -> bool:
    rel = _source_rel(path, root)
    if not rel or rel.startswith("../"):
        return False
    parts = rel.split("/")
    if any(part in _SOURCE_EXCLUDED_DIRS for part in parts[:-1]):
        return False
    if any(rel == prefix or rel.startswith(prefix + "/") for prefix in _SOURCE_EXCLUDED_PREFIXES):
        return False
    if parts[-1] in _SOURCE_EXCLUDED_FILES:
        return False
    if path.suffix.lower() in {".pyc", ".pyo", ".log", ".db", ".sqlite", ".jsonl"}:
        return False
    return path.is_file()


def _is_excluded_source_dir(path: Path, root: Path) -> bool:
    rel = _source_rel(path, root)
    if not rel or rel == ".":
        return False
    parts = rel.split("/")
    if any(part in _SOURCE_EXCLUDED_DIRS for part in parts):
        return True
    return any(rel == prefix or rel.startswith(prefix + "/") for prefix in _SOURCE_EXCLUDED_PREFIXES)


def _iter_source_candidates(root: Path):
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        dirs[:] = [
            name for name in dirs
            if not _is_excluded_source_dir(current_path / name, root)
        ]
        for name in files:
            path = current_path / name
            if _is_source_candidate(path, root):
                yield path


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _zip_relative_name(name: str) -> str:
    normalized = str(name or "").replace("\\", "/").strip("/")
    if not normalized:
        return ""
    parts = normalized.split("/")
    if len(parts) > 1:
        return "/".join(parts[1:])
    return normalized


def _artifact_hashes_for_paths(artifact_path: Path, relative_paths: set[str]) -> dict[str, str]:
    if not relative_paths or not artifact_path.exists() or not artifact_path.is_file():
        return {}
    out: dict[str, str] = {}
    try:
        with zipfile.ZipFile(artifact_path) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                rel = _zip_relative_name(entry.filename)
                if rel not in relative_paths:
                    continue
                hasher = hashlib.sha256()
                with archive.open(entry) as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        hasher.update(chunk)
                out[rel] = hasher.hexdigest()
    except Exception:
        return {}
    return out


class ReleaseStatusService:
    """Own release ledger parsing and latest release readiness summaries."""

    @staticmethod
    def ledger_entries(ledger_path: Path, limit: int = 20) -> list[dict]:
        try:
            if not Path(ledger_path).exists():
                return []
            entries: list[dict] = []
            lines = Path(ledger_path).read_text(encoding="utf-8", errors="ignore").splitlines()
            for line in lines:
                text = str(line or "").strip()
                if not text:
                    continue
                try:
                    data = json.loads(text)
                except Exception:
                    continue
                if isinstance(data, dict):
                    entries.append(data)
            entries.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
            return entries[: max(1, int(limit))]
        except Exception:
            return []

    @staticmethod
    def entry_matches_build(entry: dict, build_entry: dict) -> bool:
        if not isinstance(entry, dict) or not isinstance(build_entry, dict):
            return False
        entry_artifact_path = str(entry.get("artifact_path") or "").strip()
        build_artifact_path = str(build_entry.get("artifact_path") or "").strip()
        if entry_artifact_path and entry_artifact_path == build_artifact_path:
            return True
        entry_version = str(entry.get("artifact_version") or "").strip()
        build_version = str(build_entry.get("artifact_version") or "").strip()
        entry_channel = str(entry.get("release_channel") or "").strip()
        build_channel = str(build_entry.get("release_channel") or "").strip()
        entry_label = str(entry.get("release_label") or "").strip()
        build_label = str(build_entry.get("release_label") or "").strip()
        return bool(entry_version and entry_version == build_version and entry_channel == build_channel and entry_label == build_label)

    def source_freshness_payload(
        self,
        source_root: Path,
        build_recorded_at: str,
        *,
        artifact_path: Path | None = None,
    ) -> dict:
        root = Path(source_root)
        build_epoch = _parse_recorded_at_epoch(build_recorded_at)
        out = {
            "latest_source_status": "unknown",
            "latest_artifact_stale": False,
            "latest_source_changed_after_build": False,
            "latest_source_changed_after_build_count": 0,
            "latest_source_newest_path": "",
            "latest_source_newest_mtime": "",
            "latest_source_changed_after_build_sample": [],
            "latest_source_touched_after_build_count": 0,
            "latest_source_content_unchanged_after_build_count": 0,
            "latest_source_freshness_basis": "mtime",
        }
        if build_epoch is None or not root.exists():
            return out

        newest_path = ""
        newest_mtime = 0.0
        changed: list[tuple[float, str]] = []
        now_epoch = time.time()
        try:
            for path in _iter_source_candidates(root):
                try:
                    mtime = float(path.stat().st_mtime)
                except OSError:
                    continue
                if mtime > now_epoch + 60.0:
                    try:
                        os.utime(path, (now_epoch, now_epoch))
                    except OSError:
                        pass
                    mtime = now_epoch
                rel = _source_rel(path, root)
                if mtime > newest_mtime:
                    newest_mtime = mtime
                    newest_path = rel
                if mtime > build_epoch:
                    changed.append((mtime, rel))
        except Exception:
            return out

        changed.sort(key=lambda item: item[0], reverse=True)
        content_changed = list(changed)
        content_unchanged_count = 0
        artifact = Path(artifact_path) if artifact_path else None
        if artifact and artifact.exists():
            rels = {rel for _mtime, rel in changed}
            artifact_hashes = _artifact_hashes_for_paths(artifact, rels)
            content_changed = []
            for mtime, rel in changed:
                path = root / rel
                artifact_hash = artifact_hashes.get(rel)
                if artifact_hash:
                    try:
                        current_hash = _sha256_file(path)
                    except Exception:
                        content_changed.append((mtime, rel))
                        continue
                    if current_hash == artifact_hash:
                        content_unchanged_count += 1
                        continue
                content_changed.append((mtime, rel))
            out["latest_source_freshness_basis"] = "content"
        if newest_mtime > 0:
            out["latest_source_newest_path"] = newest_path
            out["latest_source_newest_mtime"] = datetime.fromtimestamp(newest_mtime).isoformat()
        out["latest_source_touched_after_build_count"] = len(changed)
        out["latest_source_content_unchanged_after_build_count"] = content_unchanged_count
        out["latest_source_changed_after_build_count"] = len(content_changed)
        out["latest_source_changed_after_build_sample"] = [rel for _mtime, rel in content_changed[:12]]
        if content_changed:
            out["latest_source_status"] = "changed-after-build"
            out["latest_artifact_stale"] = True
            out["latest_source_changed_after_build"] = True
        else:
            out["latest_source_status"] = "current"
        return out

    def status_payload(
        self,
        ledger_path: Path,
        limit: int = 8,
        source_root: Path | None = None,
        *,
        artifact_kind: str = "package-zip",
    ) -> dict:
        selected_kind = str(artifact_kind or "package-zip").strip() or "package-zip"
        out = {
            "ok": True,
            "artifact_kind": selected_kind,
            "ledger_path": str(ledger_path),
            "latest_state": "no-builds",
            "latest_readiness_state": "no-builds",
            "latest_ready_to_ship": False,
            "latest_readiness_note": "No release builds are recorded yet.",
            "latest_artifact_path": "",
            "latest_artifact_name": "",
            "latest_version": "",
            "latest_channel": "",
            "latest_label": "",
            "latest_build_recorded_at": "",
            "latest_verified_at": "",
            "latest_verification_target": "",
            "latest_promoted_at": "",
            "latest_validation_result": "",
            "latest_validation_note": "",
            "latest_follow_up_owner": "",
            "latest_validation_machine": "",
            "latest_validation_seed_path": "",
            "latest_source_package_artifact_path": "",
            "latest_source_package_artifact_name": "",
            "latest_source_package_manifest_path": "",
            "latest_validation_record": {},
            "latest_validation_record_exists": False,
            "latest_validation_record_complete": False,
            "latest_validation_record_result": "",
            "latest_validation_record_missing_fields": [],
            "latest_validation_record_artifact_matches": False,
            "latest_source_status": "unknown",
            "latest_artifact_stale": False,
            "latest_source_changed_after_build": False,
            "latest_source_changed_after_build_count": 0,
            "latest_source_newest_path": "",
            "latest_source_newest_mtime": "",
            "latest_source_changed_after_build_sample": [],
            "recent_entries": [],
        }
        scan_limit = max(200, int(limit) * 20)
        entries = [
            entry
            for entry in self.ledger_entries(ledger_path, scan_limit)
            if _entry_artifact_kind(entry) == selected_kind
        ]
        if not entries:
            return enrich_release_status(out)

        recent_entries: list[dict] = []
        for entry in entries[: max(1, int(limit))]:
            if not isinstance(entry, dict):
                continue
            recent_entries.append({
                "recorded_at": str(entry.get("recorded_at") or ""),
                "event": str(entry.get("event") or ""),
                "version": str(entry.get("artifact_version") or ""),
                "channel": str(entry.get("release_channel") or ""),
                "label": str(entry.get("release_label") or ""),
                "result": str(entry.get("validation_result") or entry.get("verification_result") or ""),
                "note": str(entry.get("validation_note") or entry.get("verification_note") or ""),
                "artifact_name": str(entry.get("artifact_name") or ""),
                "artifact_path": str(entry.get("artifact_path") or ""),
                "source_package_artifact_path": str(entry.get("source_package_artifact_path") or ""),
                "verification_target_path": str(entry.get("verification_target_path") or ""),
                "validation_record_seed_path": str(entry.get("validation_record_seed_path") or ""),
            })
        out["recent_entries"] = recent_entries

        build_entries = [entry for entry in entries if str(entry.get("event") or "") == "build"]
        if not build_entries:
            out["latest_state"] = "ledger-without-builds"
            return enrich_release_status(out)

        latest_build = build_entries[0]
        matching_verifications = [
            entry for entry in entries
            if str(entry.get("event") or "") == "verify" and self.entry_matches_build(entry, latest_build)
        ]
        matching_promotions = [
            entry for entry in entries
            if str(entry.get("event") or "") == "promotion" and self.entry_matches_build(entry, latest_build)
        ]
        latest_verification = matching_verifications[0] if matching_verifications else None
        latest_promotion = matching_promotions[0] if matching_promotions else None

        latest_state = "built-only"
        if latest_promotion:
            result = str(latest_promotion.get("validation_result") or "").strip()
            latest_state = f"promoted-{result}" if result else "promoted"

        readiness_state = "needs-verification"
        ready_to_ship = False
        readiness_note = "Latest build has not been re-verified."
        if latest_verification:
            if latest_promotion is None:
                readiness_state = "needs-promotion"
                readiness_note = "Latest build was verified, but no validation outcome is recorded yet."
            else:
                result = str(latest_promotion.get("validation_result") or "").strip().lower()
                if result == "pass":
                    readiness_state = "ready"
                    ready_to_ship = True
                    readiness_note = "Latest build is verified and promoted with a pass result."
                elif result == "pass-with-notes":
                    readiness_state = "ready-with-notes"
                    ready_to_ship = True
                    readiness_note = "Latest build is verified and promoted with notes."
                elif result == "fail":
                    readiness_state = "blocked"
                    readiness_note = "Latest build has a failing validation result."
                else:
                    readiness_state = "needs-promotion"
                    readiness_note = "Latest build has a promotion entry without a recognized validation result."

        out.update({
            "latest_state": latest_state,
            "latest_readiness_state": readiness_state,
            "latest_ready_to_ship": ready_to_ship,
            "latest_readiness_note": readiness_note,
            "latest_artifact_path": str(latest_build.get("artifact_path") or ""),
            "latest_artifact_name": str(latest_build.get("artifact_name") or ""),
            "latest_version": str(latest_build.get("artifact_version") or ""),
            "latest_channel": str(latest_build.get("release_channel") or ""),
            "latest_label": str(latest_build.get("release_label") or ""),
            "latest_build_recorded_at": str(latest_build.get("recorded_at") or ""),
            "latest_verified_at": str((latest_verification or {}).get("recorded_at") or ""),
            "latest_verification_target": str((latest_verification or {}).get("verification_target_path") or (latest_verification or {}).get("artifact_path") or ""),
            "latest_promoted_at": str((latest_promotion or {}).get("recorded_at") or ""),
            "latest_validation_result": str((latest_promotion or {}).get("validation_result") or ""),
            "latest_validation_note": str((latest_promotion or {}).get("validation_note") or ""),
            "latest_follow_up_owner": str((latest_promotion or {}).get("follow_up_owner") or ""),
            "latest_validation_machine": str((latest_promotion or {}).get("validation_machine") or ""),
            "latest_validation_seed_path": str(latest_build.get("validation_record_seed_path") or ""),
            "latest_source_package_artifact_path": str(latest_build.get("source_package_artifact_path") or ""),
            "latest_source_package_artifact_name": Path(str(latest_build.get("source_package_artifact_path") or "")).name
            if str(latest_build.get("source_package_artifact_path") or "").strip()
            else "",
            "latest_source_package_manifest_path": str(latest_build.get("source_package_manifest_path") or ""),
        })
        validation_record = release_validation_record_payload(
            out.get("latest_validation_seed_path") or "",
            release_status=out,
        )
        out.update({
            "latest_validation_record": validation_record,
            "latest_validation_record_exists": bool(validation_record.get("exists")),
            "latest_validation_record_complete": bool(validation_record.get("complete")),
            "latest_validation_record_result": str(validation_record.get("result") or ""),
            "latest_validation_record_missing_fields": list(validation_record.get("missing_fields") or []),
            "latest_validation_record_artifact_matches": bool(validation_record.get("artifact_matches")),
        })
        if source_root is not None:
            freshness = self.source_freshness_payload(
                Path(source_root),
                str(latest_build.get("recorded_at") or ""),
                artifact_path=Path(str(latest_build.get("artifact_path") or "")),
            )
            out.update(freshness)
            if freshness.get("latest_source_changed_after_build"):
                out["latest_readiness_state"] = "source-changed-after-build"
                out["latest_ready_to_ship"] = False
                out["latest_readiness_note"] = "Live source changed after the latest release build; rebuild and verify before promotion."
        return enrich_release_status(out)


RELEASE_STATUS_SERVICE = ReleaseStatusService()
