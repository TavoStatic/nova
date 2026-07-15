from __future__ import annotations

from pathlib import Path

import http_session_store

from services.nova_runtime_context import RUNTIME_DIR

CLI_SESSION_ID = "cli"
MAX_CLI_TURNS = 40


def cli_session_store_path(*, runtime_root: Path | None = None) -> Path:
    return (runtime_root or RUNTIME_DIR) / "cli_chat_sessions.json"


def load_cli_session_turns(*, runtime_root: Path | None = None) -> list[tuple[str, str]]:
    backing: dict[str, list[tuple[str, str]]] = {}
    owners: dict[str, str] = {}
    http_session_store.load_persisted_sessions(
        store_path=cli_session_store_path(runtime_root=runtime_root),
        session_turns=backing,
        session_owners=owners,
        max_stored_turns_per_session=MAX_CLI_TURNS * 2,
    )
    return list(backing.get(CLI_SESSION_ID) or [])


def persist_cli_session_turns(
    turns: list[tuple[str, str]],
    *,
    runtime_root: Path | None = None,
    owner: str = "",
) -> None:
    root = runtime_root or RUNTIME_DIR
    http_session_store.persist_sessions(
        runtime_dir=Path(root),
        store_path=cli_session_store_path(runtime_root=root),
        session_turns={CLI_SESSION_ID: list(turns)},
        session_owners={CLI_SESSION_ID: str(owner or "").strip()} if str(owner or "").strip() else {},
        max_stored_sessions=1,
        max_stored_turns_per_session=MAX_CLI_TURNS * 2,
    )