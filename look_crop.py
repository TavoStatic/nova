import base64
import io
import requests
import mss
from PIL import Image

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5vl:7b"

TIMEOUT_SECONDS = 1800  # 30 minutes (first runs can be slow)

def screenshot_center_crop_png_bytes(crop_w=1400, crop_h=900):
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.rgb)

        W, H = img.size
        left = max(0, (W - crop_w) // 2)
        top  = max(0, (H - crop_h) // 2)
        right = min(W, left + crop_w)
        bottom = min(H, top + crop_h)

        cropped = img.crop((left, top, right, bottom))
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
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
    data = r.json()
    return data["message"]["content"].strip()

if __name__ == "__main__":
    import time
    print("Nova: screenshot in 3 seconds... put the target window in the center.")
    time.sleep(3)
    print("Nova: taking center crop screenshot...")
    img = screenshot_center_crop_png_bytes()
    print("Nova: sending to Ollama (can take a while the first time)...")
    prompt = "Extract ALL readable text. Then summarize what I'm looking at."
    result = ask_ollama_with_image(prompt, img)
    print("\nNova: done.\n")
    print(result)