import os
import subprocess
import sys
import tempfile
import winsound
from pathlib import Path

BASE = Path(__file__).resolve().parent
PIPER = BASE / "piper" / "piper.exe"
MODEL = BASE / "piper" / "models" / "en_US-lessac-medium.onnx"
ESPEAK_DATA = BASE / "piper" / "espeak-ng-data"

text = " ".join(sys.argv[1:]).strip()


def _prefer_windows_sapi() -> bool:
    engine = str(os.environ.get("NOVA_TTS_ENGINE") or "sapi").strip().lower()
    return os.name == "nt" and engine != "piper"


def _fallback_tts(message: str) -> int:
    try:
        return subprocess.run([sys.executable, str(BASE / "tts_say.py"), message], check=False).returncode
    except Exception:
        return 2

if not text:
    sys.exit(0)

if _prefer_windows_sapi():
    sys.exit(_fallback_tts(text))

if not PIPER.exists():
    print(f"Missing Piper executable: {PIPER}; falling back to SAPI one-shot")
    sys.exit(_fallback_tts(text))

if not MODEL.exists():
    print(f"Missing Piper model: {MODEL}; falling back to SAPI one-shot")
    sys.exit(_fallback_tts(text))

with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
    wav = f.name

proc = subprocess.run(
    [
        str(PIPER),
        "--model",
        str(MODEL),
        "--output_file",
        wav,
        "--espeak_data",
        str(ESPEAK_DATA),
    ],
    input=text,
    text=True,
    capture_output=True,
    env={
        **os.environ,
        "ESPEAK_DATA_PATH": str(ESPEAK_DATA),
    },
)
if proc.returncode != 0:
    print((proc.stderr or proc.stdout or "").strip())
    sys.exit(_fallback_tts(text))

winsound.PlaySound(wav, winsound.SND_FILENAME)