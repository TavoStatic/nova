"""Unfinished Nova Shell areas that require LLC / operator pieces.

Temporary bake-ins (generic key, temp telemetry URL) are NOT completion.
Product and LLC management systems are not finished; status stays honest.
"""
from __future__ import annotations

from typing import Any

from services.nova_shell._constants import (
    LLC_KEY_PROVISIONING,
    LLC_PUBLIC_KEY_IS_TEMPORARY,
    LLC_TELEMETRY_PROVISIONING,
    LLC_TELEMETRY_SYSTEM_BUILT,
    NOVA_SHELL_VERSION,
)
from services.nova_shell.telemetry import telemetry_status
from services.nova_shell.update_receiver import receiver_status


def external_finish_status() -> dict[str, Any]:
    """Honest inventory of shell finish work (temp bake-in != done)."""
    telemetry = telemetry_status()
    receiver = receiver_status()
    key_production = str(LLC_KEY_PROVISIONING or "") == "production"
    telemetry_production = (
        str(LLC_TELEMETRY_PROVISIONING or "") == "production" and bool(LLC_TELEMETRY_SYSTEM_BUILT)
    )
    areas = [
        {
            "area": "llc_public_key",
            "finisher": "llc_external",
            "complete": key_production,
            "temporary_bake_in": bool(LLC_PUBLIC_KEY_IS_TEMPORARY),
            "missing": (
                ""
                if key_production
                else "Replace temporary bake-in key when LLC key-management system exists"
            ),
        },
        {
            "area": "telemetry_central",
            "finisher": "llc_external",
            "complete": telemetry_production and bool(telemetry.get("connected")),
            "temporary_bake_in": str(telemetry.get("provisioning") or "") == "temporary",
            "central_url": str(telemetry.get("central_url") or ""),
            "missing": (
                ""
                if telemetry_production
                else "Build LLC telemetry central; temp URL is config only, system_built=false"
            ),
        },
        {
            "area": "signed_update_apply",
            "finisher": "llc_external",
            "complete": key_production and bool(receiver.get("update_system_built")),
            "temporary_bake_in": bool(receiver.get("llc_key_temporary")),
            "missing": (
                ""
                if key_production and receiver.get("update_system_built")
                else "Build fleet update system + production key + apply path"
            ),
        },
    ]
    incomplete = [row for row in areas if not row.get("complete")]
    return {
        "ok": len(incomplete) == 0,
        "finisher": "llc_external",
        "nova_shell_version": NOVA_SHELL_VERSION,
        "product_finished": False,
        "llc_systems_built": False,
        "area_count": len(areas),
        "incomplete_count": len(incomplete),
        "areas": areas,
        "incomplete_areas": incomplete,
        "summary": (
            "Nova Shell external finish surfaces are complete"
            if not incomplete
            else (
                f"{len(incomplete)} shell area(s) still need real LLC systems "
                "(temporary key/URL bake-ins are not completion)"
            )
        ),
    }
