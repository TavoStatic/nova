from __future__ import annotations

"""
HTTP trust rules for Nova Shell roles on control/API surfaces.

Current state (honest):
  - Control panel routes are gated by CONTROL_AUTH (API token / control login).
  - Nova Shell session tokens from services.nova_shell.auth are NOT yet validated
    as middleware on nova_http routes.
  - Therefore a query-string or body `role=` is NOT a credential. Callers who pass
    control auth must not be allowed to invent elevated Shell roles for grant demos
    without an allowlist.

When shell bearer tokens are wired later, resolve_shell_role_from_request() should
read the Authorization header first and ignore client-supplied role elevation.
"""

from typing import Any

# Roles that may appear in operations.json default_grants
KNOWN_SHELL_ROLES = frozenset(
    {
        "llc_master",
        "account_admin",
        "standard_user",
        "limited_user",
        "viewer",
    }
)

# Roles a control-authenticated operator may *preview* for grant UI (not elevation proof)
CONTROL_PREVIEW_ROLES = frozenset(
    {
        "account_admin",
        "standard_user",
        "limited_user",
        "viewer",
    }
)


def resolve_control_panel_role(
    requested: str | None,
    *,
    control_authenticated: bool,
    for_privileged_action: bool = False,
) -> str:
    """
    Map a requested role string for control-panel backpack surfaces.

    - Not control-authenticated → viewer (least privilege; should not reach here).
    - Privileged actions (install, report, probe) → account_admin always.
      Control auth is the real gate; client cannot self-assert llc_master.
    - Grants preview GET → allowlisted role or account_admin default.
    """
    if not control_authenticated:
        return "viewer"

    if for_privileged_action:
        return "account_admin"

    role = str(requested or "").strip()
    if role in CONTROL_PREVIEW_ROLES:
        return role
    if role in KNOWN_SHELL_ROLES and role == "llc_master":
        # Never honor llc_master from a client claim on control UI
        return "account_admin"
    return "account_admin"


def shell_http_status() -> dict[str, Any]:
    """Status blob for diagnostics — reflects actual wiring state."""
    try:
        from services.nova_shell_control_bridge import shell_status, shell_is_active
        active = shell_is_active()
        bridge = shell_status()
    except Exception:
        active = False
        bridge = {"active": False, "reason": "bridge_import_error"}
    return {
        "shell_bearer_middleware": active,
        "control_auth_gates_control_api": True,
        "role_query_param_is_not_a_credential": True,
        "shell_bridge": bridge,
        "note": (
            "Nova Shell login is routed through services.nova_shell_control_bridge "
            "when Shell DB exists and has at least one active user. "
            "Falls back to NOVA_CONTROL_USER/PASS env-var auth otherwise. "
            "Backpack grant role claims from the client are allowlisted only."
        ),
    }
