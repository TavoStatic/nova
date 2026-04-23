# tests/test_core_seam_wiring.py
from pathlib import Path

CORE_PATH = Path("nova_core.py")

REQUIRED_MARKERS = [
    "truth_hard_answer",
    "memory_learning_mem_recall",
    "memory_learning_mem_add",
    "memory_learning_learn_from_user_correction",
    "service_ollama_chat",
    "service_patch_preview",
    "service_patch_apply",
    "service_handle_supervisor_intent",
    "service_run_loop",
    "service_handle_commands",
    "service_handle_keywords",
    "service_is_brief_command_form",
    "service_open_probe_reply",
    "service_truthful_limit_reply",
    "service_attach_learning_invitation",
    "service_truthful_limit_outcome",
    "service_execute_retrieval_followup_outcome",
    "service_last_question_recall_reply",
    "service_session_fact_recall_reply",
    "service_session_recap_reply",
    "service_truth_hierarchy_answer",
    "service_execute_planned_action",
    "service_classify_name_origin_outcome",
    "service_execute_identity_history_outcome",
    "service_action_history_reply",
    "service_start_action_ledger_record",
    "service_finalize_action_ledger_record",
    "_mem_recall_delegate_kwargs",
    "_mem_add_delegate_kwargs",
    "_learn_from_user_correction_delegate_kwargs",
    "_ollama_chat_delegate_kwargs",
    "_patch_preview_delegate_kwargs",
    "_patch_apply_delegate_kwargs",
    "_handle_supervisor_intent_delegate_kwargs",
]


def test_core_seam_wiring_markers_present() -> None:
    src = CORE_PATH.read_text(encoding="utf-8")
    missing = [m for m in REQUIRED_MARKERS if m not in src]
    assert not missing, "Missing seam wiring markers:\n- " + "\n- ".join(missing)
