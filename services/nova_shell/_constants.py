from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Role hierarchy
# Lower level = higher authority.
# Tier 0 (llc_master) is not assignable by any field operator — ever.
# Custom roles (created by account_admin) live in the DB, not here.
# ─────────────────────────────────────────────────────────────────────────────

ROLES: dict[str, dict] = {
    "llc_master": {
        "level": 0,
        "label": "Developer Admin",
        "description": "Full system access. LLC-controlled. Not assignable in the field.",
        "assignable": False,
    },
    "account_admin": {
        "level": 1,
        "label": "Account Admin",
        "description": "Manages users and installs backpacks. Cannot touch Nova core or develop backpacks.",
        "assignable": True,
    },
    "standard_user": {
        "level": 2,
        "label": "Standard User",
        "description": "Full operational access to assigned backpacks. Map to a district or business role at setup.",
        "assignable": True,
    },
    "limited_user": {
        "level": 3,
        "label": "Limited User",
        "description": "Restricted access to assigned backpacks. Map to a district or business role at setup.",
        "assignable": True,
    },
    "viewer": {
        "level": 4,
        "label": "Viewer",
        "description": "System status and health only. Read-only across the board.",
        "assignable": True,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Permissions per role.
# "*" = all permissions (llc_master only).
# Namespace wildcard: "data.*" covers data.read, data.export, etc.
#
# backpacks.develop — create / modify / delete backpack code → llc_master only
# system.config     — Nova core configuration                → llc_master only
# backpacks.install — deploy a pre-built backpack            → account_admin
# custom_roles.manage — create / update / delete custom roles → account_admin
# ─────────────────────────────────────────────────────────────────────────────

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "llc_master": {"*"},
    "account_admin": {
        "users.create", "users.read", "users.update", "users.deactivate",
        "backpacks.install", "backpacks.configure", "backpacks.run", "backpacks.view",
        "data.read", "data.export",
        "reports.read", "reports.export",
        "audit.read",
        "system.status", "system.health",
        "custom_roles.manage",
    },
    "standard_user": {
        "system.status", "system.health",
        "backpacks.configure", "backpacks.run", "backpacks.view",
        "data.read",
        "reports.read", "reports.export",
    },
    "limited_user": {
        "system.status", "system.health",
        "backpacks.run", "backpacks.view",
        "data.read",
        "reports.read",
    },
    "viewer": {
        "system.status", "system.health",
    },
}

# Maximum permission set account_admin may grant to a custom role.
# Custom role permissions must be a strict subset of this.
MAX_CUSTOM_ROLE_PERMISSIONS: frozenset[str] = frozenset(ROLE_PERMISSIONS["account_admin"])

# ─────────────────────────────────────────────────────────────────────────────
# LLC Public Key (Ed25519) — TEMPORARY bake-in
#
# The fleet LLC system that will issue and manage real keys is NOT built yet.
# Product is unfinished. This key is a generic development stand-in only.
#
# TEMP (replace when LLC management system exists):
#   1. Generate real keys offline for the LLC.
#   2. Keep private key OFFLINE — never commit it.
#   3. Replace LLC_PUBLIC_KEY_PEM with the production public key.
#   4. Set LLC_KEY_PROVISIONING = "production".
# ─────────────────────────────────────────────────────────────────────────────

# Generic Ed25519 SPKI public key (valid PEM shape for crypto libs). NOT production.
LLC_PUBLIC_KEY_PEM = """\
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAGb9ECWmEzf6FQbrBZ9w7lshQhqowtrbLDFw4rXAxZuE=
-----END PUBLIC KEY-----
"""

# provisioning: temporary = baked generic key; production = real LLC-managed key
LLC_KEY_PROVISIONING: str = "temporary"
LLC_PUBLIC_KEY_IS_PLACEHOLDER: bool = LLC_KEY_PROVISIONING != "production"
LLC_PUBLIC_KEY_IS_TEMPORARY: bool = LLC_KEY_PROVISIONING == "temporary"

# ─────────────────────────────────────────────────────────────────────────────
# LLC telemetry / central — TEMPORARY bake-in
#
# Central telemetry management is NOT built yet. Temp URL is a blank to fill.
# Do not treat reachability as "system finished."
# ─────────────────────────────────────────────────────────────────────────────

LLC_TELEMETRY_CENTRAL_URL: str = "https://llc-central.temp.local/v1/telemetry"
LLC_TELEMETRY_PROVISIONING: str = "temporary"  # temporary | production
LLC_TELEMETRY_SYSTEM_BUILT: bool = False

# ─────────────────────────────────────────────────────────────────────────────
# Session config
# ─────────────────────────────────────────────────────────────────────────────

SESSION_EXPIRY_HOURS: int = 8
MAX_SESSIONS_PER_USER: int = 5

# ─────────────────────────────────────────────────────────────────────────────
# Brute-force protection
# ─────────────────────────────────────────────────────────────────────────────

LOGIN_MAX_ATTEMPTS: int = 5
LOGIN_LOCKOUT_MINUTES: int = 15

# ─────────────────────────────────────────────────────────────────────────────
# Recovery codes
# ─────────────────────────────────────────────────────────────────────────────

RECOVERY_CODE_COUNT: int = 8
RECOVERY_CODE_LENGTH: int = 10

# ─────────────────────────────────────────────────────────────────────────────
# TOTP
# ─────────────────────────────────────────────────────────────────────────────

TOTP_ISSUER: str = "Nova by SG Intelligence"
TOTP_DIGITS: int = 6
TOTP_INTERVAL: int = 30

# ─────────────────────────────────────────────────────────────────────────────
# Nova Shell version
# ─────────────────────────────────────────────────────────────────────────────

NOVA_SHELL_VERSION: str = "0.1.0"
