from __future__ import annotations

"""
Control-panel surface for Nova backpacks.

Nova installs first (core only). Backpacks are optional capabilities added later
into a settled environment. This service is the root contract the control panel
and CLI both use — fix behavior here, not in one-off UI hacks.
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
        from services.backpack_host.install_state import backpack_runtime_installed

        return backpack_runtime_installed(backpack_id, runtime_root=self.runtime_root)

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
            "Prefer local dated data over live source queries for answers.",
            "Never invent facts not present in the local hold.",
            "Always respect the configured scope of this install.",
            "If data is missing or rate-limited, say so — do not re-query in a loop.",
            "Partial pages are not the full dataset unless a full sync completed.",
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
        """Installed backpacks default on. Uninstalled / never-installed backpacks are off."""
        if not self._installed(backpack_id):
            return False
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
                    "residue": {},
                }
            )
        from services.backpack_host.sanitize import scan_backpack_residue

        for row in rows:
            try:
                row["residue"] = scan_backpack_residue(
                    str(row.get("backpack_id") or ""),
                    runtime_root=self.runtime_root,
                    backpacks_root=self.backpacks_root,
                )
            except Exception as exc:
                row["residue"] = {"ok": False, "error": str(exc)[:200]}
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
                fusion: dict[str, Any] = {}
                # Local status only (disk profile) — do NOT live-hit the source on every panel load.
                status = backpack_status(selected)
                grants = operation_summary(backpack_dir, str(role or "account_admin"))

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
                        "health": status.get("profile_health") or "unknown",
                        "resource_count": status.get("resource_count"),
                        "source": "local_profile",
                        "note": "Live source not contacted on panel open.",
                    },
                    "grants": grants,
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
                "reference_backpack": "",
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
        # The act of saving settings must remain traceable to a Nova user.
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
        if apply_result.get("ok"):
            try:
                from services.backpack_host.install_state import clear_backpack_uninstall_mark

                clear_backpack_uninstall_mark(backpack_id, runtime_root=self.runtime_root)
            except Exception:
                pass
        if not apply_result.get("ok"):
            return (
                False,
                "backpack_apply_failed",
                {"apply": apply_result},
                "backpack_apply_failed",
            )

        def _fusion_after_change() -> dict[str, Any]:
            return {}

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

    def uninstall(
        self, payload: Mapping[str, Any]
    ) -> tuple[bool, str, dict[str, Any], str]:
        """
        Uninstall a backpack and sanitize every declared Nova surface it touched.

        Package files under backpacks/{id}/ stay. Runtime install residue and the
        fusion cache, pipeline workers, and work-tree signals listed in
        backpack_host.sanitize.BACKPACK_TOUCH_POINTS are cleaned so the rest of
        Nova does not keep treating a deleted install as a live gap.
        """
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
            or "primary"
        ).strip() or "primary"

        removed: list[str] = []
        errors: list[str] = []

        uninstalled_at = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())
        from services.backpack_host.sanitize import sanitize_uninstalled_backpack

        sanitized = sanitize_uninstalled_backpack(
            backpack_id,
            runtime_root=self.runtime_root,
            connection_id=connection_id,
            nova_user=nova_user,
            uninstalled_at=uninstalled_at,
            backpacks_root=self.backpacks_root,
        )
        removed.extend(list(sanitized.get("removed") or []))
        errors.extend(list(sanitized.get("errors") or []))

        ok = not errors
        extra = {
            "ok": ok,
            "backpack_id": backpack_id,
            "connection_id": connection_id,
            "uninstalled_by": nova_user,
            "uninstalled_at": uninstalled_at,
            "removed": removed,
            "errors": errors,
            "touch_points": dict(sanitized.get("touch_points") or {}),
            "work_tree": list(sanitized.get("work_tree") or []),
            "residue": dict(sanitized.get("residue") or {}),
            "note": (
                "Backpack code is unchanged. Runtime residue and the Nova surfaces "
                "that backpack wrote into were sanitized so the rest of Nova goes quiet."
            ),
        }
        return (
            ok,
            "backpack_uninstall_ok" if ok else "backpack_uninstall_partial",
            extra,
            "backpack_uninstall_ok" if ok else "backpack_uninstall_partial",
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
        if act == "backpack_install":
            ok, msg, extra, _ = self.install(body)
            return ok, msg, extra
        if act == "backpack_settings_save":
            body = {**body, "skip_profile": True}
            ok, msg, extra, _ = self.install(body, skip_profile=True)
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
