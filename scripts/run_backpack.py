#!/usr/bin/env python3
"""Run generic backpack discovery, installation, status, and query operations."""
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

    print(json.dumps({"ok": True, "backpacks": list_backpack_summaries()}, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from services.backpack_host.query import backpack_status

    status = backpack_status(args.backpack_id)
    print(json.dumps(status, indent=2, default=str))
    return 0 if status.get("ok") else 1


def cmd_install(args: argparse.Namespace) -> int:
    from services.backpack_host.installer import BackpackInstaller

    settings_path = Path(args.settings)
    if not settings_path.is_file():
        raise SystemExit(f"settings file not found: {settings_path}")
    try:
        values = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"invalid settings JSON: {exc}") from exc
    if not isinstance(values, dict):
        raise SystemExit("settings JSON must be an object")

    backpack_dir = _backpack_dir(args.backpack_id)
    installer = BackpackInstaller()
    errors = installer.validate(backpack_dir, values)
    if errors:
        print(json.dumps({"ok": False, "phase": "validate", "errors": errors}, indent=2))
        return 1
    result = installer.apply(backpack_dir, values, runtime_root=_runtime_root())
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


def cmd_query(args: argparse.Namespace) -> int:
    from services.backpack_host.query import run_backpack_query

    params: dict[str, object] = {}
    if args.params:
        try:
            params = json.loads(args.params)
        except Exception as exc:
            raise SystemExit(f"invalid --params JSON: {exc}") from exc
        if not isinstance(params, dict):
            raise SystemExit("--params must be a JSON object")
    result = run_backpack_query(
        args.backpack_id,
        args.operation,
        params or None,
        row_limit=args.limit,
        role=args.role,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list").set_defaults(func=cmd_list)

    status = subparsers.add_parser("status")
    status.add_argument("backpack_id")
    status.set_defaults(func=cmd_status)

    install = subparsers.add_parser("install")
    install.add_argument("backpack_id")
    install.add_argument("--settings", required=True)
    install.set_defaults(func=cmd_install)

    query = subparsers.add_parser("query")
    query.add_argument("backpack_id")
    query.add_argument("operation")
    query.add_argument("--params", default="")
    query.add_argument("--limit", type=int, default=25)
    query.add_argument("--role", default="standard_user")
    query.set_defaults(func=cmd_query)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
