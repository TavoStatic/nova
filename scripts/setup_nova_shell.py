#!/usr/bin/env python3
"""
setup_nova_shell.py — First-run setup CLI for Nova Shell security scaffolding.

Usage:
    python scripts/setup_nova_shell.py
        Interactive first-admin setup.

    python scripts/setup_nova_shell.py --generate-llc-keys
        Generate an Ed25519 LLC key pair.
        Private key → stdout (keep offline, NEVER commit).
        Public key PEM → stdout (copy into services/nova_shell/_constants.py).

    python scripts/setup_nova_shell.py --status
        Print current Nova Shell status (identity, admin exists, deps).
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

# Ensure the project root is importable
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from services.nova_shell._constants import LLC_PUBLIC_KEY_IS_PLACEHOLDER, NOVA_SHELL_VERSION
from services.nova_shell.identity import load_or_create_identity
from services.nova_shell.store import ShellStore
from services.nova_shell.auth import ShellAuth
from services.nova_shell.admin import ShellAdmin


def _print_header() -> None:
    print()
    print(f"  Nova Shell v{NOVA_SHELL_VERSION} — First-Run Setup")
    print("  " + "─" * 44)
    print()


def _check_deps() -> dict[str, bool]:
    deps = {}
    try:
        import argon2  # noqa: F401
        deps["argon2-cffi"] = True
    except ImportError:
        deps["argon2-cffi"] = False
    try:
        import pyotp  # noqa: F401
        deps["pyotp"] = True
    except ImportError:
        deps["pyotp"] = False
    try:
        import cryptography  # noqa: F401
        deps["cryptography"] = True
    except ImportError:
        deps["cryptography"] = False
    return deps


def cmd_status() -> None:
    _print_header()
    identity = load_or_create_identity()
    print(f"  Installation ID : {identity.installation_id}")
    print(f"  Shell version   : {identity.nova_shell_version}")
    print(f"  LLC key status  : {'PLACEHOLDER — dev mode' if LLC_PUBLIC_KEY_IS_PLACEHOLDER else 'REAL'}")
    print()

    deps = _check_deps()
    print("  Dependencies:")
    for name, ok in deps.items():
        status = "OK" if ok else "MISSING"
        print(f"    {name:<20} {status}")
    print()

    store = ShellStore()
    admin = ShellAdmin(store, ShellAuth(store))
    print(f"  First admin     : {'exists' if admin.first_admin_exists() else 'NOT SET UP'}")
    print()


def cmd_first_setup() -> None:
    _print_header()

    deps = _check_deps()
    missing = [k for k, v in deps.items() if not v]
    if missing:
        print(f"  WARNING: Missing deps: {', '.join(missing)}")
        print("  Install: pip install argon2-cffi pyotp cryptography")
        print()

    store = ShellStore()
    auth = ShellAuth(store)
    admin = ShellAdmin(store, auth)

    if admin.first_admin_exists():
        print("  An account_admin already exists.")
        print("  Setup is complete. Use the Nova Shell login to continue.")
        print()
        return

    print("  No account_admin found. Creating the first admin account.")
    print()

    username = input("  Admin username : ").strip()
    if not username:
        print("  ERROR: Username cannot be empty.")
        sys.exit(1)

    display_name = input(f"  Display name   [{username}]: ").strip() or username

    password = getpass.getpass("  Password       : ")
    confirm  = getpass.getpass("  Confirm        : ")

    if password != confirm:
        print("  ERROR: Passwords do not match.")
        sys.exit(1)

    if len(password) < 12:
        print("  ERROR: Password must be at least 12 characters.")
        sys.exit(1)

    try:
        user = admin.create_first_admin(username, password, display_name)
    except Exception as exc:
        print(f"  ERROR: {exc}")
        sys.exit(1)

    identity = load_or_create_identity()
    print()
    print("  ✓ Admin account created.")
    print(f"    Username        : {user['username']}")
    print(f"    Installation ID : {identity.installation_id}")
    print()
    print("  Next step: set up TOTP 2FA by logging in and calling setup_totp().")
    print()


def cmd_generate_llc_keys() -> None:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PublicFormat, PrivateFormat, NoEncryption
        )
    except ImportError:
        print("ERROR: cryptography package is required.")
        print("Install: pip install cryptography")
        sys.exit(1)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    public_pem = public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()

    print()
    print("=" * 60)
    print("  LLC Ed25519 Key Pair — GENERATED")
    print("=" * 60)
    print()
    print("  ⚠️  PRIVATE KEY — keep offline, NEVER commit to git:")
    print()
    print(private_pem)
    print()
    print("  ✓  PUBLIC KEY — copy into services/nova_shell/_constants.py")
    print("     Replace the value of LLC_PUBLIC_KEY_PEM:")
    print()
    print(public_pem)
    print()
    print("  After embedding the public key, set LLC_PUBLIC_KEY_IS_PLACEHOLDER = False")
    print("  and rebuild the Nova package.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nova Shell first-run setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--generate-llc-keys",
        action="store_true",
        help="Generate LLC Ed25519 key pair (run once, keep private key offline).",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print Nova Shell status and exit.",
    )
    args = parser.parse_args()

    if args.generate_llc_keys:
        cmd_generate_llc_keys()
    elif args.status:
        cmd_status()
    else:
        cmd_first_setup()


if __name__ == "__main__":
    main()
