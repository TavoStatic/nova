from __future__ import annotations

import argparse
import io
import json
import os
import uuid
from pathlib import Path

import requests

from tools import ToolContext, build_default_registry


OLLAMA_URL = "http://localhost:11434/api/chat"
CHAT_API_URL = "http://127.0.0.1:8080/api/chat"
CHAT_LOGIN_URL = "http://127.0.0.1:8080/api/chat/login"
LLM_MODEL = "llama3.1:8b"

WHISPER_SIZE = "small"
SAMPLE_RATE = 16000
CHANNELS = 1

BASE_DIR = Path(__file__).resolve().parent
POLICY_PATH = BASE_DIR / "policy.json"

CHAT_SESSION_ID = uuid.uuid4().hex[:12]
USER_ID = (os.environ.get("NOVA_USER_ID") or os.environ.get("NOVA_CHAT_USER") or os.environ.get("USERNAME") or "local-user").strip()
CHAT_USER = (os.environ.get("NOVA_CHAT_USER") or USER_ID).strip()
CHAT_PASS = (os.environ.get("NOVA_CHAT_PASS") or "").strip()
HTTP_SESSION = requests.Session()
CHAT_LOGIN_DONE = False
REGISTRY = build_default_registry()


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Nova run_tools dispatcher")
    ap.add_argument("--list-tools", action="store_true", help="List registered Nova tools")
    ap.add_argument("--tool", default="", help="Run one tool by name")
    ap.add_argument("--args-json", default="{}", help="JSON payload for --tool")
    ap.add_argument("--session-id", default="", help="Override session id for --tool")
    ap.add_argument("--user-id", default="", help="Override user id for --tool")
    ap.add_argument("--admin", action="store_true", help="Run with admin-capable context")
    return ap.parse_args()


def load_policy() -> dict:
    try:
        data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def ensure_chat_login() -> None:
    global CHAT_LOGIN_DONE
    if CHAT_LOGIN_DONE or not CHAT_PASS:
        return
    r = HTTP_SESSION.post(CHAT_LOGIN_URL, json={"username": CHAT_USER, "password": CHAT_PASS}, timeout=30)
    r.raise_for_status()
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(j.get("error") or "login_failed")
    CHAT_LOGIN_DONE = True


def record_seconds(seconds: int = 6):
    import sounddevice as sd

    print(f"Nova: recording for {seconds} seconds... (talk now)")
    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16")
    sd.wait()
    return audio


def transcribe(model, audio_int16):
    import scipy.io.wavfile as wav

    buf = io.BytesIO()
    wav.write(buf, SAMPLE_RATE, audio_int16)
    buf.seek(0)

    segments, _ = model.transcribe(buf)
    text = ""
    for seg in segments:
        text += seg.text.strip() + " "
    return text.strip()


def ask_nova(text: str) -> str:
    global CHAT_SESSION_ID
    try:
        ensure_chat_login()
        r = HTTP_SESSION.post(
            CHAT_API_URL,
            json={"message": text, "session_id": CHAT_SESSION_ID, "user_id": USER_ID},
            headers={"X-Nova-User-Id": USER_ID},
            timeout=120,
        )
        r.raise_for_status()
        j = r.json()
        sid = str(j.get("session_id") or "").strip()
        if sid:
            CHAT_SESSION_ID = sid
        reply = str(j.get("reply") or "").strip()
        if reply:
            return reply
    except Exception:
        pass

    payload = {
        "model": LLM_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": "You are Nova. Be helpful, concise, practical."},
            {"role": "user", "content": text},
        ],
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=1800)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def speak(text: str) -> None:
    import pyttsx3

    engine = pyttsx3.init()
    engine.setProperty("rate", 175)
    engine.say(text)
    engine.runAndWait()


def build_context(*, session_id: str = "", user_id: str = "", is_admin: bool = False) -> ToolContext:
    policy = load_policy()
    return ToolContext(
        user_id=(user_id or USER_ID).strip(),
        session_id=(session_id or CHAT_SESSION_ID).strip(),
        policy=policy,
        allowed_root=str(Path(policy.get("allowed_root") or BASE_DIR).resolve()),
        is_admin=bool(is_admin),
        extra={"chat_callable": ask_nova},
    )


def dispatch_tool(name: str, args: dict, *, context: ToolContext | None = None) -> str:
    ctx = context or build_context()
    return str(REGISTRY.run_tool(name, args, ctx))


def list_tools_text() -> str:
    return REGISTRY.describe()


def handle_tools(user_text: str, *, context: ToolContext | None = None):
    t = user_text.strip()
    low = t.lower()
    ctx = context or build_context()

    if low in {"tools", "nova tools", "show tools", "list tools"}:
        return list_tools_text()

    if low == "ls" or low.startswith("ls "):
        path = t.split(maxsplit=1)[1] if len(t.split(maxsplit=1)) > 1 else ""
        print("Nova: tool -> filesystem.ls")
        return dispatch_tool("filesystem", {"action": "ls", "path": path}, context=ctx)

    if "screen" in low:
        print("Nova: tool -> vision.screen")
        return dispatch_tool("vision", {"action": "screen"}, context=ctx)

    if "camera" in low:
        prompt = "Describe what you see."
        if len(t.split()) > 1:
            prompt = t
        print("Nova: tool -> vision.camera")
        return dispatch_tool("vision", {"action": "camera", "prompt": prompt}, context=ctx)

    if low.startswith("find "):
        parts = t.split(maxsplit=2)
        keyword = parts[1] if len(parts) > 1 else ""
        folder = parts[2] if len(parts) > 2 else ""
        print("Nova: tool -> filesystem.find")
        return dispatch_tool("filesystem", {"action": "find", "keyword": keyword, "path": folder}, context=ctx)

    if low.startswith("read "):
        file_part = t.split(maxsplit=1)[1]
        print("Nova: tool -> filesystem.read")
        return dispatch_tool("filesystem", {"action": "read", "path": file_part}, context=ctx)

    if low.startswith("web search "):
        print("Nova: tool -> research.web_search")
        return dispatch_tool("research", {"action": "web_search", "value": t[len("web search "):].strip()}, context=ctx)

    if low.startswith("web research "):
        print("Nova: tool -> research.web_research")
        return dispatch_tool("research", {"action": "web_research", "value": t[len("web research "):].strip()}, context=ctx)

    if low.startswith("web gather "):
        print("Nova: tool -> research.web_gather")
        return dispatch_tool("research", {"action": "web_gather", "value": t[len("web gather "):].strip()}, context=ctx)

    if low in {"health", "health check"}:
        print("Nova: tool -> system.health_check")
        return dispatch_tool("system", {"action": "health_check"}, context=ctx)

    return None


def main() -> None:
    global CHAT_SESSION_ID, USER_ID
    args = parse_args()
    if args.user_id:
        USER_ID = args.user_id.strip()
    if args.session_id:
        CHAT_SESSION_ID = args.session_id.strip()

    if args.list_tools:
        print(list_tools_text())
        return

    if args.tool:
        payload = json.loads(args.args_json or "{}")
        if not isinstance(payload, dict):
            raise RuntimeError("args_json_must_be_object")
        ctx = build_context(session_id=args.session_id, user_id=args.user_id, is_admin=args.admin)
        print(dispatch_tool(args.tool, payload, context=ctx))
        return

    from faster_whisper import WhisperModel

    print("Nova Orchestrator+Tools: loading Whisper (CPU mode)...")
    whisper = WhisperModel(WHISPER_SIZE, device="cpu", compute_type="int8")

    print("\nNova Orchestrator+Tools is ready.")
    print("Say things like: 'tools', 'ls', 'screen', 'camera', 'find mysql www', 'read README.md'")
    print("Press ENTER to talk (records ~6 seconds). Type 'q' then ENTER to quit.\n")

    while True:
        cmd = input("> ").strip().lower()
        if cmd == "q":
            break
        if cmd == "tools":
            print(list_tools_text() + "\n")
            continue

        audio = record_seconds(6)
        print("Nova: transcribing...")
        text = transcribe(whisper, audio)
        if not text:
            print("Nova: (heard nothing)\n")
            continue

        print(f"You: {text}")
        tool_out = handle_tools(text, context=build_context())
        if tool_out is not None:
            print(f"Nova (tool output):\n{tool_out}\n")
            speak("Done.")
            continue

        print("Nova: thinking...")
        reply = ask_nova(text)
        print(f"Nova: {reply}\n")
        speak(reply)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass