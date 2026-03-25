from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_USER_ID = "operator"
ROOT = Path(__file__).resolve().parent.parent
OPERATOR_MACROS_PATH = ROOT / "operator_macros.json"


def _headers(control_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = str(control_key or "").strip()
    if key:
        headers["X-Nova-Control-Key"] = key
    return headers


def _parse_macro_values(items: list[str] | None) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in list(items or []):
        raw = str(item or "").strip()
        if not raw:
            continue
        name, sep, value = raw.partition("=")
        key = name.strip()
        if not sep or not key:
            raise ValueError(f"Invalid macro value '{item}'. Use name=value.")
        values[key] = value.strip()
    return values


def _send_operator_prompt(
    base_url: str,
    control_key: str,
    session_id: str,
    user_id: str,
    message: str,
    *,
    macro_id: str = "",
    macro_values: dict[str, str] | None = None,
    source: str = "cli",
) -> dict[str, Any]:
    response = requests.post(
        base_url.rstrip("/") + "/api/control/action",
        headers=_headers(control_key),
        json={
            "action": "operator_prompt",
            "session_id": session_id,
            "user_id": user_id,
            "message": message,
            "macro": str(macro_id or "").strip(),
            "macro_values": dict(macro_values or {}),
            "source": str(source or "cli").strip() or "cli",
        },
        timeout=180,
    )
    payload = response.json()
    if not response.ok or not payload.get("ok"):
        raise RuntimeError(str(payload.get("message") or payload.get("error") or f"HTTP {response.status_code}"))
    return payload


def _load_operator_macros() -> list[dict[str, Any]]:
    if not OPERATOR_MACROS_PATH.exists():
        return []
    try:
        payload = json.loads(OPERATOR_MACROS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw_macros = payload.get("macros") if isinstance(payload, dict) else payload
    if not isinstance(raw_macros, list):
        return []
    macros: list[dict[str, Any]] = []
    for item in raw_macros:
        if not isinstance(item, dict):
            continue
        macro_id = str(item.get("macro_id") or "").strip()
        prompt = str(item.get("prompt") or "").strip()
        prompt_template = str(item.get("prompt_template") or "").strip()
        placeholders = item.get("placeholders") if isinstance(item.get("placeholders"), list) else []
        if not macro_id or not (prompt or prompt_template):
            continue
        macros.append(
            {
                "macro_id": macro_id,
                "label": str(item.get("label") or macro_id),
                "prompt": prompt,
                "prompt_template": prompt_template,
                "placeholders": [dict(entry) for entry in placeholders if isinstance(entry, dict)],
                "tags": [str(tag).strip() for tag in list(item.get("tags") or []) if str(tag).strip()],
            }
        )
    return macros


def _resolve_operator_macro(macro_id: str) -> dict[str, Any] | None:
    lookup = str(macro_id or "").strip()
    if not lookup:
        return None
    for item in _load_operator_macros():
        if str(item.get("macro_id") or "") == lookup:
            return item
    return None


def _print_reply(payload: dict[str, Any]) -> None:
    session_id = str(payload.get("session_id") or "")
    reply = str(payload.get("reply") or payload.get("message") or "").strip()
    print(f"\n[session {session_id}]", flush=True)
    print(reply or "(no reply)", flush=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local operator CLI for Nova control prompts.")
    parser.add_argument("message", nargs="*", help="Optional one-shot operator prompt")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Nova Web UI base URL")
    parser.add_argument("--key", default=os.environ.get("NOVA_CONTROL_KEY", ""), help="Control key; defaults to NOVA_CONTROL_KEY")
    parser.add_argument("--session", default="", help="Operator session id to reuse")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="Operator user id label")
    parser.add_argument("--new-session", action="store_true", help="Force a fresh operator session id")
    parser.add_argument("--macro", default="", help="Run a saved operator macro by id")
    parser.add_argument("--macro-value", action="append", default=[], help="Macro placeholder value as name=value; repeat as needed")
    parser.add_argument("--list-macros", action="store_true", help="List available operator macros and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    session_id = str(args.session or "").strip()
    if args.new_session or not session_id:
        session_id = f"operator-cli-{secrets.token_hex(6)}"
    user_id = str(args.user_id or DEFAULT_USER_ID).strip() or DEFAULT_USER_ID
    base_url = str(args.base_url or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    control_key = str(args.key or "")
    one_shot = " ".join(str(part) for part in list(args.message or []) if str(part).strip()).strip()
    macro = _resolve_operator_macro(str(args.macro or "")) if str(args.macro or "").strip() else None
    try:
        macro_values = _parse_macro_values(args.macro_value)
    except ValueError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    if args.list_macros:
        macros = _load_operator_macros()
        if not macros:
            print("No operator macros found.", flush=True)
            return 0
        for item in macros:
            tags = ", ".join(item.get("tags") or [])
            field_count = len(item.get("placeholders") or [])
            suffix = f" ({field_count} fields)" if field_count else ""
            print(f"{item.get('macro_id')}: {item.get('label')}{suffix}{' [' + tags + ']' if tags else ''}", flush=True)
        return 0

    if str(args.macro or "").strip() and macro is None:
        print(f"[FAIL] Unknown macro: {args.macro}", file=sys.stderr)
        return 1

    if one_shot or macro is not None:
        try:
            payload = _send_operator_prompt(
                base_url,
                control_key,
                session_id,
                user_id,
                one_shot,
                macro_id=str(args.macro or ""),
                macro_values=macro_values,
                source="cli",
            )
        except Exception as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1
        _print_reply(payload)
        return 0

    print("Nova operator CLI", flush=True)
    print(f"Base URL : {base_url}", flush=True)
    print(f"Session  : {session_id}", flush=True)
    print("Type /new for a fresh session, /quit to exit, /macros to list saved macros.", flush=True)

    while True:
        try:
            text = input("operator> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("", flush=True)
            return 0
        if not text:
            continue
        if text.lower() in {"/quit", "/exit", "q"}:
            return 0
        if text.lower() == "/new":
            session_id = f"operator-cli-{secrets.token_hex(6)}"
            print(f"[session] {session_id}", flush=True)
            continue
        if text.lower() == "/macros":
            macros = _load_operator_macros()
            if not macros:
                print("No operator macros found.", flush=True)
                continue
            for item in macros:
                tags = ", ".join(item.get("tags") or [])
                field_count = len(item.get("placeholders") or [])
                suffix = f" ({field_count} fields)" if field_count else ""
                print(f"{item.get('macro_id')}: {item.get('label')}{suffix}{' [' + tags + ']' if tags else ''}", flush=True)
            continue
        try:
            payload = _send_operator_prompt(base_url, control_key, session_id, user_id, text, source="cli")
        except Exception as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            continue
        session_id = str(payload.get("session_id") or session_id)
        _print_reply(payload)


if __name__ == "__main__":
    raise SystemExit(main())
