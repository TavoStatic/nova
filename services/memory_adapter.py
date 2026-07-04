from __future__ import annotations

import os
import json
import re
from typing import Callable, Optional

from services.memory_retention import parse_retention_policy


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

    def mem_retention_policy(self) -> dict:
        return parse_retention_policy(self._policy_memory_getter())

    def mem_recall_exclude_kinds(self) -> list[str]:
        return list(self.mem_retention_policy().get("recall_exclude_kinds") or [])

    def memory_kind_store_allowed(self, kind: str) -> tuple[bool, str]:
        blocked = {
            str(item or "").strip().lower()
            for item in list(self.mem_retention_policy().get("store_blocked_kinds") or [])
            if str(item or "").strip()
        }
        normalized = str(kind or "").strip().lower()
        if normalized in blocked:
            return False, "policy_blocked_kind"
        return True, "allowed"

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

        if low.endswith("?"):
            return False, "question"

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

        words = re.findall(r"[A-Za-z0-9_]+", t)
        has_number = bool(re.search(r"\b\d{2,}\b", t))
        if has_number:
            return True, "structured_value"

        if len(words) >= 8:
            return True, "long_statement"

        if len(words) >= 3:
            return True, "declarative_statement"

        return False, "low_signal"

    def mem_should_store(self, text: str) -> bool:
        keep, _reason = self.memory_should_keep_text(text)
        return keep

    def format_memory_recall_hits(self, hits) -> str:
        bullets = []
        seen = set()
        norm = lambda s: re.sub(r"\W+", " ", (s or "").lower()).strip()
        excluded_kinds = {
            str(item or "").strip().lower()
            for item in self.mem_recall_exclude_kinds()
            if str(item or "").strip()
        }
        for _score, _ts, kind, _source, _user_row, text in (hits or []):
            if str(kind or "").strip().lower() in excluded_kinds:
                continue
            p = self._format_recall_text(kind, text)
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

    @staticmethod
    def _format_recall_text(kind: str, text: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return ""

        if str(kind or "").strip().lower() == "user_correction":
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {}
            parsed = str(payload.get("parsed_correction") or "").strip()
            if parsed:
                return f"Correction: {parsed}"
            return ""

        return raw
