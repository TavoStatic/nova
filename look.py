import base64
import io
from pathlib import Path
import requests
import mss
from PIL import Image
from services.nova_vision_runtime import vision_model_from_policy_file

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = vision_model_from_policy_file(Path(__file__).resolve().parent)
TIMEOUT_SECONDS = 1800


def screenshot_png_bytes():
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

def ask_ollama_with_image(prompt: str, png_bytes: bytes) -> str:
    b64 = base64.b64encode(png_bytes).decode("utf-8")
    payload = {
        "model": MODEL,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [b64],
            }
        ],
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()

if __name__ == "__main__":
    print("Nova: taking screenshot...")
    img = screenshot_png_bytes()
    print("Nova: sending to Ollama (this can take a bit)...")
    prompt = "Describe what is on my screen. Extract readable text."
    result = ask_ollama_with_image(prompt, img)
    print("Nova: done.\n")
    print(result)
