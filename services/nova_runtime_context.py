from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Optional


_ACTIVE_USER_LOCAL = threading.local()


def set_active_user(name: Optional[str]):
    if not name:
        _ACTIVE_USER_LOCAL.value = None
    else:
        _ACTIVE_USER_LOCAL.value = str(name).strip()


def get_active_user() -> Optional[str]:
    value = getattr(_ACTIVE_USER_LOCAL, "value", None)
    return str(value).strip() if value else None


def resolve_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resolve_python_executable(base_dir: Path) -> str:
    candidates = [
        base_dir / ".venv" / "Scripts" / "python.exe",
        base_dir / ".venv" / "bin" / "python",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return str(Path(sys.executable).resolve())


BASE_DIR = resolve_base_dir()
RUNTIME_DIR = BASE_DIR / "runtime"
LOG_DIR = BASE_DIR / "logs"
MEMORY_DIR = BASE_DIR / "memory"
ACTION_LEDGER_DIR = RUNTIME_DIR / "actions"
MEMORY_EVENTS_LOG = RUNTIME_DIR / "memory_events.jsonl"
HEALTH_LOG = RUNTIME_DIR / "health.log"
IDENTITY_FILE = MEMORY_DIR / "identity.json"
LEARNED_FACTS_FILE = MEMORY_DIR / "learned_facts.json"
BEHAVIOR_METRICS_FILE = RUNTIME_DIR / "behavior_metrics.json"
SELF_REFLECTION_LOG = RUNTIME_DIR / "self_reflection.jsonl"
AUTONOMY_MAINTENANCE_FILE = RUNTIME_DIR / "autonomy_maintenance_state.json"
PULSE_SNAPSHOT_FILE = RUNTIME_DIR / "pulse_snapshot.json"
UPDATE_NOW_PENDING_FILE = RUNTIME_DIR / "update_now_pending.json"
DEVICE_LOCATION_FILE = RUNTIME_DIR / "device_location.json"
TEST_SESSIONS_DIR = RUNTIME_DIR / "test_sessions"
GENERATED_DEFINITIONS_DIR = TEST_SESSIONS_DIR / "generated_definitions"
PENDING_REVIEW_DIR = TEST_SESSIONS_DIR / "pending_review"
QUARANTINE_DIR = TEST_SESSIONS_DIR / "quarantine"
PROMOTION_AUDIT_LOG = TEST_SESSIONS_DIR / "promotion_audit.jsonl"
PROMOTED_DEFINITIONS_DIR = TEST_SESSIONS_DIR / "promoted"
POLICY_PATH = BASE_DIR / "policy.json"
PYTHON = resolve_python_executable(BASE_DIR)
