import sys
import subprocess
from pathlib import Path

# One-shot SAPI5 TTS.
# Short-lived process to avoid pyttsx3/SAPI deadlocks in long-running apps.

BASE = Path(__file__).resolve().parent


def _select_preferred_voice(engine) -> None:
    try:
        voices = list(engine.getProperty("voices") or [])
    except Exception:
        voices = []
    if not voices:
        return

    preferred = None
    for voice in voices:
        name = str(getattr(voice, "name", "") or "")
        voice_id = str(getattr(voice, "id", "") or "")
        combined = f"{name} {voice_id}".lower()
        if "zira" in combined:
            preferred = voice
            break

    if preferred is None:
        for voice in voices:
            gender = str(getattr(voice, "gender", "") or "").lower()
            name = str(getattr(voice, "name", "") or "").lower()
            if "female" in gender or "female" in name or "zira" in name:
                preferred = voice
                break

    if preferred is not None:
        engine.setProperty("voice", getattr(preferred, "id", None))

def main():
    text = " ".join(sys.argv[1:]).strip()
    if not text:
        return 0
    if sys.platform.startswith("win"):
        try:
            return subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(BASE / "tts_say.ps1"),
                    text,
                ],
                check=False,
            ).returncode
        except Exception:
            pass
    try:
        import pyttsx3
        e = pyttsx3.init(driverName="sapi5")
        _select_preferred_voice(e)
        e.setProperty("rate", 175)
        e.say(text)
        e.runAndWait()
        try:
            e.stop()
        except Exception:
            pass
        return 0
    except Exception as ex:
        sys.stderr.write(f"[TTS_FAIL] {ex}\n")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
