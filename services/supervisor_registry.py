from __future__ import annotations


CHAT_SUPERVISOR_RETIRED_RULE_NAMES = frozenset({
    "grounded_self_report",
    "runtime_identity",
    "capability_inventory",
    "reflective_retry",
    "profile_certainty",
    "identity_history_family",
    "open_probe_family",
    "session_fact_recall",
    "developer_profile_state",
    "last_question_recall",
    "self_location",
    "rules_list",
    "location_recall",
    "location_name",
    "name_origin_store",
    "apply_correction",
    "smalltalk",
    "store_fact",
    "capability_query",
    "policy_domain_query",
    "assistant_name",
    "self_identity_web_challenge",
    "name_origin",
    "developer_full_name",
    "developer_profile",
    "session_summary",
    "set_location",
    "location_weather",
    "retrieval_followup",
    "web_research_family",
    "weather_lookup",
})


_ALL_SUPERVISOR_RULE_SPECS = [
    {"name": "grounded_self_report", "priority": 20, "phases": ("intent",)},
    {"name": "runtime_identity", "priority": 21, "phases": ("intent",)},
    {"name": "capability_inventory", "priority": 22, "phases": ("intent",)},
    {"name": "reflective_retry", "priority": 30, "phases": ("rewrite", "handle")},
    {"name": "profile_certainty", "priority": 35, "phases": ("handle",)},
    {"name": "identity_history_family", "priority": 36, "phases": ("handle",)},
    {"name": "open_probe_family", "priority": 37, "phases": ("handle",)},
    {"name": "session_fact_recall", "priority": 38, "phases": ("handle",)},
    {"name": "developer_profile_state", "priority": 38, "phases": ("state",)},
    {"name": "last_question_recall", "priority": 39, "phases": ("handle",)},
    {"name": "self_location", "priority": 40, "phases": ("handle",)},
    {"name": "rules_list", "priority": 41, "phases": ("handle",)},
    {"name": "location_recall", "priority": 42, "phases": ("handle",)},
    {"name": "location_name", "priority": 44, "phases": ("handle",)},
    {"name": "location_weather", "priority": 46, "phases": ("handle",)},
    {"name": "retrieval_followup", "priority": 47, "phases": ("handle",)},
    {"name": "name_origin_store", "priority": 50, "phases": ("handle",)},
    {"name": "apply_correction", "priority": 60, "phases": ("handle",)},
    {"name": "smalltalk", "priority": 61, "phases": ("intent",)},
    {"name": "store_fact", "priority": 62, "phases": ("intent",)},
    {"name": "web_research_family", "priority": 62, "phases": ("intent",)},
    {"name": "weather_lookup", "priority": 62, "phases": ("intent",)},
    {"name": "set_location", "priority": 62, "phases": ("intent",)},
    {"name": "capability_query", "priority": 63, "phases": ("intent",)},
    {"name": "policy_domain_query", "priority": 64, "phases": ("intent",)},
    {"name": "assistant_name", "priority": 66, "phases": ("intent",)},
    {"name": "self_identity_web_challenge", "priority": 67, "phases": ("intent",)},
    {"name": "name_origin", "priority": 68, "phases": ("intent",)},
    {"name": "developer_full_name", "priority": 69, "phases": ("intent",)},
    {"name": "developer_profile", "priority": 70, "phases": ("intent",)},
    {"name": "session_summary", "priority": 71, "phases": ("intent",)},
]


DEFAULT_SUPERVISOR_RULE_SPECS = [
    spec
    for spec in _ALL_SUPERVISOR_RULE_SPECS
    if str(spec.get("name") or "") not in CHAT_SUPERVISOR_RETIRED_RULE_NAMES
]
