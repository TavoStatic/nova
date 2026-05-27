from __future__ import annotations

from typing import Callable


CORE_PART_ORDER = (
    "runtime_core",
    "guard_system",
    "work_tree",
    "health_monitoring",
    "memory_systems",
    "task_routing",
    "maintenance_loops",
    "release_verification",
    "subconscious_priority",
    "autonomy_handling",
    "operator_outbox",
)


def _clean(value: object, limit: int = 220) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[: max(0, int(limit or 220))]


def operational_identity_context_for_prompt(*, load_capabilities_fn: Callable[[], dict]) -> str:
    try:
        capabilities = load_capabilities_fn()
    except Exception:
        capabilities = {}
    registry = capabilities if isinstance(capabilities, dict) else {}
    parts: list[str] = []
    for key in CORE_PART_ORDER:
        description = _clean(registry.get(key))
        if description:
            parts.append(f"- {key}: {description}")

    if not parts:
        return ""

    lines = [
        "Operational Nova self evidence:",
        "Registered internal surfaces observed from the capability registry:",
        *parts[:11],
    ]
    return "\n".join(lines)
