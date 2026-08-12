"""Unfinished supervisor ownership area (operator policy).

Empty rule specs are not thrash tasks — they are missing operator-owned finish work.
"""
from __future__ import annotations

from typing import Any

from services.supervisor_registry import DEFAULT_SUPERVISOR_RULE_SPECS


def supervisor_ownership_finish_status() -> dict[str, Any]:
    """Status of supervisor ownership rules as an unfinished finish-area."""
    try:
        from services.supervisor_authority import (
            EXPLICIT_HANDLE_OWNERSHIP_RULES,
            EXPLICIT_INTENT_OWNERSHIP_RULES,
        )
    except Exception:
        EXPLICIT_HANDLE_OWNERSHIP_RULES = frozenset()
        EXPLICIT_INTENT_OWNERSHIP_RULES = frozenset()

    rule_specs = list(DEFAULT_SUPERVISOR_RULE_SPECS or [])
    intent_rules = frozenset(EXPLICIT_INTENT_OWNERSHIP_RULES or ())
    handle_rules = frozenset(EXPLICIT_HANDLE_OWNERSHIP_RULES or ())
    areas = [
        {
            "area": "default_supervisor_rule_specs",
            "finisher": "operator_policy",
            "complete": len(rule_specs) > 0,
            "missing": (
                ""
                if rule_specs
                else "Populate DEFAULT_SUPERVISOR_RULE_SPECS with real ownership rule specs"
            ),
            "count": len(rule_specs),
        },
        {
            "area": "explicit_intent_ownership_rules",
            "finisher": "operator_policy",
            "complete": len(intent_rules) > 0,
            "missing": (
                ""
                if intent_rules
                else "Define EXPLICIT_INTENT_OWNERSHIP_RULES (who owns which intents)"
            ),
            "count": len(intent_rules),
        },
        {
            "area": "explicit_handle_ownership_rules",
            "finisher": "operator_policy",
            "complete": len(handle_rules) > 0,
            "missing": (
                ""
                if handle_rules
                else "Define EXPLICIT_HANDLE_OWNERSHIP_RULES (who owns which handles)"
            ),
            "count": len(handle_rules),
        },
    ]
    incomplete = [row for row in areas if not row.get("complete")]
    return {
        "ok": len(incomplete) == 0,
        "finisher": "operator_policy",
        "incomplete_count": len(incomplete),
        "areas": areas,
        "incomplete_areas": incomplete,
        "summary": (
            "Supervisor ownership rules are populated"
            if not incomplete
            else f"{len(incomplete)} supervisor ownership area(s) need operator policy"
        ),
    }
