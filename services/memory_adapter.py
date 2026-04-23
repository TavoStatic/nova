from __future__ import annotations

import os
import re
from typing import Callable, Optional


class MemoryAdapterService:
    """Encapsulates memory policy config and write/keep heuristics."""

    def __init__(
        self,
        *,
        policy_memory_getter: Callable[[], dict],
        active_user_getter: Callable[[], Optional[str]],
    ) -> None:
        self._policy_memory_getter = policy_memory_getter
        self._active_user_getter = active_user_getter

    def mem_enabled(self) -> bool:
        return bool(self._policy_memory_getter().get("enabled", False))

    def mem_top_k(self) -> int:
        try:
            return int(self._policy_memory_getter().get("top_k", 5))
        except Exception:
            return 5

    def mem_scope(self) -> str:
        raw = str(self._policy_memory_getter().get("scope", "private") or "private").strip().lower()
        if raw not in {"private", "shared", "hybrid"}:
            return "private"
        return raw

    def mem_context_top_k(self) -> int:
        try:
            v = int(self._policy_memory_getter().get("context_top_k", 3))
            return max(1, min(v, 10))
        except Exception:
            return 3

    def mem_min_score(self) -> float:
        try:
            return float(self._policy_memory_getter().get("min_score", 0.25))
        except Exception:
            return 0.25

    def mem_exclude_sources(self) -> list[str]:
        xs = self._policy_memory_getter().get("exclude_sources") or []
        return [str(x) for x in xs if x]

    def mem_store_min_chars(self) -> int:
        try:
            return int(self._policy_memory_getter().get("store_min_chars", 12))
        except Exception:
            return 12

    def mem_store_exclude_patterns(self) -> list[str]:
        xs = self._policy_memory_getter().get("store_exclude_patterns") or []
        out = []
        for x in xs:
            s = str(x or "").strip()
            if s:
                out.append(s)
        return out

    def mem_store_include_patterns(self) -> list[str]:
        xs = self._policy_memory_getter().get("store_include_patterns") or []
        out = []
        for x in xs:
            s = str(x or "").strip()
            if s:
                out.append(s)
        return out

    @staticmethod
    def default_local_user_id() -> str:
        raw = (
            os.environ.get("NOVA_USER_ID")
            or os.environ.get("NOVA_CHAT_USER")
            or os.environ.get("USER")
            or os.environ.get("LOGNAME")
            or os.environ.get("USERNAME")
            or ""
        )
        return re.sub(r"[^A-Za-z0-9._-]", "", str(raw).strip())[:64]

    def memory_write_user(self) -> str | None:
        scope = self.mem_scope()
        active_user = (self._active_user_getter() or "").strip()
        if scope == "shared":
            return ""
        if active_user:
            return active_user
        if scope == "hybrid":
            return ""
        fallback_user = self.default_local_user_id()
        return fallback_user or None

    def memory_runtime_user(self) -> str | None:
        user = (self._active_user_getter() or "").strip()
        if self.mem_scope() == "private" and not user:
            user = self.default_local_user_id()
        if self.mem_scope() == "private" and not user:
            return None
        return user or None

    def memory_should_keep_text(self, text: str) -> tuple[bool, str]:
        t = (text or "").strip()
        if not t:
            return False, "empty"

        low = t.lower()
        if len(t) < self.mem_store_min_chars():
            return False, "too_short"

        q_starts = (
            "what ", "where ", "who ", "why ", "how ", "when ", "which ",
            "do ", "did ", "can ", "could ", "would ", "is ", "are ", "should ",
        )
        if low.endswith("?") or any(low.startswith(q) for q in q_starts):
            return False, "question"

        low_value = {
            "ok", "okay", "k", "kk", "yes", "no", "thanks", "thank you",
            "done", "cool", "nice", "great", "sounds good", "got it", "understood",
        }
        if low in low_value:
            return False, "ack"

        noise_prefixes = (
            "tip:", "nova:", "assistant:", "user:", "i couldn't find grounded sources",
            "please try:", "network error:", "loading", "checking",
        )
        if any(low.startswith(p) for p in noise_prefixes):
            return False, "ui_noise"

        for pat in self.mem_store_exclude_patterns():
            try:
                if re.search(pat, t, flags=re.I):
                    return False, "policy_exclude"
            except re.error:
                if pat.lower() in low:
                    return False, "policy_exclude"

        for pat in self.mem_store_include_patterns():
            try:
                if re.search(pat, t, flags=re.I):
                    return True, "policy_include"
            except re.error:
                if pat.lower() in low:
                    return True, "policy_include"

        durable_markers = (
            "my name is", "i am", "i'm", "i live in", "my location is", "i work",
            "my favorite", "i like ", "developer", "gus", "gustavo", "peims",
            "always", "never", "remember this", "learned_fact:",
        )
        has_number = bool(re.search(r"\b\d{2,}\b", t))
        if any(m in low for m in durable_markers) or has_number:
            return True, "durable_fact"

        if len(t.split()) >= 8:
            return True, "long_statement"

        return False, "low_signal"

    def mem_should_store(self, text: str) -> bool:
        keep, _reason = self.memory_should_keep_text(text)
        return keep

    def format_memory_recall_hits(self, hits) -> str:
        bullets = []
        seen = set()
        norm = lambda s: re.sub(r"\W+", " ", (s or "").lower()).strip()
        for _score, _ts, _kind, _source, _user_row, text in (hits or []):
            p = (text or "").strip()
            if not p:
                continue
            one = re.sub(r"\s+", " ", p).strip()
            n = norm(one)
            if n in seen:
                continue
            seen.add(n)
            bullets.append(f"- {one[:260]}")
        bullets = bullets[:max(1, int(self.mem_context_top_k()))]
        return "\n".join(bullets)[:2000] if bullets else ""
