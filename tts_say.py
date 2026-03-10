import sys

# One-shot SAPI5 TTS.
# Short-lived process to avoid pyttsx3/SAPI deadlocks in long-running apps.

def main():
    text = " ".join(sys.argv[1:]).strip()
    if not text:
        return 0
    try:
        import pyttsx3
        e = pyttsx3.init(driverName="sapi5")
        e.setProperty("rate", 175)
        e.say(text)
        e.runAndWait()
        try:
            e.stop()
        except Exception:
            pass
        return 0
    except Exception as ex:
        sys.stderr.write(f"[TTS_FAIL] {ex}\n")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
