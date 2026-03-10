import base64
import io
import sys
import requests
import cv2
from PIL import Image

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5vl:7b"

def webcam_png_bytes(cam_index=0):
    cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)

    if not cap.isOpened():
        raise RuntimeError("Could not open webcam.")

    # warm up camera
    for _ in range(5):
        cap.read()

    ok, frame = cap.read()
    cap.release()

    if not ok:
        raise RuntimeError("Could not capture frame.")

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(frame_rgb)

    buf = io.BytesIO()
    img.save(buf, format="PNG")

    return buf.getvalue()

def ask_ollama(prompt, img_bytes):
    b64 = base64.b64encode(img_bytes).decode("utf-8")

    payload = {
        "model": MODEL,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [b64]
            }
        ]
    }

    r = requests.post(OLLAMA_URL, json=payload, timeout=1800)
    r.raise_for_status()

    return r.json()["message"]["content"]

if __name__ == "__main__":

    prompt = "Describe what you see."

    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])

    print("Nova: activating camera in 3 seconds...")
    import time
    time.sleep(3)

    img = webcam_png_bytes()

    print("Nova: analyzing image...\n")

    result = ask_ollama(prompt, img)

    print(result)