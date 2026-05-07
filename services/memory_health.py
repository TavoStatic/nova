from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable


def _compact(value: Any, max_chars: int = 220) -> str:
    text = str(value or "").strip()
    return text[: max(1, int(max_chars))]


def _issue(severity: str, code: str, detail: str, *, path: Path | None = None) -> dict[str, str]:
    out = {
        "severity": _compact(severity, 24) or "warning",
        "code": _compact(code, 80) or "memory_health_issue",
        "detail": _compact(detail, 260),
    }
    if path is not None:
        out["path"] = str(path)
    return out


def _tmp_path(path: Path) -> Path:
    suffix = path.suffix
    if suffix:
        return path.with_suffix(f"{suffix}.tmp")
    return path.with_name(f"{path.name}.tmp")


def _load_json_dict(path: Path) -> tuple[dict, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, str(exc)
    if not isinstance(data, dict):
        return {}, "json_root_not_object"
    return data, ""


def _json_file_health(path: Path, *, label: str) -> dict[str, object]:
    final = Path(path)
    tmp = _tmp_path(final)
    final_exists = final.exists()
    tmp_exists = tmp.exists()
    final_error = ""
    tmp_error = ""
    final_key_count = 0
    tmp_key_count = 0
    issues: list[dict[str, str]] = []

    if final_exists:
        final_data, final_error = _load_json_dict(final)
        final_key_count = len(final_data)
        if final_error:
            issues.append(_issue("failure", f"{label}_json_invalid", f"{label} JSON is not readable: {final_error}", path=final))
    if tmp_exists:
        tmp_data, tmp_error = _load_json_dict(tmp)
        tmp_key_count = len(tmp_data)
        if tmp_error:
            issues.append(_issue("warning", f"{label}_tmp_invalid", f"{label} tmp JSON is not readable: {tmp_error}", path=tmp))
        elif not final_exists:
            issues.append(_issue("warning", f"{label}_orphan_tmp", f"{label} has a valid tmp file but no final JSON file.", path=tmp))
        elif tmp.stat().st_mtime > final.stat().st_mtime + 5:
            issues.append(_issue("warning", f"{label}_tmp_newer", f"{label} tmp JSON is newer than the final JSON file.", path=tmp))

    return {
        "path": str(final),
        "exists": final_exists,
        "valid": final_exists and not final_error,
        "key_count": final_key_count,
        "tmp_path": str(tmp),
        "tmp_exists": tmp_exists,
        "tmp_valid": tmp_exists and not tmp_error,
        "tmp_key_count": tmp_key_count,
        "issues": issues,
    }


def _sqlite_memory_health(db_path: Path) -> dict[str, object]:
    path = Path(db_path)
    issues: list[dict[str, str]] = []
    payload: dict[str, object] = {
        "path": str(path),
        "exists": path.exists(),
        "ok": False,
        "quick_check": "",
        "table_exists": False,
        "total": 0,
        "oldest_ts": None,
        "newest_ts": None,
        "issues": issues,
    }
    if not path.exists():
        issues.append(_issue("failure", "memory_db_missing", "Memory database file is missing.", path=path))
        return payload

    try:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
    except Exception as exc:
        issues.append(_issue("failure", "memory_db_open_failed", f"Memory database could not be opened read-only: {exc}", path=path))
        return payload

    try:
        quick = str(con.execute("PRAGMA quick_check").fetchone()[0] or "")
        payload["quick_check"] = quick
        if quick.lower() != "ok":
            issues.append(_issue("failure", "memory_db_quick_check_failed", f"SQLite quick_check returned {quick}.", path=path))

        table = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
        ).fetchone()
        payload["table_exists"] = table is not None
        if table is None:
            issues.append(_issue("failure", "memory_table_missing", "Memory database has no memories table.", path=path))
            return payload

        total = int(con.execute("SELECT COUNT(*) FROM memories").fetchone()[0] or 0)
        oldest = con.execute("SELECT MIN(ts) FROM memories").fetchone()[0]
        newest = con.execute("SELECT MAX(ts) FROM memories").fetchone()[0]
        payload["total"] = total
        payload["oldest_ts"] = int(oldest) if oldest else None
        payload["newest_ts"] = int(newest) if newest else None
        payload["ok"] = quick.lower() == "ok"
        return payload
    except Exception as exc:
        issues.append(_issue("failure", "memory_db_read_failed", f"Memory database read failed: {exc}", path=path))
        return payload
    finally:
        try:
            con.close()
        except Exception:
            pass


def _load_snapshot(path: Path) -> dict:
    try:
        if not Path(path).exists():
            return {}
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_snapshot(path: Path, payload: dict[str, object]) -> None:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception:
        pass


def build_memory_health_payload(
    *,
    memory_db_path: Path,
    learned_facts_file: Path,
    identity_file: Path,
    snapshot_file: Path | None = None,
    update_snapshot: bool = False,
    now_fn: Callable[[], float] = time.time,
) -> dict[str, object]:
    db = _sqlite_memory_health(Path(memory_db_path))
    learned_facts = _json_file_health(Path(learned_facts_file), label="learned_facts")
    identity = _json_file_health(Path(identity_file), label="identity")

    issues: list[dict[str, str]] = []
    for source_name, source_payload in (
        ("memory_db", db),
        ("learned_facts", learned_facts),
        ("identity", identity),
    ):
        for item in list(source_payload.get("issues") or []):
            if isinstance(item, dict):
                row = dict(item)
                row["source"] = source_name
                issues.append(row)

    snapshot = _load_snapshot(snapshot_file) if snapshot_file is not None else {}
    prior_total = int(snapshot.get("last_good_total", 0) or 0)
    current_total = int(db.get("total", 0) or 0)
    count_drop = max(0, prior_total - current_total) if prior_total else 0
    if bool(db.get("ok")) and prior_total and count_drop > 0:
        severity = "failure" if current_total == 0 or count_drop >= max(1, int(prior_total * 0.25)) else "warning"
        issues.append(
            _issue(
                severity,
                "memory_count_drop",
                f"Memory row count dropped from {prior_total} to {current_total}.",
                path=Path(memory_db_path),
            )
        )

    status = "ok"
    if any(str(item.get("severity") or "") == "failure" for item in issues):
        status = "failure"
    elif issues:
        status = "watch"
    ok = bool(db.get("ok")) and status == "ok"

    if snapshot_file is not None and update_snapshot and bool(db.get("ok")):
        should_update = not prior_total or current_total >= prior_total
        if should_update:
            _write_snapshot(
                snapshot_file,
                {
                    "updated_at": int(now_fn()),
                    "last_good_total": current_total,
                    "memory_db_path": str(memory_db_path),
                    "learned_facts_path": str(learned_facts_file),
                    "identity_path": str(identity_file),
                },
            )

    return {
        "ok": ok,
        "status": status,
        "generated_at": int(now_fn()),
        "memory_db": db,
        "learned_facts": learned_facts,
        "identity": identity,
        "snapshot": {
            "path": str(snapshot_file) if snapshot_file is not None else "",
            "last_good_total": prior_total,
            "count_drop": count_drop,
        },
        "issue_count": len(issues),
        "issues": issues[:12],
    }
