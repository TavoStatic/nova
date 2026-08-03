from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from services.nova_shell._constants import LLC_PUBLIC_KEY_IS_PLACEHOLDER, NOVA_SHELL_VERSION

_DEFAULT_RUNTIME_ROOT = Path(__file__).resolve().parents[2] / "runtime" / "nova_shell"


@dataclass
class NodeIdentity:
    """Persistent identity for this Nova installation.

    Generated once at first setup. Never changes.
    This is how the LLC central system identifies each node.
    """
    installation_id: str
    created_at: str
    nova_shell_version: str = NOVA_SHELL_VERSION
    llc_key_status: str = "placeholder"  # "placeholder" | "real"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NodeIdentity":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def _identity_path(runtime_root: Path) -> Path:
    return Path(runtime_root) / "identity.json"


def generate_installation_id() -> str:
    return str(uuid.uuid4())


def load_or_create_identity(runtime_root: Path | None = None) -> NodeIdentity:
    """Load identity from disk or create a new one on first run."""
    root = Path(runtime_root or _DEFAULT_RUNTIME_ROOT)
    path = _identity_path(root)

    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return NodeIdentity.from_dict(data)
        except Exception:
            pass

    identity = NodeIdentity(
        installation_id=generate_installation_id(),
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        llc_key_status="placeholder" if LLC_PUBLIC_KEY_IS_PLACEHOLDER else "real",
    )
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(identity.to_dict(), indent=2), encoding="utf-8")
    return identity


def get_installation_id(runtime_root: Path | None = None) -> str:
    return load_or_create_identity(runtime_root).installation_id
