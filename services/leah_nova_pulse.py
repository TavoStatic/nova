from __future__ import annotations

"""Public Leah ↔ Nova pulse. Cheap local facts — no control-auth, no full status build."""

import json
import time
from pathlib import Path
from typing import Any

from services.nova_runtime_context import RUNTIME_DIR


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _heartbeat_age_sec(heartbeat_path: Path) -> float | None:
    if not heartbeat_path.is_file():
        return None
    try:
        return max(0.0, time.time() - float(heartbeat_path.stat().st_mtime))
    except Exception:
        return None


def _guard_running(runtime_dir: Path) -> bool:
    payload = _read_json(runtime_dir / "guard_pid.json")
    pid = int(payload.get("pid") or 0)
    if pid <= 0:
        return False
    try:
        import psutil

        return bool(psutil.pid_exists(pid))
    except Exception:
        return False


def _work_tree_status(runtime_dir: Path) -> str:
    db = runtime_dir / "_internal" / "work_tree.db"
    if not db.is_file():
        return "idle"
    try:
        import sqlite3

        con = sqlite3.connect(str(db))
        try:
            row = con.execute(
                """
                SELECT COUNT(*) FROM work_tree_branches
                WHERE lower(status) IN ('ready','open','active','in_progress','doing')
                """
            ).fetchone()
        finally:
            con.close()
        return "active" if int((row or [0])[0] or 0) > 0 else "idle"
    except Exception:
        return "unknown"


def build_leah_nova_pulse(
    *,
    runtime_dir: Path | None = None,
    ollama_up: bool = False,
    chat_model: str = "",
    memory_enabled: bool = False,
    chat_login_enabled: bool = False,
    searx_ok: bool | None = None,
    searx_note: str = "",
    outbox: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(runtime_dir or RUNTIME_DIR)
    hb_age = _heartbeat_age_sec(root / "core.heartbeat")
    core_state = _read_json(root / "core_state.json")
    core_running = bool(core_state.get("pid")) and hb_age is not None and hb_age <= 15.0
    guard_running = _guard_running(root)
    autonomy = _read_json(root / "autonomy_maintenance_state.json")
    queue_run = autonomy.get("last_generated_queue_run")
    if not isinstance(queue_run, dict):
        queue_run = {}
    patch = autonomy.get("last_patch_cleanup")
    if not isinstance(patch, dict):
        patch = {}

    if guard_running and core_running:
        maintenance_status = "guard_scheduled"
    elif core_running:
        maintenance_status = "running"
    else:
        maintenance_status = "inactive"

    health_score = 100 if (core_running and ollama_up) else (70 if core_running else 0)

    pulse = {
        "ok": True,
        "surface": "leah_nova_pulse",
        "ollama_api_up": bool(ollama_up),
        "chat_model": str(chat_model or ""),
        "memory_enabled": bool(memory_enabled),
        "chat_login_enabled": bool(chat_login_enabled),
        "core_running": core_running,
        "heartbeat_age_sec": None if hb_age is None else round(float(hb_age), 1),
        "health_score": health_score,
        "queue_actionable_count": int(queue_run.get("queue_actionable_count") or 0),
        "queue_open_count": int(queue_run.get("queue_open_count") or 0),
        "patch_review_previews_total": int(patch.get("review_total_before") or 0),
        "searxng_ok": True if searx_ok is None else bool(searx_ok),
        "searxng_note": str(searx_note or ""),
        "work_tree_status": _work_tree_status(root),
        "maintenance_scheduler_status": maintenance_status,
        "guard_running": guard_running,
    }
    pulse["nova_outreach"] = compose_nova_outreach(pulse, outbox=outbox)
    return pulse


def compose_nova_outreach(
    pulse: dict[str, Any] | None = None,
    *,
    outbox: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Speak only from real runtime pressure. Idle presence is the open door, not a line."""
    data = dict(pulse or {})
    box = dict(outbox or {})
    latest = box.get("operator_actionable_latest_open") or box.get("latest_open") or {}
    if not isinstance(latest, dict):
        latest = {}
    notice = str(latest.get("message") or latest.get("title") or "").strip()
    notice_id = str(latest.get("id") or "").strip()
    if notice:
        return {"id": notice_id or "outbox", "kind": "attention", "text": notice}
    return {"id": "silent", "kind": "silent", "text": ""}


def statement_from_nova_life(pulse: dict[str, Any] | None = None) -> str:
    """One true sentence when the person gives Nova the floor. Not a ticket question."""
    data = dict(pulse or {})
    if not data:
        data = build_leah_nova_pulse()
    box = data.get("nova_outreach") if isinstance(data.get("nova_outreach"), dict) else {}
    notice = str(box.get("text") or "").strip()
    if notice and str(box.get("kind") or "") == "attention":
        return notice
    queue_n = int(data.get("queue_actionable_count") or 0)
    work = str(data.get("work_tree_status") or "").strip().lower()
    if queue_n > 0:
        noun = "item" if queue_n == 1 else "items"
        return f"I'm already carrying {queue_n} background {noun}. I don't need a topic from you to stay in this."
    if work and work not in {"idle", "complete", "unknown", ""}:
        return "I'm already in work on this machine. You don't have to hand me a task."
    if data.get("core_running"):
        return "I'm here. I don't need a question to keep this channel open."
    return "I'm here."
