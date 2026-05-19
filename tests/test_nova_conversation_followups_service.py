import unittest

from services import nova_conversation_followups


class TestNovaConversationFollowupsService(unittest.TestCase):
    def test_make_conversation_state_and_active_subject(self):
        state = nova_conversation_followups.make_conversation_state("retrieval", subject="web_research", query="PEIMS")
        self.assertEqual(state["kind"], "retrieval")
        self.assertEqual(state["subject"], "web_research")
        self.assertEqual(
            nova_conversation_followups.conversation_active_subject(state),
            "retrieval:web_research",
        )

    def test_normalize_turn_text_repairs_known_typos(self):
        self.assertEqual(
            nova_conversation_followups.normalize_turn_text("retreiving data"),
            "retrieving data",
        )

    def test_looks_like_contextual_followup_uses_prior_reference_for_short_turn(self):
        self.assertTrue(
            nova_conversation_followups.looks_like_contextual_followup(
                "the first one",
                normalize_turn_text_fn=lambda text: text.lower().strip(),
                uses_prior_reference_fn=lambda text: text == "the first one",
            )
        )

    def test_retrieval_meta_reply_lists_hosts(self):
        reply = nova_conversation_followups.retrieval_meta_reply(
            {
                "query": "PEIMS attendance",
                "urls": [
                    "https://tea.texas.gov/a",
                    "https://example.com/b",
                ],
            }
        )
        low = reply.lower()
        self.assertIn("peims attendance", low)
        self.assertIn("tea.texas.gov", low)
        self.assertIn("example.com", low)

    def test_looks_like_retrieval_followup_accepts_next_source(self):
        self.assertTrue(
            nova_conversation_followups.looks_like_retrieval_followup(
                "next source",
                normalize_turn_text_fn=lambda text: text.lower().strip(),
                extract_retrieval_result_index_fn=lambda text: None,
            )
        )

    def test_looks_like_location_recall_followup_uses_recent_location_reply_context(self):
        self.assertTrue(
            nova_conversation_followups.looks_like_location_recall_followup(
                [("assistant", "Your saved location is Brownsville.")],
                "what did you find?",
                looks_like_contextual_continuation_fn=lambda text: True,
            )
        )

    def test_make_retrieval_and_tool_conversation_state(self):
        retrieval_state = nova_conversation_followups.make_retrieval_conversation_state(
            "web_research",
            "",
            "1) https://example.com/a",
            extract_urls_fn=lambda text: ["https://example.com/a"],
            make_conversation_state_fn=nova_conversation_followups.make_conversation_state,
            web_research_has_results_fn=lambda: True,
            web_research_result_count_fn=lambda: 3,
            web_research_query_fn=lambda: "PEIMS attendance",
        )
        self.assertEqual(retrieval_state["kind"], "retrieval")
        self.assertEqual(retrieval_state["result_count"], 3)
        self.assertEqual(retrieval_state["query"], "PEIMS attendance")

        tool_state = nova_conversation_followups.make_tool_conversation_state(
            "queue_status",
            "",
            "queue ready",
            make_retrieval_conversation_state_fn=lambda tool, query, output: None,
            make_queue_status_conversation_state_fn=lambda output: {"kind": "queue_status", "subject": "generated_work_queue"},
        )
        self.assertEqual(tool_state, {"kind": "queue_status", "subject": "generated_work_queue"})

    def test_make_tool_conversation_state_records_self_status_evidence(self):
        state = nova_conversation_followups.make_tool_conversation_state(
            "self_status",
            "what is troubling you today",
            "Work Tree is blocked_observing with 2 open task(s).",
            make_retrieval_conversation_state_fn=lambda tool, query, output: None,
            make_queue_status_conversation_state_fn=lambda output: None,
        )

        self.assertEqual(state["kind"], "self_status")
        self.assertEqual(state["subject"], "runtime")
        self.assertIn("blocked_observing", state["tool_result"])

    def test_make_tool_conversation_state_records_verified_self_evidence(self):
        identity_state = nova_conversation_followups.make_tool_conversation_state(
            "runtime_identity",
            "who are you",
            "I am Nova, a local AI runtime.",
            make_retrieval_conversation_state_fn=lambda tool, query, output: None,
            make_queue_status_conversation_state_fn=lambda output: None,
        )
        capability_state = nova_conversation_followups.make_tool_conversation_state(
            "capability_inventory",
            "what can you do",
            "Current capabilities:\n- runtime_core",
            make_retrieval_conversation_state_fn=lambda tool, query, output: None,
            make_queue_status_conversation_state_fn=lambda output: None,
        )

        self.assertEqual(identity_state["kind"], "runtime_identity")
        self.assertEqual(identity_state["subject"], "runtime")
        self.assertIn("local AI runtime", identity_state["tool_result"])
        self.assertEqual(capability_state["kind"], "capability_inventory")
        self.assertEqual(capability_state["subject"], "runtime")
        self.assertIn("runtime_core", capability_state["tool_result"])

    def test_make_tool_conversation_state_records_system_check_evidence(self):
        state = nova_conversation_followups.make_tool_conversation_state(
            "system_check",
            "can you prove that from your internals?",
            "System check: OK",
            make_retrieval_conversation_state_fn=lambda tool, query, output: None,
            make_queue_status_conversation_state_fn=lambda output: None,
        )

        self.assertEqual(state["kind"], "system_check")
        self.assertEqual(state["subject"], "runtime")
        self.assertIn("System check", state["tool_result"])

    def test_make_tool_conversation_state_records_operator_help_evidence(self):
        state = nova_conversation_followups.make_tool_conversation_state(
            "operator_help",
            "neutral user turn",
            "Today I am mainly stuck on: Work Tree needs operator context.",
            make_retrieval_conversation_state_fn=lambda tool, query, output: None,
            make_queue_status_conversation_state_fn=lambda output: None,
        )

        self.assertEqual(state["kind"], "operator_help")
        self.assertEqual(state["subject"], "runtime")
        self.assertIn("operator context", state["tool_result"])

    def test_retrieval_query_requires_explicit_web_search_command(self):
        query = nova_conversation_followups.retrieval_query_from_text(
            "web_search",
            "web search peims attendance rules",
            web_research_query_fn=lambda: "",
        )
        self.assertEqual(query, "peims attendance rules")

        self.assertEqual(
            nova_conversation_followups.retrieval_query_from_text(
                "web_search",
                "search peims attendance rules",
                web_research_query_fn=lambda: "",
            ),
            "search peims attendance rules",
        )

    def test_retrieval_query_requires_url_for_web_fetch_command(self):
        self.assertEqual(
            nova_conversation_followups.retrieval_query_from_text(
                "web_fetch",
                "web https://example.com/report",
                web_research_query_fn=lambda: "",
            ),
            "https://example.com/report",
        )
        self.assertEqual(
            nova_conversation_followups.retrieval_query_from_text(
                "web_fetch",
                "web peims attendance rules",
                web_research_query_fn=lambda: "",
            ),
            "web peims attendance rules",
        )

    def test_llm_fallback_does_not_infer_hidden_state_from_chat_content(self):
        state = nova_conversation_followups.infer_post_reply_conversation_state(
            "what else do you know about me?",
            planner_decision="llm_fallback",
            turns=[("user", "what else do you know about me?")],
            fallback_state={"kind": "retrieval", "subject": "web_search"},
            make_tool_conversation_state_fn=lambda tool, query, output: {"kind": "tool"},
            infer_profile_conversation_state_fn=lambda text: {"kind": "identity_profile", "subject": "developer"},
            is_location_recall_query_fn=lambda text: True,
            looks_like_location_recall_followup_fn=lambda turns, text: True,
            make_conversation_state_fn=nova_conversation_followups.make_conversation_state,
        )

        self.assertEqual(state, {"kind": "retrieval", "subject": "web_search"})


if __name__ == "__main__":
    unittest.main()
