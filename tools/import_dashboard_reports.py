from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TABLE_PATTERN = re.compile(
    r"\b(?:from|join|update|into)\s+(?:\[?dbo\]?\.)?\[?([A-Za-z][A-Za-z0-9_]+)\]?",
    re.IGNORECASE,
)
PROGRAM_PATTERN = re.compile(
    r"PROGRAM_ID\s*=\s*['\"]?([0-9A-Za-z_]+)['\"]?.{0,120}?FIELD_NUMBER\s*=\s*['\"]?([0-9A-Za-z_]+)['\"]?",
    re.IGNORECASE | re.DOTALL,
)
FIELD_PROGRAM_PATTERN = re.compile(
    r"FIELD_NUMBER\s*=\s*['\"]?([0-9A-Za-z_]+)['\"]?.{0,120}?PROGRAM_ID\s*=\s*['\"]?([0-9A-Za-z_]+)['\"]?",
    re.IGNORECASE | re.DOTALL,
)
SQL_HINT_PATTERN = re.compile(r"\b(select|from|join|where|group by|order by)\b", re.IGNORECASE)

DEFAULT_EXTENSIONS = {".php", ".twig", ".js"}
SKIP_PARTS = {"archived_reports", "__pycache__"}
SKIP_SUFFIXES = {".log", ".json", ".xlsx", ".xls", ".pdf", ".txt"}


def _module_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    return rel.parts[0] if len(rel.parts) > 1 else root.name


def _normalize_table(table: str) -> str:
    raw = str(table or "").strip().strip("[]")
    if not raw:
        return ""
    upper = raw.upper()
    return f"dbo.{upper}"


def _scan_file(path: Path, known_tables: set[str] | None = None) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tables": [], "population_filters": [], "sql_hint_count": 0}

    found_tables = sorted({
        normalized
        for match in TABLE_PATTERN.finditer(text)
        for normalized in [_normalize_table(match.group(1))]
        if normalized and normalized.upper() not in {"dbo.SELECT", "dbo.WHERE"}
    })
    if known_tables:
        tables = [table for table in found_tables if table.upper() in known_tables]
        unknown_tables = [table for table in found_tables if table.upper() not in known_tables]
    else:
        tables = found_tables
        unknown_tables = []
    population_filters = []
    for match in PROGRAM_PATTERN.finditer(text):
        population_filters.append({"program_id": match.group(1), "field_number": match.group(2)})
    for match in FIELD_PROGRAM_PATTERN.finditer(text):
        population_filters.append({"program_id": match.group(2), "field_number": match.group(1)})

    unique_filters = []
    seen_filters = set()
    for item in population_filters:
        key = (item["program_id"], item["field_number"])
        if key not in seen_filters:
            seen_filters.add(key)
            unique_filters.append(item)

    return {
        "ok": True,
        "tables": tables,
        "unknown_table_like_tokens": unknown_tables[:20],
        "population_filters": unique_filters,
        "sql_hint_count": len(SQL_HINT_PATTERN.findall(text)),
    }


def _load_known_tables(vendor_dictionary: Path | None) -> set[str]:
    if vendor_dictionary is None or not vendor_dictionary.exists():
        return set()
    data = json.loads(vendor_dictionary.read_text(encoding="utf-8"))
    return {
        str(item.get("table") or "").upper()
        for item in data.get("tables") or []
        if isinstance(item, dict) and item.get("table")
    }


def build_report_index(reports_root: Path, vendor_dictionary: Path | None = None) -> dict[str, Any]:
    known_tables = _load_known_tables(vendor_dictionary)
    files = []
    module_tables: dict[str, Counter[str]] = defaultdict(Counter)
    module_filters: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    module_file_counts: Counter[str] = Counter()
    table_counts: Counter[str] = Counter()
    filter_counts: Counter[tuple[str, str]] = Counter()

    for path in sorted(reports_root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.relative_to(reports_root).parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.suffix.lower() not in DEFAULT_EXTENSIONS:
            continue

        scan = _scan_file(path, known_tables=known_tables)
        module = _module_name(reports_root, path)
        module_file_counts[module] += 1
        rel_path = str(path.relative_to(reports_root)).replace("\\", "/")
        tables = scan.get("tables") or []
        population_filters = scan.get("population_filters") or []
        for table in tables:
            table_counts[table] += 1
            module_tables[module][table] += 1
        for item in population_filters:
            key = (str(item.get("program_id") or ""), str(item.get("field_number") or ""))
            filter_counts[key] += 1
            module_filters[module][key] += 1
        if tables or population_filters or int(scan.get("sql_hint_count") or 0) > 0:
            files.append({
                "path": rel_path,
                "module": module,
                "tables": tables,
                "population_filters": population_filters,
                "unknown_table_like_tokens": scan.get("unknown_table_like_tokens") or [],
                "sql_hint_count": int(scan.get("sql_hint_count") or 0),
            })

    modules = []
    for module in sorted(module_file_counts):
        modules.append({
            "name": module,
            "file_count": int(module_file_counts[module]),
            "tables": [
                {"table": table, "file_count": count}
                for table, count in module_tables[module].most_common(20)
            ],
            "population_filters": [
                {"program_id": program_id, "field_number": field_number, "file_count": count}
                for (program_id, field_number), count in module_filters[module].most_common(20)
            ],
        })

    return {
        "source": {
            "kind": "dashboard_predefined_reports",
            "root": str(reports_root),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "notes": [
                "Read-only catalog of existing dashboard report code.",
                "Use this as report-pattern grounding, not as permission to run raw SQL.",
                "Generated Excel archives, logs, token files, PDFs, and JSON debug files are excluded.",
                "Grounded table counts are filtered against the vendor dictionary when one is supplied.",
            ],
            "vendor_dictionary_filter": str(vendor_dictionary) if vendor_dictionary else "",
        },
        "summary": {
            "module_count": len(modules),
            "file_count": len(files),
            "table_count": len(table_counts),
            "population_filter_count": len(filter_counts),
        },
        "top_tables": [
            {"table": table, "file_count": count}
            for table, count in table_counts.most_common(40)
        ],
        "top_population_filters": [
            {"program_id": program_id, "field_number": field_number, "file_count": count}
            for (program_id, field_number), count in filter_counts.most_common(40)
        ],
        "modules": modules,
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Index existing dashboard report definitions for a Nova data lane.")
    parser.add_argument("reports_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--vendor-dictionary", type=Path, default=None)
    args = parser.parse_args()

    index = build_report_index(args.reports_root.resolve(), args.vendor_dictionary.resolve() if args.vendor_dictionary else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(
        f"Wrote {args.output} "
        f"({index['summary']['module_count']} modules, {index['summary']['file_count']} files, "
        f"{index['summary']['table_count']} tables)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
