from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from pypdf import PdfReader


TABLE_RE = re.compile(r"Table:\s+(dbo\.[A-Z0-9_]+)(?:\s+\(([^)]*)\))?", re.I)
DATA_TYPE_RE = re.compile(
    r"^(?:bigint|binary|bit|char\(\d+\)|date|datetime|decimal\([^)]*\)|float|image|int|money|nchar\(\d+\)|ntext|numeric\([^)]*\)|nvarchar\([^)]*\)|real|smallint|text|time|tinyint|uniqueidentifier|varbinary\([^)]*\)|varchar\([^)]*\)|xml)$",
    re.I,
)
COLUMN_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text or "").replace("\xa0", " ").splitlines() if line.strip()]


def _extract_columns(section: str) -> list[dict[str, str]]:
    lines = _clean_lines(section)
    try:
        start = next(index for index, line in enumerate(lines) if line.lower() == "columns")
    except StopIteration:
        return []
    relevant = lines[start + 1 :]
    stop_markers = {"unique keys", "foreign keys", "indexes", "triggers"}
    for index, line in enumerate(relevant):
        if line.lower() in stop_markers:
            relevant = relevant[:index]
            break

    columns: list[dict[str, str]] = []
    for index in range(1, len(relevant)):
        data_type = relevant[index - 1]
        name = relevant[index]
        if not DATA_TYPE_RE.match(data_type) or not COLUMN_RE.match(name):
            continue
        description_lines: list[str] = []
        cursor = index - 2
        while cursor >= 0:
            line = relevant[cursor]
            if DATA_TYPE_RE.match(line) or COLUMN_RE.match(line) or line.lower() in {"description / attributes", "n", "data type", "name"}:
                break
            description_lines.append(line)
            cursor -= 1
        description = " ".join(reversed(description_lines)).strip()
        columns.append({"name": name, "data_type": data_type, "description": description})

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for column in columns:
        name = column["name"]
        if name in seen:
            continue
        seen.add(name)
        deduped.append(column)
    return deduped


def build_index(pdf_path: Path, *, content_start_page: int = 31) -> dict[str, Any]:
    reader = PdfReader(str(pdf_path))
    page_texts: list[tuple[int, str]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        if page_number < content_start_page:
            continue
        page_texts.append((page_number, page.extract_text() or ""))

    chunks: list[str] = []
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for page_number, text in page_texts:
        marker = f"\n[[PAGE {page_number}]]\n"
        chunks.append(marker)
        cursor += len(marker)
        offsets.append((cursor, page_number))
        chunks.append(text)
        cursor += len(text)
    body = "".join(chunks)

    matches = list(TABLE_RE.finditer(body))
    tables: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        table_name = match.group(1).strip()
        normalized = table_name.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        page = 0
        for offset, page_number in offsets:
            if offset <= start:
                page = page_number
            else:
                break
        section = body[start:end]
        title = str(match.group(2) or "").strip()
        tables.append(
            {
                "table": table_name,
                "title": title,
                "page": page,
                "columns": _extract_columns(section),
            }
        )

    return {
        "source": {
            "title": "eSchoolPLUS Data Dictionary",
            "source_file": str(pdf_path),
            "source_date": "2021-12-07",
            "producer": "Dataedo",
            "grounding_status": "vendor_dictionary_grounded",
            "verification_note": "Vendor schema reference only; confirm district live tables and columns through schema_inventory before treating as live database truth.",
            "page_count": len(reader.pages),
        },
        "table_count": len(tables),
        "tables": tables,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: import_eschoolplus_data_dictionary.py <pdf_path> <output_json>", file=sys.stderr)
        return 2
    pdf_path = Path(argv[1])
    output_path = Path(argv[2])
    payload = build_index(pdf_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"Wrote {payload['table_count']} tables to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
