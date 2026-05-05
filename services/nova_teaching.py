from __future__ import annotations

import difflib
import json
import re
from pathlib import Path


def apply_reply_overrides(reply: str, *, updates_dir: Path) -> str:
    """Return a taught correction when the reply matches a stored teach example."""
    try:
        examples_file = updates_dir / "teaching" / "examples.jsonl"
        if not examples_file.exists():
            return reply

        def _norm(value: str) -> str:
            return re.sub(r"\s+", " ", (value or "").strip())

        def _loose_norm(value: str) -> str:
            base = _norm(value).lower()
            base = re.sub(r"[^a-z0-9 ]+", " ", base)
            return re.sub(r"\s+", " ", base).strip()

        target = _norm(reply)
        target_loose = _loose_norm(reply)
        best_ratio = 0.0
        best_corr = ""

        with examples_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    original = _norm(row.get("orig") or "")
                    correction = row.get("corr") or ""
                    if original and original == target:
                        return correction
                    original_loose = _loose_norm(original)
                    if original_loose and original_loose == target_loose:
                        return correction
                    if original_loose and target_loose:
                        ratio = difflib.SequenceMatcher(None, target_loose, original_loose).ratio()
                        if ratio > best_ratio:
                            best_ratio = ratio
                            best_corr = correction
                except Exception:
                    continue
        if best_ratio >= 0.94 and best_corr:
            return best_corr
    except Exception:
        pass
    return reply
