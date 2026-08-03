from __future__ import annotations

from services.nova_shell._constants import TOTP_DIGITS, TOTP_INTERVAL, TOTP_ISSUER

try:
    import pyotp as _pyotp
    _PYOTP_AVAILABLE = True
except ImportError:
    _pyotp = None  # type: ignore[assignment]
    _PYOTP_AVAILABLE = False


def _require_pyotp() -> None:
    if not _PYOTP_AVAILABLE:
        raise ImportError(
            "pyotp is required for TOTP support. "
            "Install it with: pip install pyotp"
        )


def generate_totp_secret() -> str:
    """Generate a new base32 TOTP secret for a user."""
    _require_pyotp()
    return _pyotp.random_base32()


def totp_uri(secret: str, username: str, issuer: str = TOTP_ISSUER) -> str:
    """Return the otpauth:// URI for QR code generation."""
    _require_pyotp()
    totp = _pyotp.TOTP(
        secret,
        digits=TOTP_DIGITS,
        interval=TOTP_INTERVAL,
    )
    return totp.provisioning_uri(name=username, issuer_name=issuer)


def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
    """
    Verify a 6-digit TOTP code.

    valid_window=1 allows ±1 time step to account for clock skew.
    Returns True only if the code is valid.
    """
    if not _PYOTP_AVAILABLE:
        return False
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return False
    try:
        totp = _pyotp.TOTP(
            secret,
            digits=TOTP_DIGITS,
            interval=TOTP_INTERVAL,
        )
        return totp.verify(code, valid_window=valid_window)
    except Exception:
        return False


def totp_available() -> bool:
    return _PYOTP_AVAILABLE
