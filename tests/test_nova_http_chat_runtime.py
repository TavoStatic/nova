import unittest
from unittest.mock import patch

import nova_http
from services.nova_http_chat_runtime import HTTP_CHAT_RUNTIME_SERVICE


class _FakeSession:
    def __init__(self):
        self.pending_action = None
        self.pending_correction_target = None
        self.conversation_state = {"kind": "idle"}
        self.continuation_used_last_turn = False
        self.prefer_web_for_data_queries = False
        self.language_mix_spanish_pct = 0

    def reset_turn_flags(self):
        return None

    def active_subject(self):
        return ""

    def reflection_summary(self):
        return {"overrides_active": []}

    def set_pending_action(self, payload):
        self.pending_action = payload

    def apply_state_update(self, payload, fallback_state=None):
        self.conversation_state = payload

    def set_retrieval_state(self, payload):
        self.conversation_state = payload


class _SessionManager:
    def __init__(self, session):
        self._session = session

    def get(self, _session_id: str):
        return self._session


class TestNovaHttpChatRuntimeService(unittest.TestCase):
    def test_process_chat_returns_ok_for_empty_text_and_restores_active_user(self):
        invalidations = []

        with patch.object(nova_http.nova_core, "get_active_user", return_value="runner"), \
             patch.object(nova_http.nova_core, "set_active_user") as set_user_mock, \
             patch.object(nova_http.nova_core, "_strip_invocation_prefix", return_value=""):
            reply = HTTP_CHAT_RUNTIME_SERVICE.process_chat(
                "s-empty",
                "   ",
                user_id="worker",
                core_module=nova_http.nova_core,
                session_state_manager=nova_http.SESSION_STATE_MANAGER,
                turn_entry_service=nova_http.HTTP_TURN_ENTRY_SERVICE,
                chat_orchestration_service=nova_http.HTTP_CHAT_ORCHESTRATION_SERVICE,
                turn_finalization_service=nova_http.HTTP_TURN_FINALIZATION_SERVICE,
                http_chat_flow_module=nova_http.http_chat_flow,
                append_session_turn_fn=nova_http._append_session_turn,
                generate_chat_reply_fn=nova_http._generate_chat_reply,
                invalidate_control_status_cache_fn=lambda: invalidations.append(True),
                fast_smalltalk_reply_fn=nova_http._fast_smalltalk_reply,
                is_developer_profile_request_fn=nova_http._is_developer_profile_request,
                developer_profile_reply_fn=nova_http._developer_profile_reply,
                learn_contextual_developer_facts_fn=nova_http._learn_contextual_developer_facts,
                extract_memory_teach_text_fn=nova_http._extract_memory_teach_text,
            )

        self.assertEqual(reply, "Okay.")
        self.assertEqual(invalidations, [True])
        self.assertEqual(set_user_mock.call_args_list[0].args, ("worker",))
        self.assertEqual(set_user_mock.call_args_list[-1].args, ("runner",))

    def test_process_chat_finalizes_handled_turn_entry(self):
        session = _FakeSession()

        with patch.object(nova_http.nova_core, "get_active_user", return_value="runner"), \
             patch.object(nova_http.nova_core, "set_active_user") as set_user_mock, \
             patch.object(nova_http.nova_core, "_strip_invocation_prefix", side_effect=lambda text: text), \
             patch.object(nova_http.nova_core, "start_action_ledger_record", return_value={"turn_acts": []}), \
             patch.object(
                 nova_http.HTTP_TURN_ENTRY_SERVICE,
                 "execute_turn_entry",
                 return_value={
                     "handled": True,
                     "flow_result": {
                         "reply": "runtime delegated",
                         "planner_decision": "deterministic",
                         "reply_contract": "turn.entry",
                         "reply_outcome": {},
                     },
                     "routing_decision": {"entry_point": "http"},
                     "conversation_state": {"kind": "idle"},
                 },
             ), \
             patch.object(nova_http.HTTP_TURN_FINALIZATION_SERVICE, "finalize_flow_reply", return_value="runtime delegated") as finalize_mock:
            reply = HTTP_CHAT_RUNTIME_SERVICE.process_chat(
                "s-runtime",
                "hello",
                core_module=nova_http.nova_core,
                session_state_manager=_SessionManager(session),
                turn_entry_service=nova_http.HTTP_TURN_ENTRY_SERVICE,
                chat_orchestration_service=nova_http.HTTP_CHAT_ORCHESTRATION_SERVICE,
                turn_finalization_service=nova_http.HTTP_TURN_FINALIZATION_SERVICE,
                http_chat_flow_module=nova_http.http_chat_flow,
                append_session_turn_fn=nova_http._append_session_turn,
                generate_chat_reply_fn=nova_http._generate_chat_reply,
                invalidate_control_status_cache_fn=nova_http._invalidate_control_status_cache,
                fast_smalltalk_reply_fn=nova_http._fast_smalltalk_reply,
                is_developer_profile_request_fn=nova_http._is_developer_profile_request,
                developer_profile_reply_fn=nova_http._developer_profile_reply,
                learn_contextual_developer_facts_fn=nova_http._learn_contextual_developer_facts,
                extract_memory_teach_text_fn=nova_http._extract_memory_teach_text,
            )

        self.assertEqual(reply, "runtime delegated")
        finalize_mock.assert_called_once()
        self.assertEqual(set_user_mock.call_args_list[-1].args, ("runner",))