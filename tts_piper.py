import subprocess
import sys
import tempfile
import winsound
from pathlib import Path

BASE = Path(__file__).resolve().parent
PIPER = BASE / "piper" / "piper.exe"
MODEL = BASE / "piper" / "models" / "en_US-lessac-medium.onnx"

text = " ".join(sys.argv[1:]).strip()

if not text:
    sys.exit(0)

if not PIPER.exists():
    print(f"Missing Piper executable: {PIPER}")
    sys.exit(1)

if not MODEL.exists():
    print(f"Missing Piper model: {MODEL}")
    sys.exit(1)

with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
    wav = f.name

subprocess.run(
    [str(PIPER), "--model", str(MODEL), "--output_file", wav],
    input=text,
    text=True
)

winsound.PlaySound(wav, winsound.SND_FILENAME)