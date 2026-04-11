import unittest

from services.nova_cli_delivery import apply_cli_handled_outcome
from services.nova_cli_delivery import apply_cli_outcome_to_ledger
from services.nova_cli_delivery import emit_cli_reply_outcome


class TestNovaCliDelivery(unittest.TestCase):
    def test_apply_cli_handled_outcome_clears_pending_and_delivers_reply(self):
        ledger = {}
        session_turns = []
        printed = []
        spoken = []
        done = []
        cleared = []
        synced = []

        out = apply_cli_handled_outcome(
            pending_action_ledger=ledger,
            outcome={
                "planner_decision": "llm_fallback",
                "grounded": False,
                "reply": "I need a weather source first.",
                "clear_pending_action": True,
            },
            default_planner_decision="llm_fallback",
            session_turns=session_turns,
            print_fn=lambda text, flush=True: printed.append((text, flush)),
            speak_chunked_fn=lambda text: spoken.append(text),
            say_done_fn=lambda text: done.append(text),
            coerce_grounded=True,
            clear_pending_action_fn=lambda: cleared.append(True),
            sync_pending_conversation_tracking_fn=lambda: synced.append(True),
        )

        self.assertEqual(ledger, {"planner_decision": "llm_fallback", "grounded": False})
        self.assertEqual(session_turns, [("assistant", "I need a weather source first.")])
        self.assertEqual(printed[0][0], "Nova: I need a weather source first.\n")
        self.assertEqual(spoken, ["I need a weather source first."])
        self.assertEqual(done, [])
        self.assertEqual(cleared, [True])
        self.assertEqual(synced, [True])
        self.assertEqual(out.get("spoken_mode"), "assistant_reply")

    def test_apply_cli_outcome_to_ledger_updates_basic_block_fields(self):
        ledger = {}

        apply_cli_outcome_to_ledger(
            pending_action_ledger=ledger,
            outcome={"planner_decision": "policy_block", "grounded": True},
            default_planner_decision="policy_block",
            coerce_grounded=True,
        )

        self.assertEqual(ledger, {"planner_decision": "policy_block", "grounded": True})

    def test_apply_cli_outcome_to_ledger_updates_reply_fields_without_forcing_none_grounded(self):
        ledger = {"grounded": True}

        apply_cli_outcome_to_ledger(
            pending_action_ledger=ledger,
            outcome={
                "planner_decision": "llm_fallback",
                "grounded": None,
                "reply_contract": "",
                "reply_outcome": {"kind": "none"},
            },
            default_planner_decision="llm_fallback",
            update_reply_fields=True,
        )

        self.assertEqual(ledger.get("planner_decision"), "llm_fallback")
        self.assertTrue(ledger.get("grounded"))
        self.assertEqual(ledger.get("reply_contract"), "")
        self.assertEqual(ledger.get("reply_outcome"), {"kind": "none"})

    def test_emit_cli_reply_outcome_speaks_standard_reply(self):
        session_turns = []
        printed = []
        spoken = []
        done = []

        out = emit_cli_reply_outcome(
            reply_text="Blocked by policy.",
            planner_decision="policy_block",
            session_turns=session_turns,
            print_fn=lambda text, flush=True: printed.append((text, flush)),
            speak_chunked_fn=lambda text: spoken.append(text),
            say_done_fn=lambda text: done.append(text),
        )

        self.assertEqual(out.get("spoken_mode"), "assistant_reply")
        self.assertEqual(session_turns, [("assistant", "Blocked by policy.")])
        self.assertEqual(spoken, ["Blocked by policy."])
        self.assertEqual(done, [])
        self.assertEqual(printed[0][0], "Nova: Blocked by policy.\n")

    def test_emit_cli_reply_outcome_announces_tool_output(self):
        session_turns = []
        printed = []
        spoken = []
        done = []

        out = emit_cli_reply_outcome(
            reply_text="Standing work queue:\n- open: 2 of 4",
            planner_decision="run_tool",
            session_turns=session_turns,
            print_fn=lambda text, flush=True: printed.append((text, flush)),
            speak_chunked_fn=lambda text: spoken.append(text),
            say_done_fn=lambda text: done.append(text),
        )

        self.assertEqual(out.get("spoken_mode"), "tool_done")
        self.assertEqual(session_turns, [("assistant", "Standing work queue:\n- open: 2 of 4")])
        self.assertEqual(spoken, [])
        self.assertEqual(done, ["Done."])
        self.assertEqual(printed[0][0], "Nova (tool output):\nStanding work queue:\n- open: 2 of 4\n")


if __name__ == "__main__":
    unittest.main()