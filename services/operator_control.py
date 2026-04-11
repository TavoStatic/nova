from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping


class OperatorControlService:
    """Load operator macros and backend command decks outside the HTTP transport layer."""

    @staticmethod
    def operator_macros_path(base_dir: Path) -> Path:
        return Path(base_dir) / "operator_macros.json"

    @staticmethod
    def backend_command_deck_path(base_dir: Path) -> Path:
        return Path(base_dir) / "backend_command_deck.json"

    @staticmethod
    def backend_command_list_action(*, load_backend_commands_fn) -> tuple[bool, str, dict, str]:
        commands = load_backend_commands_fn(80)
        return True, "backend_command_list_ok", {"commands": commands}, f"backend_command_list_ok:{len(commands)}"

    @staticmethod
    def backend_command_run_action(payload: dict, *, load_backend_commands_fn, run_backend_command_fn) -> tuple[bool, str, dict, str]:
        command_id = str(payload.get("command_id") or payload.get("command") or "").strip().lower()
        if not command_id:
            return False, "backend_command_required", {"available_commands": load_backend_commands_fn(80)}, "backend_command_required"
        ok, msg, extra = run_backend_command_fn(command_id, payload)
        return ok, msg, extra, msg

    @staticmethod
    def operator_prompt_action(
        payload: dict,
        *,
        resolve_operator_macro_fn,
        render_operator_macro_prompt_fn,
        load_operator_macros_fn,
        normalize_user_id_fn,
        assert_session_owner_fn,
        process_chat_fn,
        session_summaries_fn,
        token_hex_fn,
    ) -> tuple[bool, str, dict, str, dict]:
        macro_id = str(payload.get("macro") or "").strip()
        macro = resolve_operator_macro_fn(macro_id) if macro_id else None
        macro_values = payload.get("macro_values") if isinstance(payload.get("macro_values"), dict) else {}
        message = str(payload.get("message") or payload.get("prompt") or "").strip()
        resolved_macro_values: dict[str, str] = {}
        operator_mode = "macro" if macro is not None else ("cli" if str(payload.get("source") or "").strip().lower() == "cli" else "manual")

        if macro is not None:
            ok_macro, rendered_message, resolved_macro_values = render_operator_macro_prompt_fn(macro, macro_values, note=message)
            if not ok_macro:
                return False, rendered_message, {
                    "available_macros": load_operator_macros_fn(24),
                    "macro": dict(macro),
                    "resolved_macro_values": resolved_macro_values,
                }, rendered_message, {**payload, "operator_mode": "macro"}
            message = rendered_message
        elif macro_id:
            detail = f"operator_macro_not_found:{macro_id}"
            return False, detail, {"available_macros": load_operator_macros_fn(24)}, detail, payload

        if not message:
            return False, "operator_message_required", {}, "operator_message_required", payload

        session_id = str(payload.get("session_id") or "").strip() or f"operator-{token_hex_fn(6)}"
        user_id = normalize_user_id_fn(str(payload.get("user_id") or "operator")) or "operator"
        ok_owner, reason_owner = assert_session_owner_fn(session_id, user_id, allow_bind=True)
        if not ok_owner:
            return False, reason_owner, {"session_id": session_id}, reason_owner, payload

        try:
            reply = process_chat_fn(session_id, message, user_id=user_id)
            sessions = session_summaries_fn(80)
            session_summary = next((item for item in sessions if str(item.get("session_id") or "") == session_id), None)
            detail = f"operator_prompt_ok:{session_id}"
            return True, "operator_prompt_ok", {
                "session_id": session_id,
                "user_id": user_id,
                "macro": dict(macro or {}),
                "resolved_macro_values": resolved_macro_values,
                "reply": reply,
                "session": session_summary or {},
                "sessions": sessions,
            }, detail, {**payload, "operator_mode": operator_mode}
        except Exception as exc:
            detail = f"operator_prompt_failed:{exc}"
            return False, detail, {"session_id": session_id}, detail, {**payload, "operator_mode": operator_mode}

    def load_operator_macros(self, path: Path, limit: int = 24) -> list[dict]:
        macro_path = Path(path)
        if not macro_path.exists():
            return []
        try:
            payload = json.loads(macro_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        raw_macros = payload.get("macros") if isinstance(payload, dict) else payload
        if not isinstance(raw_macros, list):
            return []

        macros: list[dict] = []
        for item in raw_macros:
            if not isinstance(item, dict):
                continue
            macro_id = str(item.get("macro_id") or "").strip()
            prompt = str(item.get("prompt") or "").strip()
            prompt_template = str(item.get("prompt_template") or prompt).strip()
            if not macro_id or not prompt_template:
                continue
            placeholders: list[dict] = []
            for placeholder in list(item.get("placeholders") or []):
                if not isinstance(placeholder, dict):
                    continue
                name = str(placeholder.get("name") or "").strip()
                if not name:
                    continue
                placeholders.append(
                    {
                        "name": name,
                        "label": str(placeholder.get("label") or name),
                        "default": str(placeholder.get("default") or ""),
                        "required": bool(placeholder.get("required", False)),
                    }
                )
            macros.append(
                {
                    "macro_id": macro_id,
                    "label": str(item.get("label") or macro_id),
                    "prompt": prompt,
                    "prompt_template": prompt_template,
                    "placeholders": placeholders,
                    "tags": [str(tag).strip() for tag in list(item.get("tags") or []) if str(tag).strip()],
                }
            )
        macros.sort(key=lambda item: str(item.get("label") or item.get("macro_id") or ""))
        return macros[: max(1, int(limit))]

    def resolve_operator_macro(self, macro_id: str, macros: list[dict]) -> dict | None:
        lookup = str(macro_id or "").strip()
        if not lookup:
            return None
        for item in list(macros or []):
            if str(item.get("macro_id") or "") == lookup:
                return item
        return None

    @staticmethod
    def render_operator_macro_prompt(macro: Mapping[str, Any], values: Mapping[str, Any] | None = None, note: str = "") -> tuple[bool, str, dict[str, str]]:
        if not isinstance(macro, Mapping):
            return False, "operator_macro_invalid", {}
        template = str(macro.get("prompt_template") or macro.get("prompt") or "").strip()
        if not template:
            return False, "operator_macro_invalid", {}
        resolved_values: dict[str, str] = {}
        raw_values = values if isinstance(values, Mapping) else {}
        for placeholder in list(macro.get("placeholders") or []):
            if not isinstance(placeholder, Mapping):
                continue
            name = str(placeholder.get("name") or "").strip()
            if not name:
                continue
            provided = str(raw_values.get(name) or "").strip()
            default = str(placeholder.get("default") or "").strip()
            required = bool(placeholder.get("required", False))
            value = provided or default
            if required and not value:
                return False, f"operator_macro_placeholder_required:{name}", resolved_values
            resolved_values[name] = value
            template = template.replace("{" + name + "}", value)
        final = template.strip()
        clean_note = str(note or "").strip()
        if clean_note:
            final = f"{final}\n\nOperator note: {clean_note}" if final else clean_note
        return True, final, resolved_values

    def load_backend_commands(self, path: Path, limit: int = 40) -> list[dict]:
        deck_path = Path(path)
        if not deck_path.exists():
            return []
        try:
            payload = json.loads(deck_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        raw_items = payload.get("commands") if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            return []

        out: list[dict] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            command_id = str(item.get("command_id") or "").strip().lower()
            kind = str(item.get("kind") or "python_script").strip().lower()
            entry = str(item.get("entry") or "").strip()
            if not command_id or not entry:
                continue
            if kind not in {"python_script", "python_module"}:
                continue
            fixed_args = [str(arg).strip() for arg in list(item.get("args") or []) if str(arg).strip()]
            out.append(
                {
                    "command_id": command_id,
                    "label": str(item.get("label") or command_id),
                    "description": str(item.get("description") or ""),
                    "kind": kind,
                    "entry": entry,
                    "args": fixed_args,
                    "allow_dynamic_args": bool(item.get("allow_dynamic_args", False)),
                    "enabled": bool(item.get("enabled", True)),
                    "timeout_sec": max(10, min(int(item.get("timeout_sec", 1800) or 1800), 7200)),
                }
            )
        out.sort(key=lambda row: str(row.get("label") or row.get("command_id") or ""))
        return out[: max(1, int(limit))]

    def resolve_backend_command(self, command_id: str, commands: list[dict]) -> dict | None:
        lookup = str(command_id or "").strip().lower()
        if not lookup:
            return None
        for row in list(commands or []):
            if str(row.get("command_id") or "").strip().lower() == lookup:
                return row
        return None

    @staticmethod
    def parse_backend_dynamic_args(raw: Any) -> list[str]:
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()][:24]
        text = str(raw or "").strip()
        if not text:
            return []
        tokens = re.findall(r"[^\s\"']+|\"[^\"]*\"|'[^']*'", text)
        out: list[str] = []
        for token in tokens[:24]:
            out.append(token.strip().strip("\"'").strip())
        return [item for item in out if item]

    def run_backend_command(
        self,
        command_id: str,
        payload: dict,
        *,
        commands: list[dict],
        python_bin: Path,
        base_dir: Path,
        subprocess_run=subprocess.run,
    ) -> tuple[bool, str, dict]:
        command = self.resolve_backend_command(command_id, commands)
        if not command:
            return False, "backend_command_not_found", {"available_commands": commands[:80]}
        if not bool(command.get("enabled", True)):
            return False, "backend_command_disabled", {"command": command, "available_commands": commands[:80]}

        py_bin = str(python_bin)
        kind = str(command.get("kind") or "python_script")
        entry = str(command.get("entry") or "").strip()
        fixed_args = [str(arg).strip() for arg in list(command.get("args") or []) if str(arg).strip()]
        dynamic_args = self.parse_backend_dynamic_args(payload.get("args")) if bool(command.get("allow_dynamic_args")) else []

        cmd: list[str] = []
        workspace_root = Path(base_dir).resolve()
        if kind == "python_script":
            script_path = (workspace_root / entry).resolve()
            if not script_path.exists():
                return False, "backend_command_entry_missing", {"command": command}
            if workspace_root not in script_path.parents and script_path != workspace_root:
                return False, "backend_command_entry_outside_workspace", {"command": command}
            cmd = [py_bin, str(script_path), *fixed_args, *dynamic_args]
        elif kind == "python_module":
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\.]*", entry):
                return False, "backend_command_invalid_module", {"command": command}
            cmd = [py_bin, "-m", entry, *fixed_args, *dynamic_args]
        else:
            return False, "backend_command_invalid_kind", {"command": command}

        try:
            proc = subprocess_run(
                cmd,
                cwd=str(workspace_root),
                capture_output=True,
                text=True,
                timeout=int(command.get("timeout_sec", 1800) or 1800),
            )
        except Exception as exc:
            return False, f"backend_command_run_failed:{exc}", {"command": command, "cmd": cmd}

        stdout = str(proc.stdout or "")
        stderr = str(proc.stderr or "")
        ok = proc.returncode == 0
        msg = f"backend_command_ok:{command.get('command_id')}" if ok else f"backend_command_failed:{command.get('command_id')}:exit:{proc.returncode}"
        return ok, msg, {
            "command": command,
            "cmd": cmd,
            "returncode": int(proc.returncode),
            "stdout": stdout[-12000:],
            "stderr": stderr[-12000:],
            "output": (stdout + ("\n" + stderr if stderr else ""))[-12000:],
            "available_commands": commands[:80],
        }


OPERATOR_CONTROL_SERVICE = OperatorControlService()