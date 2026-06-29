from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from services.end_to_end_wiring import FRONTDOOR_COMMANDS
from services.nova_control_action_dispatcher import NovaControlActionDispatcher
from services.operator_control import OPERATOR_CONTROL_SERVICE

HTTP_BACKEND_COMMAND_ACTIONS = (
    "backend_command_list",
    "backend_command_run",
)

_DISPATCHER_SOURCE = Path(NovaControlActionDispatcher.__module__.replace(".", "/") + ".py")
if not _DISPATCHER_SOURCE.exists():
    _DISPATCHER_SOURCE = Path(__file__).resolve().parents[1] / "services" / "nova_control_action_dispatcher.py"


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _frontdoor_entry_checks(root: Path) -> dict[str, Any]:
    nova_cmd = root / "nova.cmd"
    nova_ps1 = root / "nova.ps1"
    cmd_exists = nova_cmd.exists()
    ps1_exists = nova_ps1.exists()
    cmd_text = _read_text(nova_cmd) if cmd_exists else ""
    ps1_text = _read_text(nova_ps1) if ps1_exists else ""
    cmd_delegates = "powershell.exe" in cmd_text.lower() and "nova.ps1" in cmd_text.lower()
    missing_ps1_commands = [
        command for command in FRONTDOOR_COMMANDS if f'"{command}"' not in ps1_text
    ]
    return {
        "nova_cmd_exists": cmd_exists,
        "nova_ps1_exists": ps1_exists,
        "cmd_delegates_to_ps1": cmd_delegates,
        "missing_ps1_commands": missing_ps1_commands,
        "frontdoor_checks_ok": bool(
            cmd_exists and ps1_exists and cmd_delegates and not missing_ps1_commands
        ),
    }


def _deck_entry_checks(root: Path, backend_commands: list[dict]) -> dict[str, Any]:
    missing_entries: list[str] = []
    disabled_entries: list[str] = []
    deck_command_ids: list[str] = []
    for row in list(backend_commands or []):
        if not isinstance(row, dict):
            continue
        command_id = str(row.get("command_id") or "").strip().lower()
        entry = str(row.get("entry") or "").strip()
        if not command_id:
            continue
        deck_command_ids.append(command_id)
        if not bool(row.get("enabled", True)):
            disabled_entries.append(command_id)
            continue
        if not entry:
            missing_entries.append(command_id)
            continue
        entry_path = root / entry
        if not entry_path.exists():
            missing_entries.append(command_id)
    return {
        "deck_command_ids": deck_command_ids,
        "missing_deck_entries": missing_entries,
        "disabled_deck_entries": disabled_entries,
        "deck_entries_ok": not missing_entries,
    }


def _http_backend_action_checks() -> dict[str, Any]:
    dispatcher_text = _read_text(_DISPATCHER_SOURCE)
    missing_http_actions = [
        action
        for action in HTTP_BACKEND_COMMAND_ACTIONS
        if f'if act == "{action}"' not in dispatcher_text
    ]
    return {
        "http_backend_actions": list(HTTP_BACKEND_COMMAND_ACTIONS),
        "missing_http_actions": missing_http_actions,
        "http_actions_present": not missing_http_actions,
    }


def _derive_frontdoor_cli_status(
    *,
    backend_commands: Any,
    frontdoor_checks_ok: bool,
    deck_entries_ok: bool,
    http_actions_present: bool,
) -> str:
    if backend_commands is not None and not isinstance(backend_commands, list):
        return "unreadable"
    if not frontdoor_checks_ok:
        return "missing"
    if not deck_entries_ok or not http_actions_present:
        return "degraded"
    return "ok"


def build_frontdoor_cli_surfaces(
    *,
    root: Path,
    backend_commands: list[dict] | None = None,
    limit: int = 40,
    load_backend_commands_fn: Callable[[int], list[dict]] | None = None,
) -> dict[str, Any]:
    clean_root = Path(root)
    malformed_commands = backend_commands is not None and not isinstance(backend_commands, list)
    if malformed_commands:
        commands: list[dict] = []
    elif isinstance(backend_commands, list):
        commands = list(backend_commands)
    elif callable(load_backend_commands_fn):
        commands = list(load_backend_commands_fn(max(1, int(limit))) or [])
    else:
        commands = OPERATOR_CONTROL_SERVICE.load_backend_commands(
            OPERATOR_CONTROL_SERVICE.backend_command_deck_path(clean_root),
            limit=max(1, int(limit)),
        )

    frontdoor = _frontdoor_entry_checks(clean_root)
    deck = _deck_entry_checks(clean_root, commands)
    http_actions = _http_backend_action_checks()
    status = _derive_frontdoor_cli_status(
        backend_commands=None if malformed_commands else commands,
        frontdoor_checks_ok=bool(frontdoor.get("frontdoor_checks_ok")),
        deck_entries_ok=bool(deck.get("deck_entries_ok")),
        http_actions_present=bool(http_actions.get("http_actions_present")),
    )
    if malformed_commands:
        status = "unreadable"
    parity_ok = (
        status == "ok"
        and bool(frontdoor.get("frontdoor_checks_ok"))
        and bool(deck.get("deck_entries_ok"))
        and bool(http_actions.get("http_actions_present"))
    )
    cli_http_parity = {
        "ok": parity_ok,
        "status": status,
        "frontdoor_checks_ok": bool(frontdoor.get("frontdoor_checks_ok")),
        "deck_entries_ok": bool(deck.get("deck_entries_ok")),
        "http_actions_present": bool(http_actions.get("http_actions_present")),
        "missing_ps1_commands": list(frontdoor.get("missing_ps1_commands") or []),
        "missing_deck_entries": list(deck.get("missing_deck_entries") or []),
        "disabled_deck_entries": list(deck.get("disabled_deck_entries") or []),
        "missing_http_actions": list(http_actions.get("missing_http_actions") or []),
        "deck_command_ids": list(deck.get("deck_command_ids") or []),
        "http_backend_actions": list(http_actions.get("http_backend_actions") or []),
        "ps1_command_count": len(FRONTDOOR_COMMANDS),
    }
    return {
        "backend_commands": commands,
        "backend_command_count": len(commands),
        "frontdoor_cli_status": status,
        "cli_http_parity": cli_http_parity,
    }


class FrontdoorCliParityService:
    @staticmethod
    def build_surfaces(
        *,
        root: Path,
        backend_commands: list[dict] | None = None,
        limit: int = 40,
        load_backend_commands_fn: Callable[[int], list[dict]] | None = None,
    ) -> dict[str, Any]:
        return build_frontdoor_cli_surfaces(
            root=root,
            backend_commands=backend_commands,
            limit=limit,
            load_backend_commands_fn=load_backend_commands_fn,
        )


FRONTDOOR_CLI_PARITY_SERVICE = FrontdoorCliParityService()