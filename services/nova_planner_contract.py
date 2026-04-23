from __future__ import annotations

import json
import time
from typing import Callable

from services.work_tree_seeding import WORK_TREE_SEEDING_SERVICE


def _active_work_tree_id(*, pending_action: dict | None, session) -> str:
    if hasattr(session, "active_work_tree_id"):
        tree_id = str(getattr(session, "active_work_tree_id", "") or "").strip()
        if tree_id:
            return tree_id
    pending = pending_action if isinstance(pending_action, dict) else {}
    return str(pending.get("work_tree_id") or "").strip()


def _active_work_identity(*, pending_action: dict | None, session) -> str:
    if hasattr(session, "active_work_identity"):
        identity = str(getattr(session, "active_work_identity", "") or "").strip()
        if identity:
            return identity
    pending = pending_action if isinstance(pending_action, dict) else {}
    return str(pending.get("work_identity_key") or "").strip()


def _looks_like_work_tree_request(text: str) -> bool:
    low = str(text or "").strip().lower()
    if _looks_like_work_tree_create_request(low) or _looks_like_work_tree_inspect_request(low):
        return True
    if low in {"continue", "continue.", "resume", "resume."}:
        return True
    phrases = (
        "next step",
        "next task",
        "what next",
        "what should i do next",
        "continue work",
        "resume work",
        "resume plan",
        "continue the tree",
        "continue the work tree",
        "next autonomous step",
    )
    return any(phrase in low for phrase in phrases)


def _looks_like_work_tree_create_request(text: str) -> bool:
    return WORK_TREE_SEEDING_SERVICE.looks_like_explicit_work_tree_request(text)


def _looks_like_work_tree_inspect_request(text: str) -> bool:
    low = str(text or "").strip().lower()
    phrases = (
        "show work tree",
        "show the work tree",
        "show active work tree",
        "inspect work tree",
        "work tree status",
        "active work tree",
        "tree status",
    )
    return any(phrase in low for phrase in phrases)


def _looks_like_work_tree_execute_request(text: str) -> bool:
    low = str(text or "").strip().lower()
    phrases = (
        "continue",
        "continue.",
        "continue work",
        "continue the tree",
        "continue the work tree",
        "resume",
        "resume.",
        "resume work",
        "resume plan",
        "run next step",
        "execute next step",
    )
    return low in phrases or any(low.startswith(phrase + " ") for phrase in phrases)


def _format_work_tree_reply(step: dict | None) -> str:
    if step is None:
        return "The active work tree is complete."
    action = str(step.get("action") or "").strip()
    if action == "created":
        snapshot_text = str(step.get("snapshot_text") or "").strip()
        return snapshot_text or "Created a new work tree."
    if action == "inspect":
        snapshot_text = str(step.get("snapshot_text") or "").strip()
        return snapshot_text or "The active work tree is ready."
    if action == "executed":
        tool_name = str(step.get("tool") or "tool").strip()
        result = str(step.get("tool_result") or "").strip()
        if result:
            return result
        task_title = str(step.get("task_title") or step.get("branch_title") or "next task").strip()
        return f"Executed {tool_name} for {task_title}."
    if action == "tool_failed":
        error = str(step.get("error") or "unknown error").strip()
        tool_name = str(step.get("tool") or "tool").strip()
        return f"Work tree tool {tool_name} failed: {error}"
    if str(step.get("action") or "") == "wait_for_tools":
        missing = [str(item).strip() for item in list(step.get("missing_tools") or []) if str(item).strip()]
        missing_text = ", ".join(missing) if missing else "required tools"
        return f"The next work tree branch is waiting for tools: {missing_text}."
    if action == "governance_blocked":
        tool_name = str(step.get("recommended_tool") or "tool").strip() or "tool"
        reason = str(step.get("reason") or "blocked").strip()
        branch_title = str(step.get("branch_title") or step.get("branch_id") or "next branch").strip()
        return f"The next work tree step is governance-blocked on {branch_title}: {tool_name} ({reason})."
    if action == "no_tool_selected":
        branch_title = str(step.get("branch_title") or step.get("branch_id") or "next branch").strip()
        return f"The next work tree step has no governed tool selected for {branch_title}."
    branch_title = str(step.get("branch_title") or step.get("branch_id") or "next branch").strip()
    recommended_tool = str(step.get("recommended_tool") or "").strip()
    if recommended_tool:
        return f"Next work tree step: {branch_title}. Recommended tool: {recommended_tool}."
    return f"Next work tree step: {branch_title}."


def _maybe_handle_work_tree_sequence(*, text: str, pending_action: dict | None, session, core, trace: Callable[..., None], normalize_reply: Callable[[str], str], ensure_active_work_tree_fn: Callable[[str], str] | None = None, work_tree_seed_source: str = "", work_tree_seed_mode: str = "") -> tuple[str, dict] | None:
    work_tree_started = time.perf_counter()
    tree_id = _active_work_tree_id(pending_action=pending_action, session=session)
    active_identity = _active_work_identity(pending_action=pending_action, session=session)
    low = str(text or "").strip().lower()
    wants_create = _looks_like_work_tree_create_request(low)
    wants_inspect = _looks_like_work_tree_inspect_request(low)
    wants_identity_continuity = WORK_TREE_SEEDING_SERVICE.should_continue_active_identity(
        message=text,
        active_work_identity=active_identity,
    )
    should_auto_seed = WORK_TREE_SEEDING_SERVICE.should_seed_system_work_tree(
        message=text,
        source=work_tree_seed_source,
        operator_mode=work_tree_seed_mode,
    )
    if not tree_id and callable(ensure_active_work_tree_fn) and (wants_create or should_auto_seed or wants_identity_continuity):
        tree_id = str(ensure_active_work_tree_fn(text) or "").strip()
    if tree_id and hasattr(session, "set_active_work_tree_id"):
        try:
            session.set_active_work_tree_id(tree_id)
        except Exception:
            pass
    if tree_id and (wants_identity_continuity or _looks_like_work_tree_request(text)) and hasattr(session, "set_last_work_continuity"):
        try:
            session.set_last_work_continuity("continuing_existing_work")
        except Exception:
            pass
    if tree_id and hasattr(session, "set_active_work_identity") and not active_identity:
        inferred_identity = WORK_TREE_SEEDING_SERVICE.build_work_identity_key(text)
        if inferred_identity:
            try:
                session.set_active_work_identity(inferred_identity)
                active_identity = inferred_identity
            except Exception:
                pass
    if not tree_id:
        return None
    if not (_looks_like_work_tree_request(text) or wants_identity_continuity):
        return None
    try:
        import work_tree
    except Exception:
        return None
    if wants_create:
        reuse_note = WORK_TREE_SEEDING_SERVICE.consume_reuse_note(tree_id=tree_id, request_text=text)
        snapshot_text = work_tree.format_tree_snapshot(tree_id)
        if reuse_note:
            snapshot_text = reuse_note + "\n" + snapshot_text
        step = {
            "action": "created",
            "tree_id": tree_id,
            "snapshot_text": snapshot_text,
        }
    elif wants_inspect:
        step = {
            "action": "inspect",
            "tree_id": tree_id,
            "snapshot_text": work_tree.format_tree_snapshot(tree_id),
        }
    elif _looks_like_work_tree_execute_request(text):
        step_started = time.perf_counter()
        step = work_tree.execute_autonomous_step(tree_id, execute_planned_action_fn=core.execute_planned_action)
        trace("timing", "completed", "work_tree_step", duration_ms=int((time.perf_counter() - step_started) * 1000))
    else:
        step_started = time.perf_counter()
        step = work_tree.next_autonomous_step(tree_id)
        trace("timing", "completed", "work_tree_step", duration_ms=int((time.perf_counter() - step_started) * 1000))
    action = str((step or {}).get("action") or "complete")
    trace("work_tree", "matched", detail=action)
    trace("timing", "completed", "work_tree_sequence", duration_ms=int((time.perf_counter() - work_tree_started) * 1000))
    reply = _format_work_tree_reply(step)
    return normalize_reply(reply), {
        "planner_decision": "work_tree",
        "tool": str((step or {}).get("recommended_tool") or "work_tree"),
        "tool_args": {"tree_id": tree_id},
        "tool_result": json.dumps(step, ensure_ascii=True) if isinstance(step, dict) else "",
        "grounded": True,
        "pending_action": {
            **dict(pending_action or {}),
            "work_tree_id": tree_id,
            "work_identity_key": active_identity or WORK_TREE_SEEDING_SERVICE.build_work_identity_key(text),
        },
        "route_evidence": _route_evidence(owner="work_tree", action_type=action, tool=str((step or {}).get("recommended_tool") or "work_tree")),
    }


def build_planner_config(
    *,
    turns: list[tuple[str, str]],
    pending_action: dict | None,
    prefer_web_for_data_queries: bool,
) -> dict:
    return {
        "session_turns": turns,
        "pending_action": pending_action or {},
        "prefer_web_for_data_queries": prefer_web_for_data_queries,
    }


def _route_evidence(*, owner: str, action_type: str, tool: str = "") -> dict:
    payload = {
        "final_owner": owner,
        "planner_owner": owner,
        "planner_action": action_type,
    }
    if tool:
        payload["planner_tool"] = tool
    return payload


def merge_route_evidence(routing_decision: dict | None, meta: dict | None) -> dict | None:
    if not isinstance(meta, dict):
        return routing_decision
    route_evidence = meta.get("route_evidence")
    if not isinstance(route_evidence, dict) or not route_evidence:
        return routing_decision
    payload = dict(routing_decision or {})
    payload.update(route_evidence)
    return payload


def maybe_handle_planner_sequence(
    *,
    text: str,
    turns: list[tuple[str, str]],
    pending_action: dict | None,
    prefer_web_for_data_queries: bool,
    session,
    core,
    trace: Callable[..., None],
    normalize_reply: Callable[[str], str],
    is_web_preferred_data_query: Callable[[str], bool],
    ensure_active_work_tree_fn: Callable[[str], str] | None = None,
    work_tree_seed_source: str = "",
    work_tree_seed_mode: str = "",
) -> tuple[str, dict] | None:
    planner_started = time.perf_counter()
    tool_selection_ms = 0
    tool_time_ms = 0

    def _planner_elapsed_ms() -> int:
        return int((time.perf_counter() - planner_started) * 1000)

    def _record_tool_timing(tool_name: str, duration_ms: int) -> None:
        trace("timing", "completed", "tool_response", duration_ms=int(duration_ms or 0), tool=str(tool_name or ""))
        if str(tool_name or "").startswith("web"):
            trace("timing", "completed", "web_search", duration_ms=int(duration_ms or 0), tool=str(tool_name or ""))

    def _return_with_timing(reply: str, meta: dict) -> tuple[str, dict]:
        planner_ms = _planner_elapsed_ms()
        trace("timing", "completed", "planner", duration_ms=planner_ms)
        payload = dict(meta or {})
        timing = dict(payload.get("timing") or {})
        timing["planner_time"] = planner_ms
        timing["tool_selection_time"] = int(tool_selection_ms or 0)
        timing["tool_time"] = int(tool_time_ms or 0)
        payload["timing"] = timing
        return reply, payload

    config = build_planner_config(
        turns=turns,
        pending_action=pending_action,
        prefer_web_for_data_queries=prefer_web_for_data_queries,
    )
    work_tree_outcome = _maybe_handle_work_tree_sequence(
        text=text,
        pending_action=pending_action,
        session=session,
        core=core,
        trace=trace,
        normalize_reply=normalize_reply,
        ensure_active_work_tree_fn=ensure_active_work_tree_fn,
        work_tree_seed_source=work_tree_seed_source,
        work_tree_seed_mode=work_tree_seed_mode,
    )
    if work_tree_outcome is not None:
        return _return_with_timing(work_tree_outcome[0], work_tree_outcome[1])
    decide_started = time.perf_counter()
    try:
        actions = core.decide_actions(text, config=config)
    except Exception:
        actions = []
    tool_selection_ms = int((time.perf_counter() - decide_started) * 1000)
    trace("timing", "completed", "planner_decide_actions", duration_ms=tool_selection_ms)
    trace("timing", "completed", "tool_selection", duration_ms=tool_selection_ms)

    if actions:
        act = actions[0]
        atype = str(act.get("type") or "").strip()
        if atype == "ask_clarify":
            trace("action_planner", "ask_clarify")
            reply = act.get("question") or act.get("note") or "Can you clarify?"
            return _return_with_timing(normalize_reply(reply), {
                "planner_decision": "ask_clarify",
                "tool": "",
                "tool_args": {"query": text},
                "tool_result": str(reply or ""),
                "grounded": False,
                "pending_action": core.make_pending_weather_action() if "weather lookup" in str(reply or "").lower() else {},
                "route_evidence": _route_evidence(owner="action_planner", action_type=atype),
            })

        if atype == "respond":
            trace("action_planner", "respond")
            reply = act.get("note") or act.get("message") or "Tell me a bit more about what you want me to inspect."
            return _return_with_timing(normalize_reply(reply), {
                "planner_decision": "respond",
                "tool": "",
                "tool_args": {"query": text},
                "tool_result": str(reply or ""),
                "grounded": False,
                "route_evidence": _route_evidence(owner="action_planner", action_type=atype),
            })

        if atype == "route_command":
            trace("action_planner", "route_command")
            cmd_reply = core.handle_commands(text, session_turns=turns, session=session)
            if cmd_reply:
                tool_name = "weather" if "api.weather.gov" in str(cmd_reply).lower() else ""
                trace("command", "matched", tool=tool_name)
                return _return_with_timing(normalize_reply(cmd_reply), {
                    "planner_decision": "command",
                    "tool": tool_name,
                    "tool_args": {"raw": text},
                    "tool_result": str(cmd_reply or ""),
                    "grounded": bool(tool_name),
                    "pending_action": {},
                    "route_evidence": _route_evidence(owner="action_planner", action_type=atype, tool=tool_name),
                })
            trace("command", "not_matched")

        if atype == "route_keyword":
            trace("action_planner", "route_keyword")
            kw = core.handle_keywords(text)
            if kw:
                _kind, tool_name, out = kw
                trace("keyword_tool", "matched", tool=str(tool_name or ""), grounded=bool(str(out or "").strip()))
                return _return_with_timing(normalize_reply(str(out or "")), {
                    "planner_decision": "run_tool",
                    "tool": str(tool_name or ""),
                    "tool_args": {"raw": text},
                    "tool_result": str(out or ""),
                    "grounded": bool(str(out or "").strip()),
                    "pending_action": {},
                    "route_evidence": _route_evidence(owner="action_planner", action_type=atype, tool=str(tool_name or "")),
                })
            trace("keyword_tool", "not_matched")

        if atype == "run_tool":
            tool = str(act.get("tool") or "")
            args = act.get("args") or []
            trace("action_planner", "run_tool", tool=tool)
            tool_started = time.perf_counter()
            out = core.execute_planned_action(tool, args)
            tool_time_ms = int((time.perf_counter() - tool_started) * 1000)
            _record_tool_timing(tool, tool_time_ms)
            route_evidence = _route_evidence(owner="action_planner", action_type=atype, tool=tool)
            if out is None or (isinstance(out, str) and not out.strip()):
                trace("tool_execution", "empty_result", tool=tool)
                reply = core._web_allowlist_message("requested resource") if tool.startswith("web") else f"The {tool} tool did not return a result. No data was available."
                return _return_with_timing(normalize_reply(reply), {
                    "planner_decision": "run_tool",
                    "tool": tool,
                    "tool_args": {"args": list(args) if isinstance(args, (list, tuple)) else args},
                    "tool_result": "",
                    "grounded": False,
                    "pending_action": {},
                    "route_evidence": route_evidence,
                })
            if isinstance(out, dict) and not out.get("ok", True):
                trace("tool_execution", "error", tool=tool, error=str(out.get("error") or "unknown error"))
                err = out.get("error", "unknown error")
                if isinstance(err, str) and ("not allowed" in err.lower() or "domain not allowed" in err.lower()):
                    reply = core._web_allowlist_message(args[0] if args else "")
                else:
                    reply = f"Tool {tool} failed: {err}"
                return _return_with_timing(normalize_reply(reply), {
                    "planner_decision": "run_tool",
                    "tool": tool,
                    "tool_args": {"args": list(args) if isinstance(args, (list, tuple)) else args},
                    "tool_result": json.dumps(out, ensure_ascii=True),
                    "grounded": False,
                    "pending_action": {},
                    "route_evidence": route_evidence,
                })
            rendered_out = str(out or "")
            if tool == "web_research" and hasattr(core, "_ground_web_research_reply"):
                grounded_out = core._ground_web_research_reply(text, rendered_out)
                if grounded_out:
                    rendered_out = grounded_out
            trace("tool_execution", "ok", tool=tool, grounded=bool(rendered_out.strip()))
            return _return_with_timing(normalize_reply(rendered_out), {
                "planner_decision": "run_tool",
                "tool": tool,
                "tool_args": {"args": list(args) if isinstance(args, (list, tuple)) else args},
                "tool_result": rendered_out,
                "grounded": bool(rendered_out.strip()),
                "pending_action": {},
                "route_evidence": route_evidence,
            })

    if prefer_web_for_data_queries and is_web_preferred_data_query(text):
        trace("session_override", "matched", detail="prefer_web_for_data_queries", tool="web_research")
        tool_started = time.perf_counter()
        out = core.execute_planned_action("web_research", [text])
        tool_time_ms = int((time.perf_counter() - tool_started) * 1000)
        _record_tool_timing("web_research", tool_time_ms)
        if out is None or (isinstance(out, str) and not out.strip()):
            fallback_tool_started = time.perf_counter()
            out = core.tool_web_research(text)
            fallback_tool_ms = int((time.perf_counter() - fallback_tool_started) * 1000)
            tool_time_ms += fallback_tool_ms
            _record_tool_timing("web_research", fallback_tool_ms)
        route_evidence = _route_evidence(owner="session_override", action_type="prefer_web_for_data_queries", tool="web_research")
        if isinstance(out, dict) and not out.get("ok", True):
            trace("tool_execution", "error", tool="web_research", error=str(out.get("error") or "unknown error"))
            err = out.get("error", "unknown error")
            reply = f"Tool web_research failed: {err}"
            return _return_with_timing(normalize_reply(reply), {
                "planner_decision": "run_tool",
                "tool": "web_research",
                "tool_args": {"args": [text]},
                "tool_result": json.dumps(out, ensure_ascii=True),
                "grounded": False,
                "pending_action": {},
                "route_evidence": route_evidence,
            })
        if str(out or "").strip():
            trace("tool_execution", "ok", tool="web_research", grounded=True)
            return _return_with_timing(normalize_reply(str(out or "")), {
                "planner_decision": "run_tool",
                "tool": "web_research",
                "tool_args": {"args": [text]},
                "tool_result": str(out or ""),
                "grounded": True,
                "pending_action": {},
                "route_evidence": route_evidence,
            })
        trace("tool_execution", "empty_result", tool="web_research")

    return None