"""
log_session.py
--------------
Developer tool: append a session entry to docs/ledger/session_log.jsonl
and regenerate NOVA_LEDGER.md.

Usage:
  python scripts/log_session.py \
    --tool claude-cowork \
    --session-id "my_session_id" \
    --modules "services/sock_service.py,static/control.js" \
    --changes "Added X,Fixed Y,Built Z" \
    --tests 5 \
    --docs-added "docs/NEW_DOC.md" \
    --docs-updated "docs/DOC_OWNERSHIP.md" \
    --notes "Optional free-text note"

Or import and call log_session() directly from another script.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

NOVA_ROOT = Path(__file__).parent.parent
SESSION_LOG = NOVA_ROOT / "docs" / "ledger" / "session_log.jsonl"
GENERATE_SCRIPT = NOVA_ROOT / "scripts" / "generate_nova_ledger.py"


def log_session(
    *,
    tool: str,
    session_id: str = "",
    modules_touched: list[str] | None = None,
    changes: list[str] | None = None,
    tests_added: int = 0,
    docs_added: list[str] | None = None,
    docs_updated: list[str] | None = None,
    notes: str = "",
    entry_date: str | None = None,
    regenerate: bool = True,
) -> dict:
    entry = {
        "date": entry_date or str(date.today()),
        "source": "developer",
        "tool": tool,
        "session_id": session_id,
        "modules_touched": modules_touched or [],
        "changes": changes or [],
        "tests_added": tests_added,
        "docs_added": docs_added or [],
        "docs_updated": docs_updated or [],
        "notes": notes,
    }
    SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SESSION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"Session logged: {entry['date']} / {tool} / {session_id or '(no id)'}")
    if regenerate:
        result = subprocess.run(
            [sys.executable, str(GENERATE_SCRIPT)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(result.stdout.strip())
        else:
            print(f"Ledger regeneration failed:\n{result.stderr}", file=sys.stderr)
    return entry


def _parse_list(s: str) -> list[str]:
    return [item.strip() for item in s.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Log a developer session to the Nova ledger")
    parser.add_argument("--tool", required=True, help="Tool used (claude-cowork, cursor, etc.)")
    parser.add_argument("--session-id", default="", help="Session identifier")
    parser.add_argument("--modules", default="", help="Comma-separated modules touched")
    parser.add_argument("--changes", default="", help="Comma-separated change descriptions")
    parser.add_argument("--tests", type=int, default=0, help="Number of tests added")
    parser.add_argument("--docs-added", default="", help="Comma-separated docs added")
    parser.add_argument("--docs-updated", default="", help="Comma-separated docs updated")
    parser.add_argument("--notes", default="", help="Free-text notes")
    parser.add_argument("--date", default=None, help="Override date (YYYY-MM-DD)")
    parser.add_argument("--no-regenerate", action="store_true", help="Skip ledger regeneration")
    args = parser.parse_args()

    log_session(
        tool=args.tool,
        session_id=args.session_id,
        modules_touched=_parse_list(args.modules),
        changes=_parse_list(args.changes),
        tests_added=args.tests,
        docs_added=_parse_list(args.docs_added),
        docs_updated=_parse_list(args.docs_updated),
        notes=args.notes,
        entry_date=args.date,
        regenerate=not args.no_regenerate,
    )


if __name__ == "__main__":
    main()
