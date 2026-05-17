#!/usr/bin/env python3
"""Health checks for Project NOVA.

Modes:
- check  : machine-readable JSON summary for automation/smoke tests
- diag   : human-readable environment diagnostics
- repair : best-effort Ollama repair, then diagnostics
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Tuple

import psutil
import requests
from services.ollama_health import build_ollama_health_payload

BASE = Path(__file__).resolve().parent
RUNTIME = BASE / "runtime"
HEARTBEAT = RUNTIME / "core.heartbeat"
STATE = RUNTIME / "core_state.json"
OLLAMA_BASE = "http://127.0.0.1:11434"
DEFAULT_CHAT_MODEL = "llama3.2:3b"
DEFAULT_VISION_MODEL = "qwen2.5vl:7b"


def configured_models() -> dict[str, str]:
    try:
        policy = json.loads((BASE / "policy.json").read_text(encoding="utf-8"))
    except Exception:
        policy = {}
    models = policy.get("models") if isinstance(policy.get("models"), dict) else {}
    chat = str(models.get("chat") or DEFAULT_CHAT_MODEL).strip()
    vision = str(models.get("vision") or DEFAULT_VISION_MODEL).strip()
    return {"chat": chat, "vision": vision}


def required_ollama_models() -> list[str]:
    required = []
    for model in configured_models().values():
        if model and model not in required:
            required.append(model)
    return required


def ok(msg: str):
    print(f"[OK]   {msg}")


def warn(msg: str):
    print(f"[WARN] {msg}")


def bad(msg: str):
    print(f"[FAIL] {msg}")


def check_heartbeat(max_age: int = 10) -> Tuple[bool, str]:
    if not HEARTBEAT.exists():
        return False, "missing"
    age = time.time() - HEARTBEAT.stat().st_mtime
    return age <= max_age, f"age={int(age)}s"


def check_state() -> Tuple[bool, str]:
    if not STATE.exists():
        return False, "missing"
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        pid = int(data.get("pid", 0) or 0)
        if pid <= 0:
            return False, "invalid-pid"
        alive = psutil.pid_exists(pid)
        return alive, f"pid={pid}"
    except Exception as e:
        return False, f"error:{e}"


def check_ollama(timeout: float = 1.0) -> Tuple[bool, str]:
    payload = ollama_health_payload(timeout=timeout)
    return bool(payload.get("ok")), str(payload.get("info") or payload.get("status") or "")


def ollama_health_payload(timeout: float = 2.0) -> dict:
    return build_ollama_health_payload(
        requests_get_fn=requests.get,
        requests_post_fn=requests.post,
        ollama_base=OLLAMA_BASE,
        chat_model=configured_models().get("chat") or DEFAULT_CHAT_MODEL,
        timeout=timeout,
        live_calls_allowed=True,
    )


def tcp_listening(host: str = "127.0.0.1", port: int = 11434, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ollama_api_up(timeout: float = 2.0) -> bool:
    return bool(ollama_health_payload(timeout=timeout).get("server_ok"))


def ollama_tags() -> Tuple[bool, list[str]]:
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        r.raise_for_status()
        data = r.json()
        models = [m.get("name", "") for m in data.get("models", [])]
        return True, models
    except Exception:
        return False, []


def start_ollama_serve_detached() -> bool:
    try:
        detached_process = 0x00000008
        new_process_group = 0x00000200
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=detached_process | new_process_group,
        )
        return True
    except Exception:
        return False


def kill_ollama() -> bool:
    try:
        subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"], capture_output=True, text=True)
        return True
    except Exception:
        return False


def check_gpu() -> None:
    try:
        r = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            ok("nvidia-smi OK (GPU visible)")
        else:
            warn("nvidia-smi failed (GPU may be unavailable or driver missing)")
    except Exception:
        warn("nvidia-smi not available")


def check_mic() -> None:
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        inputs = [d for d in devices if d.get("max_input_channels", 0) > 0]
        if inputs:
            ok(f"Microphone devices found: {len(inputs)}")
        else:
            warn("No microphone input devices found")
    except Exception as e:
        warn(f"Microphone check failed: {e}")


def check_camera() -> None:
    try:
        import cv2

        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if cap.isOpened():
            ok("Camera index 0 opens OK")
        else:
            warn("Camera index 0 failed to open")
        cap.release()
    except Exception as e:
        warn(f"Camera check failed: {e}")


def check_python_packages() -> None:
    needed = ["requests", "pyttsx3", "faster_whisper", "sounddevice", "scipy", "cv2", "PIL"]
    missing = []
    for package_name in needed:
        try:
            __import__(package_name)
        except Exception:
            missing.append(package_name)
    if not missing:
        ok("Python packages OK")
    else:
        bad(f"Missing Python packages: {', '.join(missing)}")


def repair_ollama() -> bool:
    if not tcp_listening():
        warn("Port 11434 not listening. Starting ollama serve...")
        if not start_ollama_serve_detached():
            bad("Failed to start ollama serve")
            return False

    if tcp_listening() and not ollama_api_up():
        warn("Port is listening but Ollama API not responding. Restarting ollama...")
        kill_ollama()
        time.sleep(1.5)
        if not start_ollama_serve_detached():
            bad("Failed to restart ollama serve")
            return False

    for _ in range(15):
        if ollama_api_up(timeout=2.0):
            ok("Ollama API is up")
            return True
        time.sleep(1)

    bad("Ollama API still not responding after repair attempts")
    return False


def run_check(include_ollama: bool = True) -> int:
    profile = "runtime" if include_ollama else "base-package"
    if include_ollama:
        hb_ok, hb_msg = check_heartbeat()
        st_ok, st_msg = check_state()
        ol_ok, ol_msg = check_ollama()
        ollama_payload = {"ok": ol_ok, "info": ol_msg, "required": True}
        runtime_ok = hb_ok and st_ok
    else:
        hb_ok, hb_msg = None, "skipped"
        st_ok, st_msg = None, "skipped"
        ol_ok, ol_msg = True, "skipped"
        ollama_payload = {"ok": None, "info": ol_msg, "required": False}
        runtime_ok = True

    all_ok = runtime_ok and ol_ok
    out = {
        "profile": profile,
        "heartbeat": {"ok": hb_ok, "info": hb_msg, "required": include_ollama},
        "core_state": {"ok": st_ok, "info": st_msg, "required": include_ollama},
        "ollama": ollama_payload,
        "ok": all_ok,
    }
    print(json.dumps(out, indent=2))
    return 0 if all_ok else 1


def run_diag() -> int:
    print("\n=== Nova Health Diagnostics ===\n")
    check_python_packages()
    check_gpu()
    check_mic()
    check_camera()

    if tcp_listening():
        ok("Port 11434 is listening")
    else:
        bad("Port 11434 is NOT listening (Ollama not serving)")

    ollama_health = ollama_health_payload(timeout=2.0)
    if bool(ollama_health.get("tags_ok")):
        ok("Ollama tags endpoint responding (/api/tags)")
        tags_ok, models = ollama_tags()
        if tags_ok:
            ok(f"Ollama models found: {len(models)}")
            missing = [m for m in required_ollama_models() if m not in models]
            if missing:
                warn("Missing required models: " + ", ".join(missing))
                warn("Fix: ollama pull " + " ; ".join(missing))
            else:
                ok("Required models present")
        else:
            warn("Could not fetch model list")
    else:
        bad("Ollama tags endpoint NOT responding")

    if bool(ollama_health.get("chat_route_ok")):
        ok(f"Ollama chat route responding (/api/chat probe status={ollama_health.get('chat_route_status')})")
    else:
        bad(f"Ollama chat route NOT responding ({ollama_health.get('info') or ollama_health.get('status')})")

    print("\n=== Done ===\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", default="check", choices=["check", "diag", "repair"])
    parser.add_argument("--skip-ollama", action="store_true", help="Skip the Ollama requirement during check mode")
    args = parser.parse_args()

    if args.mode == "check":
        return run_check(include_ollama=not args.skip_ollama)

    if args.mode == "repair":
        print("\n=== Repair Mode ===\n")
        repair_ollama()

    return run_diag()


if __name__ == "__main__":
    sys.exit(main())
