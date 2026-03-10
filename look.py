import base64
import io
import requests
import mss
from PIL import Image

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5vl:7b"
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
        "prompt": prompt,
        "stream": False,
        "images": [b64],
    }
    r = requests.post(OLLAMA_URL, json=payload)
    r.raise_for_status()
    return r.json()["response"]

if __name__ == "__main__":
    print("Nova: taking screenshot...")
    img = screenshot_png_bytes()
    print("Nova: sending to Ollama (this can take a bit)...")
    prompt = "Describe what is on my screen. Extract readable text."
    result = ask_ollama_with_image(prompt, img)
    print("Nova: done.\n")
    print(result)