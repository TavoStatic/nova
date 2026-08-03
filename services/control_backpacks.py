from __future__ import annotations

"""
Control-panel surface for Nova backpacks.

Nova installs first (core only). Backpacks are optional capabilities added later
into a settled environment. This service is the root contract the control panel
and CLI both use — fix behavior here, not in one-off UI hacks.

Ed-Fi (backpacks/edfi) is the reference implementation of backpack.v1.
"""

import json
from pathlib import Path
from typing import Any, Mapping

from services.nova_runtime_context import BASE_DIR, RUNTIME_DIR


class ControlBackpacksService:
    """Discover, install, status, and probe backpacks for the control panel."""

    def __init__(
        self,
        *,
        backpacks_root: Path | None = None,
        runtime_root: Path | None = None,
        nova_root: Path | None = None,
    ) -> None:
        self.backpacks_root = Path(backpacks_root or (BASE_DIR / "backpacks"))
        self.runtime_root = Path(runtime_root or RUNTIME_DIR)
        self.nova_root = Path(nova_root or BASE_DIR)

    def _backpack_dir(self, backpack_id: str) -> Path:
        safe = "".join(
            ch for ch in str(backpack_id or "").strip() if ch.isalnum() or ch in {"_", "-"}
        )
        path = self.backpacks_root / safe
        if not (path / "backpack.json").is_file():
            raise FileNotFoundError(f"backpack_not_found:{safe}")
        return path

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _settings_path(self, backpack_id: str) -> Path:
        return self.runtime_root / backpack_id / "settings.json"

    def _installed(self, backpack_id: str) -> bool:
        settings = self._settings_path(backpack_id)
        if settings.is_file():
            return True
        # Ed-Fi may only have connection config on older installs
        if backpack_id == "edfi":
            conn_root = self.runtime_root / "edfi" / "connections"
            if conn_root.is_dir() and any(conn_root.iterdir()):
                return True
        return False

    def _connection_config_public(self, connection_id: str = "district-main") -> dict[str, Any]:
        """Load Ed-Fi connection config as a settings-shaped dict (includes secret for merge only)."""
        try:
            cid = str(connection_id or "district-main").strip() or "district-main"
            # Prefer this service's runtime_root (tests + multi-root safe).
            path = self.runtime_root / "edfi" / "connections" / cid / "local_config.json"
            data = self._read_json(path)
            if not data:
                return {}
            return {
                "connection_id": str(data.get("connection_id") or cid),
                "base_url": str(data.get("base_url") or ""),
                "client_id": str(data.get("client_id") or ""),
                "client_secret": str(data.get("client_secret") or ""),
                "token_path": str(data.get("token_path") or "/oauth/token"),
                "api_root": str(data.get("api_root") or "/data/v3"),
                "metadata_path": str(data.get("metadata_path") or "/metadata/resources"),
                "timeout_sec": int(data.get("timeout_sec") or 30),
                "verify_ssl": bool(data.get("verify_ssl", True)),
                "ca_bundle_path": str(data.get("ca_bundle_path") or ""),
                "token_auth_mode": str(data.get("token_auth_mode") or "auto"),
                "district_lea_id": str(data.get("district_lea_id") or ""),
                "scope_mode": "single_lea",
                "credential_access_tier": "read",
            }
        except Exception:
            return {}

    def ensure_settings(self, backpack_id: str, *, write: bool = True) -> dict[str, Any]:
        """
        Return backpack settings. For edfi, bootstrap from connection config when
        settings.json is missing so Setup A1/A2 can pass without a manual retype.
        """
        bid = str(backpack_id or "").strip()
        path = self._settings_path(bid)
        existing = self._read_json(path)
        if existing:
            return existing
        if bid != "edfi":
            return {}

        # Prefer district-main; else first connection folder
        conn_id = "district-main"
        conn_root = self.runtime_root / "edfi" / "connections"
        if conn_root.is_dir():
            names = sorted(
                p.name for p in conn_root.iterdir() if p.is_dir() and (p / "local_config.json").is_file()
            )
            if names:
                if "district-main" in names:
                    conn_id = "district-main"
                else:
                    conn_id = names[0]

        boot = self._connection_config_public(conn_id)
        if not boot:
            return {}

        try:
            from services.backpack_host.installer import BackpackInstaller

            boot = BackpackInstaller.normalize_settings_values(boot)
        except Exception:
            pass

        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Persist full settings (secret stays under runtime only; never returned via public API).
            path.write_text(json.dumps(boot, ensure_ascii=True, indent=2), encoding="utf-8")
        return boot

    def _public_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        return {
            k: v
            for k, v in (settings or {}).items()
            if "secret" not in str(k).lower() and "password" not in str(k).lower()
        }

    def _teach_surface(self, backpack_dir: Path) -> dict[str, Any]:
        """Minimum teach rules for Nova (Control B6) — honest pipeline facts only."""
        brief_path = Path(backpack_dir) / "brief.md"
        excerpt = ""
        if brief_path.is_file():
            try:
                lines = brief_path.read_text(encoding="utf-8").splitlines()
                excerpt = "\n".join(lines[:40]).strip()
            except Exception:
                excerpt = ""
        rules = [
            "Prefer local dated data (warehouse/extract) over live ODS for answers.",
            "Never invent LEA, campus, or student facts not present in local hold.",
            "Always treat scope: only this install's LEA (or allowed list).",
            "If data is missing or rate-limited, say so — do not re-hit TEA in a loop.",
            "Partial pages are not the full district unless a full-LEA sync completed.",
            "Setup and control first; dashboards only within declared capabilities later.",
        ]
        return {
            "brief_path": str(brief_path) if brief_path.is_file() else "",
            "brief_excerpt": excerpt,
            "rules": rules,
            "phase": "pipeline",
            "note": "Teach surface for Nova — not a user dashboard.",
        }

    def _enabled_path(self, backpack_id: str) -> Path:
        return self.runtime_root / str(backpack_id or "").strip() / "enabled.json"

    def is_enabled(self, backpack_id: str) -> bool:
        """Default on. Explicit enabled.json can turn a backpack off for queries/reports."""
        path = self._enabled_path(backpack_id)
        if not path.is_file():
            return True
        data = self._read_json(path)
        if "enabled" not in data:
            return True
        return bool(data.get("enabled"))

    def set_enabled(self, backpack_id: str, enabled: bool, *, reason: str = "") -> dict[str, Any]:
        path = self._enabled_path(backpack_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "enabled": bool(enabled),
            "reason": str(reason or "").strip(),
            "updated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {**payload, "path": str(path), "backpack_id": backpack_id}

    def list_backpacks(self) -> list[dict[str, Any]]:
        from services.backpack_host.loader import load_backpack_manifest
        from services.backpack_host.query import backpack_status

        rows: list[dict[str, Any]] = []
        if not self.backpacks_root.is_dir():
            return rows
        for child in sorted(self.backpacks_root.iterdir()):
            if not child.is_dir() or not (child / "backpack.json").is_file():
                continue
            try:
                manifest = load_backpack_manifest(
                    child,
                    nova_root=self.nova_root,
                    runtime_root=self.runtime_root,
                )
            except Exception as exc:
                rows.append(
                    {
                        "backpack_id": child.name,
                        "ok": False,
                        "error": f"manifest_load_failed:{exc}",
                        "installed": False,
                        "enabled": False,
                    }
                )
                continue
            backpack_id = str(manifest.meta.get("backpack_id") or manifest.pipeline_id)
            status: dict[str, Any] = {}
            try:
                status = backpack_status(manifest.pipeline_id)
            except Exception as exc:
                status = {"ok": False, "error": str(exc)}
            rows.append(
                {
                    "backpack_id": backpack_id,
                    "pipeline_id": manifest.pipeline_id,
                    "display_name": manifest.display_name,
                    "version": manifest.version,
                    "description": manifest.description,
                    "protocol_version": str(
                        (manifest.meta or {}).get("protocol_version") or "backpack.v1"
                    ),
                    "read_only": bool(manifest.read_only),
                    "installed": self._installed(backpack_id),
                    "enabled": self.is_enabled(backpack_id),
                    "settings_path": str(self._settings_path(backpack_id)),
                    "status": status,
                    "ok": True,
                }
            )
        return rows

    def payload(self, *, selected_backpack_id: str = "", role: str = "account_admin") -> dict[str, Any]:
        from services.backpack_host.grant_enforcer import operation_summary
        from services.backpack_host.installer import BackpackInstaller
        from services.backpack_host.query import backpack_status

        backpacks = self.list_backpacks()
        # Do not auto-select when empty — UI requires an explicit choice.
        selected = str(selected_backpack_id or "").strip()
        if selected and not any(
            str(b.get("backpack_id") or "") == selected for b in backpacks
        ):
            selected = ""

        detail: dict[str, Any] = {}
        if selected:
            try:
                backpack_dir = self._backpack_dir(selected)
                schema = self._read_json(backpack_dir / "settings_schema.json")
                operations = self._read_json(backpack_dir / "operations.json")
                # Bootstrap settings.json from connection when missing (setup A1/A2).
                settings = self.ensure_settings(selected, write=True)
                public_settings = self._public_settings(settings)
                # Rescan nervous-system fusion when operator opens this backpack.
                fusion: dict[str, Any] = {}
                if selected == "edfi":
                    try:
                        from services.backpack_host.capability_surface import get_fusion_status

                        fusion = get_fusion_status(max_age_sec=60.0, force=False)
                    except Exception as exc:
                        fusion = {"ok": False, "error": str(exc)}
                # Local status only (disk profile) — do NOT live-hit TEA on every panel load.
                status = backpack_status(selected)
                grants = operation_summary(backpack_dir, str(role or "account_admin"))
                from services.backpack_host.reports import list_report_intents

                detail = {
                    "backpack_id": selected,
                    "settings_schema": schema,
                    "operations": operations,
                    "settings_public": public_settings,
                    "settings_path": str(self._settings_path(selected)),
                    "has_client_secret_on_disk": bool(
                        str(settings.get("client_secret") or "").strip()
                    ),
                    "installed": self._installed(selected),
                    "enabled": self.is_enabled(selected),
                    "status": status,
                    "connection_health": {
                        "ok": bool(status.get("auth_ok") or status.get("profile_ok")),
                        "connection_id": status.get("connection_id"),
                        "district_lea_id": status.get("district_lea_id"),
                        "health": status.get("profile_health") or "unknown",
                        "resource_count": status.get("resource_count"),
                        "source": "local_profile",
                        "note": "Live ODS not contacted on panel open. Use Report: health to refresh from TEA.",
                    },
                    "grants": grants,
                    "report_intents": list_report_intents(selected),
                    "teach": self._teach_surface(backpack_dir),
                    "fusion": fusion,
                    "available_capability_ids": list(
                        (fusion or {}).get("available_capability_ids") or []
                    ),
                    "checklist": {
                        "phase": "pipeline",
                        "setup_gate": "setup_settings",
                        "control_gate": "control_settings",
                        "dashboard_gate": "locked_until_setup_and_control",
                        "fusion_ok": bool((fusion or {}).get("ok")),
                    },
                    "install_field_keys": [
                        str(f.get("key") or "")
                        for section in (schema.get("sections") or [])
                        if isinstance(section, dict)
                        for f in (section.get("fields") or [])
                        if isinstance(f, dict) and str(f.get("key") or "").strip()
                    ],
                }
            except Exception as exc:
                detail = {"backpack_id": selected, "error": str(exc)}

        return {
            "ok": True,
            "model": {
                "nova_install_first": True,
                "backpacks_optional_after_settle": True,
                "reference_backpack": "edfi",
                "credentials_never_in_repo": True,
                "note": (
                    "Install Nova core first. Add backpacks later from this panel. "
                    "Client id/secret are entered at backpack install and stored only under runtime/."
                ),
            },
            "backpacks": backpacks,
            "selected_backpack_id": selected,
            "detail": detail,
            "role": str(role or "account_admin"),
        }

    def install(
        self,
        payload: Mapping[str, Any],
        *,
        skip_profile: bool = False,
    ) -> tuple[bool, str, dict[str, Any], str]:
        from services.backpack_host.installer import BackpackInstaller

        backpack_id = str(payload.get("backpack_id") or "").strip()
        values = dict(payload.get("settings") if isinstance(payload.get("settings"), dict) else {})
        if not backpack_id:
            return False, "backpack_id_required", {}, "backpack_id_required"
        if not values:
            return False, "settings_required", {}, "settings_required"

        try:
            backpack_dir = self._backpack_dir(backpack_id)
        except FileNotFoundError as exc:
            return False, str(exc), {}, str(exc)

        # Allow save without re-typing secret when one already exists on disk (control B5).
        if not str(values.get("client_secret") or "").strip():
            prior = self.ensure_settings(backpack_id, write=False)
            if not prior:
                prior = self._connection_config_public(
                    str(values.get("connection_id") or "district-main")
                )
            if str(prior.get("client_secret") or "").strip():
                values["client_secret"] = prior["client_secret"]

        installer = BackpackInstaller()
        errors = installer.validate(backpack_dir, dict(values))
        if errors:
            return (
                False,
                "backpack_validate_failed",
                {"errors": errors},
                "backpack_validate_failed",
            )

        apply_result = installer.apply(
            backpack_dir, dict(values), runtime_root=self.runtime_root
        )
        if not apply_result.get("ok"):
            return (
                False,
                "backpack_apply_failed",
                {"apply": apply_result},
                "backpack_apply_failed",
            )

        def _fusion_after_change() -> dict[str, Any]:
            if backpack_id != "edfi":
                return {}
            try:
                from services.backpack_host.capability_surface import scan_backpack_fusion

                return scan_backpack_fusion("edfi", persist=True)
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        if skip_profile or bool(payload.get("skip_profile")):
            return (
                True,
                "backpack_settings_saved",
                {
                    "apply": apply_result,
                    "steps": [],
                    "skip_profile": True,
                    "fusion": _fusion_after_change(),
                },
                "backpack_settings_saved",
            )

        steps = installer.run_all_install_steps(
            backpack_dir, dict(values), runtime_root=self.runtime_root
        )
        ok = all(bool(s.get("ok")) for s in steps) if steps else True
        return (
            ok,
            "backpack_install_ok" if ok else "backpack_install_failed",
            {
                "apply": apply_result,
                "steps": steps,
                "fusion": _fusion_after_change(),
            },
            "backpack_install_ok" if ok else "backpack_install_failed",
        )

    def probe_lea(
        self, payload: Mapping[str, Any]
    ) -> tuple[bool, str, dict[str, Any], str]:
        from services.backpack_host.query import run_backpack_query
        from services.backpack_host.scope_settings import format_lea_id, lea_identity_key
        from services.nova_shell.http_trust import resolve_control_panel_role

        backpack_id = str(payload.get("backpack_id") or "edfi").strip() or "edfi"
        lea = str(payload.get("lea") or payload.get("district_lea_id") or "").strip()
        role = resolve_control_panel_role(
            str(payload.get("role") or ""),
            control_authenticated=True,
            for_privileged_action=True,
        )
        limit = int(payload.get("limit") or 3)
        if not lea:
            return False, "lea_required", {}, "lea_required"

        result = run_backpack_query(
            backpack_id,
            "list_schools",
            {"district_lea_id": lea},
            row_limit=max(1, min(limit, 10)),
            role=role,
        )
        items = list(result.get("items") or result.get("rows") or [])
        key = lea_identity_key(lea)
        extra = {
            "ok": bool(result.get("ok")),
            "backpack_id": backpack_id,
            "requested_lea": lea,
            "normalized_lea": format_lea_id(lea) if key is not None else lea,
            "school_items": len(items),
            "error": result.get("error") or result.get("error_code"),
            "result": result,
        }
        ok = bool(result.get("ok")) and len(items) > 0
        return (
            ok,
            "backpack_probe_lea_ok" if ok else "backpack_probe_lea_failed",
            extra,
            "backpack_probe_lea_ok" if ok else "backpack_probe_lea_failed",
        )

    def report(
        self, payload: Mapping[str, Any]
    ) -> tuple[bool, str, dict[str, Any], str]:
        """User-request report path (e.g. intent=schools) → shaped rows for dashboard/table."""
        from services.backpack_host.reports import list_report_intents, run_backpack_report
        from services.nova_shell.http_trust import resolve_control_panel_role

        backpack_id = str(payload.get("backpack_id") or "edfi").strip() or "edfi"
        intent = str(payload.get("intent") or payload.get("report") or "schools").strip()
        # Control panel actions are control-auth gated; do not honor client role elevation.
        role = resolve_control_panel_role(
            str(payload.get("role") or ""),
            control_authenticated=True,
            for_privileged_action=True,
        )
        lea = str(payload.get("lea") or payload.get("district_lea_id") or "").strip()
        # Display/page limit. Schools force_refresh uses full_lea (dynamic LEA size) server-side.
        try:
            limit = int(payload.get("limit") or 50)
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 2000))

        if intent in {"list", "intents", "help"}:
            return (
                True,
                "backpack_report_intents",
                {"intents": list_report_intents(backpack_id)},
                "backpack_report_intents",
            )

        force_refresh = bool(payload.get("force_refresh") or payload.get("refresh"))
        prefer_local = payload.get("prefer_local")
        if prefer_local is None:
            prefer_local = not force_refresh
        else:
            prefer_local = bool(prefer_local)

        report = run_backpack_report(
            intent,
            backpack_id=backpack_id,
            role=role,
            lea=lea,
            limit=limit,
            force_refresh=force_refresh,
            prefer_local=prefer_local,
        )
        # HTTP action always succeeds so the panel can render structured errors
        # (rate limit, grants). Do NOT put report["ok"] at the top level — the
        # control route merges extras and would flip body.ok false and throw in UI.
        ok = bool(report.get("ok"))
        extra = {
            "report_ok": ok,
            "report": report,
            "summary": report.get("summary") or "",
            "columns": report.get("columns") or [],
            "rows": report.get("rows") or [],
            "row_count": report.get("row_count") or 0,
            "error": report.get("error") or "",
            "rate_limited": bool(report.get("rate_limited")),
            "from_extract": bool(report.get("from_extract")),
            "live_pull": bool(report.get("live_pull")),
            "synced_at": report.get("synced_at") or "",
            "intent": report.get("intent") or intent,
            "label": report.get("label") or "",
        }
        return (
            True,
            "backpack_report_ok" if ok else "backpack_report_failed",
            extra,
            "backpack_report_ok" if ok else "backpack_report_failed",
        )

    def handle_action(
        self, action: str, payload: Mapping[str, Any]
    ) -> tuple[bool, str, dict[str, Any]]:
        act = str(action or "").strip()
        body = dict(payload or {})
        if act == "backpack_install":
            ok, msg, extra, _ = self.install(body)
            return ok, msg, extra
        if act == "backpack_settings_save":
            body = {**body, "skip_profile": True}
            ok, msg, extra, _ = self.install(body, skip_profile=True)
            return ok, msg, extra
        if act == "backpack_probe_lea":
            ok, msg, extra, _ = self.probe_lea(body)
            return ok, msg, extra
        if act == "backpack_report":
            ok, msg, extra, _ = self.report(body)
            return ok, msg, extra
        if act == "backpack_set_enabled":
            backpack_id = str(body.get("backpack_id") or "").strip()
            if not backpack_id:
                return False, "backpack_id_required", {}
            enabled = body.get("enabled")
            if isinstance(enabled, str):
                enabled = enabled.strip().lower() in {"1", "true", "yes", "on"}
            else:
                enabled = bool(enabled)
            try:
                self._backpack_dir(backpack_id)
            except FileNotFoundError as exc:
                return False, str(exc), {}
            extra = self.set_enabled(
                backpack_id,
                enabled,
                reason=str(body.get("reason") or ""),
            )
            return True, "backpack_enabled" if enabled else "backpack_disabled", extra
        if act == "backpack_refresh":
            role = str(body.get("role") or "account_admin")
            selected = str(body.get("backpack_id") or "")
            return True, "backpack_refresh_ok", self.payload(
                selected_backpack_id=selected, role=role
            )
        return False, f"unknown_backpack_action:{act}", {}


CONTROL_BACKPACKS_SERVICE = ControlBackpacksService()
