from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Nova Shell — LLC-signed update receiver
#
# Intended: verify update packages with LLC public key, then unpack/apply.
# LLC key management and fleet update system are NOT built yet.
# A temporary public key is baked so crypto shape is real; apply stays unfinished.
# ─────────────────────────────────────────────────────────────────────────────

from services.nova_shell._constants import (
    LLC_KEY_PROVISIONING,
    LLC_PUBLIC_KEY_IS_PLACEHOLDER,
    LLC_PUBLIC_KEY_IS_TEMPORARY,
    LLC_PUBLIC_KEY_PEM,
)


def verify_update_signature(payload: bytes, signature: bytes) -> bool:
    """
    Verify that payload was signed by the LLC private key.

    Temporary key may verify if cryptography is installed and signature matches
    the temp keypair — production trust requires production provisioning.
    """
    if LLC_PUBLIC_KEY_IS_PLACEHOLDER and not LLC_PUBLIC_KEY_IS_TEMPORARY:
        return False

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        public_key: Ed25519PublicKey = load_pem_public_key(LLC_PUBLIC_KEY_PEM.encode())  # type: ignore[assignment]
        public_key.verify(signature, payload)
        return True
    except Exception:
        return False


def accept_update(payload: bytes, signature: bytes) -> dict:
    """
    Gate for applying a Nova update bundle.

    Even with a temporary key present, apply is not production-ready until the
    LLC update system exists and provisioning is production.
    """
    if LLC_KEY_PROVISIONING != "production":
        return {
            "accepted": False,
            "reason": "LLC key provisioning is temporary; fleet update system not built yet.",
            "provisioning": LLC_KEY_PROVISIONING,
        }

    if not verify_update_signature(payload, signature):
        return {"accepted": False, "reason": "Signature verification failed."}

    # Production path: unpack and apply update bundle (not implemented).
    return {
        "accepted": False,
        "reason": "Signature path ready; update apply not implemented yet.",
        "provisioning": LLC_KEY_PROVISIONING,
    }


def receiver_status() -> dict:
    return {
        "llc_key_real": not bool(LLC_PUBLIC_KEY_IS_PLACEHOLDER) or bool(LLC_PUBLIC_KEY_IS_TEMPORARY),
        "llc_key_temporary": bool(LLC_PUBLIC_KEY_IS_TEMPORARY),
        "provisioning": str(LLC_KEY_PROVISIONING or "temporary"),
        "verification_enabled": bool(LLC_PUBLIC_KEY_IS_TEMPORARY) or not bool(LLC_PUBLIC_KEY_IS_PLACEHOLDER),
        "update_system_built": str(LLC_KEY_PROVISIONING or "") == "production",
        "note": (
            "Temporary LLC public key baked; fleet key management and update apply not built."
            if LLC_PUBLIC_KEY_IS_TEMPORARY
            else "Update receiver awaiting production LLC key and apply path."
        ),
    }
