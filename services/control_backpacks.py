from __future__ import annotations

"""
Control-panel surface for Nova backpacks.

Nova installs first (core only). Backpacks are optional capabilities added later
into a settled environment. This service is the root contract the control panel
and CLI both use — fix behavior here, not in one-off UI hacks.

data connector (backpacks/edfi) is the reference implementation of backpack.v1.
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
        return self._settings_path(backpack_id).is_file()

    def ensure_settings(self, backpack_id: str, *, write: bool = True) -> dict[str, Any]:
        """Return saved settings for a backpack, or empty dict if not installed."""
        bid = str(backpack_id or "").strip()
        path = self._settings_path(bid)
        existing = self._read_json(path)
        if existing:
            return existing
        return {}

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

    # ── Backpack sniffer / auto-discovery ────────────────────────────────────

    _REQUIRED_FILES = {
        "backpack_json": "backpack.json",
        "connector": "connector.py",
        "operations": "operations.json",
        "settings_schema": "settings_schema.json",
    }

    _SUPPORTED_PROTOCOLS = {"backpack.v1"}

    def _handshake(self, bp_dir: Path, backpack_id: str) -> dict[str, Any]:
        """
        Validate a newly-dropped backpack folder.

        Checks that all required files are present, backpack.json parses
        correctly, and the protocol_version is one Nova supports. Returns
        a handshake dict consumed by the discovery log and the control panel.

        ok=False means the backpack is bad or incompatible and should NOT
        be installed.
        """
        checks = {
            key: (bp_dir / fname).is_file()
            for key, fname in self._REQUIRED_FILES.items()
        }
        missing = [
            fname
            for key, fname in self._REQUIRED_FILES.items()
            if not checks[key]
        ]

        display_name = backpack_id
        version = "?"
        protocol_version = "unknown"
        manifest_ok = False
        incompatible = False
        reason = ""

        try:
            manifest_data = json.loads(
                (bp_dir / "backpack.json").read_text(encoding="utf-8")
            )
            manifest_ok = True
            display_name = str(
                manifest_data.get("name")
                or manifest_data.get("display_name")
                or backpack_id
            )
            version = str(manifest_data.get("version") or "?")
            protocol_version = str(
                manifest_data.get("protocol_version") or "backpack.v1"
            )
            if protocol_version not in self._SUPPORTED_PROTOCOLS:
                incompatible = True
                reason = (
                    f"Protocol '{protocol_version}' is not supported by this Nova. "
                    f"Supported: {', '.join(sorted(self._SUPPORTED_PROTOCOLS))}."
                )
        except Exception as exc:
            reason = f"backpack.json unreadable: {exc}"

        files_ok = not missing
        ok = files_ok and manifest_ok and not incompatible

        if not ok and not reason:
            reason = f"Missing required files: {', '.join(missing)}"

        return {
            "ok": ok,
            "backpack_id": backpack_id,
            "display_name": display_name,
            "version": version,
            "protocol_version": protocol_version,
            "home": str(bp_dir),
            "checks": checks,
            "missing": missing,
            "incompatible": incompatible,
            "reason": reason,
            "message": (
                f"Handshake OK — '{display_name}' v{version} found its home at {bp_dir.name}/"
                if ok
                else f"Bad backpack — {reason}"
            ),
        }

    def sniff_new_backpacks(self) -> list[dict[str, Any]]:
        """
        Scan backpacks/ for directories that weren't there before.

        Compares current directory listing against
        runtime/backpacks/known.json. Any new directories get a
        _handshake() validation and are written to
        runtime/backpacks/discovery_log.jsonl. The known registry is
        updated so subsequent calls don't re-alert.

        Returns a list of handshake dicts for newly-found backpacks
        (empty list when nothing is new).
        """
        import time as _time

        known_path = self.runtime_root / "backpacks" / "known.json"
        log_path = self.runtime_root / "backpacks" / "discovery_log.jsonl"

        # Load previously-known IDs.
        known_ids: set[str] = set()
        try:
            if known_path.exists():
                known_ids = set(json.loads(known_path.read_text(encoding="utf-8")))
        except Exception:
            known_ids = set()

        # Discover current backpack directories.
        current: dict[str, Path] = {}
        if self.backpacks_root.is_dir():
            for child in self.backpacks_root.iterdir():
                if child.is_dir() and (child / "backpack.json").is_file():
                    current[child.name] = child

        current_ids = set(current)
        new_ids = current_ids - known_ids

        newly_found: list[dict[str, Any]] = []
        for bid in sorted(new_ids):
            handshake = self._handshake(current[bid], bid)
            entry = {
                "discovered_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                **handshake,
            }
            newly_found.append(entry)
            # Append to discovery log.
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")
            except Exception:
                pass

        # Update known registry (include all current — even invalid — so we
        # don't keep re-alerting about broken folders).
        if new_ids:
            try:
                known_path.parent.mkdir(parents=True, exist_ok=True)
                known_path.write_text(
                    json.dumps(sorted(current_ids), ensure_ascii=True),
                    encoding="utf-8",
                )
            except Exception:
                pass

        return newly_found

    def payload(self, *, selected_backpack_id: str = "", role: str = "account_admin") -> dict[str, Any]:
        from services.backpack_host.grant_enforcer import operation_summary
        from services.backpack_host.installer import BackpackInstaller
        from services.backpack_host.query import backpack_status

        # Sniff for newly-dropped backpacks on every payload request.
        # Lightweight (directory scan only); results go to discovery_log.jsonl.
        newly_found = self.sniff_new_backpacks()

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
            "newly_found": newly_found,
        }

    def install(
        self,
        payload: Mapping[str, Any],
        *,
        skip_profile: bool = False,
    ) -> tuple[bool, str, dict[str, Any], str]:
        import time as _time
        from services.backpack_host.installer import BackpackInstaller

        backpack_id = str(payload.get("backpack_id") or "").strip()
        values = dict(payload.get("settings") if isinstance(payload.get("settings"), dict) else {})
        if not backpack_id:
            return False, "backpack_id_required", {}, "backpack_id_required"
        if not values:
            return False, "settings_required", {}, "settings_required"

        # Stamp which Nova Shell user is configuring the backpack.
        # The key/secret are ODS (system) credentials, not user credentials,
        # but the act of saving them must be traceable to a Nova user.
        nova_user = str(payload.get("nova_user") or payload.get("user") or "").strip()
        if nova_user:
            values["configured_by"] = nova_user
            values["last_configured_at"] = _time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", _time.gmtime()
            )

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

    def uninstall(
        self, payload: Mapping[str, Any]
    ) -> tuple[bool, str, dict[str, Any], str]:
        """
        Remove all runtime residue for a backpack.

        For data connector this means:
          runtime/edfi/settings.json
          runtime/edfi/connections/{connection_id}/local_config.json
          runtime/edfi/warehouse/{connection_id}.sqlite3
          runtime/edfi/profiles/{connection_id}.json
          runtime/edfi/enabled.json
          runtime/backpacks/capability_scan.json

        The backpack code under backpacks/edfi/ is NOT touched — it is part of
        the Nova source tree, not install residue. Only runtime/ files are removed.

        The requesting Nova Shell user is required in payload["nova_user"].
        """
        import shutil
        import time as _time

        backpack_id = str(payload.get("backpack_id") or "").strip()
        if not backpack_id:
            return False, "backpack_id_required", {}, "backpack_id_required"

        nova_user = str(payload.get("nova_user") or payload.get("user") or "").strip() or "operator"

        # Resolve connection_id from saved settings before we delete anything.
        saved = self.ensure_settings(backpack_id, write=False)
        connection_id = str(
            saved.get("connection_id")
            or payload.get("connection_id")
            or "district-main"
        ).strip() or "district-main"

        # Block uninstall if a warehouse sync is actively running.
        # The lock file is written by run_full_sync() and removed in its finally block.
        # Removing the warehouse SQLite mid-sync would corrupt the database.
        _sync_lock = self.runtime_root / backpack_id / "warehouse_sync.lock"
        if _sync_lock.exists():
            return False, "sync_in_progress", {
                "hint": (
                    "A warehouse sync is currently running. "
                    "Wait for it to complete before uninstalling."
                ),
                "lock_file": str(_sync_lock),
            }, "sync_in_progress"

        removed: list[str] = []
        errors: list[str] = []

        def _rm(path: Path) -> None:
            try:
                if path.is_file():
                    path.unlink()
                    removed.append(str(path))
                elif path.is_dir():
                    shutil.rmtree(path)
                    removed.append(str(path))
            except Exception as exc:
                errors.append(f"{path}: {exc}")

        rt = self.runtime_root

        # 1. Nuke the entire backpack runtime directory (catches all residue:
        #    settings, connections, warehouse, profiles, cursors, extracts, audit logs, etc.)
        backpack_runtime_dir = rt / backpack_id
        if backpack_runtime_dir.is_dir():
            try:
                shutil.rmtree(backpack_runtime_dir)
                removed.append(str(backpack_runtime_dir))
            except Exception as exc:
                errors.append(f"{backpack_runtime_dir}: {exc}")

        # 2. capability scan (Nova's nervous-system fusion cache — outside backpack dir)
        _rm(rt / "backpacks" / "capability_scan.json")

        ok = not errors
        extra = {
            "ok": ok,
            "backpack_id": backpack_id,
            "connection_id": connection_id,
            "uninstalled_by": nova_user,
            "uninstalled_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            "removed": removed,
            "errors": errors,
            "note": (
                "Backpack code (backpacks/edfi/) is unchanged — only runtime/ residue was removed. "
                "Re-enter credentials and run Install + profile to reinstall."
            ),
        }
        return (
            ok,
            "backpack_uninstall_ok" if ok else "backpack_uninstall_partial",
            extra,
            "backpack_uninstall_ok" if ok else "backpack_uninstall_partial",
        )

    def probe_credentials(
        self, payload: Mapping[str, Any]
    ) -> tuple[bool, str, dict[str, Any], str]:
        """
        Test ODS credentials without writing anything to disk.

        Accepts either explicit fields (base_url, client_id, client_secret) or
        falls back to what is already saved under runtime/ for the given
        backpack_id/connection_id.  The requesting Nova Shell user must be
        supplied in payload["nova_user"] for audit purposes — the probe result
        records who performed the test but saves nothing itself.
        """
        from services.edfi.auth_probe import probe_auth

        backpack_id = str(payload.get("backpack_id") or "edfi").strip() or "edfi"
        nova_user = str(payload.get("nova_user") or payload.get("user") or "").strip()

        # Resolve credential fields: prefer explicit form values, fall back to disk.
        base_url = str(payload.get("base_url") or "").strip()
        client_id = str(payload.get("client_id") or "").strip()
        client_secret = str(payload.get("client_secret") or "").strip()

        if not base_url or not client_id or not client_secret:
            # Fall back to what is already on disk for this backpack.
            saved = self.ensure_settings(backpack_id, write=False)
            if not saved:
                conn_id = str(payload.get("connection_id") or "district-main").strip()
                saved = self._connection_config_public(conn_id)
            base_url = base_url or str(saved.get("base_url") or "").strip()
            client_id = client_id or str(saved.get("client_id") or "").strip()
            client_secret = client_secret or str(saved.get("client_secret") or "").strip()

        # Advanced overrides (optional).
        token_path = str(payload.get("token_path") or "/oauth/token").strip() or "/oauth/token"
        verify_ssl = payload.get("verify_ssl")
        if verify_ssl is None:
            verify_ssl = True
        else:
            verify_ssl = bool(verify_ssl)
        ca_bundle_path = str(payload.get("ca_bundle_path") or "").strip()
        timeout_sec = int(payload.get("timeout_sec") or 15)

        result = probe_auth(
            base_url=base_url,
            client_id=client_id,
            client_secret=client_secret,
            token_path=token_path,
            timeout_sec=min(timeout_sec, 30),
            verify_ssl=verify_ssl,
            ca_bundle_path=ca_bundle_path,
        )

        ok = bool(result.get("ok"))
        extra = {
            "ok": ok,
            "backpack_id": backpack_id,
            "base_url": base_url,
            "client_id": client_id,
            "latency_ms": result.get("latency_ms", 0),
            "token_type": result.get("token_type", ""),
            "error": result.get("error", ""),
            "error_code": result.get("error_code", ""),
            "hint": result.get("hint", ""),
            "tested_by": nova_user,
        }
        return (
            ok,
            "backpack_probe_credentials_ok" if ok else "backpack_probe_credentials_failed",
            extra,
            "backpack_probe_credentials_ok" if ok else "backpack_probe_credentials_failed",
        )

    def handle_action(
        self, action: str, payload: Mapping[str, Any]
    ) -> tuple[bool, str, dict[str, Any]]:
        act = str(action or "").strip()
        body = dict(payload or {})
        if act == "backpack_sniff":
            found = self.sniff_new_backpacks()
            good = [f for f in found if f.get("ok")]
            bad  = [f for f in found if not f.get("ok")]
            return True, "sniff_complete", {
                "ok": True,
                "newly_found": found,
                "good_count": len(good),
                "bad_count": len(bad),
                "bad": bad,
                "message": (
                    f"Found {len(good)} new backpack(s)."
                    + (f" {len(bad)} bad/incompatible: {[b['backpack_id'] for b in bad]}" if bad else "")
                ) if found else "No new backpacks found.",
            }
        if act == "backpack_uninstall":
            ok, msg, extra, _ = self.uninstall(body)
            return ok, msg, extra
        if act == "backpack_probe_credentials":
            ok, msg, extra, _ = self.probe_credentials(body)
            return ok, msg, extra
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
