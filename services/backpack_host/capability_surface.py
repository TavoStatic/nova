from __future__ import annotations

"""
Backpack ↔ Nova nervous-system fusion.

Control-panel "green" is not enough. Nova must:
  - discover installed backpacks
  - know declared capabilities (what it may claim)
  - probe/scan those capabilities without thrashing TEA
  - carry teach rules so the AI does not invent beyond hold

Scan results land under runtime/backpacks/capability_scan.json and on control status.
"""

import json
import time
from pathlib import Path
from typing import Any

from services.nova_runtime_context import BASE_DIR, RUNTIME_DIR

SCAN_PATH = RUNTIME_DIR / "backpacks" / "capability_scan.json"
SCAN_SCHEMA = "nova.backpack_capability_scan.v1"


def _now() -> float:
    return time.time()


def _iso(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts if ts is not None else _now()))


def _probe(name: str, ok: bool, detail: str = "", *, severity: str = "info") -> dict[str, Any]:
    return {
        "probe": name,
        "ok": bool(ok),
        "detail": str(detail or "")[:400],
        "severity": severity if not ok else "info",
    }


def declared_capabilities_edfi() -> list[dict[str, Any]]:
    """What the edfi backpack may honestly offer in pipeline phase."""
    return [
        {
            "id": "edfi.connection_health_local",
            "label": "Connection health (local profile)",
            "live_ods": False,
            "tool": "edfi_explore",
            "action": "health",
        },
        {
            "id": "edfi.schools_local",
            "label": "Schools directory from local hold",
            "live_ods": False,
            "tool": "edfi_explore",
            "action": "schools",
            "source": "warehouse_or_extract",
        },
        {
            "id": "edfi.schools_sync",
            "label": "Deliberate full-LEA schools refresh from ODS",
            "live_ods": True,
            "rate_limit_risk": True,
            "tool": "edfi_explore",
            "action": "schools_refresh",
        },
        {
            "id": "edfi.resource_catalog_profile",
            "label": "Discovered resource names from saved profile",
            "live_ods": False,
            "tool": "edfi_explore",
            "action": "list_resources",
        },
        {
            "id": "edfi.teach_rules",
            "label": "Pipeline teach rules for Nova",
            "live_ods": False,
            "source": "brief_and_control_teach",
        },
    ]


def _schools_local_hold() -> dict[str, Any]:
    out: dict[str, Any] = {
        "has_extract": False,
        "has_warehouse": False,
        "row_count": 0,
        "lea": "",
        "source": "",
    }
    try:
        from services.edfi.extract_store import list_extracts

        for item in list_extracts("edfi"):
            if str(item.get("intent") or "") != "schools":
                continue
            n = int(item.get("row_count") or 0)
            if n > out["row_count"]:
                out["has_extract"] = True
                out["row_count"] = n
                out["lea"] = str(item.get("lea") or "")
                out["source"] = "extract"
    except Exception:
        pass
    try:
        from services.edfi.warehouse import warehouse_status
        from services.control_backpacks import ControlBackpacksService

        settings = ControlBackpacksService().ensure_settings("edfi", write=False)
        lea = str(settings.get("district_lea_id") or out.get("lea") or "")
        conn = str(settings.get("connection_id") or "district-main")
        # Try both raw and normalized LEA keys (state education data vs data connector format).
        lea_candidates = [lea]
        try:
            from services.backpack_host.scope_settings import format_lea_id

            if lea:
                lea_candidates.append(format_lea_id(lea))
            if out.get("lea"):
                lea_candidates.append(str(out.get("lea")))
                lea_candidates.append(format_lea_id(str(out.get("lea"))))
        except Exception:
            pass
        seen: set[str] = set()
        for candidate in lea_candidates:
            key = str(candidate or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            wh = warehouse_status(conn, lea_id=key)
            if wh.get("ok") and int(wh.get("schools_count") or 0) > 0:
                out["has_warehouse"] = True
                if int(wh.get("schools_count") or 0) >= int(out["row_count"] or 0):
                    out["row_count"] = int(wh.get("schools_count") or 0)
                    out["lea"] = key
                    out["source"] = "warehouse"
                break
    except Exception:
        pass
    return out


def _tool_registered() -> bool:
    try:
        from tools.registry import build_default_registry

        reg = build_default_registry()
        return reg.get("edfi_explore") is not None
    except Exception:
        try:
            from tools.edfi_tool import DataConnectorExploreTool

            return str(getattr(DataConnectorExploreTool, "name", "")) == "edfi_explore"
        except Exception:
            return False


def scan_backpack_fusion(backpack_id: str = "edfi", *, persist: bool = True) -> dict[str, Any]:
    """
    Probe/scan backpack fusion into Nova's nervous system.

    No live TEA multi-page pulls — only disk, registry, and local hold checks.
    """
    bid = str(backpack_id or "edfi").strip() or "edfi"
    probes: list[dict[str, Any]] = []
    started = _now()

    # 1) Package on disk
    backpack_dir = BASE_DIR / "backpacks" / bid
    pack_ok = (backpack_dir / "backpack.json").is_file()
    probes.append(
        _probe(
            "backpack_package",
            pack_ok,
            str(backpack_dir) if pack_ok else f"missing backpacks/{bid}/backpack.json",
            severity="failure",
        )
    )

    # 2) Settings / install
    settings: dict[str, Any] = {}
    enabled_flag = True
    teach: dict[str, Any] = {}
    settings_ok = False
    try:
        from services.control_backpacks import ControlBackpacksService

        svc = ControlBackpacksService()
        settings = svc.ensure_settings(bid, write=True)
        settings_ok = bool(settings.get("connection_id") and settings.get("base_url"))
        probes.append(
            _probe(
                "setup_settings",
                settings_ok,
                f"connection_id={settings.get('connection_id')} lea={settings.get('district_lea_id')}",
                severity="failure",
            )
        )
        enabled_flag = svc.is_enabled(bid)
        probes.append(
            _probe("control_enabled", enabled_flag, "on" if enabled_flag else "off", severity="warning")
        )
        teach = svc._teach_surface(backpack_dir) if pack_ok else {}
        probes.append(
            _probe(
                "teach_surface",
                bool(teach.get("rules")),
                f"rules={len(teach.get('rules') or [])}",
                severity="warning",
            )
        )
    except Exception as exc:
        probes.append(_probe("setup_settings", False, str(exc), severity="failure"))

    # 3) Host status (local profile)
    status: dict[str, Any] = {}
    try:
        from services.backpack_host.query import backpack_status

        status = backpack_status(bid)
        ready = str((status.get("readiness") or {}).get("state") or "") == "ready" or bool(
            status.get("profile_ok") and status.get("auth_ok")
        )
        probes.append(
            _probe(
                "backpack_status",
                ready,
                f"profile_ok={status.get('profile_ok')} auth_ok={status.get('auth_ok')} lea={status.get('district_lea_id')}",
                severity="failure",
            )
        )
    except Exception as exc:
        ready = False
        probes.append(_probe("backpack_status", False, str(exc), severity="failure"))

    # 4) Tool registered in Nova tool nervous system
    tool_ok = _tool_registered()
    probes.append(
        _probe("tool_edfi_explore_registered", tool_ok, "tools.registry DataConnectorExploreTool", severity="failure")
    )

    # 5) Host query path (local health only — no full ODS scan)
    health_ok = False
    try:
        from services.backpack_host.query import run_backpack_query

        health = run_backpack_query(bid, "connection_health", role="account_admin")
        if health.get("error") == "backpack_disabled":
            probes.append(_probe("host_query_health", False, "backpack_disabled", severity="warning"))
        else:
            health_ok = bool(health.get("ok")) or bool(status.get("profile_ok"))
            if health.get("auth_ok") is True or str(health.get("health") or "").lower() in {
                "ok",
                "watch",
            }:
                health_ok = True
            probes.append(
                _probe(
                    "host_query_health",
                    health_ok,
                    f"ok={health.get('ok')} health={health.get('health')}",
                    severity="failure",
                )
            )
    except Exception as exc:
        probes.append(_probe("host_query_health", False, str(exc), severity="failure"))

    # 6) Local schools hold (what Nova may claim)
    hold = _schools_local_hold()
    hold_ok = bool(hold.get("row_count"))
    probes.append(
        _probe(
            "local_schools_hold",
            hold_ok,
            f"source={hold.get('source')} rows={hold.get('row_count')} lea={hold.get('lea')}",
            severity="warning",
        )
    )

    # 7) Core readiness fusion
    core_ready = False
    try:
        from services.edfi.core_readiness import read_edfi_core_readiness

        core = read_edfi_core_readiness(str(settings.get("connection_id") or "district-main"))
        core_ready = bool(core.get("ready"))
        probes.append(
            _probe(
                "edfi_core_readiness",
                core_ready,
                f"ready={core_ready} backpack_op={core.get('backpack_operational')}",
                severity="warning",
            )
        )
    except Exception as exc:
        core = {}
        probes.append(_probe("edfi_core_readiness", False, str(exc), severity="warning"))

    # Capabilities Nova may claim right now
    caps = declared_capabilities_edfi()
    available: list[str] = []
    for cap in caps:
        cid = str(cap.get("id") or "")
        if cid == "edfi.connection_health_local" and (status.get("profile_ok") or health_ok):
            available.append(cid)
        elif cid == "edfi.schools_local" and hold_ok:
            available.append(cid)
        elif cid == "edfi.schools_sync" and settings_ok and enabled_flag:
            available.append(cid)  # allowed action, still rate-limit risk
        elif cid == "edfi.resource_catalog_profile" and int(status.get("resource_count") or 0) > 0:
            available.append(cid)
        elif cid == "edfi.teach_rules" and teach.get("rules"):
            available.append(cid)

    required_ok = all(
        p["ok"]
        for p in probes
        if p["probe"]
        in {
            "backpack_package",
            "setup_settings",
            "backpack_status",
            "tool_edfi_explore_registered",
            "host_query_health",
        }
    )
    fused_ok = required_ok and bool(available)

    scan = {
        "schema": SCAN_SCHEMA,
        "ok": fused_ok,
        "required_ok": required_ok,
        "backpack_id": bid,
        "scanned_at": _iso(),
        "scanned_at_epoch": started,
        "duration_ms": int((_now() - started) * 1000),
        "enabled": enabled_flag,
        "connection_id": str(settings.get("connection_id") or status.get("connection_id") or ""),
        "district_lea_id": str(
            settings.get("district_lea_id") or status.get("district_lea_id") or hold.get("lea") or ""
        ),
        "probes": probes,
        "probe_fail_count": sum(1 for p in probes if not p.get("ok")),
        "declared_capabilities": caps,
        "available_capability_ids": available,
        "local_hold": hold,
        "teach_rules": list((teach or {}).get("rules") or []),
        "teach_phase": str((teach or {}).get("phase") or "pipeline"),
        "status_snapshot": {
            "profile_ok": status.get("profile_ok"),
            "auth_ok": status.get("auth_ok"),
            "resource_count": status.get("resource_count"),
            "readiness": (status.get("readiness") or {}).get("state"),
        },
        "core_ready": core_ready,
        "nova_must_know": {
            "has_edfi_backpack": pack_ok,
            "may_answer_schools_from_local": hold_ok,
            "may_live_pull_schools": settings_ok and enabled_flag,
            "must_prefer_local": True,
            "must_not_invent": True,
            "pipeline_phase": True,
            "dashboard_phase": False,
        },
        "note": (
            "Fusion scan is local-first. Green control checklist is not enough — "
            "Nova must see available_capability_ids and teach_rules."
        ),
    }

    if persist:
        try:
            SCAN_PATH.parent.mkdir(parents=True, exist_ok=True)
            SCAN_PATH.write_text(json.dumps(scan, indent=2, ensure_ascii=True), encoding="utf-8")
            scan["scan_path"] = str(SCAN_PATH)
        except Exception as exc:
            scan["persist_error"] = str(exc)[:200]

    return scan


def load_last_scan() -> dict[str, Any] | None:
    if not SCAN_PATH.is_file():
        return None
    try:
        data = json.loads(SCAN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def get_fusion_status(*, max_age_sec: float = 300.0, force: bool = False) -> dict[str, Any]:
    """Return last scan if fresh; otherwise rescan (still no TEA full pull)."""
    if not force:
        last = load_last_scan()
        if last and last.get("scanned_at_epoch"):
            age = _now() - float(last.get("scanned_at_epoch") or 0)
            if age <= float(max_age_sec):
                last = dict(last)
                last["from_cache"] = True
                last["age_sec"] = int(age)
                return last
    scan = scan_backpack_fusion("edfi", persist=True)
    scan["from_cache"] = False
    return scan
