"""Export Grok session JSONL to readable verbatim chat."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT = ROOT / "nova_grok.jsonl"
TRANSCRIPT_FALLBACK = Path(
    r"C:\Users\hotst\.grok\sessions\C%3A%5Cnova\019f0c47-dd5f-7503-9b16-0f083699f775\updates.jsonl"
)
OUT = Path(__file__).resolve().parents[1] / "nova_grok.md"
HANDOFF_HEADER = Path(__file__).resolve().parents[1] / "nova_grok_handoff.md"


def _text_from_update(update: dict) -> str:
    content = update.get("content")
    if isinstance(content, dict):
        return str(content.get("text") or "")
    return str(content or "")


def extract_turns(path: Path) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    current_role = ""
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_role, current_parts
        if current_role and current_parts:
            text = "".join(current_parts).strip()
            if text:
                turns.append((current_role, text))
        current_role = ""
        current_parts = []

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            update = (payload.get("params") or {}).get("update") or {}
            kind = str(update.get("sessionUpdate") or "")
            if kind == "user_message_chunk":
                if current_role != "user":
                    flush()
                    current_role = "user"
                current_parts.append(_text_from_update(update))
            elif kind == "agent_message_chunk":
                if current_role != "assistant":
                    flush()
                    current_role = "assistant"
                current_parts.append(_text_from_update(update))
            elif kind in {"turn_completed", "user_message"}:
                flush()
    flush()
    return turns


def render_transcript(turns: list[tuple[str, str]], *, source: Path) -> str:
    lines = [
        "# nova_grok — full session transcript",
        "",
        f"**Source:** `{source}`",
        f"**Turns:** {len(turns)}",
        "",
        "---",
        "",
    ]
    turn_no = 0
    for role, text in turns:
        turn_no += 1
        label = "USER" if role == "user" else "ASSISTANT"
        lines.append(f"## Turn {turn_no} — {label}")
        lines.append("")
        lines.append(text)
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    source = TRANSCRIPT if TRANSCRIPT.exists() else TRANSCRIPT_FALLBACK
    if not source.exists():
        print(f"transcript missing: {TRANSCRIPT} and {TRANSCRIPT_FALLBACK}", file=sys.stderr)
        return 1

    turns = extract_turns(source)
    transcript_body = render_transcript(turns, source=source)

    handoff = ""
    if HANDOFF_HEADER.exists():
        handoff = HANDOFF_HEADER.read_text(encoding="utf-8").strip() + "\n\n"
    elif OUT.exists():
        # preserve existing handoff block before first verbatim marker
        existing = OUT.read_text(encoding="utf-8")
        marker = "# nova_grok — full session transcript"
        if marker in existing:
            handoff = existing.split(marker, 1)[0].strip() + "\n\n"
        else:
            handoff = existing.strip() + "\n\n"

    OUT.write_text(handoff + transcript_body, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(turns)} turns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())