"""Aggregate unfinished finish-areas (not pending thrash tasks)."""
from __future__ import annotations

from typing import Any

from services.capabilities_gap_detector import detect_capability_gaps
from services.nova_shell.external_finish import external_finish_status
from services.supervisor_finish import supervisor_ownership_finish_status


def build_finish_areas_inventory(*, base_dir=None) -> dict[str, Any]:
    gaps, gap_summary = detect_capability_gaps(base_dir)
    ownership = dict(gap_summary.get("finish_ownership") or {})
    external_caps = list(ownership.get("external_gaps") or [])
    nova_caps = list(ownership.get("nova_code_gaps") or [])
    shell = external_finish_status()
    supervisor = supervisor_ownership_finish_status()

    external_rows: list[dict[str, Any]] = []
    for row in external_caps:
        if isinstance(row, dict):
            external_rows.append(row)
        else:
            external_rows.append({"capability": str(row), "finisher": "operator_product", "missing": ""})

    for row in list(shell.get("incomplete_areas") or []):
        external_rows.append(
            {
                "area": row.get("area"),
                "finisher": row.get("finisher") or "llc_external",
                "missing": row.get("missing") or "",
                "surface": "nova_shell",
            }
        )
    for row in list(supervisor.get("incomplete_areas") or []):
        external_rows.append(
            {
                "area": row.get("area"),
                "finisher": row.get("finisher") or "operator_policy",
                "missing": row.get("missing") or "",
                "surface": "supervisor",
            }
        )

    return {
        "ok": bool(shell.get("ok")) and bool(supervisor.get("ok")) and not external_caps,
        "capability_gap_count": len(gaps),
        "nova_code_finish_count": len(nova_caps),
        "nova_code_finish": nova_caps,
        "external_finish_count": len(external_rows),
        "external_finish": external_rows,
        "shell_external_finish": shell,
        "supervisor_ownership_finish": supervisor,
        "capabilities_gap_summary": gap_summary,
    }
