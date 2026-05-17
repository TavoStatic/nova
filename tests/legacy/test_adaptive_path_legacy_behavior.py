import unittest

from services import nova_planner_contract


class TestAdaptivePathLegacyBehavior(unittest.TestCase):
    def test_legacy_exact_work_tree_wait_reply_text(self):
        reply = nova_planner_contract._format_work_tree_reply({
            "action": "wait_for_tools",
            "missing_tools": ["web_fetch"],
        })

        self.assertEqual(reply, "The next work tree branch is waiting for tools: web_fetch.")
