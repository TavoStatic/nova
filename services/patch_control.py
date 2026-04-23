from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


class PatchControlService:
    """Own patch-preview and update-now control action logic outside HTTP."""

    def patch_preview_list_action(
        self,
        *,
        patch_status_payload_fn: Callable[[], dict],
        preview_summaries_fn: Callable[[int], list[dict]],
        patch_action_readiness_payload_fn: Callable[[dict], dict],
    ) -> tuple[bool, str, dict, str]:
        patch = patch_status_payload_fn()
        previews = list(patch.get("previews") or []) if isinstance(patch.get("previews"), list) else []
        if not previews:
            previews = list(preview_summaries_fn(40) or [])
        extra = self.patch_control_state(
            patch,
            previews,
            include_readiness=True,
            readiness_payload=patch_action_readiness_payload_fn(patch),
        )
        msg = "patch_preview_list_ok"
        return True, msg, extra, msg

    @staticmethod
    def pulse_status_action(
        *,
        build_pulse_payload_fn: Callable[[], dict],
        render_nova_pulse_fn: Callable[[dict], str],
        update_now_pending_payload_fn: Callable[[], dict],
    ) -> tuple[bool, str, dict, str]:
        pulse = build_pulse_payload_fn()
        msg = "pulse_status_ok"
        return True, msg, {
            "pulse": pulse,
            "text": render_nova_pulse_fn(pulse),
            "update_now_pending": update_now_pending_payload_fn(),
        }, msg

    def patch_action_readiness_payload(
        self,
        patch_summary: dict | None = None,
        *,
        preview_summaries_fn: Callable[[int], list[dict]],
        show_preview_fn: Callable[[str], str],
        updates_dir: Path,
    ) -> dict:
        summary = dict(patch_summary or {})
        previews = list(summary.get("previews") or []) if isinstance(summary.get("previews"), list) else []
        if not previews:
            previews = list(preview_summaries_fn(40) or [])
            summary["previews"] = previews
        default_preview = str(summary.get("last_preview_name") or "").strip()
        if not default_preview and previews:
            default_preview = str((previews[0] or {}).get("name") or "").strip()

        readiness = {
            "preview_refresh": {
                "enabled": True,
                "reason": "Refresh patch preview queue state and governance telemetry.",
            },
            "default_preview": default_preview,
            "has_previews": bool(previews),
            "preview_fallback_reason": "Select a patch preview first." if previews else "No patch previews are available.",
            "by_preview": {},
        }

        for item in previews:
            name = str((item or {}).get("name") or "").strip()
            if not name:
                continue
            decision = str((item or {}).get("decision") or "pending").strip().lower() or "pending"
            status_text = str((item or {}).get("status") or "unknown").strip()
            status_low = status_text.lower()
            patch_enabled = bool(summary.get("enabled", False))
            strict_manifest = bool(summary.get("strict_manifest", False))
            behavioral_check = bool(summary.get("behavioral_check", False))
            tests_available = bool(summary.get("tests_available", False))
            zip_exists = True
            zip_reason = ""
            preview_text = show_preview_fn(name)
            zip_name = ""
            for line in str(preview_text or "").splitlines():
                if line.lower().startswith("zip:"):
                    zip_name = str(line.split(":", 1)[1] or "").strip()
                    break
            if zip_name:
                zip_path = Path(updates_dir) / zip_name
                if not zip_path.exists():
                    zip_exists = False
                    zip_reason = f"Preview references a missing patch zip: {zip_name}"

            apply_enabled = True
            apply_reason = "Approved preview is eligible for validated apply."
            if not patch_enabled:
                apply_enabled = False
                apply_reason = "Patch pipeline is disabled by policy."
            elif not strict_manifest:
                apply_enabled = False
                apply_reason = "Strict manifest validation is disabled."
            elif not behavioral_check:
                apply_enabled = False
                apply_reason = "Behavioral validation is disabled."
            elif not tests_available:
                apply_enabled = False
                apply_reason = "Behavioral tests are not available in this workspace."
            elif not zip_exists:
                apply_enabled = False
                apply_reason = zip_reason or "Preview references a missing patch zip."
            elif not status_low.startswith("eligible"):
                apply_enabled = False
                apply_reason = f"Preview is not eligible for apply: {status_text or 'unknown'}."
            elif decision != "approved":
                apply_enabled = False
                apply_reason = "Preview must be approved before apply."

            readiness["by_preview"][name] = {
                "status": status_text,
                "decision": decision,
                "zip_name": zip_name,
                "zip_exists": zip_exists,
                "show": {
                    "enabled": True,
                    "reason": "Open the preview text for inspection.",
                },
                "approve": {
                    "enabled": True,
                    "reason": (
                        "Preview is already approved; approving again updates the recorded note."
                        if decision == "approved"
                        else "Record operator approval for this preview."
                    ),
                },
                "reject": {
                    "enabled": True,
                    "reason": (
                        "Preview is already rejected; rejecting again updates the recorded note."
                        if decision == "rejected"
                        else "Record operator rejection for this preview."
                    ),
                },
                "apply": {
                    "enabled": apply_enabled,
                    "reason": apply_reason,
                },
            }

        return readiness

    @staticmethod
    def patch_preview_target(payload: dict, previews: list[dict]) -> str:
        requested = str((payload or {}).get("preview") or "").strip()
        if requested:
            return requested
        if previews:
            return str((previews[0] or {}).get("name") or "").strip()
        return ""

    @staticmethod
    def patch_preview_entry(target: str, previews: list[dict]) -> dict:
        lookup = str(target or "").strip()
        if not lookup:
            return {}
        for item in list(previews or []):
            name = str((item or {}).get("name") or "").strip()
            path = str((item or {}).get("path") or "").strip()
            if lookup == name or lookup == path:
                return dict(item)
        return {}

    @staticmethod
    def patch_control_state(
        patch_payload: dict,
        previews: list[dict],
        *,
        include_readiness: bool = True,
        readiness_payload: dict | None = None,
    ) -> dict:
        patch = patch_payload if isinstance(patch_payload, dict) else {}
        preview_rows = list(previews or [])
        if not preview_rows:
            preview_rows = list(patch.get("previews") or []) if isinstance(patch.get("previews"), list) else []
        if "previews" not in patch:
            patch["previews"] = preview_rows
        out = {
            "previews": preview_rows,
            "patch": patch,
        }
        if include_readiness:
            out["patch_action_readiness"] = dict(readiness_payload or {})
        return out

    def patch_preview_show(
        self,
        payload: dict,
        *,
        preview_target_fn: Callable[[dict], str],
        patch_control_state_fn: Callable[..., dict],
        show_preview_fn: Callable[[str], str],
    ) -> tuple[bool, str, dict, str]:
        target = preview_target_fn(payload)
        if not target:
            return False, "patch_preview_missing", patch_control_state_fn(), "patch_preview_missing"
        text = str(show_preview_fn(target) or "")
        ok = not text.startswith("Preview not found:") and not text.startswith("Failed to read preview:")
        msg = "patch_preview_show_ok" if ok else "patch_preview_show_failed"
        return ok, msg, {
            "preview": target,
            "text": text,
            **patch_control_state_fn(include_readiness=False),
        }, f"{msg}:{target}"

    def patch_preview_decision(
        self,
        action_name: str,
        payload: dict,
        *,
        preview_target_fn: Callable[[dict], str],
        patch_control_state_fn: Callable[..., dict],
        decision_fn: Callable[[str, str], str],
    ) -> tuple[bool, str, dict, str]:
        target = preview_target_fn(payload)
        if not target:
            return False, "patch_preview_missing", patch_control_state_fn(), "patch_preview_missing"
        note = str((payload or {}).get("note") or "").strip()
        result = str(decision_fn(target, note) or "")
        ok_prefix = "approved" if action_name == "approve" else "rejected"
        ok = result.strip().lower().startswith(ok_prefix)
        msg = f"patch_preview_{action_name}_ok" if ok else f"patch_preview_{action_name}_failed"
        return ok, msg, {
            "preview": target,
            "text": result,
            **patch_control_state_fn(),
        }, f"{msg}:{target}"

    def patch_preview_apply(
        self,
        payload: dict,
        *,
        preview_target_fn: Callable[[dict], str],
        preview_entry_fn: Callable[[str], dict],
        patch_control_state_fn: Callable[..., dict],
        show_preview_fn: Callable[[str], str],
        updates_dir: Path,
        patch_apply_fn: Callable[[str], str],
    ) -> tuple[bool, str, dict, str]:
        target = preview_target_fn(payload)
        if not target:
            return False, "patch_preview_missing", patch_control_state_fn(), "patch_preview_missing"

        preview_entry = preview_entry_fn(target)
        decision = str(preview_entry.get("decision") or "pending").strip().lower()
        status_text = str(preview_entry.get("status") or "").strip().lower()
        if decision != "approved":
            return False, "patch_preview_not_approved", {
                "preview": target,
                "text": "Preview must be approved before apply.",
                **patch_control_state_fn(),
            }, f"patch_preview_not_approved:{target}"
        if not status_text.startswith("eligible"):
            return False, "patch_preview_not_eligible", {
                "preview": target,
                "text": f"Preview is not eligible for apply: {status_text or 'unknown'}",
                **patch_control_state_fn(),
            }, f"patch_preview_not_eligible:{target}"

        preview_text = str(show_preview_fn(target) or "")
        zip_name = ""
        for line in preview_text.splitlines():
            if line.lower().startswith("zip:"):
                zip_name = str(line.split(":", 1)[1] or "").strip()
                break
        if not zip_name:
            return False, "patch_preview_zip_missing", {
                "preview": target,
                "text": "Preview did not contain a resolvable zip name.",
                **patch_control_state_fn(),
            }, f"patch_preview_zip_missing:{target}"

        zip_path = Path(updates_dir) / zip_name
        if not zip_path.exists():
            return False, "patch_zip_missing", {
                "preview": target,
                "text": f"Resolved patch zip not found: {zip_path}",
                **patch_control_state_fn(),
            }, f"patch_zip_missing:{zip_name}"

        result = str(patch_apply_fn(str(zip_path)) or "")
        ok = not result.strip().lower().startswith("patch rejected") and "rolled back" not in result.strip().lower()
        msg = "patch_preview_apply_ok" if ok else "patch_preview_apply_failed"
        return ok, msg, {
            "preview": target,
            "zip": str(zip_path),
            "text": result,
            **patch_control_state_fn(),
        }, f"{msg}:{target}"

    @staticmethod
    def update_now_dry_run(text: str, *, pending_payload: dict, patch_payload: dict) -> tuple[bool, str, dict]:
        body = str(text or "")
        ok = body.lower().startswith("update dry-run ready")
        msg = "update_now_dry_run_ok" if ok else "update_now_dry_run_failed"
        return ok, msg, {
            "text": body,
            "pending": dict(pending_payload or {}),
            "patch": dict(patch_payload or {}),
        }

    def update_now_dry_run_action(
        self,
        *,
        tool_update_now_fn: Callable[[], str],
        update_now_pending_payload_fn: Callable[[], dict],
        patch_status_payload_fn: Callable[[], dict],
    ) -> tuple[bool, str, dict, str]:
        ok, msg, extra = self.update_now_dry_run(
            str(tool_update_now_fn() or ""),
            pending_payload=update_now_pending_payload_fn(),
            patch_payload=patch_status_payload_fn(),
        )
        return ok, msg, extra, msg

    @staticmethod
    def update_now_confirm(text: str, *, pending_payload: dict, patch_payload: dict) -> tuple[bool, str, dict]:
        body = str(text or "")
        ok = body.lower().startswith("patch applied:")
        msg = "update_now_confirm_ok" if ok else "update_now_confirm_failed"
        return ok, msg, {
            "text": body,
            "pending": dict(pending_payload or {}),
            "patch": dict(patch_payload or {}),
        }

    def update_now_confirm_action(
        self,
        payload: dict,
        *,
        tool_update_now_confirm_fn: Callable[[str], str],
        update_now_pending_payload_fn: Callable[[], dict],
        patch_status_payload_fn: Callable[[], dict],
    ) -> tuple[bool, str, dict, str]:
        token = str(payload.get("token") or "").strip()
        ok, msg, extra = self.update_now_confirm(
            str(tool_update_now_confirm_fn(token) or ""),
            pending_payload=update_now_pending_payload_fn(),
            patch_payload=patch_status_payload_fn(),
        )
        return ok, msg, extra, msg

    @staticmethod
    def update_now_cancel(text: str, *, pending_payload: dict) -> tuple[bool, str, dict]:
        return True, "update_now_cancel_ok", {
            "text": str(text or ""),
            "pending": dict(pending_payload or {}),
        }

    def update_now_cancel_action(
        self,
        *,
        tool_update_now_cancel_fn: Callable[[], str],
        update_now_pending_payload_fn: Callable[[], dict],
    ) -> tuple[bool, str, dict, str]:
        ok, msg, extra = self.update_now_cancel(
            str(tool_update_now_cancel_fn() or ""),
            pending_payload=update_now_pending_payload_fn(),
        )
        return ok, msg, extra, msg


PATCH_CONTROL_SERVICE = PatchControlService()