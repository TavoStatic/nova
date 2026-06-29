#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.server_side_runtime import SERVER_SIDE_RUNTIME_SERVICE


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reverse proxy frontdoor helper")
    parser.add_argument("--server-name", default="localhost")
    parser.add_argument("--listen-port", type=int, default=80)
    parser.add_argument("--upstream-url", default="http://127.0.0.1:8080")
    parser.add_argument("--json", action="store_true", help="Emit JSON envelope")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    vhost = SERVER_SIDE_RUNTIME_SERVICE.render_apache_reverse_proxy_vhost(
        server_name=args.server_name,
        listen_port=args.listen_port,
        upstream_url=args.upstream_url,
    )
    if args.json:
        payload = {
            "ok": True,
            "server_name": args.server_name,
            "listen_port": args.listen_port,
            "upstream_url": args.upstream_url,
            "vhost": vhost,
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        print(vhost)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
