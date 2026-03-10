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
from urllib.parse import urlparse, parse_qs, unquote, urljoin
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

    # Run a preview check first to avoid blind applies.
    try:
        preview_out = patch_preview(str(z))
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

    return r


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
            return "I understood you, but I don't have a clear reply yet."
        return r
    except Exception:
        return "I understood you, but I don't have a clear reply yet."


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

        return f"Created proposal: {out_zip} — apply with: patch apply {out_zip}"
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
        return f"[FAIL] {out.get('error', 'unknown error')}"
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


def _crawl_domain_for_query(start_url: str, query_tokens: list[str], max_pages: int, max_depth: int) -> list[tuple[float, str, str]]:
    parsed = urlparse(start_url)
    host = parsed.hostname or ""
    if not host:
        return []

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
        low_text = text.lower()
        low_url = url.lower()

        text_hits = 0
        url_hits = 0
        for t in query_tokens:
            text_hits += low_text.count(t)
            url_hits += low_url.count(t)

        score = (url_hits * 2.0) + min(40.0, float(text_hits) * 0.5)
        if score > 0:
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

                # Nested sitemap index entries often point to other XML sitemap files.
                if clean.lower().endswith(".xml"):
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

    scored = []
    for u in candidates:
        low = u.lower()
        score = sum(low.count(t) for t in query_tokens)
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

    # Bias search toward allowed domains only
    scoped = q + " " + " ".join(f"site:{d}" for d in allow_domains[:6])

    try:
        r = requests.get(
            "https://duckduckgo.com/html/",
            params={"q": scoped},
            headers={"User-Agent": "Nova/1.0"},
            timeout=30,
        )
        r.raise_for_status()
        page = r.text
    except Exception as e:
        return f"[FAIL] Web search request failed: {e}"

    hrefs = re.findall(r'href=["\']([^"\']+)["\']', page, flags=re.I)
    # Fallback: capture literal URLs in result page text when redirect links are absent
    direct_urls = re.findall(r"https?://[^\s\"'<>]+", page)
    seen = set()
    urls = []
    for h in hrefs:
        u = _decode_search_href(h)
        if not u:
            continue
        host = urlparse(u).hostname or ""
        if not _host_allowed(host, allow_domains):
            continue
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)
        if len(urls) >= 5:
            break

    if len(urls) < 5:
        for u in direct_urls:
            host = urlparse(u).hostname or ""
            if not _host_allowed(host, allow_domains):
                continue
            if u in seen:
                continue
            seen.add(u)
            urls.append(u)
            if len(urls) >= 5:
                break

    if not urls:
        return "No allowlisted web results found for that query."

    lines = ["Web results (allowlisted):"]
    for i, u in enumerate(urls, start=1):
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
        return f"[FAIL] {out.get('error', 'unknown error')}"

    p = Path(out["path"])
    snippet = _extract_text_from_path(p, max_chars=2200)
    if snippet:
        return (
            f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)\n"
            f"Summary snippet:\n{snippet}"
        )

    return f"[OK] Saved: {out['path']} ({out['content_type']}, {out['bytes']} bytes)"


def tool_web_research(query: str):
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
    if not q:
        return "Usage: web research <query>"

    toks = _tokenize(q)
    if not toks:
        return "Query too short for web research."

    domains_limit = int(cfg.get("research_domains_limit") or 4)
    pages_per_domain = int(cfg.get("research_pages_per_domain") or 8)
    max_depth = int(cfg.get("research_max_depth") or 1)
    max_results = int(cfg.get("research_max_results") or 8)
    seeds_per_domain = int(cfg.get("research_seeds_per_domain") or 8)

    domains = allow_domains[:max(1, min(domains_limit, len(allow_domains)))]
    all_hits = []
    for d in domains:
        seeds = _seed_urls_for_domain(d, toks, max_seed=max(1, seeds_per_domain))
        for start in seeds:
            all_hits.extend(_crawl_domain_for_query(start, toks, max_pages=max(2, pages_per_domain), max_depth=max(0, max_depth)))

    if not all_hits:
        return "No relevant pages found across allowlisted domains for that query."

    all_hits.sort(key=lambda x: x[0], reverse=True)
    lines = ["Web research results (allowlisted crawl):"]
    used = set()
    rank = 0
    for score, url, snippet in all_hits:
        if url in used:
            continue
        used.add(url)
        rank += 1
        lines.append(f"{rank}. [{score:.1f}] {url}")
        if snippet:
            lines.append(f"   {snippet[:220]}")
        if rank >= max_results:
            break

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
def handle_commands(user_text: str) -> Optional[str]:
    t = (user_text or "").strip()
    low = t.lower()

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
    print("Commands: screen | camera <prompt> | web <url> | web search <query> | web research <query> | web gather <url> | ls [folder] | read <file> | find <kw> [folder] | health | capabilities | inspect", flush=True)
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
            greet_regex = re.compile(r"^(hi|hello|hey|good morning|good afternoon|good evening)([\s!,\.]|$)")
            m = greet_regex.match(low_q)
            if m:
                who = get_active_user() or ""
                word = m.group(1)
                if word in {"hi", "hello"}:
                    if who:
                        msg = f"Hi {who}."
                    else:
                        msg = "Hello."
                elif word == "hey":
                    msg = "Hey, what do you need?"
                else:
                    if who:
                        msg = f"{word.capitalize()}, {who}."
                    else:
                        msg = f"{word.capitalize()}."

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
                            top = results[0]
                            preview = _normalize_location_preview((top.get("preview") or "").strip())
                            msg = f"I have your stored location as {preview}. I can look up the weather for that location if you want."
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
                    msg = f"I can look up the weather for {place}. Do you want me to fetch it now?"
                    try:
                        final = _apply_reply_overrides(msg)
                    except Exception:
                        final = msg
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
                ack = "Got it. I've noted that."
                print(f"Nova: {ack}\n", flush=True)
                session_turns.append(("assistant", ack))
                speak_chunked(tts, ack)
                continue
        except Exception:
            pass

        cmd_out = handle_commands(user_text)
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

        print("Nova: thinking...", flush=True)

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
                        out = f"Tool error: {e}"

                    # If the tool returned a path-like success, include a TOOL citation
                    citation = format_tool_citation(tool, out)

                    if citation:
                        print(f"Nova (tool output):\n{citation}{out}\n", flush=True)
                    else:
                        print(f"Nova (tool output):\n{out}\n", flush=True)

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
        try:
            final = _apply_reply_overrides(clean_reply)
        except Exception:
            final = clean_reply
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
