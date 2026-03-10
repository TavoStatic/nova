# Nova (stable core)

This bundle is a **clean, self-contained** Nova core.

## What changed
- `nova_core.py` is now stable and **supports both**:
  - Voice input (press ENTER)
  - Typed input (type message/command and press ENTER)
- Piper TTS is used via `tts_piper.py` (oneshot per utterance) with **chunked speaking** to avoid timeouts.
- Adds **Knowledge Packs (B-mode)** (lightweight lexical search, no embeddings).
- Adds **Self Patching** with snapshot + rollback (zip overlay + compile check).

## Knowledge packs (B-mode)
Commands inside Nova:
- `kb list`
- `kb use <pack>`
- `kb off`
- `kb add <zip_path> <pack_name>`

Knowledge packs live in:
- `C:\Nova\knowledge\packs\<pack_name>\*.txt|*.md`

Active pack is stored in:
- `C:\Nova\knowledge\active_pack.txt`

## Self patching
Commands inside Nova:
- `patch apply <zip_path>`
- `patch rollback`

Snapshots are stored in:
- `C:\Nova\updates\snapshots\snapshot_*.zip`

Safety rules:
- Only overlays: `.py .json .md .txt .ps1 .cmd`
- Skips: `.venv, runtime, logs, models`
- Runs `python -m compileall` and **auto-rolls back** on failure.

## Start
From PowerShell:
- `nova run`
