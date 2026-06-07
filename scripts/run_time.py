from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nova_core import tool_temporal_review


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="nova time",
        description="Temporal review surface for calendar pressure and scheduled work.",
    )
    parser.add_argument(
        "payload",
        nargs="?",
        default="",
        help="Optional JSON payload, .ics file path, or temporal review input.",
    )
    parser.add_argument("--json", action="store_true", help="Print raw JSON output.")
    args = parser.parse_args()

    payload = str(args.payload or "").strip()
    if payload and Path(payload).exists() and Path(payload).is_file():
        payload = str(Path(payload).resolve())

    result = tool_temporal_review(payload)
    if args.json:
        print(result)
        return 0

    try:
        parsed = json.loads(result)
    except Exception:
        print(result)
    else:
        print(json.dumps(parsed, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())