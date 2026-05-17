from __future__ import annotations

import ast
import unittest
from pathlib import Path


NOVA_CORE_PATH = Path(r"C:\Nova\nova_core.py")
MAX_NOVA_CORE_LINES = 8000
EXPECTED_SERVICE_DELEGATES = {
    "_execute_registered_supervisor_rule": "service_execute_registered_supervisor_rule_from_runtime",
    "_handle_supervisor_intent": "service_handle_supervisor_intent_from_runtime",
    "_consume_conversation_followup": "service_consume_conversation_followup_from_runtime",
    "start_action_ledger_record": "service_start_action_ledger_record",
    "finalize_action_ledger_record": "service_finalize_action_ledger_record_from_runtime",
    "_record_memory_event": "service_record_memory_event",
    "execute_planned_action": "service_execute_planned_action_from_runtime",
    "web_search": "service_web_search",
    "tool_search": "service_tool_search",
    "patch_preview": "service_patch_preview",
    "hard_answer": "service_hard_answer",
    "ollama_chat": "service_ollama_chat",
    "tool_web_search": "service_tool_web_search",
    "tool_web_research": "service_tool_web_research",
    "handle_commands": "service_handle_commands",
}


class TestNovaCoreGuardrails(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._source = NOVA_CORE_PATH.read_text(encoding="utf-8")
        cls._module = ast.parse(cls._source)
        cls._functions = {
            node.name: node
            for node in cls._module.body
            if isinstance(node, ast.FunctionDef)
        }

    def test_nova_core_line_count_stays_below_guardrail(self):
        line_count = len(self._source.splitlines())
        self.assertLessEqual(
            line_count,
            MAX_NOVA_CORE_LINES,
            f"nova_core.py drifted to {line_count} lines; guardrail is {MAX_NOVA_CORE_LINES}",
        )

    def test_service_owned_wrappers_remain_single_return_delegates(self):
        for function_name, target_name in EXPECTED_SERVICE_DELEGATES.items():
            with self.subTest(function_name=function_name):
                node = self._functions.get(function_name)
                self.assertIsNotNone(node, f"{function_name} is missing from nova_core.py")
                self.assertEqual(len(node.body), 1, f"{function_name} should stay as a thin wrapper")
                self.assertIsInstance(node.body[0], ast.Return, f"{function_name} should stay as a thin wrapper")
                call = node.body[0].value
                self.assertIsInstance(call, ast.Call, f"{function_name} should directly call its service owner")
                self.assertIsInstance(call.func, ast.Name, f"{function_name} should directly call its service owner")
                self.assertEqual(call.func.id, target_name)


if __name__ == "__main__":
    unittest.main()
