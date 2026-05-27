import unittest
from types import SimpleNamespace
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

    def set_language_mix_spanish_pct(self, value):
        self.language_mix_spanish_pct = value

    def set_pending_action(self, payload):
        self.pending_action = payload

    def apply_state_update(self, payload, fallback_state=None):
        self.conversation_state = payload

    def set_conversation_state(self, payload):
        self.conversation_state = payload

    def set_retrieval_state(self, payload):
        self.conversation_state = payload

    def mark_continuation_used(self):
        self.continuation_used_last_turn = True


class _SessionManager:
    def __init__(self, session):
        self._session = session

    def get(self, _session_id: str):
        return self._session


class TestNovaHttpChatRuntimeService(unittest.TestCase):
    def test_process_chat_from_runtime_resolves_http_runtime_bundle(self):
        with patch.object(
            HTTP_CHAT_RUNTIME_SERVICE,
            "process_chat",
            return_value="runtime ok",
        ) as process_mock:
            reply = HTTP_CHAT_RUNTIME_SERVICE.process_chat_from_runtime(
                "sid",
                "hello",
                user_id="runner",
                core_module=nova_http.nova_core,
                runtime_scope={
                    "SESSION_STATE_MANAGER": nova_http.SESSION_STATE_MANAGER,
                    "HTTP_TURN_FINALIZATION_SERVICE": nova_http.HTTP_TURN_FINALIZATION_SERVICE,
                    "http_chat_flow": nova_http.http_chat_flow,
                    "_append_session_turn": nova_http._append_session_turn,
                    "_generate_chat_reply": nova_http._generate_chat_reply,
                    "_invalidate_control_status_cache": nova_http._invalidate_control_status_cache,
                },
            )

        self.assertEqual(reply, "runtime ok")
        self.assertEqual(process_mock.call_args.args[:2], ("sid", "hello"))
        self.assertEqual(process_mock.call_args.kwargs.get("user_id"), "runner")
        self.assertIs(process_mock.call_args.kwargs.get("session_state_manager"), nova_http.SESSION_STATE_MANAGER)
        self.assertIs(process_mock.call_args.kwargs.get("generate_chat_reply_fn"), nova_http._generate_chat_reply)
        self.assertNotIn("fast_smalltalk_reply_fn", process_mock.call_args.kwargs)
        self.assertNotIn("extract_memory_teach_text_fn", process_mock.call_args.kwargs)

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
                turn_finalization_service=nova_http.HTTP_TURN_FINALIZATION_SERVICE,
                http_chat_flow_module=nova_http.http_chat_flow,
                append_session_turn_fn=nova_http._append_session_turn,
                generate_chat_reply_fn=nova_http._generate_chat_reply,
                invalidate_control_status_cache_fn=lambda: invalidations.append(True),
            )

        self.assertEqual(reply, "Okay.")
        self.assertEqual(invalidations, [True])
        self.assertEqual(set_user_mock.call_args_list[0].args, ("worker",))
        self.assertEqual(set_user_mock.call_args_list[-1].args, ("runner",))

    def test_process_chat_url_fetch_reaches_runtime_web_fetch_tool(self):
        session = _FakeSession()
        turns = []
        finalized = []

        def append_turn(_session_id, role, text):
            turns.append((role, text))
            return list(turns)

        def finalize_record(record, **kwargs):
            finalized.append({"record": record, **kwargs})
            return "captured.json"

        with patch.object(nova_http.nova_core, "get_active_user", return_value="runner"), \
             patch.object(nova_http.nova_core, "set_active_user"), \
             patch.object(
                 nova_http.nova_core,
                 "_llm_classify_routing_intent",
                 return_value={
                     "tool": "web_fetch",
                     "args": ["http://127.0.0.1:8080/control"],
                     "confidence": 0.94,
                     "reason": "semantic access request",
                 },
             ), \
             patch.object(nova_http.nova_core, "tool_web_fetch", return_value="FETCHED_CONTROL"), \
             patch.object(nova_http.nova_core, "build_turn_reflection", return_value={}), \
             patch.object(nova_http.nova_core, "finalize_action_ledger_record", side_effect=finalize_record), \
             patch.object(nova_http.nova_core, "behavior_record_event"):
            reply = HTTP_CHAT_RUNTIME_SERVICE.process_chat(
                "s-web-fetch",
                "can you access the following website http://127.0.0.1:8080/control",
                user_id="runner",
                core_module=nova_http.nova_core,
                session_state_manager=_SessionManager(session),
                turn_finalization_service=nova_http.HTTP_TURN_FINALIZATION_SERVICE,
                http_chat_flow_module=nova_http.http_chat_flow,
                append_session_turn_fn=append_turn,
                generate_chat_reply_fn=nova_http._generate_chat_reply,
                invalidate_control_status_cache_fn=lambda: None,
            )

        self.assertEqual(reply, "FETCHED_CONTROL")
        self.assertTrue(finalized)
        self.assertEqual(finalized[-1].get("planner_decision"), "run_tool")
        self.assertEqual(finalized[-1].get("tool"), "web_fetch")
        self.assertEqual(finalized[-1].get("tool_result"), "FETCHED_CONTROL")

    def test_process_chat_web_fetch_failure_question_stays_llm_owned(self):
        session = _FakeSession()
        turns = []
        finalized = []

        def append_turn(_session_id, role, text):
            turns.append((role, text))
            return list(turns)

        def finalize_record(record, **kwargs):
            finalized.append({"record": record, **kwargs})
            return "captured.json"

        with patch.object(nova_http.nova_core, "get_active_user", return_value="runner"), \
             patch.object(nova_http.nova_core, "set_active_user"), \
             patch.object(
                 nova_http.nova_core,
                 "_llm_classify_routing_intent",
                 return_value={"tool": "none", "args": [], "confidence": 0.91, "reason": "conversation about prior tool result"},
             ), \
             patch.object(nova_http.nova_core, "build_fallback_context_details", return_value={}), \
             patch.object(nova_http.nova_core, "ollama_chat", return_value="LLM_DIAGNOSTIC"), \
             patch.object(nova_http.nova_core, "build_turn_reflection", return_value={}), \
             patch.object(nova_http.nova_core, "finalize_action_ledger_record", side_effect=finalize_record), \
             patch.object(nova_http.nova_core, "behavior_record_event"):
            reply = HTTP_CHAT_RUNTIME_SERVICE.process_chat(
                "s-web-fetch-diagnostic",
                "why did you web_fetch tool failed ?",
                user_id="runner",
                core_module=nova_http.nova_core,
                session_state_manager=_SessionManager(session),
                turn_finalization_service=nova_http.HTTP_TURN_FINALIZATION_SERVICE,
                http_chat_flow_module=nova_http.http_chat_flow,
                append_session_turn_fn=append_turn,
                generate_chat_reply_fn=nova_http._generate_chat_reply,
                invalidate_control_status_cache_fn=lambda: None,
            )

        self.assertEqual(reply, "LLM_DIAGNOSTIC")
        self.assertTrue(finalized)
        self.assertEqual(finalized[-1].get("planner_decision"), "llm_fallback")
        self.assertEqual(finalized[-1].get("tool"), "")
