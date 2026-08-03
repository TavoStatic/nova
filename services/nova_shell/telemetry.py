from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Nova Shell — Telemetry stub
#
# Behavioural signals from Nova nodes flow here before being forwarded to
# the LLC central system.  This module is intentionally a no-op in 0.1.
#
# Design contract (do not break):
#   - emit_signal() must always be safe to call with any keyword arguments.
#   - No import of nova_core or any product backpack.
#   - _ENABLED is the single switch; nothing else changes call sites.
# ─────────────────────────────────────────────────────────────────────────────

_ENABLED: bool = False
_CENTRAL_CONNECTED: bool = False


def emit_signal(event: str, **kwargs) -> None:
    """
    Emit a behavioural signal to the LLC central system.
    No-op in dev mode (_ENABLED=False).
    """
    if not _ENABLED:
        return
    # TODO (LLC): Serialize event + kwargs, queue for batch send to central.


def connect_central(endpoint: str, installation_id: str, public_key_pem: str) -> bool:
    """
    Establish connection to LLC central system.
    Returns True on success.  Always False until implemented.
    """
    return False


def is_connected() -> bool:
    return _CENTRAL_CONNECTED


def telemetry_status() -> dict:
    return {
        "enabled": _ENABLED,
        "connected": _CENTRAL_CONNECTED,
        "note": "Telemetry is a stub in nova_shell 0.1.",
    }
