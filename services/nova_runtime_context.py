from __future__ import annotations

import os
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


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _path_from_env(value: str, *, base_dir: Path) -> Path:
    path = Path(str(value or "").strip()).expanduser()
    return path if path.is_absolute() else Path(base_dir) / path


def _looks_like_test_process(argv=None) -> bool:
    text = " ".join(str(arg or "") for arg in list(sys.argv if argv is None else argv))
    lowered = text.lower()
    return "unittest" in lowered or "pytest" in lowered


def runtime_scope_name(environ=None, argv=None) -> str:
    env = os.environ if environ is None else environ
    return "validation" if _truthy(env.get("NOVA_TEST_RUNNER")) or _looks_like_test_process(argv) else "live"


def resolve_runtime_dir(base_dir: Path | None = None, environ=None, argv=None) -> Path:
    """Return the runtime root for the current execution scope.

    Live Nova keeps using ``runtime``. Regression and validation runs get a
    separate runtime root before test modules import live path constants.
    """
    env = os.environ if environ is None else environ
    base = Path(base_dir) if base_dir is not None else resolve_base_dir()
    runtime_override = str(env.get("NOVA_RUNTIME_DIR") or "").strip()
    validation_override = str(env.get("NOVA_VALIDATION_RUNTIME_DIR") or "").strip()

    if runtime_scope_name(env, argv) == "validation":
        if validation_override:
            return _path_from_env(validation_override, base_dir=base)
        if runtime_override:
            return _path_from_env(runtime_override, base_dir=base)
        return base / "runtime" / "validation"

    if runtime_override:
        return _path_from_env(runtime_override, base_dir=base)
    return base / "runtime"


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
RUNTIME_SCOPE = runtime_scope_name()
RUNTIME_DIR = resolve_runtime_dir(BASE_DIR)
LOG_DIR = (
    _path_from_env(os.environ["NOVA_LOG_DIR"], base_dir=BASE_DIR)
    if str(os.environ.get("NOVA_LOG_DIR") or "").strip()
    else (RUNTIME_DIR / "logs" if RUNTIME_SCOPE == "validation" else BASE_DIR / "logs")
)
MEMORY_DIR = (
    _path_from_env(os.environ["NOVA_MEMORY_DIR"], base_dir=BASE_DIR)
    if str(os.environ.get("NOVA_MEMORY_DIR") or "").strip()
    else (RUNTIME_DIR / "memory" if RUNTIME_SCOPE == "validation" else BASE_DIR / "memory")
)
ACTION_LEDGER_DIR = RUNTIME_DIR / "actions"
MEMORY_EVENTS_LOG = RUNTIME_DIR / "memory_events.jsonl"
HEALTH_LOG = RUNTIME_DIR / "health.log"
IDENTITY_FILE = MEMORY_DIR / "identity.json"
LEARNED_FACTS_FILE = MEMORY_DIR / "learned_facts.json"
MEMORY_BOOTSTRAP_ORIGIN_FILE = MEMORY_DIR / "bootstrap_origin.json"
BEHAVIOR_METRICS_FILE = RUNTIME_DIR / "behavior_metrics.json"
SELF_REFLECTION_LOG = RUNTIME_DIR / "self_reflection.jsonl"
AUTONOMY_MAINTENANCE_FILE = RUNTIME_DIR / "autonomy_maintenance_state.json"
AUTONOMY_ORCHESTRATOR_LEDGER_FILE = RUNTIME_DIR / "autonomy_orchestrator_ledger.jsonl"
OPERATOR_OUTBOX_FILE = RUNTIME_DIR / "operator_outbox.jsonl"
OS_CAPABILITY_SCRIPTS_DIR = BASE_DIR / "tools" / "os_capabilities"
OS_CAPABILITY_REGISTRY_FILE = OS_CAPABILITY_SCRIPTS_DIR / "os_capabilities.json"
OS_CAPABILITY_LEDGER_FILE = RUNTIME_DIR / "os_capability_ledger.jsonl"
OS_CAPABILITY_EVIDENCE_DIR = RUNTIME_DIR / "os_capability_evidence"
PULSE_SNAPSHOT_FILE = RUNTIME_DIR / "pulse_snapshot.json"
UPDATE_NOW_PENDING_FILE = RUNTIME_DIR / "update_now_pending.json"
DEVICE_LOCATION_FILE = RUNTIME_DIR / "device_location.json"
TOOL_EVENTS_FILE = RUNTIME_DIR / "tool_events.jsonl"
WORK_DECISION_LEARNING_FILE = RUNTIME_DIR / "work_decision_learning.json"
TEST_SESSIONS_DIR = RUNTIME_DIR / "test_sessions"
GENERATED_DEFINITIONS_DIR = TEST_SESSIONS_DIR / "generated_definitions"
PENDING_REVIEW_DIR = TEST_SESSIONS_DIR / "pending_review"
QUARANTINE_DIR = TEST_SESSIONS_DIR / "quarantine"
PROMOTION_AUDIT_LOG = TEST_SESSIONS_DIR / "promotion_audit.jsonl"
PROMOTED_DEFINITIONS_DIR = TEST_SESSIONS_DIR / "promoted"
POLICY_PATH = BASE_DIR / "policy.json"
PYTHON = resolve_python_executable(BASE_DIR)
WORK_TREE_RUN_TRIGGER_FILE = RUNTIME_DIR / "work_tree_run_trigger.json"
PATCH_QUEUE_RUN_TRIGGER_FILE = RUNTIME_DIR / "patch_queue_run_trigger.json"
TEMPORAL_CALENDAR_FILE = BASE_DIR / "runtime" / "temporal" / "operator_calendar.ics"
