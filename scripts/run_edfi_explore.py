from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.redaction import redact_edfi_result
from services.edfi.inventory import list_resources, profile_summary, read_preset, read_resource


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--connection-id", default="district-main", help="Connection profile id.")
    common.add_argument("--json", action="store_true", help="Print JSON output.")

    parser = argparse.ArgumentParser(
        description="Explore a profiled Ed-Fi ODS: health, resource browser, governed reads.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", parents=[common], help="Show saved capability profile summary.")

    resources = sub.add_parser("resources", parents=[common], help="Browse discovered resources.")
    resources.add_argument("--query", default="", help="Substring filter.")
    resources.add_argument("--namespace", default="", help="Namespace filter, e.g. ed-fi or TX.")
    resources.add_argument("--limit", type=int, default=50)
    resources.add_argument("--offset", type=int, default=0)

    for preset in ("schools", "students", "student_school_associations"):
        cmd = sub.add_parser(preset, parents=[common], help=f"Read {preset} with a governed limit.")
        cmd.add_argument("--limit", type=int, default=25)
        cmd.add_argument("--offset", type=int, default=0)

    get_cmd = sub.add_parser("get", parents=[common], help="Read any resource by name.")
    get_cmd.add_argument("resource", help="Resource path, e.g. ed-fi/schools or schools.")
    get_cmd.add_argument("--limit", type=int, default=25)
    get_cmd.add_argument("--offset", type=int, default=0)
    get_cmd.add_argument(
        "--no-district-scope",
        action="store_true",
        help="Do not apply district_lea_id filter from connection config.",
    )

    for preset in ("schools", "students", "student_school_associations"):
        preset_cmd = sub.choices[preset]
        preset_cmd.add_argument(
            "--no-district-scope",
            action="store_true",
            help="Do not apply district_lea_id filter from connection config.",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    connection_id = str(args.connection_id or "district-main").strip()

    if args.command == "health":
        result = profile_summary(connection_id)
    elif args.command == "resources":
        result = list_resources(
            connection_id,
            query=args.query,
            namespace=args.namespace,
            limit=args.limit,
            offset=args.offset,
        )
    elif args.command == "get":
        result = read_resource(
            connection_id,
            args.resource,
            limit=args.limit,
            offset=args.offset,
            apply_district_scope=not bool(getattr(args, "no_district_scope", False)),
        )
    else:
        result = read_preset(
            connection_id,
            args.command,
            limit=args.limit,
            offset=args.offset,
            apply_district_scope=not bool(getattr(args, "no_district_scope", False)),
        )

    if args.command in {"schools", "students", "student_school_associations", "get"}:
        resource = args.resource if args.command == "get" else None
        result = redact_edfi_result(
            result,
            operation=args.command,
            resource=resource,
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        ok = bool(result.get("ok"))
        print(f"connection_id: {connection_id}")
        print(f"ok: {ok}")
        if args.command == "health":
            print(f"health: {result.get('health')}")
            print(f"resource_count: {result.get('resource_count')}")
            print(f"catalog_truncated: {result.get('catalog_truncated')}")
        elif args.command == "resources":
            print(f"matches: {result.get('total_matches')}")
            for name in result.get("resources") or []:
                print(f"- {name}")
        else:
            print(f"resource: {result.get('resource')}")
            print(f"count: {result.get('count')}")
            if not ok:
                print(f"error: {result.get('error_code')} - {result.get('error')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())