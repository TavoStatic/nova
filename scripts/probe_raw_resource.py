#!/usr/bin/env python3
"""
Probe a raw data connector ODS resource and dump the first record's JSON structure.

Used to diagnose client-side filter misses — shows the exact field names on
the wire so district_scope.item_matches_district() can be updated to match.

Usage:
  python scripts/probe_raw_resource.py sections
  python scripts/probe_raw_resource.py grading_periods
  python scripts/probe_raw_resource.py sections --limit 2
  python scripts/probe_raw_resource.py sections --connection my-conn
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make sure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.edfi.config import load_connection_config
from services.edfi.client import DataConnectorClient
from services.edfi.resources import get_page
from services.edfi.inventory import EXPLORE_PRESETS


def _resolve(resource_key: str) -> str:
    """Map preset key → data connector endpoint path."""
    paths = EXPLORE_PRESETS.get(resource_key)
    if paths:
        return paths[0]
    # Fall back to treating it as a literal path
    return resource_key


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump raw data connector ODS record structure.")
    ap.add_argument("resource", help="Resource key or path (e.g. sections, grading_periods)")
    ap.add_argument("--limit", type=int, default=1, help="Records to dump (default 1)")
    ap.add_argument("--connection", default="", help="Connection ID (default from settings)")
    ap.add_argument("--page-size", type=int, default=3, help="HTTP page size to request")
    args = ap.parse_args()

    # Resolve connection id
    if args.connection:
        conn_id = args.connection
    else:
        try:
            from services.edfi.warehouse_sync import load_backpack_settings, _connection_id
            conn_id = _connection_id(load_backpack_settings())
        except Exception:
            conn_id = "district-main"

    config = load_connection_config(conn_id)
    if config is None:
        print(f"ERROR: No connection config found for '{conn_id}'.")
        print("Run:  python scripts/run_backpack.py install edfi --settings <path>")
        sys.exit(1)

    endpoint = _resolve(args.resource)
    print(f"Connection : {conn_id}")
    print(f"Base URL   : {config.normalized_base_url()}")
    print(f"Endpoint   : {endpoint}")
    print(f"Requesting : page_size={args.page_size}, dumping first {args.limit} record(s)")
    print("-" * 70)

    client = DataConnectorClient(config)
    page = get_page(client, endpoint, limit=args.page_size, offset=0, audit=True)

    if not page.ok:
        print(f"FAILED  status={page.status_code}  error={page.error}  code={page.error_code}")
        print(f"URL     : {page.url}")
        sys.exit(1)

    print(f"HTTP {page.status_code}  records_in_page={page.count}  url={page.url}")
    print()

    if not page.items:
        print("(empty collection — 0 records returned by ODS)")
        sys.exit(0)

    for i, rec in enumerate(page.items[: args.limit], 1):
        print(f"── Record {i} ──────────────────────────────────────────────────────────")
        print(json.dumps(rec, indent=2, default=str))
        print()

        # Also print a flat key inventory for quick reference
        print("Top-level keys:", list(rec.keys()))
        nested = {k: list(v.keys()) for k, v in rec.items() if isinstance(v, dict)}
        if nested:
            print("Nested dicts:")
            for k, subkeys in nested.items():
                print(f"  {k}: {subkeys}")
        print()


if __name__ == "__main__":
    main()
