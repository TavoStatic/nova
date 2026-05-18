from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from services.nova_runtime_context import BASE_DIR, OS_CAPABILITY_REGISTRY_FILE


OPERATOR_OUTBOX_REASONS = {
    "missing_capability",
    "contract_stale",
    "invalid_args",
    "authority_blocked",
}
SUPPORTED_SCRIPT_KINDS = {"powershell"}
REQUIRED_CAPABILITY_FIELDS = {
    "name",
    "contract_version",
    "status",
    "authority_level",
    "mutating",
    "locality",
    "script",
    "arg_schema",
    "evidence_schema_version",
}
REQUIRED_SCRIPT_FIELDS = {"kind", "path", "sha256", "timeout_ms", "working_directory"}


def _safe_text(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[: max(1, int(limit or 1))]


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class OsCapabilityRegistryService:
    """Loads and verifies OS capability contracts without executing scripts."""

    def load_registry(
        self,
        path: Path | None = None,
        *,
        base_dir: Path | None = None,
    ) -> dict[str, Any]:
        registry_path = Path(path or OS_CAPABILITY_REGISTRY_FILE)
        root = Path(base_dir or BASE_DIR).resolve()
        if not registry_path.exists():
            return {
                "ok": False,
                "reason": "registry_missing",
                "operator_outbox": False,
                "path": str(registry_path),
                "capabilities": {},
                "errors": [f"registry_missing:{registry_path}"],
            }

        try:
            raw = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "ok": False,
                "reason": "registry_unreadable",
                "operator_outbox": False,
                "path": str(registry_path),
                "capabilities": {},
                "errors": [f"registry_unreadable:{exc}"],
            }

        if not isinstance(raw, dict):
            return {
                "ok": False,
                "reason": "invalid_registry",
                "operator_outbox": False,
                "path": str(registry_path),
                "capabilities": {},
                "errors": ["registry_root_must_be_object"],
            }

        capability_rows = raw.get("capabilities")
        if isinstance(capability_rows, dict):
            iterable = list(capability_rows.values())
        elif isinstance(capability_rows, list):
            iterable = capability_rows
        else:
            iterable = []

        default_outbox = {
            _safe_text(item, 80)
            for item in _safe_list(raw.get("default_operator_outbox_on"))
            if _safe_text(item, 80)
        } or set(OPERATOR_OUTBOX_REASONS)

        capabilities: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        for index, item in enumerate(iterable):
            normalized = self._normalize_capability(
                item,
                base_dir=root,
                default_outbox=default_outbox,
                index=index,
            )
            name = _safe_text(normalized.get("name"), 120) or f"capability_{index}"
            if name in capabilities:
                errors.append(f"duplicate_capability:{name}")
                normalized["status"] = "invalid_contract"
                normalized["executable"] = False
                normalized.setdefault("errors", []).append("duplicate_capability")
            capabilities[name] = normalized
            errors.extend(_safe_list(normalized.get("errors")))

        return {
            "ok": not any(
                str(row.get("status") or "") == "invalid_contract"
                for row in capabilities.values()
            ),
            "reason": "" if capabilities or not errors else "invalid_registry",
            "operator_outbox": False,
            "path": str(registry_path),
            "schema_version": _safe_text(raw.get("schema_version"), 40),
            "registry_version": _safe_text(raw.get("registry_version"), 40),
            "default_operator_outbox_on": sorted(default_outbox),
            "capabilities": capabilities,
            "errors": errors,
        }

    def resolve_capability(
        self,
        name: str,
        path: Path | None = None,
        *,
        base_dir: Path | None = None,
    ) -> dict[str, Any]:
        registry = self.load_registry(path, base_dir=base_dir)
        capability_name = _safe_text(name, 120)
        if not registry.get("ok") and not registry.get("capabilities"):
            return registry
        capability = _safe_dict(_safe_dict(registry.get("capabilities")).get(capability_name))
        if not capability:
            return self._blocked_result(
                "missing_capability",
                f"missing_capability:{capability_name}",
                registry=registry,
            )
        return {
            "ok": bool(capability.get("executable")),
            "reason": "" if capability.get("executable") else "contract_stale",
            "operator_outbox": self._should_outbox(capability, "contract_stale")
            if not capability.get("executable")
            else False,
            "capability": capability,
            "registry": registry,
            "errors": _safe_list(capability.get("errors")),
        }

    def validate_args(
        self,
        capability: dict[str, Any],
        args: dict[str, Any] | None,
    ) -> dict[str, Any]:
        clean_capability = _safe_dict(capability)
        schema = _safe_dict(clean_capability.get("arg_schema"))
        normalized_args = dict(args or {})
        errors: list[str] = []

        if schema.get("type") != "object":
            errors.append("arg_schema_type_must_be_object")
            return self._invalid_args_result(clean_capability, normalized_args, errors)

        properties = _safe_dict(schema.get("properties"))
        required = {
            _safe_text(item, 120)
            for item in _safe_list(schema.get("required"))
            if _safe_text(item, 120)
        }

        if schema.get("additionalProperties") is False:
            unknown = sorted(set(normalized_args) - set(properties))
            errors.extend(f"unknown_arg:{key}" for key in unknown)

        for key, spec in properties.items():
            clean_key = _safe_text(key, 120)
            if clean_key not in normalized_args and isinstance(spec, dict) and "default" in spec:
                normalized_args[clean_key] = copy.deepcopy(spec.get("default"))

        missing = sorted(key for key in required if key not in normalized_args)
        errors.extend(f"missing_arg:{key}" for key in missing)

        for key, value in list(normalized_args.items()):
            spec = _safe_dict(properties.get(key))
            if not spec:
                continue
            errors.extend(self._validate_value(key, value, spec))

        errors.extend(self._validate_contract_bounds(clean_capability, normalized_args))
        if errors:
            return self._invalid_args_result(clean_capability, normalized_args, errors)
        return {
            "ok": True,
            "reason": "",
            "operator_outbox": False,
            "args": normalized_args,
            "errors": [],
        }

    def prepare_request(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        path: Path | None = None,
        *,
        base_dir: Path | None = None,
    ) -> dict[str, Any]:
        resolved = self.resolve_capability(name, path, base_dir=base_dir)
        if not resolved.get("ok"):
            return resolved
        capability = _safe_dict(resolved.get("capability"))

        execution_hash = self.verify_capability_hash(capability)
        if not execution_hash.get("ok"):
            result = self._blocked_result(
                "contract_stale",
                _safe_text(execution_hash.get("reason"), 180) or "contract_stale",
                registry=resolved.get("registry"),
                capability=capability,
                errors=_safe_list(execution_hash.get("errors")),
            )
            result["execution_hash"] = execution_hash
            return result

        arg_result = self.validate_args(capability, args)
        if not arg_result.get("ok"):
            return {
                "ok": False,
                "reason": "invalid_args",
                "operator_outbox": True,
                "capability": capability,
                "registry": resolved.get("registry"),
                "args": arg_result.get("args", {}),
                "errors": _safe_list(arg_result.get("errors")),
            }

        return {
            "ok": True,
            "reason": "",
            "operator_outbox": False,
            "capability": capability,
            "registry": resolved.get("registry"),
            "args": arg_result.get("args", {}),
            "execution_hash": execution_hash,
            "evidence_schema_enforced": bool(capability.get("evidence_schema")),
        }

    def verify_capability_hash(self, capability: dict[str, Any]) -> dict[str, Any]:
        clean_capability = _safe_dict(capability)
        script = _safe_dict(clean_capability.get("script"))
        expected = _safe_text(script.get("sha256"), 128).lower()
        script_path = Path(_safe_text(script.get("resolved_path"), 1000))
        if not expected:
            return {
                "ok": False,
                "reason": "contract_stale:empty_sha256",
                "errors": ["empty_sha256"],
            }
        if not script_path.exists() or not script_path.is_file():
            return {
                "ok": False,
                "reason": "contract_stale:script_missing",
                "errors": [f"script_missing:{script_path}"],
            }
        try:
            actual = _sha256_file(script_path)
        except Exception as exc:
            return {
                "ok": False,
                "reason": "contract_stale:hash_failed",
                "errors": [f"hash_failed:{exc}"],
            }
        if actual != expected:
            return {
                "ok": False,
                "reason": "contract_stale:sha256_mismatch",
                "expected_sha256": expected,
                "actual_sha256": actual,
                "errors": ["sha256_mismatch"],
            }
        return {
            "ok": True,
            "reason": "",
            "sha256": actual,
            "errors": [],
        }

    def _normalize_capability(
        self,
        item: Any,
        *,
        base_dir: Path,
        default_outbox: set[str],
        index: int,
    ) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {
                "name": f"capability_{index}",
                "status": "invalid_contract",
                "executable": False,
                "errors": ["capability_must_be_object"],
                "operator_outbox_on": sorted(default_outbox),
            }

        raw = dict(item)
        errors: list[str] = []
        for field in sorted(REQUIRED_CAPABILITY_FIELDS):
            if field not in raw:
                errors.append(f"missing_contract_field:{field}")

        name = _safe_text(raw.get("name"), 120)
        if not name:
            errors.append("name_required")
        if not isinstance(raw.get("mutating"), bool):
            errors.append("mutating_must_be_boolean")
        if not _safe_text(raw.get("contract_version"), 40):
            errors.append("contract_version_required")
        if not _safe_text(raw.get("authority_level"), 80):
            errors.append("authority_level_required")
        if not _safe_text(raw.get("locality"), 80):
            errors.append("locality_required")
        if not _safe_text(raw.get("evidence_schema_version"), 40):
            errors.append("evidence_schema_version_required")

        script = _safe_dict(raw.get("script"))
        for field in sorted(REQUIRED_SCRIPT_FIELDS):
            if field not in script:
                errors.append(f"missing_script_field:{field}")
        script_kind = _safe_text(script.get("kind"), 80).lower()
        if script_kind not in SUPPORTED_SCRIPT_KINDS:
            errors.append(f"unsupported_script_kind:{script_kind or 'missing'}")
        timeout_ms = script.get("timeout_ms")
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
            errors.append("script_timeout_ms_must_be_positive_integer")
        if not _safe_text(script.get("working_directory"), 500):
            errors.append("script_working_directory_required")

        script_path_text = _safe_text(script.get("path"), 1000)
        if not script_path_text:
            errors.append("script_path_required")
            resolved_path = base_dir
        else:
            raw_path = Path(script_path_text)
            resolved_path = (raw_path if raw_path.is_absolute() else base_dir / raw_path).resolve()
            if not _is_relative_to(resolved_path, base_dir):
                errors.append(f"script_path_outside_base:{script_path_text}")

        declared_status = _safe_text(raw.get("status"), 80).lower() or "draft"
        expected_hash = _safe_text(script.get("sha256"), 128).lower()
        hash_result: dict[str, Any] = {"ok": False, "reason": "not_checked", "errors": []}

        if declared_status == "draft" or not expected_hash:
            status = "draft"
            executable = False
        elif declared_status != "active":
            status = "invalid_contract"
            executable = False
            errors.append(f"invalid_status:{declared_status}")
        else:
            hash_probe = {
                "script": {
                    **script,
                    "resolved_path": str(resolved_path),
                    "sha256": expected_hash,
                }
            }
            hash_result = self.verify_capability_hash(hash_probe)
            if hash_result.get("ok"):
                status = "active"
                executable = True
            else:
                status = "contract_stale"
                executable = False
                errors.extend(_safe_list(hash_result.get("errors")))

        if errors and status not in {"draft", "contract_stale"}:
            status = "invalid_contract"
            executable = False

        operator_outbox_on = {
            _safe_text(row, 80)
            for row in _safe_list(raw.get("operator_outbox_on"))
            if _safe_text(row, 80)
        } or set(default_outbox)
        arg_schema = _safe_dict(raw.get("arg_schema"))
        if not arg_schema:
            status = "invalid_contract"
            executable = False
            errors.append("arg_schema_required")
        elif arg_schema.get("type") != "object":
            status = "invalid_contract"
            executable = False
            errors.append("arg_schema_type_must_be_object")
        elif arg_schema.get("additionalProperties") is not False:
            status = "invalid_contract"
            executable = False
            errors.append("arg_schema_additional_properties_must_be_false")
        elif not isinstance(arg_schema.get("properties"), dict):
            status = "invalid_contract"
            executable = False
            errors.append("arg_schema_properties_must_be_object")
        if self._has_structural_contract_errors(errors):
            status = "invalid_contract"
            executable = False

        normalized_script = dict(script)
        normalized_script["resolved_path"] = str(resolved_path)
        normalized_script["sha256"] = expected_hash

        return {
            **raw,
            "name": name,
            "status": status,
            "declared_status": declared_status,
            "executable": executable,
            "operator_outbox_on": sorted(operator_outbox_on),
            "script": normalized_script,
            "hash_check": hash_result,
            "errors": errors,
            "evidence_schema_enforced": bool(raw.get("evidence_schema")),
        }

    @staticmethod
    def _has_structural_contract_errors(errors: list[str]) -> bool:
        stale_hash_errors = {"sha256_mismatch", "empty_sha256"}
        for error in errors:
            text = _safe_text(error, 500)
            if text in stale_hash_errors:
                continue
            if text.startswith("script_missing:") or text.startswith("hash_failed:"):
                continue
            return True
        return False

    def _validate_value(self, key: str, value: Any, spec: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        expected_type = _safe_text(spec.get("type"), 40)
        if expected_type == "string":
            if not isinstance(value, str):
                errors.append(f"arg_type:{key}:string")
            else:
                min_length = spec.get("minLength")
                if isinstance(min_length, int) and len(value) < min_length:
                    errors.append(f"arg_min_length:{key}:{min_length}")
        elif expected_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"arg_type:{key}:integer")
            else:
                minimum = spec.get("minimum")
                maximum = spec.get("maximum")
                if isinstance(minimum, int) and value < minimum:
                    errors.append(f"arg_minimum:{key}:{minimum}")
                if isinstance(maximum, int) and value > maximum:
                    errors.append(f"arg_maximum:{key}:{maximum}")
        elif expected_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"arg_type:{key}:boolean")
        elif expected_type == "array":
            if not isinstance(value, list):
                errors.append(f"arg_type:{key}:array")
            else:
                item_spec = _safe_dict(spec.get("items"))
                for index, item in enumerate(value):
                    errors.extend(
                        self._validate_value(f"{key}[{index}]", item, item_spec)
                        if item_spec
                        else []
                    )

        enum = spec.get("enum")
        if isinstance(enum, list) and value not in enum:
            errors.append(f"arg_enum:{key}")
        return errors

    def _validate_contract_bounds(
        self,
        capability: dict[str, Any],
        args: dict[str, Any],
    ) -> list[str]:
        errors: list[str] = []
        allowed_roots = [
            _safe_text(item, 120)
            for item in _safe_list(capability.get("allowed_roots"))
            if _safe_text(item, 120)
        ]
        if allowed_roots and "root" in args and _safe_text(args.get("root"), 120) not in allowed_roots:
            errors.append("arg_not_allowed_root:root")

        network_scope = _safe_text(capability.get("network_scope"), 120)
        base_url = _safe_text(args.get("base_url"), 500)
        if network_scope and base_url:
            parsed = urlparse(base_url)
            if parsed.hostname != network_scope:
                errors.append(f"arg_network_scope:base_url:{network_scope}")
        return errors

    def _invalid_args_result(
        self,
        capability: dict[str, Any],
        args: dict[str, Any],
        errors: list[str],
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "reason": "invalid_args",
            "operator_outbox": self._should_outbox(capability, "invalid_args"),
            "args": args,
            "errors": errors,
        }

    def _blocked_result(
        self,
        reason: str,
        detail: str,
        *,
        registry: Any = None,
        capability: dict[str, Any] | None = None,
        errors: list[str] | None = None,
    ) -> dict[str, Any]:
        clean_capability = _safe_dict(capability)
        return {
            "ok": False,
            "reason": reason,
            "detail": detail,
            "operator_outbox": self._should_outbox(clean_capability, reason, registry=registry),
            "capability": clean_capability,
            "registry": registry,
            "errors": errors or [detail],
        }

    def _should_outbox(
        self,
        capability: dict[str, Any],
        reason: str,
        *,
        registry: Any = None,
    ) -> bool:
        outbox_on = {
            _safe_text(item, 80)
            for item in _safe_list(capability.get("operator_outbox_on"))
            if _safe_text(item, 80)
        }
        if not outbox_on and isinstance(registry, dict):
            outbox_on = {
                _safe_text(item, 80)
                for item in _safe_list(registry.get("default_operator_outbox_on"))
                if _safe_text(item, 80)
            }
        return reason in (outbox_on or OPERATOR_OUTBOX_REASONS)


OS_CAPABILITY_REGISTRY_SERVICE = OsCapabilityRegistryService()
