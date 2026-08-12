from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Nova Shell — Telemetry
#
# Behavioural signals from Nova nodes are intended to flow to LLC central.
# The LLC central management system is NOT built yet. A temporary URL is baked
# in so configuration shape is real; transport stays no-op until systems exist.
#
# Design contract (do not break):
#   - emit_signal() must always be safe to call with any keyword arguments.
#   - No import of nova_core or any product backpack.
#   - Do not treat TEMP URL presence as "telemetry finished."
# ─────────────────────────────────────────────────────────────────────────────

from services.nova_shell._constants import (
    LLC_TELEMETRY_CENTRAL_URL,
    LLC_TELEMETRY_PROVISIONING,
    LLC_TELEMETRY_SYSTEM_BUILT,
)

# Enable local enqueue shape only when central system is built. Still false.
_ENABLED: bool = False
_CENTRAL_CONNECTED: bool = False
_CONFIGURED_ENDPOINT: str = str(LLC_TELEMETRY_CENTRAL_URL or "").strip()


def configured_central_url() -> str:
    return _CONFIGURED_ENDPOINT or str(LLC_TELEMETRY_CENTRAL_URL or "").strip()


def emit_signal(event: str, **kwargs) -> None:
    """
    Emit a behavioural signal to the LLC central system.
    No-op while LLC telemetry system is not built / not enabled.
    """
    if not _ENABLED or not LLC_TELEMETRY_SYSTEM_BUILT:
        return
    # When system exists: serialize event + kwargs, POST/queue to configured_central_url().
    return


def connect_central(endpoint: str = "", installation_id: str = "", public_key_pem: str = "") -> bool:
    """
    Establish connection to LLC central system.

    Temporary URL may be passed or defaulted from constants. Returns False until
    LLC_TELEMETRY_SYSTEM_BUILT is true and a real connect path is implemented.
    """
    global _CENTRAL_CONNECTED, _CONFIGURED_ENDPOINT
    url = str(endpoint or LLC_TELEMETRY_CENTRAL_URL or "").strip()
    if url:
        _CONFIGURED_ENDPOINT = url
    if not LLC_TELEMETRY_SYSTEM_BUILT:
        _CENTRAL_CONNECTED = False
        return False
    # Real connect not implemented — product unfinished.
    _CENTRAL_CONNECTED = False
    return False


def is_connected() -> bool:
    return bool(_CENTRAL_CONNECTED) and bool(LLC_TELEMETRY_SYSTEM_BUILT)


def telemetry_status() -> dict:
    return {
        "enabled": bool(_ENABLED),
        "connected": bool(_CENTRAL_CONNECTED),
        "central_url": configured_central_url(),
        "provisioning": str(LLC_TELEMETRY_PROVISIONING or "temporary"),
        "system_built": bool(LLC_TELEMETRY_SYSTEM_BUILT),
        "temporary_bake_in": str(LLC_TELEMETRY_PROVISIONING or "") == "temporary",
        "note": (
            "Telemetry central is not built yet; temp URL is baked for config only."
            if not LLC_TELEMETRY_SYSTEM_BUILT
            else "Telemetry central configured."
        ),
    }
