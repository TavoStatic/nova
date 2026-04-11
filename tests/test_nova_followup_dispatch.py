import unittest

from services import nova_followup_dispatch


class TestNovaFollowupDispatch(unittest.TestCase):
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
            handle_location_conversation_turn_fn=lambda *_args, **_kwargs: (False, "", None, ""),
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