from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

from .base_tool import NovaTool, ToolContext, ToolInvocationError
from services.patch_promotion_memory import PATCH_PROMOTION_MEMORY_SERVICE


_ALLOWED_EXTENSIONS = {".py", ".md", ".json", ".html", ".css", ".js", ".txt"}
_MAX_FILES_DEFAULT = 8
_MAX_PATH_LENGTH = 140


def _norm_text(value: object) -> str:
    return str(value or "").strip()


def _safe_path(value: object) -> str:
    raw = _norm_text(value).replace("\\", "/")
    if not raw:
        raise ToolInvocationError("codegen_spec_path_missing")
    if len(raw) > _MAX_PATH_LENGTH:
        raise ToolInvocationError("codegen_spec_path_too_long")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ToolInvocationError("codegen_spec_path_outside_allowed_root")
    if path.suffix.lower() not in _ALLOWED_EXTENSIONS:
        raise ToolInvocationError("codegen_spec_path_extension_not_allowed")
    return path.as_posix()


def _validate_spec(spec: dict[str, Any], max_files: int) -> tuple[str, str, list[dict[str, str]]]:
    name = _norm_text(spec.get("name"))
    purpose = _norm_text(spec.get("purpose"))
    if not name:
        raise ToolInvocationError("codegen_spec_name_missing")
    if not purpose:
        raise ToolInvocationError("codegen_spec_purpose_missing")
    files_raw = spec.get("files") if isinstance(spec.get("files"), list) else []
    if not files_raw:
        raise ToolInvocationError("codegen_spec_files_missing")
    if len(files_raw) > max_files:
        raise ToolInvocationError("codegen_spec_too_many_files")
    files: list[dict[str, str]] = []
    for item in files_raw:
        if not isinstance(item, dict):
            raise ToolInvocationError("codegen_spec_file_invalid")
        path = _safe_path(item.get("path"))
        kind = _norm_text(item.get("kind") or "module").lower()
        intent = _norm_text(item.get("intent") or item.get("purpose") or "")
        files.append({"path": path, "kind": kind, "intent": intent})
    return name, purpose, files


def _render_preview_content(path: str, spec_name: str, spec_purpose: str, kind: str, intent: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    short_intent = intent or f"Implement {spec_name} behavior."
    if suffix == ".py":
        class_name = "".join(part.title() for part in PurePosixPath(path).stem.split("_") if part) or "Generated"
        return (
            f'"""Generated module for {spec_name}.\n'
            f"Purpose: {spec_purpose}\n"
            f"Intent: {short_intent}\n"
            '"""\n\n'
            "from __future__ import annotations\n\n\n"
            f"class {class_name}Service:\n"
            "    def describe(self) -> dict[str, str]:\n"
            f"        return {{'spec': {json.dumps(spec_name)}, 'kind': {json.dumps(kind)}, 'path': {json.dumps(path)}}}\n\n"
            "    def run(self, payload: dict[str, object] | None = None) -> dict[str, object]:\n"
            f"        intent = {json.dumps(short_intent)}\n"
            "        data = dict(payload or {})\n"
            "        return {\n"
            "            'ok': False,\n"
            "            'status': 'preview_only',\n"
            "            'spec': self.describe(),\n"
            "            'intent': intent,\n"
            "            'payload_keys': sorted(str(key) for key in data.keys()),\n"
            "            'next_step': 'implement run() before promotion',\n"
            "        }\n"
        )
    if suffix == ".json":
        payload = {
            "schema": "nova.codegen.preview.file.v1",
            "spec": spec_name,
            "purpose": spec_purpose,
            "intent": short_intent,
            "kind": kind,
            "path": path,
        }
        return json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
    if suffix in {".html", ".css", ".js"}:
        return (
            f"/* Generated preview for {spec_name}.\n"
            f"Purpose: {spec_purpose}\n"
            f"Intent: {short_intent}\n"
            "Preview-only artifact. */\n"
        )
    return (
        f"# Generated preview for {spec_name}\n"
        f"Purpose: {spec_purpose}\n"
        f"Intent: {short_intent}\n"
        "Status: preview-only\n"
    )


class CodegenTool(NovaTool):
    name = "codegen"
    description = "Generate preview-only code artifacts from a structured spec under governance constraints"
    category = "generation"
    safe = False
    requires_admin = True
    locality = "local"
    mutating = False
    scope = "system"

    def check_policy(self, args: dict[str, Any], context: ToolContext) -> tuple[bool, str]:
        ok, reason = super().check_policy(args, context)
        if not ok:
            return ok, reason
        tools = (context.policy.get("tools_enabled") or {}) if isinstance(context.policy, dict) else {}
        codegen_cfg = (context.policy.get("codegen") or {}) if isinstance(context.policy, dict) else {}
        if not bool(tools.get("codegen", False)) or not bool(codegen_cfg.get("enabled", False)):
            return False, "codegen_tool_disabled"
        action = _norm_text(args.get("action")).lower()
        if action != "preview":
            return False, "unknown_codegen_action"
        return True, ""

    def run(self, args: dict[str, Any], context: ToolContext) -> str:
        action = _norm_text(args.get("action")).lower()
        if action != "preview":
            raise ToolInvocationError("unknown_codegen_action")
        spec = args.get("spec") if isinstance(args.get("spec"), dict) else {}
        max_files = int(args.get("max_files", _MAX_FILES_DEFAULT) or _MAX_FILES_DEFAULT)
        if max_files <= 0:
            raise ToolInvocationError("codegen_spec_too_many_files")

        name, purpose, files = _validate_spec(spec, max_files)
        
        # Get prior patterns from memory for pattern injection
        memory_context = ""
        try:
            memory_context = PATCH_PROMOTION_MEMORY_SERVICE.get_memory_injection(name, purpose)
        except Exception:
            # Graceful degradation: if memory lookup fails, continue without injection
            pass
        
        prompt_payload = {
            "name": name,
            "purpose": purpose,
            "files": files,
            "constraints": {
                "preview_only": True,
                "apply_allowed": False,
                "allowed_extensions": sorted(_ALLOWED_EXTENSIONS),
                "max_files": max_files,
            },
        }
        
        # Include memory injection context if patterns found
        if memory_context:
            prompt_payload["prior_patterns_context"] = memory_context
        
        prompt_json = json.dumps(prompt_payload, ensure_ascii=True, sort_keys=True)
        prompt_hash = hashlib.sha256(prompt_json.encode("utf-8")).hexdigest()

        artifacts = []
        for item in files:
            artifacts.append(
                {
                    "path": item["path"],
                    "kind": item["kind"],
                    "intent": item["intent"],
                    "content": _render_preview_content(item["path"], name, purpose, item["kind"], item["intent"]),
                }
            )

        payload = {
            "schema": "nova.codegen.preview.v1",
            "status": "preview",
            "preview_only": True,
            "apply_allowed": False,
            "spec": {
                "name": name,
                "purpose": purpose,
                "file_count": len(files),
            },
            "artifacts": artifacts,
            "provenance": {
                "generator": "codegen_tool",
                "model": _norm_text((context.policy.get("models") or {}).get("chat")) if isinstance(context.policy, dict) else "",
                "prompt_hash": prompt_hash,
            },
        }
        
        # Include memory injection in final payload if available
        if memory_context:
            payload["prior_patterns_context"] = memory_context
        
        return json.dumps(payload, ensure_ascii=True)
