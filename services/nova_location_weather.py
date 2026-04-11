from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import math
import os
import re
import time
from typing import Callable, Optional
from urllib.parse import quote

import requests


DEVICE_LOCATION_MAX_AGE_SEC = 300.0

BROWNSVILLE_LAT = 25.9017
BROWNSVILLE_LON = -97.4975
_LOCATION_HINT_COORDS = {
    "78521": (BROWNSVILLE_LAT, BROWNSVILLE_LON),
}
_LOCATION_HINT_LABELS = {
    "78521": "Brownsville, TX",
}


def weather_source_host(*, policy_web_fn: Callable[[], dict]) -> Optional[str]:
    allow_domains = [str(d).strip().lower() for d in (policy_web_fn().get("allow_domains") or []) if str(d).strip()]
    for preferred in ("api.weather.gov", "wttr.in"):
        for domain in allow_domains:
            if domain == preferred or domain.endswith("." + preferred):
                return preferred
    return None


def weather_unavailable_message() -> str:
    return (
        "I can access websites, but I don't yet have a reliable structured weather source configured. "
        "I cannot honestly claim weather results from raw weather.com pages. "
        "Add a source like 'policy allow api.weather.gov' and then use 'weather <location-or-lat,lon>'."
    )


def weather_response_style(*, policy_web_fn: Callable[[], dict]) -> str:
    try:
        style = str((policy_web_fn().get("weather_response_style") or "concise")).strip().lower()
        if style in {"concise", "tool"}:
            return style
    except Exception:
        pass
    return "concise"


def format_weather_output(
    label: str,
    summary: str,
    *,
    weather_response_style_fn: Callable[[], str],
) -> str:
    normalized_summary = re.sub(r"\s+", " ", (summary or "").strip())
    normalized_summary = re.sub(r"^(?:weather|forecast)\s+for\s+[^:]+:\s*", "", normalized_summary, flags=re.I)
    normalized_label = (label or "").strip() or "this location"

    aliases = {
        "brownsville": "Brownsville, TX",
        "brownsville tx": "Brownsville, TX",
        "brownsville, tx": "Brownsville, TX",
    }
    label_key = re.sub(r"\s+", " ", normalized_label.lower()).strip()
    normalized_label = aliases.get(label_key, normalized_label)

    style = weather_response_style_fn()
    if style == "tool":
        return f"Forecast for {normalized_label}: {normalized_summary}"
    return f"{normalized_label}: {normalized_summary}"


def runtime_device_backend_provider() -> dict:
    platform_supported = os.name == "nt"
    winsdk_installed = False
    if platform_supported:
        try:
            winsdk_installed = bool(
                importlib.util.find_spec("winsdk.windows.devices.geolocation")
                or importlib.util.find_spec("winsdk")
            )
        except Exception:
            winsdk_installed = False
    available = platform_supported and winsdk_installed
    if available:
        message = "Windows geolocation fallback is ready."
    elif platform_supported:
        message = "Windows geolocation fallback requires the winsdk package."
    else:
        message = "Windows geolocation fallback is only available on Windows hosts."
    return {
        "name": "windows_geolocator",
        "platform_supported": platform_supported,
        "winsdk_installed": winsdk_installed,
        "available": available,
        "message": message,
    }


def coerce_bounded_float(value, *, minimum: float, maximum: float) -> Optional[float]:
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    if number < minimum or number > maximum:
        return None
    return number


def coerce_optional_metric(value) -> Optional[float]:
    try:
        if value in {None, ""}:
            return None
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def normalize_source_timestamp(value) -> float:
    now = time.time()
    try:
        number = float(value)
    except Exception:
        return now
    if not math.isfinite(number) or number <= 0:
        return now
    if number > 1_000_000_000_000:
        number /= 1000.0
    return min(number, now)


def format_runtime_coords(lat: float, lon: float) -> str:
    return f"{lat:.5f},{lon:.5f}"


def device_location_status_payload(
    snapshot: Optional[dict],
    *,
    max_age_sec: float = DEVICE_LOCATION_MAX_AGE_SEC,
    runtime_device_backend_provider_fn: Callable[[], dict],
) -> dict:
    backend_provider = runtime_device_backend_provider_fn()
    if not isinstance(snapshot, dict):
        return {
            "available": False,
            "status": "unavailable",
            "stale": False,
            "message": "No live device location fix is available.",
            "backend_provider": backend_provider,
        }

    lat = coerce_bounded_float(snapshot.get("lat"), minimum=-90.0, maximum=90.0)
    lon = coerce_bounded_float(snapshot.get("lon"), minimum=-180.0, maximum=180.0)
    if lat is None or lon is None:
        return {
            "available": False,
            "status": "invalid",
            "stale": False,
            "message": "Live device location data is invalid.",
            "backend_provider": backend_provider,
        }

    captured_ts = normalize_source_timestamp(snapshot.get("captured_ts"))
    age_sec = max(0.0, time.time() - captured_ts)
    stale = age_sec > max(0.0, float(max_age_sec))
    accuracy_m = coerce_optional_metric(snapshot.get("accuracy_m"))
    speed_mps = coerce_optional_metric(snapshot.get("speed_mps"))
    heading_deg = coerce_optional_metric(snapshot.get("heading_deg"))
    altitude_m = coerce_optional_metric(snapshot.get("altitude_m"))
    coords_text = format_runtime_coords(lat, lon)
    source = str(snapshot.get("source") or "unknown").strip().lower() or "unknown"

    payload = {
        "available": True,
        "status": "stale" if stale else "live",
        "stale": stale,
        "message": "Live device location is active." if not stale else "Live device location is stale.",
        "lat": lat,
        "lon": lon,
        "coords_text": coords_text,
        "source": source,
        "permission_state": str(snapshot.get("permission_state") or "").strip().lower(),
        "captured_ts": captured_ts,
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(captured_ts)),
        "age_sec": round(age_sec, 1),
        "backend_provider": backend_provider,
    }
    if accuracy_m is not None:
        payload["accuracy_m"] = round(max(0.0, accuracy_m), 1)
    if speed_mps is not None:
        payload["speed_mps"] = round(max(0.0, speed_mps), 2)
    if heading_deg is not None:
        payload["heading_deg"] = round(heading_deg % 360.0, 1)
    if altitude_m is not None:
        payload["altitude_m"] = round(altitude_m, 1)
    return payload


def runtime_device_location_payload(
    *,
    device_location_file,
    max_age_sec: float = DEVICE_LOCATION_MAX_AGE_SEC,
    device_location_status_payload_fn: Callable[..., dict],
    runtime_device_backend_provider_fn: Callable[[], dict],
) -> dict:
    try:
        if not device_location_file.exists():
            return device_location_status_payload_fn(None, max_age_sec=max_age_sec)
        raw = json.loads(device_location_file.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {
            "available": False,
            "status": "error",
            "stale": False,
            "message": "Failed to read live device location state.",
            "backend_provider": runtime_device_backend_provider_fn(),
        }
    return device_location_status_payload_fn(raw, max_age_sec=max_age_sec)


def set_runtime_device_location(
    payload: dict,
    *,
    device_location_file,
    atomic_write_json_fn: Callable[[object, dict], None],
    runtime_device_location_payload_fn: Callable[..., dict],
) -> tuple[bool, str, dict]:
    data = payload if isinstance(payload, dict) else {}
    lat = coerce_bounded_float(data.get("lat"), minimum=-90.0, maximum=90.0)
    lon = coerce_bounded_float(data.get("lon"), minimum=-180.0, maximum=180.0)
    if lat is None or lon is None:
        return False, "device_location_invalid", runtime_device_location_payload_fn()

    snapshot = {
        "lat": lat,
        "lon": lon,
        "accuracy_m": coerce_optional_metric(data.get("accuracy_m")),
        "speed_mps": coerce_optional_metric(data.get("speed_mps")),
        "heading_deg": coerce_optional_metric(data.get("heading_deg")),
        "altitude_m": coerce_optional_metric(data.get("altitude_m")),
        "source": str(data.get("source") or "browser_watch").strip().lower() or "browser_watch",
        "permission_state": str(data.get("permission_state") or "").strip().lower(),
        "captured_ts": normalize_source_timestamp(data.get("captured_ts")),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        device_location_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json_fn(device_location_file, snapshot)
    except Exception:
        return False, "device_location_write_failed", runtime_device_location_payload_fn()
    return True, "device_location_updated", runtime_device_location_payload_fn()


def clear_runtime_device_location(*, device_location_file, runtime_device_location_payload_fn: Callable[..., dict]) -> dict:
    try:
        device_location_file.unlink(missing_ok=True)
    except Exception:
        pass
    return runtime_device_location_payload_fn()


def resolve_windows_device_coords(
    timeout_sec: float = 8.0,
    *,
    runtime_device_backend_provider_fn: Callable[[], dict],
) -> Optional[dict]:
    provider = runtime_device_backend_provider_fn()
    if not provider.get("available"):
        return None
    try:
        wdg = importlib.import_module("winsdk.windows.devices.geolocation")
    except Exception:
        return None

    async def _read_position() -> Optional[dict]:
        locator = wdg.Geolocator()
        try:
            locator.desired_accuracy = wdg.PositionAccuracy.HIGH
        except Exception:
            pass
        try:
            position = await asyncio.wait_for(locator.get_geoposition_async(), timeout=float(timeout_sec))
        except Exception:
            return None
        try:
            point = position.coordinate.point.position
            return {
                "lat": float(point.latitude),
                "lon": float(point.longitude),
                "accuracy_m": coerce_optional_metric(getattr(position.coordinate, "accuracy", None)),
                "speed_mps": coerce_optional_metric(getattr(position.coordinate, "speed", None)),
                "heading_deg": coerce_optional_metric(getattr(position.coordinate, "heading", None)),
                "altitude_m": coerce_optional_metric(getattr(point, "altitude", None)),
                "source": "windows_geolocator",
                "permission_state": "granted",
                "captured_ts": time.time(),
            }
        except Exception:
            return None

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_read_position())
    except Exception:
        return None
    finally:
        try:
            loop.close()
        except Exception:
            pass


def resolve_current_device_coords(
    *,
    max_age_sec: float = DEVICE_LOCATION_MAX_AGE_SEC,
    runtime_device_location_payload_fn: Callable[..., dict],
    resolve_windows_device_coords_fn: Callable[..., Optional[dict]],
    set_runtime_device_location_fn: Callable[[dict], tuple[bool, str, dict]],
) -> Optional[tuple[float, float]]:
    live = runtime_device_location_payload_fn(max_age_sec=max_age_sec)
    if live.get("available") and not live.get("stale"):
        return (float(live.get("lat")), float(live.get("lon")))

    windows_fix = resolve_windows_device_coords_fn()
    if isinstance(windows_fix, dict):
        ok, _msg, updated = set_runtime_device_location_fn(windows_fix)
        if ok and updated.get("available"):
            return (float(updated.get("lat")), float(updated.get("lon")))
    return None


def mentions_location_phrase(text: str) -> bool:
    low = (text or "").lower()
    return any(phrase in low for phrase in [
        "location",
        "locaiton",
        "physical location",
        "physical locaiton",
    ])


def parse_lat_lon(text: str) -> Optional[tuple[float, float]]:
    match = re.search(r"(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)", (text or ""))
    if not match:
        return None
    try:
        lat = float(match.group(1))
        lon = float(match.group(2))
    except Exception:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return (lat, lon)


def coords_for_location_hint(location: str) -> Optional[tuple[float, float]]:
    loc = (location or "").strip().lower()
    if not loc:
        return None
    parsed = parse_lat_lon(loc)
    if parsed:
        return parsed
    if loc in _LOCATION_HINT_COORDS:
        return _LOCATION_HINT_COORDS[loc]
    if "brownsville" in loc:
        return (BROWNSVILLE_LAT, BROWNSVILLE_LON)
    return None


def coords_from_saved_location(
    *,
    read_core_state_fn: Callable[[object], dict],
    default_statefile,
    mem_audit_fn: Callable[[str], str],
    get_saved_location_text_fn: Callable[[], str],
) -> Optional[tuple[float, float]]:
    try:
        state = read_core_state_fn(default_statefile)
        coords = state.get("location_coords") if isinstance(state, dict) else None
        if isinstance(coords, dict):
            lat = float(coords.get("lat"))
            lon = float(coords.get("lon"))
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                return (lat, lon)
    except Exception:
        pass

    try:
        audit_out = mem_audit_fn("location coordinates lat lon")
        payload = json.loads(audit_out) if audit_out else {}
        results = payload.get("results") if isinstance(payload, dict) else []
        for row in results:
            preview = (row.get("preview") or "").strip()
            parsed = parse_lat_lon(preview)
            if parsed:
                return parsed
    except Exception:
        return None

    try:
        saved_text = get_saved_location_text_fn()
        if saved_text:
            return coords_for_location_hint(saved_text)
    except Exception:
        return None
    return None


def get_saved_location_text(
    *,
    read_core_state_fn: Callable[[object], dict],
    default_statefile,
    normalize_location_preview_fn: Callable[[str], str],
    mem_audit_fn: Callable[[str], str],
) -> str:
    try:
        state = read_core_state_fn(default_statefile)
        raw = state.get("location_text") if isinstance(state, dict) else ""
        cleaned = normalize_location_preview_fn(str(raw or ""))
        if cleaned:
            return cleaned
    except Exception:
        pass

    try:
        audit_out = mem_audit_fn("location")
        payload = json.loads(audit_out) if audit_out else {}
        results = payload.get("results") if isinstance(payload, dict) else []
        for row in results:
            preview = normalize_location_preview_fn((row.get("preview") or "").strip())
            low = preview.lower()
            if not preview:
                continue
            if low.startswith("name:"):
                continue
            if "coordinates" in low:
                continue
            if parse_lat_lon(preview):
                continue
            return preview
    except Exception:
        pass
    return ""


def set_location_text(
    value: str,
    *,
    input_source: str = "typed",
    normalize_location_preview_fn: Callable[[str], str],
    set_core_state_fn: Callable[[object, str, object], None],
    default_statefile,
    mem_add_fn: Callable[[str, str, str], None],
) -> str:
    cleaned = normalize_location_preview_fn(value)
    if not cleaned:
        return "Usage: my location is <place>"

    try:
        set_core_state_fn(default_statefile, "location_text", cleaned)
    except Exception:
        pass

    try:
        mem_add_fn("profile", input_source, f"location: {cleaned}")
    except Exception:
        pass

    try:
        mem_add_fn("user_fact", input_source, f"My location is {cleaned}")
    except Exception:
        pass

    try:
        coords = coords_for_location_hint(cleaned)
        if coords:
            lat, lon = coords
            set_core_state_fn(default_statefile, "location_coords", {"lat": lat, "lon": lon})
    except Exception:
        pass

    return f"Saved current location: {cleaned}"


def extract_location_fact(text: str, *, normalize_location_preview_fn: Callable[[str], str]) -> str:
    raw = (text or "").strip()
    if not raw or "?" in raw:
        return ""

    patterns = [
        r"^\s*(?:my|your)(?:\s+(?:current|physical))?\s+location\s+is\s+(.+?)\s*[.!?]*$",
        r"^\s*i\s+am\s+located\s+in\s+(.+?)\s*[.!?]*$",
        r"^\s*you\s+are\s+located\s+in\s+(.+?)\s*[.!?]*$",
    ]
    for pattern in patterns:
        match = re.match(pattern, raw, flags=re.I)
        if match:
            return normalize_location_preview_fn(match.group(1))
    return ""


def store_location_fact_reply(
    text: str,
    *,
    input_source: str = "typed",
    pending_action: Optional[dict] = None,
    set_location_text_fn: Callable[..., str],
    extract_location_fact_fn: Callable[[str], str],
) -> str:
    action = pending_action if isinstance(pending_action, dict) else {}
    if (
        str(action.get("kind") or "") == "weather_lookup"
        and str(action.get("status") or "") == "awaiting_location"
    ):
        return ""

    location_value = extract_location_fact_fn(text)
    if not location_value:
        return ""

    try:
        set_location_text_fn(location_value, input_source=input_source)
    except Exception:
        return ""
    return "Noted."


def store_declarative_fact_outcome(
    text: str,
    *,
    input_source: str = "typed",
    is_declarative_info_fn: Callable[[str], bool],
    mem_should_store_fn: Callable[[str], bool],
    mem_add_fn: Callable[[str, str, str], None],
    classify_store_fact_outcome_fn: Callable[..., Optional[dict[str, object]]],
) -> Optional[dict[str, object]]:
    fact_text = str(text or "").strip()
    if not fact_text or not is_declarative_info_fn(fact_text):
        return None

    storage_performed = False
    try:
        if mem_should_store_fn(fact_text):
            mem_add_fn("fact", input_source, fact_text)
            storage_performed = True
    except Exception:
        storage_performed = False

    return classify_store_fact_outcome_fn(
        {
            "fact_text": fact_text,
            "store_fact_kind": "declarative_ack",
            "user_commitment": "implied",
            "memory_kind": "fact",
        },
        fact_text,
        source="declarative",
        storage_performed=storage_performed,
    )


def store_declarative_fact_reply(
    text: str,
    *,
    input_source: str = "typed",
    store_declarative_fact_outcome_fn: Callable[..., Optional[dict[str, object]]],
    render_reply_fn: Callable[[Optional[dict]], str],
) -> str:
    outcome = store_declarative_fact_outcome_fn(text, input_source=input_source)
    if not isinstance(outcome, dict):
        return ""
    return render_reply_fn(outcome)


def is_saved_location_weather_query(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text_fn(text).strip(" .,!?")
    if not normalized:
        return False
    return normalized in {
        "weather",
        "weather now",
        "weather current",
        "weather today",
        "current weather",
        "what's the weather",
        "what is the weather",
        "what is the weather now",
        "what's the weather now",
    }


def weather_for_saved_location(
    *,
    get_saved_location_text_fn: Callable[[], str],
    tool_weather_fn: Callable[[str], str],
) -> str:
    saved_location = str(get_saved_location_text_fn() or "").strip()
    if not saved_location:
        return ""
    try:
        return str(tool_weather_fn(saved_location) or "")
    except Exception:
        return ""


def extract_weather_source_host(tool_result: str) -> str:
    text = str(tool_result or "").strip()
    if not text:
        return ""
    match = re.search(r"\[source:\s*([^\]]+)\]", text, flags=re.I)
    if not match:
        return ""
    return str(match.group(1) or "").strip().lower()


def weather_location_label(
    weather_mode: str,
    location_value: str = "",
    *,
    get_saved_location_text_fn: Callable[[], str],
    coords_from_saved_location_fn: Callable[[], Optional[tuple[float, float]]],
) -> str:
    mode = str(weather_mode or "").strip().lower()
    explicit_value = str(location_value or "").strip()
    if mode == "explicit_location" and explicit_value:
        return explicit_value
    saved_location = str(get_saved_location_text_fn() or "").strip()
    if saved_location:
        return saved_location
    coords = coords_from_saved_location_fn()
    if coords:
        return f"{coords[0]},{coords[1]}"
    return explicit_value


def make_weather_result_state(
    *,
    weather_mode: str,
    location_value: str = "",
    tool_result: str = "",
    make_conversation_state_fn: Callable[..., dict],
    weather_location_label_fn: Callable[[str, str], str],
    extract_weather_source_host_fn: Callable[[str], str],
    weather_source_host_fn: Callable[[], Optional[str]],
) -> dict:
    return make_conversation_state_fn(
        "weather_result",
        subject="weather",
        weather_mode=str(weather_mode or "").strip().lower(),
        location_value=weather_location_label_fn(weather_mode, location_value),
        source_host=extract_weather_source_host_fn(tool_result) or str(weather_source_host_fn() or "").strip().lower(),
        tool_result=str(tool_result or "").strip(),
    )


def is_weather_meta_followup(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text_fn(text)
    if not normalized or "weather" not in normalized:
        return False
    return any(phrase in normalized for phrase in (
        "how did you get the weather",
        "how did you get that weather",
        "how did you get the weather information",
        "where did you get the weather",
        "where did you get that weather",
        "what source did you use for the weather",
        "weather tool",
    ))


def is_weather_status_followup(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text_fn(text)
    if not normalized or "weather" not in normalized:
        return False
    return any(phrase in normalized for phrase in (
        "what happened to my weather",
        "what happened to the weather",
        "what happened to that weather",
        "what happened to my weather information",
        "what happened to the weather information",
        "did you get the weather",
        "did you get my weather",
    ))


def weather_meta_reply(state: dict) -> str:
    source_host = str(state.get("source_host") or "").strip()
    location_value = str(state.get("location_value") or "").strip()
    if source_host and location_value:
        return f"I got that weather information from the weather tool using {source_host} for {location_value}."
    if source_host:
        return f"I got that weather information from the weather tool using {source_host}."
    if location_value:
        return f"I got that weather information from the weather tool for {location_value}."
    return "I got that weather information from the weather tool."


def weather_status_reply(state: dict) -> str:
    location_value = str(state.get("location_value") or "").strip()
    tool_result = str(state.get("tool_result") or "").strip()
    if tool_result and location_value:
        return f"The last weather lookup I handled was for {location_value}. Result: {tool_result}"
    if tool_result:
        return f"The last weather lookup I handled returned: {tool_result}"
    if location_value:
        return f"The last weather lookup I handled was for {location_value}, but I do not have the final result cached here."
    return "I do not have a completed weather result cached for this thread yet."


def is_location_recall_query(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    cues = [
        "where am i",
        "where am i located",
        "what's my location",
        "recall my location",
        "remember my location",
        "what is my location",
        "where is my location",
        "do you know my location",
        "can you recall my location",
        "can you remember my location",
    ]
    return any(cue in lowered for cue in cues)


def location_recall_reply(*, get_saved_location_text_fn: Callable[[], str]) -> str:
    preview = get_saved_location_text_fn()
    if preview:
        expanded = _LOCATION_HINT_LABELS.get(str(preview or "").strip().lower())
        if expanded and expanded.lower() not in str(preview or "").strip().lower():
            return f"Your saved location is {preview} ({expanded})."
        return f"Your saved location is {preview}."
    return "I don't have a stored location yet. You can tell me: 'My location is ...'"


def is_location_name_query(
    text: str,
    *,
    normalize_turn_text_fn: Callable[[str], str],
    uses_prior_reference_fn: Callable[[str], bool],
) -> bool:
    normalized = normalize_turn_text_fn(text).strip(" .,!?")
    if not normalized:
        return False
    explicit_cues = [
        "give me the name to that location",
        "give me the name of that location",
        "whats the name of that location",
        "what's the name of that location",
        "what is the name of that location",
        "what location is that",
        "which location is that",
        "what city is that zip",
        "what city is that location",
        "name of that location",
        "name to that location",
    ]
    if any(cue in normalized for cue in explicit_cues):
        return True
    return "location" in normalized and "name" in normalized and uses_prior_reference_fn(normalized)


def location_name_reply(*, get_saved_location_text_fn: Callable[[], str]) -> str:
    preview = get_saved_location_text_fn()
    if not preview:
        return "I don't have a stored location yet. You can tell me: 'My location is ...'"
    expanded = _LOCATION_HINT_LABELS.get(str(preview or "").strip().lower())
    if expanded:
        return f"That location is {expanded}."
    return f"The location I have saved is {preview}."


def handle_location_conversation_turn(
    state: Optional[dict],
    text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    make_conversation_state_fn: Callable[..., dict],
    is_location_name_query_fn: Callable[[str], bool],
    location_name_reply_fn: Callable[[], str],
    is_location_recall_query_fn: Callable[[str], bool],
    location_recall_reply_fn: Callable[[], str],
    looks_like_contextual_followup_fn: Callable[[str], bool],
    is_location_recall_state_fn: Callable[[Optional[dict]], bool],
    looks_like_location_recall_followup_fn: Callable[[list[tuple[str, str]], str], bool],
) -> tuple[bool, str, Optional[dict], str]:
    next_state = state if isinstance(state, dict) else make_conversation_state_fn("location_recall")
    if is_location_name_query_fn(text):
        return True, location_name_reply_fn(), next_state, "location_name"
    if is_location_recall_query_fn(text):
        return True, location_recall_reply_fn(), make_conversation_state_fn("location_recall"), "location_recall"
    if looks_like_contextual_followup_fn(text) and (
        is_location_recall_state_fn(state) or looks_like_location_recall_followup_fn(list(turns or []), text)
    ):
        return True, location_recall_reply_fn(), make_conversation_state_fn("location_recall"), "location_recall"
    return False, "", next_state, ""


def set_location_coords(
    value: str,
    *,
    set_core_state_fn: Callable[[object, str, object], None],
    default_statefile,
) -> str:
    parsed = parse_lat_lon(value)
    if not parsed:
        return "Usage: location coords <lat,lon>"
    lat, lon = parsed
    try:
        set_core_state_fn(default_statefile, "location_coords", {"lat": lat, "lon": lon})
    except Exception:
        return "Failed to save current location coordinates."
    return f"Saved current location coordinates: {lat},{lon}"


def get_weather_for_location(lat: float, lon: float) -> str:
    headers = {
        "User-Agent": "Nova/1.0 (local assistant)",
        "Accept": "application/geo+json",
    }

    point_url = f"https://api.weather.gov/points/{lat},{lon}"
    point_response = requests.get(point_url, headers=headers, timeout=20)
    point_response.raise_for_status()
    point_data = point_response.json()
    forecast_url = ((point_data.get("properties") or {}).get("forecast") or "").strip()
    if not forecast_url:
        return "I reached the weather service, but no forecast URL was returned for that location."

    forecast_response = requests.get(forecast_url, headers=headers, timeout=20)
    forecast_response.raise_for_status()
    forecast_data = forecast_response.json()

    periods = ((forecast_data.get("properties") or {}).get("periods") or [])
    if not periods:
        return "I reached the weather service, but no forecast periods were returned."

    now = periods[0]
    return (
        f"{now.get('name', 'Current')}: {now.get('temperature', '?')}°{now.get('temperatureUnit', 'F')}, "
        f"{now.get('shortForecast', 'unknown')}. Wind {now.get('windSpeed', '?')} {now.get('windDirection', '?')}. "
        f"[source: api.weather.gov]"
    )


def need_confirmed_location_message() -> str:
    return "I have a weather tool now, but I still need a confirmed location or coordinates for the current device."


def tool_weather(
    location: str,
    *,
    policy_tools_enabled_fn: Callable[[], dict],
    web_enabled_fn: Callable[[], bool],
    weather_source_host_fn: Callable[[], Optional[str]],
    weather_unavailable_message_fn: Callable[[], str],
    coords_for_location_hint_fn: Callable[[str], Optional[tuple[float, float]]],
    need_confirmed_location_message_fn: Callable[[], str],
    get_weather_for_location_fn: Callable[[float, float], str],
    format_weather_output_fn: Callable[[str, str], str],
) -> str:
    if not policy_tools_enabled_fn().get("web", False) or not web_enabled_fn():
        return "Weather lookup unavailable: web tool is disabled by policy."

    source = weather_source_host_fn()
    if not source:
        return weather_unavailable_message_fn()

    loc = (location or "").strip()

    if source == "api.weather.gov":
        coords = coords_for_location_hint_fn(loc)
        if not coords:
            return need_confirmed_location_message_fn()
        lat, lon = coords
        try:
            summary = get_weather_for_location_fn(lat, lon)
            label = loc if loc else f"{lat},{lon}"
            return format_weather_output_fn(label, summary)
        except Exception as e:
            return f"Weather lookup failed: {e}"

    if not loc:
        return "Usage: weather <location-or-lat,lon>"

    if source == "wttr.in":
        url = f"https://wttr.in/{quote(loc)}?format=j1"
        try:
            response = requests.get(url, headers={"User-Agent": "Nova/1.0"}, timeout=25)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            return f"Weather lookup failed: {e}"

        try:
            current = ((data.get("current_condition") or [{}])[0])
            desc = (((current.get("weatherDesc") or [{}])[0]).get("value") or "unknown").strip()
            temp_f = (current.get("temp_F") or "?").strip()
            feels_f = (current.get("FeelsLikeF") or "?").strip()
            humidity = (current.get("humidity") or "?").strip()
            wind_mph = (current.get("windspeedMiles") or "?").strip()

            return format_weather_output_fn(
                loc,
                f"{desc}, {temp_f}F (feels like {feels_f}F), humidity {humidity}%, wind {wind_mph} mph. [source: wttr.in]",
            )
        except Exception:
            return "Weather lookup succeeded but returned an unexpected payload format."

    return need_confirmed_location_message_fn()