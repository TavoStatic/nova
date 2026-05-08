import unittest

from services import nova_followup_dispatch


class TestNovaFollowupDispatch(unittest.TestCase):
    def test_runtime_scope_dispatches_queue_status_reason_reply(self):
        runtime_scope = {
            "TURN_SUPERVISOR": type(
                "SupervisorStub",
                (),
                {"evaluate_rules": staticmethod(lambda *_args, **_kwargs: {})},
            )(),
            "_execute_registered_supervisor_rule": lambda *_args, **_kwargs: (False, "", None),
            "_is_retrieval_meta_question": lambda text: False,
            "_retrieval_meta_reply": lambda state: "",
            "_looks_like_retrieval_followup": lambda text: False,
            "_retrieval_followup_reply": lambda state, text: ("", state),
            "_is_queue_status_reason_followup": lambda text: True,
            "_queue_status_reason_reply": lambda state: "Because the worker is paused.",
            "_is_queue_status_report_followup": lambda text: False,
            "_queue_status_report_reply": lambda state: "",
            "_is_queue_status_seam_followup": lambda text: False,
            "_queue_status_seam_reply": lambda state: "",
            "_is_weather_meta_followup": lambda text: False,
            "_weather_meta_reply": lambda state: "",
            "_is_weather_status_followup": lambda text: False,
            "_weather_status_reply": lambda state: "",
            "_normalize_turn_text": lambda text: text.lower(),
            "_numeric_reference_guess_reply": lambda value: "",
            "_numeric_reference_binding_reply": lambda value, referent: "",
            "_make_conversation_state": lambda kind, **data: {"kind": kind, **data},
            "_extract_work_role_parts": lambda text: [],
            "_store_developer_role_facts": lambda roles, input_source="typed": (False, ""),
            "_strip_confirmation_prefix": lambda text: text,
            "_looks_like_profile_followup": lambda text: False,
            "_developer_identity_followup_reply": lambda **kwargs: "",
            "_non_retrieval_resource_meta_reply": lambda: "",
            "_is_developer_location_request": lambda *_args, **_kwargs: False,
            "_developer_location_reply": lambda: "",
            "_identity_name_followup_reply": lambda subject: "",
            "_identity_profile_followup_reply": lambda subject, turns=None: "",
        }

        handled, msg, next_state = nova_followup_dispatch.consume_conversation_followup_from_runtime(
            {"kind": "queue_status"},
            "why is the queue blocked?",
            runtime_scope=runtime_scope,
        )

        self.assertTrue(handled)
        self.assertEqual(msg, "Because the worker is paused.")
        self.assertEqual(next_state, {"kind": "queue_status"})

    def test_missing_retrieval_context_returns_clarifying_reply(self):
        handled, msg, next_state = nova_followup_dispatch.consume_conversation_followup(
            None,
            "tell me about the first one",
            evaluate_rules_fn=lambda *_args, **_kwargs: {},
            execute_registered_supervisor_rule_fn=lambda *_args, **_kwargs: (False, "", None),
            is_retrieval_meta_question_fn=lambda text: False,
            retrieval_meta_reply_fn=lambda state: "",
            looks_like_retrieval_followup_fn=lambda text: True,
            retrieval_followup_reply_fn=lambda state, text: ("", state),
            is_queue_status_reason_followup_fn=lambda text: False,
            queue_status_reason_reply_fn=lambda state: "",
            is_queue_status_report_followup_fn=lambda text: False,
            queue_status_report_reply_fn=lambda state: "",
            is_queue_status_seam_followup_fn=lambda text: False,
            queue_status_seam_reply_fn=lambda state: "",
            is_weather_meta_followup_fn=lambda text: False,
            weather_meta_reply_fn=lambda state: "",
            is_weather_status_followup_fn=lambda text: False,
            weather_status_reply_fn=lambda state: "",
            normalize_turn_text_fn=lambda text: text.lower(),
            numeric_reference_guess_reply_fn=lambda value: "",
            numeric_reference_binding_reply_fn=lambda value, referent: "",
            make_conversation_state_fn=lambda kind, **data: {"kind": kind, **data},
            extract_work_role_parts_fn=lambda text: [],
            store_developer_role_facts_fn=lambda roles, input_source="typed": (False, ""),
            strip_confirmation_prefix_fn=lambda text: text,
            looks_like_profile_followup_fn=lambda text: False,
            developer_identity_followup_reply_fn=lambda **kwargs: "",
            non_retrieval_resource_meta_reply_fn=lambda: "",
            is_developer_location_request_fn=lambda *_args, **_kwargs: False,
            developer_location_reply_fn=lambda: "",
            identity_name_followup_reply_fn=lambda subject: "",
            identity_profile_followup_reply_fn=lambda subject, turns=None: "",
        )

        self.assertTrue(handled)
        self.assertIn("active retrieval context", msg)
        self.assertIsNone(next_state)

    def test_queue_status_followup_dispatches_reason_reply(self):
        handled, msg, next_state = nova_followup_dispatch.consume_conversation_followup(
            {"kind": "queue_status"},
            "why is the queue blocked?",
            evaluate_rules_fn=lambda *_args, **_kwargs: {},
            execute_registered_supervisor_rule_fn=lambda *_args, **_kwargs: (False, "", None),
            is_retrieval_meta_question_fn=lambda text: False,
            retrieval_meta_reply_fn=lambda state: "",
            looks_like_retrieval_followup_fn=lambda text: False,
            retrieval_followup_reply_fn=lambda state, text: ("", state),
            is_queue_status_reason_followup_fn=lambda text: True,
            queue_status_reason_reply_fn=lambda state: "Because the worker is paused.",
            is_queue_status_report_followup_fn=lambda text: False,
            queue_status_report_reply_fn=lambda state: "",
            is_queue_status_seam_followup_fn=lambda text: False,
            queue_status_seam_reply_fn=lambda state: "",
            is_weather_meta_followup_fn=lambda text: False,
            weather_meta_reply_fn=lambda state: "",
            is_weather_status_followup_fn=lambda text: False,
            weather_status_reply_fn=lambda state: "",
            normalize_turn_text_fn=lambda text: text.lower(),
            numeric_reference_guess_reply_fn=lambda value: "",
            numeric_reference_binding_reply_fn=lambda value, referent: "",
            make_conversation_state_fn=lambda kind, **data: {"kind": kind, **data},
            extract_work_role_parts_fn=lambda text: [],
            store_developer_role_facts_fn=lambda roles, input_source="typed": (False, ""),
            strip_confirmation_prefix_fn=lambda text: text,
            looks_like_profile_followup_fn=lambda text: False,
            developer_identity_followup_reply_fn=lambda **kwargs: "",
            non_retrieval_resource_meta_reply_fn=lambda: "",
            is_developer_location_request_fn=lambda *_args, **_kwargs: False,
            developer_location_reply_fn=lambda: "",
            identity_name_followup_reply_fn=lambda subject: "",
            identity_profile_followup_reply_fn=lambda subject, turns=None: "",
        )

        self.assertTrue(handled)
        self.assertEqual(msg, "Because the worker is paused.")
        self.assertEqual(next_state, {"kind": "queue_status"})


if __name__ == "__main__":
    unittest.main()
