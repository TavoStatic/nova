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
_KNOWN_LOCATION_CENTERS = [
    ("Brownsville, TX", BROWNSVILLE_LAT, BROWNSVILLE_LON, 35_000.0),
]


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
        "Add a source like 'policy allow api.weather.gov' and then use 'weather in <location-or-lat,lon>'."
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


def distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    return radius_m * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def location_label_for_coords(lat: float, lon: float) -> str:
    for label, center_lat, center_lon, radius_m in _KNOWN_LOCATION_CENTERS:
        try:
            if distance_meters(lat, lon, center_lat, center_lon) <= radius_m:
                return label
        except Exception:
            continue
    return ""


def live_device_location_summary(
    *,
    runtime_device_location_payload_fn: Optional[Callable[[], dict]] = None,
    resolve_current_device_coords_fn: Optional[Callable[[], object]] = None,
    allow_stale: bool = False,
) -> dict:
    if not callable(runtime_device_location_payload_fn):
        return {}
    try:
        live = runtime_device_location_payload_fn()
    except Exception:
        return {}
    if isinstance(live, dict) and (not live.get("available") or live.get("stale")) and callable(resolve_current_device_coords_fn):
        try:
            resolve_current_device_coords_fn()
            live = runtime_device_location_payload_fn()
        except Exception:
            pass
    if not isinstance(live, dict) or not live.get("available") or (live.get("stale") and not allow_stale):
        return {}
    lat = coerce_bounded_float(live.get("lat"), minimum=-90.0, maximum=90.0)
    lon = coerce_bounded_float(live.get("lon"), minimum=-180.0, maximum=180.0)
    if lat is None or lon is None:
        return {}
    coords_text = str(live.get("coords_text") or format_runtime_coords(lat, lon)).strip()
    accuracy = coerce_optional_metric(live.get("accuracy_m"))
    source = str(live.get("source") or "").strip()
    return {
        "lat": lat,
        "lon": lon,
        "coords_text": coords_text,
        "accuracy_m": accuracy,
        "source": source,
        "stale": bool(live.get("stale")),
        "label": location_label_for_coords(lat, lon),
    }


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
        try:
            os.chmod(device_location_file, 0o666)
            device_location_file.unlink(missing_ok=True)
        except Exception:
            try:
                device_location_file.write_text("null", encoding="utf-8")
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

    return None


def get_saved_location_text(
    *,
    read_core_state_fn: Callable[[object], dict],
    default_statefile,
) -> str:
    try:
        state = read_core_state_fn(default_statefile)
        raw = state.get("location_text") if isinstance(state, dict) else ""
        cleaned = re.sub(r"\s+", " ", str(raw or "").strip())
        if cleaned:
            return cleaned
    except Exception:
        pass
    return ""


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
        return "Usage: weather in <location-or-lat,lon>"

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
