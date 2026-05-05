from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional


def read_update_now_pending(pending_file: Path, *, load_json_file_fn: Callable[[Path, object], object]) -> dict:
    return load_json_file_fn(pending_file, {}) if pending_file.exists() else {}


def write_update_now_pending(pending_file: Path, payload: dict) -> None:
    try:
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        pending_file.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception:
        return


def clear_update_now_pending(pending_file: Path) -> None:
    try:
        if pending_file.exists():
            pending_file.unlink()
    except Exception:
        return


def update_now_pending_payload(pending_file: Path, *, read_pending_fn: Callable[[], dict]) -> dict:
    data = read_pending_fn()
    if not isinstance(data, dict) or not data:
        return {"ok": False, "pending": False}
    return {
        "ok": True,
        "pending": True,
        "created_at": str(data.get("created_at") or ""),
        "token": str(data.get("token") or ""),
        "zip_path": str(data.get("zip_path") or ""),
        "preview_status": str(data.get("preview_status") or ""),
    }


def build_update_now_token(zip_path: Path) -> str:
    seed = f"{str(zip_path)}|{time.time()}|{os.getpid()}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]


def extract_preview_status(preview_text: str) -> str:
    match = re.search(r"^Status:\s*(.+)$", str(preview_text or ""), flags=re.M)
    return str(match.group(1) or "").strip() if match else "unknown"


def extract_preview_zip(preview_text: str) -> str:
    match = re.search(r"^Zip:\s*(.+)$", str(preview_text or ""), flags=re.M)
    return str(match.group(1) or "").strip() if match else ""


def tool_update_now(
    *,
    patch_status_payload_fn: Callable[[], dict],
    latest_approved_update_zip_fn: Callable[[Optional[dict]], Optional[Path]],
    patch_preview_fn: Callable[..., str],
    clear_pending_fn: Callable[[], None],
    write_pending_fn: Callable[[dict], None],
    build_token_fn: Callable[[Path], str] = build_update_now_token,
) -> str:
    patch_payload = patch_status_payload_fn()
    zip_path = latest_approved_update_zip_fn(patch_payload)
    if zip_path is None:
        clear_pending_fn()
        return "No approved validated update is queued right now. Run pulse to inspect the current update pipeline."

    preview_text = patch_preview_fn(str(zip_path), write_report=False)
    preview_status = extract_preview_status(preview_text)
    if not str(preview_status or "").lower().startswith("eligible"):
        clear_pending_fn()
        return (
            "Update candidate is not eligible after dry-run preview.\n"
            f"- zip: {zip_path}\n"
            f"- status: {preview_status or 'unknown'}\n"
            "Update not applied."
        )

    token = build_token_fn(zip_path)
    write_pending_fn(
        {
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "token": token,
            "zip_path": str(zip_path),
            "preview_status": preview_status,
            "preview_zip": extract_preview_zip(preview_text),
        }
    )
    return (
        "Update dry-run ready.\n"
        f"- zip: {zip_path}\n"
        f"- status: {preview_status}\n"
        f"Confirm with: update now confirm {token}\n"
        "Cancel with: update now cancel"
    )


def tool_update_now_confirm(
    token: str = "",
    *,
    read_pending_fn: Callable[[], dict],
    clear_pending_fn: Callable[[], None],
    patch_status_payload_fn: Callable[[], dict],
    latest_approved_update_zip_fn: Callable[[Optional[dict]], Optional[Path]],
    execute_patch_action_fn: Callable[..., str],
) -> str:
    pending = read_pending_fn()
    if not isinstance(pending, dict) or not pending:
        return "No pending update confirmation. Start with: update now"

    expected_token = str(pending.get("token") or "").strip()
    provided_token = str(token or "").strip()
    if not provided_token:
        return f"Confirmation token required. Run: update now confirm {expected_token}"
    if expected_token and provided_token != expected_token:
        return "Confirmation token mismatch. Run update now again to refresh the token."

    zip_path_text = str(pending.get("zip_path") or "").strip()
    if not zip_path_text:
        clear_pending_fn()
        return "Pending update payload is invalid. Run update now to regenerate the dry-run confirmation."
    zip_path = Path(zip_path_text)
    if not zip_path.exists():
        clear_pending_fn()
        return f"Update package is missing: {zip_path}. Run update now to regenerate the dry-run confirmation."

    patch_payload = patch_status_payload_fn()
    latest_zip = latest_approved_update_zip_fn(patch_payload)
    if latest_zip is None or str(latest_zip) != str(zip_path):
        clear_pending_fn()
        return "Approved update candidate changed. Run update now again before confirming."

    out = execute_patch_action_fn("apply", str(zip_path), is_admin=True)
    if str(out or "").lower().startswith("patch applied:"):
        clear_pending_fn()
    return str(out or "")


def tool_update_now_cancel(*, read_pending_fn: Callable[[], dict], clear_pending_fn: Callable[[], None]) -> str:
    had_pending = bool(read_pending_fn())
    clear_pending_fn()
    if had_pending:
        return "Canceled pending update confirmation."
    return "No pending update confirmation was active."
