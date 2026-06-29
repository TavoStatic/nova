#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import nova_core
from services.server_side_runtime import SERVER_SIDE_RUNTIME_SERVICE


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nova server-side runtime helper")
    sub = parser.add_subparsers(dest="command")

    status = sub.add_parser("status", help="Probe configured server-side/frontdoor endpoint")
    status.add_argument("--json", action="store_true", help="Emit JSON output")
    status.add_argument("--timeout-sec", type=float, default=2.5, help="HTTP probe timeout")

    render = sub.add_parser("render-apache", help="Render Apache reverse proxy vhost")
    render.add_argument("--server-name", default="localhost")
    render.add_argument("--listen-port", type=int, default=80)
    render.add_argument("--upstream-url", default="http://127.0.0.1:8080")

    return parser


def _status_payload(timeout_sec: float) -> dict:
    settings = nova_core.get_server_side_settings()
    return SERVER_SIDE_RUNTIME_SERVICE.status_payload(settings, timeout_sec=timeout_sec)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "render-apache":
        print(
            SERVER_SIDE_RUNTIME_SERVICE.render_apache_reverse_proxy_vhost(
                server_name=args.server_name,
                listen_port=args.listen_port,
                upstream_url=args.upstream_url,
            )
        )
        return 0

    payload = _status_payload(getattr(args, "timeout_sec", 2.5))
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        print("Nova server-side runtime: {}".format("OK" if payload.get("ok") else "FAIL"))
        print("mode={} frontdoor={} docker_enabled={}".format(payload.get("mode"), payload.get("frontdoor"), payload.get("docker_enabled")))
        print("target={}".format(payload.get("probe_target_base_url") or "(none)"))
        print("health={} ({})".format(payload.get("health_status"), payload.get("health_detail")))
        print("control={} ({})".format(payload.get("control_status_http"), payload.get("control_status_detail")))
        print("note={}".format(payload.get("server_side_runtime_note")))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
