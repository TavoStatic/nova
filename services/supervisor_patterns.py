from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    normalized = str(text or "").lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()
