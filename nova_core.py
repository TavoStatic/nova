# Nova Core (stable) - Voice + Typed chat, tools, local knowledge packs, safe web fetch, safe self-patching
# Target: Windows + Ollama + Faster-Whisper + Piper TTS
#
# Design goals:
# - Deterministic safety: never hallucinate tool output or machine actions.
# - Mixed input: press ENTER for voice, or type a message/command.
# - Piper TTS runs as a subprocess per utterance (reliable).
# - Optional knowledge packs (B-mode, lightweight lexical search).
# - Optional self-patching (zip overlay + snapshot + rollback + compile test).
# - Optional web fetch tool (allowlist + max bytes) that NEVER crashes core.

from __future__ import annotations

import argparse
import io
import json
import os
import queue
import re
import socket
import subprocess
import threading
import time
import zipfile
import hashlib
import mimetypes
import html
import tempfile
import difflib
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs, unquote, urljoin, quote
from capabilities import explain_missing, describe_capabilities
from task_engine import analyze_request
from action_planner import decide_actions
from env_inspector import inspect_environment, format_report
import requests
import psutil
try:
    import memory as memory_mod
except Exception:
    memory_mod = None

# Active session user id (simple session-scoped identity)
ACTIVE_USER: Optional[str] = None

def set_active_user(name: Optional[str]):
    global ACTIVE_USER
    if not name:
        ACTIVE_USER = None
    else:
        ACTIVE_USER = str(name).strip()

def get_active_user() -> Optional[str]:
    return ACTIVE_USER

# -------------------------
# Voice deps are optional
# -------------------------
VOICE_OK = True
VOICE_IMPORT_ERR = ""
try:
    import sounddevice as sd
    import scipy.io.wavfile as wav
    from faster_whisper import WhisperModel
except Exception as e:
    VOICE_OK = False
    VOICE_IMPORT_ERR = str(e)
    sd = None
    wav = None
    WhisperModel = None




# =========================
# Config / Policy
# =========================
import sys

# Robust BASE_DIR detection
if getattr(sys, "frozen", False):
    # Running as compiled executable
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    # Running as normal Python script
    BASE_DIR = Path(__file__).resolve().parent

RUNTIME_DIR = BASE_DIR / "runtime"
LOG_DIR = BASE_DIR / "logs"
MEMORY_DIR = BASE_DIR / "memory"
IDENTITY_FILE = MEMORY_DIR / "identity.json"
POLICY_PATH = BASE_DIR / "policy.json"
PYTHON = str(BASE_DIR / ".venv" / "Scripts" / "python.exe")
OLLAMA_BASE = "http://127.0.0.1:11434"

SAMPLE_RATE = 16000
CHANNELS = 1

# UX tuning
RECORD_SECONDS = 3
OLLAMA_BOOT_RETRIES = 15
OLLAMA_REQ_TIMEOUT = 1800

# Knowledge packs (B-mode)
KNOWLEDGE_ROOT = BASE_DIR / "knowledge"
PACKS_DIR = KNOWLEDGE_ROOT / "packs"
ACTIVE_PACK_FILE = KNOWLEDGE_ROOT / "active_pack.txt"
KB_MAX_FILES = 3
KB_MAX_CHARS = 2000
CHAT_CONTEXT_TURNS = 6

KNOWN_COLORS = {
    "red", "blue", "green", "yellow", "orange", "purple", "violet", "indigo",
    "pink", "brown", "black", "white", "gray", "grey", "silver", "gold",
    "teal", "cyan", "magenta", "maroon", "navy", "lime", "olive", "beige",
    "turquoise", "lavender", "coral", "burgundy", "tan", "mint", "aqua",
}

KNOWN_ANIMALS = {
    "dog", "dogs", "cat", "cats", "bird", "birds", "fish", "horse", "horses",
    "rabbit", "rabbits", "hamster", "hamsters", "turtle", "turtles", "snake", "snakes",
    "lizard", "lizards", "parrot", "parrots", "eagle", "eagles", "hawk", "hawks",
}

# Web cache folder
WEB_CACHE_DIR = KNOWLEDGE_ROOT / "web"

# Self patching
UPDATES_DIR = BASE_DIR / "updates"
SNAPSHOTS_DIR = UPDATES_DIR / "snapshots"
PATCH_LOG = UPDATES_DIR / "patch.log"
PATCH_REVISION_FILE = UPDATES_DIR / "revision.json"
PATCH_MANIFEST_NAME = "nova_patch.json"
POLICY_AUDIT_LOG = RUNTIME_DIR / "policy_changes.jsonl"

# Session-scoped web research continuation cache.
WEB_RESEARCH_LAST_QUERY: str = ""
WEB_RESEARCH_LAST_RESULTS: list[tuple[float, str, str]] = []
WEB_RESEARCH_CURSOR: int = 0


def ok(msg): print(f"[OK]   {msg}", flush=True)
def warn(msg): print(f"[WARN] {msg}", flush=True)
def bad(msg): print(f"[FAIL] {msg}", flush=True)


def load_policy() -> dict:
    data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    data["allowed_root"] = str(Path(data.get("allowed_root", str(BASE_DIR))).resolve())
    data.setdefault("tools_enabled", {})
    data.setdefault("models", {})
    data.setdefault("memory", {"enabled": False, "mode": "B", "top_k": 5, "min_score": 0.25, "exclude_sources": []})
    data.setdefault("web", {"enabled": False, "allow_domains": [], "max_bytes": 20_000_000})
    data.setdefault("patch", {"strict_manifest": True})
    return data


def _load_policy_raw() -> dict:
    try:
        return json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_policy_raw(data: dict) -> None:
    POLICY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _record_policy_change(action: str, target: str, result: str, details: str = "") -> None:
    entry = {
        "ts": int(time.time()),
        "user": get_active_user() or "unknown",
        "action": str(action or "").strip(),
        "target": str(target or "").strip(),
        "result": str(result or "").strip(),
        "details": str(details or "").strip(),
    }
    try:
        POLICY_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(POLICY_AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def policy_models():
    p = load_policy()
    return p.get("models") or {}


def policy_memory():
    p = load_policy()
    return p.get("memory") or {}


def policy_tools_enabled():
    p = load_policy()
    return p.get("tools_enabled") or {}


def policy_web():
    p = load_policy()
    return (p.get("web") or {})


def policy_patch():
    p = load_policy()
    return (p.get("patch") or {})


def web_enabled() -> bool:
    p = load_policy()
    return bool((p.get("tools_enabled") or {}).get("web")) and bool((p.get("web") or {}).get("enabled"))


def _host_allowed(host: str, allow_domains: list[str]) -> bool:
    host = (host or "").lower()
    for d in allow_domains:
        d = (d or "").lower().strip()
        if not d:
            continue
        if host == d or host.endswith("." + d):
            return True
    return False


def web_fetch(url: str, save_dir: Path) -> dict:
    """
    Fetch a URL (http/https only) if host is allowlisted.
    Saves to save_dir with deterministic filename.
    Never raises; always returns {"ok": bool, ...}.
    """
    if not web_enabled():
        return {"ok": False, "error": "Web tool disabled by policy."}

    cfg = policy_web()
    allow_domains = cfg.get("allow_domains") or []
    max_bytes = int(cfg.get("max_bytes") or 20_000_000)

    u = urlparse(url.strip())
    if u.scheme not in ("http", "https"):
        return {"ok": False, "error": "Only http/https URLs are allowed."}
    host = u.hostname or ""
    if not _host_allowed(host, allow_domains):
        return {"ok": False, "error": f"Domain not allowed: {host}"}

    save_dir.mkdir(parents=True, exist_ok=True)

    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    ts = time.strftime("%Y%m%d_%H%M%S")
    base = f"{ts}_{host}_{h}"

    try:
        r = requests.get(url, stream=True, timeout=60, headers={"User-Agent": "Nova/1.0"})
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"Request failed: {e}"}

    try:
        r.raise_for_status()
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()

        if ctype == "application/pdf":
            ext = ".pdf"
        elif ctype in ("text/html", "application/xhtml+xml"):
            ext = ".html"
        elif ctype.startswith("text/"):
            ext = ".txt"
        else:
            ext = mimetypes.guess_extension(ctype) or ".bin"

        out_path = save_dir / (base + ext)

        total = 0
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    out_path.unlink(missing_ok=True)
                    return {"ok": False, "error": f"File too large (>{max_bytes} bytes)."}
                f.write(chunk)

        return {"ok": True, "url": url, "path": str(out_path), "content_type": ctype, "bytes": total}

    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"HTTP error: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}
    finally:
        try:
            r.close()
        except Exception:
            pass


def _web_allowlist_message(context: str = "") -> str:
    """Return a friendly message explaining web allowlist restrictions and list allowed domains."""
    cfg = policy_web()
    allow_domains = cfg.get("allow_domains") or []
    if not allow_domains:
        base = "I attempted to access the web, but web access is restricted by policy and no allowlisted domains are configured."
        return base

    lines = [f"I attempted to access the web{(' for ' + context) if context else ''}, but my web tool only allows specific sources:"]
    for d in allow_domains:
        lines.append(f"- {d}")

    # suggest common weather API if present in allowlist otherwise suggest a known source
    preferred = None
    for candidate in ("api.weather.gov", "noaa.gov", "weather.gov"):
        for d in allow_domains:
            if candidate in d:
                preferred = candidate
                break
        if preferred:
            break

    if preferred:
        lines.append(f"If you'd like, I can try again using {preferred}.")
    else:
        lines.append("If you'd like, tell me which of the allowlisted domains to try, or provide an allowed URL to fetch.")
    lines.append("To add a new allowed domain, use: policy allow <domain>")

    return "\n".join(lines)


def _weather_source_host() -> Optional[str]:
    allow_domains = [str(d).strip().lower() for d in (policy_web().get("allow_domains") or []) if str(d).strip()]
    for preferred in ("api.weather.gov", "wttr.in"):
        for d in allow_domains:
            if d == preferred or d.endswith("." + preferred):
                return preferred
    return None


def _weather_unavailable_message() -> str:
    return (
        "I can access websites, but I don't yet have a reliable structured weather source configured. "
        "I cannot honestly claim weather results from raw weather.com pages. "
        "Add a source like 'policy allow api.weather.gov' and then use 'weather <location-or-lat,lon>'."
    )


def weather_response_style() -> str:
    try:
        s = str((policy_web().get("weather_response_style") or "concise")).strip().lower()
        if s in {"concise", "tool"}:
            return s
    except Exception:
        pass
    return "concise"


def _format_weather_output(label: str, summary: str) -> str:
    # Normalize whitespace and strip any existing weather-style prefixes so output is never stacked.
    s = re.sub(r"\s+", " ", (summary or "").strip())
    s = re.sub(r"^(?:weather|forecast)\s+for\s+[^:]+:\s*", "", s, flags=re.I)
    l = (label or "").strip() or "this location"

    # Normalize common deterministic location aliases to cleaner display names.
    aliases = {
        "brownsville": "Brownsville, TX",
        "brownsville tx": "Brownsville, TX",
        "brownsville, tx": "Brownsville, TX",
    }
    n = re.sub(r"\s+", " ", l.lower()).strip()
    l = aliases.get(n, l)

    style = weather_response_style()
    if style == "tool":
        return f"Forecast for {l}: {s}"
    return f"{l}: {s}"


def _mentions_location_phrase(text: str) -> bool:
    low = (text or "").lower()
    return any(p in low for p in [
        "location",
        "locaiton",  # common typo seen in transcript
        "physical location",
        "physical locaiton",
    ])


BROWNSVILLE_LAT = 25.9017
BROWNSVILLE_LON = -97.4975


def _parse_lat_lon(text: str) -> Optional[tuple[float, float]]:
    m = re.search(r"(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)", (text or ""))
    if not m:
        return None
    try:
        lat = float(m.group(1))
        lon = float(m.group(2))
    except Exception:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return (lat, lon)


def _coords_for_location_hint(location: str) -> Optional[tuple[float, float]]:
    loc = (location or "").strip().lower()
    if not loc:
        return None
    parsed = _parse_lat_lon(loc)
    if parsed:
        return parsed

    if "brownsville" in loc:
        return (BROWNSVILLE_LAT, BROWNSVILLE_LON)

    return None


def _coords_from_saved_location() -> Optional[tuple[float, float]]:
    # Prefer explicit operator-set coordinates stored in core state.
    try:
        st = read_core_state(DEFAULT_STATEFILE)
        c = st.get("location_coords") if isinstance(st, dict) else None
        if isinstance(c, dict):
            lat = float(c.get("lat"))
            lon = float(c.get("lon"))
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                return (lat, lon)
    except Exception:
        pass

    try:
        audit_out = mem_audit("location coordinates lat lon")
        j = json.loads(audit_out) if audit_out else {}
        results = j.get("results") if isinstance(j, dict) else []
        for r in results:
            preview = (r.get("preview") or "").strip()
            parsed = _parse_lat_lon(preview)
            if parsed:
                return parsed
    except Exception:
        return None
    return None


def set_location_coords(value: str) -> str:
    coords = _parse_lat_lon(value)
    if not coords:
        return "Usage: location coords <lat>,<lon>"

    lat, lon = coords
    try:
        set_core_state(DEFAULT_STATEFILE, "location_coords", {"lat": lat, "lon": lon})
    except Exception:
        pass

    # Also store in memory for continuity across tooling.
    try:
        mem_add("profile", "location_coords", f"location coordinates: {lat},{lon}")
    except Exception:
        pass

    return f"Saved current location coordinates: {lat},{lon}"


def get_weather_for_location(lat: float, lon: float) -> str:
    headers = {
        "User-Agent": "Nova/1.0 (local assistant)",
        "Accept": "application/geo+json",
    }

    point_url = f"https://api.weather.gov/points/{lat},{lon}"
    r1 = requests.get(point_url, headers=headers, timeout=20)
    r1.raise_for_status()
    point_data = r1.json()
    forecast_url = ((point_data.get("properties") or {}).get("forecast") or "").strip()
    if not forecast_url:
        return "I reached the weather service, but no forecast URL was returned for that location."

    r2 = requests.get(forecast_url, headers=headers, timeout=20)
    r2.raise_for_status()
    forecast_data = r2.json()

    periods = ((forecast_data.get("properties") or {}).get("periods") or [])
    if not periods:
        return "I reached the weather service, but no forecast periods were returned."

    now = periods[0]
    return (
        f"{now.get('name', 'Current')}: {now.get('temperature', '?')}°{now.get('temperatureUnit', 'F')}, "
        f"{now.get('shortForecast', 'unknown')}. Wind {now.get('windSpeed', '?')} {now.get('windDirection', '?')}. "
        f"[source: api.weather.gov]"
    )


def _need_confirmed_location_message() -> str:
    return "I have a weather tool now, but I still need a confirmed location or coordinates."


def tool_weather(location: str) -> str:
    if not policy_tools_enabled().get("web", False) or not web_enabled():
        return "Weather lookup unavailable: web tool is disabled by policy."

    source = _weather_source_host()
    if not source:
        return _weather_unavailable_message()

    loc = (location or "").strip()

    if source == "api.weather.gov":
        coords = _coords_for_location_hint(loc)
        if not coords:
            return _need_confirmed_location_message()
        lat, lon = coords
        try:
            summary = get_weather_for_location(lat, lon)
            label = loc if loc else f"{lat},{lon}"
            return _format_weather_output(label, summary)
        except Exception as e:
            return f"Weather lookup failed: {e}"

    if not loc:
        return "Usage: weather <location-or-lat,lon>"

    if source == "wttr.in":
        url = f"https://wttr.in/{quote(loc)}?format=j1"
        try:
            r = requests.get(url, headers={"User-Agent": "Nova/1.0"}, timeout=25)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return f"Weather lookup failed: {e}"

        try:
            cur = ((data.get("current_condition") or [{}])[0])
            desc = (((cur.get("weatherDesc") or [{}])[0]).get("value") or "unknown").strip()
            temp_f = (cur.get("temp_F") or "?").strip()
            feels_f = (cur.get("FeelsLikeF") or "?").strip()
            humidity = (cur.get("humidity") or "?").strip()
            wind_mph = (cur.get("windspeedMiles") or "?").strip()

            return _format_weather_output(
                loc,
                f"{desc}, {temp_f}F (feels like {feels_f}F), humidity {humidity}%, wind {wind_mph} mph. [source: wttr.in]",
            )
        except Exception:
            return "Weather lookup succeeded but returned an unexpected payload format."

    return _need_confirmed_location_message()

def allowed_root() -> Path:
    p = load_policy()
    return Path(p["allowed_root"]).resolve()


def chat_model() -> str:
    m = policy_models()
    return m.get("chat", "llama3.1:8b")


def whisper_size() -> str:
    m = policy_models()
    return m.get("stt_size", "small")


# =========================
# Guard/Core liveness contract
# =========================
DEFAULT_HEARTBEAT = RUNTIME_DIR / "core.heartbeat"
DEFAULT_STATEFILE = RUNTIME_DIR / "core_state.json"


def atomic_write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def touch(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(time.time()), encoding="utf-8")


def write_core_identity(statefile: Path):
    pid = os.getpid()
    ct = psutil.Process(pid).create_time()
    atomic_write_json(statefile, {
        "pid": int(pid),
        "create_time": float(ct),
        "ts": time.time(),
        "note": "canonical (written by core)"
    })


def read_core_state(statefile: Path) -> dict:
    try:
        if not statefile.exists():
            return {}
        return json.loads(statefile.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def set_core_state(statefile: Path, key: str, value) -> None:
    try:
        st = read_core_state(statefile)
        st[key] = value
        atomic_write_json(statefile, st)
    except Exception:
        pass


def start_heartbeat(heartbeat_file: Path, interval_sec: float = 1.0):
    stop_evt = threading.Event()

    def _loop():
        while not stop_evt.is_set():
            try:
                touch(heartbeat_file)
            except Exception:
                pass
            stop_evt.wait(interval_sec)

    t = threading.Thread(target=_loop, name="core-heartbeat", daemon=True)
    t.start()
    return stop_evt


# =========================
# Subprocess TTS (Piper oneshot)
# =========================
class SubprocessTTS:
    """Piper oneshot wrapper: python tts_piper.py "text"""

    def __init__(self, python_exe: str, oneshot_script: Path, timeout_sec: float = 25.0):
        self.python_exe = python_exe
        self.oneshot_script = oneshot_script
        self.timeout_sec = float(timeout_sec)
        self.q = queue.Queue()
        self.stop_evt = threading.Event()
        self.t = threading.Thread(target=self._run, name="tts-worker", daemon=True)

    def start(self):
        self.t.start()

    def stop(self):
        self.stop_evt.set()
        self.q.put(None)

    def say(self, text: str):
        if text:
            self.q.put(str(text))

    def _run(self):
        while not self.stop_evt.is_set():
            item = self.q.get()
            if item is None:
                break

            try:
                creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
                p = subprocess.Popen(
                    [self.python_exe, str(self.oneshot_script), item],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    creationflags=creationflags,
                )
                try:
                    _, err = p.communicate(timeout=self.timeout_sec)
                except subprocess.TimeoutExpired:
                    p.kill()
                    warn("TTS timed out; killed piper subprocess.")
                    continue

                if p.returncode != 0:
                    msg = (err or b"").decode("utf-8", errors="ignore").strip()
                    warn(f"TTS failed rc={p.returncode}: {msg}")

            except Exception as e:
                warn(f"TTS error: {e}")


def speak_chunked(tts: SubprocessTTS, text: str, max_len: int = 220):
    text = (text or "").strip()
    if not text:
        return
    parts = re.split(r'(?<=[.!?])\s+', text)
    buf = ""
    for p in parts:
        if len(buf) + len(p) + 1 <= max_len:
            buf = (buf + " " + p).strip()
        else:
            if buf:
                tts.say(buf)
            buf = p.strip()
    if buf:
        tts.say(buf)


# =========================
# Memory hooks (optional)
# =========================
def mem_enabled() -> bool:
    return bool(policy_memory().get("enabled", False))


def mem_top_k() -> int:
    try:
        return int(policy_memory().get("top_k", 5))
    except Exception:
        return 5


def mem_context_top_k() -> int:
    try:
        v = int(policy_memory().get("context_top_k", 3))
        return max(1, min(v, 10))
    except Exception:
        return 3


def mem_min_score() -> float:
    try:
        return float(policy_memory().get("min_score", 0.25))
    except Exception:
        return 0.25


def mem_exclude_sources() -> list[str]:
    xs = policy_memory().get("exclude_sources") or []
    return [str(x) for x in xs if x]


def mem_store_min_chars() -> int:
    try:
        return int(policy_memory().get("store_min_chars", 12))
    except Exception:
        return 12


def mem_should_store(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if len(t) < mem_store_min_chars():
        return False

    low = t.lower()
    low_value = {
        "ok", "okay", "k", "kk", "yes", "no", "thanks", "thank you",
        "done", "cool", "nice", "great", "sounds good",
    }
    if low in low_value:
        return False

    return True


def mem_add(kind: str, source: str, text: str):
    if not mem_enabled():
        return
    try:
        # Avoid storing assistant outputs and obvious questions
        low = (text or "").strip().lower()
        if source and str(source).lower() in {"assistant", "nova"}:
            return
        # reject lines that are questions even without punctuation
        q_starts = ("what ", "where ", "who ", "why ", "how ", "when ", "which ", "do ", "did ", "can ", "could ", "would ", "is ", "are ", "should ")
        if low.endswith("?") or any(low.startswith(q) for q in q_starts):
            return

        # Duplicate check: run memory audit for same user and skip if near-duplicate exists
        user = get_active_user()
        audit_cmd = [PYTHON, str(BASE_DIR / "memory.py"), "audit", "--query", text, "--topk", "1", "--minscore", str(mem_min_score())]
        if user:
            audit_cmd += ["--user", str(user)]
        try:
            r = subprocess.run(audit_cmd, capture_output=True, text=True, timeout=30)
            out = (r.stdout or "").strip()
            if out:
                try:
                    j = json.loads(out)
                    res = j.get("results") or []
                    if res:
                        top = res[0]
                        score = float(top.get("score") or 0.0)
                        preview = (top.get("preview") or "").strip()
                        def _norm(s: str) -> str:
                            return re.sub(r"\W+", " ", (s or "").lower()).strip()
                        if score >= 0.85 or _norm(preview) == _norm(text):
                            return
                except Exception:
                    pass
        except Exception:
            pass

        cmd = [PYTHON, str(BASE_DIR / "memory.py"), "add", "--kind", kind, "--source", source, "--text", text]
        if user:
            cmd += ["--user", str(user)]
        subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except Exception:
        pass


def mem_recall(query: str) -> str:
    if not mem_enabled():
        return ""

    if len((query or "").strip()) < 8:
        return ""

    try:
        cmd = [
            PYTHON, str(BASE_DIR / "memory.py"), "recall",
            "--query", query,
            "--topk", str(mem_context_top_k()),
            "--minscore", str(mem_min_score()),
        ]
        user = get_active_user()
        if user:
            cmd += ["--user", str(user)]
        for s in mem_exclude_sources():
            cmd += ["--exclude-source", s]

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        out = (r.stdout or "").strip()
        if not out or "No memories" in out:
            return ""

        bullets = []
        parts = re.split(r"\n--- score=.*?---\n", "\n" + out + "\n")
        seen = set()
        norm = lambda s: re.sub(r"\W+", " ", (s or "").lower()).strip()
        for p in parts:
            p = (p or "").strip()
            if not p:
                continue
            one = re.sub(r"\s+", " ", p).strip()
            n = norm(one)
            if n in seen:
                continue
            seen.add(n)
            bullets.append(f"- {one[:260]}")

        # limit returned context to configured top-k
        topk = mem_context_top_k()
        bullets = bullets[:max(1, int(topk))]
        return "\n".join(bullets)[:2000] if bullets else ""
    except Exception:
        return ""


def mem_stats() -> str:
    try:
        r = subprocess.run(
            [PYTHON, str(BASE_DIR / "memory.py"), "stats"],
            capture_output=True, text=True, timeout=1800
        )
        out = (r.stdout or "").strip()
        return out or "No memory stats available."
    except Exception as e:
        return f"Memory stats failed: {e}"


def mem_audit(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return "Usage: mem audit <query>"
    try:
        cmd = [
            PYTHON, str(BASE_DIR / "memory.py"), "audit",
            "--query", q,
            "--topk", str(mem_context_top_k()),
            "--minscore", str(mem_min_score()),
        ]
        user = get_active_user()
        if user:
            cmd += ["--user", str(user)]
        for s in mem_exclude_sources():
            cmd += ["--exclude-source", s]

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        out = (r.stdout or "").strip()
        return out or "No memory audit output."
    except Exception as e:
        return f"Memory audit failed: {e}"


def mem_remember_fact(text: str) -> str:
    fact = (text or "").strip().strip("\"'")
    if not fact:
        return "Usage: remember: <fact>"
    if not mem_enabled():
        return "Memory is disabled in policy."
    if len(fact) < 3:
        return "Fact is too short to store."

    mem_add("fact", "pinned", fact)
    return f"Pinned memory saved: {fact}"


def load_identity_profile() -> dict:
    try:
        if not IDENTITY_FILE.exists():
            return {}
        data = json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_identity_profile(data: dict) -> None:
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        tmp = IDENTITY_FILE.with_suffix(".json.tmp")
        payload = json.dumps(data, ensure_ascii=True, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(IDENTITY_FILE)
    except Exception:
        pass


def remember_name_origin(story_text: str) -> str:
    story = re.sub(r"\s+", " ", (story_text or "").strip())
    if len(story) < 30:
        return "Please provide a longer origin story so I can store it accurately."

    profile = load_identity_profile()
    profile["name_origin"] = story
    profile["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_identity_profile(profile)

    if mem_enabled():
        try:
            mem_add("identity", "typed", f"nova_name_origin: {story[:1400]}")
        except Exception:
            pass

    return "Stored. I will remember this as the story behind my name."


def get_name_origin_story() -> str:
    p = load_identity_profile()
    story = str(p.get("name_origin") or "").strip()
    if story:
        return story

    # Fallback to memory recall if identity file has not been set yet.
    try:
        recall = mem_recall("nova name origin story creator gus")
        if recall:
            return recall.strip()[:2000]
    except Exception:
        pass
    return ""


def identity_context_for_prompt() -> str:
    p = load_identity_profile()
    lines = []
    story = str(p.get("name_origin") or "").strip()
    if story:
        lines.append("Identity fact: The assistant's name origin story is user-defined.")
        lines.append(f"Name origin story: {story[:1400]}")
    if not lines:
        return ""
    return "\n".join(lines)


def build_learning_context(query: str) -> str:
    blocks = []

    kb_block = kb_search(query)
    if kb_block:
        blocks.append(kb_block)

    mem_block = mem_recall(query)
    if mem_block:
        # Keep memory context for the LLM but avoid injecting visible markers into user-facing reply.
        blocks.append(mem_block)

    if not blocks:
        return ""

    return "\n\n".join(blocks)[:4000]


def _render_chat_context(turns: list[tuple[str, str]], max_chars: int = 1800) -> str:
    if not turns:
        return ""
    lines = []
    for role, text in turns[-CHAT_CONTEXT_TURNS:]:
        role_name = "User" if role == "user" else "Assistant"
        t = re.sub(r"\s+", " ", (text or "").strip())
        if not t:
            continue
        lines.append(f"{role_name}: {t[:300]}")
    if not lines:
        return ""
    out = "\n".join(lines)
    return out[:max_chars]


def _uses_prior_reference(user_text: str) -> bool:
    t = (user_text or "").strip().lower()
    if not t:
        return False
    triggers = [
        "that information", "that info", "that", "those", "it",
        "from that", "from those", "summarize that", "give me that",
        "can you give me that", "use that",
    ]
    return any(x in t for x in triggers)


def _is_declarative_info(text: str) -> bool:
    """Return True when the user is supplying info (not asking for an action).
    Matches simple patterns like: "my name is X", "my location is X", "i live in X",
    or statements that start with 'i am' and contain a noun phrase.
    """
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    # common declarative prefixes
    declarative_prefixes = [
        "my name is",
        "i am",
        "i'm",
        "my location is",
        "i live in",
        "i work at",
        "i'm from",
        "i was born",
        "i have",
        "this is",
    ]
    for p in declarative_prefixes:
        if low.startswith(p):
            # avoid treating imperative like "i am done" as info if very short
            if len(t.split()) >= 2:
                return True
    # short factual sentences without question mark
    if "?" not in t and len(t.split()) <= 6 and any(w in low for w in ["live", "located", "from", "born", "work"]):
        return True
    return False


def _is_explicit_request(text: str) -> bool:
    """Return True when the user is asking for an action or information.
    Heuristics: questions (who/what/when/where/why/how), starts with a verb (imperative), contains polite verbs.
    """
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower().strip()
    # explicit question words
    qwords = ["who", "what", "when", "where", "why", "how", "which"]
    if low.endswith("?"):
        return True
    if any(low.startswith(w + " ") for w in qwords):
        return True
    # polite request patterns
    if any(kw in low for kw in ["please", "could you", "can you", "would you", "show me", "find", "search", "do you"]):
        return True
    # imperative: starts with a verb like 'open', 'run', 'create', 'save', 'search'
    verbs = ["open", "run", "create", "save", "search", "find", "read", "show", "list", "fetch", "gather"]
    first = low.split()[0]
    if first in verbs:
        return True
    return False


def _extract_urls(text: str) -> list[str]:
    found = re.findall(r"https?://[^\s\)\]>\"']+", text or "")
    urls = []
    seen = set()
    for u in found:
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)
    return urls


def _strip_invocation_prefix(text: str) -> str:
    """Normalize inputs like 'nova, ...' so routing sees the actual request."""
    t = (text or "").strip()
    if not t:
        return t

    m = re.match(r"^nova\b[\s,:\-]*(.*)$", t, flags=re.I)
    if not m:
        return t

    rest = (m.group(1) or "").strip()
    if not rest:
        return ""

    # Only strip when it looks like direct address/invocation.
    starter = (rest.split(maxsplit=1)[0] or "").lower()
    invoke_starters = {
        "what", "which", "who", "where", "when", "why", "how",
        "can", "could", "would", "do", "does", "did", "is", "are",
        "say", "tell", "show", "find", "search", "read", "list", "give",
        "web", "screen", "camera", "health", "inspect", "capabilities",
        "patch", "kb", "mem", "teach",
    }
    if starter in invoke_starters:
        return rest

    return t


def _normalize_domain_input(value: str) -> str:
    s = (value or "").strip().lower()
    if not s:
        return ""

    if not re.match(r"^[a-z][a-z0-9+.-]*://", s):
        s = "https://" + s

    try:
        p = urlparse(s)
        host = (p.hostname or "").strip().lower()
    except Exception:
        return ""

    if not host:
        return ""

    # Basic host validation: labels with letters/numbers/hyphen, separated by dots.
    if not re.match(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$", host):
        return ""

    return host


def list_allowed_domains() -> str:
    allow_domains = list(policy_web().get("allow_domains") or [])
    if not allow_domains:
        return "No allowed domains are configured in policy.json."

    lines = ["Here are the domains I currently allow:"]
    for d in allow_domains:
        lines.append(f"- {d}")
    return "\n".join(lines)


def policy_allow_domain(value: str) -> str:
    host = _normalize_domain_input(value)
    if not host:
        _record_policy_change("allow_domain", value, "failed", "invalid_domain_input")
        return "Usage: policy allow <domain-or-url>"

    data = _load_policy_raw()
    web = data.get("web") if isinstance(data.get("web"), dict) else {}
    allow_domains = list(web.get("allow_domains") or [])

    existing = {str(x).strip().lower() for x in allow_domains if str(x).strip()}
    if host in existing:
        _record_policy_change("allow_domain", host, "skipped", "already_allowed")
        return f"Domain already allowed: {host}"

    allow_domains.append(host)
    web["allow_domains"] = allow_domains
    data["web"] = web
    _save_policy_raw(data)
    _record_policy_change("allow_domain", host, "success", "added_to_allow_domains")

    return f"Added allowed domain: {host}\n{list_allowed_domains()}"


def policy_remove_domain(value: str) -> str:
    host = _normalize_domain_input(value)
    if not host:
        _record_policy_change("remove_domain", value, "failed", "invalid_domain_input")
        return "Usage: policy remove <domain-or-url>"

    data = _load_policy_raw()
    web = data.get("web") if isinstance(data.get("web"), dict) else {}
    allow_domains = list(web.get("allow_domains") or [])

    kept = []
    removed = False
    for d in allow_domains:
        dd = str(d).strip()
        if dd.lower() == host:
            removed = True
            continue
        kept.append(dd)

    if not removed:
        _record_policy_change("remove_domain", host, "skipped", "not_found")
        return f"Domain not found in allowlist: {host}"

    web["allow_domains"] = kept
    data["web"] = web
    _save_policy_raw(data)
    _record_policy_change("remove_domain", host, "success", "removed_from_allow_domains")
    return f"Removed allowed domain: {host}\n{list_allowed_domains()}"


def policy_audit(limit: int = 20) -> str:
    n = max(1, min(200, int(limit or 20)))
    if not POLICY_AUDIT_LOG.exists():
        return "No policy audit entries yet."

    try:
        lines = [ln for ln in POLICY_AUDIT_LOG.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception as e:
        return f"Failed to read policy audit log: {e}"

    if not lines:
        return "No policy audit entries yet."

    rows = []
    for ln in lines[-n:]:
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue
    if not rows:
        return "No parseable policy audit entries found."

    out = [f"Recent policy changes (last {len(rows)}):"]
    for r in rows:
        ts = int(r.get("ts") or 0)
        tstr = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "unknown-time"
        user = str(r.get("user") or "unknown")
        action = str(r.get("action") or "")
        target = str(r.get("target") or "")
        result = str(r.get("result") or "")
        details = str(r.get("details") or "")
        out.append(f"- {tstr} user={user} action={action} target={target} result={result} details={details}")

    return "\n".join(out)


WEB_RESEARCH_PRESETS = {
    "normal": {
        "research_domains_limit": 4,
        "research_pages_per_domain": 8,
        "research_scan_pages_per_domain": 12,
        "research_max_depth": 1,
        "research_seeds_per_domain": 8,
        "research_max_results": 8,
        "research_min_score": 3.0,
    },
    "max": {
        "research_domains_limit": 8,
        "research_pages_per_domain": 25,
        "research_scan_pages_per_domain": 60,
        "research_max_depth": 2,
        "research_seeds_per_domain": 20,
        "research_max_results": 20,
        "research_min_score": 1.5,
    },
}


def web_mode_status() -> str:
    cfg = policy_web()
    lines = ["Current web research limits:"]
    keys = [
        "research_domains_limit",
        "research_pages_per_domain",
        "research_scan_pages_per_domain",
        "research_max_depth",
        "research_seeds_per_domain",
        "research_max_results",
        "research_min_score",
    ]
    for k in keys:
        lines.append(f"- {k}: {cfg.get(k)}")
    lines.append("Use: web mode max | web mode normal")
    return "\n".join(lines)


def set_web_mode(mode: str) -> str:
    m = (mode or "").strip().lower()
    if m in {"balanced", "default"}:
        m = "normal"
    if m in {"deep", "full", "maxinput"}:
        m = "max"

    if m not in WEB_RESEARCH_PRESETS:
        return "Usage: web mode <normal|max>"

    data = _load_policy_raw()
    web = data.get("web") if isinstance(data.get("web"), dict) else {}
    for k, v in WEB_RESEARCH_PRESETS[m].items():
        web[k] = v
    data["web"] = web
    _save_policy_raw(data)
    _record_policy_change("web_mode", m, "success", "updated_research_limits")
    return f"Web research mode set to {m}.\n" + web_mode_status()


def _build_greeting_reply(user_text: str, active_user: Optional[str] = None) -> Optional[str]:
    t = (user_text or "").strip().lower()
    greet_regex = re.compile(r"^(hi|hello|hey|good morning|good afternoon|good evening)([\s!,\.]|$)")
    m = greet_regex.match(t)
    if not m:
        return None

    # If this utterance includes an actual request after the greeting, do not
    # short-circuit here; let deterministic command routing handle it.
    rest = t[m.end():].strip()
    rest = re.sub(r"^nova\b[\s,:\-]*", "", rest, flags=re.I).strip()
    request_markers = [
        "can you", "could you", "would you", "please", "give me", "check", "show", "tell me",
        "weather", "web", "search", "find", "read", "list", "inspect", "health", "help",
    ]
    if rest and any(k in rest for k in request_markers):
        return None

    who = (active_user or "").strip()
    has_how_are_you = bool(re.search(r"\bhow\s+are\s+you\b", t))

    if has_how_are_you:
        if who:
            return f"Hey {who}. I'm doing good today. What's going on?"
        return "Hey. I'm doing good today. What's going on?"

    word = m.group(1)
    if word in {"hi", "hello"}:
        return f"Hi {who}." if who else "Hello."
    if word == "hey":
        return f"Hey {who}. What do you need?" if who else "Hey, what do you need?"
    return f"{word.capitalize()}, {who}." if who else f"{word.capitalize()}."


def _extract_color_preferences(session_turns: list[tuple[str, str]]) -> list[str]:
    colors = []
    seen = set()
    for role, text in session_turns:
        if role != "user":
            continue
        t = (text or "").lower().strip()

        has_preference_signal = any(s in t for s in [
            "i like", "i love", "i prefer", "favorite color", "favourite color", "like the color",
        ]) or bool(re.search(r"\bi\s+(?:\w+\s+){0,3}like\b", t))
        if not has_preference_signal:
            continue

        toks = re.findall(r"[a-z]{3,20}", t)
        found = [w for w in toks if w in KNOWN_COLORS]
        if not found:
            continue

        for c in found:
            if c in seen:
                continue
            seen.add(c)
            colors.append(c)
    return colors


def _extract_color_preferences_from_text(text: str) -> list[str]:
    toks = re.findall(r"[a-z]{3,20}", (text or "").lower())
    out = []
    seen = set()
    for t in toks:
        if t in KNOWN_COLORS and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _extract_color_preferences_from_memory() -> list[str]:
    if not mem_enabled():
        return []
    probe = mem_recall("what colors does the user like favorite color preference")
    return _extract_color_preferences_from_text(probe)


def _extract_developer_color_preferences(session_turns: list[tuple[str, str]]) -> list[str]:
    aliases = {"gus", "gustavo", "developer", "dev"}
    out = []
    seen = set()
    for role, text in session_turns:
        if role != "user":
            continue
        t = (text or "").lower().strip()
        if not any(a in t for a in aliases):
            continue
        if not any(k in t for k in ["color", "colors", "favourite", "favorite", "likes", "like", "bilingual", "english", "spanish"]):
            continue
        for w in re.findall(r"[a-z]{3,20}", t):
            if w in KNOWN_COLORS and w not in seen:
                seen.add(w)
                out.append(w)
    return out


def _extract_developer_color_preferences_from_memory() -> list[str]:
    if not mem_enabled():
        return []
    probe = mem_recall("gustavo gus developer favorite colors color preference")
    if not probe:
        return []

    out = []
    seen = set()
    lines = [ln.strip().lower() for ln in probe.splitlines() if ln.strip()]
    candidate_lines = [
        ln for ln in lines
        if any(a in ln for a in ["gus", "gustavo", "developer"])
        and any(k in ln for k in ["color", "colors", "favorite", "favourite", "likes", "like"])
    ]
    source = "\n".join(candidate_lines) if candidate_lines else probe
    for w in re.findall(r"[a-z]{3,20}", source.lower()):
        if w in KNOWN_COLORS and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _is_developer_color_lookup_request(user_text: str) -> bool:
    t = (user_text or "").lower()
    if not any(k in t for k in ["color", "colors"]):
        return False
    return any(k in t for k in ["developer", "gus", "gustavo", "he", "his"])


def _is_developer_bilingual_request(user_text: str) -> bool:
    t = (user_text or "").lower()
    if not any(k in t for k in ["developer", "gus", "gustavo", "he", "his"]):
        return False
    return any(k in t for k in ["bilingual", "english", "spanish", "languages", "language"])


def _developer_is_bilingual(session_turns: list[tuple[str, str]]) -> Optional[bool]:
    aliases = ["developer", "gus", "gustavo"]
    for role, text in reversed(session_turns):
        if role != "user":
            continue
        t = (text or "").lower()
        if not any(a in t for a in aliases):
            continue
        if "bilingual" in t and ("english" in t or "spanish" in t):
            return True
        if "not bilingual" in t:
            return False
    return None


def _developer_is_bilingual_from_memory() -> Optional[bool]:
    if not mem_enabled():
        return None
    probe = mem_recall("is gustavo bilingual english spanish developer")
    low = (probe or "").lower()
    if not low:
        return None
    if ("gus" in low or "gustavo" in low or "developer" in low) and "bilingual" in low and ("english" in low or "spanish" in low):
        return True
    if "not bilingual" in low:
        return False
    return None


def _extract_animal_preferences(session_turns: list[tuple[str, str]]) -> list[str]:
    animals = []
    seen = set()
    for role, text in session_turns:
        if role != "user":
            continue
        t = (text or "").lower().strip()
        has_signal = any(s in t for s in ["i like", "i love", "i prefer", "favorite animal", "favourite animal"]) \
            or bool(re.search(r"\bi\s+(?:\w+\s+){0,3}like\b", t))
        if not has_signal:
            continue
        toks = re.findall(r"[a-z]{3,20}", t)
        for w in toks:
            if w not in KNOWN_ANIMALS:
                continue
            norm = "birds" if w in {"bird", "birds"} else ("dogs" if w in {"dog", "dogs"} else w)
            if norm in seen:
                continue
            seen.add(norm)
            animals.append(norm)
    return animals


def _extract_animal_preferences_from_text(text: str) -> list[str]:
    toks = re.findall(r"[a-z]{3,20}", (text or "").lower())
    out = []
    seen = set()
    for w in toks:
        if w not in KNOWN_ANIMALS:
            continue
        norm = "birds" if w in {"bird", "birds"} else ("dogs" if w in {"dog", "dogs"} else w)
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _extract_animal_preferences_from_memory() -> list[str]:
    if not mem_enabled():
        return []
    probe = mem_recall("what animals does the user like favorite animal preference")
    return _extract_animal_preferences_from_text(probe)


def _is_color_animal_match_question(user_text: str) -> bool:
    t = (user_text or "").lower()
    return ("what color" in t or "which color" in t) and ("animal" in t or "animals" in t) and any(
        k in t for k in ["match", "best", "goes", "fit", "fits"]
    )


def _pick_color_for_animals(colors: list[str], animals: list[str]) -> str:
    if not colors:
        return ""
    if len(colors) == 1:
        return colors[0]

    score = {c: 0 for c in colors}
    for c in colors:
        cl = c.lower()
        for a in animals:
            al = a.lower()
            if al in {"birds", "parrots", "eagles", "hawks"} and cl in {"red", "blue", "green", "yellow", "orange"}:
                score[c] += 2
            if al in {"dogs", "cats", "horses"} and cl in {"brown", "black", "white", "gray", "grey", "silver", "gold"}:
                score[c] += 1
    best = sorted(colors, key=lambda c: score.get(c, 0), reverse=True)
    return best[0]


def _is_color_lookup_request(user_text: str) -> bool:
    t = (user_text or "").lower()
    direct = [
        "what color do i like",
        "what colors do i like",
        "which color do i like",
        "which colors do i like",
        "color i like",
        "colors i like",
    ]
    if any(x in t for x in direct):
        return True
    if "go back" in t and "color" in t:
        return True
    if "past chat" in t and "color" in t:
        return True
    return False


# =========================
# Guard rails (files)
# =========================
def is_within_allowed(p: Path) -> bool:
    try:
        p.resolve().relative_to(allowed_root())
        return True
    except Exception:
        return False


def safe_path(user_path: str) -> Path:
    p = Path(user_path)
    if not p.is_absolute():
        p = (allowed_root() / p)
    p = p.resolve()
    if not is_within_allowed(p):
        raise PermissionError(f"Denied: outside allowed root: {allowed_root()}")
    return p


# =========================
# Ollama helpers
# =========================
def tcp_listening(host="127.0.0.1", port=11434, timeout=1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ollama_api_up(timeout=2.0) -> bool:
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def start_ollama_serve_detached() -> bool:
    try:
        DETACHED = 0x00000008
        NEW_GROUP = 0x00000200
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=DETACHED | NEW_GROUP,
        )
        return True
    except Exception:
        return False


def kill_ollama() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"], capture_output=True, text=True)


def ensure_ollama_boot():
    if not tcp_listening():
        warn("Ollama not listening on 11434. Starting ollama serve...")
        start_ollama_serve_detached()

    if tcp_listening() and not ollama_api_up():
        warn("Ollama port open but API not responding. Restarting...")
        kill_ollama()
        time.sleep(1.2)
        start_ollama_serve_detached()

    for _ in range(OLLAMA_BOOT_RETRIES):
        if ollama_api_up():
            ok("Ollama API up")
            return True
        time.sleep(1)

    bad("Ollama API still down.")
    return False


def ensure_ollama():
    if not tcp_listening():
        start_ollama_serve_detached()
    if tcp_listening() and not ollama_api_up():
        kill_ollama()
        time.sleep(1.0)
        start_ollama_serve_detached()
    for _ in range(10):
        if ollama_api_up():
            return
        time.sleep(0.5)


# =========================
# Knowledge packs (B-mode)
# =========================
def _tokenize(q: str):
    q = (q or "").lower()
    toks = re.findall(r"[a-z0-9]{3,}", q)
    if "peims" in q and "peims" not in toks:
        toks.append("peims")
    return list(dict.fromkeys(toks))[:25]


def kb_active_pack() -> Optional[str]:
    try:
        if ACTIVE_PACK_FILE.exists():
            name = ACTIVE_PACK_FILE.read_text(encoding="utf-8").strip()
            return name or None
    except Exception:
        pass
    return None


def kb_set_active(name: Optional[str]) -> str:
    KNOWLEDGE_ROOT.mkdir(parents=True, exist_ok=True)
    if not name:
        if ACTIVE_PACK_FILE.exists():
            ACTIVE_PACK_FILE.unlink(missing_ok=True)
        return "Knowledge pack disabled."
    (PACKS_DIR / name).mkdir(parents=True, exist_ok=True)
    ACTIVE_PACK_FILE.write_text(name, encoding="utf-8")
    return f"Active knowledge pack: {name}"


def kb_list_packs() -> str:
    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    packs = [p.name for p in PACKS_DIR.iterdir() if p.is_dir()]
    packs.sort(key=str.lower)
    active = kb_active_pack()
    lines = []
    for p in packs:
        mark = "*" if active and p.lower() == active.lower() else " "
        lines.append(f"{mark} {p}")
    if not lines:
        return "No knowledge packs yet. (You can add one with: kb add <zip_path> <pack_name>)"
    return "Knowledge packs:\n" + "\n".join(lines)


def kb_add_zip(zip_path: str, pack_name: str) -> str:
    zpath = safe_path(zip_path) if not Path(zip_path).is_absolute() else Path(zip_path)
    if not zpath.exists() or not zpath.is_file():
        return f"Not a file: {zpath}"

    dest = PACKS_DIR / pack_name
    dest.mkdir(parents=True, exist_ok=True)

    exts = {".txt", ".md"}
    extracted = 0
    with zipfile.ZipFile(zpath, "r") as z:
        for member in z.infolist():
            if member.is_dir():
                continue
            name = Path(member.filename).name
            if Path(name).suffix.lower() not in exts:
                continue
            out = dest / name
            out.write_bytes(z.read(member))
            extracted += 1

    if extracted == 0:
        return "No .txt/.md files found in zip. (For now, keep packs as txt/md; we can add PDF parsing later.)"
    return f"Added {extracted} file(s) to knowledge pack: {pack_name}"


def kb_search(query: str, max_files: int = KB_MAX_FILES, max_chars: int = KB_MAX_CHARS) -> str:
    pack = kb_active_pack()
    if not pack:
        return ""
    root = PACKS_DIR / pack
    if not root.exists():
        return ""

    toks = _tokenize(query)
    if not toks:
        return ""

    candidates = []
    exts = {".txt", ".md"}

    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        low = text.lower()
        score = 0
        for t in toks:
            score += low.count(t)

        if score > 0:
            candidates.append((score, p, text))

    if not candidates:
        return ""

    candidates.sort(key=lambda x: x[0], reverse=True)
    picked = candidates[:max_files]

    blocks = []
    used = 0
    for score, path, text in picked:
        low = text.lower()
        idx = None
        for t in toks:
            j = low.find(t)
            if j != -1:
                idx = j
                break
        if idx is None:
            idx = 0

        start = max(0, idx - 250)
        end = min(len(text), idx + 950)
        snippet = text[start:end].strip().replace("\r\n", "\n")

        chunk = f"[FILE] {path.name} (score={score})\n{snippet}\n"
        if used + len(chunk) > max_chars:
            break
        blocks.append(chunk)
        used += len(chunk)

    if not blocks:
        return ""
    return f"REFERENCE (knowledge pack: {pack}):\n\n" + "\n---\n".join(blocks)


# =========================
# Self patching (zip overlay + snapshot + rollback)
# =========================
def _log_patch(msg: str):
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {msg}\n"
    PATCH_LOG.write_text(PATCH_LOG.read_text(encoding="utf-8") + line if PATCH_LOG.exists() else line, encoding="utf-8")


def _read_patch_revision() -> int:
    try:
        if not PATCH_REVISION_FILE.exists():
            return 0
        data = json.loads(PATCH_REVISION_FILE.read_text(encoding="utf-8"))
        return int(data.get("revision", 0) or 0)
    except Exception:
        return 0


def _write_patch_revision(revision: int, source: str):
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "revision": int(revision),
        "source": source,
        "ts": time.time(),
    }
    PATCH_REVISION_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_patch_manifest(zip_path: Path) -> Tuple[Optional[dict], Optional[str]]:
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            names = {n.replace("\\", "/").lstrip("/") for n in z.namelist()}
            if PATCH_MANIFEST_NAME not in names:
                return None, None
            raw = z.read(PATCH_MANIFEST_NAME)
            data = json.loads(raw.decode("utf-8", errors="replace"))
            if not isinstance(data, dict):
                return None, "Patch manifest must be a JSON object."
            return data, None
    except json.JSONDecodeError as e:
        return None, f"Invalid patch manifest JSON: {e}"
    except Exception as e:
        return None, f"Unable to read patch manifest: {e}"


def _snapshot_meta_path(snapshot_zip: Path) -> Path:
    return snapshot_zip.with_suffix(snapshot_zip.suffix + ".meta.json")


def _write_snapshot_meta(snapshot_zip: Path, revision: int):
    meta = {
        "revision": int(revision),
        "snapshot": snapshot_zip.name,
        "ts": time.time(),
    }
    _snapshot_meta_path(snapshot_zip).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_snapshot_meta(snapshot_zip: Path) -> Optional[dict]:
    p = _snapshot_meta_path(snapshot_zip)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _snapshot_current() -> Path:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    snap = SNAPSHOTS_DIR / f"snapshot_{ts}.zip"
    skip_dirs = {".venv", "runtime", "logs", "models", "updates", "__pycache__", "knowledge"}
    with zipfile.ZipFile(snap, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in BASE_DIR.rglob("*"):
            if p.is_dir():
                continue
            rel = p.relative_to(BASE_DIR)
            if rel.parts and rel.parts[0] in skip_dirs:
                continue
            if "__pycache__" in rel.parts:
                continue
            z.write(p, arcname=str(rel))
    _write_snapshot_meta(snap, _read_patch_revision())
    _log_patch(f"SNAPSHOT {snap.name}")
    return snap


def _overlay_zip(zip_path: Path) -> int:
    allowed_ext = {".py", ".json", ".md", ".txt", ".ps1", ".cmd"}
    blocked_prefix = {".venv/", "runtime/", "logs/", "models/"}

    count = 0
    with zipfile.ZipFile(zip_path, "r") as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/").lstrip("/")
            if name == PATCH_MANIFEST_NAME:
                continue
            if any(name.startswith(bp) for bp in blocked_prefix):
                continue
            ext = Path(name).suffix.lower()
            if ext not in allowed_ext:
                continue
            out = BASE_DIR / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read(info))
            count += 1

    return count


def _py_compile_check() -> Tuple[bool, str]:
    try:
        r = subprocess.run(
            [PYTHON, "-m", "compileall", str(BASE_DIR)],
            capture_output=True, text=True, timeout=1800
        )
        out = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
        ok_ = (r.returncode == 0)
        return ok_, out.strip()
    except Exception as e:
        return False, str(e)


def _patch_reject_message(
    reason: str,
    *,
    strict_manifest: bool,
    current_revision: int,
    incoming_revision: Optional[int],
    required_base_revision: Optional[int],
) -> str:
    incoming_text = str(incoming_revision) if incoming_revision is not None else "missing"
    required_base_text = str(required_base_revision) if required_base_revision is not None else "not specified"
    strict_text = "on" if strict_manifest else "off"
    return (
        f"Patch rejected: {reason}\n"
        f"- incoming revision: {incoming_text}\n"
        f"- current revision: {current_revision}\n"
        f"- required base: {required_base_text}\n"
        f"- current base: {current_revision}\n"
        f"- strict mode: {strict_text}"
    )


def patch_apply(zip_path: str, force: bool = False) -> str:
    z = safe_path(zip_path) if not Path(zip_path).is_absolute() else Path(zip_path)
    if not z.exists() or not z.is_file():
        return f"Not a file: {z}"

    # Run a preview check first to avoid blind applies and write a preview report.
    try:
        preview_out = patch_preview(str(z), write_report=True)
        # Only proceed automatically if preview indicates eligible or force=True
        if not force and "Status: eligible" not in preview_out:
            # Try to return a structured rejection message consistent with previous behavior
            strict_manifest = bool(policy_patch().get("strict_manifest", True))
            current_revision = _read_patch_revision()
            manifest, manifest_err = _read_patch_manifest(z)
            if manifest_err:
                _log_patch(f"APPLY_REJECT invalid_manifest {z.name} err={manifest_err}")
                return _patch_reject_message(
                    manifest_err,
                    strict_manifest=strict_manifest,
                    current_revision=current_revision,
                    incoming_revision=None,
                    required_base_revision=None,
                )

            # parse incoming revision and min_base if present
            try:
                incoming_rev = int(manifest.get("patch_revision", 0) or 0)
            except Exception:
                incoming_rev = None
            try:
                min_base = int(manifest.get("min_base_revision", 0) or 0)
            except Exception:
                min_base = None

            if incoming_rev is not None and incoming_rev <= current_revision:
                _log_patch(f"APPLY_REJECT downgrade current={current_revision} next={incoming_rev} zip={z.name}")
                return _patch_reject_message(
                    "non-forward revision (downgrade blocked).",
                    strict_manifest=strict_manifest,
                    current_revision=current_revision,
                    incoming_revision=incoming_rev,
                    required_base_revision=min_base,
                )

            if min_base is not None and current_revision < min_base:
                _log_patch(f"APPLY_REJECT base_too_old current={current_revision} min_base={min_base} zip={z.name}")
                return _patch_reject_message(
                    "incompatible base state.",
                    strict_manifest=strict_manifest,
                    current_revision=current_revision,
                    incoming_revision=incoming_rev,
                    required_base_revision=min_base,
                )

            # Fallback: return preview output
            # If preview was written to disk, require an explicit local approval
            m = re.search(r"Preview written:\s*(.+)$", preview_out, flags=re.M)
            if m:
                preview_path = m.group(1).strip()
                # check approvals
                approved = False
                for a in _read_approvals():
                    if str(preview_path) == str(a.get("preview")) and a.get("decision") == "approved":
                        approved = True
                        break
                if not approved:
                    return (f"Patch rejected: preview check failed. A preview was generated at {preview_path} and requires local approval before applying.\n\nPreview output:\n{preview_out}\n\n"
                            "Approve with: patch approve <preview_filename>\nOr re-run with --force to override.")

            return (f"Patch rejected: preview check failed.\n\nPreview output:\n{preview_out}\n\n"
                    "If you really want to apply anyway, re-run with: patch apply <zip_path> --force")
    except Exception:
        # If preview fails unexpectedly, block apply unless forced
        if not force:
            return "Patch preview failed; aborting apply. Use --force to override."

    strict_manifest = bool(policy_patch().get("strict_manifest", True))
    current_revision = _read_patch_revision()
    manifest, manifest_err = _read_patch_manifest(z)
    if manifest_err:
        _log_patch(f"APPLY_REJECT invalid_manifest {z.name} err={manifest_err}")
        return _patch_reject_message(
            manifest_err,
            strict_manifest=strict_manifest,
            current_revision=current_revision,
            incoming_revision=None,
            required_base_revision=None,
        )

    next_revision = None
    if manifest is None:
        if strict_manifest:
            _log_patch(f"APPLY_REJECT missing_manifest {z.name}")
            return _patch_reject_message(
                f"missing {PATCH_MANIFEST_NAME}. Include patch_revision > current revision.",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=None,
                required_base_revision=None,
            )
    else:
        try:
            next_revision = int(manifest.get("patch_revision", 0) or 0)
        except Exception:
            _log_patch(f"APPLY_REJECT bad_revision {z.name}")
            return _patch_reject_message(
                "manifest field 'patch_revision' must be an integer.",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=None,
                required_base_revision=None,
            )

        try:
            min_base = int(manifest.get("min_base_revision", 0) or 0)
        except Exception:
            _log_patch(f"APPLY_REJECT bad_min_base {z.name}")
            return _patch_reject_message(
                "manifest field 'min_base_revision' must be an integer when provided.",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=next_revision,
                required_base_revision=None,
            )

        if next_revision <= current_revision:
            _log_patch(f"APPLY_REJECT downgrade current={current_revision} next={next_revision} zip={z.name}")
            return _patch_reject_message(
                "non-forward revision (downgrade blocked).",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=next_revision,
                required_base_revision=min_base,
            )
        if current_revision < min_base:
            _log_patch(f"APPLY_REJECT base_too_old current={current_revision} min_base={min_base} zip={z.name}")
            return _patch_reject_message(
                "incompatible base state.",
                strict_manifest=strict_manifest,
                current_revision=current_revision,
                incoming_revision=next_revision,
                required_base_revision=min_base,
            )

    snap = _snapshot_current()
    _log_patch(f"APPLY {z.name} current_rev={current_revision} next_rev={next_revision if next_revision is not None else 'unversioned'}")

    n = _overlay_zip(z)
    if n == 0:
        _log_patch("APPLY no files overlayed")
        return "Patch zip contained no eligible files to apply."

    ok_compile, out = _py_compile_check()
    if not ok_compile:
        _log_patch("COMPILE_FAIL -> rollback")
        patch_rollback(str(snap))
        return "Patch applied, but compile check failed. Rolled back.\n\nCompile output:\n" + out[-3500:]

    if next_revision is not None:
        _write_patch_revision(next_revision, source=z.name)

    _log_patch(f"APPLY_OK files={n}")
    rev_msg = f" Revision: {next_revision}." if next_revision is not None else ""
    return f"Patch applied: {n} file(s). Compile check OK. Snapshot: {snap.name}.{rev_msg}"


def patch_rollback(snapshot_zip: Optional[str] = None) -> str:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snaps = sorted(SNAPSHOTS_DIR.glob("snapshot_*.zip"), key=lambda p: p.name, reverse=True)
    if snapshot_zip:
        snap = Path(snapshot_zip)
        if not snap.is_absolute():
            snap = SNAPSHOTS_DIR / snapshot_zip
    else:
        snap = snaps[0] if snaps else None

    if not snap or not snap.exists():
        return "No snapshot found to rollback."

    _log_patch(f"ROLLBACK {snap.name}")

    with zipfile.ZipFile(snap, "r") as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            out = BASE_DIR / info.filename
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read(info))

    meta = _read_snapshot_meta(snap)
    if meta and "revision" in meta:
        try:
            _write_patch_revision(int(meta.get("revision", 0) or 0), source=f"rollback:{snap.name}")
        except Exception:
            pass

    ok_compile, out = _py_compile_check()
    if not ok_compile:
        return "Rollback completed, but compile check still failing.\n\nCompile output:\n" + out[-3500:]
    return f"Rollback completed from snapshot: {snap.name}"


def patch_preview(zip_path: str, write_report: bool = False) -> str:
    """Preview a patch zip against the current repo.
    - lists manifest info (patch_revision, min_base_revision)
    - lists added / changed / skipped files
    - provides a short diff summary for text files
    If `write_report` is True, writes a preview text into UPDATES_DIR/previews/.
    """
    z = safe_path(zip_path) if not Path(zip_path).is_absolute() else Path(zip_path)
    if not z.exists() or not z.is_file():
        return f"Not found: {z}"

    manifest, manifest_err = _read_patch_manifest(z)
    if manifest_err:
        manifest = None

    current_revision = _read_patch_revision()
    patch_rev = None
    min_base = None
    try:
        if manifest:
            patch_rev = int(manifest.get("patch_revision", 0) or 0)
            min_base = int(manifest.get("min_base_revision", 0) or 0)
    except Exception:
        pass

    # decide skipped prefixes and text extensions
    skip_prefixes = ("runtime/", "logs/", "updates/", "piper/", "models/", "pkgconfig/")
    text_ext = {".py", ".md", ".txt", ".json", ".rst", ".yaml", ".yml", ".ini", ".cfg", ".html", ".css", ".js", ".csv"}

    added = []
    changed = []
    skipped = []
    diffs = {}

    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(z, "r") as zz:
            members = [m for m in zz.infolist() if not m.is_dir()]
            for m in members:
                fn = m.filename.replace("\\", "/")
                # skip obvious runtime artifacts
                if any(fn.startswith(p) for p in skip_prefixes):
                    skipped.append(fn)
                    continue

                # target path in repo
                target = BASE_DIR / fn

                # extract member to tempdir
                try:
                    zz.extract(m, path=td)
                except Exception:
                    skipped.append(fn)
                    continue

                src = Path(td) / fn
                if not src.exists():
                    skipped.append(fn)
                    continue

                if target.exists():
                    # compare
                    try:
                        if src.suffix.lower() in text_ext:
                            a = target.read_text(encoding="utf-8", errors="ignore").splitlines()
                            b = src.read_text(encoding="utf-8", errors="ignore").splitlines()
                            if a != b:
                                changed.append(fn)
                                ud = difflib.unified_diff(a, b, fromfile=str(target), tofile=str(z.name + ":" + fn), lineterm="")
                                diffs[fn] = "\n".join(list(ud)[:400])
                        else:
                            # binary or unknown - mark changed if bytes differ
                            if target.read_bytes() != src.read_bytes():
                                changed.append(fn)
                    except Exception:
                        changed.append(fn)
                else:
                    added.append(fn)

    # prepare summary
    status = "eligible"
    if patch_rev is not None:
        if patch_rev <= current_revision:
            status = "rejected: non-forward revision"
        elif min_base is not None and current_revision < min_base:
            status = "rejected: incompatible base revision"

    lines = []
    lines.append("Patch Preview")
    lines.append("-------------")
    lines.append(f"Zip: {z.name}")
    lines.append(f"Patch revision: {patch_rev if patch_rev is not None else 'unknown'}")
    lines.append(f"Min base revision: {min_base if min_base is not None else 'not specified'}")
    lines.append(f"Current revision: {current_revision}")
    lines.append(f"Status: {status}")
    lines.append("")

    if changed:
        lines.append("Changed files:")
        for c in changed:
            lines.append(f"- {c}")
        lines.append("")

    if added:
        lines.append("Added files:")
        for a in added:
            lines.append(f"- {a}")
        lines.append("")

    if skipped:
        lines.append("Skipped files:")
        for s in skipped[:50]:
            lines.append(f"- {s}")
        if len(skipped) > 50:
            lines.append(f"- ... and {len(skipped)-50} more")
        lines.append("")

    lines.append("Diff summary:")
    if diffs:
        for fn, d in diffs.items():
            lines.append(f"- {fn}: modified")
            lines.append("```")
            lines.append(d)
            lines.append("```")
    else:
        lines.append("- No text diffs available or all changes are binary/non-text")

    out = "\n".join(lines)

    if write_report:
        try:
            previews = UPDATES_DIR / "previews"
            previews.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            fn = previews / f"preview_{ts}_{z.name}.txt"
            fn.write_text(out, encoding="utf-8")
            out = out + f"\n\nPreview written: {fn}"
        except Exception:
            pass

    return out


# -------------------------
# Preview approval helpers
# -------------------------
def _approvals_file() -> Path:
    p = UPDATES_DIR / "approvals.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_approvals() -> list[dict]:
    p = _approvals_file()
    if not p.exists():
        return []
    out = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except Exception:
                    continue
    except Exception:
        return []
    return out


def _record_approval(preview_path: str, decision: str, user: Optional[str] = None, note: str = "") -> bool:
    rec = {
        "ts": int(time.time()),
        "preview": str(preview_path),
        "decision": decision,
        "user": user or (get_active_user() or "unknown"),
        "note": note,
    }
    try:
        with open(_approvals_file(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def list_previews() -> str:
    previews = UPDATES_DIR / "previews"
    if not previews.exists():
        return "No previews found."
    files = sorted(previews.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    approvals = _read_approvals()
    mapping = {a.get("preview"): a for a in approvals}
    lines = []
    for p in files:
        status = "pending"
        ap = mapping.get(str(p)) or mapping.get(p.name)
        if ap:
            status = ap.get("decision", "pending")
        lines.append(f"- {p.name}  [{status}]")
    return "\n".join(lines)


def show_preview(path_or_name: str) -> str:
    previews = UPDATES_DIR / "previews"
    p = Path(path_or_name)
    if not p.is_absolute():
        p = previews / path_or_name
    if not p.exists():
        return f"Preview not found: {p}"
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"Failed to read preview: {e}"


def approve_preview(path_or_name: str, note: str = "") -> str:
    previews = UPDATES_DIR / "previews"
    p = Path(path_or_name)
    if not p.is_absolute():
        p = previews / path_or_name
    if not p.exists():
        return f"Preview not found: {p}"
    ok = _record_approval(str(p), "approved", user=get_active_user(), note=note)
    return "Approved." if ok else "Failed to record approval."


def reject_preview(path_or_name: str, note: str = "") -> str:
    previews = UPDATES_DIR / "previews"
    p = Path(path_or_name)
    if not p.is_absolute():
        p = previews / path_or_name
    if not p.exists():
        return f"Preview not found: {p}"
    ok = _record_approval(str(p), "rejected", user=get_active_user(), note=note)
    return "Rejected." if ok else "Failed to record rejection."


def interactive_preview_review(preview_path: str) -> str:
    """TTY-only interactive review loop for a preview file.
    Options: approve, reject, view, cancel
    Records decision to approvals log.
    Returns a short status message.
    """
    try:
        import sys
        p = Path(preview_path)
        if not p.exists():
            return f"Preview not found: {p}"
        # show concise header
        header = p.name
        # read first ~2000 chars of preview for quick summary
        text = p.read_text(encoding="utf-8")
        summary = "\n".join(text.splitlines()[:40])
        print("\nProposal review:\n", flush=True)
        print(f"Name: {header}")
        # try to extract patch revision line
        mrev = re.search(r"Patch revision:\s*(.+)$", text, flags=re.M)
        if mrev:
            print(f"Revision: {mrev.group(1).strip()}")
        # list changed/added counts
        changed = re.findall(r"^Changed files:\s*$", text, flags=re.M)
        # print short summary
        print("Files / diff preview (first lines):")
        print(summary)

        while True:
            try:
                resp = input('\nDecision? (approve/reject/view/cancel): ').strip().lower()
            except EOFError:
                return "No interactive input; review aborted."
            if resp in {"approve", "a"}:
                ok = _record_approval(str(p), "approved", user=get_active_user())
                return "Approved." if ok else "Failed to record approval."
            if resp in {"reject", "r"}:
                ok = _record_approval(str(p), "rejected", user=get_active_user())
                return "Rejected." if ok else "Failed to record rejection."
            if resp in {"view", "v"}:
                print('\n---- Full preview ----\n')
                print(text)
                print('\n---- End preview ----\n')
                continue
            if resp in {"cancel", "c", "quit", "q"}:
                return "Review canceled."
            print("Unknown response. Enter 'approve', 'reject', 'view', or 'cancel'.")
    except Exception as e:
        return f"Interactive review failed: {e}"


# =========================
# Deterministic answers & hallucination filters
# =========================
def hard_answer(user_text: str) -> Optional[str]:
    t = (user_text or "").strip().lower()

    if t in {"can you code", "can you code?", "do you code", "do you code?"}:
        return ("Yes. I can write code, debug it, and explain it. "
                "I just can’t scan your machine or execute system actions unless you trigger an explicit tool command.")

    if "scan my machine" in t or "scan my computer" in t or "run a scan" in t or "nmap" in t:
        return ("No. I can’t scan your machine or run tools like nmap by myself. "
                "Tell me what you want checked and I’ll give you safe commands to run, then paste the output and I’ll interpret it.")

    return None


def sanitize_llm_reply(reply: str, tool_context: str = "") -> str:
    r = (reply or "").strip()
    low = r.lower()

    # Block obviously fabricated system-scan language.
    scan_patterns = [
        r"starting nmap",
        r"nmap scan report",
        r"c:\\>nmap",
        r"host is up",
        r"port\s+state\s+service",
        r"i'm running a system scan",
        r"scan report for",
    ]
    for p in scan_patterns:
        if re.search(p, low):
            return ("I didn’t run any scans or system commands. I won’t fabricate scan outputs. "
                    "If you want a scan, run the tool and paste the real output and I’ll interpret it.")

    # Prevent ungrounded weather success claims when no structured weather output exists.
    if re.search(r"\bi\s+(?:fetched|retrieved|got)\s+(?:the\s+)?weather", low):
        tc = (tool_context or "").lower()
        if "weather for" not in tc and "source: wttr.in" not in tc:
            return _weather_unavailable_message()

    # Enforce explicit TOOL citation when assistant appears to reference tool-produced artifacts.
    strong_patterns = [
        r"\bsaved\s+to\b",
        r"\bdownloaded\b",
        r"\bpatch\s+appl(?:y|ied)\b",
        r"\bsnapshot(?:_[\w\-]+)?\b",
        r"\b(?:created|wrote)\s+(?:file|folder|directory)\b",
        r"\b(?:/|\\)[\w\-\.\/]+\.[a-z0-9]{1,6}\b",
    ]

    def _needs_citation(text_lower: str) -> bool:
        return any(re.search(p, text_lower) for p in strong_patterns)

    if _needs_citation(low):
        if "[tool:" not in low and "[tool:" not in r.lower():
            return ("I can’t claim tool outputs unless I include an explicit TOOL citation. "
                    "Please run the tool and paste its output or enable tool access; I won't fabricate results.")

    # Verify any [TOOL:...] citations are grounded in the provided tool context.
    cited = re.findall(r"\[TOOL:([a-zA-Z0-9_\-]+)\]", r)
    if cited:
        tc = (tool_context or "").lower()
        bad_found = False
        for name in cited:
            token = f"[tool:{name.lower()}]"
            if token not in tc:
                bad_found = True
        if bad_found:
            cleaned = re.sub(r"\[TOOL:[^\]]+\]", "", r).strip()
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if cleaned:
                return cleaned
            return ("I can’t claim tool outputs unless they come from a real tool run in this chat. "
                    "I won’t fabricate TOOL citations.")

    # --- Additional UX rules to strip auto-offer phrases, unsolicited links, and ungrounded capability claims ---
    # Remove sentences that offer help unsolicitedly (unless we have tool context)
    offer_patterns = [
        r"how can i (help|assist)",
        r"would you like me to",
        r"do you want me to",
        r"\bi can (help|assist)\b",
        r"i(?:'| i)?ll start (?:research|researching)",
        r"i will start (?:research|researching)",
        r"i(?:'| i)?ll research",
        r"i will research",
        # remove terse "retrieving ..." or similar interim-status sentences when no tool ran
        r"\bretriev(?:ing|e)?\b",
    ]

    def _sentence_filter(text: str) -> str:
        parts = re.split(r'(?<=[.!?])\s+', text)
        out = []
        for s in parts:
            low_s = s.lower()
            skip = False
            for p in offer_patterns:
                if re.search(p, low_s):
                    # if tool_context contains some tool token, keep; else skip
                    if not (tool_context or ""):  # no tool context
                        skip = True
                        break
            if not skip:
                out.append(s)
        return " ".join(out).strip()

    # Remove sentences that promise future research or actions unless a tool ran
    research_patterns = [
        r"i\s*(?:'| i)?ll (?:research|look into|investigate|start researching|go research)",
        r"i will (?:research|look into|investigate|start researching|go research)",
        r"i(?:'| i)?m going to (?:research|look into|investigate)",
    ]

    def _remove_research_promises(text: str) -> str:
        parts = re.split(r'(?<=[.!?])\s+', text)
        out = []
        for s in parts:
            low_s = s.lower()
            skip = False
            for p in research_patterns:
                if re.search(p, low_s):
                    if not (tool_context or ""):
                        skip = True
                        break
            if not skip:
                out.append(s)
        return " ".join(out).strip()

    filtered = _sentence_filter(r)
    filtered = _remove_research_promises(filtered)

    # Remove raw URLs unless a TOOL citation is present or user requested sources
    if re.search(r"https?://", filtered) and not (tool_context or ""):
        # strip URLs
        filtered = re.sub(r"https?://\S+", "[link removed]", filtered)

    # If the assistant claims 'I can <action>' for capabilities, replace with known capabilities list
    cap_match = re.search(r"\bi can (fetch|browse|search|lookup|open|download|run|apply|patch|install|scan)\b", filtered or "", flags=re.I)
    if cap_match:
        caps = describe_capabilities()
        return caps

    filtered = filtered.strip()
    if not filtered:
        # fallback to short acknowledgement
        return "Okay."

    return filtered


def _strip_mem_leak(reply: str, mem_block: str) -> str:
    """Remove raw memory dump snippets from a model reply for user-facing output.
    If mem_block appears verbatim in reply, strip it. Also remove any leading
    'MEMORY RECALL' markers and lines that look like audit dumps.
    """
    out = (reply or "")
    try:
        if mem_block:
            out = out.replace(mem_block, "")
        # remove visible MEMORY RECALL header lines (standalone or inline)
        out = re.sub(r"(?i)memory\s*recall:\s*", "", out)
        # remove audit style separators and score lines
        out = re.sub(r"(?m)^--- score=.*?---\s*$", "", out)
        # collapse multiple blank lines
        out = re.sub(r"\n{3,}", "\n\n", out)
        return out.strip()
    except Exception:
        return reply


def format_tool_citation(tool: str, tool_output: str) -> str:
    """
    Return a TOOL citation line when a tool output contains a saved path.
    Keeps citation formatting centralized so other code can reuse it.
    """
    try:
        if not isinstance(tool_output, str):
            return ""
        m = re.search(r"Saved:\s*(\S+)", tool_output)
        if m:
            return f"[TOOL:{tool}] {m.group(1)}\n"
    except Exception:
        pass
    return ""


def _ensure_reply(reply: Optional[str]) -> str:
    """Guarantee a non-empty user-facing reply."""
    try:
        r = (reply or "")
        if not r or not r.strip():
            return "Okay."
        return r
    except Exception:
        return "Okay."


def _normalize_location_preview(preview: str) -> str:
    """Normalize stored location previews into a clean canonical sentence fragment."""
    if not preview:
        return preview
    p = preview.strip()
    # remove common leading phrases
    p = re.sub(r'^(my(?: full| physical)? location is\s*:?)', '', p, flags=re.I).strip()
    p = re.sub(r'^location\s*:\s*', '', p, flags=re.I).strip()
    # remove duplicate leading 'my' artifacts
    p = re.sub(r'^my\s+', '', p, flags=re.I).strip()
    # collapse whitespace and stray punctuation
    p = re.sub(r'\s+', ' ', p).strip()
    p = p.rstrip('.')
    p = p.strip()
    return p


# =========================
# Ollama chat
# =========================
def ollama_chat(text: str, retrieved_context: str = "") -> str:
    """
    Deterministic chat wrapper: strict non-hallucination rules and low temperature.
    This function avoids injecting memory and enforces a constrained system prompt.
    """
    # Ensure the Ollama service is available (boot-time should have called ensure_ollama_boot)
    try:
        ensure_ollama()
    except Exception:
        # proceed; requests will surface an error which we retry below
        pass

    # Build a strict system message that prevents fabricated actions and enforces
    # a specific TOOL citation format when referencing tool-produced outputs.
    casual_prompt = (
        "You are Nova, a friendly conversational assistant running locally on Windows.\n"
        "Tone and behavior rules:\n"
        "- Speak naturally and briefly like a person in the room; prefer short acknowledgements for casual statements.\n"
        "- Do NOT repeatedly offer assistance or suggest actions unless the user explicitly asks for help. Avoid endings like 'Would you like me to...' in casual chat.\n"
        "- Avoid formal task-oriented phrasing for ordinary conversation; use gentle acknowledgements (e.g., 'Got it.', 'She sounds tired.', 'Nice.').\n"
        "- Never claim you performed actions on the PC (open, unzip, delete, move, install, browse, click, run commands) unless a tool was actually executed and its real output is available.\n"
        "- Do NOT provide external links or URLs unless the user asks specifically for a link or sources. If asked for a source, provide one and include a TOOL citation only when the output is grounded.\n"
        "- Never invent links, file paths, filenames, or results. If unsure, say you are unsure.\n"
        "- Only ask clarifying questions sparingly and only when necessary to complete a requested task; do not ask follow-ups for simple observational statements.\n"
        "- Keep answers concise and verifiable.\n"
        "- IMPORTANT: If you reference results produced by tools (files saved, snapshots, patches, downloads, paths, etc.), include an exact citation line in this format: '[TOOL:<tool_name>] <short description or path>'.\n"
        "  Example citations:\n"
        "    [TOOL:web_fetch] runtime/web/20260101_example.html\n"
        "    [TOOL:patch_apply] Patch applied: 3 files\n"
        "- Do NOT fabricate any such citation — if you do not have a real tool output, say you don't have the output and provide the command the user should run to get it.\n"
    )

    assist_prompt = (
        "You are Nova, a helpful assistant running locally on Windows.\n"
        "Tone and behavior rules:\n"
        "- Be helpful and offer assistance when helpful, but avoid fabricating actions or results.\n"
        "- If the user is vague and a follow-up is needed to complete a requested task, ask one concise clarifying question.\n"
        "- For task-oriented requests, prioritize clear, actionable steps.\n"
        "- Never claim you performed actions on the PC (open, unzip, delete, move, install, browse, click, run commands) unless a tool was actually executed and its real output is available.\n"
        "- Do NOT provide external links unless the user requests sources; when providing tool outputs include TOOL citations.\n"
        "- Keep answers concrete and verifiable.\n"
        "- IMPORTANT: If you reference results produced by tools (files saved, snapshots, patches, downloads, paths, etc.), include an exact citation line in this format: '[TOOL:<tool_name>] <short description or path>'.\n"
        "  Example citations:\n"
        "    [TOOL:web_fetch] runtime/web/20260101_example.html\n"
        "    [TOOL:patch_apply] Patch applied: 3 files\n"
        "- Do NOT fabricate any such citation — if you do not have a real tool output, say you don't have the output and provide the command the user should run to get it.\n"
    )

    # Choose prompt variant via CASUAL_MODE env var (default: casual)
    if os.environ.get("CASUAL_MODE", "1").lower() in {"1", "true", "yes"}:
        system_msg = casual_prompt
    else:
        system_msg = assist_prompt

    identity_ctx = identity_context_for_prompt()
    if identity_ctx:
        system_msg = f"{system_msg}\n\nPersistent identity memory:\n{identity_ctx}"

    # Build user content with optional retrieved context
    user_content = text
    if retrieved_context:
        user_content = (
            f"{text}\n\n"
            "Retrieved context (use only if relevant; if uncertain, say uncertain):\n"
            "<<<CONTEXT\n"
            f"{retrieved_context[:6000]}\n"
            ">>>"
        )

    payload = {
        "model": chat_model(),
        "stream": False,
        "options": {"temperature": 0.2, "top_p": 0.9, "repeat_penalty": 1.1},
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ],
    }

    # Primary call with one deterministic retry after a service restart
    try:
        r = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=OLLAMA_REQ_TIMEOUT)
        r.raise_for_status()
        try:
            return r.json()["message"]["content"].strip()
        except Exception:
            return None
    except Exception:
        warn("Ollama chat failed; attempting one restart and retry.")
        try:
            kill_ollama()
            time.sleep(1.2)
            start_ollama_serve_detached()
            time.sleep(1.2)
            r = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=OLLAMA_REQ_TIMEOUT)
            r.raise_for_status()
            try:
                return r.json()["message"]["content"].strip()
            except Exception:
                return None
        except Exception as e:
            warn(f"Ollama chat final attempt failed: {e}")
            return "(error: LLM service unavailable)"


def _teach_store_example(original: str, correction: str, user: Optional[str] = None) -> str:
    """Store a teach example both in memory and as a local examples file for patch proposals."""
    try:
        user = user or get_active_user() or ""
        ex = {"orig": original, "corr": correction, "user": user, "ts": int(time.time())}
        # store in memory for runtime learning
        mem_add("teach", "user_teach", json.dumps(ex))

        # also append to local examples file for patch proposals
        teach_dir = UPDATES_DIR / "teaching"
        teach_dir.mkdir(parents=True, exist_ok=True)
        fn = teach_dir / "examples.jsonl"
        with open(fn, "a", encoding="utf-8") as f:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        return "OK"
    except Exception as e:
        return f"Failed to store teach example: {e}"


def _parse_correction(text: str) -> Optional[str]:
    """Parse a freeform correction and return the corrected reply if found."""
    if not text:
        return None
    t = text.strip()
    # common patterns
    patterns = [
        r"^(?:no|nah|nope|that's wrong|wrong|not quite|don't)\b.*(?:say|respond|reply|use)\s+[\"'](.+?)[\"'](?:\s*instead)?$",
        r"^(?:say|respond|reply|use)\s+[\"'](.+?)[\"']\s*(?:instead)?$",
        r".*instead[,:\s]+[\"']?(.+?)[\"']?$",
    ]
    for pat in patterns:
        m = re.match(pat, t, flags=re.I)
        if m:
            corr = m.group(1).strip()
            if corr:
                return corr
    return None


def _apply_reply_overrides(reply: str) -> str:
    """Check stored teach examples and return an overridden reply if a matching original is found."""
    try:
        teach_dir = UPDATES_DIR / "teaching"
        fn = teach_dir / "examples.jsonl"
        if not fn.exists():
            return reply
        norm = lambda s: re.sub(r"\s+", " ", (s or "").strip())
        target = norm(reply)
        # Try semantic fuzzy match if memory embed utilities are available
        try:
            if memory_mod is not None and hasattr(memory_mod, "embed") and hasattr(memory_mod, "cosine"):
                tvec = memory_mod.embed(target)
                best = (0.0, None)
                with open(fn, "r", encoding="utf-8") as f:
                    for ln in f:
                        try:
                            j = json.loads(ln)
                            orig = norm(j.get("orig") or "")
                            corr = j.get("corr") or ""
                            if not orig:
                                continue
                            ovec = memory_mod.embed(orig)
                            sim = memory_mod.cosine(tvec, ovec)
                            if sim > best[0]:
                                best = (sim, corr)
                        except Exception:
                            continue
                # threshold for accepting a fuzzy override
                if best[0] >= 0.85 and best[1]:
                    return best[1]
        except Exception:
            pass

        # Fallback: exact normalized match
        with open(fn, "r", encoding="utf-8") as f:
            for ln in f:
                try:
                    j = json.loads(ln)
                    orig = norm(j.get("orig") or "")
                    corr = j.get("corr") or ""
                    if orig and orig == target:
                        return corr
                except Exception:
                    continue
    except Exception:
        pass
    return reply


def _teach_list_examples() -> str:
    try:
        teach_dir = UPDATES_DIR / "teaching"
        fn = teach_dir / "examples.jsonl"
        if not fn.exists():
            return "No teach examples stored. Use: teach remember <orig> => <correction>"
        lines = []
        with open(fn, "r", encoding="utf-8") as f:
            for ln in f:
                try:
                    j = json.loads(ln)
                    lines.append(f"- [{j.get('user')}] {j.get('orig')} => {j.get('corr')}")
                except Exception:
                    continue
        return "\n".join(lines) if lines else "No teach examples found."
    except Exception as e:
        return f"Failed to read teach examples: {e}"


def _teach_propose_patch(description: str) -> str:
    try:
        teach_dir = UPDATES_DIR / "teaching"
        fn = teach_dir / "examples.jsonl"
        if not fn.exists():
            return "No teach examples to propose. Use: teach remember <orig> => <correction>"

        ts = time.strftime("%Y%m%d_%H%M%S")
        out_zip = UPDATES_DIR / f"teach_proposal_{ts}.zip"
        manifest = {
            "name": f"teach_proposal_{ts}",
            "desc": description or "Teach examples proposal",
            "rev": int(time.time()),
        }
        tmp_manifest = UPDATES_DIR / f"teach_manifest_{ts}.json"
        tmp_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(fn, arcname="examples.jsonl")
            z.write(tmp_manifest, arcname=PATCH_MANIFEST_NAME)

        try:
            tmp_manifest.unlink()
        except Exception:
            pass

        # generate preview report for this proposal
        try:
            preview_out = patch_preview(str(out_zip), write_report=True)
        except Exception:
            preview_out = "Preview generation failed."

        # If running in an interactive terminal, offer immediate local review UI
        try:
            import sys
            if sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
                # extract preview filename if present
                m = re.search(r"Preview written:\s*(.+)$", preview_out or "", flags=re.M)
                preview_path = m.group(1).strip() if m else None
                if preview_path:
                    decision_msg = interactive_preview_review(preview_path)
                else:
                    decision_msg = "Preview saved but path not found. Use 'patch list-previews' to locate it."
            else:
                decision_msg = ""
        except Exception:
            decision_msg = ""

        base_msg = f"Created proposal: {out_zip} — apply with: patch apply {out_zip}"
        if decision_msg:
            return base_msg + "\n" + decision_msg
        return base_msg
    except Exception as e:
        return f"Failed to create teach proposal: {e}"


def _teach_autoapply_proposal(zip_path: str, apply_live: bool = False) -> str:
    """Test a proposal zip in a staging copy of the repo first.
    If tests pass in staging and `apply_live` is True, apply the patch to the live repo via patch_apply().
    By default (`apply_live=False`) this runs staging and returns the test output and the suggested apply command
    without modifying the live repository.
    """
    try:
        z = Path(zip_path)
        if not z.exists():
            return f"Not found: {z}"

        # Generate and save a preview report for this proposal
        try:
            preview_out = patch_preview(str(z), write_report=True)
        except Exception as e:
            # Save failure reason to previews
            try:
                previews = UPDATES_DIR / "previews"
                previews.mkdir(parents=True, exist_ok=True)
                tsf = time.strftime("%Y%m%d_%H%M%S")
                fail_fn = previews / f"preview_fail_{tsf}_{z.name}.txt"
                fail_fn.write_text(f"Preview generation failed: {e}", encoding="utf-8")
            except Exception:
                pass
            return f"Preview generation failed: {e}"

        # If preview indicates rejected status, save and abort autoapply
        if "Status: eligible" not in (preview_out or ""):
            return f"Preview indicates proposal is not eligible for autoapply. Preview saved.\n\n{preview_out}"

        ts = time.strftime("%Y%m%d_%H%M%S")
        staging = UPDATES_DIR / f"staging_{ts}"
        # copy repo to staging
        import shutil
        staging.mkdir(parents=True, exist_ok=True)
        # copytree requires empty target; copy contents instead
        for item in BASE_DIR.iterdir():
            if item.name in {"runtime", "logs", "updates", "piper", "models"}:
                # skip large runtime artifacts
                continue
            dest = staging / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # extract zip into staging (overlay)
        with zipfile.ZipFile(z, "r") as zz:
            zz.extractall(path=staging)

        # run tests in staging
        python_exe = PYTHON
        cmd = [python_exe, "-m", "unittest", "discover", "-v"]
        proc = subprocess.run(cmd, cwd=str(staging), capture_output=True, text=True, timeout=600)
        out = proc.stdout + "\n" + proc.stderr
        if proc.returncode != 0:
            # cleanup staging
            try:
                shutil.rmtree(staging)
            except Exception:
                pass
            return f"Tests failed in staging:\n{out}"

        # tests passed; either apply to live repo or return suggested command
        if apply_live:
            apply_out = patch_apply(str(z))

            # cleanup staging
            try:
                shutil.rmtree(staging)
            except Exception:
                pass

            return f"Staging tests passed. patch_apply result:\n{apply_out}"
        else:
            # cleanup staging
            try:
                shutil.rmtree(staging)
            except Exception:
                pass

            return (
                "Staging tests passed. To apply this proposal to the live repo run:\n"
                f"  teach autoapply apply {zip_path}\n"
                "Or run the suggested patch apply command directly: patch apply <zip_path>"
            )
    except Exception as e:
        return f"Autoapply failed: {e}"

    user_content = text
    if retrieved_context:
        user_content = (
            f"{text}\n\n"
            "Retrieved context (use only if relevant; if uncertain, say uncertain):\n"
            "<<<CONTEXT\n"
            f"{retrieved_context[:6000]}\n"
            ">>>"
        )

    payload = {
        "model": chat_model(),
        "stream": False,
        "options": {"temperature": 0.2, "top_p": 0.9, "repeat_penalty": 1.1},
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ],
    }

    # Primary call with one deterministic retry after a service restart
    try:
        r = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=OLLAMA_REQ_TIMEOUT)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception:
        warn("Ollama chat failed; attempting one restart and retry.")
        try:
            kill_ollama()
            time.sleep(1.2)
            start_ollama_serve_detached()
            time.sleep(1.2)
            r = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=OLLAMA_REQ_TIMEOUT)
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        except Exception as e:
            warn(f"Ollama chat final attempt failed: {e}")
            return "(error: LLM service unavailable)"


# =========================
# Voice (STT)
# =========================
def record_seconds(seconds=3):
    if not VOICE_OK or sd is None:
        raise RuntimeError(f"Voice is disabled (import error: {VOICE_IMPORT_ERR})")
    print(f"Nova: recording for {seconds} seconds... (talk now)", flush=True)
    audio = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
    )
    sd.wait()
    return audio


def transcribe(model, audio_int16):
    if not VOICE_OK or wav is None:
        raise RuntimeError(f"Voice is disabled (import error: {VOICE_IMPORT_ERR})")
    buf = io.BytesIO()
    wav.write(buf, SAMPLE_RATE, audio_int16)
    buf.seek(0)
    segments, _ = model.transcribe(buf)
    return " ".join(seg.text.strip() for seg in segments).strip()


# =========================
# Tools
# =========================
def run_tool_py(script: str, args=None) -> str:
    args = args or []
    p = subprocess.run([PYTHON, script] + args, capture_output=True, text=True)
    out = (p.stdout or "")
    if p.stderr:
        out += ("\n" + p.stderr)
    return out.strip()


def tool_screen():
    if not policy_tools_enabled().get("screen", True):
        return "Screen tool disabled by policy."
    return run_tool_py(str(BASE_DIR / "look_crop.py"))


def tool_camera(prompt: str):
    if not policy_tools_enabled().get("camera", True):
        return "Camera tool disabled by policy."
    return run_tool_py(str(BASE_DIR / "camera.py"), [prompt])


def tool_ls(subfolder=""):
    if not policy_tools_enabled().get("files", True):
        return "File tools disabled by policy."
    target = allowed_root() if not subfolder else safe_path(subfolder)
    if not target.exists() or not target.is_dir():
        return f"Not a folder: {target}"
    lines = []
    for p in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        lines.append(("DIR  " if p.is_dir() else "FILE ") + p.name)
    return "\n".join(lines)


def tool_read(path: str):
    if not policy_tools_enabled().get("files", True):
        return "File tools disabled by policy."
    p = safe_path(path)
    if not p.exists() or not p.is_file():
        return f"Not a file: {p}"
    return p.read_text(encoding="utf-8", errors="replace")


def tool_find(keyword: str, subfolder=""):
    if not policy_tools_enabled().get("files", True):
        return "File tools disabled by policy."
    start = allowed_root() if not subfolder else safe_path(subfolder)
    if not start.exists() or not start.is_dir():
        return f"Not a folder: {start}"

    exts = {".txt", ".md", ".log", ".json", ".xml", ".csv", ".ini", ".conf",
            ".php", ".js", ".ts", ".css", ".html", ".htm", ".py", ".sql"}
    hits = []
    kw = keyword.lower()

    for root, _, files in os.walk(start):
        for name in files:
            p = Path(root) / name
            if p.suffix.lower() not in exts:
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore").lower()
            except Exception:
                continue
            if kw in content:
                hits.append(str(p))

    if not hits:
        return "No matches found."
    return "Matches:\n" + "\n".join(hits[:200]) + (f"\n...and {len(hits)-200} more" if len(hits) > 200 else "")


def tool_web(url: str):
    # capability awareness check
    missing = explain_missing("web_fetch", ["web_access"])
    if missing:
        return missing
    
    if not policy_tools_enabled().get("web", False):
        return "Web tool disabled by policy."
    out = web_fetch(url, WEB_CACHE_DIR)

    if not out.get("ok"):
        err = out.get("error", "unknown error")
        # If domain blocked by allowlist, provide helpful instructions
        if isinstance(err, str) and "not allowed" in err.lower():
            return _web_allowlist_message(url)
        return f"[FAIL] {err}"
    return f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)"


def web_search(query: str, save_dir: Path, max_results: int = 5) -> dict:
    """
    Conservative web search using DuckDuckGo HTML interface.
    Saves a plain-text summary to `save_dir` and returns {ok, path, bytes}.
    This avoids JS-heavy scraping and does not require external deps.
    """
    if not web_enabled():
        return {"ok": False, "error": "Web tool disabled by policy."}

    save_dir.mkdir(parents=True, exist_ok=True)
    try:
        url = "https://html.duckduckgo.com/html/"
        r = requests.post(url, data={"q": query}, timeout=30, headers={"User-Agent": "Nova/1.0"})
    except requests.RequestException as e:
        return {"ok": False, "error": f"Search request failed: {e}"}

    try:
        r.raise_for_status()
        text = r.text or ""

        # crude parse for DuckDuckGo result links/titles (no external parser)
        entries = []
        for m in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text, re.I | re.S):
            href = m.group(1)
            title_html = m.group(2)
            title = re.sub(r'<.*?>', '', title_html).strip()
            entries.append((title, href))
            if len(entries) >= int(max_results):
                break

        ts = time.strftime("%Y%m%d_%H%M%S")
        h = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
        out_path = save_dir / f"search_{ts}_{h}.txt"

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"Search results for: {query}\n\n")
            for i, (title, href) in enumerate(entries, start=1):
                f.write(f"{i}. {title}\n   {href}\n\n")

        size = out_path.stat().st_size
        return {"ok": True, "query": query, "path": str(out_path), "bytes": int(size)}

    except Exception as e:
        return {"ok": False, "error": f"Parsing error: {e}"}


def tool_search(query: str):
    missing = explain_missing("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled().get("web", False):
        return "Web tool disabled by policy."

    out = web_search(query, WEB_CACHE_DIR, max_results=5)
    if not out.get("ok"):
        return f"[FAIL] {out.get('error', 'unknown error')}"
    return f"[OK] Saved: {out['path']} (text, {out['bytes']} bytes)"


def _decode_search_href(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""

    # DuckDuckGo style redirect: /l/?uddg=<encoded_url>
    if href.startswith("/l/?"):
        q = parse_qs(urlparse("https://duckduckgo.com" + href).query)
        u = (q.get("uddg") or [""])[0]
        return unquote(u)

    if href.startswith("http://") or href.startswith("https://"):
        return href

    return ""


def _extract_text_from_path(path: Path, max_chars: int = 2000) -> str:
    try:
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md", ".log"}:
            t = path.read_text(encoding="utf-8", errors="ignore")
            return re.sub(r"\s+", " ", t).strip()[:max_chars]

        if suffix in {".html", ".htm"}:
            raw = path.read_text(encoding="utf-8", errors="ignore")
            raw = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
            raw = re.sub(r"(?is)<style.*?>.*?</style>", " ", raw)
            raw = re.sub(r"(?is)<[^>]+>", " ", raw)
            raw = html.unescape(raw)
            return re.sub(r"\s+", " ", raw).strip()[:max_chars]

        return ""
    except Exception:
        return ""


def _extract_text_from_html_content(raw_html: str, max_chars: int = 2000) -> str:
    raw = raw_html or ""
    raw = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()[:max_chars]


def _extract_same_host_links(raw_html: str, base_url: str, host: str) -> list[str]:
    links = []
    seen = set()
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', raw_html or "", flags=re.I)
    for href in hrefs:
        href = (href or "").strip()
        if not href or href.startswith("#"):
            continue
        if href.startswith("javascript:") or href.startswith("mailto:"):
            continue

        abs_url = urljoin(base_url, href)
        p = urlparse(abs_url)
        if p.scheme not in ("http", "https"):
            continue
        if not p.hostname:
            continue
        if p.hostname.lower() != host.lower():
            continue

        clean = f"{p.scheme}://{p.netloc}{p.path}"
        if p.query:
            clean += f"?{p.query}"
        if clean in seen:
            continue
        seen.add(clean)
        links.append(clean)
    return links


def _expand_research_terms(tokens: list[str]) -> list[str]:
    terms = set(t for t in tokens if t)
    if "peims" in terms:
        terms.update({"tsds", "submission", "interchange", "student", "reporting"})
    if "attendance" in terms:
        terms.update({"ada", "attendance", "reporting"})
    if "timeline" in terms:
        terms.update({"calendar", "deadline", "dates"})
    if "reporting" in terms:
        terms.update({"submission", "report"})
    return list(terms)


def _score_research_hit(url: str, text: str, terms: list[str], primary_tokens: Optional[list[str]] = None) -> float:
    low_url = (url or "").lower()
    low_text = (text or "").lower()
    primary_tokens = [t for t in (primary_tokens or []) if t]
    p = urlparse(url or "")

    unique_text_hits = sum(1 for t in terms if t in low_text)
    unique_url_hits = sum(1 for t in terms if t in low_url)
    total_text_hits = sum(low_text.count(t) for t in terms)
    total_url_hits = sum(low_url.count(t) for t in terms)

    # Domain-specific boosts for likely data/reporting pages.
    boost_patterns = ["peims", "tsds", "attendance", "ada", "submission", "calendar", "timeline", "report", "student-data"]
    path_boost = sum(1 for p in boost_patterns if p in low_url)

    score = (
        unique_text_hits * 4.0
        + unique_url_hits * 6.0
        + min(30.0, float(total_text_hits) * 0.25)
        + min(20.0, float(total_url_hits) * 0.75)
        + path_boost * 1.5
    )

    # Penalize generic pages when none of the user's original query tokens are present.
    if primary_tokens and not any(t in low_text or t in low_url for t in primary_tokens):
        score -= 8.0

    # Strongly de-prioritize homepage if it doesn't contain primary intent terms.
    if (p.path or "/") in {"", "/"} and primary_tokens and not any(t in low_text or t in low_url for t in primary_tokens):
        score -= 12.0

    return score


def _crawl_domain_for_query(start_url: str, query_tokens: list[str], max_pages: int, max_depth: int) -> list[tuple[float, str, str]]:
    parsed = urlparse(start_url)
    host = parsed.hostname or ""
    if not host:
        return []

    terms = _expand_research_terms(query_tokens)
    q = [(start_url, 0)]
    seen = {start_url}
    fetched = 0
    hits = []

    while q and fetched < max_pages:
        url, depth = q.pop(0)

        try:
            r = requests.get(url, headers={"User-Agent": "Nova/1.0"}, timeout=25)
            r.raise_for_status()
        except Exception:
            continue

        fetched += 1
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "html" not in ctype:
            continue

        raw = r.text
        text = _extract_text_from_html_content(raw, max_chars=5000)
        score = _score_research_hit(url, text, terms, primary_tokens=query_tokens)
        if score >= 3.0:
            snippet = text[:900]
            hits.append((score, url, snippet))

        if depth >= max_depth:
            continue

        for nxt in _extract_same_host_links(raw, url, host):
            if nxt in seen:
                continue
            seen.add(nxt)
            q.append((nxt, depth + 1))

    return hits


def _scan_candidate_urls_for_query(urls: list[str], query_tokens: list[str], max_pages: int, min_score: float = 3.0) -> list[tuple[float, str, str]]:
    terms = _expand_research_terms(query_tokens)

    def _url_candidate_score(u: str) -> float:
        low = (u or "").lower()
        p = urlparse(u)
        score = 0.0
        for t in terms:
            score += low.count(t) * 2.0
        for k in ("peims", "tsds", "attendance", "ada", "submission", "calendar", "timeline", "report", "student-data"):
            if k in low:
                score += 3.0
        # Prefer content pages over domain root index pages.
        if (p.path or "/") in {"", "/"}:
            score -= 2.0
        # De-prioritize non-html document links during candidate scan.
        if re.search(r"\.(pdf|docx?|xlsx?|pptx?)($|\?)", low):
            score -= 4.0
        return score

    ranked_urls = sorted(urls, key=_url_candidate_score, reverse=True)

    hits = []
    scanned = 0

    for url in ranked_urls:
        if scanned >= max_pages:
            break
        try:
            r = requests.get(url, headers={"User-Agent": "Nova/1.0"}, timeout=20)
            r.raise_for_status()
        except Exception:
            continue

        ctype = (r.headers.get("Content-Type") or "").lower()
        scanned += 1

        if "html" in ctype:
            text = _extract_text_from_html_content(r.text, max_chars=5000)
            score = _score_research_hit(url, text, terms, primary_tokens=query_tokens)
            if score >= min_score:
                hits.append((score, url, text[:900]))
        else:
            # Keep high-relevance document links (pdf/doc/xls/etc.) as sources.
            score = _score_research_hit(url, "", terms, primary_tokens=query_tokens)
            if score >= min_score:
                snippet = f"Non-HTML source ({ctype or 'unknown'}). Use web gather <url> to fetch and inspect."
                hits.append((score, url, snippet))

    return hits


def _fetch_sitemap_urls(domain: str, limit: int = 80) -> list[str]:
    urls = []
    seen = set()
    seen_sitemaps = set()
    queue = [f"https://{domain}/sitemap.xml", f"https://{domain}/sitemap_index.xml"]

    while queue and len(urls) < limit:
        sm = queue.pop(0)
        if sm in seen_sitemaps:
            continue
        seen_sitemaps.add(sm)

        try:
            r = requests.get(sm, headers={"User-Agent": "Nova/1.0"}, timeout=20)
            if r.status_code != 200:
                continue
            body = r.text
            locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", body, flags=re.I)
            for u in locs:
                u = html.unescape((u or "").strip())
                p = urlparse(u)
                if p.scheme not in ("http", "https"):
                    continue
                if not p.hostname:
                    continue
                if not _host_allowed(p.hostname, [domain]):
                    continue

                clean = f"{p.scheme}://{p.netloc}{p.path}"
                if p.query:
                    clean += f"?{p.query}"

                # Nested sitemap index entries often point to other XML sitemap files,
                # including forms like sitemap.xml?page=2.
                if Path(p.path).suffix.lower() == ".xml":
                    if clean not in seen_sitemaps:
                        queue.append(clean)
                    continue

                if clean in seen:
                    continue
                seen.add(clean)
                urls.append(clean)
                if len(urls) >= limit:
                    break
        except Exception:
            continue

    return urls


def _seed_urls_for_domain(domain: str, query_tokens: list[str], max_seed: int = 30) -> list[str]:
    seeds = [f"https://{domain}/"]
    candidates = _fetch_sitemap_urls(domain, limit=max_seed * 3)
    if not candidates:
        return seeds

    terms = _expand_research_terms(query_tokens)
    scored = []
    for u in candidates:
        low = u.lower()
        score = sum(low.count(t) for t in terms)
        for p in ("peims", "tsds", "attendance", "ada", "submission", "calendar", "timeline", "report"):
            if p in low:
                score += 2
        if score > 0:
            scored.append((score, u))

    scored.sort(key=lambda x: x[0], reverse=True)
    for _, u in scored[:max_seed]:
        if u not in seeds:
            seeds.append(u)

    # Fill remaining seed slots with earliest sitemap URLs even if token score is zero,
    # so we still traverse deeper pages when URL text doesn't contain query tokens.
    if len(seeds) < (max_seed + 1):
        for u in candidates:
            if u in seeds:
                continue
            seeds.append(u)
            if len(seeds) >= (max_seed + 1):
                break
    return seeds


def tool_web_search(query: str):
    missing = explain_missing("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled().get("web", False):
        return "Web tool disabled by policy."
    if not web_enabled():
        return "Web tool disabled by policy."

    cfg = policy_web()
    allow_domains = cfg.get("allow_domains") or []
    if not allow_domains:
        return "Web search unavailable: no allow_domains configured in policy."

    q = (query or "").strip()
    if not q:
        return "Usage: web search <query>"

    def _search_via_api(query_text: str, domains: list[str], max_results: int = 5) -> tuple[list[tuple[str, str]], Optional[str]]:
        provider = str(cfg.get("search_provider") or "").strip().lower()
        if provider not in {"brave", "searxng"}:
            return ([], None)

        scoped_query = query_text + " " + " ".join(f"site:{d}" for d in domains[:8])

        if provider == "brave":
            key_env = str(cfg.get("search_api_key_env") or "BRAVE_SEARCH_API_KEY").strip() or "BRAVE_SEARCH_API_KEY"
            api_key = (os.environ.get(key_env) or "").strip()
            if not api_key:
                return ([], f"missing_api_key_env:{key_env}")

            endpoint = str(cfg.get("search_api_endpoint") or "https://api.search.brave.com/res/v1/web/search").strip()
            try:
                r = requests.get(
                    endpoint,
                    params={"q": scoped_query, "count": max(1, min(20, int(max_results)))},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": api_key,
                        "User-Agent": "Nova/1.0",
                    },
                    timeout=30,
                )
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                return ([], f"api_error:{e}")

            items = []
            for it in ((data.get("web") or {}).get("results") or []):
                url = str(it.get("url") or "").strip()
                title = str(it.get("title") or "").strip() or url
                if not url:
                    continue
                host = urlparse(url).hostname or ""
                if not _host_allowed(host, domains):
                    continue
                items.append((title, url))
                if len(items) >= max_results:
                    break
            return (items, None)

        # searxng provider: self-hosted instance, no API key required.
        endpoint = str(cfg.get("search_api_endpoint") or "http://127.0.0.1:8080/search").strip()
        try:
            r = requests.get(
                endpoint,
                params={"q": scoped_query, "format": "json"},
                headers={"Accept": "application/json", "User-Agent": "Nova/1.0"},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return ([], f"api_error:{e}")

        items = []
        for it in (data.get("results") or []):
            url = str(it.get("url") or "").strip()
            title = str(it.get("title") or "").strip() or url
            if not url:
                continue
            host = urlparse(url).hostname or ""
            if not _host_allowed(host, domains):
                continue
            items.append((title, url))
            if len(items) >= max_results:
                break
        return (items, None)

    def _search_via_html(query_text: str, domains: list[str], max_results: int = 5) -> tuple[list[tuple[str, str]], Optional[str]]:
        scoped_query = query_text + " " + " ".join(f"site:{d}" for d in domains[:6])
        try:
            r = requests.get(
                "https://duckduckgo.com/html/",
                params={"q": scoped_query},
                headers={"User-Agent": "Nova/1.0"},
                timeout=30,
            )
            r.raise_for_status()
            page = r.text
        except Exception as e:
            return ([], f"html_error:{e}")

        hrefs = re.findall(r'href=["\']([^"\']+)["\']', page, flags=re.I)
        direct_urls = re.findall(r"https?://[^\s\"'<>]+", page)
        seen = set()
        urls = []
        for h in hrefs:
            u = _decode_search_href(h)
            if not u:
                continue
            host = urlparse(u).hostname or ""
            if not _host_allowed(host, domains):
                continue
            if u in seen:
                continue
            seen.add(u)
            urls.append((u, u))
            if len(urls) >= max_results:
                break

        if len(urls) < max_results:
            for u in direct_urls:
                host = urlparse(u).hostname or ""
                if not _host_allowed(host, domains):
                    continue
                if u in seen:
                    continue
                seen.add(u)
                urls.append((u, u))
                if len(urls) >= max_results:
                    break
        return (urls, None)

    provider = str(cfg.get("search_provider") or "").strip().lower()
    rows, api_err = _search_via_api(q, allow_domains, max_results=5)
    provider_used = f"api:{provider}" if rows else "html"
    if not rows:
        rows, html_err = _search_via_html(q, allow_domains, max_results=5)
        if not rows and api_err:
            return f"[FAIL] Web search unavailable. API reason={api_err}; HTML fallback failed={html_err}"

    if not rows:
        msg = "No allowlisted web results found for that query."
        # Offer a helpful allowlist explanation
        msg += "\n\n" + _web_allowlist_message(query)
        return msg

    lines = [f"Web results (allowlisted, provider={provider_used}):"]
    for i, (title, u) in enumerate(rows, start=1):
        if title and title != u:
            lines.append(f"{i}. {title}")
            lines.append(f"   {u}")
        else:
            lines.append(f"{i}. {u}")
    lines.append("Tip: run 'web gather <url>' to fetch and summarize one result.")
    return "\n".join(lines)


def tool_web_gather(url: str):
    missing = explain_missing("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled().get("web", False):
        return "Web tool disabled by policy."

    out = web_fetch(url, WEB_CACHE_DIR)
    if not out.get("ok"):
        err = out.get("error", "unknown error")
        if isinstance(err, str) and "not allowed" in err.lower():
            return _web_allowlist_message(url)
        return f"[FAIL] {err}"

    p = Path(out["path"])
    snippet = _extract_text_from_path(p, max_chars=2200)
    if snippet:
        return (
            f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)\n"
            f"Summary snippet:\n{snippet}"
        )

    ctype = str(out.get("content_type") or "").lower()
    if "html" in ctype:
        return (
            f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)\n"
            "I could access the page, but I couldn't extract readable content. "
            "It may be JavaScript-heavy/dynamic, and I do not run a browser renderer in this path."
        )

    return f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)"


def tool_web_research(query: str, continue_mode: bool = False):
    global WEB_RESEARCH_LAST_QUERY, WEB_RESEARCH_LAST_RESULTS, WEB_RESEARCH_CURSOR

    missing = explain_missing("web_fetch", ["web_access"])
    if missing:
        return missing

    if not policy_tools_enabled().get("web", False):
        return "Web tool disabled by policy."
    if not web_enabled():
        return "Web tool disabled by policy."

    cfg = policy_web()
    allow_domains = cfg.get("allow_domains") or []
    if not allow_domains:
        return "Web research unavailable: no allow_domains configured in policy."

    q = (query or "").strip()
    if continue_mode:
        if not WEB_RESEARCH_LAST_RESULTS:
            return "No active web research session. Start with: web research <query>"

        max_results = max(1, min(40, int((policy_web().get("research_max_results") or 8))))
        start = WEB_RESEARCH_CURSOR
        end = min(len(WEB_RESEARCH_LAST_RESULTS), start + max_results)
        if start >= len(WEB_RESEARCH_LAST_RESULTS):
            return "No more cached research results. Start a new search with: web research <query>"

        lines = [f"Web research results (continued) for: {WEB_RESEARCH_LAST_QUERY}"]
        rank = start
        for score, url, snippet in WEB_RESEARCH_LAST_RESULTS[start:end]:
            rank += 1
            lines.append(f"{rank}. [{score:.1f}] {url}")
            if snippet:
                lines.append(f"   {snippet[:220]}")

        WEB_RESEARCH_CURSOR = end
        if WEB_RESEARCH_CURSOR < len(WEB_RESEARCH_LAST_RESULTS):
            remaining = len(WEB_RESEARCH_LAST_RESULTS) - WEB_RESEARCH_CURSOR
            lines.append(f"{remaining} more result(s) available. Type 'web continue' to keep going.")
        else:
            lines.append("End of cached research results.")

        lines.append("Tip: run 'web gather <url>' for any source above to fetch and summarize it fully.")
        return "\n".join(lines)

    if not q:
        return "Usage: web research <query>"

    toks = _tokenize(q)
    if not toks:
        return "Query too short for web research."

    domains_limit = max(1, min(12, int(cfg.get("research_domains_limit") or 4)))
    pages_per_domain = max(2, min(50, int(cfg.get("research_pages_per_domain") or 8)))
    max_depth = max(0, min(3, int(cfg.get("research_max_depth") or 1)))
    max_results = max(1, min(40, int(cfg.get("research_max_results") or 8)))
    seeds_per_domain = max(1, min(40, int(cfg.get("research_seeds_per_domain") or 8)))
    scan_pages_per_domain = max(2, min(200, int(cfg.get("research_scan_pages_per_domain") or 12)))
    min_score = max(0.0, min(10.0, float(cfg.get("research_min_score") or 3.0)))

    domains = allow_domains[:max(1, min(domains_limit, len(allow_domains)))]
    all_hits = []
    for d in domains:
        sitemap_urls = _fetch_sitemap_urls(d, limit=max(200, scan_pages_per_domain * 25))
        if sitemap_urls:
            all_hits.extend(_scan_candidate_urls_for_query(sitemap_urls, toks, max_pages=max(2, scan_pages_per_domain), min_score=min_score))

        seeds = _seed_urls_for_domain(d, toks, max_seed=max(1, seeds_per_domain))
        for start in seeds:
            all_hits.extend(_crawl_domain_for_query(start, toks, max_pages=max(2, pages_per_domain), max_depth=max(0, max_depth)))

    if not all_hits:
        return "No relevant pages found across allowlisted domains for that query."

    all_hits.sort(key=lambda x: x[0], reverse=True)
    used = set()
    ordered = []
    for score, url, snippet in all_hits:
        if url in used:
            continue
        used.add(url)
        ordered.append((score, url, snippet))

    WEB_RESEARCH_LAST_QUERY = q
    WEB_RESEARCH_LAST_RESULTS = ordered
    WEB_RESEARCH_CURSOR = 0

    max_results = max(1, min(40, int((cfg.get("research_max_results") or 8))))
    start = WEB_RESEARCH_CURSOR
    end = min(len(WEB_RESEARCH_LAST_RESULTS), start + max_results)

    lines = [f"Web research results (allowlisted crawl) for: {q}"]
    rank = start
    for score, url, snippet in WEB_RESEARCH_LAST_RESULTS[start:end]:
        rank += 1
        lines.append(f"{rank}. [{score:.1f}] {url}")
        if snippet:
            lines.append(f"   {snippet[:220]}")

    WEB_RESEARCH_CURSOR = end
    if WEB_RESEARCH_CURSOR < len(WEB_RESEARCH_LAST_RESULTS):
        remaining = len(WEB_RESEARCH_LAST_RESULTS) - WEB_RESEARCH_CURSOR
        lines.append(f"{remaining} more result(s) available. Type 'web continue' to keep going.")
    else:
        lines.append("No more results pending for this query.")

    lines.append("Tip: run 'web gather <url>' for any source above to fetch and summarize it fully.")
    return "\n".join(lines)


def handle_keywords(text: str):
    low = text.lower().strip()

    if low in {"screen", "look at my screen"}:
        return ("tool", tool_screen())

    if low.startswith("camera"):
        prompt = text[len("camera"):].strip() or "what do you see"
        return ("tool", tool_camera(prompt))

    if low.startswith("web research "):
        q = text.split(maxsplit=2)[2].strip() if len(text.split(maxsplit=2)) >= 3 else ""
        return ("tool", tool_web_research(q))

    if low in {"web continue", "continue web", "continue web research"}:
        return ("tool", tool_web_research("", continue_mode=True))

    if low.startswith("web search "):
        q = text.split(maxsplit=2)[2].strip() if len(text.split(maxsplit=2)) >= 3 else ""
        return ("tool", tool_web_search(q))

    # shorthand: `search <query>` -> conservative DuckDuckGo search (saves summary)
    if low.startswith("search "):
        q = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) >= 2 else ""
        return ("tool", tool_search(q))

    # shorthand: `findweb <query>` -> quick allowlisted web search (returns URLs)
    if low.startswith("findweb "):
        q = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) >= 2 else ""
        return ("tool", tool_web_search(q))

    if low.startswith("web gather "):
        url = text.split(maxsplit=2)[2].strip() if len(text.split(maxsplit=2)) >= 3 else ""
        return ("tool", tool_web_gather(url))

    if low.startswith("web "):
        url = text.split(maxsplit=1)[1].strip()
        return ("tool", tool_web(url))

    if low.startswith("ls"):
        parts = text.split(maxsplit=1)
        sub = parts[1] if len(parts) > 1 else ""
        return ("tool", tool_ls(sub))

    if low.startswith("read "):
        path = text.split(maxsplit=1)[1]
        return ("tool", tool_read(path))

    if low.startswith("find "):
        parts = text.split(maxsplit=2)
        keyword = parts[1] if len(parts) > 1 else ""
        folder = parts[2] if len(parts) > 2 else ""
        return ("tool", tool_find(keyword, folder))

    if low in {"health", "status"}:
        hp = BASE_DIR / "health.py"
        if hp.exists():
            return ("tool", run_tool_py(str(hp), ["check"]))
        return ("tool", "health.py not found.")

    return None


# =========================
# Commands (typed) for kb / patch
# =========================
def handle_commands(user_text: str, session_turns: Optional[list[tuple[str, str]]] = None) -> Optional[str]:
    t = _strip_invocation_prefix((user_text or "").strip())
    low = t.lower()

    # Natural follow-up variants such as "use your location nova" should resolve deterministically.
    if ("use your" in low or low.startswith("use ")) and _mentions_location_phrase(low):
        return tool_weather("brownsville")

    if low in {"use your physical location", "use your location", "use default location", "default location"}:
        return tool_weather("brownsville")

    # Natural weather requests should stay deterministic and not fall through to LLM.
    if "weather" in low and not low.startswith("web "):
        if "your" in low and _mentions_location_phrase(low):
            return tool_weather("brownsville")
        if any(p in low for p in ["give me", "check", "show", "tell me", "what is", "what's", "today", "now", "current"]):
            coords = _coords_from_saved_location()
            if coords:
                lat, lon = coords
                return tool_weather(f"{lat},{lon}")
            return _need_confirmed_location_message() + " You can set one with: location coords <lat,lon>"

    if low in {"chat context", "show chat context", "context", "chatctx"}:
        rendered = _render_chat_context(session_turns or [])
        if not rendered:
            return "No chat context is available yet in this session."
        return "Current chat context:\n" + rendered

    if "domanins" in low and any(k in low for k in ["domain", "domanins", "allow", "policy", "list", "show"]):
        return "It looks like you meant \"domains\".\n" + list_allowed_domains()

    if low in {"domains", "list domains", "show domains", "list the domains", "allowed domains", "allow domains", "policy domains"}:
        return list_allowed_domains()

    if low.startswith("policy allow "):
        value = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return policy_allow_domain(value)

    if low.startswith("policy remove "):
        value = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return policy_remove_domain(value)

    if low.startswith("policy audit"):
        parts = t.split()
        n = 20
        if len(parts) >= 3:
            try:
                n = int(parts[2])
            except Exception:
                n = 20
        return policy_audit(n)

    if low in {"web mode", "web limits", "web research limits"}:
        return web_mode_status()

    if low.startswith("web mode "):
        mode = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return set_web_mode(mode)

    if low.startswith("location coords ") or low.startswith("set location coords "):
        raw = t
        if low.startswith("set location coords "):
            raw = t[len("set location coords "):].strip()
        else:
            raw = t[len("location coords "):].strip()
        return set_location_coords(raw)

    if low in {"weather", "check weather", "weather current location", "weather current"}:
        coords = _coords_from_saved_location()
        if not coords:
            return _need_confirmed_location_message()
        lat, lon = coords
        return tool_weather(f"{lat},{lon}")

    if low.startswith("weather ") or low.startswith("check weather "):
        parts = t.split(maxsplit=2)
        loc = ""
        if low.startswith("check weather ") and len(parts) >= 3:
            loc = parts[2].strip()
        elif low.startswith("weather ") and len(parts) >= 2:
            loc = t.split(maxsplit=1)[1].strip()
        return tool_weather(loc)

    if low.startswith("remember:"):
        return mem_remember_fact(t.split(":", 1)[1])

    if low in {"what can you do", "capabilities", "show capabilities"}:
        return describe_capabilities()

    if low in {"mem stats", "memory stats"}:
        return mem_stats()

    if low.startswith("mem audit ") or low.startswith("memory audit "):
        q = t.split(maxsplit=2)[2] if len(t.split(maxsplit=2)) >= 3 else ""
        return mem_audit(q)

    if low == "kb" or low == "kb help":
        return ("KB commands:\n"
                "  kb list\n"
                "  kb use <pack>\n"
                "  kb off\n"
                "  kb add <zip_path> <pack_name>\n")

    if low == "kb list":
        return kb_list_packs()

    if low.startswith("kb use "):
        name = t.split(maxsplit=2)[2].strip()
        return kb_set_active(name)

    if low == "kb off":
        return kb_set_active(None)

    if low.startswith("kb add "):
        parts = t.split(maxsplit=3)
        if len(parts) < 4:
            return "Usage: kb add <zip_path> <pack_name>"
        return kb_add_zip(parts[2], parts[3])

    if low == "patch" or low == "patch help":
        return ("Patch commands:\n"
            "  patch preview <zip_path>  # preview proposal without applying\n"
            "  patch apply <zip_path> [--force]\n"
            "      # preview runs automatically; use --force to bypass preview check\n"
            "  patch rollback   (roll back to last snapshot)\n"
            )
    if low.startswith("patch apply "):
        raw = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        # detect --force flag
        force = False
        if "--force" in raw:
            force = True
            raw = raw.replace("--force", "").strip()
        return patch_apply(raw, force=force)

    if low.startswith("patch preview "):
        p = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return patch_preview(p)

    if low == "patch list-previews":
        return list_previews()

    if low.startswith("patch show "):
        p = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return show_preview(p)

    if low.startswith("patch approve "):
        p = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return approve_preview(p)

    if low.startswith("patch reject "):
        p = t.split(maxsplit=2)[2].strip() if len(t.split(maxsplit=2)) >= 3 else ""
        return reject_preview(p)

    if low == "patch rollback":
        return patch_rollback()

    # Teach workflow: remember examples and propose patches
    if low.startswith("teach "):
        parts = t.split(maxsplit=1)
        sub = parts[1].strip() if len(parts) > 1 else ""
        if sub.startswith("remember "):
            # format: teach remember <orig> => <correction>
            body = sub[len("remember "):].strip()
            if "=>" in body:
                orig, corr = body.split("=>", 1)
                orig = orig.strip().strip("\"'")
                corr = corr.strip().strip("\"'")
                return _teach_store_example(orig, corr)
            return "Usage: teach remember <original text> => <correction text>"

        if sub == "list":
            return _teach_list_examples()

        if sub.startswith("propose"):
            desc = sub[len("propose"):].strip()
            return _teach_propose_patch(desc)

        if sub.startswith("autoapply "):
            body = sub[len("autoapply "):].strip()
            # support: "autoapply <zip>" (dry-run/staging only)
            # and: "autoapply apply <zip>" or "autoapply <zip> --apply" to actually apply
            apply_live = False
            zp = body
            if body.startswith("apply "):
                apply_live = True
                zp = body[len("apply "):].strip()
            elif "--apply" in body:
                apply_live = True
                zp = body.replace("--apply", "").strip()
            return _teach_autoapply_proposal(zp, apply_live=apply_live)

        if sub.startswith("apply "):
            zp = sub[len("apply "):].strip()
            # direct apply (no staging tests) — still uses patch_apply
            return patch_apply(zp)

        return ("Teach commands:\n"
            "  teach remember <orig> => <correction>\n"
            "  teach list\n"
            "  teach propose <description>\n"
            "  teach autoapply <zip>              # run staging tests (safe)\n"
            "  teach autoapply apply <zip>       # run staging tests and APPLY if tests pass\n"
            "  teach autoapply <zip> --apply     # same as above\n"
    )
    if low == "inspect":
        data = inspect_environment()
        return format_report(data)

    # casual_mode control: casual_mode status|on|off|toggle
    if low.startswith("casual_mode") or low.startswith("casual mode"):
        parts = low.replace("casual mode", "casual_mode").split()
        cmd = parts[1] if len(parts) > 1 else "status"
        statefile = DEFAULT_STATEFILE
        try:
            if cmd in {"on", "1", "true"}:
                os.environ["CASUAL_MODE"] = "1"
                set_core_state(statefile, "casual_mode", True)
                return "casual_mode enabled"
            if cmd in {"off", "0", "false"}:
                os.environ["CASUAL_MODE"] = "0"
                set_core_state(statefile, "casual_mode", False)
                return "casual_mode disabled"
            if cmd == "toggle":
                cur = os.environ.get("CASUAL_MODE", "1").lower() in {"1", "true"}
                nxt = not cur
                os.environ["CASUAL_MODE"] = "1" if nxt else "0"
                set_core_state(statefile, "casual_mode", bool(nxt))
                return f"casual_mode set to {os.environ['CASUAL_MODE']}"
            # status
            cur = os.environ.get("CASUAL_MODE", "1")
            return f"casual_mode={cur}"
        except Exception as e:
            return f"Failed to set casual_mode: {e}"

    return None


# =========================
# Main loop
# =========================
def run_loop(tts):
    whisper = None
    if VOICE_OK and WhisperModel is not None:
        print("Nova Core: loading Whisper (CPU mode)...", flush=True)
        whisper = WhisperModel(whisper_size(), device="cpu", compute_type="int8")
    else:
        warn(f"Voice mode disabled; typed chat still works. (Reason: {VOICE_IMPORT_ERR})")

    print("\nNova Core is ready.", flush=True)
    print("Commands: screen | camera <prompt> | web <url> | web search <query> | web research <query> | web gather <url> | weather <location-or-lat,lon> | check weather <location> | weather current location | location coords <lat,lon> | domains | policy allow <domain> | chat context | ls [folder] | read <file> | find <kw> [folder] | health | capabilities | inspect", flush=True)
    print("Press ENTER for voice. Or type a message/command and press ENTER. Type 'q' to quit.\n", flush=True)

    recent_tool_context = ""
    recent_web_urls: list[str] = []
    session_turns: list[tuple[str, str]] = []

    while True:
        raw = input("> ").strip()
        input_source = "typed"

        if raw.lower() == "q":
            break

        if raw:
            user_text = raw
            m_idx = re.match(r"^\s*web\s+gather\s+(\d+)\s*$", user_text, flags=re.I)
            if m_idx and recent_web_urls:
                idx = int(m_idx.group(1))
                if 1 <= idx <= len(recent_web_urls):
                    user_text = f"web gather {recent_web_urls[idx - 1]}"
            user_text = _strip_invocation_prefix(user_text)
            print(f"You (typed): {user_text}", flush=True)
        else:
            input_source = "voice"
            if not whisper:
                print("Nova: voice is disabled on this machine right now. Type your message instead.\n", flush=True)
                continue
            audio = record_seconds(RECORD_SECONDS)
            print("Nova: transcribing...", flush=True)
            user_text = transcribe(whisper, audio)
            if not user_text:
                print("Nova: (heard nothing)\n", flush=True)
                continue
            user_text = _strip_invocation_prefix(user_text)
            print(f"You: {user_text}", flush=True)

        session_turns.append(("user", user_text))

        # Interactive correction capture: if the user provides a correction like
        # "no — say 'Hi Gus' instead" or "say 'Hi Gus' instead", store it as a teach example.
        try:
            corr_text = (user_text or "").strip()
            # find last assistant message
            last_assistant = None
            for role, txt in reversed(session_turns[:-1]):
                if role == "assistant":
                    last_assistant = txt
                    break

            if last_assistant:
                corr = _parse_correction(corr_text)
                if corr:
                    _teach_store_example(last_assistant, corr, user=get_active_user() or None)
                    ack = "Thanks — I'll prefer that reply in future. I've stored the example."
                    print(f"Nova: {ack}\n", flush=True)
                    session_turns.append(("assistant", ack))
                    speak_chunked(tts, ack)
                    continue
        except Exception:
            pass

        # Quick greeting fast-path (avoid LLM for simple salutations)
        try:
            low_q = (user_text or "").strip().lower()
            msg = _build_greeting_reply(low_q, active_user=get_active_user() or "")
            if msg:

                # Apply any stored reply overrides before sending
                try:
                    final = _apply_reply_overrides(msg)
                except Exception:
                    final = msg
                final = _ensure_reply(final)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

        # Memory summary / operator query: handle without sending to LLM
        try:
            low_q = (user_text or "").strip().lower()
            if low_q.startswith("what else do you remember") or low_q.startswith("what do you remember") or "what else do you remember" in low_q:
                stats = mem_stats()
                brief = "I remember a few things about our conversations and some saved facts."
                # include a short stats line if available
                if stats and "No memory" not in stats:
                    brief += " " + (stats.splitlines()[0] if stats else "")
                brief += " You can ask me to audit specific items, e.g. 'mem audit location'."
                final = _ensure_reply(brief)
                session_turns.append(("assistant", final))
                print(f"Nova: {final}\n", flush=True)
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

        # Natural 'remember X' intent: ask a friendly follow-up
        try:
            m = re.match(r"^remember\s+(.+)$", (user_text or "").strip(), flags=re.I)
            if m:
                subj = m.group(1).strip().strip('.!?,')
                if subj:
                    q = f"What would you like me to remember about {subj}?"
                    final = _ensure_reply(q)
                    session_turns.append(("assistant", final))
                    print(f"Nova: {final}\n", flush=True)
                    speak_chunked(tts, final)
                    continue
        except Exception:
            pass

        # Auto-capture simple identity phrases and store to memory so Nova can tie
        # future conversation to the correct user. Matches: "my name is X", "i am X", "i'm X", "this is X".
        try:
            # Only capture explicit identity phrases to avoid false positives.
            id_m = re.match(r"^(?:my name is|my name's|call me|you can call me|this is)\s+(.+)$", user_text.strip(), flags=re.I)
            if id_m:
                name = id_m.group(1).strip().strip(".!,")
                if name:
                    mem_add("profile", input_source, f"name: {name}")
                    set_active_user(name)
                    ack = f"Nice to meet you, {name}. I'll remember that and use that identity for this session."
                    print(f"Nova: {ack}\n", flush=True)
                    session_turns.append(("assistant", ack))
                    speak_chunked(tts, ack)
                    continue
        except Exception:
            pass

        # Quick replies for explicit location queries using stored memory
        try:
            low_q = (user_text or "").strip().lower()

            # WEATHER quick-path: if user asks about weather in 'your location', use stored location without invoking LLM
            if "weather" in low_q:
                if "your location" in low_q:
                    try:
                        audit_out = mem_audit("location")
                        j = json.loads(audit_out) if audit_out else {}
                        results = j.get("results") if isinstance(j, dict) else None
                        if results and len(results) > 0:
                            coords = _coords_from_saved_location()
                            if coords:
                                lat, lon = coords
                                msg = tool_weather(f"{lat},{lon}")
                            else:
                                msg = _need_confirmed_location_message()
                        else:
                            msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"
                    except Exception:
                        msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"

                    try:
                        final = _apply_reply_overrides(msg)
                    except Exception:
                        final = msg
                    final = _ensure_reply(final)
                    print(f"Nova: {final}\n", flush=True)
                    session_turns.append(("assistant", final))
                    speak_chunked(tts, final)
                    continue

                # If user asked 'weather in <place>' try to extract a place and respond directly (no LLM)
                m = re.search(r"weather in ([a-z0-9 ,.-]+)", low_q)
                if m:
                    place = m.group(1).strip()
                    msg = tool_weather(place)
                    try:
                        final = _apply_reply_overrides(msg)
                    except Exception:
                        final = msg
                    print(f"Nova: {final}\n", flush=True)
                    session_turns.append(("assistant", final))
                    speak_chunked(tts, final)
                    continue

                # For generic weather questions, be explicit about capability status.
                if any(x in low_q for x in ["what is the weather", "what's the weather", "weather today", "weather now"]):
                    if not _weather_source_host():
                        msg = _weather_unavailable_message()
                    else:
                        msg = "Tell me a location/coordinates and run: weather <location-or-lat,lon>."
                    try:
                        final = _apply_reply_overrides(msg)
                    except Exception:
                        final = msg
                    final = _ensure_reply(final)
                    print(f"Nova: {final}\n", flush=True)
                    session_turns.append(("assistant", final))
                    speak_chunked(tts, final)
                    continue

            # Follow-up/expansion triggers (ask for more info about location)
            expand_triggers = ["what else", "other information", "anything else", "more about", "what other", "anything more"]
            if "location" in low_q and any(t in low_q for t in expand_triggers):
                try:
                    audit_out = mem_audit("location")
                    j = json.loads(audit_out) if audit_out else {}
                    results = j.get("results") if isinstance(j, dict) else []
                    previews = []
                    seen = set()
                    for r in results:
                        p = (r.get("preview") or "").strip()
                        n = re.sub(r"\W+", " ", p.lower()).strip()
                        if not p or n in seen:
                            continue
                        seen.add(n)
                        previews.append(p)

                    if not previews:
                        msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"
                    elif len(previews) == 1:
                        msg = f"I only have one stored location fact right now: {_normalize_location_preview(previews[0])}"
                    else:
                        # summarize up to 3 entries
                        summary = "; ".join(_normalize_location_preview(p) for p in previews[:3])
                        msg = f"I have multiple stored location facts: {summary}"
                except Exception:
                    msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"

                try:
                    final = _apply_reply_overrides(msg)
                except Exception:
                    final = msg
                final = _ensure_reply(final)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue

            # Primary direct-location triggers: only match if input starts with a direct phrasing
            loc_triggers = [
                "what is your location",
                "where are you located",
                "where are you",
                "what is your location nova",
            ]
            if any(low_q.startswith(t) for t in loc_triggers):
                # Use mem_audit (JSON) to pick a single canonical memory result
                try:
                    audit_out = mem_audit("location")
                    j = json.loads(audit_out) if audit_out else {}
                    results = j.get("results") if isinstance(j, dict) else None
                    if results and len(results) > 0:
                        top = results[0]
                        preview = _normalize_location_preview((top.get("preview") or "").strip())
                        # Only include debug source metadata when NOVA_DEBUG=1
                        include_source = os.environ.get("NOVA_DEBUG") == "1"
                        msg = f"My location is {preview}."
                        if include_source:
                            source = (top.get("source") or "").strip()
                            if source:
                                msg += f" (source: {source})"
                    else:
                        msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"
                except Exception:
                    msg = "I don't have a stored location yet. You can tell me: 'My location is ...'"

                try:
                    final = _apply_reply_overrides(msg)
                except Exception:
                    final = msg
                final = _ensure_reply(final)
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue
        except Exception:
            pass

        # Treat declarative info (not requests) as facts to store and acknowledge.
        try:
            if _is_declarative_info(user_text):
                if mem_should_store(user_text):
                    mem_add("fact", input_source, user_text)
                # Soften casual acknowledgements
                ack = "Noted."
                print(f"Nova: {ack}\n", flush=True)
                session_turns.append(("assistant", ack))
                speak_chunked(tts, ack)
                continue
        except Exception:
            pass

        cmd_out = handle_commands(user_text, session_turns=session_turns)
        if cmd_out:
            print(f"Nova: {cmd_out}\n", flush=True)
            session_turns.append(("assistant", cmd_out))
            speak_chunked(tts, cmd_out)
            continue

        routed = handle_keywords(user_text)
        if routed:
            _, out = routed
            print(f"Nova (tool output):\n{out}\n", flush=True)
            if isinstance(out, str) and out.strip():
                recent_tool_context = out.strip()[:2500]
                recent_web_urls = _extract_urls(out)
                session_turns.append(("assistant", out.strip()[:350]))
            tts.say("Done.")
            continue

        ha = hard_answer(user_text)
        if ha:
            try:
                final = _apply_reply_overrides(ha)
            except Exception:
                final = ha
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        if _is_color_lookup_request(user_text):
            prefs = _extract_color_preferences(session_turns)
            if not prefs:
                prefs = _extract_color_preferences_from_memory()
            if prefs:
                if len(prefs) == 1:
                    msg = f"You told me you like the color {prefs[0]}."
                else:
                    msg = "You told me you like these colors: " + ", ".join(prefs[:-1]) + f", and {prefs[-1]}."
            else:
                msg = "You haven't told me a color preference in this current chat yet."
            try:
                final = _apply_reply_overrides(msg)
            except Exception:
                final = msg
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        if _is_developer_color_lookup_request(user_text):
            prefs = _extract_developer_color_preferences(session_turns)
            if not prefs:
                prefs = _extract_developer_color_preferences_from_memory()
            if prefs:
                if len(prefs) == 1:
                    msg = f"From what you've told me, Gus likes {prefs[0]}."
                else:
                    msg = "From what you've told me, Gus likes these colors: " + ", ".join(prefs[:-1]) + f", and {prefs[-1]}."
            else:
                msg = "I don't have Gus's color preferences yet."
            try:
                final = _apply_reply_overrides(msg)
            except Exception:
                final = msg
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        if _is_developer_bilingual_request(user_text):
            known = _developer_is_bilingual(session_turns)
            if known is None:
                known = _developer_is_bilingual_from_memory()
            if known is True:
                msg = "Yes. From what you've told me, Gus is bilingual in English and Spanish."
            elif known is False:
                msg = "From what I have, Gus is not bilingual."
            else:
                msg = "I don't have confirmed language details for Gus yet."
            try:
                final = _apply_reply_overrides(msg)
            except Exception:
                final = msg
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        low_user = (user_text or "").lower()
        if "what animals do i like" in low_user or "which animals do i like" in low_user:
            animals = _extract_animal_preferences(session_turns)
            if not animals:
                animals = _extract_animal_preferences_from_memory()
            if animals:
                if len(animals) == 1:
                    msg = f"You told me you like {animals[0]}."
                else:
                    msg = "You told me you like: " + ", ".join(animals[:-1]) + f", and {animals[-1]}."
            else:
                msg = "You haven't told me animal preferences yet in this chat, and I can't find them in saved memory."
            try:
                final = _apply_reply_overrides(msg)
            except Exception:
                final = msg
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        if _is_color_animal_match_question(user_text):
            colors = _extract_color_preferences(session_turns)
            if not colors:
                colors = _extract_color_preferences_from_memory()
            animals = _extract_animal_preferences(session_turns)
            if not animals:
                animals = _extract_animal_preferences_from_memory()

            if not colors:
                msg = "I can't pick a best color yet because I don't have your color preferences."
            elif not animals:
                msg = "I can't pick a best color for animals yet because I don't have your animal preferences."
            else:
                best = _pick_color_for_animals(colors, animals)
                msg = f"Direct answer: {best} matches best with the animals you like ({', '.join(animals)})."
                if len(colors) > 1:
                    msg += f" I considered your options: {', '.join(colors)}."

            print(f"Nova: {msg}\n", flush=True)
            session_turns.append(("assistant", msg))
            speak_chunked(tts, msg)
            continue

        # suppressed noisy interim status to keep replies concise


        # First, ask the action planner what to do deterministically
        try:
            actions = decide_actions(user_text)
        except Exception:
            actions = []

        if actions:
            act = actions[0]
            atype = act.get("type")
            if atype == "ask_clarify":
                q = act.get("question") or act.get("note") or "Can you clarify?"
                try:
                    final = _apply_reply_overrides(q)
                except Exception:
                    final = q
                print(f"Nova: {final}\n", flush=True)
                session_turns.append(("assistant", final))
                speak_chunked(tts, final)
                continue

            if atype == "run_tool":
                tool = act.get("tool")
                args = act.get("args") or []

                # map logical tool names to local functions
                tool_map = {
                    "web_fetch": tool_web,
                    "web_search": tool_web_search,
                    "web_research": tool_web_research,
                    "web_gather": tool_web_gather,
                    "patch_apply": patch_apply,
                    "patch_rollback": patch_rollback,
                    "camera": tool_camera,
                    "screen": tool_screen,
                    "read": tool_read,
                    "ls": tool_ls,
                    "find": tool_find,
                }

                fn = tool_map.get(tool)
                if fn:
                    try:
                        out = fn(*args) if isinstance(args, (list, tuple)) else fn(args)
                    except Exception as e:
                        out = {"ok": False, "error": f"Tool error: {e}"}

                    # Normalize outputs: many tools return strings, others dicts.
                    # Treat None or empty-string as failure.
                    if out is None or (isinstance(out, str) and not out.strip()):
                        # Provide a helpful failure message rather than stalling.
                        if tool.startswith("web"):
                            final_msg = _web_allowlist_message("requested resource")
                        else:
                            final_msg = f"The {tool} tool did not return a result. No data was available."
                        try:
                            final_msg = _apply_reply_overrides(final_msg)
                        except Exception:
                            pass
                        print(f"Nova: {final_msg}\n", flush=True)
                        session_turns.append(("assistant", final_msg))
                        speak_chunked(tts, final_msg)
                        continue

                    # If the tool returned a dict-style response with an explicit failure
                    if isinstance(out, dict) and not out.get("ok", True):
                        err = out.get("error", "unknown error")
                        if isinstance(err, str) and ("not allowed" in err.lower() or "domain not allowed" in err.lower()):
                            final_msg = _web_allowlist_message(args[0] if args else "")
                        else:
                            final_msg = f"Tool {tool} failed: {err}"
                        try:
                            final_msg = _apply_reply_overrides(final_msg)
                        except Exception:
                            pass
                        print(f"Nova: {final_msg}\n", flush=True)
                        session_turns.append(("assistant", final_msg))
                        speak_chunked(tts, final_msg)
                        continue

                    # If the tool returned a success string, include TOOL citation when appropriate
                    citation = format_tool_citation(tool, out)
                    if citation:
                        print(f"Nova (tool output):\n{citation}{out}\n", flush=True)
                    else:
                        print(f"Nova (tool output):\n{out}\n", flush=True)

                    # record recent tool context for later LLM retrieval if it's textual
                    if isinstance(out, str) and out.strip():
                        recent_tool_context = out.strip()[:2500]
                        recent_web_urls = _extract_urls(out)
                        session_turns.append(("assistant", out.strip()[:350]))

                    tts.say("Done.")
                    continue

        task = analyze_request(user_text)
        if not getattr(task, "allow_llm", False):
            msg = getattr(task, "message", "")
            try:
                final = _apply_reply_overrides(msg)
            except Exception:
                final = msg
            print(f"Nova: {final}\n", flush=True)
            session_turns.append(("assistant", final))
            speak_chunked(tts, final)
            continue

        retrieved_context = build_learning_context(user_text)
        chat_ctx = _render_chat_context(session_turns)
        if chat_ctx:
            retrieved_context = (retrieved_context + "\n\nCURRENT CHAT CONTEXT:\n" + chat_ctx).strip()[:6000]
        if recent_tool_context and _uses_prior_reference(user_text):
            retrieved_context = (retrieved_context + "\n\nRECENT TOOL OUTPUT:\n" + recent_tool_context).strip()[:6000]
        reply = ollama_chat(user_text, retrieved_context=retrieved_context)
        reply = sanitize_llm_reply(reply, tool_context=recent_tool_context)

        if mem_enabled():
            if mem_should_store(user_text):
                mem_add("chat_user", input_source, user_text)
            # Do not automatically store assistant replies to avoid clutter and duplicates.

        # remove any raw memory dumps leaking into the assistant reply before showing
        clean_reply = _strip_mem_leak(reply, retrieved_context)
        # Shorten replies for ordinary conversation: if the user did not explicitly request an action,
        # prefer a concise reply (first 1-2 sentences). Keep full replies for explicit requests.
        try:
            if not _is_explicit_request(user_text):
                # take up to first 2 sentences
                sents = re.split(r'(?<=[.!?])\s+', (clean_reply or "").strip())
                short = " ".join([s for s in sents if s])[:600]
                if short:
                    # prefer the short form unless it's obviously truncating a tool citation
                    clean_reply = short
        except Exception:
            pass
        try:
            final = _apply_reply_overrides(clean_reply)
        except Exception:
            final = clean_reply
        final = _ensure_reply(final)
        print(f"Nova: {final}\n", flush=True)
        session_turns.append(("assistant", final))
        speak_chunked(tts, final)

# =========================
# Entrypoint
# =========================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", default="run", choices=["run"])
    ap.add_argument("--heartbeat", default=str(DEFAULT_HEARTBEAT))
    ap.add_argument("--statefile", default=str(DEFAULT_STATEFILE))
    args = ap.parse_args()

    hb = Path(args.heartbeat)
    st = Path(args.statefile)

    write_core_identity(st)
    hb_stop = start_heartbeat(hb, interval_sec=1.0)

    tts = SubprocessTTS(PYTHON, BASE_DIR / "tts_piper.py", timeout_sec=25.0)
    tts.start()
    tts.say("Nova online.")

    ensure_ollama_boot()

    try:
        run_loop(tts)
    finally:
        hb_stop.set()
        tts.stop()


if __name__ == "__main__":
    main()
