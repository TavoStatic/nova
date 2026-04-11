from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Optional


def mem_stats_payload(
    *,
    emit_event: bool = True,
    mem_enabled_fn: Callable[[], bool],
    memory_mod: Any,
    memory_runtime_user_fn: Callable[[], Optional[str]],
    mem_scope_fn: Callable[[], str],
    record_memory_event_fn: Callable[..., None],
) -> dict:
    if not mem_enabled_fn() or memory_mod is None:
        return {"ok": False, "error": "memory_disabled"}
    started = time.time()
    try:
        user = memory_runtime_user_fn()
        data = memory_mod.stats(scope=mem_scope_fn(), user=user)
        if isinstance(data, dict):
            out = dict(data)
            out["ok"] = True
            if emit_event:
                record_memory_event_fn(
                    "stats",
                    "ok",
                    user=user,
                    scope=mem_scope_fn(),
                    backend="in_process",
                    result_count=int(out.get("total", 0) or 0),
                    duration_ms=int((time.time() - started) * 1000),
                )
            return out
        if emit_event:
            record_memory_event_fn(
                "stats",
                "error",
                user=user,
                scope=mem_scope_fn(),
                backend="in_process",
                error="invalid_memory_stats",
                duration_ms=int((time.time() - started) * 1000),
            )
        return {"ok": False, "error": "invalid_memory_stats"}
    except Exception as e:
        if emit_event:
            record_memory_event_fn(
                "stats",
                "error",
                user=memory_runtime_user_fn(),
                scope=mem_scope_fn(),
                backend="in_process",
                error=str(e),
                duration_ms=int((time.time() - started) * 1000),
            )
        return {"ok": False, "error": str(e)}


def mem_add(
    kind: str,
    source: str,
    text: str,
    *,
    mem_enabled_fn: Callable[[], bool],
    identity_memory_text_allowed_fn: Callable[[str, str], bool],
    record_memory_event_fn: Callable[..., None],
    mem_scope_fn: Callable[[], str],
    memory_should_keep_text_fn: Callable[[str], tuple[bool, str]],
    memory_write_user_fn: Callable[[], Optional[str]],
    memory_mod: Any,
    mem_min_score_fn: Callable[[], float],
    python_path: str,
    base_dir: Path,
) -> None:
    if not mem_enabled_fn():
        return
    started = time.time()
    try:
        if not identity_memory_text_allowed_fn(kind, text):
            record_memory_event_fn(
                "add",
                "skipped",
                scope=mem_scope_fn(),
                kind=kind,
                source=source,
                reason="identity_only_mode",
                duration_ms=int((time.time() - started) * 1000),
            )
            return
        if source and str(source).lower() in {"assistant", "nova"}:
            record_memory_event_fn(
                "add",
                "skipped",
                scope=mem_scope_fn(),
                kind=kind,
                source=source,
                reason="assistant_source",
                duration_ms=int((time.time() - started) * 1000),
            )
            return

        bypass_filter = str(kind or "").strip().lower() == "test" or str(source or "").strip().lower() in {"test", "unittest"}
        keep, reason = memory_should_keep_text_fn(text)
        if bypass_filter:
            keep, reason = True, "test_bypass"
        if not keep:
            record_memory_event_fn(
                "add",
                "skipped",
                scope=mem_scope_fn(),
                kind=kind,
                source=source,
                reason=reason or "filtered_text",
                duration_ms=int((time.time() - started) * 1000),
            )
            return

        user = memory_write_user_fn()
        if user is None:
            record_memory_event_fn(
                "add",
                "skipped",
                scope=mem_scope_fn(),
                kind=kind,
                source=source,
                reason="missing_user",
                duration_ms=int((time.time() - started) * 1000),
            )
            return

        if memory_mod is not None:
            try:
                explain = memory_mod.recall_explain(
                    text,
                    top_k=1,
                    min_score=mem_min_score_fn(),
                    user=user,
                    scope=mem_scope_fn(),
                )
                results = (explain or {}).get("results") or []
                if results:
                    top = results[0]
                    score = float(top.get("score") or 0.0)
                    preview = (top.get("preview") or "").strip()

                    def _normalize_duplicate_text(value: str) -> str:
                        return re.sub(r"\W+", " ", (value or "").lower()).strip()

                    if score >= 0.85 or _normalize_duplicate_text(preview) == _normalize_duplicate_text(text):
                        record_memory_event_fn(
                            "add",
                            "skipped",
                            user=user,
                            scope=mem_scope_fn(),
                            backend="in_process",
                            kind=kind,
                            source=source,
                            reason="duplicate",
                            result_count=len(results),
                            duration_ms=int((time.time() - started) * 1000),
                        )
                        return
                memory_mod.add_memory(kind, source, text, user=user or "", scope=mem_scope_fn())
                record_memory_event_fn(
                    "add",
                    "ok",
                    user=user,
                    scope=mem_scope_fn(),
                    backend="in_process",
                    kind=kind,
                    source=source,
                    duration_ms=int((time.time() - started) * 1000),
                )
                return
            except Exception:
                pass

        cmd = [python_path, str(base_dir / "memory.py"), "add", "--kind", kind, "--source", source, "--text", text]
        cmd += ["--scope", mem_scope_fn()]
        if user:
            cmd += ["--user", str(user)]
        subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        record_memory_event_fn(
            "add",
            "ok",
            user=user,
            scope=mem_scope_fn(),
            backend="subprocess",
            kind=kind,
            source=source,
            duration_ms=int((time.time() - started) * 1000),
        )
    except Exception:
        record_memory_event_fn(
            "add",
            "error",
            user=memory_write_user_fn(),
            scope=mem_scope_fn(),
            kind=kind,
            source=source,
            error="mem_add_failed",
            duration_ms=int((time.time() - started) * 1000),
        )


def mem_recall(
    query: str,
    *,
    mem_enabled_fn: Callable[[], bool],
    memory_recall_plan_fn: Callable[..., Any] | None = None,
    memory_runtime_user_fn: Callable[[], Optional[str]],
    memory_mod: Any,
    mem_context_top_k_fn: Callable[[], int],
    mem_min_score_fn: Callable[[], float],
    mem_exclude_sources_fn: Callable[[], list[str]],
    mem_scope_fn: Callable[[], str],
    format_memory_recall_hits_fn: Callable[[Any], str],
    record_memory_event_fn: Callable[..., None],
    python_path: str,
    base_dir: Path,
    purpose: str = "general",
    conversation_state: Optional[dict] = None,
    pending_action: Optional[dict] = None,
) -> str:
    if not mem_enabled_fn():
        return ""
    if len((query or "").strip()) < 8:
        return ""

    plan = None
    if callable(memory_recall_plan_fn):
        try:
            plan = memory_recall_plan_fn(
                query,
                purpose=purpose,
                conversation_state=conversation_state,
                pending_action=pending_action,
            )
        except TypeError:
            plan = memory_recall_plan_fn(query)

    if plan is not None and not bool(getattr(plan, "allow", False)):
        record_memory_event_fn(
            "recall",
            "skipped",
            user=memory_runtime_user_fn(),
            scope=mem_scope_fn(),
            query=query,
            lane=str(getattr(plan, "lane", "") or ""),
            reason=str(getattr(plan, "reason", "blocked") or "blocked"),
            mode=str(getattr(plan, "purpose", purpose) or purpose),
        )
        return ""

    started = time.time()
    try:
        user = memory_runtime_user_fn()
        if memory_mod is not None:
            hits = memory_mod.recall(
                query,
                top_k=mem_context_top_k_fn(),
                min_score=mem_min_score_fn(),
                exclude_sources=mem_exclude_sources_fn(),
                user=user,
                scope=mem_scope_fn(),
            )
            out = format_memory_recall_hits_fn(hits)
            record_memory_event_fn(
                "recall",
                "ok",
                user=user,
                scope=mem_scope_fn(),
                backend="in_process",
                query=query,
                lane=str(getattr(plan, "lane", "") or ""),
                result_count=len(hits or []),
                reason=str(getattr(plan, "reason", "") or ""),
                duration_ms=int((time.time() - started) * 1000),
                mode=str(getattr(plan, "purpose", purpose) or purpose),
            )
            return out

        cmd = [
            python_path,
            str(base_dir / "memory.py"),
            "recall",
            "--query",
            query,
            "--topk",
            str(mem_context_top_k_fn()),
            "--minscore",
            str(mem_min_score_fn()),
            "--scope",
            mem_scope_fn(),
        ]
        if user:
            cmd += ["--user", str(user)]
        for source in mem_exclude_sources_fn():
            cmd += ["--exclude-source", source]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        out = (result.stdout or "").strip()
        if not out or "No memories" in out:
            record_memory_event_fn(
                "recall",
                "ok",
                user=user,
                scope=mem_scope_fn(),
                backend="subprocess",
                query=query,
                lane=str(getattr(plan, "lane", "") or ""),
                result_count=0,
                reason=str(getattr(plan, "reason", "") or ""),
                duration_ms=int((time.time() - started) * 1000),
                mode=str(getattr(plan, "purpose", purpose) or purpose),
            )
            return ""
        parts = re.split(r"\n--- score=.*?---\n", "\n" + out + "\n")
        parsed = [(0.0, 0, "", "", "", part.strip()) for part in parts if (part or "").strip()]
        rendered = format_memory_recall_hits_fn(parsed)
        record_memory_event_fn(
            "recall",
            "ok",
            user=user,
            scope=mem_scope_fn(),
            backend="subprocess",
            query=query,
            lane=str(getattr(plan, "lane", "") or ""),
            result_count=len(parsed),
            reason=str(getattr(plan, "reason", "") or ""),
            duration_ms=int((time.time() - started) * 1000),
            mode=str(getattr(plan, "purpose", purpose) or purpose),
        )
        return rendered
    except Exception:
        record_memory_event_fn(
            "recall",
            "error",
            user=memory_runtime_user_fn(),
            scope=mem_scope_fn(),
            query=query,
            error="mem_recall_failed",
            duration_ms=int((time.time() - started) * 1000),
        )
        return ""


def prefix_from_earlier_memory(reply_text: str) -> str:
    reply = str(reply_text or "").strip()
    if not reply:
        return reply
    if reply.lower().startswith("from earlier memory:"):
        return reply
    return f"From earlier memory: {reply}"


def normalize_recent_learning_item(kind: str, text: str) -> str:
    raw_kind = str(kind or "").strip().lower()
    raw_text = str(text or "").strip()
    if not raw_text:
        return ""

    if raw_kind == "user_correction":
        try:
            payload = json.loads(raw_text)
        except Exception:
            payload = {}
        parsed = str(payload.get("parsed_correction") or "").strip()
        correction_text = str(payload.get("text") or raw_text).strip()
        value = parsed or correction_text
        return f"Correction: {value}" if value else ""

    clean = raw_text
    if raw_kind == "identity" and clean.lower().startswith("learned_fact:"):
        clean = clean.split(":", 1)[1].strip()
    if raw_kind in {"user_fact", "fact", "identity", "profile"}:
        return clean
    return ""


def mem_get_recent_learned(
    limit: int = 5,
    *,
    mem_enabled_fn: Callable[[], bool],
    memory_mod: Any,
    memory_runtime_user_fn: Callable[[], Optional[str]],
    mem_scope_fn: Callable[[], str],
    normalize_recent_learning_item_fn: Callable[[str, str], str],
    load_learned_facts_fn: Callable[[], dict],
    memory_read_plan_fn: Callable[..., Any] | None = None,
    record_memory_event_fn: Callable[..., None] | None = None,
) -> list[str]:
    requested = max(1, int(limit or 5))
    items: list[str] = []
    seen: set[str] = set()
    plan = None
    query = "what have you learned from me"

    if callable(memory_read_plan_fn):
        try:
            plan = memory_read_plan_fn(query, purpose="recent_learning_summary")
        except TypeError:
            plan = memory_read_plan_fn(query)

    if plan is not None and not bool(getattr(plan, "allow", False)):
        if callable(record_memory_event_fn):
            record_memory_event_fn(
                "recent_learned",
                "skipped",
                user=memory_runtime_user_fn(),
                scope=mem_scope_fn(),
                query=query,
                lane=str(getattr(plan, "lane", "") or ""),
                reason=str(getattr(plan, "reason", "blocked") or "blocked"),
                mode=str(getattr(plan, "purpose", "recent_learning_summary") or "recent_learning_summary"),
            )
        return []

    if mem_enabled_fn() and memory_mod is not None:
        connection = None
        try:
            connection = memory_mod.connect()
            rows = memory_mod.select_memory_rows(connection, memory_runtime_user_fn(), mem_scope_fn())
            for _ts, kind, source, _user_row, text, _vec in rows:
                source_name = str(source or "").strip().lower()
                kind_name = str(kind or "").strip().lower()
                if source_name in {"assistant", "nova", "pinned"}:
                    continue
                if kind_name not in {"user_correction", "user_fact", "fact", "identity", "profile"}:
                    continue
                item = normalize_recent_learning_item_fn(kind_name, text)
                if not item:
                    continue
                dedupe_key = re.sub(r"\s+", " ", item).strip().lower()
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                items.append(item)
                if len(items) >= requested:
                    if callable(record_memory_event_fn):
                        record_memory_event_fn(
                            "recent_learned",
                            "ok",
                            user=memory_runtime_user_fn(),
                            scope=mem_scope_fn(),
                            query=query,
                            lane=str(getattr(plan, "lane", "durable_user") or "durable_user"),
                            reason=str(getattr(plan, "reason", "") or ""),
                            result_count=len(items),
                            mode=str(getattr(plan, "purpose", "recent_learning_summary") or "recent_learning_summary"),
                        )
                    return items
        except Exception:
            pass
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    learned = load_learned_facts_fn()
    fallback_pairs = [
        ("assistant_name", "Assistant name"),
        ("developer_name", "Developer name"),
        ("developer_nickname", "Developer nickname"),
    ]
    for key, label in fallback_pairs:
        value = str(learned.get(key) or "").strip()
        if not value:
            continue
        item = f"{label}: {value}"
        dedupe_key = item.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(item)
        if len(items) >= requested:
            break
    if callable(record_memory_event_fn):
        lane = str(getattr(plan, "lane", "") or "")
        record_memory_event_fn(
            "recent_learned",
            "ok",
            user=memory_runtime_user_fn(),
            scope=mem_scope_fn(),
            query=query,
            lane=lane or ("identity" if items else "durable_user"),
            reason=str(getattr(plan, "reason", "") or ""),
            result_count=len(items),
            mode=str(getattr(plan, "purpose", "recent_learning_summary") or "recent_learning_summary"),
        )
    return items[:requested]


def mem_stats(*, mem_stats_payload_fn: Callable[..., dict], memory_mod: Any, python_path: str, base_dir: Path) -> str:
    try:
        payload = mem_stats_payload_fn()
        if payload.get("ok"):
            return json.dumps(payload, indent=2)
        if memory_mod is not None:
            return "No memory stats available."
        result = subprocess.run(
            [python_path, str(base_dir / "memory.py"), "stats"],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        out = (result.stdout or "").strip()
        return out or "No memory stats available."
    except Exception as e:
        return f"Memory stats failed: {e}"


def mem_audit(
    query: str,
    *,
    memory_runtime_user_fn: Callable[[], Optional[str]],
    memory_mod: Any,
    mem_context_top_k_fn: Callable[[], int],
    mem_min_score_fn: Callable[[], float],
    mem_exclude_sources_fn: Callable[[], list[str]],
    mem_scope_fn: Callable[[], str],
    record_memory_event_fn: Callable[..., None],
    python_path: str,
    base_dir: Path,
) -> str:
    q = (query or "").strip()
    if not q:
        return "Usage: mem audit <query>"
    started = time.time()
    try:
        user = memory_runtime_user_fn()
        if memory_mod is not None:
            out = memory_mod.recall_explain(
                q,
                top_k=mem_context_top_k_fn(),
                min_score=mem_min_score_fn(),
                exclude_sources=mem_exclude_sources_fn(),
                user=user,
                scope=mem_scope_fn(),
            )
            result_count = len((out or {}).get("results") or []) if isinstance(out, dict) else 0
            record_memory_event_fn(
                "audit",
                "ok",
                user=user,
                scope=mem_scope_fn(),
                backend="in_process",
                query=q,
                result_count=result_count,
                mode=str((out or {}).get("mode") or "") if isinstance(out, dict) else "",
                duration_ms=int((time.time() - started) * 1000),
            )
            return json.dumps(out, indent=2)

        cmd = [
            python_path,
            str(base_dir / "memory.py"),
            "audit",
            "--query",
            q,
            "--topk",
            str(mem_context_top_k_fn()),
            "--minscore",
            str(mem_min_score_fn()),
            "--scope",
            mem_scope_fn(),
        ]
        if user:
            cmd += ["--user", str(user)]
        for source in mem_exclude_sources_fn():
            cmd += ["--exclude-source", source]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        out = (result.stdout or "").strip()
        record_memory_event_fn(
            "audit",
            "ok",
            user=user,
            scope=mem_scope_fn(),
            backend="subprocess",
            query=q,
            duration_ms=int((time.time() - started) * 1000),
        )
        return out or "No memory audit output."
    except Exception as e:
        record_memory_event_fn(
            "audit",
            "error",
            user=memory_runtime_user_fn(),
            scope=mem_scope_fn(),
            query=q,
            error=str(e),
            duration_ms=int((time.time() - started) * 1000),
        )
        return f"Memory audit failed: {e}"


def mem_remember_fact(text: str, *, mem_enabled_fn: Callable[[], bool], mem_add_fn: Callable[[str, str, str], None]) -> str:
    fact = (text or "").strip().strip("\"'")
    if not fact:
        return "Usage: remember: <fact>"
    if not mem_enabled_fn():
        return "Memory is disabled in policy."
    if len(fact) < 3:
        return "Fact is too short to store."

    mem_add_fn("fact", "pinned", fact)
    return f"Pinned memory saved: {fact}"


def load_identity_profile(identity_file: Path) -> dict:
    try:
        if not identity_file.exists():
            return {}
        data = json.loads(identity_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_identity_profile(data: dict, *, memory_dir: Path, identity_file: Path) -> None:
    try:
        memory_dir.mkdir(parents=True, exist_ok=True)
        tmp = identity_file.with_suffix(".json.tmp")
        payload = json.dumps(data, ensure_ascii=True, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(identity_file)
    except Exception:
        pass


def looks_invalid_person_token(value: str) -> bool:
    low = str(value or "").strip().lower()
    if not low:
        return True
    invalid = {
        "your",
        "yours",
        "you",
        "me",
        "my",
        "i",
        "nova",
        "nova's",
        "creator",
        "developer",
        "the same person",
        "same person",
    }
    return low in invalid


def sanitize_learned_facts(data: dict) -> dict:
    facts = dict(data or {})
    developer_name = str(facts.get("developer_name") or "").strip()
    developer_nickname = str(facts.get("developer_nickname") or "").strip()

    if developer_name and looks_invalid_person_token(developer_name):
        facts.pop("developer_name", None)

    if developer_nickname and looks_invalid_person_token(developer_nickname):
        facts.pop("developer_nickname", None)

    return facts


def load_learned_facts(*, learned_facts_file: Path, save_learned_facts_fn: Callable[[dict], None]) -> dict:
    try:
        if not learned_facts_file.exists():
            return {}
        data = json.loads(learned_facts_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        sanitized = sanitize_learned_facts(data)
        if sanitized != data:
            save_learned_facts_fn(sanitized)
        return sanitized
    except Exception:
        return {}


def save_learned_facts(data: dict, *, memory_dir: Path, learned_facts_file: Path) -> None:
    try:
        memory_dir.mkdir(parents=True, exist_ok=True)
        tmp = learned_facts_file.with_suffix(".json.tmp")
        payload = json.dumps(sanitize_learned_facts(data), ensure_ascii=True, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(learned_facts_file)
    except Exception:
        pass


def clean_fact_value(raw: str, max_words: int = 4) -> str:
    text = re.sub(r"\s+", " ", (raw or "").strip()).strip(" .,:;!?\"'")
    if not text:
        return ""
    words = text.split()
    text = " ".join(words[:max_words])
    return text[:80]


def title_name(value: str) -> str:
    out = clean_fact_value(value)
    if not out:
        return ""
    return " ".join(word[:1].upper() + word[1:] for word in out.split())


def learn_from_user_correction(
    text: str,
    *,
    load_learned_facts_fn: Callable[[], dict],
    get_learned_fact_fn: Callable[[str, str], str],
    save_learned_facts_fn: Callable[[dict], None],
    set_active_user_fn: Callable[[str], None],
    mem_enabled_fn: Callable[[], bool],
    mem_add_fn: Callable[[str, str, str], None],
) -> tuple[bool, str]:
    low = (text or "").strip().lower()
    if not low:
        return False, ""
    normalized_low = re.sub(r"\byes\s+iam\b", "yes i am", low)
    normalized_low = re.sub(r"\biam\b", "i am", normalized_low)
    low = normalized_low

    facts = load_learned_facts_fn()
    changed: list[str] = []

    assistant_match = re.search(r"\b(?:your name is|you are called|you're called)\s+([a-z][a-z '\-]{1,40})", low)
    if assistant_match:
        assistant_name = title_name(assistant_match.group(1))
        if assistant_name and facts.get("assistant_name") != assistant_name:
            facts["assistant_name"] = assistant_name
            changed.append(f"assistant_name={assistant_name}")

    if not assistant_match and "your name" in low:
        assistant_quoted = re.search(r"\bmy name is\s+([a-z][a-z '\-]{1,40})", low)
        if assistant_quoted:
            assistant_name = title_name(assistant_quoted.group(1))
            if assistant_name and facts.get("assistant_name") != assistant_name:
                facts["assistant_name"] = assistant_name
                changed.append(f"assistant_name={assistant_name}")

    developer_match = re.search(
        r"\b(?:developer(?:'s)? name is|develper(?:'s)? name is|his full name is|developer(?:'s)? full name is|develper(?:'s)? full name is|creator(?:'s)? full name is)\s+([a-z][a-z '\-]{1,60}(?:\s+(?:jr|sr|ii|iii|iv))?)",
        low,
    )
    if developer_match:
        developer_name = title_name(developer_match.group(1))
        if developer_name and facts.get("developer_name") != developer_name:
            facts["developer_name"] = developer_name
            changed.append(f"developer_name={developer_name}")

    nickname_match = re.search(r"\b(?:nick\s*name is|nickname is)\s+([a-z][a-z '\-]{1,40})", low)
    if nickname_match:
        nickname = title_name(nickname_match.group(1))
        if nickname and facts.get("developer_nickname") != nickname:
            facts["developer_nickname"] = nickname
            changed.append(f"developer_nickname={nickname}")

    creator_match = re.search(
        r"\bi am\s+([a-z][a-z '\-]{1,60}?)(?=\s+(?:the\s+)?(?:creator|developer)\b)(?:\s*,)?\s+(?:the\s+)?(?:creator|developer)(?:\s+and\s+(?:creator|developer))?(?:\s+of\s+nova)?\b",
        low,
    )
    self_creator_bound = False
    if creator_match:
        person_name = title_name(creator_match.group(1))
        low_person_name = (person_name or "").strip().lower()
        invalid_markers = {
            "your",
            "yours",
            "nova's",
            "nova",
            "the same person",
            "same person",
        }
        if low_person_name in invalid_markers or low_person_name.startswith("the same person"):
            person_name = ""
        if person_name:
            name_parts = person_name.split()
            if len(name_parts) >= 2:
                if facts.get("developer_name") != person_name:
                    facts["developer_name"] = person_name
                    changed.append(f"developer_name={person_name}")
                nickname = facts.get("developer_nickname") or name_parts[0]
                nickname = title_name(str(nickname))
                if nickname and facts.get("developer_nickname") != nickname:
                    facts["developer_nickname"] = nickname
                    changed.append(f"developer_nickname={nickname}")
                set_active_user_fn(person_name)
                self_creator_bound = True
            else:
                if facts.get("developer_nickname") != person_name:
                    facts["developer_nickname"] = person_name
                    changed.append(f"developer_nickname={person_name}")
                set_active_user_fn(person_name)
                self_creator_bound = True

    if not self_creator_bound:
        implied_creator = bool(re.search(r"\bi am\s+(?:your|nova'?s)\s+(?:creator|developer)\b", low))
        same_person_creator = "same person" in low and any(token in low for token in ["developer", "creator"])
        if implied_creator or same_person_creator:
            developer_name = str(facts.get("developer_name") or get_learned_fact_fn("developer_name", "Gustavo Uribe")).strip()
            developer_nickname = str(facts.get("developer_nickname") or get_learned_fact_fn("developer_nickname", "Gus")).strip()
            bind_name = developer_name or developer_nickname
            if bind_name:
                set_active_user_fn(bind_name)
                if developer_nickname and developer_name and facts.get("developer_nickname") != developer_nickname:
                    facts["developer_nickname"] = developer_nickname
                if developer_name and facts.get("developer_name") != developer_name:
                    facts["developer_name"] = developer_name
                if "identity_binding=developer" not in changed:
                    changed.append("identity_binding=developer")

    if not changed:
        return False, ""

    facts["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_learned_facts_fn(facts)

    try:
        if mem_enabled_fn():
            for item in changed:
                mem_add_fn("identity", "typed", f"learned_fact: {item}")
    except Exception:
        pass

    return True, "Understood. I learned: " + ", ".join(changed) + "."


def get_learned_fact(key: str, default: str = "", *, load_learned_facts_fn: Callable[[], dict]) -> str:
    data = load_learned_facts_fn()
    value = str(data.get(key) or "").strip()
    return value or default


def speaker_matches_developer(
    *,
    get_active_user_fn: Callable[[], Optional[str]],
    get_learned_fact_fn: Callable[[str, str], str],
) -> bool:
    active_user = (get_active_user_fn() or "").strip().lower()
    if not active_user:
        return False
    developer_name = get_learned_fact_fn("developer_name", "Gustavo Uribe").strip().lower()
    developer_nickname = get_learned_fact_fn("developer_nickname", "Gus").strip().lower()
    developer_first = developer_name.split()[0] if developer_name else ""
    return active_user in {developer_name, developer_nickname, developer_first}


def learn_self_identity_binding(
    text: str,
    *,
    set_active_user_fn: Callable[[str], None],
    get_learned_fact_fn: Callable[[str, str], str],
) -> tuple[bool, str]:
    raw = (text or "").strip()
    low = raw.lower()
    if not raw:
        return False, ""

    match = re.match(r"^i\s+am\s+([a-z][a-z '\-]{1,40})[.!?]*$", low)
    if not match:
        return False, ""

    person_name = title_name(match.group(1))
    if not person_name or looks_invalid_person_token(person_name):
        return False, ""

    developer_name = get_learned_fact_fn("developer_name", "Gustavo Uribe")
    developer_nickname = get_learned_fact_fn("developer_nickname", "Gus")
    developer_first = developer_name.split()[0] if developer_name else ""

    if person_name.lower() in {developer_nickname.lower(), developer_first.lower()}:
        set_active_user_fn(developer_name or person_name)
        return True, "Understood. Identity confirmed: you are my developer."

    if person_name.lower() == developer_name.lower():
        set_active_user_fn(person_name)
        return True, "Understood. Identity confirmed: you are my developer."

    return False, ""


def learn_contextual_self_facts(
    text: str,
    *,
    input_source: str = "typed",
    speaker_matches_developer_fn: Callable[[], bool],
    extract_color_preferences_from_text_fn: Callable[[str], list[str]],
    mem_enabled_fn: Callable[[], bool],
    mem_add_fn: Callable[[str, str, str], None],
) -> tuple[bool, str]:
    raw = (text or "").strip()
    if not raw:
        return False, ""

    learned: list[str] = []
    if speaker_matches_developer_fn():
        color_match = re.search(r"\bmy\s+fav(?:ou?rite|ortie)\s+colors?\s+are\s+(.+)$", raw, flags=re.I)
        if color_match and mem_enabled_fn():
            colors = extract_color_preferences_from_text_fn(color_match.group(1))
            if colors:
                pretty = ", ".join(colors[:-1]) + (f", and {colors[-1]}" if len(colors) > 1 else colors[0])
                mem_add_fn("identity", input_source, f"Gus favorite colors are {pretty}.")
                learned.append(f"Gus favorite colors are {pretty}")

    if not learned:
        return False, ""
    return True, "Understood. I learned: " + "; ".join(learned) + "."


def remember_name_origin(
    story_text: str,
    *,
    load_identity_profile_fn: Callable[[], dict],
    save_identity_profile_fn: Callable[[dict], None],
    mem_enabled_fn: Callable[[], bool],
    mem_add_fn: Callable[[str, str, str], None],
) -> str:
    story = re.sub(r"\s+", " ", (story_text or "").strip())
    if len(story) < 30:
        return "Please provide a longer origin story so I can store it accurately."

    profile = load_identity_profile_fn()
    profile["name_origin"] = story
    profile["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_identity_profile_fn(profile)

    if mem_enabled_fn():
        try:
            mem_add_fn("identity", "typed", f"nova_name_origin: {story[:1400]}")
        except Exception:
            pass

    return "Stored. I will remember this as the story behind my name."


def get_name_origin_story(
    *,
    load_identity_profile_fn: Callable[[], dict],
    mem_recall_fn: Callable[[str], str],
) -> str:
    profile = load_identity_profile_fn()
    story = str(profile.get("name_origin") or "").strip()
    if story:
        return story

    try:
        recall = mem_recall_fn("nova name origin story creator gus")
        if recall:
            for raw in str(recall).splitlines():
                item = (raw or "").strip().lstrip("-*\u2022").strip()
                if not item:
                    continue
                low = item.lower()
                if "nova_name_origin:" in low:
                    out = item.split(":", 1)[1].strip() if ":" in item else ""
                    if out and "my name is gus" not in out.lower() and "name: gus" not in out.lower():
                        return out[:2000]
    except Exception:
        pass
    return ""


def identity_context_for_prompt(*, load_identity_profile_fn: Callable[[], dict], load_learned_facts_fn: Callable[[], dict]) -> str:
    profile = load_identity_profile_fn()
    learned = load_learned_facts_fn()
    lines = []
    story = str(profile.get("name_origin") or "").strip()
    if story:
        lines.append("Identity fact: The assistant's name origin story is user-defined.")
        lines.append(f"Name origin story: {story[:1400]}")
    assistant_name = str(learned.get("assistant_name") or "").strip()
    developer_name = str(learned.get("developer_name") or "").strip()
    developer_nickname = str(learned.get("developer_nickname") or "").strip()
    if assistant_name:
        lines.append(f"Identity fact: assistant_name={assistant_name}")
    if developer_name:
        lines.append(f"Identity fact: developer_name={developer_name}")
    if developer_nickname:
        lines.append(f"Identity fact: developer_nickname={developer_nickname}")
    if not lines:
        return ""
    return "\n".join(lines)


def extract_name_origin_teach_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    low = raw.lower()

    if "remember this" in low and any(
        cue in low
        for cue in (
            "nova",
            "name",
            "story behind your name",
            "story behing your name",
            "gus gave you your name",
            "gus named you",
        )
    ):
        idx = low.find("remember this")
        candidate = raw[idx:]
        candidate = re.sub(r"(?is)^\s*remember\s+this\s*[:.\-]*\s*", "", candidate).strip()
        return candidate

    cues = [
        "symbol of new light",
        "new beginnings",
        "story behind your name",
        "nova was given",
        "in astronomy, a nova occurs",
    ]
    if any(cue in low for cue in cues) and len(raw) >= 120:
        return raw

    return ""


def build_learning_context_details(
    query: str,
    *,
    kb_search_fn: Callable[[str], str],
    mem_recall_fn: Callable[[str], str],
) -> dict:
    blocks = []
    kb_block = kb_search_fn(query)
    mem_block = mem_recall_fn(query)

    if kb_block:
        blocks.append(kb_block)
    if mem_block:
        blocks.append(mem_block)

    if not blocks:
        return {
            "context": "",
            "knowledge_used": False,
            "memory_used": False,
            "knowledge_chars": 0,
            "memory_chars": 0,
        }

    context = "\n\n".join(blocks)[:4000]
    return {
        "context": context,
        "knowledge_used": bool(kb_block),
        "memory_used": bool(mem_block),
        "knowledge_chars": len(kb_block or ""),
        "memory_chars": len(mem_block or ""),
    }


def build_learning_context(
    query: str,
    *,
    build_learning_context_details_fn: Callable[[str], dict],
) -> str:
    return str(build_learning_context_details_fn(query).get("context") or "")