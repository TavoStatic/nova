import unittest

from services import nova_turn_heuristics


class TestNovaTurnHeuristics(unittest.TestCase):
    def test_session_recap_reply_summarizes_recent_user_topics(self):
        reply = nova_turn_heuristics.session_recap_reply(
            [
                ("user", "What are the attendance reporting rules for PEIMS?"),
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
                ("user", "What are the attendance reporting rules for PEIMS?"),
                ("assistant", "Checking."),
                ("user", "can you do a deep search and let me know what else you dig up?"),
                ("user", "give me a recap of this entire chat session nova"),
            ],
            is_deep_search_followup_request_fn=nova_turn_heuristics.is_deep_search_followup_request,
            is_session_recap_request_fn=nova_turn_heuristics.is_session_recap_request,
        )

        self.assertIn("PEIMS attendance reporting rules Texas TEA ADA", query)

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


if __name__ == "__main__":
    unittest.main()