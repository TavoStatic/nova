from __future__ import annotations

"""
Ed-Fi local warehouse (SQLite).

Product model (bridge, not live SIS browser):
  - TEA/IODS rate-limits forbid back-to-back full pulls for user clicks.
  - Nova runs a paced full-LEA sync into this DB (daily window or explicit job).
  - Reports and tools read the warehouse first; live ODS is for sync only.

Path: runtime/edfi/warehouse/{connection_id}.sqlite3
"""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Iterable, Mapping

from services.nova_runtime_context import RUNTIME_DIR

WAREHOUSE_ROOT = RUNTIME_DIR / "edfi" / "warehouse"
SCHEMA_VERSION = 1


def warehouse_path(connection_id: str = "district-main") -> Path:
    safe = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "_"
        for ch in str(connection_id or "district-main").strip()
    ) or "district-main"
    return WAREHOUSE_ROOT / f"{safe}.sqlite3"


@contextmanager
def _connect(connection_id: str = "district-main") -> Generator[sqlite3.Connection, None, None]:
    path = warehouse_path(connection_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        _ensure_schema(con)
        yield con
        con.commit()
    finally:
        con.close()


def _ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id TEXT NOT NULL,
            lea_id TEXT NOT NULL,
            resource TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at REAL NOT NULL,
            finished_at REAL,
            row_count INTEGER NOT NULL DEFAULT 0,
            records_scanned INTEGER NOT NULL DEFAULT 0,
            district_page_complete INTEGER NOT NULL DEFAULT 0,
            rate_limited INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS schools (
            lea_id TEXT NOT NULL,
            school_id TEXT NOT NULL,
            school_name TEXT NOT NULL DEFAULT '',
            school_type TEXT NOT NULL DEFAULT '',
            grade_levels TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL,
            synced_at REAL NOT NULL,
            sync_run_id INTEGER,
            PRIMARY KEY (lea_id, school_id)
        );

        CREATE INDEX IF NOT EXISTS idx_schools_lea ON schools(lea_id);
        CREATE INDEX IF NOT EXISTS idx_sync_runs_conn ON sync_runs(connection_id, resource, started_at);
        """
    )
    con.execute(
        "INSERT OR REPLACE INTO meta(key, value, updated_at) VALUES(?,?,?)",
        ("schema_version", str(SCHEMA_VERSION), time.time()),
    )


def begin_sync_run(
    *,
    connection_id: str,
    lea_id: str,
    resource: str,
) -> int:
    with _connect(connection_id) as con:
        cur = con.execute(
            """
            INSERT INTO sync_runs(
                connection_id, lea_id, resource, status, started_at
            ) VALUES (?,?,?,?,?)
            """,
            (
                str(connection_id or "").strip(),
                str(lea_id or "").strip(),
                str(resource or "").strip(),
                "running",
                time.time(),
            ),
        )
        return int(cur.lastrowid or 0)


def finish_sync_run(
    connection_id: str,
    run_id: int,
    *,
    status: str,
    row_count: int = 0,
    records_scanned: int = 0,
    district_page_complete: bool = False,
    rate_limited: bool = False,
    error: str = "",
    notes: str = "",
) -> None:
    with _connect(connection_id) as con:
        con.execute(
            """
            UPDATE sync_runs SET
                status=?, finished_at=?, row_count=?, records_scanned=?,
                district_page_complete=?, rate_limited=?, error=?, notes=?
            WHERE id=?
            """,
            (
                str(status or "failed")[:40],
                time.time(),
                int(row_count or 0),
                int(records_scanned or 0),
                1 if district_page_complete else 0,
                1 if rate_limited else 0,
                str(error or "")[:2000],
                str(notes or "")[:2000],
                int(run_id),
            ),
        )


def replace_schools(
    *,
    connection_id: str,
    lea_id: str,
    rows: Iterable[Mapping[str, Any]],
    sync_run_id: int | None = None,
) -> int:
    """Replace all warehouse schools for one LEA with the full sync result."""
    lea = str(lea_id or "").strip()
    now = time.time()
    prepared: list[tuple[Any, ...]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        school_id = str(
            raw.get("school_id")
            or raw.get("schoolId")
            or raw.get("id")
            or ""
        ).strip()
        if not school_id:
            continue
        name = str(
            raw.get("school_name")
            or raw.get("nameOfInstitution")
            or raw.get("name")
            or ""
        ).strip()
        school_type = str(raw.get("school_type") or raw.get("schoolType") or "").strip()
        grades = raw.get("grade_levels") or raw.get("gradeLevels") or ""
        if isinstance(grades, list):
            grades = ", ".join(str(g) for g in grades)
        prepared.append(
            (
                lea,
                school_id,
                name,
                school_type,
                str(grades or ""),
                json.dumps(dict(raw), ensure_ascii=False, default=str),
                now,
                int(sync_run_id or 0) or None,
            )
        )

    with _connect(connection_id) as con:
        con.execute("DELETE FROM schools WHERE lea_id=?", (lea,))
        if prepared:
            con.executemany(
                """
                INSERT INTO schools(
                    lea_id, school_id, school_name, school_type, grade_levels,
                    payload_json, synced_at, sync_run_id
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                prepared,
            )
        con.execute(
            "INSERT OR REPLACE INTO meta(key, value, updated_at) VALUES(?,?,?)",
            (f"schools_synced_at:{lea}", str(now), now),
        )
        con.execute(
            "INSERT OR REPLACE INTO meta(key, value, updated_at) VALUES(?,?,?)",
            (f"schools_row_count:{lea}", str(len(prepared)), now),
        )
    return len(prepared)


def list_schools(
    *,
    connection_id: str,
    lea_id: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    lea = str(lea_id or "").strip()
    with _connect(connection_id) as con:
        sql = """
            SELECT school_id, school_name, school_type, grade_levels, payload_json, synced_at
            FROM schools WHERE lea_id=?
            ORDER BY school_name COLLATE NOCASE, school_id
        """
        params: list[Any] = [lea]
        if limit is not None and int(limit) > 0:
            sql += " LIMIT ?"
            params.append(int(limit))
        rows = con.execute(sql, params).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        payload: dict[str, Any] = {}
        try:
            parsed = json.loads(row["payload_json"] or "{}")
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:
            payload = {}
        if not payload:
            payload = {
                "school_id": row["school_id"],
                "school_name": row["school_name"],
                "school_type": row["school_type"],
                "grade_levels": row["grade_levels"],
            }
        else:
            payload.setdefault("school_id", row["school_id"])
            payload.setdefault("school_name", row["school_name"])
        payload["_warehouse_synced_at"] = row["synced_at"]
        out.append(payload)
    return out


def schools_count(*, connection_id: str, lea_id: str) -> int:
    lea = str(lea_id or "").strip()
    with _connect(connection_id) as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM schools WHERE lea_id=?",
            (lea,),
        ).fetchone()
    return int(row["n"] if row else 0)


def last_successful_sync(
    *,
    connection_id: str,
    resource: str = "schools",
    lea_id: str = "",
) -> dict[str, Any] | None:
    with _connect(connection_id) as con:
        if lea_id:
            row = con.execute(
                """
                SELECT * FROM sync_runs
                WHERE connection_id=? AND resource=? AND lea_id=? AND status='ok'
                ORDER BY finished_at DESC LIMIT 1
                """,
                (connection_id, resource, str(lea_id).strip()),
            ).fetchone()
        else:
            row = con.execute(
                """
                SELECT * FROM sync_runs
                WHERE connection_id=? AND resource=? AND status='ok'
                ORDER BY finished_at DESC LIMIT 1
                """,
                (connection_id, resource),
            ).fetchone()
    if not row:
        return None
    return {k: row[k] for k in row.keys()}


def warehouse_status(connection_id: str = "district-main", lea_id: str = "") -> dict[str, Any]:
    path = warehouse_path(connection_id)
    last = last_successful_sync(connection_id=connection_id, resource="schools", lea_id=lea_id)
    count = schools_count(connection_id=connection_id, lea_id=lea_id) if lea_id else 0
    if not lea_id and path.is_file():
        with _connect(connection_id) as con:
            row = con.execute("SELECT COUNT(*) AS n FROM schools").fetchone()
            count = int(row["n"] if row else 0)
    return {
        "ok": path.is_file() and count > 0,
        "connection_id": connection_id,
        "path": str(path),
        "exists": path.is_file(),
        "schools_count": count,
        "lea_id": lea_id,
        "last_schools_sync": last,
        "model": "local_warehouse_first",
        "note": (
            "Reports should read this warehouse. Live TEA is for scheduled/full sync only — "
            "not back-to-back user clicks."
        ),
    }
