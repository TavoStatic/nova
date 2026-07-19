#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.nova_setup_wizard import render_setup_report, run_setup_wizard


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nova setup wizard: check/install/verify host dependencies.")
    parser.add_argument("--root", default=str(ROOT), help="Nova package root")
    parser.add_argument("--check-only", action="store_true", help="Do not install; only check")
    parser.add_argument("--skip-ollama", action="store_true", help="Skip Ollama install/checks")
    parser.add_argument("--skip-models", action="store_true", help="Skip Ollama model pulls")
    parser.add_argument("--skip-webui", action="store_true", help="Skip webui start/health proof")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip smoke-base")
    parser.add_argument("--webui-port", type=int, default=18088)
    parser.add_argument("--report", default="", help="Optional report path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = run_setup_wizard(
        Path(args.root),
        install=not bool(args.check_only),
        include_ollama=not bool(args.skip_ollama),
        include_models=not bool(args.skip_models),
        include_webui=not bool(args.skip_webui),
        include_smoke=not bool(args.skip_smoke),
        webui_port=int(args.webui_port),
        report_path=args.report or None,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_setup_report(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
