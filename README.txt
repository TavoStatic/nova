Nova bundle v5 — Subprocess TTS (reliable)

Goal:
- Fix Windows TTS going silent after the first interaction.

Approach:
- Speak via a short-lived subprocess (tts_say.py) for each utterance.
- Avoids pyttsx3/SAPI5 deadlocks in long-running processes.

Install:
1) Unzip into C:\Nova
   - overwrite: nova_core.py
   - add: tts_say.py
2) Run:
   nova run
