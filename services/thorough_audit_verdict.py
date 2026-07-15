"""Verdict logic for the thorough audit probe (canonical, testable)."""
from __future__ import annotations

from typing import Any, Mapping


def live_closure_hard_fail(live_closure: Mapping[str, Any] | None) -> bool:
    """Fail when any root is not ok, not only when semantic live_gaps are non-empty."""
    payload = dict(live_closure or {})
    if not bool(payload.get("ok", False)):
        return True
    return int(payload.get("gap_count") or 0) > 0


def build_hard_fail_report(
    *,
    profiles: Mapping[str, Any] | None,
    wiring: Mapping[str, Any] | None,
    live_closure: Mapping[str, Any] | None,
    regression: Mapping[str, Any] | None,
    mission: Mapping[str, Any] | None,
) -> dict[str, Any]:
    profile_payload = dict(profiles or {})
    wiring_payload = dict(wiring or {})
    closure_payload = dict(live_closure or {})
    regression_payload = dict(regression or {})
    mission_payload = dict(mission or {})

    live_gaps = [
        {"root_id": row.get("root_id"), "gaps": row.get("live_gaps")}
        for row in list(closure_payload.get("roots") or [])
        if isinstance(row, dict) and row.get("live_gaps")
    ]
    closure_fail = live_closure_hard_fail(closure_payload)
    mission_autonomy_blocked = bool(mission_payload.get("autonomy_blocked"))
    hard_fail = (
        not bool(profile_payload.get("code_ok", profile_payload.get("ok")))
        or not bool(wiring_payload.get("ok"))
        or closure_fail
        or bool(regression_payload.get("failure_active"))
        or mission_autonomy_blocked
    )
    return {
        "hard_fail": hard_fail,
        "closure_fail": closure_fail,
        "live_closure_ok": bool(closure_payload.get("ok")),
        "gap_count": int(closure_payload.get("gap_count") or 0),
        "gap_roots": list(closure_payload.get("gap_roots") or []),
        "semantic_live_gap_count": len(live_gaps),
        "semantic_live_gaps": live_gaps,
        "mission_autonomy_blocked": mission_autonomy_blocked,
    }