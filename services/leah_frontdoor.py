from __future__ import annotations

import base64
import mimetypes
import re
import time
from pathlib import Path
from typing import Any, Callable


class LeahFrontdoorService:
    """Own LEAH front-door asset rendering, ingest, and recent handoff context."""

    _TEXT_SUFFIXES = {
        ".txt",
        ".md",
        ".json",
        ".csv",
        ".tsv",
        ".py",
        ".ps1",
        ".js",
        ".html",
        ".css",
        ".yml",
        ".yaml",
        ".toml",
        ".ini",
        ".xml",
        ".sql",
        ".log",
    }

    def __init__(
        self,
        *,
        asset_service: Any,
        template_path_provider: Callable[[], Path],
        css_path_provider: Callable[[], Path],
        js_path_provider: Callable[[], Path],
        fx_js_path_provider: Callable[[], Path] | None = None,
        upload_root_provider: Callable[[], Path],
        upload_max_items: int = 6,
        upload_max_bytes: int = 8 * 1024 * 1024,
        context_ttl_seconds: int = 30 * 60,
    ) -> None:
        self._asset_service = asset_service
        self._template_path_provider = template_path_provider
        self._css_path_provider = css_path_provider
        self._js_path_provider = js_path_provider
        self._fx_js_path_provider = fx_js_path_provider
        self._upload_root_provider = upload_root_provider
        self._upload_max_items = int(upload_max_items)
        self._upload_max_bytes = int(upload_max_bytes)
        self._context_ttl_seconds = int(context_ttl_seconds)
        self._session_context: dict[str, dict[str, Any]] = {}

    def render_html(self) -> str:
        template_path = self._template_path_provider()
        css_path = self._css_path_provider()
        js_path = self._js_path_provider()
        html = self._asset_service.read_asset_text(template_path)
        html = html.replace("{{LEAH_BUILD_VERSION}}", self._asset_service.asset_version_token(template_path))
        html = html.replace("{{LEAH_CSS_VERSION}}", self._asset_service.asset_version_token(css_path))
        html = html.replace("{{LEAH_JS_VERSION}}", self._asset_service.asset_version_token(js_path))
        if self._fx_js_path_provider is not None:
            html = html.replace(
                "{{LEAH_FX_JS_VERSION}}",
                self._asset_service.asset_version_token(self._fx_js_path_provider()),
            )
        return html

    def clear_session_context(self) -> None:
        self._session_context.clear()

    def _safe_filename(self, name: str, *, mime: str = "", source: str = "") -> str:
        raw = Path(str(name or "").strip() or f"{source or 'asset'}").name
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(raw).stem).strip("._-") or "asset"
        suffix = str(Path(raw).suffix or "").strip()
        if not suffix:
            guessed = mimetypes.guess_extension(str(mime or "").split(";")[0].strip().lower())
            suffix = guessed or (".png" if str(source or "").strip().lower() == "camera" else ".bin")
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        return f"{stem[:64]}{suffix[:12]}"

    def _session_upload_dir(self, session_id: str) -> Path:
        safe_session = re.sub(r"[^A-Za-z0-9_-]+", "", str(session_id or "").strip()) or "session"
        path = self._upload_root_provider() / safe_session
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ingest_items(self, session_id: str, user_id: str, items: list[dict]) -> list[dict]:
        stored: list[dict] = []
        target_dir = self._session_upload_dir(session_id)
        for index, item in enumerate(list(items or [])[: self._upload_max_items], start=1):
            if not isinstance(item, dict):
                continue
            content_b64 = str(item.get("content_b64") or "").strip()
            if not content_b64:
                continue
            try:
                payload = base64.b64decode(content_b64, validate=True)
            except Exception:
                continue
            if not payload or len(payload) > self._upload_max_bytes:
                continue
            source = str(item.get("source") or "upload").strip().lower() or "upload"
            mime = str(item.get("mime") or "application/octet-stream").strip()
            safe_name = self._safe_filename(str(item.get("name") or f"{source}_{index}"), mime=mime, source=source)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            out = target_dir / f"{stamp}_{index:02d}_{safe_name}"
            out.write_bytes(payload)
            stored.append(
                {
                    "name": safe_name,
                    "original_name": str(item.get("name") or safe_name).strip() or safe_name,
                    "path": str(out),
                    "bytes": len(payload),
                    "mime": mime,
                    "source": source,
                    "uploaded_at": int(time.time()),
                    "session_id": session_id,
                    "user_id": user_id,
                }
            )
        return stored

    def compose_chat_message(self, message: str, attachments: list[dict]) -> str:
        text = str(message or "").strip()
        usable = [dict(item or {}) for item in list(attachments or []) if isinstance(item, dict)]
        if not usable:
            return text
        lines = [
            text,
            "",
            "[LEAH session context]",
            "The user staged the following local items for this turn.",
            "Treat these local items as the primary context for the turn when the user is asking about them.",
            "If the user asks whether you can read, inspect, review, or summarize them, answer that directly instead of switching to a generic planning reply.",
        ]
        for item in usable[: self._upload_max_items]:
            name = str(item.get("original_name") or item.get("name") or "item").strip() or "item"
            source = str(item.get("source") or "upload").strip() or "upload"
            path = str(item.get("path") or "").strip()
            mime = str(item.get("mime") or "").strip()
            size = int(item.get("bytes") or 0)
            detail = f"- {source}: {name}"
            if mime:
                detail += f" | {mime}"
            if size > 0:
                detail += f" | {size} bytes"
            if path:
                detail += f" | path={path}"
            lines.append(detail)
        return "\n".join(lines).strip()

    def _prune_session_context(self, *, now: float | None = None) -> None:
        current = float(now if now is not None else time.time())
        stale = [
            str(session_id)
            for session_id, payload in list(self._session_context.items())
            if current - float((payload or {}).get("ts") or 0.0) > self._context_ttl_seconds
        ]
        for session_id in stale:
            self._session_context.pop(session_id, None)

    def remember_session_context(self, session_id: str, items: list[dict], *, stage: str) -> None:
        safe_session = str(session_id or "").strip()
        usable = [dict(item or {}) for item in list(items or []) if isinstance(item, dict)]
        if not safe_session or not usable:
            return
        self._prune_session_context()
        self._session_context[safe_session] = {
            "ts": time.time(),
            "stage": str(stage or "").strip().lower() or "staged",
            "items": usable[: self._upload_max_items],
        }

    def recent_session_context(self, session_id: str) -> tuple[list[dict], str]:
        safe_session = str(session_id or "").strip()
        if not safe_session:
            return [], ""
        self._prune_session_context()
        payload = self._session_context.get(safe_session)
        if not isinstance(payload, dict):
            return [], ""
        items = [dict(item or {}) for item in list(payload.get("items") or []) if isinstance(item, dict)]
        stage = str(payload.get("stage") or "").strip().lower()
        return items[: self._upload_max_items], stage

    def _attachment_intent(self, message: str, attachments: list[dict]) -> bool:
        usable = [dict(item or {}) for item in list(attachments or []) if isinstance(item, dict)]
        if not usable:
            return False
        normalized = " ".join(str(message or "").strip().lower().split())
        if not normalized:
            return True
        cues = (
            "read it",
            "read this",
            "can you read",
            "can you see",
            "look at it",
            "look at this",
            "inspect it",
            "inspect this",
            "review it",
            "review this",
            "summarize it",
            "summarize this",
            "what did i upload",
            "did you get",
            "open it",
            "open this",
            "can you open",
            "what do you see",
        )
        return any(cue in normalized for cue in cues)

    def _text_preview(self, path_text: str) -> str:
        path = Path(str(path_text or "").strip())
        if not path.exists() or not path.is_file():
            return ""
        suffix = path.suffix.lower()
        if suffix not in self._TEXT_SUFFIXES:
            return ""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""
        snippet = " ".join(text.lstrip("\ufeff").strip().split())
        if not snippet:
            return ""
        if len(snippet) > 280:
            return f"{snippet[:277]}..."
        return snippet

    def maybe_answer_attachment_turn(
        self,
        message: str,
        attachments: list[dict],
        *,
        recent_items: list[dict] | None = None,
        recent_stage: str = "",
    ) -> str | None:
        usable = [dict(item or {}) for item in list(attachments or []) if isinstance(item, dict)]
        fallback_items = [dict(item or {}) for item in list(recent_items or []) if isinstance(item, dict)]
        active_items = usable or fallback_items
        if not self._attachment_intent(message, active_items):
            return None
        first = active_items[0]
        total = len(active_items)
        name = str(first.get("original_name") or first.get("name") or "item").strip() or "item"
        source = str(first.get("source") or "upload").strip() or "upload"
        mime = str(first.get("mime") or "").strip()
        path_text = str(first.get("path") or "").strip()
        preview = self._text_preview(path_text)
        if usable:
            header = f"Yes. I have {total} staged item{'s' if total != 1 else ''} for this turn."
        elif str(recent_stage or "").strip().lower() == "handoff":
            header = f"Yes. I still have the last {total} item{'s' if total != 1 else ''} you handed to Nova in this session."
        else:
            header = f"Yes. I still have {total} staged item{'s' if total != 1 else ''} waiting in this session."
        if preview:
            return (
                f"{header} The first one is {name} ({mime or 'text'}). "
                f"I can read it directly. Preview: {preview}"
            )
        if mime.startswith("image/") or source == "camera":
            return (
                f"{header} I have the image {name} staged from {source}. "
                "I can work from that local image next if you want a description or visible-text pass."
            )
        if path_text:
            return (
                f"{header} I have {name} staged locally at {path_text}. "
                "Tell me whether you want a summary, review, extraction, or a closer inspection."
            )
        return f"{header} Tell me what you want me to do with it next."
