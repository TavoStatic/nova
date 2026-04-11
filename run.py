from services.voice_interaction import VOICE_INTERACTION_SERVICE

DEFAULT_RECORD_SECONDS = 6

def record_seconds(seconds=6):
    return VOICE_INTERACTION_SERVICE.record_seconds(seconds)

def transcribe(model, audio_int16):
    return VOICE_INTERACTION_SERVICE.transcribe(model, audio_int16)

def ask_nova(text):
    return VOICE_INTERACTION_SERVICE.chat(text, session_id="run-cli")

def speak(text):
    VOICE_INTERACTION_SERVICE.speak(text)

def main():
    print("Nova Orchestrator: loading Whisper (CPU mode)...")
    whisper = VOICE_INTERACTION_SERVICE.load_whisper(device="cpu", compute_type="int8")

    print("\nNova Orchestrator is ready.")
    print("Press ENTER to talk (records ~6 seconds). Type 'q' then ENTER to quit.\n")

    while True:
        cmd = input("> ").strip().lower()
        if cmd == "q":
            break

        audio = record_seconds(DEFAULT_RECORD_SECONDS)

        print("Nova: transcribing...")
        text = transcribe(whisper, audio)

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