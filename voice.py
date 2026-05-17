import nova_core
import nova_http
from services.voice_interaction import VoiceInteractionService


def _fallback_chat(text: str) -> str:
    return nova_core.ollama_chat(
        text,
        retrieved_context="",
        language_mix_spanish_pct=0,
    )


VOICE_INTERACTION_SERVICE = VoiceInteractionService(
    whisper_size_fn=nova_core.whisper_size,
    record_seconds_fn=nova_core.record_seconds,
    transcribe_fn=nova_core.transcribe,
    chat_fn=lambda session_id, text, user_id: nova_http.process_chat(session_id, text, user_id=user_id),
    fallback_chat_fn=_fallback_chat,
)

DEFAULT_RECORD_SECONDS = 6


def record_push_to_talk(seconds=6):
    return VOICE_INTERACTION_SERVICE.record_seconds(seconds)


def transcribe_whisper(model, audio_int16):
    return VOICE_INTERACTION_SERVICE.transcribe(model, audio_int16)


def ask_nova(text):
    return VOICE_INTERACTION_SERVICE.chat(text, session_id="voice-cli")


def speak(text):
    VOICE_INTERACTION_SERVICE.speak(text)


def main():
    print("Nova: loading Whisper (CPU mode)...")

    whisper = VOICE_INTERACTION_SERVICE.load_whisper(device="cpu", compute_type="int8")

    print("\nNova Voice is ready.")
    print("Press ENTER to talk (records ~6 seconds). Type 'q' then ENTER to quit.\n")

    while True:
        cmd = input("> ").strip().lower()
        if cmd == "q":
            break

        audio = record_push_to_talk(DEFAULT_RECORD_SECONDS)

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
