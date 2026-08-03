from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Nova Shell — LLC-signed update receiver stub
#
# The LLC holds an offline Ed25519 private key.
# Every update package pushed to Nova nodes is signed with it.
# This module verifies those signatures using the LLC public key embedded
# in _constants.py before any update is accepted.
#
# Status: stub — signature verification returns False until a real
# LLC public key is embedded and full implementation lands.
# ─────────────────────────────────────────────────────────────────────────────

from services.nova_shell._constants import LLC_PUBLIC_KEY_IS_PLACEHOLDER, LLC_PUBLIC_KEY_PEM


def verify_update_signature(payload: bytes, signature: bytes) -> bool:
    """
    Verify that payload was signed by the LLC private key.

    Returns False if:
      - LLC_PUBLIC_KEY_IS_PLACEHOLDER is True (dev mode)
      - cryptography library is not installed
      - signature does not verify

    Raises nothing — callers treat False as "do not apply update".
    """
    if LLC_PUBLIC_KEY_IS_PLACEHOLDER:
        return False

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        from cryptography.exceptions import InvalidSignature

        public_key: Ed25519PublicKey = load_pem_public_key(LLC_PUBLIC_KEY_PEM.encode())  # type: ignore[assignment]
        public_key.verify(signature, payload)
        return True
    except Exception:
        return False


def accept_update(payload: bytes, signature: bytes) -> dict:
    """
    Gate for applying a Nova update bundle.

    Returns a dict with keys:
      accepted (bool), reason (str)
    """
    if LLC_PUBLIC_KEY_IS_PLACEHOLDER:
        return {"accepted": False, "reason": "LLC public key is a placeholder. Update verification disabled."}

    if not verify_update_signature(payload, signature):
        return {"accepted": False, "reason": "Signature verification failed."}

    # TODO (LLC): Unpack and apply update bundle.
    return {"accepted": True, "reason": "Signature verified. Update pending application."}


def receiver_status() -> dict:
    return {
        "llc_key_real": not LLC_PUBLIC_KEY_IS_PLACEHOLDER,
        "verification_enabled": not LLC_PUBLIC_KEY_IS_PLACEHOLDER,
        "note": "Update receiver is a stub in nova_shell 0.1.",
    }
