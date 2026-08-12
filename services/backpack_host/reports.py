from __future__ import annotations

"""
User-request report path for backpacks.

Default model for data connector / TEA:
  1. Serve from local extract (runtime/edfi/extracts) when available.
  2. Live ODS pull only on explicit refresh (force_refresh=True).
  3. After a successful live pull, save a clean extract for next reports.

This avoids rate-limits from re-querying TEA on every panel click.
"""

from typing import Any, Mapping, Optional

# intent → pipeline operation
EDFI_REPORT_INTENTS: dict[str, dict[str, str]] = {
    "schools": {
        "pipeline_id": "edfi",
        "operation": "list_schools",
        "backpack_operation": "view_data",
        "label": "Schools directory",
        "description": "List campuses for the scoped LEA (reader-friendly).",
        "prefer_local": "true",
    },
    "schools_directory": {
        "pipeline_id": "edfi",
        "operation": "list_schools",
        "backpack_operation": "view_data",
        "label": "Schools directory",
        "description": "List campuses for the scoped LEA (reader-friendly).",
        "prefer_local": "true",
    },
    "health": {
        "pipeline_id": "edfi",
        "operation": "connection_health",
        "backpack_operation": "view_status",
        "label": "Connection health",
        "description": "data connector connection health summary (local profile; refresh only when forced).",
        "prefer_local": "true",
    },
    "connection_health": {
        "pipeline_id": "edfi",
        "operation": "connection_health",
        "backpack_operation": "view_status",
        "label": "Connection health",
        "description": "data connector connection health summary (local profile; refresh only when forced).",
        "prefer_local": "true",
    },
    "students": {
        "pipeline_id": "edfi",
        "operation": "list_students",
        "backpack_operation": "view_data",
        "label": "Students directory",
        "description": "List students for the scoped LEA (limited fields).",
        "prefer_local": "true",
    },
}


def list_report_intents(backpack_id: str = "edfi") -> list[dict[str, str]]:
    bid = str(backpack_id or "edfi").strip() or "edfi"
    if bid != "edfi":
        return []
    preferred = []
    for name in ("health", "schools", "students"):
        if name in EDFI_REPORT_INTENTS:
            m = EDFI_REPORT_INTENTS[name]
            preferred.append(
                {
                    "intent": name,
                    "label": m["label"],
                    "description": m["description"],
                    "operation": m["operation"],
                    "backpack_operation": m["backpack_operation"],
                }
            )
    return preferred


def resolve_report_intent(intent: str, backpack_id: str = "edfi") -> dict[str, str] | None:
    key = str(intent or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "school": "schools",
        "campus": "schools",
        "campuses": "schools",
        "show_schools": "schools",
        "list_schools": "schools",
        "status": "health",
        "connection": "health",
        "student": "students",
        "list_students": "students",
        "refresh_schools": "schools",
        "sync_schools": "schools",
    }
    key = aliases.get(key, key)
    meta = EDFI_REPORT_INTENTS.get(key)
    if not meta:
        return None
    bid = str(backpack_id or meta.get("pipeline_id") or "edfi").strip() or "edfi"
    return {
        "intent": key,
        "pipeline_id": bid if bid == "edfi" else meta["pipeline_id"],
        "operation": meta["operation"],
        "backpack_operation": meta["backpack_operation"],
        "label": meta["label"],
        "description": meta["description"],
        "prefer_local": meta.get("prefer_local") or "true",
    }


def _is_rate_limited_error(error: Any, result: Mapping[str, Any] | None = None) -> bool:
    text = str(error or "").lower()
    if "ratelimit" in text or "rate_limit" in text or "rate limited" in text or "429" in text:
        return True
    if result and (
        result.get("rate_limited")
        or str(result.get("error_code") or "").lower() in {"edfi_rate_limited", "rate_limited"}
    ):
        return True
    if "operation" in text and "ratelimit" in text.replace(" ", ""):
        return True
    return False


def _friendly_report_error(error: Any, result: Mapping[str, Any] | None = None) -> str:
    if _is_rate_limited_error(error, result):
        return (
            "TEA ODS rate limit. Nova will serve local extracts when available. "
            "Wait 1–2 minutes, then use Refresh from ODS once — not every click."
        )
    raw = str(error or "report_failed").strip()
    if not raw:
        return "report_failed"
    if len(raw) > 180:
        return raw[:177] + "..."
    return raw


_RATE_LIMIT_COOLDOWN_UNTIL: float = 0.0


def clear_report_cache() -> None:
    """Compatibility no-op name; clears rate-limit cooldown."""
    global _RATE_LIMIT_COOLDOWN_UNTIL
    _RATE_LIMIT_COOLDOWN_UNTIL = 0.0


def _resolve_lea_for_extract(lea: str, result: Mapping[str, Any] | None = None) -> str:
    from services.backpack_host.scope_settings import format_lea_id

    if lea and str(lea).strip():
        return format_lea_id(lea)
    if result:
        raw = result.get("district_lea_id")
        if raw not in (None, ""):
            return format_lea_id(raw)
    # Fall back to settings primary
    try:
        from services.nova_runtime_context import RUNTIME_DIR
        import json
        from pathlib import Path

        settings_path = Path(RUNTIME_DIR) / "edfi" / "settings.json"
        if settings_path.is_file():
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("district_lea_id"):
                return format_lea_id(data.get("district_lea_id"))
    except Exception:
        pass
    return ""


def _local_health_report(resolved: Mapping[str, str], *, role: str) -> dict[str, Any]:
    """Serve connection health from disk profile — no live ODS traffic."""
    from services.edfi.inventory import profile_summary
    from services.edfi.present import present_operation_result

    connection_id = "district-main"
    try:
        from services.nova_runtime_context import RUNTIME_DIR
        import json
        from pathlib import Path

        settings_path = Path(RUNTIME_DIR) / "edfi" / "settings.json"
        if settings_path.is_file():
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("connection_id"):
                connection_id = str(data.get("connection_id") or connection_id)
    except Exception:
        pass

    raw = profile_summary(connection_id)
    presented = present_operation_result("connection_health", raw if isinstance(raw, dict) else {})
    ok = bool(raw.get("ok")) if isinstance(raw, dict) else False
    summary = str(presented.get("summary") or "")
    if ok:
        summary = (summary + " [local profile — not a live TEA check]").strip()
    return {
        "ok": ok,
        "intent": resolved["intent"],
        "label": resolved["label"],
        "description": resolved["description"],
        "pipeline_id": resolved["pipeline_id"],
        "operation": resolved["operation"],
        "backpack_operation": resolved["backpack_operation"],
        "role": role,
        "summary": summary or ("Profile health unavailable." if not ok else "ok"),
        "report_intent": "connection_health",
        "columns": list(presented.get("columns") or []),
        "rows": list(presented.get("rows") or []),
        "row_count": int(presented.get("row_count") or 0),
        "connection_id": connection_id,
        "reader_friendly": True,
        "governed_route": "local_profile",
        "from_extract": False,
        "from_cache": True,
        "live_pull": False,
        "error": "" if ok else str((raw or {}).get("error") or "edfi_profile_missing"),
    }


def _payload_from_extract(
    resolved: Mapping[str, str],
    extract: Mapping[str, Any],
    *,
    role: str,
    limit: Optional[int],
) -> dict[str, Any]:
    rows = list(extract.get("rows") or [])
    if limit is not None and int(limit) > 0:
        rows = rows[: int(limit)]
    synced = str(extract.get("synced_at") or "")
    base_summary = str(extract.get("summary") or "")
    summary = (
        f"{base_summary} [local extract synced {synced}]"
        if base_summary
        else f"Local extract ({len(rows)} row(s)), synced {synced or 'unknown'}."
    )
    return {
        "ok": True,
        "intent": resolved["intent"],
        "label": resolved["label"],
        "description": resolved["description"],
        "pipeline_id": resolved["pipeline_id"],
        "operation": resolved["operation"],
        "backpack_operation": resolved["backpack_operation"],
        "role": role,
        "summary": summary,
        "report_intent": resolved["intent"],
        "columns": list(extract.get("columns") or []),
        "rows": rows,
        "row_count": len(rows),
        "connection_id": extract.get("connection_id"),
        "district_lea_id": extract.get("lea"),
        "reader_friendly": True,
        "governed_route": "local_extract",
        "from_extract": True,
        "from_cache": True,
        "synced_at": synced,
        "extract_path": extract.get("extract_path"),
        "stale": bool(extract.get("stale")),
    }


def run_backpack_report(
    intent: str,
    *,
    backpack_id: str = "edfi",
    role: str = "standard_user",
    lea: str = "",
    limit: Optional[int] = 50,
    params: Optional[Mapping[str, Any]] = None,
    retry_on_rate_limit: bool = False,
    use_cache: bool = True,
    prefer_local: bool | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    User report path.

    prefer_local (default True for schools/students):
      serve local extract if present; do not hit TEA.
    force_refresh:
      pull from ODS, save extract, return live rows.
      Schools refresh uses a high row cap so full LEAs (often >25 campuses) fit.
    """
    import time

    from services.backpack_host.query import run_backpack_query
    from services.edfi.extract_store import load_extract, save_extract

    global _RATE_LIMIT_COOLDOWN_UNTIL

    resolved = resolve_report_intent(intent, backpack_id=backpack_id)
    if not resolved:
        return {
            "ok": False,
            "error": f"unknown_report_intent:{intent}",
            "available_intents": [i["intent"] for i in list_report_intents(backpack_id)],
        }

    use_local = prefer_local
    if use_local is None:
        use_local = str(resolved.get("prefer_local") or "true").lower() in {
            "1",
            "true",
            "yes",
        }

    lea_key = _resolve_lea_for_extract(lea)

    # Health is local profile only unless force_refresh (never auto-hammer TEA).
    if resolved["intent"] in {"health", "connection_health"} and not force_refresh:
        return _local_health_report(resolved, role=role)

    # 0) Local warehouse first for schools (full LEA dataset from daily/paced sync).
    if (
        use_local
        and not force_refresh
        and use_cache
        and resolved["intent"] in {"schools", "schools_directory"}
    ):
        try:
            from services.edfi.warehouse_sync import schools_report_from_warehouse

            wh = schools_report_from_warehouse(lea_id=lea_key, limit=limit)
            if wh and wh.get("ok") and wh.get("rows") is not None:
                return {
                    "ok": True,
                    "intent": resolved["intent"],
                    "label": resolved["label"],
                    "description": resolved["description"],
                    "pipeline_id": resolved["pipeline_id"],
                    "operation": resolved["operation"],
                    "backpack_operation": resolved["backpack_operation"],
                    "role": role,
                    "summary": wh.get("summary") or "",
                    "report_intent": "schools_directory",
                    "columns": list(wh.get("columns") or []),
                    "rows": list(wh.get("rows") or []),
                    "row_count": int(wh.get("row_count") or 0),
                    "connection_id": wh.get("connection_id"),
                    "district_lea_id": wh.get("district_lea_id") or lea_key,
                    "reader_friendly": True,
                    "governed_route": "edfi_warehouse",
                    "from_warehouse": True,
                    "from_extract": False,
                    "from_cache": True,
                    "live_pull": False,
                    "synced_at": wh.get("synced_at") or "",
                    "total_in_warehouse": wh.get("total_in_warehouse"),
                }
        except Exception:
            pass

    # 1) Local extract file next (legacy holding cell / partial pages)
    if use_local and not force_refresh and use_cache:
        extract = load_extract(
            backpack_id=resolved["pipeline_id"],
            intent=resolved["intent"],
            lea=lea_key,
            connection_id="",
        )
        if extract and extract.get("rows") is not None:
            return _payload_from_extract(resolved, extract, role=role, limit=limit)

    # 2) Cooldown: if rate-limited recently, try extract again or fail soft
    now = time.time()
    if now < _RATE_LIMIT_COOLDOWN_UNTIL and not force_refresh:
        extract = load_extract(
            backpack_id=resolved["pipeline_id"],
            intent=resolved["intent"],
            lea=lea_key,
        )
        if extract and extract.get("rows") is not None:
            out = _payload_from_extract(resolved, extract, role=role, limit=limit)
            out["summary"] = (
                str(out.get("summary") or "")
                + " (served during TEA cooldown)"
            ).strip()
            return out
        wait = int(max(1, _RATE_LIMIT_COOLDOWN_UNTIL - now))
        friendly = (
            f"TEA cooldown (~{wait}s). No local extract yet for this report. "
            "Wait, then use Refresh from ODS once."
        )
        return {
            "ok": False,
            "intent": resolved["intent"],
            "label": resolved["label"],
            "error": friendly,
            "rate_limited": True,
            "summary": friendly,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "cooldown_seconds": wait,
        }

    # 3) Live ODS pull
    query_params: dict[str, Any] = dict(params or {})
    if lea and str(lea).strip():
        query_params["district_lea_id"] = str(lea).strip()

    # Live pull size:
    # - schools refresh: full_lea=true → collect ALL matching schools for the LEA
    #   (dynamic district size; soft safety 2000 — not a fixed 25/50 cap)
    # - casual display: caller limit only
    intent_key = str(resolved["intent"] or "")
    # Schools force_refresh → warehouse full sync (not a thin page, not back-to-back UI spam).
    if force_refresh and intent_key in {"schools", "schools_directory"}:
        try:
            from services.edfi.warehouse_sync import run_full_schools_sync

            sync = run_full_schools_sync(lea_id=lea_key or lea)
            if sync.get("ok"):
                from services.edfi.warehouse_sync import schools_report_from_warehouse

                wh = schools_report_from_warehouse(
                    lea_id=str(sync.get("lea_id") or lea_key or lea),
                    limit=limit,
                )
                if wh and wh.get("ok"):
                    wh = dict(wh)
                    wh["summary"] = (
                        str(wh.get("summary") or "")
                        + " [warehouse sync completed — do not re-pull immediately]"
                    ).strip()
                    wh["live_pull"] = False
                    wh["warehouse_sync"] = {
                        "sync_run_id": sync.get("sync_run_id"),
                        "row_count": sync.get("row_count"),
                        "records_scanned": sync.get("records_scanned"),
                        "district_page_complete": sync.get("district_page_complete"),
                    }
                    return {
                        "ok": True,
                        "intent": resolved["intent"],
                        "label": resolved["label"],
                        "description": resolved["description"],
                        "pipeline_id": resolved["pipeline_id"],
                        "operation": resolved["operation"],
                        "backpack_operation": resolved["backpack_operation"],
                        "role": role,
                        **{k: wh[k] for k in wh if k not in {"ok"}},
                        "reader_friendly": True,
                    }
            # Rate-limited or failed sync: fall through to extract if any
            if sync.get("rate_limited"):
                extract = load_extract(
                    backpack_id=resolved["pipeline_id"],
                    intent=resolved["intent"],
                    lea=lea_key,
                )
                if extract and extract.get("rows") is not None:
                    out = _payload_from_extract(resolved, extract, role=role, limit=limit)
                    out["rate_limited"] = True
                    out["summary"] = (
                        str(out.get("summary") or "")
                        + " (TEA rate-limited during warehouse sync — showing last local data)"
                    ).strip()
                    return out
                return {
                    "ok": False,
                    "intent": resolved["intent"],
                    "label": resolved["label"],
                    "error": (
                        "TEA rate-limited during full warehouse sync. "
                        "Wait for the daily window (or several hours), then try one sync only."
                    ),
                    "rate_limited": True,
                    "summary": "Warehouse sync rate-limited",
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "warehouse_sync": sync,
                }
        except Exception as exc:
            # Fall through to legacy live query path
            query_params["_warehouse_sync_error"] = str(exc)[:160]

    if force_refresh and intent_key in {"schools", "schools_directory"}:
        query_params["full_lea"] = True
        live_limit = 2000
    elif force_refresh and intent_key in {"students"}:
        live_limit = 100
    else:
        live_limit = int(limit or 50)

    result = run_backpack_query(
        resolved["pipeline_id"],
        resolved["operation"],
        query_params or None,
        row_limit=live_limit,
        role=role,
    )

    if not result.get("ok"):
        err = result.get("error") or result.get("error_code") or "report_failed"
        if _is_rate_limited_error(err, result):
            try:
                from services.edfi.rate_limit_evidence import (
                    load_latest_evidence,
                    suggested_cooldown_seconds,
                )

                latest = load_latest_evidence() or {}
                cool = float(
                    latest.get("suggested_cooldown_sec")
                    or suggested_cooldown_seconds(latest.get("response_headers") or {}, default=60.0)
                )
            except Exception:
                cool = 60.0
            _RATE_LIMIT_COOLDOWN_UNTIL = time.time() + max(5.0, cool)
            # Fall back to extract if we have one
            extract = load_extract(
                backpack_id=resolved["pipeline_id"],
                intent=resolved["intent"],
                lea=lea_key or _resolve_lea_for_extract("", result),
            )
            if extract and extract.get("rows") is not None:
                out = _payload_from_extract(resolved, extract, role=role, limit=limit)
                out["summary"] = (
                    str(out.get("summary") or "")
                    + " (TEA rate-limited — showing last local extract)"
                ).strip()
                out["rate_limited"] = True
                return out
        friendly = _friendly_report_error(err, result)
        if _is_rate_limited_error(err, result):
            friendly = (
                "TEA ODS rate limit. No local extract available yet. "
                "Wait 1–2 minutes, then click Refresh from ODS once to build a local copy. "
                "After that, Report: schools reads local data without hitting TEA."
            )
        return {
            "ok": False,
            "intent": resolved["intent"],
            "label": resolved["label"],
            "pipeline_id": resolved["pipeline_id"],
            "operation": resolved["operation"],
            "backpack_operation": resolved["backpack_operation"],
            "role": role,
            "error": friendly,
            "error_raw": str(err),
            "rate_limited": _is_rate_limited_error(err, result),
            "summary": friendly,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "result": result,
        }

    columns = list(result.get("columns") or [])
    rows = list(result.get("rows") or [])
    summary = str(result.get("summary") or "")
    connection_id = str(result.get("connection_id") or "")
    resolved_lea = _resolve_lea_for_extract(lea, result)

    extract_path = ""
    extract_saved = False
    # Always persist schools/students after a successful live pull (holding cell).
    if resolved["intent"] in {"schools", "schools_directory", "students"} or force_refresh:
        try:
            from services.edfi.extract_store import canonical_extract_intent

            saved = save_extract(
                backpack_id=resolved["pipeline_id"],
                intent=canonical_extract_intent(resolved["intent"]),
                lea=resolved_lea,
                connection_id=connection_id,
                columns=columns,
                rows=rows,
                summary=summary,
                meta={
                    "operation": resolved["operation"],
                    "role": role,
                    "force_refresh": bool(force_refresh),
                    "full_lea": bool(query_params.get("full_lea")),
                    "lea_match_count": len(rows),
                    "district_page_complete": (
                        (result.get("edfi") or {}).get("district_page_complete")
                        if isinstance(result.get("edfi"), dict)
                        else result.get("district_page_complete")
                    ),
                    "records_scanned": result.get("edfi", {}).get("records_scanned")
                    if isinstance(result.get("edfi"), dict)
                    else result.get("records_scanned"),
                },
            )
            extract_path = str(saved)
            extract_saved = True
        except Exception as exc:
            summary = (summary + f" [extract save failed: {exc}]").strip()

    display_rows = rows[: int(limit)] if limit else rows
    if extract_saved:
        summary = (summary + " [live ODS pull — saved as local extract]").strip()
    return {
        "ok": True,
        "intent": resolved["intent"],
        "label": resolved["label"],
        "description": resolved["description"],
        "pipeline_id": resolved["pipeline_id"],
        "operation": resolved["operation"],
        "backpack_operation": resolved["backpack_operation"],
        "role": role,
        "summary": summary,
        "report_intent": result.get("report_intent") or resolved["intent"],
        "columns": columns,
        "rows": display_rows,
        "row_count": len(display_rows),
        "connection_id": connection_id,
        "district_lea_id": resolved_lea or result.get("district_lea_id"),
        "reader_friendly": True,
        "governed_route": result.get("governed_route") or "backpack_host",
        "from_extract": False,
        "from_cache": False,
        "live_pull": True,
        "extract_saved": extract_saved,
        "extract_path": extract_path,
        "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) if extract_saved else "",
    }
