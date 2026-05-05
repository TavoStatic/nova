from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, Callable, Mapping


def parse_pipeline_params(tokens: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for token in tokens:
        raw = str(token or "").strip()
        if not raw or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            params[key] = value
    return params


def parse_pipeline_command(command_text: str) -> dict[str, Any]:
    tokens = shlex.split(str(command_text or "").strip())
    if not tokens or tokens[0].lower() != "pipeline":
        return {"ok": False, "error": "Usage: pipeline <list|status|schema|search|plan|preview|run> ..."}
    if len(tokens) == 1 or tokens[1].lower() in {"help", "-h", "--help"}:
        return {"ok": True, "action": "help"}

    action = tokens[1].lower()
    if action == "list":
        return {"ok": True, "action": "list"}
    if action in {"status", "schema"}:
        if len(tokens) < 3:
            return {"ok": False, "error": f"Usage: pipeline {action} <pipeline_id>"}
        return {"ok": True, "action": action, "pipeline_id": tokens[2]}
    if action == "search":
        if len(tokens) < 4:
            return {"ok": False, "error": "Usage: pipeline search <pipeline_id> <query> [limit=N]"}
        limit = 12
        query_tokens: list[str] = []
        for token in tokens[3:]:
            if token.startswith("limit="):
                try:
                    limit = int(token.split("=", 1)[1])
                except Exception:
                    limit = 12
                continue
            query_tokens.append(token)
        return {"ok": True, "action": "search", "pipeline_id": tokens[2], "query": " ".join(query_tokens), "limit": limit}
    if action == "plan":
        if len(tokens) < 4:
            return {"ok": False, "error": "Usage: pipeline plan <pipeline_id> <report request> [limit=N]"}
        limit = 8
        request_tokens: list[str] = []
        for token in tokens[3:]:
            if token.startswith("limit="):
                try:
                    limit = int(token.split("=", 1)[1])
                except Exception:
                    limit = 8
                continue
            request_tokens.append(token)
        return {"ok": True, "action": "plan", "pipeline_id": tokens[2], "request": " ".join(request_tokens), "limit": limit}
    if action in {"preview", "run"}:
        if len(tokens) < 4:
            return {"ok": False, "error": f"Usage: pipeline {action} <pipeline_id> <operation> key=value ..."}
        row_limit = None
        remaining: list[str] = []
        for token in tokens[4:]:
            if token.startswith("row_limit="):
                try:
                    row_limit = int(token.split("=", 1)[1])
                except Exception:
                    row_limit = None
                continue
            remaining.append(token)
        return {
            "ok": True,
            "action": action,
            "pipeline_id": tokens[2],
            "operation": tokens[3],
            "params": parse_pipeline_params(remaining),
            "row_limit": row_limit,
        }
    return {"ok": False, "error": f"Unknown pipeline action: {action}"}


def render_pipeline_help() -> str:
    return (
        "Pipeline commands:\n"
        "  pipeline list\n"
        "  pipeline status <pipeline_id>\n"
        "  pipeline schema <pipeline_id>\n"
        "  pipeline search <pipeline_id> <table-or-column-text> [limit=N]\n"
        "  pipeline plan <pipeline_id> <report request> [limit=N]\n"
        "  pipeline preview <pipeline_id> <operation> key=value ... [row_limit=N]\n"
        "  pipeline run <pipeline_id> <operation> key=value ... [row_limit=N]\n"
        "Live runs use the governed pipeline path; use preview first unless you are confirming an intentional read."
    )


def render_pipeline_list(summaries: list[dict[str, Any]]) -> str:
    if not summaries:
        return "No data pipelines are registered."
    lines = ["Registered data pipelines:"]
    for item in summaries:
        pipeline_id = str(item.get("pipeline_id") or "").strip()
        display = str(item.get("display_name") or pipeline_id).strip()
        scope = str(item.get("network_scope") or "").strip()
        read_only = "read-only" if bool(item.get("read_only")) else "read/write"
        ops = ", ".join(str(op) for op in (item.get("safe_operations") or []) if op)
        lines.append(f"- {pipeline_id}: {display} ({read_only}; {scope}); operations: {ops or 'none'}")
    return "\n".join(lines)


def render_pipeline_status(status: Mapping[str, Any]) -> str:
    pipeline_id = str(status.get("pipeline_id") or "").strip()
    display = str(status.get("display_name") or pipeline_id).strip()
    ready = bool(status.get("live_query_ready"))
    configured = bool(status.get("configured"))
    network = status.get("network_probe") if isinstance(status.get("network_probe"), Mapping) else {}
    auth = status.get("auth_probe") if isinstance(status.get("auth_probe"), Mapping) else {}
    lines = [
        f"Pipeline status for {pipeline_id} ({display}):",
        f"- read_only: {bool(status.get('read_only'))}",
        f"- network_scope: {status.get('network_scope') or 'unknown'}",
        f"- configured: {configured}",
        f"- driver_selected: {status.get('driver_selected') or 'none'}",
        f"- network: {network.get('reason') or 'unknown'}",
        f"- auth: {auth.get('reason') or 'unknown'}",
        f"- live_query_ready: {ready}",
    ]
    if not ready:
        if not configured:
            next_step = "add or complete local_config.json before live reads."
        elif not bool(network.get("reachable")):
            next_step = f"fix SIS network reachability: {network.get('reason') or 'network_unreachable'}"
        elif not bool(auth.get("authenticated")):
            next_step = f"fix SIS read-only authentication: {auth.get('reason') or 'auth_not_ready'}"
        else:
            next_step = "fix driver/client readiness before live reads."
        lines.append(f"- next_step: {next_step}")
    return "\n".join(lines)


def render_pipeline_schema(probe: Mapping[str, Any]) -> str:
    pipeline_id = str(probe.get("pipeline_id") or "").strip()
    schema = probe.get("schema") if isinstance(probe.get("schema"), Mapping) else {}
    entities = schema.get("entities") if isinstance(schema.get("entities"), list) else []
    lines = [f"Schema probe for {pipeline_id}:"]
    source = schema.get("source") if isinstance(schema.get("source"), Mapping) else {}
    if source.get("verification_status"):
        lines.append(f"Schema status: {source.get('verification_status')}")
    vendor_dictionary = probe.get("vendor_dictionary") if isinstance(probe.get("vendor_dictionary"), Mapping) else {}
    vendor_source = vendor_dictionary.get("source") if isinstance(vendor_dictionary.get("source"), Mapping) else {}
    if vendor_dictionary:
        lines.append(
            "Vendor dictionary: "
            f"{vendor_source.get('grounding_status') or 'available'}; "
            f"tables={int(vendor_dictionary.get('table_count') or 0)}"
        )
    predefined_reports = probe.get("predefined_reports") if isinstance(probe.get("predefined_reports"), Mapping) else {}
    report_summary = predefined_reports.get("summary") if isinstance(predefined_reports.get("summary"), Mapping) else {}
    if report_summary:
        lines.append(
            "Predefined reports: "
            f"modules={int(report_summary.get('module_count') or 0)}; "
            f"files={int(report_summary.get('file_count') or 0)}; "
            f"tables={int(report_summary.get('table_count') or 0)}"
        )
    for entity in entities:
        if not isinstance(entity, Mapping):
            continue
        name = str(entity.get("name") or "").strip()
        tables = ", ".join(str(x) for x in (entity.get("tables") or []) if x)
        keys = ", ".join(str(x) for x in (entity.get("lookup_keys") or []) if x)
        verification = str(entity.get("verification_status") or "").strip()
        suffix = f"; status={verification}" if verification else ""
        lines.append(f"- {name}: tables={tables or 'none'}; lookup_keys={keys or 'none'}{suffix}")
    templates = ", ".join(str(x) for x in (probe.get("query_templates") or []) if x)
    lines.append(f"Governed operations: {templates or 'none'}")
    definitions = probe.get("population_definitions") if isinstance(probe.get("population_definitions"), Mapping) else {}
    populations = definitions.get("populations") if isinstance(definitions.get("populations"), list) else []
    if populations:
        keys = []
        for item in populations:
            if isinstance(item, Mapping) and item.get("key"):
                keys.append(str(item.get("key")))
        lines.append(f"Population definitions: {', '.join(keys) if keys else 'none'}")
    return "\n".join(lines)


def render_pipeline_dictionary_search(result: Mapping[str, Any]) -> str:
    if not bool(result.get("ok")):
        return f"Pipeline dictionary search failed: {result.get('error') or 'unknown_error'}"
    pipeline_id = str(result.get("pipeline_id") or "").strip()
    query = str(result.get("query") or "").strip()
    matches = result.get("matches") if isinstance(result.get("matches"), list) else []
    lines = [
        f"Vendor dictionary search for {pipeline_id}: {query}",
        f"- grounding: {result.get('grounding_status') or 'vendor_dictionary'}",
        f"- matches: {int(result.get('match_count') or 0)}",
    ]
    for item in matches:
        if not isinstance(item, Mapping):
            continue
        columns = item.get("column_hits") if isinstance(item.get("column_hits"), list) else []
        column_text = ", ".join(
            f"{column.get('name')}:{column.get('data_type')}"
            for column in columns[:5]
            if isinstance(column, Mapping) and column.get("name")
        )
        suffix = f"; columns={column_text}" if column_text else ""
        lines.append(
            f"- {item.get('table')}: {item.get('title') or 'untitled'} "
            f"(page {item.get('page') or 'n/a'}, {int(item.get('column_count') or 0)} cols){suffix}"
        )
    return "\n".join(lines)


def render_pipeline_report_plan(result: Mapping[str, Any]) -> str:
    if not bool(result.get("ok")):
        return f"Pipeline report plan failed: {result.get('error') or 'unknown_error'}"
    lines = [
        f"Pipeline report plan for {result.get('pipeline_id')}:",
        f"- request: {result.get('request') or ''}",
        f"- grounding: {result.get('grounding_status') or 'unknown'}",
        f"- live_schema: {result.get('live_schema_status') or 'unknown'}",
        f"- default_row_limit: {int(result.get('default_row_limit') or 20)}",
    ]
    populations = result.get("matched_populations") if isinstance(result.get("matched_populations"), list) else []
    if populations:
        rendered = []
        for item in populations:
            if not isinstance(item, Mapping):
                continue
            rendered.append(
                f"{item.get('key')}({item.get('program_id')}/{item.get('field_number')})"
            )
        lines.append(f"- populations: {', '.join(rendered)}")
    else:
        lines.append("- populations: none matched")
    if result.get("suggested_operation"):
        lines.append(f"- suggested_operation: {result.get('suggested_operation')}")
    intent = result.get("intent") if isinstance(result.get("intent"), Mapping) else {}
    if intent:
        group_by = ", ".join(str(item) for item in (intent.get("group_by") or []) if item)
        lines.append(f"- intent: {intent.get('report_kind') or 'unknown'}; group_by={group_by or 'none'}")
        filters = intent.get("filters") if isinstance(intent.get("filters"), list) else []
        if filters:
            rendered_filters = []
            for item in filters:
                if not isinstance(item, Mapping):
                    continue
                if item.get("type") == "population":
                    rendered_filters.append(
                        f"{item.get('key')} PROGRAM_ID={item.get('program_id')} FIELD_NUMBER={item.get('field_number')}"
                    )
            if rendered_filters:
                lines.append(f"- filters: {'; '.join(rendered_filters)}")
        missing = ", ".join(str(item) for item in (intent.get("missing_inputs") or []) if item)
        if missing:
            lines.append(f"- needs_clarification: {missing}")
    required_tables = result.get("required_tables") if isinstance(result.get("required_tables"), list) else []
    if required_tables:
        lines.append("Required tables:")
    for item in required_tables:
        if not isinstance(item, Mapping):
            continue
        role = f"; role={item.get('role')}" if item.get("role") else ""
        join_key = f"; join_key={item.get('join_key')}" if item.get("join_key") else ""
        lines.append(
            f"- {item.get('table')}: {item.get('title') or 'untitled'}; "
            f"reason={item.get('reason') or 'required'}{role}{join_key}"
        )
        if item.get("active_status_note"):
            lines.append(f"  active_status: {item.get('active_status_note')}")
        activity = item.get("activity_inference") if isinstance(item.get("activity_inference"), Mapping) else {}
        if activity:
            lines.append(
                "  activity_inference: "
                f"{activity.get('signal') or 'unknown'}; "
                f"join={activity.get('join_rule') or 'unknown'}"
            )
        candidates = item.get("active_status_candidates_to_verify")
        if isinstance(candidates, list) and candidates:
            rendered = []
            for candidate in candidates:
                if not isinstance(candidate, Mapping):
                    continue
                table = candidate.get("table") or "unknown"
                field = candidate.get("field") or "unknown"
                rendered.append(f"{table}.{field}")
            if rendered:
                lines.append(f"  active_status_candidates_to_verify: {', '.join(rendered)}")
    tables = result.get("candidate_tables") if isinstance(result.get("candidate_tables"), list) else []
    if tables:
        lines.append("Candidate tables:")
    for item in tables:
        if not isinstance(item, Mapping):
            continue
        terms = ", ".join(str(term) for term in (item.get("matched_terms") or [])[:5])
        columns = item.get("column_hits") if isinstance(item.get("column_hits"), list) else []
        column_text = ", ".join(
            f"{column.get('name')}:{column.get('data_type')}"
            for column in columns[:4]
            if isinstance(column, Mapping) and column.get("name")
        )
        suffix = f"; columns={column_text}" if column_text else ""
        lines.append(f"- {item.get('table')}: {item.get('title') or 'untitled'}; terms={terms}{suffix}")
    lines.append(f"Next step: {result.get('next_step') or 'Review before preview/run.'}")
    return "\n".join(lines)


def render_pipeline_query_result(result: Mapping[str, Any], *, live_requested: bool = False) -> str:
    ok = bool(result.get("ok"))
    pipeline_id = str(result.get("pipeline_id") or "").strip()
    operation = str(result.get("operation") or "").strip()
    mode = str(result.get("execution_mode") or ("live" if live_requested else "dry_run")).strip()
    if not ok:
        error = str(result.get("error") or "pipeline query failed").strip()
        next_step = str(result.get("next_step") or "").strip()
        suffix = f"\nNext step: {next_step}" if next_step else ""
        return f"Pipeline {pipeline_id}.{operation} did not run successfully ({mode}).\nError: {error}{suffix}"

    lines = [
        f"Pipeline {pipeline_id}.{operation} {mode} result:",
        f"- tables: {', '.join(str(x) for x in (result.get('tables') or [])) or 'none'}",
        f"- effective_row_limit: {int(result.get('effective_row_limit') or 0)}",
        f"- read_only: {bool(result.get('read_only'))}",
    ]
    if mode == "live":
        lines.append(f"- row_count: {int(result.get('row_count') or 0)}")
        columns = [str(x) for x in (result.get("columns") or [])]
        if columns:
            lines.append(f"- columns: {', '.join(columns[:12])}")
        rows = result.get("rows") if isinstance(result.get("rows"), list) else []
        if rows:
            lines.append("Rows:")
            for row in rows[:5]:
                if isinstance(row, Mapping):
                    preview = "; ".join(f"{k}={v}" for k, v in list(row.items())[:8])
                    lines.append(f"- {preview}")
    else:
        params = result.get("params") if isinstance(result.get("params"), Mapping) else {}
        if params:
            lines.append("- params: " + ", ".join(f"{k}={v}" for k, v in params.items()))
        next_step = str(result.get("next_step") or "").strip()
        if next_step:
            lines.append(f"- next_step: {next_step}")
    return "\n".join(lines)


def handle_pipeline_command(
    command_text: str,
    *,
    data_sources_root: Path,
    list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]],
    get_pipeline_status_fn: Callable[..., dict[str, Any]],
    get_pipeline_schema_probe_fn: Callable[..., dict[str, Any]],
    preview_pipeline_query_fn: Callable[..., dict[str, Any]],
    run_privileged_pipeline_query_fn: Callable[..., dict[str, Any]],
    search_pipeline_vendor_dictionary_fn: Callable[..., dict[str, Any]] | None = None,
    plan_pipeline_report_fn: Callable[..., dict[str, Any]] | None = None,
) -> str:
    parsed = parse_pipeline_command(command_text)
    if not parsed.get("ok"):
        return str(parsed.get("error") or render_pipeline_help())

    action = str(parsed.get("action") or "").strip()
    if action == "help":
        return render_pipeline_help()
    if action == "list":
        return render_pipeline_list(list_pipeline_summaries_fn(data_sources_root))

    pipeline_id = str(parsed.get("pipeline_id") or "").strip()
    if action == "status":
        return render_pipeline_status(get_pipeline_status_fn(pipeline_id, data_sources_root=data_sources_root))
    if action == "schema":
        return render_pipeline_schema(get_pipeline_schema_probe_fn(pipeline_id, data_sources_root=data_sources_root))
    if action == "search":
        if not callable(search_pipeline_vendor_dictionary_fn):
            return "Pipeline dictionary search is not available in this runtime."
        return render_pipeline_dictionary_search(
            search_pipeline_vendor_dictionary_fn(
                pipeline_id,
                str(parsed.get("query") or ""),
                limit=int(parsed.get("limit") or 12),
                data_sources_root=data_sources_root,
            )
        )
    if action == "plan":
        if not callable(plan_pipeline_report_fn):
            return "Pipeline report planning is not available in this runtime."
        return render_pipeline_report_plan(
            plan_pipeline_report_fn(
                pipeline_id,
                str(parsed.get("request") or ""),
                limit=int(parsed.get("limit") or 8),
                data_sources_root=data_sources_root,
            )
        )

    operation = str(parsed.get("operation") or "").strip()
    params = parsed.get("params") if isinstance(parsed.get("params"), Mapping) else {}
    row_limit = parsed.get("row_limit")
    if action == "preview":
        result = preview_pipeline_query_fn(
            pipeline_id,
            operation,
            params,
            row_limit=row_limit,
            dry_run=True,
            data_sources_root=data_sources_root,
        )
        return render_pipeline_query_result(result)
    if action == "run":
        result = run_privileged_pipeline_query_fn(
            pipeline_id,
            operation,
            params,
            row_limit=row_limit,
            requested_by="nova_pipeline_command",
        )
        return render_pipeline_query_result(result, live_requested=True)

    return render_pipeline_help()
