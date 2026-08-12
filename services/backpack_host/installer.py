from __future__ import annotations

"""
Backpack Installer

Validates user-supplied settings against settings_schema.json,
writes them to the paths the connector expects, and runs the
ordered install_steps sequence.

Write paths:
  1. runtime/{backpack_id}/settings.json
     Flat settings file read by the connector via manifest.local_config_path.
     This is what connector._settings() returns.

  2. runtime/edfi/connections/{connection_id}/local_config.json  (data connector only)
     Written via services.edfi.config.save_connection_config() so the DataConnector
     service layer (run_self_profile, DataConnectorClient, etc.) can find the config.
     Triggered when the settings include base_url + client_id + client_secret
     (the shape of an HTTP-authenticated ODS connection).
"""

import json
import re
from pathlib import Path
from typing import Any


def _read_schema(backpack_dir: Path) -> dict[str, Any]:
    path = Path(backpack_dir) / "settings_schema.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _all_fields(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten all fields from all sections."""
    fields: list[dict[str, Any]] = []
    for section in schema.get("sections") or []:
        if isinstance(section, dict):
            for field in section.get("fields") or []:
                if isinstance(field, dict):
                    fields.append(field)
    return fields


def _backpack_id_from_dir(backpack_dir: Path) -> str:
    manifest_path = Path(backpack_dir) / "backpack.json"
    if not manifest_path.exists():
        return backpack_dir.name
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return str(data.get("id") or backpack_dir.name).strip()
    except Exception:
        return backpack_dir.name


class BackpackInstaller:
    """
    Validate, apply, and run install steps for a backpack.

    Usage:
        installer = BackpackInstaller()
        errors = installer.validate(backpack_dir, values)
        if errors:
            return errors
        apply_result = installer.apply(backpack_dir, values, runtime_root=runtime_root)
        steps = installer.run_all_install_steps(backpack_dir, values, runtime_root=runtime_root)
    """

    # ── Normalization ──────────────────────────────────────────────────────

    @staticmethod
    def normalize_settings_values(values: dict[str, Any]) -> dict[str, Any]:
        """
        Return a copy with canonical scope_mode, credential_access_tier, and LEA fields.

        Used by validate (writes back into the caller's dict on success) and apply
        (so settings.json never stores aliases like "district" instead of "single_lea").
        """
        prepared = dict(values or {})
        try:
            from services.backpack_host.scope_settings import (
                allowed_leas_from_settings,
                normalize_access_tier,
                normalize_scope_mode,
                primary_lea_from_settings,
            )

            prepared["scope_mode"] = normalize_scope_mode(prepared.get("scope_mode"))
            prepared["credential_access_tier"] = normalize_access_tier(
                prepared.get("credential_access_tier")
            )
            primary = primary_lea_from_settings(prepared)
            if primary:
                prepared["district_lea_id"] = primary
            allowed = allowed_leas_from_settings(prepared)
            if prepared.get("scope_mode") == "multi_lea" and allowed:
                prepared["allowed_lea_ids"] = ", ".join(allowed)
        except Exception:
            pass
        return prepared

    # ── Validation ─────────────────────────────────────────────────────────

    def validate(
        self,
        backpack_dir: Path,
        values: dict[str, Any],
    ) -> list[dict[str, str]]:
        """
        Validate user-supplied values against settings_schema.json.

        On success (no errors), mutates `values` in place with normalized
        scope_mode / credential_access_tier / LEA fields so a subsequent
        apply() writes the same canonical form.

        Returns a list of error dicts (empty = valid).
        Each error has: code, field, detail.
        """
        schema = _read_schema(backpack_dir)
        errors: list[dict[str, str]] = []

        for field in _all_fields(schema):
            key = str(field.get("key") or "")
            label = str(field.get("label") or key)
            required = bool(field.get("required", False))
            field_type = str(field.get("type") or "string")
            value = values.get(key)

            # Required check
            if required and (value is None or str(value).strip() == ""):
                errors.append({
                    "code": f"{key}_required",
                    "field": key,
                    "detail": f"'{label}' is required.",
                })
                continue

            if value is None or str(value).strip() == "":
                continue  # optional, absent — skip further checks

            # Pattern check (string fields only)
            pattern = str(field.get("pattern") or "")
            if pattern and field_type == "string":
                if not re.match(pattern, str(value)):
                    errors.append({
                        "code": f"{key}_invalid_format",
                        "field": key,
                        "detail": f"'{label}' does not match expected format.",
                    })

            # URL check
            if field_type == "url":
                from urllib.parse import urlparse
                parsed = urlparse(str(value))
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    errors.append({
                        "code": f"{key}_invalid_url",
                        "field": key,
                        "detail": f"'{label}' must be a valid http(s) URL.",
                    })

            # Integer range check
            if field_type == "integer":
                try:
                    int_val = int(value)
                    min_val = field.get("min")
                    max_val = field.get("max")
                    if min_val is not None and int_val < int(min_val):
                        errors.append({
                            "code": f"{key}_out_of_range",
                            "field": key,
                            "detail": f"'{label}' must be at least {min_val}.",
                        })
                    if max_val is not None and int_val > int(max_val):
                        errors.append({
                            "code": f"{key}_out_of_range",
                            "field": key,
                            "detail": f"'{label}' must be at most {max_val}.",
                        })
                except (TypeError, ValueError):
                    errors.append({
                        "code": f"{key}_not_integer",
                        "field": key,
                        "detail": f"'{label}' must be an integer.",
                    })

            # Filepath check
            if field_type == "filepath" and str(value).strip():
                if not Path(str(value).strip()).is_file():
                    errors.append({
                        "code": f"{key}_file_not_found",
                        "field": key,
                        "detail": f"'{label}' path does not exist: {value}",
                    })

        # Scope rules (district vs region) — beyond per-field required flags
        try:
            from services.backpack_host.scope_settings import validate_scope_values

            errors.extend(validate_scope_values(values))
        except Exception:
            pass

        # Write normalized form back into the caller's dict so apply() sees it.
        if not errors:
            prepared = self.normalize_settings_values(values)
            values.clear()
            values.update(prepared)

        return errors

    # ── Apply ──────────────────────────────────────────────────────────────

    def apply(
        self,
        backpack_dir: Path,
        values: dict[str, Any],
        *,
        runtime_root: Path,
    ) -> dict[str, Any]:
        """
        Write validated settings to all paths the connector needs.

        Always writes:
          runtime/{backpack_id}/settings.json  (flat settings for connector)

        Also writes (when values include an HTTP ODS connection):
          runtime/edfi/connections/{connection_id}/local_config.json

        Normalizes scope_mode / LEA / credential_access_tier before write, and
        updates `values` in place so callers keep the canonical form.
        """
        prepared = self.normalize_settings_values(values)
        values.clear()
        values.update(prepared)

        backpack_id = _backpack_id_from_dir(backpack_dir)
        connection_id = str(values.get("connection_id") or "district-main").strip()

        # 1. Flat settings file — connector reads via manifest.local_config_path
        settings_dir = Path(runtime_root) / backpack_id
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_path = settings_dir / "settings.json"
        settings_path.write_text(
            json.dumps(values, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

        result: dict[str, Any] = {
            "ok": True,
            "backpack_id": backpack_id,
            "connection_id": connection_id,
            "settings_path": str(settings_path),
        }

        # 2. data connector ConnectionConfig — for DataConnector service layer (run_self_profile etc.)
        # Triggered by shape: base_url + client_id + client_secret present
        if (
            str(values.get("base_url") or "").strip()
            and str(values.get("client_id") or "").strip()
            and str(values.get("client_secret") or "").strip()
        ):
            try:
                from services.edfi.config import connection_config_from_dict, save_connection_config
                config = connection_config_from_dict(values, connection_id=connection_id)
                saved = save_connection_config(config)
                result["connection_config_path"] = str(saved)
            except ValueError as exc:
                result["ok"] = False
                result["error"] = str(exc)

        return result

    # ── Install steps ──────────────────────────────────────────────────────

    def run_install_step(
        self,
        backpack_dir: Path,
        step: dict[str, Any],
        *,
        values: dict[str, Any],
        runtime_root: Path,
    ) -> dict[str, Any]:
        """Execute a single install_step from settings_schema.json."""
        action = str(step.get("action") or "")
        connection_id = str(values.get("connection_id") or "district-main").strip()

        if action == "validate_settings":
            errors = self.validate(backpack_dir, values)
            return {
                "ok": not errors,
                "action": action,
                "errors": errors,
            }

        if action == "run_self_profile":
            try:
                from services.edfi import run_self_profile
                result = run_self_profile(connection_id=connection_id)
                return {
                    "ok": bool(result.get("ok")),
                    "action": action,
                    "connection_id": connection_id,
                    "health": result.get("health"),
                    "resource_count": (result.get("discovery") or {}).get("resource_count"),
                    "error": result.get("error_code") if not result.get("ok") else None,
                }
            except Exception as exc:
                return {"ok": False, "action": action, "error": str(exc)}

        if action == "verify_district_scope":
            try:
                from services.edfi.inventory import read_preset
                result = read_preset(connection_id, "schools", limit=1, offset=0)
                items = list(result.get("items") or [])
                if not items:
                    return {
                        "ok": False,
                        "action": action,
                        "error": "district_scope_empty",
                        "detail": (
                            "No schools returned for this LEA ID. "
                            "Verify district_lea_id in settings."
                        ),
                    }
                return {
                    "ok": True,
                    "action": action,
                    "connection_id": connection_id,
                    "district_lea_id": str(values.get("district_lea_id") or ""),
                    "schools_found": len(items),
                }
            except Exception as exc:
                return {"ok": False, "action": action, "error": str(exc)}

        return {
            "ok": False,
            "action": action,
            "error": f"unknown_install_step:{action}",
        }

    def run_all_install_steps(
        self,
        backpack_dir: Path,
        values: dict[str, Any],
        *,
        runtime_root: Path,
    ) -> list[dict[str, Any]]:
        """
        Run all install_steps from settings_schema.json in order.

        Stops on first failure and returns results so far.
        """
        schema = _read_schema(backpack_dir)
        steps = sorted(
            [s for s in (schema.get("install_steps") or []) if isinstance(s, dict)],
            key=lambda s: int(s.get("order") or 0),
        )
        results: list[dict[str, Any]] = []
        for step in steps:
            result = self.run_install_step(
                backpack_dir, step, values=values, runtime_root=runtime_root
            )
            results.append({**result, "order": int(step.get("order") or 0)})
            if not result.get("ok"):
                break
        return results
