from __future__ import annotations

"""
Ed-Fi report presentation layer.

Turns raw ODS JSON into stable, human-readable rows for Nova reports/dashboards.
This is the "clean the pipe" step — not a full PEIMS product and not a SIS clone.

Crosswalks stay thin and only cover intents we expose (schools, students, health).
"""

from typing import Any, Mapping

from services.edfi.district_scope import normalize_district_lea_id


def _dig(item: Mapping[str, Any], *path: str) -> Any:
    cur: Any = item
    for key in path:
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(key)
    return cur


def _descriptor_tail(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    # Ed-Fi descriptors often look like uri://.../SchoolTypeDescriptor#Regular
    if "#" in text:
        return text.rsplit("#", 1)[-1].strip()
    if "/" in text:
        return text.rstrip("/").rsplit("/", 1)[-1].strip()
    return text


def format_lea_display(value: Any) -> str:
    """Prefer 6-digit PEIMS-style when identity is known; keep raw if not numeric."""
    key = normalize_district_lea_id(value)
    if key is None:
        return str(value or "").strip()
    # Texas LEAs are commonly shown zero-padded to 6 digits
    return f"{key:06d}"


def shape_school_row(item: Mapping[str, Any]) -> dict[str, Any]:
    lea = _dig(item, "localEducationAgencyReference", "localEducationAgencyId")
    if lea is None:
        lea = item.get("localEducationAgencyId")
    grade_levels = item.get("gradeLevels") or []
    grades: list[str] = []
    if isinstance(grade_levels, list):
        for gl in grade_levels:
            if isinstance(gl, Mapping):
                grades.append(_descriptor_tail(gl.get("gradeLevelDescriptor")))
            else:
                grades.append(_descriptor_tail(gl))
    return {
        "school_id": str(item.get("schoolId") or item.get("educationOrganizationId") or "").strip(),
        "school_name": str(item.get("nameOfInstitution") or item.get("shortNameOfInstitution") or "").strip(),
        "lea_id": format_lea_display(lea) if lea not in (None, "") else "",
        "lea_id_edfi": str(normalize_district_lea_id(lea) or "").strip(),
        "school_type": _descriptor_tail(item.get("schoolTypeDescriptor")),
        "operational_status": _descriptor_tail(item.get("operationalStatusDescriptor")),
        "grade_levels": ", ".join(g for g in grades if g),
        "title_i_part_a": _descriptor_tail(item.get("titleIPartASchoolDesignationDescriptor")),
    }


def shape_student_row(item: Mapping[str, Any]) -> dict[str, Any]:
    # Prefer non-PII identifiers for default report rows
    name_parts = []
    for key in ("firstName", "middleName", "lastSurname"):
        val = str(item.get(key) or "").strip()
        if val:
            name_parts.append(val)
    display = " ".join(name_parts).strip()
    if not display:
        display = str(item.get("studentUniqueId") or "").strip()
    return {
        "student_unique_id": str(item.get("studentUniqueId") or "").strip(),
        "display_name": display,
        "birth_date": str(item.get("birthDate") or "").strip(),  # may be redacted later
        "sex": _descriptor_tail(item.get("birthSexDescriptor") or item.get("sexDescriptor")),
    }


def shape_association_row(item: Mapping[str, Any]) -> dict[str, Any]:
    school = _dig(item, "schoolReference", "schoolId")
    student = _dig(item, "studentReference", "studentUniqueId")
    return {
        "student_unique_id": str(student or item.get("studentUniqueId") or "").strip(),
        "school_id": str(school or item.get("schoolId") or "").strip(),
        "entry_date": str(item.get("entryDate") or "").strip(),
        "exit_withdraw_date": str(item.get("exitWithdrawDate") or "").strip(),
        "entry_type": _descriptor_tail(item.get("entryTypeDescriptor")),
        "exit_withdraw_type": _descriptor_tail(item.get("exitWithdrawTypeDescriptor")),
        "primary_school": item.get("primarySchool"),
    }


def shape_health_row(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "connection_id": str(raw.get("connection_id") or "").strip(),
        "health": str(raw.get("health") or ("ok" if raw.get("ok") else "unknown")).strip(),
        "base_url": str(raw.get("base_url") or "").strip(),
        "lea_id": format_lea_display(raw.get("district_lea_id")),
        "resource_count": raw.get("resource_count") or raw.get("catalog_count") or 0,
        "api_version": str(raw.get("api_version") or "").strip(),
        "data_model_version": str(raw.get("data_model_version") or "").strip(),
        "auth_ok": bool(raw.get("auth_ok") if "auth_ok" in raw else raw.get("ok")),
        "scope_mode": str(raw.get("scope_mode") or "").strip(),
        "credential_access_tier": str(raw.get("credential_access_tier") or "").strip(),
    }


def shape_resource_name_rows(names: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in names:
        text = str(name or "").strip()
        if not text:
            continue
        ns = ""
        short = text
        if "/" in text:
            ns, short = text.split("/", 1)
        rows.append({"resource": text, "namespace": ns, "name": short})
    return rows


SCHOOL_COLUMNS = [
    "school_id",
    "school_name",
    "lea_id",
    "school_type",
    "operational_status",
    "grade_levels",
]
STUDENT_COLUMNS = ["student_unique_id", "display_name", "sex"]
ASSOC_COLUMNS = [
    "student_unique_id",
    "school_id",
    "entry_date",
    "exit_withdraw_date",
    "entry_type",
    "primary_school",
]
HEALTH_COLUMNS = [
    "connection_id",
    "health",
    "lea_id",
    "resource_count",
    "api_version",
    "auth_ok",
    "scope_mode",
]
RESOURCE_COLUMNS = ["resource", "namespace", "name"]


def present_operation_result(
    operation: str,
    raw: Mapping[str, Any],
    *,
    include_raw_sample: bool = False,
) -> dict[str, Any]:
    """
    Build report-friendly presentation for a live operation result.

    Returns columns + rows + a short summary string for chat/dashboard use.
    """
    op = str(operation or "").strip()
    rows: list[dict[str, Any]] = []
    columns: list[str] = []
    intent = op

    if op == "list_schools":
        columns = list(SCHOOL_COLUMNS)
        rows = [shape_school_row(i) for i in (raw.get("items") or []) if isinstance(i, dict)]
        intent = "schools_directory"
    elif op == "list_students":
        columns = list(STUDENT_COLUMNS)
        rows = [shape_student_row(i) for i in (raw.get("items") or []) if isinstance(i, dict)]
        intent = "students_directory"
    elif op == "student_school_associations":
        columns = list(ASSOC_COLUMNS)
        rows = [shape_association_row(i) for i in (raw.get("items") or []) if isinstance(i, dict)]
        intent = "enrollments"
    elif op == "connection_health":
        columns = list(HEALTH_COLUMNS)
        rows = [shape_health_row(raw)]
        intent = "connection_health"
    elif op == "sync_status":
        columns = sorted(str(k) for k in raw.keys() if k not in {"items"})
        rows = [{k: raw.get(k) for k in columns}]
        intent = "sync_status"
    elif op == "list_resources":
        columns = list(RESOURCE_COLUMNS)
        names = raw.get("resources") or raw.get("items") or []
        if names and isinstance(names[0], dict):
            names = [n.get("resource") or n.get("name") for n in names]
        rows = shape_resource_name_rows(list(names or []))
        intent = "resource_catalog"
    elif op == "changes_since":
        columns = list(SCHOOL_COLUMNS)  # often schools; fall back to generic keys
        items = [i for i in (raw.get("items") or []) if isinstance(i, dict)]
        if items and "schoolId" in items[0]:
            rows = [shape_school_row(i) for i in items]
            intent = "changes_schools"
        else:
            # generic thin shape
            keys: list[str] = []
            seen: set[str] = set()
            for item in items[:3]:
                for k in item.keys():
                    if k not in seen and not isinstance(item.get(k), (dict, list)):
                        seen.add(str(k))
                        keys.append(str(k))
            columns = keys[:8] or ["id"]
            rows = [{k: item.get(k) for k in columns} for item in items]
            intent = "changes"
    else:
        items = [i for i in (raw.get("items") or []) if isinstance(i, dict)]
        if items:
            columns = [str(k) for k in list(items[0].keys())[:8]]
            rows = [{k: item.get(k) for k in columns} for item in items]
        else:
            columns = ["value"]
            rows = []

    summary = _summary_line(intent, rows, raw)
    out: dict[str, Any] = {
        "report_intent": intent,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "summary": summary,
        "reader_friendly": True,
    }
    if include_raw_sample and rows:
        # never dump full raw PII blob by default
        out["raw_keys_sample"] = sorted(
            {
                str(k)
                for item in (raw.get("items") or [])[:1]
                if isinstance(item, dict)
                for k in item.keys()
            }
        )[:24]
    return out


def _summary_line(intent: str, rows: list[dict[str, Any]], raw: Mapping[str, Any]) -> str:
    n = len(rows)
    if intent == "connection_health":
        if not rows:
            return "Ed-Fi connection health unavailable."
        r = rows[0]
        return (
            f"Ed-Fi connection '{r.get('connection_id') or '?'}' health={r.get('health') or '?'} "
            f"LEA={r.get('lea_id') or '?'} resources={r.get('resource_count') or 0}."
        )
    if intent == "schools_directory":
        if n == 0:
            return "No schools returned for this LEA scope."
        names = [str(r.get("school_name") or r.get("school_id") or "") for r in rows[:3]]
        names = [x for x in names if x]
        more = f" (+{n - 3} more)" if n > 3 else ""
        return f"{n} school(s): " + ", ".join(names) + more + "."
    if intent == "students_directory":
        return f"{n} student record(s) in this page." if n else "No students returned for this LEA scope."
    if intent == "enrollments":
        return f"{n} student–school association(s) in this page." if n else "No associations returned."
    if intent == "resource_catalog":
        return f"{n} resource name(s) in catalog page." if n else "Resource catalog empty."
    if n:
        return f"{n} row(s) for {intent}."
    return f"No rows for {intent}."
