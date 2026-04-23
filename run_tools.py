import argparse

import nova_core
import planner_decision
from services.tool_console import ToolConsoleService
from services.voice_interaction import VOICE_INTERACTION_SERVICE

DEFAULT_RECORD_SECONDS = 6


def _tool_console_service() -> ToolConsoleService:
    return ToolConsoleService(
        decide_turn_fn=planner_decision.decide_turn,
        execute_planned_action_fn=nova_core.execute_planned_action,
        handle_commands_fn=nova_core.handle_commands,
        describe_tools_fn=nova_core.TOOL_REGISTRY_SERVICE.describe_tools,
    )


def record_seconds(seconds=6):
    return VOICE_INTERACTION_SERVICE.record_seconds(seconds)


def transcribe(model, audio_int16):
    return VOICE_INTERACTION_SERVICE.transcribe(model, audio_int16)


def ask_nova(text):
    return VOICE_INTERACTION_SERVICE.chat(text, session_id="run-tools")


def speak(text):
    VOICE_INTERACTION_SERVICE.speak(text)


def list_tools_text() -> str:
    return _tool_console_service().list_tools_text()


def handle_tools(user_text: str):
    return _tool_console_service().handle_tools(user_text, emit_status=print)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--list-tools", action="store_true", help="List direct tool routes and registered tools, then exit.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.list_tools:
        print(list_tools_text())
        return

    print("Nova Orchestrator+Tools: loading Whisper (CPU mode)...")
    whisper = VOICE_INTERACTION_SERVICE.load_whisper(device="cpu", compute_type="int8")

    print("\nNova Orchestrator+Tools is ready.")
    print("Say things like: 'screen', 'camera', 'find mysql www', 'read 14_0_5_ZeroXIV_read_me.txt'")
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