# task_engine.py

from capabilities import has_capability


class TaskResult:
    def __init__(self, allow_llm=True, message=None):
        self.allow_llm = allow_llm
        self.message = message


SUGGESTIONS = {
    "database_connection": "Provide a read-only database connection string",
    "sis_attendance_table": "Provide the SIS attendance table name or schema",
    "student_records_table": "Provide the SIS student records table or schema",
    "query_execution": "Enable a safe SELECT-only SQL query runner",
    "web_access": "Enable the web tool and allowed domains in policy.json",
    "python_execution": "Enable a restricted Python execution environment"
}


def _looks_like_explicit_web_research(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False

    direct_phrases = [
        "just use the web",
        "use the web",
        "only need web",
        "all you need is the web",
        "all you need is web",
        "need is the web",
        "online about",
        "online for",
        "online on",
        "search online",
        "research online",
        "search the web",
        "web research",
        "web search",
        "find online",
        "look online",
        "anything online",
    ]
    if any(phrase in low for phrase in direct_phrases):
        return True

    research_terms = ["research", "search", "find", "lookup", "look up", "browse", "fetch"]
    web_terms = ["web", "online", "internet", "website", "site", "tea.texas.gov", "txschools.gov"]
    return any(term in low for term in research_terms) and any(term in low for term in web_terms)


def extract_requirements(user_text: str, config: dict | None = None) -> list[str]:

    t = user_text.lower().strip()
    req = set()
    cfg = config if isinstance(config, dict) else {}
    prefer_web_for_data_queries = bool(cfg.get("prefer_web_for_data_queries", False))

    def _looks_like_profile_statement(text: str) -> bool:
        low = (text or "").strip().lower()
        if not low or "?" in low:
            return False
        role_markers = [
            "developer",
            "engineer",
            "specialist",
            "analyst",
            "manager",
            "administrator",
            "teacher",
            "programmer",
            "full stack",
        ]
        if not any(marker in low for marker in role_markers):
            return False
        profile_markers = [
            " i am ",
            " i'm ",
            " he is ",
            " she's ",
            " she is ",
            " gus is ",
            " gustavo is ",
            " works as ",
            " work as ",
            " works in ",
        ]
        padded = f" {low} "
        return any(marker in padded for marker in profile_markers) or low.startswith("yes ")

    if _looks_like_profile_statement(t):
        return []

    # --------------------------------------------------
    # Knowledge / explanation questions
    # --------------------------------------------------

    knowledge_starters = [
        "what is",
        "what do you know",
        "tell me about",
        "explain",
        "define",
        "what else do you know"
    ]

    if any(t.startswith(k) for k in knowledge_starters):
        return []

    explicit_web_research = _looks_like_explicit_web_research(t)

    # --------------------------------------------------
    # SIS / student data / PEIMS
    # --------------------------------------------------

    sis_keywords = [
        "attendance",
        "ada",
        "peims",
        "enrollment",
        "withdrawal",
        "student",
        "grade",
        "transcript",
        "report card",
        "aeries",
        "skyward",
        "powerschool",
        "infinite campus",
        "records",
        "roster",
        "outcome",
        "list all",
        "show me"
    ]

    if any(kw in t for kw in sis_keywords) and not (explicit_web_research or prefer_web_for_data_queries):

        req.update([
            "database_connection",
            "query_execution"
        ])

        if any(kw in t for kw in ["attendance", "ada", "outcome"]):
            req.add("sis_attendance_table")

        if any(kw in t for kw in [
            "student",
            "grade",
            "transcript",
            "records",
            "roster",
            "report card",
            "list all",
            "show me"
        ]):
            req.add("student_records_table")

    # --------------------------------------------------
    # Web / external lookup
    # --------------------------------------------------

    web_keywords = [
        "web",
        "internet",
        "browse",
        "search",
        "lookup",
        "fetch",
        "tea.texas.gov",
        "txschools.gov",
        "guidelines",
        "manual",
        "data submission"
    ]

    if any(kw in t for kw in web_keywords):
        req.add("web_access")

    if explicit_web_research or prefer_web_for_data_queries:
        req.add("web_access")

    # --------------------------------------------------
    # Code execution requests
    # --------------------------------------------------

    code_keywords = [
        "run this code",
        "execute this code",
        "run python",
        "execute python",
        "run script",
        "run program"
    ]

    if any(kw in t for kw in code_keywords):
        req.add("python_execution")

    return sorted(req)


def analyze_request(user_text: str, config: dict | None = None) -> TaskResult:

    req = extract_requirements(user_text, config=config)

    # no special capability needed
    if not req:
        return TaskResult(allow_llm=True, message=None)

    missing = [r for r in req if not has_capability(r)]

    if not missing:
        return TaskResult(allow_llm=True, message=None)

    msg_lines = [
        "This task requires capabilities I don't currently have:"
    ]

    for m in missing:

        msg_lines.append(f"• {m}")

        if m in SUGGESTIONS:
            msg_lines.append(f"  Suggestion: {SUGGESTIONS[m]}")

    if "web_access" in missing and "tea" in user_text.lower():
        msg_lines.append("")
        msg_lines.append(
            "Note: Web access is restricted to official TEA/TSDS domains only."
        )

    return TaskResult(
        allow_llm=False,
        message="\n".join(msg_lines)
    )