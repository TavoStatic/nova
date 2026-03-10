import io
import subprocess
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

PYTHON = r"C:\Nova\.venv\Scripts\python.exe"

def record_seconds(seconds=6):
    print(f"Nova: recording for {seconds} seconds... (talk now)")
    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                   channels=CHANNELS, dtype="int16")
    sd.wait()
    return audio

def transcribe(model, audio_int16):
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

def run_tool(args):
    # run a helper script and return printed output
    p = subprocess.run([PYTHON] + args, capture_output=True, text=True)
    out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    return out.strip()

def handle_tools(user_text: str):
    t = user_text.strip()
    low = t.lower()

    # tool: screen
    if "screen" in low:
        print("Nova: tool -> screen (center crop)")
        return run_tool([r"C:\Nova\look_crop.py"])

    # tool: camera
    if "camera" in low:
        prompt = "Describe what you see."
        # allow: "camera read the text" etc.
        if "camera" in low and len(t.split()) > 1:
            prompt = t
        print("Nova: tool -> camera")
        return run_tool([r"C:\Nova\camera.py", prompt])

    # tool: find <keyword> [folder]
    if low.startswith("find "):
        parts = t.split(maxsplit=2)
        keyword = parts[1] if len(parts) > 1 else ""
        folder = parts[2] if len(parts) > 2 else ""
        print("Nova: tool -> find")
        args = [r"C:\Nova\agent.py", "find", keyword]
        if folder:
            args.append(folder)
        return run_tool(args)

    # tool: read <file>
    if low.startswith("read "):
        file_part = t.split(maxsplit=1)[1]
        print("Nova: tool -> read")
        return run_tool([r"C:\Nova\agent.py", "read", file_part])

    return None

def main():
    print("Nova Orchestrator+Tools: loading Whisper (CPU mode)...")
    whisper = WhisperModel(WHISPER_SIZE, device="cpu", compute_type="int8")

    print("\nNova Orchestrator+Tools is ready.")
    print("Say things like: 'screen', 'camera', 'find mysql www', 'read 14_0_5_ZeroXIV_read_me.txt'")
    print("Press ENTER to talk (records ~6 seconds). Type 'q' then ENTER to quit.\n")

    while True:
        cmd = input("> ").strip().lower()
        if cmd == "q":
            break

        audio = record_seconds(6)

        print("Nova: transcribing...")
        text = transcribe(whisper, audio)

        if not text:
            print("Nova: (heard nothing)\n")
            continue

        print(f"You: {text}")

        tool_out = handle_tools(text)
        if tool_out is not None:
            # Speak + print tool output directly
            print(f"Nova (tool output):\n{tool_out}\n")
            speak("Done.")
            continue

        print("Nova: thinking...")
        reply = ask_nova(text)
        print(f"Nova: {reply}\n")
        speak(reply)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass