from __future__ import annotations

# Nova Shell — security scaffolding.
# Standalone: no nova_core dependency.
# Provides: identity, auth, roles, admin, TOTP, recovery, telemetry stub, update receiver stub.

from services.nova_shell.identity import get_installation_id, load_or_create_identity
from services.nova_shell.store import ShellStore
from services.nova_shell.auth import ShellAuth
from services.nova_shell.admin import ShellAdmin

__all__ = [
    "get_installation_id",
    "load_or_create_identity",
    "ShellStore",
    "ShellAuth",
    "ShellAdmin",
]
