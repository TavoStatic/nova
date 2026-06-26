from __future__ import annotations

import io
import queue
import subprocess
import threading
import re
import time
from collections.abc import MutableMapping
from typing import Any, Callable


def _as_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _is_virtual_input_name(name: str) -> bool:
    lowered = str(name or "").strip().lower()
    if not lowered:
        return False
    markers = (
        "virtual",
        "stereo mix",
        "wave out",
        "what u hear",
        "monitor of",
        "streaming audio",
    )
    return any(token in lowered for token in markers)


def _is_generic_wrapper_input_name(name: str) -> bool:
    lowered = str(name or "").strip().lower()
    if not lowered:
        return False
    markers = (
        "microsoft sound mapper",
        "primary sound capture driver",
    )
    return any(token in lowered for token in markers)


def _input_device_score(item: tuple[int, dict]) -> int:
    _idx, dev = item
    name = str(dev.get("name") or "").lower()
    channels = int(dev.get("max_input_channels", 0) or 0)
    score = channels * 10
    if "microphone" in name or "mic" in name:
        score += 50
    if "headset" in name:
        score += 30
    if "usb" in name:
        score += 20
    if "array" in name:
        score -= 25
    if _is_virtual_input_name(name):
        score -= 100
    if _is_generic_wrapper_input_name(name):
        score -= 120
    return score


def _enumerate_input_devices(sd) -> list[tuple[int, dict]]:
    try:
        raw = sd.query_devices()
    except Exception:
        raw = []
    devices = []
    for idx, dev in enumerate(list(raw or [])):
        item = dev if isinstance(dev, dict) else {}
        channels = int(item.get("max_input_channels", 0) or 0)
        if channels > 0:
            devices.append((idx, item))
    return devices


def _default_input_index(sd) -> int | None:
    try:
        default_value = getattr(getattr(sd, "default", None), "device", None)
    except Exception:
        default_value = None
    if isinstance(default_value, (list, tuple)) and default_value:
        return _as_int(default_value[0])
    return _as_int(default_value)


def _resolve_input_device(sd, preferred: Any) -> tuple[int, dict]:
    inputs = _enumerate_input_devices(sd)
    if not inputs:
        raise RuntimeError("No microphone input devices available")

    by_index = {idx: dev for idx, dev in inputs}
    preferred_text = str(preferred or "").strip()
    preferred_lower = preferred_text.lower()

    if preferred_text and preferred_lower not in {"auto", "default"}:
        preferred_idx = _as_int(preferred_text)
        if preferred_idx is not None and preferred_idx in by_index:
            return preferred_idx, by_index[preferred_idx]
        for idx, dev in inputs:
            name = str(dev.get("name") or "")
            if preferred_lower in name.lower():
                return idx, dev

    default_idx = _default_input_index(sd)
    non_virtual = [(idx, dev) for idx, dev in inputs if not _is_virtual_input_name(str(dev.get("name") or ""))]
    candidates = non_virtual or inputs

    if default_idx is not None:
        for idx, dev in candidates:
            name = str(dev.get("name") or "").lower()
            if idx == default_idx and "array" not in name:
                return idx, dev

    best = max(candidates, key=_input_device_score)
    return best


def _ordered_input_candidates(sd, preferred: Any, runtime_scope: MutableMapping[str, Any]) -> list[tuple[int, dict]]:
    inputs = _enumerate_input_devices(sd)
    if not inputs:
        return []

    by_index = {idx: dev for idx, dev in inputs}
    ordered: list[tuple[int, dict]] = []
    seen: set[int] = set()

    def _push(idx: int):
        if idx in seen or idx not in by_index:
            return
        seen.add(idx)
        ordered.append((idx, by_index[idx]))

    preferred_idx = _as_int(preferred)
    if preferred_idx is not None:
        _push(preferred_idx)

    preferred_text = str(preferred or "").strip().lower()
    if preferred_text and preferred_text not in {"auto", "default"} and preferred_idx is None:
        for idx, dev in inputs:
            name = str(dev.get("name") or "").lower()
            if preferred_text in name:
                _push(idx)

    last_good = _as_int(runtime_scope.get("VOICE_WORKING_INPUT_DEVICE_INDEX"))
    if last_good is not None:
        _push(last_good)

    try:
        first_idx, _first_dev = _resolve_input_device(sd, preferred)
        _push(first_idx)
    except Exception:
        pass

    remaining = sorted(inputs, key=_input_device_score, reverse=True)
    for idx, _dev in remaining:
        _push(idx)
    return ordered


def _chunk_peak_abs(chunk: Any) -> int:
    try:
        if chunk is None:
            return 0
        if hasattr(chunk, "astype") and hasattr(chunk, "max"):
            try:
                arr = chunk.astype("int32", copy=False)
            except Exception:
                arr = chunk
            return int(abs(arr).max())
        peak = 0
        for sample in chunk:
            if isinstance(sample, (list, tuple)):
                for inner in sample:
                    value = abs(int(inner))
                    if value > peak:
                        peak = value
            else:
                value = abs(int(sample))
                if value > peak:
                    peak = value
        return int(peak)
    except Exception:
        return 0


def _concat_audio_chunks(chunks: list[Any], runtime_scope: MutableMapping[str, Any]):
    if not chunks:
        return chunks
    if len(chunks) == 1:
        return chunks[0]
    np_mod = runtime_scope.get("np")
    if np_mod is not None:
        try:
            return np_mod.concatenate(chunks, axis=0)
        except Exception:
            pass
    return chunks[0]


def _downmix_to_mono(audio: Any, runtime_scope: MutableMapping[str, Any]):
    """Convert multi-channel int16-ish audio into mono for Whisper."""
    if audio is None:
        return audio

    np_mod = runtime_scope.get("np")
    if np_mod is not None:
        try:
            arr = np_mod.asarray(audio)
            if arr.ndim >= 2:
                mono = arr.mean(axis=1)
                return mono.astype("int16", copy=False)
            return arr.astype("int16", copy=False)
        except Exception:
            pass

    try:
        if hasattr(audio, "shape") and len(getattr(audio, "shape", ())) >= 2:
            return audio[:, 0]
    except Exception:
        pass
    return audio


def _segments_indicate_no_usable_speech(segment_list: list[Any]) -> bool:
    probs: list[float] = []
    text_parts: list[str] = []
    for seg in segment_list:
        text_parts.append(str(getattr(seg, "text", "") or "").strip())
        value = getattr(seg, "no_speech_prob", None)
        if value is None:
            continue
        try:
            probs.append(float(value))
        except Exception:
            continue

    joined = " ".join(part for part in text_parts if part).strip()
    if not joined:
        return True
    if not probs:
        return False
    return len(joined.split()) <= 3 and all(prob >= 0.65 for prob in probs)


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
            import numpy as _np
            from faster_whisper import WhisperModel as _WhisperModel
        else:
            loaded = import_voice_modules_fn()
            if isinstance(loaded, tuple) and len(loaded) >= 4:
                _sd, _wav, _WhisperModel, _np = loaded[0], loaded[1], loaded[2], loaded[3]
            else:
                _sd, _wav, _WhisperModel = loaded
                _np = None

        runtime_scope["sd"] = _sd
        runtime_scope["wav"] = _wav
        runtime_scope["WhisperModel"] = _WhisperModel
        runtime_scope["np"] = _np
        runtime_scope["VOICE_OK"] = True
        runtime_scope["VOICE_IMPORT_ERR"] = ""
    except Exception as exc:
        runtime_scope["VOICE_OK"] = False
        runtime_scope["VOICE_IMPORT_ERR"] = str(exc)
        runtime_scope["sd"] = None
        runtime_scope["wav"] = None
        runtime_scope["WhisperModel"] = None
        runtime_scope["np"] = None

    return bool(runtime_scope.get("VOICE_OK"))


def voice_status_payload(runtime_scope: MutableMapping[str, Any]) -> dict[str, Any]:
    ready = bool(runtime_scope.get("VOICE_READY"))
    ok = bool(runtime_scope.get("VOICE_OK"))
    import_error = str(runtime_scope.get("VOICE_IMPORT_ERR") or "").strip()
    sd_ready = runtime_scope.get("sd") is not None
    wav_ready = runtime_scope.get("wav") is not None
    whisper_ready = runtime_scope.get("WhisperModel") is not None
    last_capture_error = str(runtime_scope.get("VOICE_LAST_CAPTURE_ERROR") or "").strip()

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
        "input_device": str(runtime_scope.get("VOICE_INPUT_DEVICE_NAME") or "").strip(),
        "input_device_index": runtime_scope.get("VOICE_INPUT_DEVICE_INDEX"),
        "last_capture_error": last_capture_error,
        "note": note,
    }


def record_seconds(
    seconds: int = 3,
    *,
    ensure_voice_deps_fn: Callable[[], bool],
    runtime_scope: MutableMapping[str, Any],
    sample_rate: int,
    channels: int,
    preferred_input_device: Any = "",
    print_fn: Callable[..., None] = print,
):
    sd = runtime_scope.get("sd")
    if not ensure_voice_deps_fn() or sd is None:
        raise RuntimeError(f"Voice is disabled (import error: {runtime_scope.get('VOICE_IMPORT_ERR') or ''})")
    runtime_scope["VOICE_LAST_CAPTURE_ERROR"] = ""

    candidates = _ordered_input_candidates(sd, preferred_input_device, runtime_scope)
    if not candidates:
        raise RuntimeError("No microphone input devices available")

    selected_pos = 0
    selected_index, selected_device = candidates[selected_pos]

    def _apply_selected(idx: int, dev: dict) -> tuple[str, int]:
        name = str(dev.get("name") or "").strip()
        max_input_channels = max(1, int(dev.get("max_input_channels", 1) or 1))
        channels_local = max(1, min(4, max_input_channels))
        runtime_scope["VOICE_INPUT_DEVICE_INDEX"] = idx
        runtime_scope["VOICE_INPUT_DEVICE_NAME"] = name
        runtime_scope["VOICE_CAPTURE_CHANNELS"] = channels_local
        return name, channels_local

    selected_name, capture_channels = _apply_selected(selected_index, selected_device)

    max_seconds = max(3.0, float(seconds or 0))
    min_seconds = min(2.0, max_seconds)
    start_timeout_sec = min(max_seconds, 6.0)
    silence_hang_sec = 1.0
    energy_threshold = 550
    chunk_seconds = 0.20

    print_fn(f"Nova: microphone input -> {selected_name or 'unknown'} (index {selected_index})", flush=True)
    print_fn(
        f"Nova: recording up to {int(max_seconds)} seconds... (auto-stop after you stop talking, channels={capture_channels})",
        flush=True,
    )

    chunks: list[Any] = []
    heard_speech = False
    trailing_silence = 0.0
    elapsed = 0.0
    start_time = time.monotonic()

    while elapsed < max_seconds:
        remaining = max_seconds - elapsed
        this_chunk_sec = min(chunk_seconds, remaining)
        frames = max(1, int(this_chunk_sec * sample_rate))
        while True:
            try:
                chunk = sd.rec(
                    frames,
                    samplerate=sample_rate,
                    channels=capture_channels,
                    dtype="int16",
                    device=selected_index,
                )
                sd.wait()
                runtime_scope["VOICE_WORKING_INPUT_DEVICE_INDEX"] = selected_index
                break
            except Exception as exc:
                if selected_pos + 1 >= len(candidates):
                    runtime_scope["VOICE_LAST_CAPTURE_ERROR"] = str(exc)
                    raise RuntimeError(f"Unable to open microphone input device: {exc}") from exc
                selected_pos += 1
                selected_index, selected_device = candidates[selected_pos]
                selected_name, capture_channels = _apply_selected(selected_index, selected_device)
                print_fn(
                    f"Nova: microphone fallback -> {selected_name or 'unknown'} (index {selected_index})",
                    flush=True,
                )

        # Keep compatibility with test doubles that return sentinel values.
        if not hasattr(chunk, "shape") and not hasattr(chunk, "astype"):
            return chunk

        chunks.append(chunk)
        elapsed += this_chunk_sec
        peak = _chunk_peak_abs(chunk)

        if peak >= energy_threshold:
            heard_speech = True
            trailing_silence = 0.0
        elif heard_speech:
            trailing_silence += this_chunk_sec

        if heard_speech and elapsed >= min_seconds and trailing_silence >= silence_hang_sec:
            break

        if not heard_speech and (time.monotonic() - start_time) >= start_timeout_sec and elapsed >= min_seconds:
            break

    if not heard_speech:
        capture_error = (
            "No speech was detected from the microphone. "
            "The mic may be muted, turned off, disconnected, or not receiving input."
        )
        runtime_scope["VOICE_LAST_CAPTURE_ERROR"] = capture_error
        raise RuntimeError(capture_error)

    return _concat_audio_chunks(chunks, runtime_scope)


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
    prepared_audio = _downmix_to_mono(audio_int16, runtime_scope)
    buf = io.BytesIO()
    wav.write(buf, sample_rate, prepared_audio)
    buf.seek(0)
    segments, _ = model.transcribe(buf)
    segment_list = list(segments)
    if _segments_indicate_no_usable_speech(segment_list):
        capture_error = (
            "The microphone did not produce usable speech. "
            "It may be muted, off, too quiet, or capturing background noise instead of your voice."
        )
        runtime_scope["VOICE_LAST_CAPTURE_ERROR"] = capture_error
        raise RuntimeError(capture_error)
    return " ".join(seg.text.strip() for seg in segment_list).strip()


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
