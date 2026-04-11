from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Tuple


SessionTurns = Dict[str, List[Tuple[str, str]]]
SessionOwners = Dict[str, str]


def load_persisted_sessions(
    *,
    store_path: Path,
    session_turns: SessionTurns,
    session_owners: SessionOwners,
    max_stored_turns_per_session: int,
) -> None:
    try:
        if not store_path.exists():
            return
        data = json.loads(store_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        loaded: SessionTurns = {}
        session_owners.clear()
        for sid, turns in data.items():
            if not isinstance(sid, str):
                continue
            owner = ""
            turn_list = turns
            if isinstance(turns, dict):
                owner = str(turns.get("owner") or "").strip()
                turn_list = turns.get("turns")
            if not isinstance(turn_list, list):
                continue
            cleaned: List[Tuple[str, str]] = []
            for it in turn_list[-max_stored_turns_per_session:]:
                if not isinstance(it, dict):
                    continue
                role = str(it.get("role") or "").strip().lower()
                text = str(it.get("text") or "").strip()
                if role not in {"user", "assistant"} or not text:
                    continue
                cleaned.append((role, text))
            if cleaned:
                loaded[sid] = cleaned
                if owner:
                    session_owners[sid] = owner
        session_turns.clear()
        session_turns.update(loaded)
    except Exception:
        pass


def persist_sessions(
    *,
    runtime_dir: Path,
    store_path: Path,
    session_turns: SessionTurns,
    session_owners: SessionOwners,
    max_stored_sessions: int,
    max_stored_turns_per_session: int,
) -> None:
    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        items = list(session_turns.items())
        if len(items) > max_stored_sessions:
            items = items[-max_stored_sessions:]

        payload = {}
        for sid, turns in items:
            safe_turns = []
            for role, text in turns[-max_stored_turns_per_session:]:
                safe_turns.append({"role": role, "text": text})
            payload[sid] = {
                "owner": str(session_owners.get(sid) or ""),
                "turns": safe_turns,
            }

        tmp = store_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        tmp.replace(store_path)
    except Exception:
        pass


def trim_turns(turns: List[Tuple[str, str]], *, max_turns: int) -> None:
    cap = max_turns * 2
    if len(turns) > cap:
        del turns[: len(turns) - cap]


def append_session_turn(
    session_id: str,
    role: str,
    text: str,
    *,
    session_turns: SessionTurns,
    max_turns: int,
    persist_callback: Callable[[], None],
) -> List[Tuple[str, str]]:
    turns = session_turns.setdefault(session_id, [])
    turns.append((role, text))
    trim_turns(turns, max_turns=max_turns)
    persist_callback()
    return turns


def get_session_turns(session_id: str, *, session_turns: SessionTurns) -> List[Tuple[str, str]]:
    return list(session_turns.get(session_id, []))


def get_last_session_turn(session_id: str, *, session_turns: SessionTurns) -> tuple[str, str] | None:
    turns = session_turns.get(session_id, [])
    if not turns:
        return None
    return turns[-1]


def session_summaries(
    *,
    session_turns: SessionTurns,
    session_owners: SessionOwners,
    state_manager,
    limit: int = 60,
) -> List[dict]:
    items = list(session_turns.items())[-max(1, int(limit)):]
    out = []
    for sid, turns in reversed(items):
        if not sid:
            continue
        session = state_manager.peek(sid)
        last_user = ""
        last_assistant = ""
        for role, text in reversed(turns):
            if not last_user and role == "user":
                last_user = (text or "").strip()[:180]
            if not last_assistant and role == "assistant":
                last_assistant = (text or "").strip()[:180]
            if last_user and last_assistant:
                break
        out.append(
            {
                "session_id": sid,
                "owner": str(session_owners.get(sid) or ""),
                "turn_count": len(turns),
                "last_user": last_user,
                "last_assistant": last_assistant,
                "state": {
                    "active_subject": session.active_subject() if session is not None else "",
                    "state_kind": session.state_kind() if session is not None else "",
                    "pending_action": dict(session.pending_action) if session is not None and isinstance(session.pending_action, dict) else None,
                    "pending_correction_target": str(session.pending_correction_target or "") if session is not None else "",
                    "continuation_used": bool(session.continuation_used_last_turn) if session is not None else False,
                },
                "reflection": session.reflection_summary() if session is not None else {
                    "active_subject": "",
                    "continuation_used": False,
                    "overrides_active": [],
                },
            }
        )
    return out


def delete_session(
    session_id: str,
    *,
    session_turns: SessionTurns,
    session_owners: SessionOwners,
    state_manager,
    persist_callback: Callable[[], None],
    on_session_end: Callable[[str, object], None] | None = None,
) -> tuple[bool, str]:
    sid = (session_id or "").strip()
    if not sid:
        return False, "session_id_required"
    existed = sid in session_turns
    session = state_manager.peek(sid)
    if session is not None and callable(on_session_end):
        on_session_end(sid, session)
    session_turns.pop(sid, None)
    session_owners.pop(sid, None)
    state_manager.drop(sid)
    persist_callback()
    return True, "session_deleted" if existed else "session_not_found"


def assert_session_owner(
    session_id: str,
    user_id: str,
    *,
    session_owners: SessionOwners,
    normalize_user_id: Callable[[str], str],
    persist_callback: Callable[[], None],
    allow_bind: bool = True,
) -> tuple[bool, str]:
    sid = (session_id or "").strip()
    uid = normalize_user_id(user_id)
    if not sid:
        return False, "session_id_required"
    if not uid:
        return False, "user_id_required"
    owner = normalize_user_id(session_owners.get(sid) or "")
    if not owner:
        if allow_bind:
            session_owners[sid] = uid
            persist_callback()
            return True, "owner_bound"
        return False, "session_owner_missing"
    if owner != uid:
        return False, "session_owner_mismatch"
    return True, "ok"
