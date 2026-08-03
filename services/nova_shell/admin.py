from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from services.nova_shell._constants import MAX_CUSTOM_ROLE_PERMISSIONS
from services.nova_shell.auth import ShellAuth, hash_password
from services.nova_shell.recovery import (
    codes_to_json,
    generate_recovery_codes,
)
from services.nova_shell.roles import (
    is_assignable,
    resolve_can_assign_role,
    resolve_role_level,
)
from services.nova_shell.store import ShellStore
from services.nova_shell.totp import generate_totp_secret, totp_uri, verify_totp

# Custom role level bounds (cannot be llc_master or account_admin level)
_CUSTOM_ROLE_MIN_LEVEL = 2
_CUSTOM_ROLE_MAX_LEVEL = 4


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class TOTPSetupResult:
    secret: str
    uri: str
    user_id: str


class ShellAdmin:
    """
    Administrative operations for Nova Shell.

    All mutating operations write to audit_log.
    Role-assignment rules are enforced by the roles module (static + custom).
    """

    def __init__(self, store: ShellStore, auth: ShellAuth) -> None:
        self._store = store
        self._auth = auth

    # ── Bootstrap ──────────────────────────────────────────────────────────

    def first_admin_exists(self) -> bool:
        users = self._store.list_users()
        return any(u["role"] == "account_admin" for u in users)

    def create_first_admin(
        self,
        username: str,
        password: str,
        display_name: str = "",
    ) -> dict[str, Any]:
        """
        Create the initial account_admin.
        Fails if one already exists — prevents re-seeding on live systems.
        """
        if self.first_admin_exists():
            raise RuntimeError("An account_admin already exists.")
        _validate_password(password)
        return self._create_user_internal(
            username=username,
            password=password,
            display_name=display_name or username,
            role="account_admin",
            actor_role=None,
        )

    # ── User management ────────────────────────────────────────────────────

    def create_user(
        self,
        actor_token: str,
        username: str,
        password: str,
        role: str,
        display_name: str = "",
    ) -> dict[str, Any]:
        actor = self._auth.require_permission(actor_token, "users.create")
        self._check_role_assignable(actor.role, role)
        _validate_password(password)
        user = self._create_user_internal(
            username=username,
            password=password,
            display_name=display_name or username,
            role=role,
            actor_role=actor.role,
        )
        self._store.audit(
            "user_created",
            user_id=actor.user_id,
            username=actor.username,
            detail=f"new_user={username} role={role}",
        )
        return user

    def _create_user_internal(
        self,
        username: str,
        password: str,
        display_name: str,
        role: str,
        actor_role: str | None,
    ) -> dict[str, Any]:
        from services.nova_shell.roles import resolve_role_exists
        if not resolve_role_exists(role, self._store):
            raise ValueError(f"Unknown role: {role}")
        if actor_role is not None:
            self._check_role_assignable(actor_role, role)
        if self._store.get_user_by_username(username):
            raise ValueError(f"Username already exists: {username}")
        now = _now()
        _, hashed_codes = generate_recovery_codes()
        user: dict[str, Any] = {
            "id": _new_id(),
            "username": username,
            "display_name": display_name,
            "role": role,
            "password_hash": hash_password(password),
            "totp_secret": None,
            "totp_enabled": 0,
            "recovery_codes_json": codes_to_json(hashed_codes),
            "active": 1,
            "created_at": now,
            "updated_at": now,
        }
        self._store.create_user(user)
        return {k: v for k, v in user.items() if k not in ("password_hash", "totp_secret", "recovery_codes_json")}

    def set_role(self, actor_token: str, target_username: str, new_role: str) -> None:
        actor = self._auth.require_permission(actor_token, "users.update")
        self._check_role_assignable(actor.role, new_role)
        target = self._get_user_or_raise(target_username)
        # Strict rule: cannot act on a peer or superior
        self._check_authority_over(actor.role, target["role"])
        self._store.update_user(target["id"], {"role": new_role})
        self._store.revoke_all_sessions(target["id"])
        self._store.audit(
            "role_changed",
            user_id=actor.user_id,
            username=actor.username,
            detail=f"target={target_username} old={target['role']} new={new_role}",
        )

    def deactivate_user(self, actor_token: str, target_username: str) -> None:
        actor = self._auth.require_permission(actor_token, "users.deactivate")
        target = self._get_user_or_raise(target_username)
        if target["role"] == "llc_master":
            raise PermissionError("Cannot deactivate llc_master accounts.")
        self._check_authority_over(actor.role, target["role"])
        self._store.update_user(target["id"], {"active": 0})
        self._store.revoke_all_sessions(target["id"])
        self._store.audit(
            "user_deactivated",
            user_id=actor.user_id,
            username=actor.username,
            detail=f"target={target_username}",
        )

    def reactivate_user(self, actor_token: str, target_username: str) -> None:
        actor = self._auth.require_permission(actor_token, "users.update")
        target = self._get_user_or_raise(target_username)
        self._check_authority_over(actor.role, target["role"])
        self._store.update_user(target["id"], {"active": 1})
        self._store.audit(
            "user_reactivated",
            user_id=actor.user_id,
            username=actor.username,
            detail=f"target={target_username}",
        )

    # ── Password ───────────────────────────────────────────────────────────

    def change_password(self, actor_token: str, target_username: str, new_password: str) -> None:
        actor = self._auth.verify_session(actor_token)
        if not actor:
            raise PermissionError("Not authenticated.")
        target = self._get_user_or_raise(target_username)
        is_self = actor.username == target_username
        if not is_self:
            self._check_authority_over(actor.role, target["role"])
        if target["role"] == "llc_master" and not is_self:
            raise PermissionError("Cannot reset llc_master password remotely.")
        _validate_password(new_password)
        self._store.update_user(target["id"], {
            "password_hash": hash_password(new_password),
            "force_password_reset": 0,
        })
        self._store.revoke_all_sessions(target["id"])
        self._store.audit(
            "password_changed",
            user_id=actor.user_id,
            username=actor.username,
            detail=f"target={target_username}",
        )

    def force_password_reset(self, actor_token: str, target_username: str) -> None:
        actor = self._auth.require_permission(actor_token, "users.update")
        target = self._get_user_or_raise(target_username)
        self._check_authority_over(actor.role, target["role"])
        self._store.update_user(target["id"], {"force_password_reset": 1})
        self._store.audit(
            "force_password_reset",
            user_id=actor.user_id,
            username=actor.username,
            detail=f"target={target_username}",
        )

    # ── TOTP ───────────────────────────────────────────────────────────────

    def setup_totp(self, actor_token: str) -> TOTPSetupResult:
        actor = self._auth.verify_session(actor_token)
        if not actor:
            raise PermissionError("Not authenticated.")
        secret = generate_totp_secret()
        self._store.update_user(actor.user_id, {"totp_secret": secret})
        return TOTPSetupResult(
            secret=secret,
            uri=totp_uri(secret, actor.username),
            user_id=actor.user_id,
        )

    def confirm_totp(self, actor_token: str, code: str) -> bool:
        actor = self._auth.verify_session(actor_token)
        if not actor:
            raise PermissionError("Not authenticated.")
        user = self._store.get_user_by_id(actor.user_id)
        if not user or not user["totp_secret"]:
            raise RuntimeError("No pending TOTP setup. Call setup_totp() first.")
        if not verify_totp(user["totp_secret"], code):
            self._store.audit("totp_confirm_fail", user_id=actor.user_id, username=actor.username, ok=False)
            return False
        self._store.update_user(actor.user_id, {"totp_enabled": 1})
        self._store.audit("totp_enabled", user_id=actor.user_id, username=actor.username)
        return True

    def disable_totp(self, actor_token: str, target_username: str) -> None:
        actor = self._auth.verify_session(actor_token)
        if not actor:
            raise PermissionError("Not authenticated.")
        target = self._get_user_or_raise(target_username)
        is_self = actor.username == target_username
        if not is_self:
            self._check_authority_over(actor.role, target["role"])
        self._store.update_user(target["id"], {"totp_secret": None, "totp_enabled": 0})
        self._store.audit(
            "totp_disabled",
            user_id=actor.user_id,
            username=actor.username,
            detail=f"target={target_username}",
        )

    # ── Recovery codes ─────────────────────────────────────────────────────

    def regenerate_recovery_codes(self, actor_token: str) -> list[str]:
        actor = self._auth.verify_session(actor_token)
        if not actor:
            raise PermissionError("Not authenticated.")
        plaintext, hashed = generate_recovery_codes()
        self._store.update_user(actor.user_id, {"recovery_codes_json": codes_to_json(hashed)})
        self._store.audit("recovery_codes_regenerated", user_id=actor.user_id, username=actor.username)
        return plaintext

    # ── Custom roles ───────────────────────────────────────────────────────

    def create_custom_role(
        self,
        actor_token: str,
        name: str,
        label: str,
        level: int,
        permissions: list[str],
    ) -> dict[str, Any]:
        """
        Create a custom role.

        name        — machine name, e.g. "data_entry" (lowercase, no spaces)
        label       — display name
        level       — 2–4 (cannot be 0 or 1 — those are reserved for llc/admin)
        permissions — must be a subset of MAX_CUSTOM_ROLE_PERMISSIONS
        """
        actor = self._auth.require_permission(actor_token, "custom_roles.manage")
        _validate_custom_role_name(name)
        _validate_custom_role_level(level)
        _validate_custom_role_permissions(permissions)

        if self._store.get_custom_role_by_name(name):
            raise ValueError(f"Custom role already exists: {name}")

        now = _now()
        role: dict[str, Any] = {
            "id": _new_id(),
            "name": name,
            "label": label,
            "level": level,
            "permissions_json": json.dumps(sorted(set(permissions))),
            "created_by": actor.user_id,
            "created_at": now,
            "updated_at": now,
        }
        self._store.create_custom_role(role)
        self._store.audit(
            "custom_role_created",
            user_id=actor.user_id,
            username=actor.username,
            detail=f"name={name} level={level}",
        )
        return role

    def update_custom_role(
        self,
        actor_token: str,
        name: str,
        *,
        label: str | None = None,
        level: int | None = None,
        permissions: list[str] | None = None,
    ) -> None:
        actor = self._auth.require_permission(actor_token, "custom_roles.manage")
        if not self._store.get_custom_role_by_name(name):
            raise ValueError(f"Custom role not found: {name}")
        fields: dict[str, Any] = {}
        if label is not None:
            fields["label"] = label
        if level is not None:
            _validate_custom_role_level(level)
            fields["level"] = level
        if permissions is not None:
            _validate_custom_role_permissions(permissions)
            fields["permissions_json"] = json.dumps(sorted(set(permissions)))
        if not fields:
            return
        self._store.update_custom_role(name, fields)
        self._store.audit(
            "custom_role_updated",
            user_id=actor.user_id,
            username=actor.username,
            detail=f"name={name} changed={list(fields.keys())}",
        )

    def delete_custom_role(self, actor_token: str, name: str) -> None:
        """
        Delete a custom role. Blocked if any active users hold it.
        Reassign users before deleting.
        """
        actor = self._auth.require_permission(actor_token, "custom_roles.manage")
        if not self._store.get_custom_role_by_name(name):
            raise ValueError(f"Custom role not found: {name}")
        active = self._store.count_users_with_role(name)
        if active > 0:
            raise RuntimeError(
                f"Cannot delete '{name}': {active} active user(s) hold this role. "
                "Reassign them first."
            )
        self._store.delete_custom_role(name)
        self._store.audit(
            "custom_role_deleted",
            user_id=actor.user_id,
            username=actor.username,
            detail=f"name={name}",
        )

    def list_custom_roles(self, actor_token: str) -> list[dict[str, Any]]:
        self._auth.require_permission(actor_token, "custom_roles.manage")
        return self._store.list_custom_roles()

    # ── Utilities ──────────────────────────────────────────────────────────

    def list_users(self, actor_token: str) -> list[dict[str, Any]]:
        self._auth.require_permission(actor_token, "users.read")
        users = self._store.list_users()
        return [
            {k: v for k, v in u.items()
             if k not in ("password_hash", "totp_secret", "recovery_codes_json")}
            for u in users
        ]

    def _get_user_or_raise(self, username: str) -> dict[str, Any]:
        user = self._store.get_user_by_username(username)
        if not user:
            raise ValueError(f"User not found: {username}")
        return user

    def _check_role_assignable(self, actor_role: str, target_role: str) -> None:
        """Raise PermissionError if actor cannot assign target_role."""
        from services.nova_shell.roles import is_assignable as _static_is_assignable
        # Static non-assignable (llc_master)
        if target_role in ("llc_master",):
            raise PermissionError(f"Role '{target_role}' is not assignable.")
        if not resolve_can_assign_role(actor_role, target_role, self._store):
            raise PermissionError(
                f"Role '{actor_role}' cannot assign role '{target_role}'."
            )

    def _check_authority_over(self, actor_role: str, target_role: str) -> None:
        """
        Strict peer check: actor must strictly outrank target.
        account_admin cannot act on another account_admin.
        """
        try:
            actor_level = resolve_role_level(actor_role, self._store)
            target_level = resolve_role_level(target_role, self._store)
        except KeyError:
            raise PermissionError("Unknown role in authority check.")
        if actor_level >= target_level:
            raise PermissionError(
                f"Insufficient authority: '{actor_role}' cannot act on '{target_role}'."
            )


# ── Validators ────────────────────────────────────────────────────────────────

def _validate_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters.")


def _validate_custom_role_name(name: str) -> None:
    import re
    if not re.match(r"^[a-z][a-z0-9_]{1,49}$", name):
        raise ValueError(
            "Custom role name must be lowercase letters, digits, or underscores, "
            "start with a letter, and be 2–50 characters."
        )


def _validate_custom_role_level(level: int) -> None:
    if level < _CUSTOM_ROLE_MIN_LEVEL or level > _CUSTOM_ROLE_MAX_LEVEL:
        raise ValueError(
            f"Custom role level must be between {_CUSTOM_ROLE_MIN_LEVEL} "
            f"and {_CUSTOM_ROLE_MAX_LEVEL}."
        )


def _validate_custom_role_permissions(permissions: list[str]) -> None:
    invalid = set(permissions) - MAX_CUSTOM_ROLE_PERMISSIONS
    if invalid:
        raise ValueError(
            f"Permissions exceed what account_admin can grant: {sorted(invalid)}"
        )
