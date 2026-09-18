from __future__ import annotations

import unittest
from unittest import mock

import nova_core


class TestNovaCoreIdentityContext(unittest.TestCase):
    def test_learning_context_includes_confirmed_identity_when_memory_and_kb_are_empty(self):
        with mock.patch.object(
            nova_core,
            "load_identity_profile",
            return_value={"bootstrap": {"origin_authority": "operator_confirmed", "origin_status": "ready"}},
        ), mock.patch.object(
            nova_core,
            "load_learned_facts",
            return_value={
                "assistant_name": "Nova",
                "developer_name": "Gustavo Uribe",
                "developer_nickname": "Gus",
            },
        ), mock.patch.object(nova_core, "kb_search", return_value=""), mock.patch.object(
            nova_core, "mem_recall", return_value=""
        ):
            details = nova_core.build_learning_context_details("session turn")

        context = str(details.get("context") or "")
        self.assertTrue(details.get("identity_used"))
        self.assertGreater(details.get("identity_chars") or 0, 0)
        self.assertIn("Confirmed Nova identity evidence", context)
        self.assertIn("assistant_name=Nova", context)
        self.assertIn("developer_name=Gustavo Uribe", context)

    def test_learning_context_includes_operational_self_evidence_from_capability_registry(self):
        capabilities = {
            "runtime_core": "Nova runs as a local runtime with core state and heartbeat",
            "guard_system": "Nova has a guard process and maintenance loop",
            "work_tree": "Nova can organize internal work into trees and tasks",
            "autonomy_handling": "Nova has autonomy advisory and execution-gate machinery",
        }
        with mock.patch.object(nova_core, "load_identity_profile", return_value={}), mock.patch.object(
            nova_core, "load_learned_facts", return_value={}
        ), mock.patch.object(nova_core, "load_capabilities", return_value=capabilities), mock.patch.object(
            nova_core, "kb_search", return_value=""
        ), mock.patch.object(nova_core, "mem_recall", return_value=""):
            details = nova_core.build_learning_context_details("session turn")

        context = str(details.get("context") or "")
        self.assertTrue(details.get("operational_identity_used"))
        self.assertGreater(details.get("operational_identity_chars") or 0, 0)
        self.assertIn("Operational Nova self evidence", context)
        self.assertIn("Registered internal surfaces observed from the capability registry", context)
        self.assertNotIn("conversation is one interface", context)
        self.assertNotIn("Operational identity statement", context)
        self.assertIn("runtime_core", context)
        self.assertIn("work_tree", context)
        self.assertIn("autonomy_handling", context)

    def test_fallback_context_orders_conversation_before_answer_evidence(self):
        with mock.patch.object(
            nova_core,
            "load_identity_profile",
            return_value={"bootstrap": {"origin_authority": "operator_confirmed", "origin_status": "ready"}},
        ), mock.patch.object(
            nova_core,
            "load_learned_facts",
            return_value={"assistant_name": "Nova"},
        ), mock.patch.object(
            nova_core,
            "load_capabilities",
            return_value={"work_tree": "Nova can organize internal work into trees and tasks"},
        ), mock.patch.object(nova_core, "kb_search", return_value=""), mock.patch.object(
            nova_core, "mem_recall", return_value=""
        ):
            details = nova_core.build_fallback_context_details(
                "what are you?",
                [("user", "hi nova"), ("assistant", "Hello.")],
            )

        context = str(details.get("context") or "")
        self.assertLess(context.index("CURRENT CHAT CONTEXT"), context.index("Confirmed Nova identity evidence"))
        self.assertLess(context.index("CURRENT CHAT CONTEXT"), context.index("Operational Nova self evidence"))

    def test_learning_context_blocks_durable_recall_for_non_memory_queries(self):
        recall_calls: list[str] = []

        def _track_recall(query, **kwargs):
            recall_calls.append(str(query))
            return ""

        with mock.patch.object(nova_core, "load_identity_profile", return_value={}), mock.patch.object(
            nova_core, "load_learned_facts", return_value={}
        ), mock.patch.object(nova_core, "load_capabilities", return_value={}), mock.patch.object(
            nova_core, "kb_search", return_value=""
        ), mock.patch.object(nova_core, "mem_recall", side_effect=_track_recall), mock.patch.object(
            nova_core, "mem_get_recent_learned", return_value=["Correction: sky blue"]
        ) as recent_mock:
            details = nova_core.build_learning_context_details("tell me a joke about weather")

        self.assertFalse(details.get("memory_used"))
        self.assertEqual(recall_calls, [])
        recent_mock.assert_not_called()

    def test_learning_context_uses_recent_learned_summary_for_learning_queries(self):
        with mock.patch.object(nova_core, "load_identity_profile", return_value={}), mock.patch.object(
            nova_core, "load_learned_facts", return_value={}
        ), mock.patch.object(nova_core, "load_capabilities", return_value={}), mock.patch.object(
            nova_core, "kb_search", return_value=""
        ), mock.patch.object(nova_core, "mem_recall", return_value="SHOULD_NOT_USE_RECALL") as recall_mock, mock.patch.object(
            nova_core, "mem_get_recent_learned", return_value=["Correction: sky blue"]
        ) as recent_mock:
            details = nova_core.build_learning_context_details("what have you learned from me")

        recall_mock.assert_not_called()
        recent_mock.assert_called_once()
        context = str(details.get("context") or "")
        self.assertTrue(details.get("memory_used"))
        self.assertIn("Recent learning:", context)
        self.assertIn("Correction: sky blue", context)

    def test_fallback_context_keeps_current_turn_out_of_prior_transcript(self):
        details = nova_core.build_fallback_context_details(
            "current turn",
            [
                ("user", "older turn"),
                ("assistant", "prior answer"),
                ("user", "current turn"),
            ],
        )

        context = str(details.get("context") or "")
        self.assertIn("CURRENT CHAT CONTEXT", context)
        self.assertIn("Assistant: prior answer", context)
        self.assertNotIn("User: current turn", context)

    def test_estimate_spanish_ratio_accented_characters(self):
        self.assertEqual(nova_core._estimate_spanish_ratio("Hello world"), 0.0)
        self.assertGreater(nova_core._estimate_spanish_ratio("Como estás"), 0.0)
        self.assertEqual(nova_core._estimate_spanish_ratio("¿Cómo estás?"), 1.0)


if __name__ == "__main__":
    unittest.main()
