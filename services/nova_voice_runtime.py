from __future__ import annotations

import io
import queue
import subprocess
import threading
import re
from collections.abc import MutableMapping
from typing import Any, Callable


def ensure_voice_deps(
    runtime_scope: MutableMapping[str, Any],
    *,
    import_voice_modules_fn: Callable[[], tuple[object, object, object]] | None = None,
) -> bool:
    """Import voice dependencies lazily and mirror their state onto the provided runtime scope."""
    if bool(runtime_scope.get("VOICE_READY")):
        return bool(runtime_scope.get("VOICE_OK"))

    runtime_scope["VOICE_READY"] = True
    try:
        if import_voice_modules_fn is None:
            import sounddevice as _sd
            import scipy.io.wavfile as _wav
            from faster_whisper import WhisperModel as _WhisperModel
        else:
            _sd, _wav, _WhisperModel = import_voice_modules_fn()

        runtime_scope["sd"] = _sd
        runtime_scope["wav"] = _wav
        runtime_scope["WhisperModel"] = _WhisperModel
        runtime_scope["VOICE_OK"] = True
        runtime_scope["VOICE_IMPORT_ERR"] = ""
    except Exception as exc:
        runtime_scope["VOICE_OK"] = False
        runtime_scope["VOICE_IMPORT_ERR"] = str(exc)
        runtime_scope["sd"] = None
        runtime_scope["wav"] = None
        runtime_scope["WhisperModel"] = None

    return bool(runtime_scope.get("VOICE_OK"))


def voice_status_payload(runtime_scope: MutableMapping[str, Any]) -> dict[str, Any]:
    ready = bool(runtime_scope.get("VOICE_READY"))
    ok = bool(runtime_scope.get("VOICE_OK"))
    import_error = str(runtime_scope.get("VOICE_IMPORT_ERR") or "").strip()
    sd_ready = runtime_scope.get("sd") is not None
    wav_ready = runtime_scope.get("wav") is not None
    whisper_ready = runtime_scope.get("WhisperModel") is not None

    if not ready:
        status = "not_initialized"
        note = "Voice dependencies have not been requested in this runtime."
    elif ok and sd_ready and wav_ready and whisper_ready:
        status = "ok"
        note = "Voice dependencies are loaded."
    else:
        status = "disabled"
        note = import_error or "Voice dependency state is incomplete."

    return {
        "ok": bool(status in {"not_initialized", "ok"}),
        "status": status,
        "requested": ready,
        "voice_ready": ready,
        "voice_ok": ok,
        "import_error": import_error,
        "sounddevice_loaded": sd_ready,
        "sounddevice_available": sd_ready,
        "wav_loaded": wav_ready,
        "wav_available": wav_ready,
        "whisper_loaded": whisper_ready,
        "whisper_available": whisper_ready,
        "sample_rate": int(runtime_scope.get("SAMPLE_RATE", 0) or 0),
        "channels": int(runtime_scope.get("CHANNELS", 0) or 0),
        "note": note,
    }


def record_seconds(
    seconds: int = 3,
    *,
    ensure_voice_deps_fn: Callable[[], bool],
    runtime_scope: MutableMapping[str, Any],
    sample_rate: int,
    channels: int,
    print_fn: Callable[..., None] = print,
):
    sd = runtime_scope.get("sd")
    if not ensure_voice_deps_fn() or sd is None:
        raise RuntimeError(f"Voice is disabled (import error: {runtime_scope.get('VOICE_IMPORT_ERR') or ''})")
    print_fn(f"Nova: recording for {seconds} seconds... (talk now)", flush=True)
    audio = sd.rec(
        int(seconds * sample_rate),
        samplerate=sample_rate,
        channels=channels,
        dtype="int16",
    )
    sd.wait()
    return audio


def transcribe(
    model,
    audio_int16,
    *,
    ensure_voice_deps_fn: Callable[[], bool],
    runtime_scope: MutableMapping[str, Any],
    sample_rate: int,
) -> str:
    wav = runtime_scope.get("wav")
    if not ensure_voice_deps_fn() or wav is None:
        raise RuntimeError(f"Voice is disabled (import error: {runtime_scope.get('VOICE_IMPORT_ERR') or ''})")
    buf = io.BytesIO()
    wav.write(buf, sample_rate, audio_int16)
    buf.seek(0)
    segments, _ = model.transcribe(buf)
    return " ".join(seg.text.strip() for seg in segments).strip()


class SubprocessTTS:
    """Piper oneshot wrapper: python tts_piper.py "text"."""

    def __init__(
        self,
        python_exe: str,
        oneshot_script,
        timeout_sec: float = 25.0,
        *,
        warn_fn: Callable[[str], None],
    ):
        self.python_exe = python_exe
        self.oneshot_script = oneshot_script
        self.timeout_sec = float(timeout_sec)
        self.warn_fn = warn_fn
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
                creationflags = 0x08000000 if __import__("os").name == "nt" else 0
                proc = subprocess.Popen(
                    [self.python_exe, str(self.oneshot_script), item],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    creationflags=creationflags,
                )
                try:
                    _, err = proc.communicate(timeout=self.timeout_sec)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    self.warn_fn("TTS timed out; killed piper subprocess.")
                    continue

                if proc.returncode != 0:
                    msg = (err or b"").decode("utf-8", errors="ignore").strip()
                    self.warn_fn(f"TTS failed rc={proc.returncode}: {msg}")
            except Exception as exc:
                self.warn_fn(f"TTS error: {exc}")


def speak_chunked(tts: SubprocessTTS, text: str, max_len: int = 220):
    cleaned = (text or "").strip()
    if not cleaned:
        return
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    buf = ""
    for part in parts:
        if len(buf) + len(part) + 1 <= max_len:
            buf = (buf + " " + part).strip()
        else:
            if buf:
                tts.say(buf)
            buf = part.strip()
    if buf:
        tts.say(buf)
