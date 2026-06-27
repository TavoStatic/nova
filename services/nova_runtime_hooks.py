from __future__ import annotations

from typing import Any, Callable, Mapping, Optional


def resolve_runtime_hooks(
    hook_map: Mapping[str, str],
    *,
    explicit_hooks: Mapping[str, Any],
    runtime_scope: Optional[Mapping[str, Any]] = None,
    factories: Optional[Mapping[str, Callable[[Mapping[str, Any]], Any]]] = None,
) -> dict[str, Callable[..., Any]]:
    resolved: dict[str, Callable[..., Any]] = {}
    factories = factories or {}
    for hook_name, runtime_name in hook_map.items():
        value = explicit_hooks.get(hook_name)
        if value is None:
            if runtime_scope is None:
                raise TypeError(f"{hook_name} is required")
            factory = factories.get(hook_name)
            if factory is not None:
                value = factory(runtime_scope)
            else:
                value = runtime_scope.get(runtime_name)
        if value is None:
            # Provide a safe no-op for tests and incomplete scopes (e.g. new actions)
            def _noop(*a, **k):
                return (False, f"{hook_name}_unavailable", {}, f"{hook_name}_unavailable")
            value = _noop
        if not callable(value):
            raise TypeError(f"{hook_name} must be callable")
        resolved[hook_name] = value
    return resolved
