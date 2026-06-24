from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from services.nova_temporal_service import TemporalEvent


# ---------------------------------------------------------------------------
# ICS line folding / unfolding
# ---------------------------------------------------------------------------

def _unfold_ics_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        if raw_line.startswith((" ", "\t")) and lines:
            lines[-1] = lines[-1] + raw_line[1:]
        else:
            lines.append(raw_line.rstrip("\r\n"))
    return lines


# ---------------------------------------------------------------------------
# Datetime helpers
# ---------------------------------------------------------------------------

def _parse_dt_parts(token: str) -> tuple[str, str]:
    head = token
    tzid = ""
    if ";" in token and ":" in token:
        head, _value = token.split(":", 1)
        if "TZID=" in head:
            tzid = head.split("TZID=", 1)[1].split(";", 1)[0].strip()
    return head, tzid


def _dt_from_ics(value: str, tzid: str = "") -> datetime | None:
    """Parse a compact ICS datetime string (YYYYMMDDTHHmmss[Z]) into a datetime."""
    text = value.strip()
    if not text:
        return None
    # Compact form: YYYYMMDDTHHmmss
    if "T" in text and "-" not in text[:8]:
        date_part, time_part = text.split("T", 1)
        if len(date_part) == 8 and date_part.isdigit():
            date_iso = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
            t = time_part.rstrip("Z")
            if len(t) >= 6:
                time_iso = f"{t[:2]}:{t[2:4]}:{t[4:6]}"
                tz_suffix = "+00:00" if time_part.endswith("Z") else ""
                text = f"{date_iso}T{time_iso}{tz_suffix}"
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# RRULE recurrence expansion
# ---------------------------------------------------------------------------

_RRULE_FREQ_DELTA = {
    "DAILY": timedelta(days=1),
    "WEEKLY": timedelta(weeks=1),
    "MONTHLY": None,   # handled specially
    "YEARLY": None,    # handled specially
}

_MAX_RECURRENCE_INSTANCES = 52  # cap to prevent runaway expansion


def _parse_rrule(rrule_text: str) -> dict[str, str]:
    """Parse RRULE value string into a dict of key→value pairs."""
    parts: dict[str, str] = {}
    for segment in str(rrule_text or "").split(";"):
        segment = segment.strip()
        if "=" in segment:
            k, v = segment.split("=", 1)
            parts[k.strip().upper()] = v.strip().upper()
    return parts


def _expand_rrule(
    dtstart: datetime,
    dtend: datetime | None,
    rrule_text: str,
    *,
    now: datetime | None = None,
) -> list[tuple[datetime, datetime | None]]:
    """
    Return a list of (start, end) pairs for the recurrence rule.
    Only returns instances that are >= now - 1 day (past instances are not useful).
    Caps at _MAX_RECURRENCE_INSTANCES total.
    """
    rule = _parse_rrule(rrule_text)
    freq = rule.get("FREQ", "")
    if freq not in _RRULE_FREQ_DELTA:
        return [(dtstart, dtend)]

    count_str = rule.get("COUNT", "")
    until_str = rule.get("UNTIL", "")
    interval_str = rule.get("INTERVAL", "1")
    interval = max(1, int(interval_str) if interval_str.isdigit() else 1)

    count_limit = int(count_str) if count_str.isdigit() else _MAX_RECURRENCE_INSTANCES
    until_dt: datetime | None = None
    if until_str:
        until_dt = _dt_from_ics(until_str)

    anchor = now or datetime.now(timezone.utc)
    lookback = anchor - timedelta(days=1)

    duration = (dtend - dtstart) if dtend is not None else None
    instances: list[tuple[datetime, datetime | None]] = []
    current = dtstart
    generated = 0

    while generated < min(count_limit, _MAX_RECURRENCE_INSTANCES):
        if until_dt is not None:
            cur_naive = current.replace(tzinfo=None) if current.tzinfo else current
            until_naive = until_dt.replace(tzinfo=None) if until_dt.tzinfo else until_dt
            if cur_naive > until_naive:
                break

        if current >= lookback or not instances:
            end_dt = (current + duration) if duration is not None else None
            instances.append((current, end_dt))

        # Advance to next occurrence
        if freq == "DAILY":
            current = current + timedelta(days=interval)
        elif freq == "WEEKLY":
            current = current + timedelta(weeks=interval)
        elif freq == "MONTHLY":
            month = current.month - 1 + interval
            year = current.year + month // 12
            month = month % 12 + 1
            day = min(current.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
            current = current.replace(year=year, month=month, day=day)
        elif freq == "YEARLY":
            try:
                current = current.replace(year=current.year + interval)
            except ValueError:
                # Feb 29 on non-leap year
                current = current.replace(year=current.year + interval, day=28)
        else:
            break

        generated += 1

    return instances if instances else [(dtstart, dtend)]


# ---------------------------------------------------------------------------
# Sidecar enrichment
# ---------------------------------------------------------------------------

def _sidecar_path(ics_path: Path) -> Path:
    """Return the enrichment sidecar JSON path for a given ICS file."""
    return ics_path.with_suffix(".enrichment.json")


def load_sidecar_enrichment(ics_path: str | Path) -> dict[str, dict[str, Any]]:
    """
    Load sidecar enrichment JSON keyed by event UID.
    Returns {} if the file doesn't exist or can't be parsed.
    Schema: { "<uid>": { "importance": 0.0-1.0, "dependency_risk": 0.0-1.0,
                         "stale_evidence": 0.0-1.0, "operator_context": 0.0-1.0 } }
    """
    path = _sidecar_path(Path(ics_path))
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return dict(raw) if isinstance(raw, dict) else {}
    except Exception:
        return {}


def save_sidecar_enrichment(ics_path: str | Path, enrichment: dict[str, dict[str, Any]]) -> None:
    """Persist sidecar enrichment JSON alongside the ICS file."""
    path = _sidecar_path(Path(ics_path))
    path.write_text(json.dumps(enrichment, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# ICS event parser
# ---------------------------------------------------------------------------

def _parse_ics_event(lines: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {"metadata": {}}
    for line in lines:
        if not line or ":" not in line:
            continue
        key_part, value = line.split(":", 1)
        key_upper = key_part.split(";", 1)[0].strip().upper()
        payload.setdefault("metadata", {})[key_upper.lower()] = value.strip()
        if key_upper == "SUMMARY":
            payload["title"] = value.strip()
        elif key_upper == "DTSTART":
            payload["start"] = value.strip()
            _head, tzid = _parse_dt_parts(line)
            if tzid:
                payload["timezone"] = tzid
        elif key_upper == "DTEND":
            payload["end"] = value.strip()
            _head, tzid = _parse_dt_parts(line)
            if tzid and not payload.get("timezone"):
                payload["timezone"] = tzid
        elif key_upper == "STATUS":
            payload["confidence"] = value.strip()
        elif key_upper == "DESCRIPTION":
            payload.setdefault("metadata", {})["description"] = value.strip()
        elif key_upper == "LOCATION":
            payload.setdefault("metadata", {})["location"] = value.strip()
        elif key_upper == "UID":
            payload.setdefault("metadata", {})["uid"] = value.strip()
        elif key_upper == "RRULE":
            payload.setdefault("metadata", {})["rrule"] = value.strip()
    return payload


# ---------------------------------------------------------------------------
# ICS serialisation (write back)
# ---------------------------------------------------------------------------

def _dt_to_ics(dt: datetime | None) -> str:
    """Serialize a datetime to compact ICS format YYYYMMDDTHHmmssZ."""
    if dt is None:
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _fold_ics_line(line: str) -> str:
    """Fold long ICS lines at 75 octets."""
    result = []
    while len(line.encode("utf-8")) > 75:
        result.append(line[:75])
        line = " " + line[75:]
    result.append(line)
    return "\r\n".join(result)


def serialize_events_to_ics(events: list[dict[str, Any]], *, prodid: str = "-//NOVA//Temporal Calendar//EN") -> str:
    """
    Serialize a list of event dicts back to ICS text.
    Each event dict must have: uid, title, start (ISO str), end (ISO str, optional),
    confidence (optional), and optionally metadata.description / metadata.location.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{prodid}",
    ]
    for ev in events:
        uid = str(ev.get("uid") or ev.get("metadata", {}).get("uid") or "")
        title = str(ev.get("title") or "Untitled")
        start_raw = str(ev.get("start") or "")
        end_raw = str(ev.get("end") or "")
        confidence = str(ev.get("confidence") or "CONFIRMED").upper()
        description = str((ev.get("metadata") or {}).get("description") or "").strip()
        location = str((ev.get("metadata") or {}).get("location") or "").strip()
        rrule = str((ev.get("metadata") or {}).get("rrule") or "").strip()

        # Parse start/end to canonical ICS form
        start_dt = _dt_from_ics(start_raw) if start_raw else None
        end_dt = _dt_from_ics(end_raw) if end_raw else None
        # Also accept ISO strings from the API layer
        if start_dt is None and start_raw:
            try:
                start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            except ValueError:
                pass
        if end_dt is None and end_raw:
            try:
                end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
            except ValueError:
                pass

        lines.append("BEGIN:VEVENT")
        if uid:
            lines.append(f"UID:{uid}")
        lines.append(f"SUMMARY:{title}")
        if start_dt:
            lines.append(f"DTSTART:{_dt_to_ics(start_dt)}")
        if end_dt:
            lines.append(f"DTEND:{_dt_to_ics(end_dt)}")
        lines.append(f"STATUS:{confidence}")
        if rrule:
            lines.append(f"RRULE:{rrule}")
        if description:
            lines.append(f"DESCRIPTION:{description}")
        if location:
            lines.append(f"LOCATION:{location}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ---------------------------------------------------------------------------
# Public parse API
# ---------------------------------------------------------------------------

def parse_ics_text(
    ics_text: str,
    *,
    source: str = "ics",
    enrichment: dict[str, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> list[TemporalEvent]:
    """
    Parse ICS text into TemporalEvent objects.
    Recurring events (RRULE) are expanded into individual instances.
    Enrichment signals are merged from the sidecar dict keyed by UID.
    """
    raw_events: list[TemporalEvent] = []
    current: list[str] = []
    in_event = False

    for line in _unfold_ics_lines(ics_text):
        token = line.strip().upper()
        if token == "BEGIN:VEVENT":
            in_event = True
            current = []
            continue
        if token == "END:VEVENT":
            if current:
                raw_events.append(
                    TemporalEvent.from_payload(_parse_ics_event(current), source=source)
                )
            in_event = False
            current = []
            continue
        if in_event:
            current.append(line)

    events: list[TemporalEvent] = []
    for event in raw_events:
        uid = str(event.metadata.get("uid") or "").strip()
        rrule = str(event.metadata.get("rrule") or "").strip()
        enrich: dict[str, Any] = dict((enrichment or {}).get(uid) or {}) if uid else {}

        if rrule and event.start is not None:
            # Expand recurrence
            instances = _expand_rrule(event.start, event.end, rrule, now=now)
            for idx, (inst_start, inst_end) in enumerate(instances):
                payload = event.to_dict()
                payload["start"] = inst_start.isoformat()
                if inst_end is not None:
                    payload["end"] = inst_end.isoformat()
                # Tag recurring instances so they can be de-duplicated
                payload.setdefault("metadata", {})["recurrence_index"] = idx
                payload.setdefault("metadata", {})["rrule"] = rrule
                payload.update(enrich)
                events.append(TemporalEvent.from_payload(payload, source=source))
        else:
            if enrich:
                payload = event.to_dict()
                payload.update(enrich)
                events.append(TemporalEvent.from_payload(payload, source=source))
            else:
                events.append(event)

    return events


def parse_ics_file(
    path: str | Path,
    *,
    source: str = "ics",
    now: datetime | None = None,
) -> list[TemporalEvent]:
    """
    Parse an ICS file, automatically loading its enrichment sidecar if present.
    """
    file_path = Path(path)
    enrichment = load_sidecar_enrichment(file_path)
    return parse_ics_text(
        file_path.read_text(encoding="utf-8"),
        source=source,
        enrichment=enrichment,
        now=now,
    )


def normalize_calendar_event(record: dict[str, Any], *, source: str = "ics") -> TemporalEvent:
    return TemporalEvent.from_payload(dict(record or {}), source=source)


# ---------------------------------------------------------------------------
# Calendar event CRUD helpers (used by HTTP endpoints)
# ---------------------------------------------------------------------------

def read_calendar_events(ics_path: str | Path) -> list[dict[str, Any]]:
    """
    Read all events from an ICS file as raw dicts (not TemporalEvent objects).
    Merges enrichment sidecar data for UI editing.
    """
    file_path = Path(ics_path)
    enrichment = load_sidecar_enrichment(file_path)

    if not file_path.exists():
        return []

    raw_events: list[dict[str, Any]] = []
    current: list[str] = []
    in_event = False

    for line in _unfold_ics_lines(file_path.read_text(encoding="utf-8")):
        token = line.strip().upper()
        if token == "BEGIN:VEVENT":
            in_event = True
            current = []
            continue
        if token == "END:VEVENT":
            if current:
                raw_events.append(_parse_ics_event(current))
            in_event = False
            current = []
            continue
        if in_event:
            current.append(line)

    result: list[dict[str, Any]] = []
    for ev in raw_events:
        uid = str((ev.get("metadata") or {}).get("uid") or "").strip()
        enrich = dict(enrichment.get(uid) or {}) if uid else {}
        merged = dict(ev)
        merged["uid"] = uid
        merged["importance"] = float(enrich.get("importance") or 0.0)
        merged["dependency_risk"] = float(enrich.get("dependency_risk") or 0.0)
        merged["stale_evidence"] = float(enrich.get("stale_evidence") or 0.0)
        merged["operator_context"] = float(enrich.get("operator_context") or 0.0)
        result.append(merged)

    return result


def write_calendar_event(
    ics_path: str | Path,
    event: dict[str, Any],
) -> str:
    """
    Add or update a single event in the ICS file. Returns the UID.
    Enrichment fields are written to the sidecar JSON.
    """
    import uuid as _uuid

    file_path = Path(ics_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    uid = str(event.get("uid") or "").strip()
    if not uid:
        uid = f"nova-{_uuid.uuid4().hex}"

    # Load existing events
    existing = read_calendar_events(file_path) if file_path.exists() else []
    # Remove existing entry with same UID (will re-add updated)
    existing = [e for e in existing if str(e.get("uid") or "") != uid]
    # Build updated event entry
    updated = dict(event)
    updated["uid"] = uid
    existing.append(updated)

    # Write ICS
    file_path.write_text(
        serialize_events_to_ics(existing),
        encoding="utf-8",
    )

    # Write enrichment sidecar
    enrichment = load_sidecar_enrichment(file_path)
    enrichment[uid] = {
        "importance": float(event.get("importance") or 0.0),
        "dependency_risk": float(event.get("dependency_risk") or 0.0),
        "stale_evidence": float(event.get("stale_evidence") or 0.0),
        "operator_context": float(event.get("operator_context") or 0.0),
    }
    save_sidecar_enrichment(file_path, enrichment)

    return uid


def delete_calendar_event(ics_path: str | Path, uid: str) -> bool:
    """
    Remove an event by UID from the ICS file and its enrichment sidecar.
    Returns True if the event was found and removed.
    """
    file_path = Path(ics_path)
    if not file_path.exists():
        return False

    existing = read_calendar_events(file_path)
    before = len(existing)
    remaining = [e for e in existing if str(e.get("uid") or "") != uid]

    if len(remaining) == before:
        return False

    file_path.write_text(
        serialize_events_to_ics(remaining),
        encoding="utf-8",
    )

    enrichment = load_sidecar_enrichment(file_path)
    enrichment.pop(uid, None)
    save_sidecar_enrichment(file_path, enrichment)

    return True
