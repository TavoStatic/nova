from __future__ import annotations

"""
Paced full-LEA sync from TEA/IODS into the local Ed-Fi warehouse.

Rules learned in the field:
  - Back-to-back live pulls get rate-limited.
  - User clicks must not hammer ODS.
  - Daily (or configured) window pulls *all* schools for the LEA into SQLite,
    then reports promote from local data.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from services.edfi.extract_store import save_extract
from services.edfi.inventory import read_preset
from services.edfi.present import present_operation_result
from services.edfi.warehouse import (
    begin_sync_run,
    finish_sync_run,
    list_schools,
    replace_schools,
    warehouse_status,
)
from services.nova_runtime_context import RUNTIME_DIR

DEFAULT_RESOURCES = ("schools",)


def _settings_path() -> Path:
    return RUNTIME_DIR / "edfi" / "settings.json"


def load_backpack_settings() -> dict[str, Any]:
    path = _settings_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _connection_id(settings: Mapping[str, Any] | None = None) -> str:
    data = dict(settings or load_backpack_settings())
    return str(data.get("connection_id") or "district-main").strip() or "district-main"


def _lea_id(settings: Mapping[str, Any] | None = None, lea: str = "") -> str:
    if lea and str(lea).strip():
        raw = str(lea).strip()
    else:
        data = dict(settings or load_backpack_settings())
        raw = str(data.get("district_lea_id") or "").strip()
    if not raw:
        return ""
    try:
        from services.backpack_host.scope_settings import format_lea_id

        return format_lea_id(raw)
    except Exception:
        return raw


def sync_schedule_config(settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    data = dict(settings or load_backpack_settings())
    enabled = str(data.get("warehouse_sync_enabled") or "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    try:
        hour = int(data.get("warehouse_sync_local_hour") or 2)
    except (TypeError, ValueError):
        hour = 2
    hour = max(0, min(23, hour))
    try:
        min_gap_hours = float(data.get("warehouse_sync_min_gap_hours") or 20)
    except (TypeError, ValueError):
        min_gap_hours = 20.0
    min_gap_hours = max(1.0, min_gap_hours)
    resources_raw = str(data.get("warehouse_sync_resources") or "schools").strip()
    resources = [r.strip().lower() for r in resources_raw.split(",") if r.strip()]
    if not resources:
        resources = list(DEFAULT_RESOURCES)
    return {
        "enabled": enabled,
        "local_hour": hour,
        "min_gap_hours": min_gap_hours,
        "resources": resources,
        "connection_id": _connection_id(data),
        "lea_id": _lea_id(data),
    }


def due_for_scheduled_sync(
    *,
    connection_id: str = "",
    lea_id: str = "",
    now: datetime | None = None,
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Whether the daily window says we should run a full warehouse sync."""
    cfg = sync_schedule_config(settings)
    conn = connection_id or cfg["connection_id"]
    lea = lea_id or cfg["lea_id"]
    now = now or datetime.now()
    if not cfg["enabled"]:
        return {"due": False, "reason": "warehouse_sync_disabled", "config": cfg}
    if not lea:
        return {"due": False, "reason": "lea_missing", "config": cfg}

    from services.edfi.warehouse import last_successful_sync

    last = last_successful_sync(connection_id=conn, resource="schools", lea_id=lea)
    if last and last.get("finished_at"):
        age_h = (time.time() - float(last["finished_at"])) / 3600.0
        if age_h < float(cfg["min_gap_hours"]):
            return {
                "due": False,
                "reason": "min_gap_not_elapsed",
                "age_hours": round(age_h, 2),
                "config": cfg,
                "last": last,
            }

    # Prefer running at/after configured local hour once per day.
    if int(now.hour) < int(cfg["local_hour"]):
        return {
            "due": False,
            "reason": "before_local_hour",
            "config": cfg,
            "last": last,
        }

    if last and last.get("finished_at"):
        last_day = datetime.fromtimestamp(float(last["finished_at"])).date()
        if last_day == now.date() and int(now.hour) >= int(cfg["local_hour"]):
            return {
                "due": False,
                "reason": "already_synced_today",
                "config": cfg,
                "last": last,
            }

    return {"due": True, "reason": "schedule_window_open", "config": cfg, "last": last}


def run_full_schools_sync(
    *,
    connection_id: str = "",
    lea_id: str = "",
    settings: Mapping[str, Any] | None = None,
    also_save_extract: bool = True,
) -> dict[str, Any]:
    """
    One paced full-LEA schools pull into the warehouse.

    Not for back-to-back UI clicks — this is the daily/job path.
    """
    cfg_settings = dict(settings or load_backpack_settings())
    conn = connection_id or _connection_id(cfg_settings)
    lea = lea_id or _lea_id(cfg_settings)
    if not lea:
        return {
            "ok": False,
            "error": "district_lea_id_required",
            "detail": "Set district_lea_id in backpack settings before warehouse sync.",
        }

    run_id = begin_sync_run(connection_id=conn, lea_id=lea, resource="schools")
    started = time.time()
    try:
        raw = read_preset(
            conn,
            "schools",
            limit=2000,
            offset=0,
            apply_district_scope=True,
            district_lea_id_override=lea,
            collect_all=True,
        )
    except Exception as exc:
        finish_sync_run(
            conn,
            run_id,
            status="failed",
            error=str(exc),
        )
        return {"ok": False, "error": str(exc), "sync_run_id": run_id}

    if not raw.get("ok"):
        err = str(raw.get("error") or raw.get("error_code") or "schools_sync_failed")
        rate_limited = "rate" in err.lower() or bool(raw.get("rate_limited"))
        finish_sync_run(
            conn,
            run_id,
            status="rate_limited" if rate_limited else "failed",
            records_scanned=int(raw.get("records_scanned") or 0),
            rate_limited=rate_limited,
            error=err,
        )
        return {
            "ok": False,
            "error": err,
            "rate_limited": rate_limited,
            "sync_run_id": run_id,
            "raw": {k: raw.get(k) for k in ("error_code", "records_scanned", "status_code")},
        }

    items = [i for i in (raw.get("items") or []) if isinstance(i, dict)]
    presented = present_operation_result("list_schools", {"items": items, "ok": True})
    shaped_rows = list(presented.get("rows") or [])
    # Prefer shaped rows for warehouse readability; fall back to raw items.
    warehouse_rows = shaped_rows if shaped_rows else items
    n = replace_schools(
        connection_id=conn,
        lea_id=lea,
        rows=warehouse_rows,
        sync_run_id=run_id,
    )
    complete = bool(raw.get("district_page_complete"))
    finish_sync_run(
        conn,
        run_id,
        status="ok",
        row_count=n,
        records_scanned=int(raw.get("records_scanned") or 0),
        district_page_complete=complete,
        notes=f"full_lea_collect elapsed_sec={round(time.time() - started, 1)}",
    )

    extract_path = ""
    if also_save_extract and shaped_rows:
        try:
            path = save_extract(
                backpack_id="edfi",
                intent="schools",
                lea=lea,
                connection_id=conn,
                columns=list(presented.get("columns") or []),
                rows=shaped_rows,
                summary=str(presented.get("summary") or f"{n} school(s) from warehouse sync."),
                meta={
                    "source": "warehouse_sync",
                    "full_lea": True,
                    "sync_run_id": run_id,
                    "district_page_complete": complete,
                    "records_scanned": raw.get("records_scanned"),
                },
            )
            extract_path = str(path)
        except Exception:
            extract_path = ""

    return {
        "ok": True,
        "connection_id": conn,
        "lea_id": lea,
        "resource": "schools",
        "row_count": n,
        "records_scanned": int(raw.get("records_scanned") or 0),
        "district_page_complete": complete,
        "sync_run_id": run_id,
        "extract_path": extract_path,
        "warehouse": warehouse_status(conn, lea_id=lea),
        "summary": (
            f"Warehouse sync stored {n} school(s) for LEA {lea}. "
            f"Scanned {int(raw.get('records_scanned') or 0)} statewide rows. "
            f"complete={complete}."
        ),
        "note": (
            "Do not run this back-to-back. Next pull should wait for the configured "
            "daily window (or min gap hours) unless data is critically stale."
        ),
    }


def maybe_run_scheduled_warehouse_sync(
    *,
    force: bool = False,
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Entry for host tick / CLI: run full schools sync only when schedule says due."""
    gate = due_for_scheduled_sync(settings=settings)
    if force:
        result = run_full_schools_sync(settings=settings)
        result["schedule"] = {**gate, "forced": True}
        return result
    if not gate.get("due"):
        return {
            "ok": True,
            "ran": False,
            "schedule": gate,
            "warehouse": warehouse_status(
                gate.get("config", {}).get("connection_id") or "district-main",
                lea_id=str(gate.get("config", {}).get("lea_id") or ""),
            ),
        }
    result = run_full_schools_sync(settings=settings)
    result["ran"] = bool(result.get("ok"))
    result["schedule"] = gate
    return result


def schools_report_from_warehouse(
    *,
    connection_id: str = "",
    lea_id: str = "",
    limit: int | None = None,
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Shape warehouse schools into report rows, or None if empty."""
    cfg = dict(settings or load_backpack_settings())
    conn = connection_id or _connection_id(cfg)
    lea = lea_id or _lea_id(cfg)
    if not lea:
        return None
    rows_raw = list_schools(connection_id=conn, lea_id=lea, limit=None)
    if not rows_raw:
        return None
    presented = present_operation_result("list_schools", {"items": rows_raw, "ok": True})
    rows = list(presented.get("rows") or [])
    if limit is not None and int(limit) > 0:
        display = rows[: int(limit)]
    else:
        display = rows
    last = warehouse_status(conn, lea_id=lea).get("last_schools_sync") or {}
    synced = ""
    if last.get("finished_at"):
        synced = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(last["finished_at"])))
    return {
        "ok": True,
        "from_warehouse": True,
        "from_extract": False,
        "live_pull": False,
        "columns": list(presented.get("columns") or []),
        "rows": display,
        "row_count": len(display),
        "total_in_warehouse": len(rows),
        "summary": (
            str(presented.get("summary") or f"{len(rows)} school(s)")
            + f" [local warehouse; {len(rows)} total for LEA {lea}"
            + (f"; synced {synced}" if synced else "")
            + "]"
        ),
        "connection_id": conn,
        "district_lea_id": lea,
        "synced_at": synced,
        "governed_route": "edfi_warehouse",
    }
