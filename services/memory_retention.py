from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable


DEFAULT_DURABLE_KINDS = (
    "identity",
    "fact",
    "user_correction",
    "profile",
    "user_fact",
)
DEFAULT_EPHEMERAL_KINDS = ("chat_user",)
DEFAULT_RECALL_EXCLUDE_KINDS = ("chat_user",)
DEFAULT_STORE_BLOCKED_KINDS = ("chat_user",)


def _normalize_kind_list(values: Any, *, fallback: tuple[str, ...]) -> list[str]:
    if not isinstance(values, list):
        return list(fallback)
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        kind = str(raw or "").strip().lower()
        if not kind or kind in seen:
            continue
        seen.add(kind)
        out.append(kind)
    return out or list(fallback)


def parse_retention_policy(memory_policy: dict[str, Any] | None) -> dict[str, Any]:
    policy = memory_policy if isinstance(memory_policy, dict) else {}
    retention = policy.get("retention") if isinstance(policy.get("retention"), dict) else {}
    durable = _normalize_kind_list(retention.get("durable_kinds"), fallback=DEFAULT_DURABLE_KINDS)
    ephemeral = _normalize_kind_list(retention.get("ephemeral_kinds"), fallback=DEFAULT_EPHEMERAL_KINDS)
    recall_exclude = _normalize_kind_list(
        retention.get("recall_exclude_kinds"),
        fallback=DEFAULT_RECALL_EXCLUDE_KINDS,
    )
    store_blocked = _normalize_kind_list(
        retention.get("store_blocked_kinds"),
        fallback=DEFAULT_STORE_BLOCKED_KINDS,
    )
    try:
        contamination_threshold = int(retention.get("contamination_min_ephemeral_rows", 1) or 1)
    except Exception:
        contamination_threshold = 1
    contamination_threshold = max(1, contamination_threshold)
    return {
        "durable_kinds": durable,
        "ephemeral_kinds": ephemeral,
        "recall_exclude_kinds": recall_exclude,
        "store_blocked_kinds": store_blocked,
        "contamination_min_ephemeral_rows": contamination_threshold,
        "purge_kinds": list(ephemeral),
    }


def _kind_counts(con: sqlite3.Connection) -> dict[str, int]:
    rows = con.execute(
        "SELECT kind, COUNT(*) FROM memories GROUP BY kind ORDER BY COUNT(*) DESC"
    ).fetchall()
    return {str(kind or "").strip().lower(): int(count or 0) for kind, count in rows}


def evaluate_contamination(
    db_path: Path,
    *,
    retention_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = parse_retention_policy(retention_policy or {})
    path = Path(db_path)
    payload: dict[str, Any] = {
        "ok": True,
        "path": str(path),
        "exists": path.exists(),
        "total": 0,
        "by_kind": {},
        "ephemeral_kinds": list(policy["ephemeral_kinds"]),
        "ephemeral_rows": 0,
        "contaminated": False,
        "contamination_threshold": int(policy["contamination_min_ephemeral_rows"]),
        "purge_candidates": [],
    }
    if not path.exists():
        return payload

    try:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
    except Exception as exc:
        payload["ok"] = False
        payload["error"] = str(exc)
        return payload

    try:
        table = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
        ).fetchone()
        if table is None:
            payload["ok"] = False
            payload["error"] = "memory_table_missing"
            return payload

        payload["total"] = int(con.execute("SELECT COUNT(*) FROM memories").fetchone()[0] or 0)
        by_kind = _kind_counts(con)
        payload["by_kind"] = by_kind

        purge_candidates: list[dict[str, Any]] = []
        ephemeral_rows = 0
        for kind in policy["ephemeral_kinds"]:
            count = int(by_kind.get(kind, 0) or 0)
            if count <= 0:
                continue
            ephemeral_rows += count
            purge_candidates.append({"kind": kind, "count": count})

        payload["ephemeral_rows"] = ephemeral_rows
        payload["purge_candidates"] = purge_candidates
        payload["contaminated"] = ephemeral_rows >= int(policy["contamination_min_ephemeral_rows"])
        return payload
    except Exception as exc:
        payload["ok"] = False
        payload["error"] = str(exc)
        return payload
    finally:
        try:
            con.close()
        except Exception:
            pass


def _append_audit_line(path: Path, entry: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
    except Exception:
        pass


def apply_memory_hygiene(
    db_path: Path,
    *,
    retention_policy: dict[str, Any] | None = None,
    dry_run: bool = True,
    audit_log_path: Path | None = None,
    now_fn: Callable[[], float] = time.time,
) -> dict[str, Any]:
    policy = parse_retention_policy(retention_policy or {})
    evaluation = evaluate_contamination(db_path, retention_policy=policy)
    kinds = [str(item.get("kind") or "").strip().lower() for item in list(evaluation.get("purge_candidates") or [])]
    kinds = [kind for kind in kinds if kind]
    result: dict[str, Any] = {
        "ok": bool(evaluation.get("ok")),
        "dry_run": bool(dry_run),
        "path": str(db_path),
        "contaminated": bool(evaluation.get("contaminated")),
        "ephemeral_rows": int(evaluation.get("ephemeral_rows", 0) or 0),
        "purge_kinds": kinds,
        "deleted_rows": 0,
        "remaining_total": int(evaluation.get("total", 0) or 0),
        "by_kind_before": dict(evaluation.get("by_kind") or {}),
        "by_kind_after": dict(evaluation.get("by_kind") or {}),
        "samples": [],
        "audit_log_path": str(audit_log_path) if audit_log_path is not None else "",
    }
    if not evaluation.get("ok"):
        result["error"] = str(evaluation.get("error") or "evaluation_failed")
        return result
    if not kinds:
        result["status"] = "clean"
        return result

    path = Path(db_path)
    try:
        con = sqlite3.connect(path)
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)
        return result

    placeholders = ",".join("?" for _ in kinds)
    try:
        sample_rows = con.execute(
            f"""
            SELECT id, ts, kind, source, substr(text, 1, 120)
            FROM memories
            WHERE lower(kind) IN ({placeholders})
            ORDER BY ts DESC
            LIMIT 5
            """,
            tuple(kinds),
        ).fetchall()
        result["samples"] = [
            {
                "id": int(row[0]),
                "ts": int(row[1] or 0),
                "kind": str(row[2] or ""),
                "source": str(row[3] or ""),
                "preview": str(row[4] or ""),
            }
            for row in sample_rows
        ]

        if dry_run:
            pending = int(
                con.execute(
                    f"SELECT COUNT(*) FROM memories WHERE lower(kind) IN ({placeholders})",
                    tuple(kinds),
                ).fetchone()[0]
                or 0
            )
            result["deleted_rows"] = pending
            result["remaining_total"] = max(0, int(evaluation.get("total", 0) or 0) - pending)
            after = dict(result["by_kind_before"])
            for kind in kinds:
                after.pop(kind, None)
            result["by_kind_after"] = after
            result["status"] = "dry_run"
            return result

        deleted = con.execute(
            f"DELETE FROM memories WHERE lower(kind) IN ({placeholders})",
            tuple(kinds),
        ).rowcount
        con.commit()
        result["deleted_rows"] = int(deleted or 0)
        result["remaining_total"] = int(con.execute("SELECT COUNT(*) FROM memories").fetchone()[0] or 0)
        result["by_kind_after"] = _kind_counts(con)
        result["status"] = "applied"

        if audit_log_path is not None:
            _append_audit_line(
                audit_log_path,
                {
                    "ts": int(now_fn()),
                    "action": "memory_hygiene",
                    "dry_run": False,
                    "deleted_rows": result["deleted_rows"],
                    "purge_kinds": kinds,
                    "remaining_total": result["remaining_total"],
                    "path": str(path),
                },
            )
        return result
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)
        return result
    finally:
        try:
            con.close()
        except Exception:
            pass


def render_memory_hygiene_result(result: dict[str, Any]) -> str:
    lines = [
        "Memory Hygiene",
        f"- status: {result.get('status') or ('blocked' if not result.get('ok') else 'unknown')}",
        f"- dry_run: {bool(result.get('dry_run'))}",
        f"- contaminated: {bool(result.get('contaminated'))}",
        f"- ephemeral_rows: {int(result.get('ephemeral_rows', 0) or 0)}",
        f"- purge_kinds: {', '.join(result.get('purge_kinds') or []) or 'none'}",
        f"- deleted_rows: {int(result.get('deleted_rows', 0) or 0)}",
        f"- remaining_total: {int(result.get('remaining_total', 0) or 0)}",
    ]
    if result.get("error"):
        lines.append(f"- error: {result.get('error')}")
    samples = list(result.get("samples") or [])
    if samples:
        lines.append("- samples:")
        for row in samples[:3]:
            if not isinstance(row, dict):
                continue
            lines.append(
                "  - "
                f"id={row.get('id')} kind={row.get('kind')} source={row.get('source')} "
                f"preview={str(row.get('preview') or '')[:80]}"
            )
    if bool(result.get("dry_run")) and bool(result.get("contaminated")):
        lines.append("- next: rerun with dry_run=false after operator review to apply purge.")
    return "\n".join(lines)