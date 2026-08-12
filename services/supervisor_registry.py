from __future__ import annotations

# Default supervisor rule specs.
# Each entry: {name, priority, phases}
# Handlers are in services/supervisor_rules.py → DEFAULT_RULE_HANDLERS.
# Rules are loaded by supervisor.py Supervisor.__init__().
#
# priority: lower = evaluated first. Owning rules (identity_location_guard)
# should have lower priority numbers so they intercept before observers.
#
# phases: "intent" = move classification (non-owning);
#         "handle" = turn interception (may be owning).

DEFAULT_SUPERVISOR_RULE_SPECS: list[dict[str, object]] = [
    {
        "name": "intent_move_classify",
        "priority": 10,
        "phases": ["intent"],
    },
    {
        "name": "identity_location_guard",
        "priority": 20,
        "phases": ["handle"],
    },
    {
        "name": "ambiguous_clarifier_gate",
        "priority": 30,
        "phases": ["handle"],
    },
    {
        "name": "safe_fallback_contract",
        "priority": 50,
        "phases": ["handle"],
    },
]
