from __future__ import annotations

import difflib
import json
import re
import time
from datetime import datetime
from typing import Optional

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore[assignment]

from services.work_tree_decision_adapter import WORK_TREE_DECISION_ADAPTER

_OLLAMA_BASE = "http://127.0.0.1:11434"

# Tools that are valid for system-internal work trees.
# Must be a strict subset of work_tree._KNOWN_TOOL_NAMES.
_SYSTEM_TOOL_NAMES = frozenset({
    "health",
    "system_check",
    "queue_status",
    "phase2_audit",
    "pulse",
    "read",
    "ls",
    "find",
    "patch_preview_apply",
    "patch_apply",
    "patch_rollback",
    "update_now",
})

_EXPLICIT_WORK_TREE_PHRASES = (
    "start a work tree",
    "create a work tree",
    "make a work tree",
    "open a work tree",
    "use a work tree",
    "track this in a work tree",
    "put this in a work tree",
    "create work tree",
    "start work tree",
    "build work tree",
    "work tree for",
)

_SYSTEM_NERVOUS_SYSTEM_CUES = (
    "runtime",
    "health",
    "system status",
    "heartbeat",
    "pulse",
    "queue",
    "backlog",
    "generated work",
    "subconscious",
    "pressure",
    "drift",
    "parity",
    "seam",
    "regression",
    "patch",
    "release",
    "assessment",
    "operator",
    "guard",
    "worker",
    "maintenance",
)

_CONTENT_ORIENTED_CUES = (
    "news",
    "wikipedia",
    "research",
    "attendance guidance",
    "district action items",
    "summarize ",
    "collect ",
    "write a blog",
)

_DECOMPOSE_SYSTEM = (
    "You are a system maintenance task decomposition engine for a local AI runtime called Nova. "
    "Nova's work tree is used ONLY for internal system health and maintenance tasks — "
    "NOT for user content research, web searches, or external data gathering. "
    "Break the given system maintenance task into 2 to 4 sequential steps. "
    "Each step is a concise action phrase of at most 60 characters describing a system check or repair action. "
    "For each step choose the single best tool from: "
    "health, system_check, pulse, queue_status, read, ls, patch_apply, patch_rollback, update_now. "
    "Reply ONLY with a JSON array — no markdown, no prose, no code fences. "
    'Example: [{"title":"check runtime pulse","tool":"pulse"},{"title":"verify Ollama model availability","tool":"health"}]'
)


class WorkTreeSeedingService:
    """Own initial work-tree branch seeding outside HTTP transport glue."""

    _STOPWORDS = frozenset({
        "a", "an", "the", "to", "for", "of", "in", "on", "and", "or", "with", "this", "that",
        "please", "nova", "work", "tree", "create", "start", "make", "open", "use", "build", "track", "put",
        "then", "also", "next",
    })

    _FOLLOWUP_CONTINUATION_CUES = (
        "also",
        "and",
        "then",
        "next",
        "after that",
        "while you're at it",
        "while you re at it",
        "in the same work",
        "same work",
        "same tree",
        "keep going",
    )
    _OUTCOME_WINDOW_SECONDS = 5 * 60
    _REOPEN_WINDOW_SECONDS = 15 * 60
    _BRANCH_EXPLOSION_THRESHOLD = 6

    def __init__(self) -> None:
        self._last_reuse: dict[str, object] = {}
        self._pending_decisions: dict[str, dict[str, object]] = {}

    @staticmethod
    def _normalize_intake_text(text: str) -> str:
        low = str(text or "").strip().lower()
        low = re.sub(r"^[a-z]+\s*:\s*", "", low)
        low = re.sub(r"[^a-z0-9\s]", " ", low)
        return re.sub(r"\s+", " ", low).strip()

    @classmethod
    def _identity_terms(cls, text: str, *, limit: int = 10) -> list[str]:
        terms = sorted(cls._keywords(text))
        return terms[: max(1, int(limit))]

    @classmethod
    def build_work_identity_key(cls, text: str) -> str:
        """Build a stable identity key from normalized intent and key terms.

        The key intentionally avoids full-string matching so phrasing variation
        still resolves to the same work identity.
        """
        seed = cls._extract_creation_intent_seed(text)
        normalized = cls._normalize_intake_text(seed)
        if not normalized:
            return ""
        terms = cls._identity_terms(normalized, limit=10)
        if not terms:
            return ""
        intent_label = "-".join(terms[:4])
        return f"work:{intent_label}|terms:{'|'.join(terms)}"

    @classmethod
    def _work_identity_label(cls, text: str) -> str:
        terms = cls._identity_terms(text, limit=4)
        if not terms:
            return ""
        return " / ".join(terms)

    @staticmethod
    def _tree_identity_key(tree) -> str:
        meta = getattr(tree, "meta", None)
        if not isinstance(meta, dict):
            return ""
        return str(meta.get("work_identity_key") or "").strip()

    @staticmethod
    def _tree_status_value(tree) -> str:
        status = getattr(tree, "status", "")
        return str(getattr(status, "value", status) or "").strip().lower()

    def _find_tree_by_identity_key(
        self,
        *,
        work_tree_module,
        work_identity_key: str,
        preferred_tree_id: str = "",
    ) -> str:
        trees = list(work_tree_module.list_trees() or [])
        if not trees:
            return ""
        key = str(work_identity_key or "").strip()
        if not key:
            return ""

        if preferred_tree_id:
            preferred = work_tree_module.get_tree(preferred_tree_id)
            if preferred is not None and self._tree_identity_key(preferred) == key:
                return str(getattr(preferred, "tree_id", "") or "").strip()

        candidates: list[tuple[float, str]] = []
        for tree in trees:
            tree_id = str(getattr(tree, "tree_id", "") or "").strip()
            if not tree_id:
                continue
            if self._tree_identity_key(tree) != key:
                continue
            status_text = self._tree_status_value(tree)
            if status_text == "archived":
                continue
            updated = getattr(tree, "updated_at", None)
            try:
                updated_epoch = float(updated.timestamp()) if updated is not None else 0.0
            except Exception:
                updated_epoch = 0.0
            # Prefer active trees; otherwise newest matching tree wins.
            active_boost = 1_000_000_000.0 if status_text == "active" else 0.0
            candidates.append((active_boost + updated_epoch, tree_id))

        if not candidates:
            return ""
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    @classmethod
    def _looks_like_followup_continuation(cls, message: str) -> bool:
        low = cls._normalize_intake_text(message)
        if not low:
            return False
        return any(cue in low for cue in cls._FOLLOWUP_CONTINUATION_CUES)

    @classmethod
    def should_continue_active_identity(cls, *, message: str, active_work_identity: str = "") -> bool:
        active = str(active_work_identity or "").strip()
        if not active:
            return False
        key = cls.build_work_identity_key(message)
        if key and key == active:
            return True

        def _terms(identity_key: str) -> set[str]:
            raw = str(identity_key or "")
            if "|terms:" in raw:
                segment = raw.split("|terms:", 1)[1]
                return {token for token in segment.split("|") if token}
            return set()

        active_terms = _terms(active)
        next_terms = _terms(key)
        overlap = len(active_terms.intersection(next_terms)) if active_terms and next_terms else 0

        # Follow-up turns should prefer continuity even when additional detail
        # introduces new terms, as long as overlap indicates same thread.
        if cls._looks_like_followup_continuation(message) and overlap >= 2:
            return True

        # If the identity terms are highly overlapping, treat as same work.
        if active_terms and next_terms:
            smaller = max(1, min(len(active_terms), len(next_terms)))
            if float(overlap) / float(smaller) >= 0.70:
                return True

        if not key and cls._looks_like_followup_continuation(message):
            return True
        return False

    @classmethod
    def _keywords(cls, text: str) -> set[str]:
        norm = cls._normalize_intake_text(text)
        out: set[str] = set()
        for token in norm.split():
            if len(token) < 3 or token in cls._STOPWORDS:
                continue
            out.add(token)
        return out

    @classmethod
    def _title_similarity(cls, candidate_title: str, requested_title: str) -> float:
        cand = cls._normalize_intake_text(candidate_title)
        req = cls._normalize_intake_text(requested_title)
        if not cand or not req:
            return 0.0
        ratio = float(difflib.SequenceMatcher(None, cand, req).ratio())
        cand_keys = cls._keywords(cand)
        req_keys = cls._keywords(req)
        overlap = 0.0
        if cand_keys and req_keys:
            overlap = float(len(cand_keys.intersection(req_keys))) / float(len(cand_keys.union(req_keys)))
        # Weighted basic similarity: token overlap plus string ratio.
        return 0.55 * overlap + 0.45 * ratio

    @staticmethod
    def _extract_creation_intent_seed(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        normalized = re.sub(r"\s+", " ", raw).strip()
        low = normalized.lower()
        for phrase in _EXPLICIT_WORK_TREE_PHRASES:
            idx = low.find(phrase)
            if idx < 0:
                continue
            tail = normalized[idx + len(phrase):].strip(" .,:;-")
            tail = re.sub(r"^(for|about|on)\s+", "", tail, flags=re.I).strip(" .,:;-")
            if tail:
                return tail
        return normalized

    @staticmethod
    def _tree_is_recent_or_active(tree, *, now_epoch: float, recent_seconds: int) -> bool:
        status_text = str(getattr(tree, "status", "") or "").strip().lower()
        if "active" in status_text:
            return True
        updated = getattr(tree, "updated_at", None)
        if updated is None:
            return False
        try:
            updated_epoch = float(updated.timestamp())
        except Exception:
            return False
        return (now_epoch - updated_epoch) <= float(max(60, int(recent_seconds)))

    def _find_similar_existing_tree_id(
        self,
        *,
        work_tree_module,
        title_seed: str,
        similarity_threshold: float = 0.62,
        recent_seconds: int = 12 * 3600,
    ) -> str:
        trees = list(work_tree_module.list_trees() or [])
        if not trees:
            return ""

        now_epoch = time.time()
        requested = str(title_seed or "").strip()
        best_id = ""
        best_score = 0.0

        for tree in trees:
            if not self._tree_is_recent_or_active(tree, now_epoch=now_epoch, recent_seconds=recent_seconds):
                continue
            tree_id = str(getattr(tree, "tree_id", "") or "").strip()
            tree_title = str(getattr(tree, "title", "") or "").strip()
            if not tree_id or not tree_title:
                continue
            score = self._title_similarity(tree_title, requested)
            if score > best_score:
                best_score = score
                best_id = tree_id

        if best_id and best_score >= float(similarity_threshold):
            return best_id
        return ""

    def _mark_reuse(self, *, tree_id: str, request_text: str) -> None:
        self._last_reuse = {
            "tree_id": str(tree_id or "").strip(),
            "request_text": self._normalize_intake_text(request_text),
            "ts": time.time(),
            "continuity": "continuing_existing_work",
        }

    def _mark_new(self, *, tree_id: str, request_text: str) -> None:
        self._last_reuse = {
            "tree_id": str(tree_id or "").strip(),
            "request_text": self._normalize_intake_text(request_text),
            "ts": time.time(),
            "continuity": "new_work",
        }

    def _ensure_tree_identity_meta(
        self,
        *,
        work_tree_module,
        tree_id: str,
        work_identity_key: str,
        identity_intent: str,
        source: str,
        user_id: str,
    ) -> None:
        tree = work_tree_module.get_tree(tree_id)
        if tree is None:
            return
        meta = dict(getattr(tree, "meta", {}) or {})
        changed = False
        if str(meta.get("work_identity_key") or "").strip() != str(work_identity_key or "").strip():
            meta["work_identity_key"] = str(work_identity_key or "").strip()
            changed = True
        if str(meta.get("work_identity_label") or "").strip() != self._work_identity_label(identity_intent):
            meta["work_identity_label"] = self._work_identity_label(identity_intent)
            changed = True
        if str(meta.get("work_identity_intent") or "").strip() != self._normalize_intake_text(identity_intent):
            meta["work_identity_intent"] = self._normalize_intake_text(identity_intent)
            changed = True
        if not str(meta.get("source") or "").strip() and source:
            meta["source"] = str(source or "")
            changed = True
        if user_id and str(meta.get("user_id") or "").strip() != str(user_id or "").strip():
            meta["user_id"] = str(user_id or "").strip()
            changed = True
        if changed:
            tree.meta = meta
            tree.updated_at = datetime.now()
            work_tree_module.save_tree(tree)

    def _append_continuation_if_needed(self, *, work_tree_module, tree_id: str, request_text: str) -> None:
        tree = work_tree_module.get_tree(tree_id)
        if tree is None:
            return
        root = work_tree_module.get_branch(tree.root_branch_id)
        if root is None:
            return
        continuation_seed = self._extract_creation_intent_seed(request_text)
        continuation_steps = self._split_steps(continuation_seed)
        if not continuation_steps:
            continuation_steps = [continuation_seed]

        if not continuation_steps or not str(continuation_steps[0] or "").strip():
            return

        step_text = str(continuation_steps[0] or "").strip()
        normalized_step = self._normalize_intake_text(step_text)
        if not normalized_step:
            return

        best_branch = None
        best_score = 0.0
        for branch_id in list(root.children or []):
            branch = work_tree_module.get_branch(branch_id)
            if branch is None:
                continue
            branch_score = self._title_similarity(branch.title, step_text)
            if branch_score > best_score:
                best_score = branch_score
                best_branch = branch
            branch_tasks = list(work_tree_module.list_branch_tasks(branch.branch_id) or [])
            for task in branch_tasks:
                if self._normalize_intake_text(getattr(task, "title", "")) == normalized_step:
                    return

        if best_branch is not None and best_score >= 0.70:
            branch_tasks = list(work_tree_module.list_branch_tasks(best_branch.branch_id) or [])
            for task in branch_tasks:
                if self._normalize_intake_text(getattr(task, "title", "")) == normalized_step:
                    return
            work_tree_module.add_task_to_branch(best_branch.branch_id, step_text)
            work_tree_module.assign_branch_tool_from_text(best_branch.branch_id, step_text)
            return

        child = work_tree_module.add_branch_to_tree(
            tree_id,
            self._step_branch_title(len(list(root.children or [])), step_text),
            "planned",
            root.branch_id,
        )
        work_tree_module.add_task_to_branch(child.branch_id, step_text)
        inferred = self._infer_tool(step_text)
        work_tree_module.set_branch_tools(
            child.branch_id,
            allowed_tools=self._allowed_tools(inferred),
            preferred_tool=inferred,
        )

    def _get_intent_overlap_strength(
        self,
        *,
        active_work_identity: str,
        new_work_identity: str,
    ) -> str:
        """Return 'strong', 'partial', or 'weak' based on term overlap.

        Phase 4: Judgment function for branching vs. continuation.
        """
        def _terms(identity_key: str) -> set[str]:
            raw = str(identity_key or "")
            if "|terms:" in raw:
                segment = raw.split("|terms:", 1)[1]
                return {token for token in segment.split("|") if token}
            return set()

        active_terms = _terms(active_work_identity)
        new_terms = _terms(new_work_identity)

        if not active_terms or not new_terms:
            return "weak"

        overlap = len(active_terms.intersection(new_terms))
        union_size = len(active_terms.union(new_terms))

        if not union_size:
            return "weak"

        overlap_ratio = float(overlap) / float(union_size)

        # Strong: >= 75% term overlap
        if overlap_ratio >= 0.75:
            return "strong"
        # Partial: >= 40% term overlap
        if overlap_ratio >= 0.40:
            return "partial"
        return "weak"

    def _should_branch_instead_of_continue(
        self,
        *,
        active_tree_id: str,
        message: str,
        active_work_identity: str,
        new_work_identity: str,
        work_tree_module,
    ) -> bool:
        """Detect if prompt should create new branch under same tree.

        Phase 4: If overlap is partial (not strong), and the new request
        introduces directional change (different keywords), branch instead of continue.
        """
        strength = self._get_intent_overlap_strength(
            active_work_identity=active_work_identity,
            new_work_identity=new_work_identity,
        )

        # Only branch if there's partial overlap (not strong, not weak)
        if strength != "partial":
            return False

        # Check if message has directional cues suggesting different work
        low = self._normalize_intake_text(message)
        direction_cues = {"fix", "refactor", "redesign", "optimize", "debug", "rewrite", "migrate", "switch"}
        has_direction_cue = any(cue in low.split() for cue in direction_cues)
        base_should_branch = bool(strength == "partial" and has_direction_cue)
        return self._apply_adaptive_bias_to_branch(
            work_identity_key=str(new_work_identity or active_work_identity or "").strip(),
            should_branch=base_should_branch,
            overlap_strength=strength,
        )

    def _tree_is_complete(self, *, work_tree_module, tree_id: str) -> bool:
        """Detect if tree is effectively complete.

        Complete when:
        - All branches are complete/archived, OR
        - No open tasks, OR
        - Tree explicitly marked complete
        """
        tree = work_tree_module.get_tree(tree_id)
        if tree is None:
            return False

        # Already marked complete
        status = self._tree_status_value(tree)
        if status == "complete":
            return True

        # Check all branches
        root = work_tree_module.get_branch(str(getattr(tree, "root_branch_id", "") or "").strip())
        branches = [work_tree_module.get_branch(bid) for bid in getattr(root, "children", []) or []]
        if not branches:
            return False

        all_branches_resolved = all(
            self._tree_status_value(b) in {"complete", "archived"}
            for b in branches
            if b is not None
        )
        if all_branches_resolved:
            return True

        # Check for open tasks
        all_tasks = list(work_tree_module.list_tree_tasks(tree_id) or [])
        open_tasks = [
            t for t in all_tasks
            if str(getattr(getattr(t, "status", ""), "value", t.status or "")).strip().lower() in {"open", "active"}
        ]

        return len(open_tasks) == 0

    def _detect_completion_signals(self, *, message: str) -> bool:
        """Detect explicit completion signals in message.

        Signals: done, finished, complete, wrap up, close, conclude, finish
        """
        low = self._normalize_intake_text(message)
        signals = {
            "done", "finished", "complete", "wrap up", "close", "conclude", "finish",
            "winding down", "final step", "last task", "all done"
        }
        for signal in signals:
            if signal in low:
                return True
        return False

    def _mark_tree_complete(
        self,
        *,
        work_tree_module,
        tree_id: str,
        reason: str = "completion_detected",
    ) -> None:
        """Mark tree as complete without deleting it.

        Phase 4: Prevents further tasks from being sent to completed trees.
        """
        tree = work_tree_module.get_tree(tree_id)
        if tree is None:
            return

        # Use TreeStatus enum for proper state transition
        try:
            from work_tree_contracts import TreeStatus
            tree.status = TreeStatus.COMPLETE
        except (ImportError, AttributeError):
            # Fallback: set status as string
            tree.status = "complete"  # type: ignore

        meta = dict(getattr(tree, "meta", {}) or {})
        meta["completion_reason"] = str(reason or "")
        tree.meta = meta
        tree.updated_at = datetime.now()
        work_tree_module.save_tree(tree)

    def should_prevent_over_continuation(
        self,
        *,
        active_work_identity: str,
        new_message: str,
        active_tree_id: str = "",
        work_tree_module=None,
    ) -> bool:
        """Over-continuation safeguard: prevent forcing divergent work.

        Returns True if the new message is sufficiently divergent that it
        should create a new tree instead of continuing the active identity.

        Phase 4: Allows natural divergence without requiring "new work" keyword.
        """
        if not active_work_identity or not active_tree_id or work_tree_module is None:
            return False

        new_identity = self.build_work_identity_key(new_message)
        if not new_identity:
            return False

        strength = self._get_intent_overlap_strength(
            active_work_identity=active_work_identity,
            new_work_identity=new_identity,
        )

        # Weak overlap = divergence; prevent automatic continuation
        return strength == "weak"

    def _apply_adaptive_bias_to_continue(
        self,
        *,
        work_identity_key: str,
        should_continue: bool,
        message: str,
        active_work_identity: str,
    ) -> bool:
        """Apply a lightweight continuation bias without overriding base logic."""
        key = str(work_identity_key or "").strip()
        if not key:
            return bool(should_continue)

        prob = WORK_TREE_DECISION_ADAPTER.apply_bias_to_probability(
            work_identity_key=key,
            decision_type="continue",
            base_probability=0.50,
        )
        new_identity = self.build_work_identity_key(message)
        strength = self._get_intent_overlap_strength(
            active_work_identity=active_work_identity,
            new_work_identity=new_identity,
        )

        if should_continue:
            if prob < 0.35 and strength != "strong":
                return False
            return True

        if (
            prob > 0.65
            and strength in {"strong", "partial"}
            and self._looks_like_followup_continuation(message)
        ):
            return True

        return False

    def _apply_adaptive_bias_to_branch(
        self,
        *,
        work_identity_key: str,
        should_branch: bool,
        overlap_strength: str,
    ) -> bool:
        """Apply a lightweight branch bias without overriding base logic."""
        key = str(work_identity_key or "").strip()
        if not key:
            return bool(should_branch)

        prob = WORK_TREE_DECISION_ADAPTER.apply_bias_to_probability(
            work_identity_key=key,
            decision_type="branch",
            base_probability=0.45 if overlap_strength == "partial" else 0.35,
        )

        if should_branch:
            if prob < 0.30:
                return False
            return True

        if overlap_strength == "partial" and prob > 0.70:
            return True

        return False

    @staticmethod
    def _root_branch_id_for_tree(*, work_tree_module, tree_id: str) -> str:
        tree = work_tree_module.get_tree(tree_id)
        if tree is None:
            return ""
        return str(getattr(tree, "root_branch_id", "") or "").strip()

    @staticmethod
    def _branch_count_for_tree(*, work_tree_module, tree_id: str) -> int:
        tree = work_tree_module.get_tree(tree_id)
        if tree is None:
            return 0
        root_id = str(getattr(tree, "root_branch_id", "") or "").strip()
        root = work_tree_module.get_branch(root_id)
        if root is None:
            return 0
        return len(list(getattr(root, "children", []) or []))

    def _flush_pending_successes(self, *, now_ts: float) -> None:
        stale: list[str] = []
        for key, pending in list(self._pending_decisions.items()):
            try:
                age = now_ts - float(pending.get("timestamp") or 0.0)
            except Exception:
                age = 0.0
            if age >= float(self._OUTCOME_WINDOW_SECONDS):
                decision_type = str(pending.get("decision_type") or "").strip()
                if decision_type:
                    WORK_TREE_DECISION_ADAPTER.record_outcome(
                        work_identity_key=key,
                        decision_type=decision_type,
                        outcome="success",
                    )
                stale.append(key)
        for key in stale:
            self._pending_decisions.pop(key, None)

    def _record_work_decision(
        self,
        *,
        work_identity_key: str,
        decision_type: str,
        tree_id: str,
        branch_id: str,
        branch_count: int,
        immediate_success: bool = False,
        failure_identity_key: str = "",
    ) -> None:
        key = str(work_identity_key or "").strip()
        decision = str(decision_type or "").strip()
        if not key or not decision:
            return

        now_ts = time.time()
        self._flush_pending_successes(now_ts=now_ts)

        previous = self._pending_decisions.get(key)
        cross_key = str(failure_identity_key or "").strip()
        if (not isinstance(previous, dict)) and cross_key and cross_key != key:
            previous = self._pending_decisions.get(cross_key)
            if isinstance(previous, dict):
                key_for_previous = cross_key
            else:
                key_for_previous = key
        else:
            key_for_previous = key

        if isinstance(previous, dict):
            prev_decision = str(previous.get("decision_type") or "").strip()
            try:
                elapsed = now_ts - float(previous.get("timestamp") or 0.0)
            except Exception:
                elapsed = 0.0

            is_failure = False
            if prev_decision == "continue":
                if decision == "new" and elapsed <= float(self._OUTCOME_WINDOW_SECONDS):
                    is_failure = True
                elif (
                    decision == "branch"
                    and elapsed <= float(self._OUTCOME_WINDOW_SECONDS)
                    and int(branch_count) >= int(self._BRANCH_EXPLOSION_THRESHOLD)
                ):
                    is_failure = True
            elif prev_decision == "complete":
                if decision in {"continue", "branch", "new"} and elapsed <= float(self._REOPEN_WINDOW_SECONDS):
                    is_failure = True

            if is_failure:
                WORK_TREE_DECISION_ADAPTER.record_outcome(
                    work_identity_key=key_for_previous,
                    decision_type=prev_decision,
                    outcome="failure",
                )
                self._pending_decisions.pop(key_for_previous, None)

        WORK_TREE_DECISION_ADAPTER.record_decision(
            decision_type=decision,
            work_identity_key=key,
            branch_id=branch_id,
            timestamp=now_ts,
        )

        if immediate_success:
            WORK_TREE_DECISION_ADAPTER.record_outcome(
                work_identity_key=key,
                decision_type=decision,
                outcome="success",
            )
            self._pending_decisions.pop(key, None)
            return

        self._pending_decisions[key] = {
            "decision_type": decision,
            "timestamp": now_ts,
            "tree_id": str(tree_id or "").strip(),
            "branch_id": str(branch_id or "").strip(),
        }

    def resolve_seeded_tree(
        self,
        *,
        work_tree_module,
        title_seed: str,
        source: str,
        user_id: str = "",
        nova_core_module=None,
        active_tree_id: str = "",
        active_work_identity: str = "",
    ) -> dict[str, str]:
        title_text = str(title_seed or "").strip() or "work tree task"
        intent_seed = self._extract_creation_intent_seed(title_text)
        work_identity_key = self.build_work_identity_key(intent_seed or title_text)

        # Phase 4: Check for completion signals and prevent continued tasking
        if active_tree_id:
            active_tree = work_tree_module.get_tree(active_tree_id)
            active_status = self._tree_status_value(active_tree) if active_tree else ""
            
            # If active tree is already complete, don't continue it
            if active_status == "complete":
                # Fall through to create new tree
                pass
            elif self._detect_completion_signals(message=title_text):
                # Mark tree complete and proceed to create new tree if intent diverges
                self._mark_tree_complete(work_tree_module=work_tree_module, tree_id=active_tree_id)
                completion_key = str(active_work_identity or work_identity_key or "").strip()
                if completion_key:
                    self._record_work_decision(
                        work_identity_key=completion_key,
                        decision_type="complete",
                        tree_id=str(active_tree_id),
                        branch_id=self._root_branch_id_for_tree(work_tree_module=work_tree_module, tree_id=active_tree_id),
                        branch_count=self._branch_count_for_tree(work_tree_module=work_tree_module, tree_id=active_tree_id),
                        immediate_success=True,
                    )
                pass
            else:
                should_continue = self.should_continue_active_identity(
                    message=title_text,
                    active_work_identity=active_work_identity,
                )
                if active_work_identity or work_identity_key:
                    should_continue = self._apply_adaptive_bias_to_continue(
                        work_identity_key=str(active_work_identity or work_identity_key or "").strip(),
                        should_continue=should_continue,
                        message=title_text,
                        active_work_identity=str(active_work_identity or work_identity_key or "").strip(),
                    )

                if should_continue:
                # Phase 4: Check if we should branch instead of continue
                    if self._should_branch_instead_of_continue(
                        active_tree_id=active_tree_id,
                        message=title_text,
                        active_work_identity=active_work_identity,
                        new_work_identity=work_identity_key,
                        work_tree_module=work_tree_module,
                    ):
                    # Create new branch under the same tree instead of continuing
                        if active_tree is not None:
                            root = work_tree_module.get_branch(active_tree.root_branch_id)
                            if root is not None:
                                intent_seed_for_branch = self._extract_creation_intent_seed(title_text)
                                child = work_tree_module.add_branch_to_tree(
                                    active_tree_id,
                                    self._step_branch_title(len(list(root.children or [])), intent_seed_for_branch or title_text),
                                    "planned",
                                    root.branch_id,
                                )
                                work_tree_module.add_task_to_branch(child.branch_id, title_text)
                                inferred = self._infer_tool(title_text)
                                work_tree_module.set_branch_tools(
                                    child.branch_id,
                                    allowed_tools=self._allowed_tools(inferred),
                                    preferred_tool=inferred,
                                )
                                selected_key = str(work_identity_key or active_work_identity or "").strip()
                                self._ensure_tree_identity_meta(
                                    work_tree_module=work_tree_module,
                                    tree_id=active_tree_id,
                                    work_identity_key=selected_key,
                                    identity_intent=intent_seed or title_text,
                                    source=source,
                                    user_id=user_id,
                                )
                                self._record_work_decision(
                                    work_identity_key=selected_key,
                                    decision_type="branch",
                                    tree_id=str(active_tree_id),
                                    branch_id=str(child.branch_id),
                                    branch_count=self._branch_count_for_tree(work_tree_module=work_tree_module, tree_id=active_tree_id),
                                )
                                self._mark_reuse(tree_id=active_tree_id, request_text=title_text)
                                return {
                                    "tree_id": str(active_tree_id),
                                    "work_identity_key": selected_key,
                                    "continuity": "branching_work",
                                    "branch_decision": "new_branch_under_same_tree",
                                    "decision_type": "branch",
                                    "branch_id": str(child.branch_id),
                                }
                    else:
                    # Continue with same identity (Phase 3 behavior)
                        if active_tree is not None:
                            selected_key = str(work_identity_key or active_work_identity or "").strip()
                            self._ensure_tree_identity_meta(
                                work_tree_module=work_tree_module,
                                tree_id=active_tree_id,
                                work_identity_key=selected_key,
                                identity_intent=intent_seed or title_text,
                                source=source,
                                user_id=user_id,
                            )
                            self._append_continuation_if_needed(work_tree_module=work_tree_module, tree_id=active_tree_id, request_text=title_text)
                            self._record_work_decision(
                                work_identity_key=selected_key,
                                decision_type="continue",
                                tree_id=str(active_tree_id),
                                branch_id=self._root_branch_id_for_tree(work_tree_module=work_tree_module, tree_id=active_tree_id),
                                branch_count=self._branch_count_for_tree(work_tree_module=work_tree_module, tree_id=active_tree_id),
                            )
                            self._mark_reuse(tree_id=active_tree_id, request_text=title_text)
                            return {
                                "tree_id": str(active_tree_id),
                                "work_identity_key": selected_key,
                                "continuity": "continuing_existing_work",
                                "decision_type": "continue",
                                "branch_id": self._root_branch_id_for_tree(work_tree_module=work_tree_module, tree_id=active_tree_id),
                            }
            # Phase 4: Check over-continuation safeguard
            if self.should_prevent_over_continuation(
                active_work_identity=active_work_identity,
                new_message=title_text,
                active_tree_id=active_tree_id,
                work_tree_module=work_tree_module,
            ):
                # Divergence detected; fall through to create new tree
                pass

        # Try to find existing tree by identity key (Phase 3)
        identity_tree_id = self._find_tree_by_identity_key(
            work_tree_module=work_tree_module,
            work_identity_key=work_identity_key,
            preferred_tree_id=active_tree_id,
        )
        if identity_tree_id and identity_tree_id != active_tree_id:
            tree = work_tree_module.get_tree(identity_tree_id)
            if tree is not None:
                status = self._tree_status_value(tree)
                if status != "complete":
                    self._ensure_tree_identity_meta(
                        work_tree_module=work_tree_module,
                        tree_id=identity_tree_id,
                        work_identity_key=work_identity_key,
                        identity_intent=intent_seed or title_text,
                        source=source,
                        user_id=user_id,
                    )
                    self._append_continuation_if_needed(work_tree_module=work_tree_module, tree_id=identity_tree_id, request_text=title_text)
                    self._record_work_decision(
                        work_identity_key=work_identity_key,
                        decision_type="continue",
                        tree_id=str(identity_tree_id),
                        branch_id=self._root_branch_id_for_tree(work_tree_module=work_tree_module, tree_id=identity_tree_id),
                        branch_count=self._branch_count_for_tree(work_tree_module=work_tree_module, tree_id=identity_tree_id),
                    )
                    self._mark_reuse(tree_id=identity_tree_id, request_text=title_text)
                    return {
                        "tree_id": identity_tree_id,
                        "work_identity_key": work_identity_key,
                        "continuity": "continuing_existing_work",
                        "decision_type": "continue",
                        "branch_id": self._root_branch_id_for_tree(work_tree_module=work_tree_module, tree_id=identity_tree_id),
                    }

        # Backward compatibility: explicit duplicate create prompts still check similarity (Phase 3)
        if self.looks_like_explicit_work_tree_request(title_text):
            similar_tree_id = self._find_similar_existing_tree_id(
                work_tree_module=work_tree_module,
                title_seed=intent_seed or title_text,
            )
            if similar_tree_id:
                tree = work_tree_module.get_tree(similar_tree_id)
                if tree is not None:
                    status = self._tree_status_value(tree)
                    if status != "complete":
                        self._ensure_tree_identity_meta(
                            work_tree_module=work_tree_module,
                            tree_id=similar_tree_id,
                            work_identity_key=work_identity_key,
                            identity_intent=intent_seed or title_text,
                            source=source,
                            user_id=user_id,
                        )
                        self._append_continuation_if_needed(work_tree_module=work_tree_module, tree_id=similar_tree_id, request_text=title_text)
                        self._record_work_decision(
                            work_identity_key=work_identity_key,
                            decision_type="continue",
                            tree_id=str(similar_tree_id),
                            branch_id=self._root_branch_id_for_tree(work_tree_module=work_tree_module, tree_id=similar_tree_id),
                            branch_count=self._branch_count_for_tree(work_tree_module=work_tree_module, tree_id=similar_tree_id),
                        )
                        self._mark_reuse(tree_id=similar_tree_id, request_text=title_text)
                        return {
                            "tree_id": similar_tree_id,
                            "work_identity_key": work_identity_key,
                            "continuity": "continuing_existing_work",
                            "decision_type": "continue",
                            "branch_id": self._root_branch_id_for_tree(work_tree_module=work_tree_module, tree_id=similar_tree_id),
                        }

        # Create new tree (Phase 3)
        title_base = intent_seed or title_text
        title = title_base if len(title_base) <= 80 else title_base[:77].rstrip() + "..."
        source_label = str(source or "chat").strip().capitalize() or "Chat"

        tree = work_tree_module.initialize_tree(
            f"{source_label}: {title}",
            {
                "source": str(source or "chat"),
                "user_id": str(user_id or ""),
                "kind": "system",
                "work_identity_key": work_identity_key,
                "work_identity_label": self._work_identity_label(intent_seed or title_text),
                "work_identity_intent": self._normalize_intake_text(intent_seed or title_text),
                "execution_policy": {
                    "allowed_tools": sorted(_SYSTEM_TOOL_NAMES),
                    "require_explicit_allow": True,
                },
            },
        )
        root_branch = work_tree_module.get_branch(tree.root_branch_id)
        if root_branch is None:
            self._mark_new(tree_id=tree.tree_id, request_text=title_text)
            self._record_work_decision(
                work_identity_key=work_identity_key,
                decision_type="new",
                tree_id=str(tree.tree_id),
                branch_id="",
                branch_count=0,
                failure_identity_key=str(active_work_identity or "").strip(),
            )
            return {
                "tree_id": tree.tree_id,
                "work_identity_key": work_identity_key,
                "continuity": "new_work",
                "decision_type": "new",
                "branch_id": "",
            }

        llm_steps = self._llm_decompose(title_text, nova_core_module=nova_core_module)

        previous_branch_id: str | None = None
        if llm_steps:
            for index, item in enumerate(llm_steps):
                step_text = item["title"]
                child = work_tree_module.add_branch_to_tree(
                    tree.tree_id,
                    self._step_branch_title(index, step_text),
                    "planned",
                    root_branch.branch_id,
                )
                work_tree_module.add_task_to_branch(child.branch_id, step_text)
                llm_tool = str(item.get("tool") or "").strip().lower()
                tool = llm_tool if llm_tool in _SYSTEM_TOOL_NAMES else self._infer_tool(step_text)
                work_tree_module.set_branch_tools(
                    child.branch_id,
                    allowed_tools=self._allowed_tools(tool),
                    preferred_tool=tool,
                )
                if previous_branch_id:
                    work_tree_module.add_dependency(child.branch_id, previous_branch_id)
                previous_branch_id = child.branch_id
        else:
            steps = self._split_steps(title_text)
            if not steps:
                steps = [title_text]

            for index, step_text in enumerate(steps):
                child = work_tree_module.add_branch_to_tree(
                    tree.tree_id,
                    self._step_branch_title(index, step_text),
                    "planned",
                    root_branch.branch_id,
                )
                work_tree_module.add_task_to_branch(child.branch_id, step_text)
                preferred = self._infer_tool(step_text)
                work_tree_module.set_branch_tools(
                    child.branch_id,
                    allowed_tools=self._allowed_tools(preferred),
                    preferred_tool=preferred,
                )
                if previous_branch_id:
                    work_tree_module.add_dependency(child.branch_id, previous_branch_id)
                previous_branch_id = child.branch_id

        self._mark_new(tree_id=tree.tree_id, request_text=title_text)
        self._record_work_decision(
            work_identity_key=work_identity_key,
            decision_type="new",
            tree_id=str(tree.tree_id),
            branch_id=str(root_branch.branch_id),
            branch_count=self._branch_count_for_tree(work_tree_module=work_tree_module, tree_id=tree.tree_id),
            failure_identity_key=str(active_work_identity or "").strip(),
        )
        return {
            "tree_id": tree.tree_id,
            "work_identity_key": work_identity_key,
            "continuity": "new_work",
            "decision_type": "new",
            "branch_id": str(root_branch.branch_id),
        }

    def consume_reuse_note(self, *, tree_id: str, request_text: str, max_age_seconds: int = 120) -> str:
        payload = dict(self._last_reuse or {})
        self._last_reuse = {}
        if not payload:
            return ""
        if str(payload.get("tree_id") or "").strip() != str(tree_id or "").strip():
            return ""
        request_norm = self._normalize_intake_text(request_text)
        if str(payload.get("request_text") or "").strip() != request_norm:
            return ""
        try:
            age = time.time() - float(payload.get("ts") or 0.0)
        except Exception:
            return ""
        if age > float(max(1, int(max_age_seconds))):
            return ""
        continuity = str(payload.get("continuity") or "").strip().lower()
        if continuity == "new_work":
            return f"Started new work: {tree_id}"
        return f"Continuing existing work: {tree_id}"

    @staticmethod
    def _llm_decompose(task_text: str, *, nova_core_module=None) -> Optional[list[dict]]:
        """Ask Ollama to decompose *task_text* into step dicts {title, tool}.

        Returns a list of 2-4 dicts on success, or None so callers fall back to
        the rule-based splitter.
        """
        if _requests is None:
            return None
        try:
            model: str = "llama3"
            if nova_core_module is not None:
                try:
                    model = nova_core_module.chat_model()
                except Exception:
                    pass

            payload = {
                "model": model,
                "stream": False,
                "options": {"temperature": 0.05, "top_p": 0.9},
                "messages": [
                    {"role": "system", "content": _DECOMPOSE_SYSTEM},
                    {"role": "user", "content": f'Task: "{task_text[:400]}"'},
                ],
            }
            r = _requests.post(
                f"{_OLLAMA_BASE}/api/chat",
                json=payload,
                timeout=12.0,
            )
            r.raise_for_status()
            raw = r.json().get("message", {}).get("content", "").strip()
            # Strip any accidental markdown fences
            raw = re.sub(r"^```[a-z]*\s*", "", raw).rstrip("`").strip()
            steps = json.loads(raw)
            if not isinstance(steps, list):
                return None
            validated: list[dict] = []
            for item in steps:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                # Reject non-system tools silently — the seeding layer will
                # infer the correct system tool from the step text instead.
                raw_tool = str(item.get("tool") or "").strip().lower()
                tool = raw_tool if raw_tool in _SYSTEM_TOOL_NAMES else ""
                if not title:
                    continue
                if len(title) > 80:
                    title = title[:77].rstrip() + "..."
                validated.append({"title": title, "tool": tool})
            if len(validated) < 2:
                return None
            return validated[:4]
        except Exception:
            return None

    @staticmethod
    def looks_like_explicit_work_tree_request(message: str) -> bool:
        low = str(message or "").strip().lower()
        return any(phrase in low for phrase in _EXPLICIT_WORK_TREE_PHRASES)

    @staticmethod
    def _looks_like_content_oriented_prompt(message: str) -> bool:
        low = str(message or "").strip().lower()
        if not low:
            return False
        return any(cue in low for cue in _CONTENT_ORIENTED_CUES)

    @staticmethod
    def _looks_like_system_nervous_system_prompt(message: str) -> bool:
        low = str(message or "").strip().lower()
        if not low:
            return False
        return any(cue in low for cue in _SYSTEM_NERVOUS_SYSTEM_CUES)

    @staticmethod
    def should_seed_system_work_tree(*, message: str, source: str = "", operator_mode: str = "") -> bool:
        """Shared activation rule for auto-seeding system work trees.

        Rules:
        1) explicit work-tree request always seeds
        2) clear content prompts do not seed
        3) internal maintenance cues seed
        4) operator macro flows default to seed unless content-oriented
        5) CLI source alone is only transport; it must still show work intent
        """
        if WorkTreeSeedingService.looks_like_explicit_work_tree_request(message):
            return True
        if WorkTreeSeedingService._looks_like_content_oriented_prompt(message):
            return False
        if WorkTreeSeedingService._looks_like_system_nervous_system_prompt(message):
            return True
        normalized_mode = str(operator_mode or "").strip().lower()
        if normalized_mode == "macro":
            return True
        return False

    @staticmethod
    def _split_steps(message: str, *, limit: int = 4) -> list[str]:
        text = str(message or "").strip()
        if not text:
            return []
        normalized = re.sub(r"\s+", " ", text)
        parts = [
            re.sub(r"^[\-\*\d\.\)\s]+", "", item).strip(" .;:-")
            for item in re.split(r"(?:\n+|;|\s+and\s+then\s+|\s+then\s+|\s*->\s*)", normalized, flags=re.I)
        ]
        parts = [item for item in parts if len(item) >= 3]
        if not parts:
            return []
        deduped: list[str] = []
        seen: set[str] = set()
        for item in parts:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= max(1, int(limit)):
                break
        return deduped

    @staticmethod
    def _infer_tool(step_text: str) -> str:
        low = str(step_text or "").strip().lower()
        if not low:
            return "health"
        if any(token in low for token in ("pulse", "beat", "heartbeat")):
            return "pulse"
        if "preview" in low and any(token in low for token in ("apply", "approved", "eligible")):
            return "patch_preview_apply"
        if any(token in low for token in ("patch", "apply patch", "rollback")):
            return "patch_apply"
        if any(token in low for token in ("update", "install update")):
            return "update_now"
        if any(token in low for token in ("queue", "backlog", "pending", "generated", "work queue")):
            return "queue_status"
        if any(token in low for token in ("list files", "directory", "folder", "list dir", "ls ")):
            return "ls"
        if any(token in low for token in ("read", "inspect file", "open file", "scan", "log", "snapshot", "report")):
            return "read"
        if any(token in low for token in ("phase2", "audit", "safety envelope")):
            return "phase2_audit"
        if any(token in low for token in ("system", "runtime", "status", "check", "verify", "validate", "diagnose")):
            return "system_check"
        return "health"

    @staticmethod
    def _allowed_tools(preferred_tool: str) -> list[str]:
        tool = str(preferred_tool or "").strip().lower()
        if tool in {"read", "ls", "find"}:
            return ["read", "ls", "find"]
        if tool in {"pulse"}:
            return ["pulse", "health", "system_check"]
        if tool in {"queue_status"}:
            return ["queue_status", "system_check", "health"]
        if tool in {"patch_preview_apply", "patch_apply", "patch_rollback"}:
            return ["patch_preview_apply", "patch_apply", "patch_rollback"]
        if tool in {"update_now"}:
            return ["update_now", "patch_preview_apply", "patch_apply"]
        if tool in {"phase2_audit"}:
            return ["phase2_audit", "system_check"]
        # Default: general system health tools
        return ["health", "system_check", "pulse", "queue_status"]

    @staticmethod
    def _step_branch_title(index: int, step_text: str) -> str:
        compact = re.sub(r"\s+", " ", str(step_text or "").strip())
        if len(compact) > 58:
            compact = compact[:55].rstrip() + "..."
        return f"Step {index + 1}: {compact}" if compact else f"Step {index + 1}"

    def create_seeded_tree(
        self,
        *,
        work_tree_module,
        title_seed: str,
        source: str,
        user_id: str = "",
        nova_core_module=None,
        active_tree_id: str = "",
        active_work_identity: str = "",
    ) -> str:
        resolved = self.resolve_seeded_tree(
            work_tree_module=work_tree_module,
            title_seed=title_seed,
            source=source,
            user_id=user_id,
            nova_core_module=nova_core_module,
            active_tree_id=active_tree_id,
            active_work_identity=active_work_identity,
        )
        return str(resolved.get("tree_id") or "").strip()


WORK_TREE_SEEDING_SERVICE = WorkTreeSeedingService()
