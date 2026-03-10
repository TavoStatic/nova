import io
import sys
import time
import requests
import sounddevice as sd
import scipy.io.wavfile as wav
import pyttsx3
from faster_whisper import WhisperModel

OLLAMA_URL = "http://localhost:11434/api/chat"
LLM_MODEL  = "llama3.1:8b"

WHISPER_SIZE = "small"
SAMPLE_RATE = 16000
CHANNELS = 1


def record_push_to_talk(seconds=6):
    print(f"Nova: recording for {seconds} seconds... (talk now)")
    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                   channels=CHANNELS, dtype="int16")
    sd.wait()
    return audio


def transcribe_whisper(model, audio_int16):
    buf = io.BytesIO()
    wav.write(buf, SAMPLE_RATE, audio_int16)
    buf.seek(0)

    segments, _ = model.transcribe(buf)
    text = ""
    for seg in segments:
        text += seg.text.strip() + " "
    return text.strip()


def ask_nova(text):
    payload = {
        "model": LLM_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": "You are Nova. Be helpful, concise, practical."},
            {"role": "user", "content": text},
        ],
    }

    r = requests.post(OLLAMA_URL, json=payload, timeout=1800)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def speak(text):
    engine = pyttsx3.init()
    engine.setProperty("rate", 175)
    engine.say(text)
    engine.runAndWait()


def main():
    print("Nova: loading Whisper (CPU mode)...")

    # FORCE CPU
    whisper = WhisperModel(
        WHISPER_SIZE,
        device="cpu",
        compute_type="int8"
    )

    print("\nNova Voice is ready.")
    print("Press ENTER to talk (records ~6 seconds). Type 'q' then ENTER to quit.\n")

    while True:
        cmd = input("> ").strip().lower()
        if cmd == "q":
            break

        audio = record_push_to_talk(6)

        print("Nova: transcribing...")
        text = transcribe_whisper(whisper, audio)

        if not text:
            print("Nova: (heard nothing)\n")
            continue

        print(f"You: {text}")
        print("Nova: thinking...")
        reply = ask_nova(text)
        print(f"Nova: {reply}\n")

        speak(reply)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass