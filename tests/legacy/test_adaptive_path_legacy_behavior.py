import unittest

import http_chat_flow
from services import nova_planner_contract


class TestAdaptivePathLegacyBehavior(unittest.TestCase):
    def test_legacy_exact_open_probe_reply_text(self):
        out = http_chat_flow.apply_supervisor_bypass_safe_fallback(
            warn_supervisor_bypass=True,
            reply_contract="",
            routed_text="tell me anything",
            turns=[("user", "tell me anything")],
            routing_decision={"final_owner": "planner"},
            ledger={},
            open_probe_reply=lambda text, turns=None: (f"safe:{text}", "safe_fallback"),
            action_ledger_add_step=lambda *a, **k: None,
        )

        self.assertEqual(out.get("reply"), "safe:tell me anything")

    def test_legacy_exact_work_tree_wait_reply_text(self):
        reply = nova_planner_contract._format_work_tree_reply({
            "action": "wait_for_tools",
            "missing_tools": ["web_fetch"],
        })

        self.assertEqual(reply, "The next work tree branch is waiting for tools: web_fetch.")
