# tests/test_core_seam_locks.py
from __future__ import annotations

import ast
from pathlib import Path


CORE_PATH = Path("nova_core.py")


SEAMS: dict[str, dict[str, object]] = {
    "hard_answer": {
        "must_contain": ["truth_hard_answer("],
        "must_not_contain": [
            "_arithmetic_expression_reply(",
            "get_learned_fact(",
            "_speaker_matches_developer(",
            "_self_identity_web_challenge_reply(",
            "get_name_origin_story(",
            "describe_capabilities(",
            "mem_get_recent_learned(",
        ],
        "max_if_count": 0,
    },
    "handle_keywords": {
        "must_contain": ["service_handle_keywords(", "is_brief_command_form_fn=service_is_brief_command_form"],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_is_brief_command_form": {
        "must_contain": ["service_is_brief_command_form("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "handle_commands": {
        "must_contain": ["service_handle_commands(", "core=sys.modules[__name__]"],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "run_loop": {
        "must_contain": ["service_run_loop(", "core=sys.modules[__name__]"],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "mem_recall": {
        "must_contain": ["memory_learning_mem_recall("],
        "must_not_contain": [
            "mem_enabled",
            "memory_mod.recall",
            "subprocess.run",
            "_format_memory_recall_hits",
            "_record_memory_event",
            "_memory_runtime_user",
            "mem_context_top_k",
            "mem_min_score",
            "mem_exclude_sources",
        ],
        "max_if_count": 0,
    },
    "_classify_name_origin_outcome": {
        "must_contain": ["service_classify_name_origin_outcome("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_execute_identity_history_outcome": {
        "must_contain": ["service_execute_identity_history_outcome("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_open_probe_reply": {
        "must_contain": ["service_open_probe_reply("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_truthful_limit_reply": {
        "must_contain": ["service_truthful_limit_reply("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_attach_learning_invitation": {
        "must_contain": ["service_attach_learning_invitation("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_truthful_limit_outcome": {
        "must_contain": ["service_truthful_limit_outcome("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_last_question_recall_reply": {
        "must_contain": ["service_last_question_recall_reply("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_session_fact_recall_reply": {
        "must_contain": ["service_session_fact_recall_reply("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_execute_retrieval_followup_outcome": {
        "must_contain": ["service_execute_retrieval_followup_outcome("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_session_recap_reply": {
        "must_contain": ["service_session_recap_reply("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_action_history_reply": {
        "must_contain": ["service_action_history_reply("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "truth_hierarchy_answer": {
        "must_contain": ["service_truth_hierarchy_answer("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "start_action_ledger_record": {
        "must_contain": ["service_start_action_ledger_record("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "finalize_action_ledger_record": {
        "must_contain": ["service_finalize_action_ledger_record("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_developer_profile_reply": {
        "must_contain": ["service_developer_profile_reply("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_identity_profile_followup_reply": {
        "must_contain": ["service_identity_profile_followup_reply("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_identity_name_followup_reply": {
        "must_contain": ["service_identity_name_followup_reply("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "_developer_identity_followup_reply": {
        "must_contain": ["service_developer_identity_followup_reply("],
        "must_not_contain": [],
        "max_if_count": 0,
    },
    "mem_add": {
        "must_contain": ["memory_learning_mem_add("],
        "must_not_contain": [
            "mem_enabled",
            "_identity_memory_text_allowed",
            "_memory_should_keep_text",
            "memory_mod.recall_explain",
            "memory_mod.add_memory",
            "subprocess.run",
            "_record_memory_event",
            "_memory_write_user",
            "mem_scope",
            "mem_min_score",
        ],
        "max_if_count": 0,
    },
    "learn_from_user_correction": {
        "must_contain": ["memory_learning_learn_from_user_correction("],
        "must_not_contain": [
            "get_learned_fact",
            "mem_add",
            "re.",
            "search(",
            "match(",
            "split(",
            "save_learned_facts",
            "set_active_user",
            "facts[",
            "append(",
        ],
        "max_if_count": 0,
    },
    "ollama_chat": {
        "must_contain": ["service_ollama_chat("],
        "must_not_contain": [
            "requests.post",
            "kill_ollama",
            "start_ollama_serve_detached",
            "warn(",
            "payload =",
            "system_msg =",
            "identity_context_for_prompt(",
            "_language_mix_instruction(",
            "chat_model(",
            "OLLAMA_BASE",
            "OLLAMA_REQ_TIMEOUT",
        ],
        "max_if_count": 0,
    },
    "patch_preview": {
        "must_contain": ["service_patch_preview("],
        "must_not_contain": [
            "zipfile.ZipFile",
            "tempfile.TemporaryDirectory",
            "difflib.unified_diff",
            "_read_patch_manifest",
            "_read_patch_revision",
            "BASE_DIR",
            "UPDATES_DIR",
            "lines.append(",
        ],
        "max_if_count": 0,
    },
    "patch_apply": {
        "must_contain": ["service_patch_apply("],
        "must_not_contain": [
            "patch_preview(",
            "policy_patch(",
            "_read_patch_manifest",
            "_read_patch_revision",
            "_log_patch(",
            "_patch_reject_message(",
            "_snapshot_current(",
            "_overlay_zip(",
            "_py_compile_check(",
            "patch_rollback(",
            "_behavioral_check(",
            "_write_patch_revision(",
            '"Status: eligible"',
            "re.search(",
        ],
        "max_if_count": 0,
    },
    "_handle_supervisor_intent": {
        "must_contain": ["service_handle_supervisor_intent("],
        "must_not_contain": [
            "intent ==",
            "execute_planned_action(",
            "mem_add(",
            "set_location_text(",
            "_parse_correction(",
            "_teach_store_example(",
            "_quick_smalltalk_reply(",
            "describe_capabilities(",
            "policy_web(",
        ],
        "max_if_count": 0,
    },
}


def _source() -> str:
    return CORE_PATH.read_text(encoding="utf-8")


def _function_source(src: str, fn_name: str) -> str:
    module = ast.parse(src)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            seg = ast.get_source_segment(src, node)
            if not seg:
                raise AssertionError(f"Could not extract source for {fn_name}")
            return seg
    raise AssertionError(f"Function not found: {fn_name}")


def _if_count(fn_src: str) -> int:
    # Count actual "if" statements in the function body only.
    tree = ast.parse(fn_src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    return sum(isinstance(n, ast.If) for n in ast.walk(fn))


def test_core_seam_locks() -> None:
    src = _source()
    failures: list[str] = []

    for fn_name, rules in SEAMS.items():
        fn_src = _function_source(src, fn_name)

        for token in rules["must_contain"]:
            if token not in fn_src:
                failures.append(f"{fn_name}: missing required delegation marker {token!r}")

        for token in rules["must_not_contain"]:
            if token in fn_src:
                failures.append(f"{fn_name}: forbidden inline token still present {token!r}")

        max_if_count = int(rules["max_if_count"])
        actual_if_count = _if_count(fn_src)
        if actual_if_count > max_if_count:
            failures.append(
                f"{fn_name}: expected <= {max_if_count} if-statements, found {actual_if_count}"
            )

    if failures:
        raise AssertionError("Core seam lock failed:\n- " + "\n- ".join(failures))
