from __future__ import annotations

from pathlib import Path
from typing import Any

from services.nova_temporal_service import TemporalEvent


def _unfold_ics_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        if raw_line.startswith((" ", "\t")) and lines:
            lines[-1] = lines[-1] + raw_line[1:]
        else:
            lines.append(raw_line.rstrip("\r\n"))
    return lines


def _parse_dt_parts(token: str) -> tuple[str, str]:
    head = token
    tzid = ""
    if ";" in token and ":" in token:
        head, _value = token.split(":", 1)
        if "TZID=" in head:
            tzid = head.split("TZID=", 1)[1].split(";", 1)[0].strip()
    return head, tzid


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
    return payload


def parse_ics_text(ics_text: str, *, source: str = "ics") -> list[TemporalEvent]:
    events: list[TemporalEvent] = []
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
                events.append(TemporalEvent.from_payload(_parse_ics_event(current), source=source))
            in_event = False
            current = []
            continue
        if in_event:
            current.append(line)
    return events


def parse_ics_file(path: str | Path, *, source: str = "ics") -> list[TemporalEvent]:
    file_path = Path(path)
    return parse_ics_text(file_path.read_text(encoding="utf-8"), source=source)


def normalize_calendar_event(record: dict[str, Any], *, source: str = "ics") -> TemporalEvent:
    return TemporalEvent.from_payload(dict(record or {}), source=source)

