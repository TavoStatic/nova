from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from services.nova_shell._constants import ROLES, ROLE_PERMISSIONS

if TYPE_CHECKING:
    from services.nova_shell.store import ShellStore


# ── Static role functions (no DB) ─────────────────────────────────────────────

def role_exists(role: str) -> bool:
    return role in ROLES


def is_static_role(role: str) -> bool:
    return role in ROLES


def role_level(role: str) -> int:
    """Return numeric authority level. Lower = more powerful. Raises KeyError if unknown."""
    return ROLES[role]["level"]


def role_label(role: str) -> str:
    return ROLES[role].get("label", role)


def is_assignable(role: str) -> bool:
    """llc_master is never assignable in the field."""
    return role_exists(role) and bool(ROLES[role].get("assignable", False))


def has_permission(role: str, permission: str) -> bool:
    """
    Check whether a static role has a given permission string.

    Supports:
      - Wildcard "*"          → matches everything (llc_master)
      - Namespace wildcard    → "data.*" matches "data.read", "data.export", ...
      - Exact match           → "system.status"
    """
    if not role_exists(role):
        return False

    perms = ROLE_PERMISSIONS.get(role, set())

    if "*" in perms:
        return True
    if permission in perms:
        return True

    ns = permission.split(".")[0]
    if f"{ns}.*" in perms:
        return True

    return False


def can_assign_role(actor_role: str, target_role: str) -> bool:
    """
    Static-only check: actor can assign target if:
      1. Target is statically assignable.
      2. Actor has users.create.
      3. Actor level < target level (strict — no peer management).
    """
    if not role_exists(actor_role) or not role_exists(target_role):
        return False
    if not is_assignable(target_role):
        return False
    if not has_permission(actor_role, "users.create"):
        return False
    return role_level(actor_role) < role_level(target_role)


def assignable_roles_for(actor_role: str) -> list[str]:
    """Static assignable roles for actor_role."""
    if not role_exists(actor_role):
        return []
    return [r for r in ROLES if can_assign_role(actor_role, r)]


def role_summary() -> list[dict]:
    """Static role list ordered by level (for display)."""
    return sorted(
        [
            {
                "role": r,
                "level": meta["level"],
                "label": meta["label"],
                "description": meta["description"],
                "assignable": meta.get("assignable", False),
                "custom": False,
            }
            for r, meta in ROLES.items()
        ],
        key=lambda x: x["level"],
    )


# ── Custom role helpers (requires store) ─────────────────────────────────────

def _fetch_custom(role: str, store: "ShellStore | None") -> dict[str, Any] | None:
    if store is None:
        return None
    try:
        return store.get_custom_role_by_name(role)
    except Exception:
        return None


def _custom_has_permission(custom: dict[str, Any], permission: str) -> bool:
    perms: set[str] = set(json.loads(custom.get("permissions_json") or "[]"))
    if "*" in perms:
        return True
    if permission in perms:
        return True
    ns = permission.split(".")[0]
    if f"{ns}.*" in perms:
        return True
    return False


# ── Resolve functions (static + custom) ───────────────────────────────────────

def resolve_role_exists(role: str, store: "ShellStore | None" = None) -> bool:
    if role in ROLES:
        return True
    return _fetch_custom(role, store) is not None


def resolve_role_level(role: str, store: "ShellStore | None" = None) -> int:
    """Raises KeyError if role unknown in both static and DB."""
    if role in ROLES:
        return ROLES[role]["level"]
    custom = _fetch_custom(role, store)
    if custom:
        return int(custom["level"])
    raise KeyError(f"Unknown role: {role}")


def resolve_has_permission(
    role: str,
    permission: str,
    store: "ShellStore | None" = None,
) -> bool:
    """Check permission for static or custom role."""
    if role in ROLES:
        return has_permission(role, permission)
    custom = _fetch_custom(role, store)
    if not custom:
        return False
    return _custom_has_permission(custom, permission)


def resolve_can_assign_role(
    actor_role: str,
    target_role: str,
    store: "ShellStore | None" = None,
) -> bool:
    """
    Full assignment check covering static and custom roles.

    Rules (same as static, extended for custom):
      1. Target must be assignable (static: ROLES flag; custom: always True).
      2. Actor must have users.create permission.
      3. Actor level must be strictly lower than target level.
      4. No peer management — account_admin cannot act on another account_admin.
    """
    # Resolve target assignability
    if target_role in ROLES:
        if not ROLES[target_role].get("assignable", False):
            return False
    else:
        # Custom role — confirm it exists
        if _fetch_custom(target_role, store) is None:
            return False
        # Custom roles are always assignable (account_admin created them)

    # Actor must have users.create
    if not resolve_has_permission(actor_role, "users.create", store):
        return False

    # Level check
    try:
        actor_level = resolve_role_level(actor_role, store)
        target_level = resolve_role_level(target_role, store)
    except KeyError:
        return False

    return actor_level < target_level


def resolve_assignable_roles_for(
    actor_role: str,
    store: "ShellStore | None" = None,
) -> list[str]:
    """All roles (static + custom) that actor_role can assign."""
    results: list[str] = []

    # Static roles
    for r in ROLES:
        if resolve_can_assign_role(actor_role, r, store):
            results.append(r)

    # Custom roles
    if store is not None:
        for cr in store.list_custom_roles():
            if resolve_can_assign_role(actor_role, cr["name"], store):
                results.append(cr["name"])

    return results


def resolve_role_summary(store: "ShellStore | None" = None) -> list[dict]:
    """Static + custom roles ordered by level for display."""
    rows = role_summary()  # static
    if store is not None:
        for cr in store.list_custom_roles():
            rows.append({
                "role": cr["name"],
                "level": cr["level"],
                "label": cr["label"],
                "description": f"Custom role. Permissions: {cr['permissions_json']}",
                "assignable": True,
                "custom": True,
            })
    return sorted(rows, key=lambda x: (x["level"], x["role"]))
