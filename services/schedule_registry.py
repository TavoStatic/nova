"""Central registry of all scheduled background tasks in Nova.

Each task is declared once here — name, owner, cadence, and description.
Execution logic stays in the authoritative owner module; this registry is the
single source of truth for *what* Nova runs on a timer and *how often*.

The control panel will eventually read ``SCHEDULE_REGISTRY.scheduled_tasks``
to display and control every scheduled job from one surface instead of hunting
across modules.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Cadence constants — canonical interval values.  If you change an interval
# in the owning module, update the constant here too.
# ---------------------------------------------------------------------------

# nova_core.py  → start_heartbeat(interval_sec=1.0)
HEARTBEAT_INTERVAL_SEC: int = 1

# nova_guard.py → POLL_SECONDS = 2
GUARD_POLL_INTERVAL_SEC: int = 2

# nova_guard.py → MAINTENANCE_INTERVAL_SECONDS = 3600
MAINTENANCE_LAUNCH_INTERVAL_SEC: int = 3600

# autonomy_maintenance.py → run_worker(interval_sec=300)
MAINTENANCE_CYCLE_INTERVAL_SEC: int = 300


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScheduledTask:
    """Metadata descriptor for one scheduled background task."""

    name: str
    """Stable machine identifier (snake_case)."""

    label: str
    """Human-readable display name for the control panel."""

    owner: str
    """Module or file that owns the execution logic."""

    trigger: str
    """
    How the task is triggered:
      daemon_thread        — Runs in a daemon thread; fires on its own interval.
      daemon_loop          — Tight loop in a long-lived process.
      interval             — Launched by the guard on a fixed interval (subprocess).
      per_maintenance_cycle — Runs once per autonomy_maintenance run_once() call.
      daily                — Runs at most once per calendar day.
    """

    interval_sec: int
    """Nominal seconds between executions (0 if not applicable)."""

    description: str
    """One-line summary shown in the control panel."""

    state_key: str = field(default="")
    """Key in autonomy_maintenance_state.json that holds last-run data, if any."""


# ---------------------------------------------------------------------------
# Registry — one entry per scheduled job across all of Nova
# ---------------------------------------------------------------------------

SCHEDULED_TASKS: list[ScheduledTask] = [
    ScheduledTask(
        name="core_heartbeat",
        label="Core Heartbeat",
        owner="nova_core.py",
        trigger="daemon_thread",
        interval_sec=HEARTBEAT_INTERVAL_SEC,
        description="Writes runtime/core.heartbeat every second so the guard can verify the core process is live.",
        state_key="",
    ),
    ScheduledTask(
        name="guard_poll",
        label="Guard Health Poll",
        owner="nova_guard.py",
        trigger="daemon_loop",
        interval_sec=GUARD_POLL_INTERVAL_SEC,
        description="Guard watches core process health; restarts on crash and enforces single-process ownership.",
        state_key="",
    ),
    ScheduledTask(
        name="maintenance_launcher",
        label="Autonomy Maintenance Launcher",
        owner="nova_guard.py",
        trigger="interval",
        interval_sec=MAINTENANCE_LAUNCH_INTERVAL_SEC,
        description="Guard launches autonomy_maintenance.py as a subprocess once per hour to run all maintenance cycles.",
        state_key="runtime_worker",
    ),
    ScheduledTask(
        name="subconscious_pack",
        label="Subconscious Training Pack",
        owner="autonomy_maintenance.py",
        trigger="per_maintenance_cycle",
        interval_sec=MAINTENANCE_CYCLE_INTERVAL_SEC,
        description="Runs subconscious_runner.py to advance training signal packs and evaluate fallback overuse pressure.",
        state_key="last_generated_at",
    ),
    ScheduledTask(
        name="generated_queue",
        label="Generated Test Queue",
        owner="autonomy_maintenance.py",
        trigger="per_maintenance_cycle",
        interval_sec=MAINTENANCE_CYCLE_INTERVAL_SEC,
        description="Advances the generated test-session definition queue by one actionable item per cycle.",
        state_key="last_generated_queue_run",
    ),
    ScheduledTask(
        name="kidney_cleanup",
        label="Kidney Cleanup",
        owner="autonomy_maintenance.py",
        trigger="per_maintenance_cycle",
        interval_sec=MAINTENANCE_CYCLE_INTERVAL_SEC,
        description="Archives and removes stale runtime artifacts according to the kidney retention policy.",
        state_key="last_kidney_status",
    ),
    ScheduledTask(
        name="work_tree_cycle",
        label="Work Tree Maintenance Cycle",
        owner="autonomy_maintenance.py",
        trigger="per_maintenance_cycle",
        interval_sec=MAINTENANCE_CYCLE_INTERVAL_SEC,
        description="Advances active system work trees up to 3 steps per cycle; seeds a new tree if none are active.",
        state_key="last_work_tree_cycle",
    ),
    ScheduledTask(
        name="daily_regression",
        label="Daily Regression Suite",
        owner="autonomy_maintenance.py",
        trigger="daily",
        interval_sec=86400,
        description="Runs the full test suite once per calendar day and records pass/fail status.",
        state_key="last_regression_date",
    ),
]

# Stable lookup by name
_TASKS_BY_NAME: dict[str, ScheduledTask] = {t.name: t for t in SCHEDULED_TASKS}


def get_task(name: str) -> ScheduledTask | None:
    """Return the task descriptor for *name*, or None if not registered."""
    return _TASKS_BY_NAME.get(name)


# ---------------------------------------------------------------------------
# Live-state merge  (used by control_status.py for the control panel)
# ---------------------------------------------------------------------------

def get_schedule_status(maintenance_state: dict | None = None) -> list[dict]:
    """Return a JSON-serialisable list merging static task metadata with live
    last-run data sourced from *maintenance_state* (the dict loaded from
    ``runtime/autonomy_maintenance_state.json``).

    Each entry in the returned list is safe to pass directly to the control
    panel renderer as-is.
    """
    ms = maintenance_state if isinstance(maintenance_state, dict) else {}
    result: list[dict] = []

    for task in SCHEDULED_TASKS:
        entry: dict = {
            "name": task.name,
            "label": task.label,
            "owner": task.owner,
            "trigger": task.trigger,
            "interval_sec": task.interval_sec,
            "description": task.description,
            "last_run_at": "",
            "last_run_status": "",
        }

        sk = task.state_key
        if not sk:
            result.append(entry)
            continue

        raw = ms.get(sk)

        if task.name == "maintenance_launcher":
            worker = raw if isinstance(raw, dict) else {}
            entry["last_run_at"] = str(worker.get("last_completed_at") or "")
            entry["last_run_status"] = str(worker.get("last_cycle_status") or "")

        elif task.name == "subconscious_pack":
            entry["last_run_at"] = str(ms.get("last_generated_at") or "")
            entry["last_run_status"] = "ok" if ms.get("last_generated_at") else ""

        elif task.name == "generated_queue":
            qr = raw if isinstance(raw, dict) else {}
            entry["last_run_at"] = str(qr.get("ts") or "")
            entry["last_run_status"] = str(qr.get("status") or "")

        elif task.name == "kidney_cleanup":
            ks = raw if isinstance(raw, dict) else {}
            entry["last_run_at"] = str(ks.get("ts") or "")
            entry["last_run_status"] = "ok" if ks.get("ts") else ""

        elif task.name == "work_tree_cycle":
            wt = raw if isinstance(raw, dict) else {}
            entry["last_run_at"] = str(wt.get("ts") or "")
            entry["last_run_status"] = str(wt.get("status") or "")

        elif task.name == "daily_regression":
            entry["last_run_at"] = str(raw or "")
            entry["last_run_status"] = str(ms.get("last_regression_status") or "")

        result.append(entry)

    return result


SCHEDULE_REGISTRY = type("ScheduleRegistry", (), {
    "scheduled_tasks": SCHEDULED_TASKS,
    "get_task": staticmethod(get_task),
    "get_schedule_status": staticmethod(get_schedule_status),
})()
