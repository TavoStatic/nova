import unittest

from services import nova_turn_heuristics


class TestNovaTurnHeuristics(unittest.TestCase):
    @staticmethod
    def _last_assistant(turns):
        for role, text in reversed(list(turns or [])):
            if role == "assistant":
                return text
        return ""

    def test_session_recap_reply_summarizes_recent_user_topics(self):
        reply = nova_turn_heuristics.session_recap_reply(
            [
                ("user", "What are the attendance reporting rules for student_data?"),
                ("assistant", "Let me check."),
                ("user", "can you do a deep search and let me know what else you dig up?"),
            ],
            "give me a recap of this entire chat session nova",
            is_session_recap_request_fn=nova_turn_heuristics.is_session_recap_request,
        )

        self.assertIn("Recap of this session so far:", reply)
        self.assertIn("attendance reporting rules", reply.lower())
        self.assertIn("deep search", reply.lower())

    def test_infer_research_query_from_turns_skips_recap_and_followup(self):
        query = nova_turn_heuristics.infer_research_query_from_turns(
            [
                ("user", "What are the attendance reporting rules for student_data?"),
                ("assistant", "Checking."),
                ("user", "can you do a deep search and let me know what else you dig up?"),
                ("user", "give me a recap of this entire chat session nova"),
            ],
            is_deep_search_followup_request_fn=nova_turn_heuristics.is_deep_search_followup_request,
            is_session_recap_request_fn=nova_turn_heuristics.is_session_recap_request,
        )

        self.assertIn("student_data attendance reporting rules Texas TEA ADA", query)

    def test_build_greeting_reply_ignores_default_local_user(self):
        reply = nova_turn_heuristics.build_greeting_reply(
            "hi nova",
            active_user="guribe",
            default_local_user_id_fn=lambda: "guribe",
        )

        self.assertEqual(reply, "Hello.")

    def test_build_greeting_reply_ignores_synthetic_runner_user(self):
        reply = nova_turn_heuristics.build_greeting_reply(
            "hi nova",
            active_user="runner",
            default_local_user_id_fn=lambda: "guribe",
        )

        self.assertEqual(reply, "Hello.")

    def test_classify_turn_acts_marks_mixed_request(self):
        text = "the weather looks good. can you check the rest of the forecast"
        acts = nova_turn_heuristics.classify_turn_acts(
            text,
            turns=None,
            active_subject="",
            pending_action=None,
            split_turn_clauses_fn=nova_turn_heuristics.split_turn_clauses,
            is_explicit_command_like_fn=lambda raw: False,
            looks_like_correction_turn_fn=lambda raw: False,
            is_explicit_request_fn=nova_turn_heuristics.is_explicit_request,
            is_statement_like_clause_fn=lambda raw: nova_turn_heuristics.is_statement_like_clause(
                raw,
                is_explicit_request_fn=nova_turn_heuristics.is_explicit_request,
                is_explicit_command_like_fn=lambda value: False,
                is_declarative_info_fn=nova_turn_heuristics.is_declarative_info,
            ),
            looks_like_continue_thread_turn_fn=lambda *_args, **_kwargs: False,
        )

        self.assertIn("inform", acts)
        self.assertIn("ask", acts)
        self.assertIn("mixed", acts)

    def test_classify_turn_acts_marks_answer_to_assistant_prompt(self):
        turns = [
            ("user", "hi nova"),
            ("assistant", "What brings you here today?"),
            ("user", "give you an update on the progress we are having creating you"),
        ]
        acts = nova_turn_heuristics.classify_turn_acts(
            turns[-1][1],
            turns=turns,
            active_subject="",
            pending_action=None,
            split_turn_clauses_fn=nova_turn_heuristics.split_turn_clauses,
            is_explicit_command_like_fn=lambda raw: False,
            looks_like_correction_turn_fn=lambda raw: False,
            is_explicit_request_fn=nova_turn_heuristics.is_explicit_request,
            is_statement_like_clause_fn=lambda raw: nova_turn_heuristics.is_statement_like_clause(
                raw,
                is_explicit_request_fn=nova_turn_heuristics.is_explicit_request,
                is_explicit_command_like_fn=lambda value: False,
                is_declarative_info_fn=nova_turn_heuristics.is_declarative_info,
            ),
            looks_like_continue_thread_turn_fn=lambda *_args, **_kwargs: False,
            looks_like_answer_to_assistant_prompt_turn_fn=lambda raw, **kwargs: nova_turn_heuristics.looks_like_answer_to_assistant_prompt_turn(
                raw,
                last_assistant_turn_text_fn=self._last_assistant,
                **kwargs,
            ),
        )

        self.assertEqual(acts, ["answer_to_prompt"])

    def test_answer_to_assistant_prompt_does_not_claim_pending_action_response(self):
        turns = [
            ("assistant", "What location should I use for the weather lookup?"),
            ("user", "Brownsville"),
        ]

        self.assertFalse(
            nova_turn_heuristics.looks_like_answer_to_assistant_prompt_turn(
                "Brownsville",
                turns=turns,
                pending_action={"kind": "weather_lookup"},
                last_assistant_turn_text_fn=self._last_assistant,
            )
        )

    def test_classify_turn_acts_does_not_mark_correction_as_answer_to_prompt(self):
        turns = [
            ("user", "what is tsds?"),
            ("assistant", "I am not sure. What would you like me to check?"),
            ("user", "no, that's wrong"),
        ]
        acts = nova_turn_heuristics.classify_turn_acts(
            turns[-1][1],
            turns=turns,
            active_subject="",
            pending_action=None,
            split_turn_clauses_fn=nova_turn_heuristics.split_turn_clauses,
            is_explicit_command_like_fn=lambda raw: False,
            looks_like_correction_turn_fn=lambda raw: nova_turn_heuristics.looks_like_correction_turn(
                raw,
                is_negative_feedback_fn=lambda value: "wrong" in value.lower(),
                parse_correction_fn=lambda value: None,
            ),
            is_explicit_request_fn=nova_turn_heuristics.is_explicit_request,
            is_statement_like_clause_fn=lambda raw: nova_turn_heuristics.is_statement_like_clause(
                raw,
                is_explicit_request_fn=nova_turn_heuristics.is_explicit_request,
                is_explicit_command_like_fn=lambda value: False,
                is_declarative_info_fn=nova_turn_heuristics.is_declarative_info,
            ),
            looks_like_continue_thread_turn_fn=lambda *_args, **_kwargs: False,
            looks_like_answer_to_assistant_prompt_turn_fn=lambda raw, **kwargs: nova_turn_heuristics.looks_like_answer_to_assistant_prompt_turn(
                raw,
                last_assistant_turn_text_fn=self._last_assistant,
                **kwargs,
            ),
        )

        self.assertNotIn("answer_to_prompt", acts)


if __name__ == "__main__":
    unittest.main()

