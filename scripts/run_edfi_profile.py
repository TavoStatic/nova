from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.edfi import run_self_profile


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe an Ed-Fi ODS: authenticate, discover metadata, save capability profile.",
    )
    parser.add_argument("--connection-id", default="district-main", help="Connection profile id.")
    parser.add_argument("--base-url", default="", help="District Ed-Fi base URL.")
    parser.add_argument("--client-id", default="", help="OAuth client id.")
    parser.add_argument("--client-secret", default="", help="OAuth client secret.")
    parser.add_argument(
        "--no-save-config",
        action="store_true",
        help="Do not persist credentials to runtime/edfi/connections.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full result payload as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = run_self_profile(
        connection_id=args.connection_id,
        base_url=args.base_url,
        client_id=args.client_id,
        client_secret=args.client_secret,
        save_config=not args.no_save_config,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        health = result.get("health") or {}
        print(f"connection_id: {result.get('connection_id')}")
        print(f"ok: {result.get('ok')}")
        print(f"status: {health.get('status')}")
        if result.get("profile_path"):
            print(f"profile_path: {result.get('profile_path')}")
        issues = health.get("issues") or []
        for issue in issues:
            print(f"issue: {issue.get('code')} - {issue.get('detail')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())