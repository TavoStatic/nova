#!/usr/bin/env python3
"""
Backpack host CLI — list, install, status, query.

Examples:
  python scripts/run_backpack.py list
  python scripts/run_backpack.py grants edfi --role viewer
  python scripts/run_backpack.py status edfi --role account_admin
  python scripts/run_backpack.py install edfi --settings path/to/settings.json
  python scripts/run_backpack.py install edfi --settings path.json --skip-profile
  python scripts/run_backpack.py query edfi connection_health --role standard_user
  python scripts/run_backpack.py query edfi list_schools --role standard_user --lea 031901
  python scripts/run_backpack.py probe-lea edfi --lea 031901 --limit 3
  python scripts/run_backpack.py report edfi schools --role standard_user --limit 10
  python scripts/run_backpack.py report edfi schools --refresh --limit 50
  python scripts/run_backpack.py report edfi health --role viewer
  python scripts/run_backpack.py rate-limit-evidence
  python scripts/run_backpack.py warehouse-status edfi
  python scripts/run_backpack.py warehouse-sync edfi
  python scripts/run_backpack.py warehouse-sync edfi --force

Legacy: data_sources/edfi_bisd is the old BISD-named lane. New installs use backpacks/edfi.
TEA keys are usually statewide; --lea / allowed_lea_ids are Nova policy filters.
Reports return reader-friendly rows for dashboards (not raw ODS JSON).
Rate-limit evidence is captured passively on real 429s — do not flood TEA to force samples.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _runtime_root() -> Path:
    from services.nova_runtime_context import RUNTIME_DIR

    return Path(RUNTIME_DIR)


def _backpack_dir(backpack_id: str) -> Path:
    path = ROOT / "backpacks" / backpack_id
    if not (path / "backpack.json").is_file():
        raise SystemExit(f"backpack not found: {path}")
    return path


def cmd_list(_: argparse.Namespace) -> int:
    from services.backpack_host.query import list_backpack_summaries

    rows = list_backpack_summaries()
    print(json.dumps({"ok": True, "backpacks": rows}, indent=2))
    return 0


def cmd_grants(args: argparse.Namespace) -> int:
    from services.backpack_host.grant_enforcer import operation_summary

    summary = operation_summary(_backpack_dir(args.backpack_id), args.role)
    print(json.dumps(summary, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from services.backpack_host.query import backpack_status, run_backpack_query

    status = backpack_status(args.backpack_id)
    # Also attempt connection_health under the given role (shows grant + readiness)
    health = run_backpack_query(
        args.backpack_id,
        "connection_health",
        role=args.role,
    )
    print(json.dumps({"status": status, "connection_health": health}, indent=2, default=str))
    return 0 if health.get("ok") or status.get("ok") is not False else 1


def cmd_install(args: argparse.Namespace) -> int:
    from services.backpack_host.installer import BackpackInstaller

    backpack_dir = _backpack_dir(args.backpack_id)
    settings_path = Path(args.settings)
    if not settings_path.is_file():
        raise SystemExit(f"settings file not found: {settings_path}")
    try:
        values = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"invalid settings JSON: {exc}") from exc
    if not isinstance(values, dict):
        raise SystemExit("settings JSON must be an object")

    installer = BackpackInstaller()
    errors = installer.validate(backpack_dir, values)
    if errors:
        print(json.dumps({"ok": False, "phase": "validate", "errors": errors}, indent=2))
        return 1

    apply_result = installer.apply(backpack_dir, values, runtime_root=_runtime_root())
    if not apply_result.get("ok"):
        print(json.dumps({"ok": False, "phase": "apply", "result": apply_result}, indent=2))
        return 1

    if args.skip_profile:
        print(
            json.dumps(
                {
                    "ok": True,
                    "phase": "apply_only",
                    "apply": apply_result,
                    "note": "Skipped install_steps (--skip-profile). Re-run without flag to profile ODS.",
                },
                indent=2,
            )
        )
        return 0

    steps = installer.run_all_install_steps(
        backpack_dir, values, runtime_root=_runtime_root()
    )
    ok = all(bool(s.get("ok")) for s in steps) if steps else True
    print(
        json.dumps(
            {"ok": ok, "phase": "install", "apply": apply_result, "steps": steps},
            indent=2,
            default=str,
        )
    )
    return 0 if ok else 1


def cmd_query(args: argparse.Namespace) -> int:
    from services.backpack_host.query import run_backpack_query

    params: dict = {}
    if args.params:
        try:
            params = json.loads(args.params)
        except Exception as exc:
            raise SystemExit(f"invalid --params JSON: {exc}") from exc
        if not isinstance(params, dict):
            raise SystemExit("--params must be a JSON object")
    if getattr(args, "lea", None):
        params["district_lea_id"] = str(args.lea).strip()
    result = run_backpack_query(
        args.backpack_id,
        args.operation,
        params or None,
        row_limit=args.limit,
        role=args.role,
        skip_grant_check=bool(args.skip_grants),
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


def cmd_report(args: argparse.Namespace) -> int:
    from services.backpack_host.reports import list_report_intents, run_backpack_report

    if args.intent in {"list", "intents", "help", ""}:
        print(
            json.dumps(
                {"ok": True, "intents": list_report_intents(args.backpack_id)},
                indent=2,
            )
        )
        return 0
    force = bool(getattr(args, "refresh", False))
    report = run_backpack_report(
        args.intent,
        backpack_id=args.backpack_id,
        role=args.role,
        lea=str(args.lea or ""),
        limit=args.limit,
        force_refresh=force,
        prefer_local=not force,
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


def cmd_rate_limit_evidence(args: argparse.Namespace) -> int:
    """Show passively captured TEA rate-limit evidence (no live flood probe)."""
    from services.edfi.rate_limit_evidence import evidence_summary, load_recent_events

    summary = evidence_summary()
    if getattr(args, "recent", False):
        summary["recent_events"] = load_recent_events(limit=int(args.limit or 20))
    print(json.dumps(summary, indent=2, default=str))
    if not summary.get("latest"):
        print(
            "\nNo rate-limit events yet. Use a normal report/refresh once; "
            "if TEA returns 429, evidence is written under runtime/edfi/rate_limit_evidence/.\n"
            "Do NOT send requests until you force a 429 — that can look like abuse.",
            file=sys.stderr,
        )
    return 0


def cmd_fusion_scan(args: argparse.Namespace) -> int:
    """Probe backpack ↔ Nova nervous system (local-first; no full TEA scan)."""
    from services.backpack_host.capability_surface import scan_backpack_fusion

    scan = scan_backpack_fusion(
        str(getattr(args, "backpack_id", None) or "edfi"),
        persist=True,
    )
    print(json.dumps(scan, indent=2, default=str))
    return 0 if scan.get("ok") else 1


def cmd_warehouse_status(args: argparse.Namespace) -> int:
    from services.edfi.warehouse import warehouse_status
    from services.edfi.warehouse_sync import due_for_scheduled_sync, load_backpack_settings, _lea_id

    settings = load_backpack_settings()
    lea = str(args.lea or _lea_id(settings) or "").strip()
    conn = str(args.connection_id or settings.get("connection_id") or "district-main").strip()
    status = warehouse_status(conn, lea_id=lea)
    schedule = due_for_scheduled_sync(connection_id=conn, lea_id=lea, settings=settings)
    print(json.dumps({"warehouse": status, "schedule": schedule}, indent=2, default=str))
    return 0 if status.get("ok") or status.get("exists") else 1


def cmd_warehouse_sync(args: argparse.Namespace) -> int:
    from services.edfi.warehouse_sync import maybe_run_scheduled_warehouse_sync, run_full_schools_sync

    force = bool(getattr(args, "force", False))
    if force:
        result = run_full_schools_sync(lea_id=str(args.lea or "").strip())
        result["forced"] = True
    else:
        result = maybe_run_scheduled_warehouse_sync(force=False)
    print(json.dumps(result, indent=2, default=str))
    if force:
        return 0 if result.get("ok") else 1
    return 0 if result.get("ok") is not False else 1


def cmd_probe_lea(args: argparse.Namespace) -> int:
    """Small, rate-limit-friendly check that an LEA returns schools (Nova-filtered)."""
    from services.backpack_host.query import run_backpack_query
    from services.backpack_host.scope_settings import format_lea_id, lea_identity_key

    lea = str(args.lea or "").strip()
    if not lea:
        raise SystemExit("--lea is required")
    key = lea_identity_key(lea)
    result = run_backpack_query(
        args.backpack_id,
        "list_schools",
        {"district_lea_id": lea},
        row_limit=int(args.limit or 3),
        role=args.role,
        skip_grant_check=bool(args.skip_grants),
    )
    items = list(result.get("items") or result.get("rows") or [])
    summary = {
        "ok": bool(result.get("ok")),
        "backpack_id": args.backpack_id,
        "requested_lea": lea,
        "normalized_lea": format_lea_id(lea) if key is not None else lea,
        "school_items": len(items),
        "error": result.get("error") or result.get("error_code"),
        "note": (
            "Scoped probe only. TEA keys are usually statewide; "
            "empty results usually mean wrong LEA or rate limit — not a single-district key."
        ),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary["ok"] and len(items) > 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nova backpack host CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List discovered backpacks")
    p_list.set_defaults(func=cmd_list)

    p_grants = sub.add_parser("grants", help="Show operation grants for a role")
    p_grants.add_argument("backpack_id")
    p_grants.add_argument("--role", default="standard_user")
    p_grants.set_defaults(func=cmd_grants)

    p_status = sub.add_parser("status", help="Backpack status + connection_health")
    p_status.add_argument("backpack_id")
    p_status.add_argument("--role", default="account_admin")
    p_status.set_defaults(func=cmd_status)

    p_install = sub.add_parser("install", help="Validate/apply settings and run install_steps")
    p_install.add_argument("backpack_id")
    p_install.add_argument(
        "--settings",
        required=True,
        help="JSON file matching settings_schema.json fields",
    )
    p_install.add_argument(
        "--skip-profile",
        action="store_true",
        help="Write settings only; skip ODS profile / LEA verify steps",
    )
    p_install.set_defaults(func=cmd_install)

    p_query = sub.add_parser("query", help="Run a pipeline operation via backpack host")
    p_query.add_argument("backpack_id")
    p_query.add_argument("operation")
    p_query.add_argument("--role", default="standard_user")
    p_query.add_argument("--limit", type=int, default=None)
    p_query.add_argument("--params", default="", help="JSON object of operation params")
    p_query.add_argument(
        "--lea",
        default="",
        help="District LEA for this query (031901 or 31901). Must be allowed by install scope.",
    )
    p_query.add_argument(
        "--skip-grants",
        action="store_true",
        help="Bypass operations.json grants (debug only)",
    )
    p_query.set_defaults(func=cmd_query)

    p_probe = sub.add_parser(
        "probe-lea",
        help="Small schools probe for one LEA (avoids unscoped statewide scans)",
    )
    p_probe.add_argument("backpack_id")
    p_probe.add_argument("--lea", required=True, help="LEA to probe (e.g. 031901)")
    p_probe.add_argument("--limit", type=int, default=3)
    p_probe.add_argument("--role", default="account_admin")
    p_probe.add_argument("--skip-grants", action="store_true")
    p_probe.set_defaults(func=cmd_probe_lea)

    p_report = sub.add_parser(
        "report",
        help="User-request report (schools|health|students) → shaped rows",
    )
    p_report.add_argument("backpack_id")
    p_report.add_argument(
        "intent",
        nargs="?",
        default="list",
        help="schools | health | students | list",
    )
    p_report.add_argument("--role", default="standard_user")
    p_report.add_argument("--lea", default="", help="Optional LEA filter (031901 or 31901)")
    p_report.add_argument("--limit", type=int, default=25)
    p_report.add_argument(
        "--refresh",
        action="store_true",
        help="Force live ODS pull and save local extract (rate-limit risk)",
    )
    p_report.set_defaults(func=cmd_report)

    p_rl = sub.add_parser(
        "rate-limit-evidence",
        help="Show passive TEA 429 evidence (headers/cooldown). Does NOT probe TEA.",
    )
    p_rl.add_argument(
        "--recent",
        action="store_true",
        help="Include recent events from the JSONL log",
    )
    p_rl.add_argument("--limit", type=int, default=20, help="Recent event count with --recent")
    p_rl.set_defaults(func=cmd_rate_limit_evidence)

    p_fuse = sub.add_parser(
        "fusion-scan",
        help="Probe backpack fusion into Nova nervous system (capabilities Nova may claim)",
    )
    p_fuse.add_argument("backpack_id", nargs="?", default="edfi")
    p_fuse.set_defaults(func=cmd_fusion_scan)

    p_ws = sub.add_parser(
        "warehouse-status",
        help="Local Ed-Fi SQLite warehouse status + daily schedule gate",
    )
    p_ws.add_argument("backpack_id", nargs="?", default="edfi")
    p_ws.add_argument("--lea", default="")
    p_ws.add_argument("--connection-id", default="")
    p_ws.set_defaults(func=cmd_warehouse_status)

    p_wsync = sub.add_parser(
        "warehouse-sync",
        help="Full LEA schools pull into warehouse (respects schedule unless --force)",
    )
    p_wsync.add_argument("backpack_id", nargs="?", default="edfi")
    p_wsync.add_argument("--lea", default="")
    p_wsync.add_argument(
        "--force",
        action="store_true",
        help="Ignore daily schedule / min gap (rate-limit risk if repeated)",
    )
    p_wsync.set_defaults(func=cmd_warehouse_sync)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
