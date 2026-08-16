from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from .base_tool import NovaTool, ToolContext, ToolInvocationError
from .codegen_tool import CodegenTool
from .filesystem_tool import FileSystemTool
from .os_capability_tool import OsCapabilityTool
from .patch_tool import PatchTool
from .research_tool import ResearchTool
from .temporal_review_tool import TemporalReviewTool
from .system_tool import SystemTool
from .vision_tool import VisionTool
from services.core_health_brief import feed_core_health_brief_to_work_tree as service_feed_core_health_brief_to_work_tree
from services.core_health_brief import render_core_health_brief as service_render_core_health_brief
from services.core_health_brief import write_core_health_brief as service_write_core_health_brief
from services.core_thinning import build_core_thinning_brief as service_build_core_thinning_brief
from services.core_thinning import execute_core_thinning_order as service_execute_core_thinning_order
from services.core_thinning import feed_core_thinning_brief_to_work_tree as service_feed_core_thinning_brief_to_work_tree
from services.core_thinning import render_core_thinning_brief as service_render_core_thinning_brief
from services.data_pipeline_registry import get_pipeline_schema_probe as service_get_pipeline_schema_probe
from services.data_pipeline_registry import get_pipeline_status as service_get_pipeline_status
from services.data_pipeline_registry import list_pipeline_summaries as service_list_pipeline_summaries
from services.data_pipeline_registry import plan_pipeline_report as service_plan_pipeline_report
from services.data_pipeline_registry import preview_pipeline_query as service_preview_pipeline_query
from services.data_pipeline_registry import search_pipeline_vendor_dictionary as service_search_pipeline_vendor_dictionary
from services.nova_pipeline_tools import handle_pipeline_command as service_handle_pipeline_command
from services.nova_pulse import tool_nova_pulse as service_tool_nova_pulse
from services.nova_self_status import build_self_status_payload as service_build_self_status_payload
from services.nova_self_status import build_repo_change_snapshot as service_build_repo_change_snapshot
from services.nova_self_status import read_recent_ops_events as service_read_recent_ops_events
from services.nova_self_status import render_self_status as service_render_self_status
from services.nova_runtime_context import BASE_DIR
from services.nova_runtime_context import TOOL_EVENTS_FILE
from services.nova_update_now import tool_update_now as service_tool_update_now
from services.nova_update_now import tool_update_now_cancel as service_tool_update_now_cancel
from services.nova_update_now import tool_update_now_confirm as service_tool_update_now_confirm
from services.nova_web_tools import tool_search as service_tool_search
from services.nova_web_tools import tool_stackexchange_search as service_tool_stackexchange_search
from services.nova_web_tools import tool_web_fetch as service_tool_web_fetch
from services.nova_web_tools import tool_web_gather as service_tool_web_gather
from services.nova_web_tools import tool_web_research as service_tool_web_research
from services.nova_web_tools import tool_web_search as service_tool_web_search
from services.nova_web_tools import tool_wikipedia_lookup as service_tool_wikipedia_lookup
from services.patch_control import PATCH_CONTROL_SERVICE
from services.pipeline_privileged_bridge import run_privileged_pipeline_query as service_run_privileged_pipeline_query


TOOL_MANIFEST_PATH = BASE_DIR / "TOOL_MANIFEST.json"
TOOL_EVENTS_PATH = TOOL_EVENTS_FILE


def _load_manifest() -> dict[str, Any]:
    if not TOOL_MANIFEST_PATH.exists():
        return {}
    try:
        data = json.loads(TOOL_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _append_tool_event(payload: dict[str, Any]) -> None:
    try:
        TOOL_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TOOL_EVENTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


class ToolRegistry:
    def __init__(self, tools: list[NovaTool]):
        self._tools = {tool.name: tool for tool in tools}
        self._manifest = _load_manifest()

    def get(self, name: str) -> NovaTool | None:
        return self._tools.get(str(name or "").strip())

    def list_metadata(self) -> list[dict[str, Any]]:
        manifest_tools = self._manifest.get("tools") if isinstance(self._manifest.get("tools"), list) else []
        manifest_by_name = {str(item.get("name") or "").strip(): item for item in manifest_tools if isinstance(item, dict)}
        out = []
        for name in sorted(self._tools.keys()):
            tool = self._tools[name]
            meta = tool.metadata()
            manifest = manifest_by_name.get(name, {})
            if manifest:
                meta["manifest"] = manifest
            out.append(meta)
        return out

    def describe(self) -> str:
        lines = ["Available Nova tools:"]
        for meta in self.list_metadata():
            flags = []
            if meta.get("safe"):
                flags.append("safe")
            if meta.get("requires_admin"):
                flags.append("admin")
            flags.append(str(meta.get("locality") or "local"))
            flags.append("mutating" if meta.get("mutating") else "read-only")
            flags.append(str(meta.get("scope") or "user"))
            flag_text = f" [{' '.join(flags)}]" if flags else ""
            lines.append(f"- {meta['name']}: {meta['description']}{flag_text}")
        return "\n".join(lines)

    def run_tool(self, name: str, args: dict[str, Any], context: ToolContext) -> Any:
        tool = self.get(name)
        if not tool:
            raise ToolInvocationError("unknown_tool")

        started = time.time()
        ok, reason = tool.check_policy(args, context)
        meta = tool.metadata()
        if not ok:
            payload = {
                "event": "tool_invocation",
                "tool": tool.name,
                "user": context.user_id,
                "session": context.session_id,
                "status": "denied",
                "reason": reason,
                "safe": bool(meta.get("safe")),
                "requires_admin": bool(meta.get("requires_admin")),
                "locality": str(meta.get("locality") or "local"),
                "mutating": bool(meta.get("mutating")),
                "scope": str(meta.get("scope") or "user"),
                "args": sorted(list((args or {}).keys())),
                "ts": int(time.time()),
            }
            _append_tool_event(payload)
            raise ToolInvocationError(reason)

        try:
            result = tool.run(args or {}, context)
            payload = {
                "event": "tool_invocation",
                "tool": tool.name,
                "user": context.user_id,
                "session": context.session_id,
                "status": "ok",
                "safe": bool(meta.get("safe")),
                "requires_admin": bool(meta.get("requires_admin")),
                "locality": str(meta.get("locality") or "local"),
                "mutating": bool(meta.get("mutating")),
                "scope": str(meta.get("scope") or "user"),
                "args": sorted(list((args or {}).keys())),
                "duration_ms": int((time.time() - started) * 1000),
                "ts": int(time.time()),
            }
            _append_tool_event(payload)
            return result
        except Exception as e:
            payload = {
                "event": "tool_invocation",
                "tool": tool.name,
                "user": context.user_id,
                "session": context.session_id,
                "status": "error",
                "error": str(e),
                "safe": bool(meta.get("safe")),
                "requires_admin": bool(meta.get("requires_admin")),
                "locality": str(meta.get("locality") or "local"),
                "mutating": bool(meta.get("mutating")),
                "scope": str(meta.get("scope") or "user"),
                "args": sorted(list((args or {}).keys())),
                "duration_ms": int((time.time() - started) * 1000),
                "ts": int(time.time()),
            }
            _append_tool_event(payload)
            raise


def _optional_data_connector_tool() -> NovaTool | None:
    """Backpack explore tool is optional — Nova core must boot without a dropped-in pack."""
    try:
        from .edfi_tool import DataConnectorExploreTool

        return DataConnectorExploreTool()
    except Exception:
        pass
    try:
        from .edfi_tool import EdFiExploreTool

        return EdFiExploreTool()
    except Exception:
        return None


def build_default_registry() -> ToolRegistry:
    tools: list[NovaTool] = [
        FileSystemTool(),
        CodegenTool(),
        PatchTool(),
        VisionTool(),
        ResearchTool(),
        SystemTool(),
        OsCapabilityTool(),
        TemporalReviewTool(),
    ]
    connector = _optional_data_connector_tool()
    if connector is not None:
        tools.append(connector)
    return ToolRegistry(tools)


def build_core_tool_exports(runtime_scope: dict[str, Any]) -> dict[str, Any]:
    execute_registered_tool_fn = runtime_scope.get("execute_registered_tool")
    if not callable(execute_registered_tool_fn):
        raise TypeError("execute_registered_tool is required")

    def tool_ls(subfolder: str = ""):
        payload = {"action": "ls"}
        if subfolder:
            payload["path"] = subfolder
        return execute_registered_tool_fn("filesystem", payload)

    def tool_read(path: str):
        return execute_registered_tool_fn("filesystem", {"action": "read", "path": path})

    def tool_find(keyword: str, subfolder: str = ""):
        payload = {"action": "find", "keyword": keyword}
        if subfolder:
            payload["path"] = subfolder
        out = execute_registered_tool_fn("filesystem", payload)
        if not out or out == "No matches found.":
            return out or "No matches found."
        return "Matches:\n" + out

    def tool_health():
        return execute_registered_tool_fn("system", {"action": "health_check"})

    def tool_system_check():
        return execute_registered_tool_fn("system", {"action": "system_check"})

    def tool_queue_status():
        return execute_registered_tool_fn("system", {"action": "queue_status"})

    def tool_temporal_review(payload: str = ""):
        args: dict[str, object] = {"action": "review"}
        text = str(payload or "").strip()
        if text:
            path = Path(text)
            if path.exists() and path.is_file():
                args["path"] = str(path.resolve())
            else:
                args["input"] = text
        return execute_registered_tool_fn("temporal_review", args)

    def tool_screen():
        return execute_registered_tool_fn("vision", {"action": "screen"})

    def tool_camera():
        return execute_registered_tool_fn("vision", {"action": "camera"})

    def tool_edfi_explore(
        action: str = "health",
        connection_id: str = "district-main",
        resource: str = "",
        limit: int = 25,
        offset: int = 0,
        query: str = "",
        namespace: str = "",
    ):
        return execute_registered_tool_fn(
            "edfi_explore",
            {
                "action": str(action or "health").strip().lower(),
                "connection_id": str(connection_id or "district-main").strip() or "district-main",
                "resource": str(resource or "").strip(),
                "limit": int(limit or 25),
                "offset": int(offset or 0),
                "query": str(query or "").strip(),
                "namespace": str(namespace or "").strip(),
            },
        )

    def tool_pipeline(command_text: str = "pipeline help"):
        return service_handle_pipeline_command(
            command_text,
            data_sources_root=runtime_scope["DATA_SOURCES_ROOT"],
            list_pipeline_summaries_fn=service_list_pipeline_summaries,
            get_pipeline_status_fn=service_get_pipeline_status,
            get_pipeline_schema_probe_fn=service_get_pipeline_schema_probe,
            preview_pipeline_query_fn=service_preview_pipeline_query,
            run_privileged_pipeline_query_fn=service_run_privileged_pipeline_query,
            search_pipeline_vendor_dictionary_fn=service_search_pipeline_vendor_dictionary,
            plan_pipeline_report_fn=service_plan_pipeline_report,
        )

    def tool_patch_preview_apply(preview: str) -> dict:
        preview_name = str(preview or "").strip()
        patch_status_payload_fn = runtime_scope["patch_status_payload"]
        patch_preview_summaries_fn = runtime_scope["patch_preview_summaries"]
        patch_summary = patch_status_payload_fn()
        preview_limit = max(200, int(patch_summary.get("previews_total", 0) or 0))
        preview_rows = list(patch_preview_summaries_fn(preview_limit) or [])
        ok, msg, extra, detail = PATCH_CONTROL_SERVICE.patch_preview_apply(
            {"preview": preview_name},
            preview_target_fn=lambda payload: PATCH_CONTROL_SERVICE.patch_preview_target(payload, preview_rows),
            preview_entry_fn=lambda target: PATCH_CONTROL_SERVICE.patch_preview_entry(target, preview_rows),
            patch_control_state_fn=runtime_scope["_patch_control_state"],
            show_preview_fn=runtime_scope["show_preview"],
            updates_dir=runtime_scope["UPDATES_DIR"],
            patch_apply_fn=runtime_scope["patch_apply"],
        )
        result = {
            "ok": bool(ok),
            "message": str(msg or ""),
            "detail": str(detail or ""),
        }
        if isinstance(extra, dict):
            result.update(extra)
        if not ok:
            result["error"] = str((extra or {}).get("text") or detail or msg or "patch_preview_apply_failed")
        return result

    def tool_patch_preview_approve(preview: str) -> dict:
        preview_name = str(preview or "").strip()
        patch_status_payload_fn = runtime_scope["patch_status_payload"]
        patch_preview_summaries_fn = runtime_scope["patch_preview_summaries"]
        patch_summary = patch_status_payload_fn()
        preview_limit = max(200, int(patch_summary.get("previews_total", 0) or 0))
        preview_rows = list(patch_preview_summaries_fn(preview_limit) or [])
        ok, msg, extra, detail = PATCH_CONTROL_SERVICE.patch_preview_decision(
            "approve",
            {
                "preview": preview_name,
                "note": "autonomy maintenance: governed work tree approval for base-compatible patch preview",
            },
            preview_target_fn=lambda payload: PATCH_CONTROL_SERVICE.patch_preview_target(payload, preview_rows),
            patch_control_state_fn=runtime_scope["_patch_control_state"],
            decision_fn=lambda target, note: runtime_scope["approve_preview"](
                target,
                note or "autonomy maintenance approved preview",
            ),
        )
        result = {
            "ok": bool(ok),
            "message": str(msg or ""),
            "detail": str(detail or ""),
        }
        if isinstance(extra, dict):
            result.update(extra)
        if not ok:
            result["error"] = str((extra or {}).get("text") or detail or msg or "patch_preview_approve_failed")
        return result

    def tool_update_now():
        return service_tool_update_now(
            patch_status_payload_fn=runtime_scope["patch_status_payload"],
            latest_approved_update_zip_fn=runtime_scope["_latest_approved_update_zip"],
            patch_preview_fn=runtime_scope["patch_preview"],
            clear_pending_fn=runtime_scope["_clear_update_now_pending"],
            write_pending_fn=runtime_scope["_write_update_now_pending"],
            build_token_fn=runtime_scope["_build_update_now_token"],
        )

    def tool_update_now_confirm(token: str = ""):
        return service_tool_update_now_confirm(
            token,
            read_pending_fn=runtime_scope["_read_update_now_pending"],
            clear_pending_fn=runtime_scope["_clear_update_now_pending"],
            patch_status_payload_fn=runtime_scope["patch_status_payload"],
            latest_approved_update_zip_fn=runtime_scope["_latest_approved_update_zip"],
            execute_patch_action_fn=runtime_scope["execute_patch_action"],
        )

    def tool_update_now_cancel():
        return service_tool_update_now_cancel(
            read_pending_fn=runtime_scope["_read_update_now_pending"],
            clear_pending_fn=runtime_scope["_clear_update_now_pending"],
        )

    def tool_nova_pulse():
        return service_tool_nova_pulse(
            build_pulse_payload_fn=runtime_scope["build_pulse_payload"],
            write_pulse_snapshot_fn=runtime_scope["write_pulse_snapshot"],
            render_nova_pulse_fn=runtime_scope["render_nova_pulse"],
        )

    def tool_nova_self_status():
        pulse_payload = runtime_scope["_apply_latest_regression_validation"](runtime_scope["build_pulse_payload"]())
        payload = service_build_self_status_payload(
            pulse_payload=pulse_payload,
            recent_ops_events=service_read_recent_ops_events(runtime_scope["RUNTIME_DIR"] / "ops_journal.jsonl", limit=60),
            repo_change_snapshot=service_build_repo_change_snapshot(BASE_DIR),
        )
        return service_render_self_status(payload)

    def tool_core_health_brief(feed: str = ""):
        brief = runtime_scope["build_core_health_brief_payload"]()
        service_write_core_health_brief(runtime_scope["RUNTIME_DIR"] / "core_health_brief.json", brief)

        feed_result = None
        if str(feed or "").strip().lower() in {"feed", "work_tree", "worktree", "seed"}:
            import work_tree

            feed_result = service_feed_core_health_brief_to_work_tree(brief, work_tree_module=work_tree)
        return service_render_core_health_brief(brief, feed_result=feed_result)

    def tool_core_thinning(feed: str = ""):
        raw = str(feed or "").strip()
        if raw.startswith("{"):
            return service_execute_core_thinning_order(raw)

        core_path = Path(str(runtime_scope.get("__file__") or "")).resolve()
        brief = service_build_core_thinning_brief([core_path, core_path.with_name("nova_http.py")])
        feed_result = None
        if raw.lower() in {"feed", "work_tree", "worktree", "seed"}:
            import work_tree

            feed_result = service_feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
        return service_render_core_thinning_brief(brief, feed_result=feed_result)

    def tool_search(query: str):
        return service_tool_search(
            query,
            explain_missing_fn=runtime_scope["explain_missing"],
            policy_tools_enabled_fn=runtime_scope["policy_tools_enabled"],
            web_search_fn=runtime_scope["web_search"],
            web_cache_dir=runtime_scope["WEB_CACHE_DIR"],
        )

    def tool_web_fetch(url: str):
        web_cache_dir = runtime_scope["WEB_CACHE_DIR"]
        return service_tool_web_fetch(
            url,
            explain_missing_fn=runtime_scope["explain_missing"],
            policy_tools_enabled_fn=runtime_scope["policy_tools_enabled"],
            web_fetch_fn=lambda target_url: runtime_scope["web_fetch"](target_url, web_cache_dir),
            web_allowlist_message_fn=runtime_scope["_web_allowlist_message"],
        )

    def tool_wikipedia_lookup(query: str):
        return service_tool_wikipedia_lookup(
            query,
            explain_missing_fn=runtime_scope["explain_missing"],
            policy_tools_enabled_fn=runtime_scope["policy_tools_enabled"],
            web_enabled_fn=runtime_scope["web_enabled"],
            requests_get_fn=requests.get,
        )

    def tool_stackexchange_search(query: str):
        return service_tool_stackexchange_search(
            query,
            explain_missing_fn=runtime_scope["explain_missing"],
            policy_tools_enabled_fn=runtime_scope["policy_tools_enabled"],
            web_enabled_fn=runtime_scope["web_enabled"],
            policy_web_fn=runtime_scope["policy_web"],
            requests_get_fn=requests.get,
            env=os.environ,
        )

    def tool_web_search(query: str):
        return service_tool_web_search(
            query,
            explain_missing_fn=runtime_scope["explain_missing"],
            policy_tools_enabled_fn=runtime_scope["policy_tools_enabled"],
            web_enabled_fn=runtime_scope["web_enabled"],
            policy_web_fn=runtime_scope["policy_web"],
            host_allowed_fn=runtime_scope["_host_allowed"],
            decode_search_href_fn=runtime_scope["_decode_search_href"],
            probe_search_endpoint_fn=runtime_scope["probe_search_endpoint"],
            web_allowlist_message_fn=runtime_scope["_web_allowlist_message"],
            requests_get_fn=requests.get,
        )

    def tool_web_gather(url: str):
        web_cache_dir = runtime_scope["WEB_CACHE_DIR"]
        return service_tool_web_gather(
            url,
            explain_missing_fn=runtime_scope["explain_missing"],
            policy_tools_enabled_fn=runtime_scope["policy_tools_enabled"],
            web_fetch_fn=lambda target_url: runtime_scope["web_fetch"](target_url, web_cache_dir),
            web_allowlist_message_fn=runtime_scope["_web_allowlist_message"],
            extract_text_from_path_fn=runtime_scope["_extract_text_from_path"],
        )

    def tool_web_research(query: str, continue_mode: bool = False):
        return service_tool_web_research(
            query,
            continue_mode=continue_mode,
            explain_missing_fn=runtime_scope["explain_missing"],
            policy_tools_enabled_fn=runtime_scope["policy_tools_enabled"],
            web_enabled_fn=runtime_scope["web_enabled"],
            policy_web_fn=runtime_scope["policy_web"],
            tokenize_fn=runtime_scope["_tokenize"],
            fetch_sitemap_urls_fn=runtime_scope["_fetch_sitemap_urls"],
            scan_candidate_urls_for_query_fn=runtime_scope["_scan_candidate_urls_for_query"],
            seed_urls_for_domain_fn=runtime_scope["_seed_urls_for_domain"],
            crawl_domain_for_query_fn=runtime_scope["_crawl_domain_for_query"],
            session_store=runtime_scope["WEB_RESEARCH_SESSION"],
        )

    return {
        "tool_ls": tool_ls,
        "tool_read": tool_read,
        "tool_find": tool_find,
        "tool_health": tool_health,
        "tool_system_check": tool_system_check,
        "tool_queue_status": tool_queue_status,
        "tool_temporal_review": tool_temporal_review,
        "tool_screen": tool_screen,
        "tool_camera": tool_camera,
        "tool_edfi_explore": tool_edfi_explore,
        "tool_pipeline": tool_pipeline,
        "tool_patch_preview_apply": tool_patch_preview_apply,
        "tool_patch_preview_approve": tool_patch_preview_approve,
        "tool_update_now": tool_update_now,
        "tool_update_now_confirm": tool_update_now_confirm,
        "tool_update_now_cancel": tool_update_now_cancel,
        "tool_nova_pulse": tool_nova_pulse,
        "tool_nova_self_status": tool_nova_self_status,
        "tool_core_health_brief": tool_core_health_brief,
        "tool_core_thinning": tool_core_thinning,
        "tool_search": tool_search,
        "tool_web_fetch": tool_web_fetch,
        "tool_wikipedia_lookup": tool_wikipedia_lookup,
        "tool_stackexchange_search": tool_stackexchange_search,
        "tool_web_search": tool_web_search,
        "tool_web_gather": tool_web_gather,
        "tool_web_research": tool_web_research,
    }
