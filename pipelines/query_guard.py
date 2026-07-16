from __future__ import annotations

from typing import Any, Mapping, Optional

from pipelines.redaction import resolve_redaction_profile


class QueryGuardError(ValueError):
    pass


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _normalize_params(params: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (params or {}).items():
        name = str(key).strip()
        if not name:
            continue
        out[name] = value.strip() if isinstance(value, str) else value
    return out


class PipelineQueryGuard:
    """Validate governed pipeline query intents before execution."""

    def __init__(self, *, max_rows_default: int = 100, max_rows_hard_cap: int = 20):
        self.max_rows_default = max(1, int(max_rows_default))
        self.max_rows_hard_cap = max(1, int(max_rows_hard_cap))

    def validate(
        self,
        templates: Mapping[str, Mapping[str, Any]],
        operation: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        row_limit: Optional[int] = None,
    ) -> dict[str, Any]:
        op = (operation or "").strip()
        if not op:
            raise QueryGuardError("Missing pipeline operation.")
        if op not in templates:
            raise QueryGuardError(f"Unknown pipeline operation: {op}")

        template = dict(templates[op] or {})
        sanitized_params = _normalize_params(params)

        allowed_params = {str(item) for item in (template.get("params") or [])}
        unexpected = sorted(key for key in sanitized_params if key not in allowed_params)
        if unexpected:
            raise QueryGuardError(
                f"Operation '{op}' does not allow parameter(s): {', '.join(unexpected)}"
            )

        required_all = [str(item) for item in (template.get("required_all") or [])]
        missing = [item for item in required_all if not _has_value(sanitized_params.get(item))]
        if missing:
            raise QueryGuardError(
                f"Operation '{op}' requires parameter(s): {', '.join(missing)}"
            )

        required_any = [
            [str(item) for item in group if str(item).strip()]
            for group in (template.get("required_any") or [])
            if isinstance(group, list)
        ]
        if required_any:
            satisfied = any(
                group and all(_has_value(sanitized_params.get(item)) for item in group)
                for group in required_any
            )
            if not satisfied:
                pretty = " or ".join("/".join(group) for group in required_any if group)
                raise QueryGuardError(
                    f"Operation '{op}' requires one of: {pretty}"
                )

        template_cap = max(1, int(template.get("max_rows") or self.max_rows_default))
        row_cap = min(template_cap, self.max_rows_hard_cap)
        requested_rows = row_cap if row_limit is None else max(1, int(row_limit))
        effective_rows = min(requested_rows, row_cap)

        return {
            "operation": op,
            "template": template,
            "params": sanitized_params,
            "requested_row_limit": requested_rows,
            "effective_row_limit": effective_rows,
            "row_limit_clamped": requested_rows != effective_rows,
            "row_limit_hard_cap": self.max_rows_hard_cap,
            "redaction_profile": resolve_redaction_profile(
                operation=op,
                template_profile=template.get("redaction_profile"),
                resource=sanitized_params.get("resource"),
            ),
        }
