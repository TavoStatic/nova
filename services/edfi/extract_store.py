from __future__ import annotations

"""
Local extract store for Ed-Fi (and similar backpack bridges).

Model:
  - Live TEA/ODS pulls are expensive and rate-limited.
  - Nova pulls on an explicit refresh (or scheduled later), cleans/shapes rows,
    and saves them under runtime/.
  - User reports/dashboards read the local extract first.

This is the durable "better way to pull data" for a bridge — not live ODS on every click.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from services.nova_runtime_context import RUNTIME_DIR

logger = logging.getLogger(__name__)

EXTRACTS_ROOT = RUNTIME_DIR / "edfi" / "extracts"

# Canonical intent keys for extract files (aliases map into these).
_INTENT_ALIASES: dict[str, str] = {
    "school": "schools",
    "schools_directory": "schools",
    "list_schools": "schools",
    "show_schools": "schools",
    "student": "students",
    "students_directory": "students",
    "list_students": "students",
}


def canonical_extract_intent(intent: str) -> str:
    key = str(intent or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _INTENT_ALIASES.get(key, key or "unknown")


def _safe_token(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return (text or "default")[:80]


def extract_path(
    *,
    backpack_id: str,
    intent: str,
    lea: str = "",
    connection_id: str = "",
) -> Path:
    intent_key = canonical_extract_intent(intent)
    lea_key = _safe_token(lea or "default_lea")
    # Always park under default_conn so load/save match regardless of connection_id.
    # connection_id is still stored inside the JSON payload for diagnostics.
    conn_key = "default_conn"
    return (
        EXTRACTS_ROOT
        / _safe_token(backpack_id or "edfi")
        / conn_key
        / lea_key
        / f"{_safe_token(intent_key)}.json"
    )


def save_extract(
    *,
    backpack_id: str,
    intent: str,
    lea: str,
    connection_id: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    summary: str = "",
    meta: dict[str, Any] | None = None,
) -> Path:
    intent_key = canonical_extract_intent(intent)
    path = extract_path(
        backpack_id=backpack_id,
        intent=intent_key,
        lea=lea,
        connection_id="",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "nova.edfi_extract.v1",
        "backpack_id": backpack_id,
        "intent": intent_key,
        "lea": lea,
        "connection_id": str(connection_id or ""),
        "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "synced_at_epoch": time.time(),
        "columns": list(columns or []),
        "rows": list(rows or []),
        "row_count": len(rows or []),
        "summary": str(summary or ""),
        "meta": dict(meta or {}),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    logger.info(
        "edfi_extract_saved path=%s intent=%s lea=%s rows=%s",
        path,
        intent_key,
        lea,
        payload["row_count"],
    )
    return path


def _read_extract_file(path: Path, *, max_age_sec: float | None) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if max_age_sec is not None:
        try:
            age = time.time() - float(data.get("synced_at_epoch") or 0)
            if age > float(max_age_sec):
                data = dict(data)
                data["stale"] = True
                data["age_sec"] = age
        except Exception:
            pass
    data["extract_path"] = str(path)
    return data


def load_extract(
    *,
    backpack_id: str,
    intent: str,
    lea: str = "",
    connection_id: str = "",  # kept for API compat; not used for path
    max_age_sec: float | None = None,
) -> dict[str, Any] | None:
    del connection_id  # path is connection-agnostic
    intent_key = canonical_extract_intent(intent)
    bid = _safe_token(backpack_id or "edfi")

    candidates: list[Path] = [
        extract_path(backpack_id=bid, intent=intent_key, lea=lea, connection_id=""),
    ]
    if lea:
        candidates.append(
            extract_path(backpack_id=bid, intent=intent_key, lea="", connection_id="")
        )

    for path in candidates:
        data = _read_extract_file(path, max_age_sec=max_age_sec)
        if data is not None:
            return data

    # Fallback: any connection folder under this backpack (legacy layouts).
    root = EXTRACTS_ROOT / bid
    if not root.is_dir():
        return None
    intent_file = f"{_safe_token(intent_key)}.json"
    lea_key = _safe_token(lea or "default_lea")
    matches: list[Path] = []
    for path in root.rglob(intent_file):
        matches.append(path)
    # Prefer matching LEA segment in path
    if lea:
        preferred = [p for p in matches if lea_key in p.parts]
        if preferred:
            matches = preferred
    if not matches:
        return None
    # Newest wins
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return _read_extract_file(matches[0], max_age_sec=max_age_sec)


def list_extracts(backpack_id: str = "edfi") -> list[dict[str, Any]]:
    root = EXTRACTS_ROOT / _safe_token(backpack_id or "edfi")
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        out.append(
            {
                "intent": data.get("intent"),
                "lea": data.get("lea"),
                "connection_id": data.get("connection_id"),
                "synced_at": data.get("synced_at"),
                "row_count": data.get("row_count"),
                "path": str(path),
            }
        )
    return out
