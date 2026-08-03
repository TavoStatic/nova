from __future__ import annotations

import json
import secrets
import string

from services.nova_shell._constants import RECOVERY_CODE_COUNT, RECOVERY_CODE_LENGTH

try:
    from argon2 import PasswordHasher as _PH
    from argon2.exceptions import VerifyMismatchError as _VME
    _ARGON2_AVAILABLE = True
except ImportError:
    _PH = None  # type: ignore[assignment]
    _VME = None  # type: ignore[assignment]
    _ARGON2_AVAILABLE = False

import hashlib

_CHARSET = string.digits  # digits-only codes are easier to read/type


def _format_code(raw: str) -> str:
    """Split a 10-digit code into XXXXX-XXXXX for readability."""
    mid = len(raw) // 2
    return f"{raw[:mid]}-{raw[mid:]}"


def _generate_raw() -> str:
    return "".join(secrets.choice(_CHARSET) for _ in range(RECOVERY_CODE_LENGTH))


def _hash_code(raw: str) -> str:
    """Hash a recovery code. Uses argon2 if available, SHA-256 otherwise."""
    if _ARGON2_AVAILABLE:
        ph = _PH()
        return ph.hash(raw)
    # Fallback: SHA-256 with a static prefix is better than plaintext.
    # Not as strong as argon2 but acceptable for one-time codes.
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _verify_code(raw: str, stored_hash: str) -> bool:
    if stored_hash.startswith("sha256:"):
        expected = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()
        return secrets.compare_digest(expected, stored_hash)
    if _ARGON2_AVAILABLE:
        try:
            ph = _PH()
            return ph.verify(stored_hash, raw)
        except Exception:
            return False
    return False


def generate_recovery_codes(
    count: int = RECOVERY_CODE_COUNT,
) -> tuple[list[str], list[str]]:
    """
    Generate recovery codes.

    Returns:
        (plaintext_codes, hashed_codes)

        plaintext_codes — show to user ONCE, never store.
        hashed_codes    — store in DB (recovery_codes_json).
    """
    raws = [_generate_raw() for _ in range(count)]
    plaintext = [_format_code(r) for r in raws]
    hashed = [_hash_code(r) for r in raws]
    return plaintext, hashed


def verify_and_consume_code(
    raw_input: str,
    hashed_codes: list[str],
) -> tuple[bool, list[str]]:
    """
    Try to consume a recovery code.

    Strips formatting (dashes/spaces) from user input before comparison.

    Returns:
        (matched, remaining_hashes)

        If matched=True, the used hash is removed from the list.
        remaining_hashes is the updated list to persist.
    """
    normalized = raw_input.strip().replace("-", "").replace(" ", "")
    for i, h in enumerate(hashed_codes):
        if _verify_code(normalized, h):
            remaining = hashed_codes[:i] + hashed_codes[i + 1:]
            return True, remaining
    return False, list(hashed_codes)


def remaining_code_count(hashed_codes: list[str]) -> int:
    return len(hashed_codes)


def codes_from_json(json_str: str) -> list[str]:
    """Deserialize hashed codes from the DB column."""
    try:
        return json.loads(json_str or "[]")
    except Exception:
        return []


def codes_to_json(hashed_codes: list[str]) -> str:
    return json.dumps(hashed_codes)
