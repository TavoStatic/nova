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
# LLC Public Key (Ed25519)
#
# IMPORTANT: This is a placeholder for development.
# Before production:
#   1. Run: python scripts/setup_nova_shell.py --generate-llc-keys
#   2. Keep the private key OFFLINE and SECURE — never commit it.
#   3. Replace the value below with your real public key.
#   4. Set LLC_PUBLIC_KEY_IS_PLACEHOLDER = False.
#   5. Rebuild and ship the package.
# ─────────────────────────────────────────────────────────────────────────────

LLC_PUBLIC_KEY_PEM = """\
-----BEGIN PUBLIC KEY-----
PLACEHOLDER_REPLACE_WITH_REAL_LLC_ED25519_PUBLIC_KEY_BEFORE_PRODUCTION
-----END PUBLIC KEY-----
"""

LLC_PUBLIC_KEY_IS_PLACEHOLDER = "PLACEHOLDER" in LLC_PUBLIC_KEY_PEM

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

TOTP_ISSUER: str = "Nova by NYO System"
TOTP_DIGITS: int = 6
TOTP_INTERVAL: int = 30

# ─────────────────────────────────────────────────────────────────────────────
# Nova Shell version
# ─────────────────────────────────────────────────────────────────────────────

NOVA_SHELL_VERSION: str = "0.1.0"
