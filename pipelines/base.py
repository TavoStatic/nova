from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


_PLAN_STOPWORDS = {
    "a", "about", "all", "and", "are", "as", "at", "by", "can", "count", "counts", "data",
    "for", "from", "give", "group", "grouped", "i", "in", "list", "me", "need", "of", "on",
    "report", "reports", "show", "student", "students", "the", "to", "with",
}

_GROUPING_ALIASES = {
    "campus": {"campus", "building", "school", "schools"},
    "grade": {"grade", "grades", "level", "levels"},
    "program": {"program", "programs"},
}

_OPERATION_TABLE_HINTS = {
    "student_lookup": ("dbo.REG", "dbo.REG_BUILDING"),
    "campus_enrollment_summary": ("dbo.REG", "dbo.REG_BUILDING"),
    "program_membership_lookup": ("dbo.REG_PROGRAMS", "dbo.REG"),
}


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9_]+", str(text or "").lower())
        if len(token) > 1 and token not in _PLAN_STOPWORDS
    ]


@dataclass(frozen=True)
class PipelineManifest:
    pipeline_id: str
    display_name: str
    kind: str
    version: str
    description: str
    read_only: bool
    network_scope: str
    safe_operations: tuple[str, ...] = field(default_factory=tuple)
    connector_module: str = ""
    connector_class: str = ""
    pipeline_dir: Path = Path(".")
    schema_manifest_path: Path = Path("schema_manifest.json")
    query_templates_path: Path = Path("query_templates.json")
    field_dictionary_path: Optional[Path] = None
    population_definitions_path: Optional[Path] = None
    vendor_dictionary_path: Optional[Path] = None
    predefined_reports_path: Optional[Path] = None
    config_example_path: Optional[Path] = None
    local_config_path: Optional[Path] = None
    audit_log_path: Optional[Path] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "display_name": self.display_name,
            "kind": self.kind,
            "version": self.version,
            "description": self.description,
            "read_only": self.read_only,
            "network_scope": self.network_scope,
            "safe_operations": list(self.safe_operations),
            "connector_module": self.connector_module,
            "connector_class": self.connector_class,
            "pipeline_dir": str(self.pipeline_dir),
            "schema_manifest_path": str(self.schema_manifest_path),
            "query_templates_path": str(self.query_templates_path),
            "field_dictionary_path": str(self.field_dictionary_path) if self.field_dictionary_path else None,
            "population_definitions_path": str(self.population_definitions_path) if self.population_definitions_path else None,
            "vendor_dictionary_path": str(self.vendor_dictionary_path) if self.vendor_dictionary_path else None,
            "predefined_reports_path": str(self.predefined_reports_path) if self.predefined_reports_path else None,
            "config_example_path": str(self.config_example_path) if self.config_example_path else None,
            "local_config_path": str(self.local_config_path) if self.local_config_path else None,
            "audit_log_path": str(self.audit_log_path) if self.audit_log_path else None,
        }


class BaseDataPipeline(ABC):
    """Common contract for Nova-native data pipelines."""

    def __init__(self, manifest: PipelineManifest):
        self.manifest = manifest
        self._schema_manifest_cache: Optional[dict[str, Any]] = None
        self._query_template_cache: Optional[dict[str, dict[str, Any]]] = None
        self._field_dictionary_cache: Optional[dict[str, Any]] = None
        self._population_definitions_cache: Optional[dict[str, Any]] = None
        self._vendor_dictionary_cache: Optional[dict[str, Any]] = None
        self._predefined_reports_cache: Optional[dict[str, Any]] = None

    def load_schema_manifest(self) -> dict[str, Any]:
        if self._schema_manifest_cache is None:
            self._schema_manifest_cache = _read_json_dict(self.manifest.schema_manifest_path)
        return dict(self._schema_manifest_cache)

    def load_query_templates(self) -> dict[str, dict[str, Any]]:
        if self._query_template_cache is None:
            raw = _read_json_dict(self.manifest.query_templates_path)
            normalized: dict[str, dict[str, Any]] = {}
            for key, value in raw.items():
                if not isinstance(value, dict):
                    continue
                normalized[str(key)] = dict(value)
            self._query_template_cache = normalized
        return {name: dict(template) for name, template in self._query_template_cache.items()}

    def load_field_dictionary(self) -> dict[str, Any]:
        if self.manifest.field_dictionary_path is None:
            return {}
        if self._field_dictionary_cache is None:
            self._field_dictionary_cache = _read_json_dict(self.manifest.field_dictionary_path)
        return dict(self._field_dictionary_cache)

    def load_population_definitions(self) -> dict[str, Any]:
        if self.manifest.population_definitions_path is None:
            return {}
        if self._population_definitions_cache is None:
            self._population_definitions_cache = _read_json_dict(self.manifest.population_definitions_path)
        return dict(self._population_definitions_cache)

    def load_vendor_dictionary(self) -> dict[str, Any]:
        if self.manifest.vendor_dictionary_path is None:
            return {}
        if self._vendor_dictionary_cache is None:
            self._vendor_dictionary_cache = _read_json_dict(self.manifest.vendor_dictionary_path)
        return dict(self._vendor_dictionary_cache)

    def load_predefined_reports(self) -> dict[str, Any]:
        if self.manifest.predefined_reports_path is None:
            return {}
        if self._predefined_reports_cache is None:
            self._predefined_reports_cache = _read_json_dict(self.manifest.predefined_reports_path)
        return dict(self._predefined_reports_cache)

    def predefined_reports_summary(self) -> dict[str, Any]:
        reports = self.load_predefined_reports()
        if not reports:
            return {}
        source = reports.get("source") if isinstance(reports.get("source"), Mapping) else {}
        summary = reports.get("summary") if isinstance(reports.get("summary"), Mapping) else {}
        return {
            "source": dict(source),
            "summary": dict(summary),
            "top_tables": list(reports.get("top_tables") or [])[:12],
            "top_population_filters": list(reports.get("top_population_filters") or [])[:12],
        }

    def vendor_dictionary_summary(self) -> dict[str, Any]:
        dictionary = self.load_vendor_dictionary()
        if not dictionary:
            return {}
        source = dictionary.get("source") if isinstance(dictionary.get("source"), Mapping) else {}
        return {
            "source": dict(source),
            "table_count": int(dictionary.get("table_count") or 0),
            "path": str(self.manifest.vendor_dictionary_path) if self.manifest.vendor_dictionary_path else "",
        }

    def search_vendor_dictionary(self, query: str, *, limit: int = 12) -> dict[str, Any]:
        needle = " ".join(str(query or "").lower().split())
        if not needle:
            return {"ok": False, "pipeline_id": self.manifest.pipeline_id, "error": "query_required", "matches": []}
        dictionary = self.load_vendor_dictionary()
        source = dictionary.get("source") if isinstance(dictionary.get("source"), Mapping) else {}
        matches: list[dict[str, Any]] = []
        for table in dictionary.get("tables") or []:
            if not isinstance(table, Mapping):
                continue
            table_name = str(table.get("table") or "")
            title = str(table.get("title") or "")
            table_text = f"{table_name} {title}".lower()
            table_score = 6 if needle in table_name.lower() else 4 if needle in table_text else 0
            column_hits: list[dict[str, str]] = []
            for column in table.get("columns") or []:
                if not isinstance(column, Mapping):
                    continue
                column_name = str(column.get("name") or "")
                description = str(column.get("description") or "")
                haystack = f"{column_name} {description}".lower()
                if needle in haystack:
                    column_hits.append({
                        "name": column_name,
                        "data_type": str(column.get("data_type") or ""),
                        "description": description,
                    })
            if table_score or column_hits:
                score = table_score + min(len(column_hits), 6)
                matches.append({
                    "table": table_name,
                    "title": title,
                    "page": table.get("page"),
                    "score": score,
                    "column_hits": column_hits[:8],
                    "column_count": len(table.get("columns") or []),
                })
        matches.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("table") or "")))
        return {
            "ok": True,
            "pipeline_id": self.manifest.pipeline_id,
            "query": query,
            "grounding_status": source.get("grounding_status") or "vendor_dictionary",
            "match_count": len(matches),
            "matches": matches[: max(1, int(limit))],
        }

    def _vendor_table_match(self, table_name: str) -> dict[str, Any]:
        wanted = str(table_name or "").strip().lower()
        if not wanted:
            return {}
        dictionary = self.load_vendor_dictionary()
        for table in dictionary.get("tables") or []:
            if isinstance(table, Mapping) and str(table.get("table") or "").lower() == wanted:
                return {
                    "table": str(table.get("table") or table_name),
                    "title": str(table.get("title") or ""),
                    "page": table.get("page"),
                    "column_count": len(table.get("columns") or []),
                    "column_hits": [
                        {
                            "name": str(column.get("name") or ""),
                            "data_type": str(column.get("data_type") or ""),
                            "description": str(column.get("description") or ""),
                        }
                        for column in table.get("columns") or []
                        if isinstance(column, Mapping)
                    ][:8],
                }
        return {}

    def plan_report(self, request: str, *, limit: int = 8) -> dict[str, Any]:
        text = str(request or "").strip()
        if not text:
            return {"ok": False, "pipeline_id": self.manifest.pipeline_id, "error": "request_required"}

        populations_payload = self.load_population_definitions()
        populations = populations_payload.get("populations") if isinstance(populations_payload.get("populations"), list) else []
        request_low = text.lower()
        matched_populations: list[dict[str, Any]] = []
        for population in populations:
            if not isinstance(population, Mapping):
                continue
            key = str(population.get("key") or "").strip()
            label = str(population.get("label") or "").strip()
            candidates = {key.lower(), label.lower()}
            if key == "eb":
                candidates.update({"emergent bilingual", "english learner"})
            if key == "sped":
                candidates.update({"special education", "special ed"})
            if key == "plan504":
                candidates.update({"504", "section 504"})
            if any(candidate and candidate in request_low for candidate in candidates):
                matched_populations.append(dict(population))

        search_terms = _tokens(text)
        token_set = set(search_terms)
        group_by = [
            grouping
            for grouping, aliases in _GROUPING_ALIASES.items()
            if token_set.intersection(aliases) or any(alias in request_low for alias in aliases)
        ]
        for population in matched_populations:
            search_terms.extend(
                token
                for token in (str(population.get("key") or ""), str(population.get("label") or ""), "reg_programs")
                if token
            )
        if any(term in {"campus", "building", "school"} for term in search_terms):
            search_terms.extend(["reg", "building"])
        if any(term in {"entry", "withdrawal", "enrollment", "timeline", "grade"} for term in search_terms):
            search_terms.append("reg_entry_with")

        table_scores: dict[str, dict[str, Any]] = {}
        for term in dict.fromkeys(search_terms):
            result = self.search_vendor_dictionary(term, limit=limit)
            for match in result.get("matches") or []:
                if not isinstance(match, Mapping):
                    continue
                table = str(match.get("table") or "")
                if not table:
                    continue
                current = table_scores.setdefault(
                    table,
                    {
                        "table": table,
                        "title": match.get("title") or "",
                        "page": match.get("page"),
                        "score": 0,
                        "matched_terms": [],
                        "column_hits": [],
                    },
                )
                current["score"] = int(current.get("score") or 0) + int(match.get("score") or 1)
                if term not in current["matched_terms"]:
                    current["matched_terms"].append(term)
                for column in match.get("column_hits") or []:
                    if isinstance(column, Mapping) and column not in current["column_hits"]:
                        current["column_hits"].append(dict(column))

        if matched_populations:
            source = populations_payload.get("source") if isinstance(populations_payload.get("source"), Mapping) else {}
            join_pattern = populations_payload.get("join_pattern") if isinstance(populations_payload.get("join_pattern"), Mapping) else {}
            for table in (source.get("table"), join_pattern.get("table")):
                table_name = str(table or "").strip()
                if not table_name:
                    continue
                search = self.search_vendor_dictionary(table_name.split(".")[-1], limit=3)
                match = next(
                    (
                        item
                        for item in search.get("matches") or []
                        if isinstance(item, Mapping) and str(item.get("table") or "").lower() == table_name.lower()
                    ),
                    {},
                )
                current = table_scores.setdefault(
                    table_name,
                    {
                        "table": table_name,
                        "title": match.get("title") if isinstance(match, Mapping) else "",
                        "page": match.get("page") if isinstance(match, Mapping) else None,
                        "score": 0,
                        "matched_terms": [],
                        "column_hits": [],
                    },
                )
                current["score"] = int(current.get("score") or 0) + 100
                if "population_definition" not in current["matched_terms"]:
                    current["matched_terms"].append("population_definition")
                if isinstance(match, Mapping):
                    for column in match.get("column_hits") or []:
                        if isinstance(column, Mapping) and column not in current["column_hits"]:
                            current["column_hits"].append(dict(column))

        known_templates = self.load_query_templates()
        suggested_operation = ""
        if matched_populations and "program_membership_lookup" in known_templates:
            suggested_operation = "program_membership_lookup"
        elif any("campus" in term or "building" in term for term in search_terms) and "campus_enrollment_summary" in known_templates:
            suggested_operation = "campus_enrollment_summary"
        elif "student_lookup" in known_templates:
            suggested_operation = "student_lookup"

        required_table_names = list(_OPERATION_TABLE_HINTS.get(suggested_operation, ()))
        if "campus" in group_by and "dbo.REG_BUILDING" not in required_table_names:
            required_table_names.append("dbo.REG_BUILDING")

        required_tables = []
        for table_name in required_table_names:
            match = self._vendor_table_match(table_name)
            table_plan = {
                "table": table_name,
                "title": match.get("title") or "",
                "page": match.get("page"),
                "reason": "governed_operation",
                "role": "fact_source",
                "column_hits": match.get("column_hits") or [],
            }
            if table_name == "dbo.REG_PROGRAMS" and matched_populations:
                table_plan["reason"] = "population_definition"
            elif table_name == "dbo.REG" and group_by:
                table_plan["reason"] = "student_base_and_grouping"
            elif table_name == "dbo.REG_BUILDING" and "campus" in group_by:
                table_plan["reason"] = "campus_name_lookup"
                table_plan["role"] = "support_lookup"
                table_plan["join_key"] = "BUILDING"
                table_plan["active_status_note"] = (
                    "Use for campus metadata joined by building/location number. "
                    "Official campus active/inactive status is unresolved and likely comes from another table or district rule."
                )
                table_plan["active_status_source"] = "unresolved"
                table_plan["activity_inference"] = {
                    "signal": "current_student_records_by_building",
                    "evidence_tables": ["dbo.REG"],
                    "join_rule": "dbo.REG.BUILDING = dbo.REG_BUILDING.BUILDING",
                    "student_status_rule": (
                        "Use current/active registration records, such as REG.CURRENT_STATUS = 'A', "
                        "after confirming the live district status rule."
                    ),
                    "meaning": (
                        "A building with current student records tied to its building/location number "
                        "is operational evidence that the campus is active or in use."
                    ),
                }
                table_plan["active_status_candidates_to_verify"] = [
                    {
                        "table": "dbo.REGTB_BLDG_TYPES",
                        "field": "ACTIVE",
                        "caution": "May mark active building-type codes, not individual active campuses.",
                    }
                ]
            required_tables.append(table_plan)

            current = table_scores.setdefault(
                table_name,
                {
                    "table": table_name,
                    "title": match.get("title") or "",
                    "page": match.get("page"),
                    "score": 0,
                    "matched_terms": [],
                    "column_hits": [],
                },
            )
            current["score"] = int(current.get("score") or 0) + 75
            if "governed_operation" not in current["matched_terms"]:
                current["matched_terms"].append("governed_operation")
            for column in match.get("column_hits") or []:
                if isinstance(column, Mapping) and column not in current["column_hits"]:
                    current["column_hits"].append(dict(column))

        candidate_tables = sorted(table_scores.values(), key=lambda item: (-int(item.get("score") or 0), str(item.get("table") or "")))[: max(1, int(limit))]
        missing_inputs = []
        if not matched_populations and any(term in {"population", "populations", "program"} for term in search_terms):
            missing_inputs.append("which student population or program definition")
        if not candidate_tables:
            missing_inputs.append("which SIS subject area or known table family")
        filters = []
        for population in matched_populations:
            filters.append(
                {
                    "type": "population",
                    "key": population.get("key"),
                    "program_id": population.get("program_id"),
                    "field_number": population.get("field_number"),
                    "active_only": bool(population.get("active_only")),
                    "source_table": populations_payload.get("source", {}).get("table")
                    if isinstance(populations_payload.get("source"), Mapping)
                    else "dbo.REG_PROGRAMS",
                }
            )

        return {
            "ok": True,
            "pipeline_id": self.manifest.pipeline_id,
            "request": text,
            "grounding_status": "vendor_dictionary_grounded",
            "live_schema_status": "not_verified_by_live_inventory",
            "default_row_limit": 20,
            "intent": {
                "report_kind": "student_population" if matched_populations else "student_registration",
                "group_by": group_by,
                "filters": filters,
                "needs_clarification": bool(missing_inputs),
                "missing_inputs": missing_inputs,
            },
            "matched_populations": matched_populations,
            "required_tables": required_tables,
            "candidate_tables": candidate_tables,
            "suggested_operation": suggested_operation,
            "next_step": "Review this plan, then run a governed preview or capped live read only after the tables and filters look right.",
        }

    def schema_probe(self) -> dict[str, Any]:
        schema = self.load_schema_manifest()
        return {
            "pipeline_id": self.manifest.pipeline_id,
            "display_name": self.manifest.display_name,
            "kind": self.manifest.kind,
            "read_only": self.manifest.read_only,
            "network_scope": self.manifest.network_scope,
            "schema": schema,
            "field_dictionary": self.load_field_dictionary(),
            "population_definitions": self.load_population_definitions(),
            "vendor_dictionary": self.vendor_dictionary_summary(),
            "predefined_reports": self.predefined_reports_summary(),
            "query_templates": sorted(self.load_query_templates().keys()),
            "query_template_catalog": self.load_query_templates(),
        }

    @abstractmethod
    def status(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def safe_query(
        self,
        operation: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        row_limit: Optional[int] = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        raise NotImplementedError
