import unittest

from services import nova_runtime_context


class TestNovaRuntimeContext(unittest.TestCase):
    def test_active_user_round_trip(self):
        original_user = nova_runtime_context.get_active_user()
        try:
            nova_runtime_context.set_active_user("Gustavo Uribe")
            self.assertEqual(nova_runtime_context.get_active_user(), "Gustavo Uribe")

            nova_runtime_context.set_active_user(None)
            self.assertIsNone(nova_runtime_context.get_active_user())
        finally:
            nova_runtime_context.set_active_user(original_user)

    def test_runtime_paths_are_derived_from_base_dir(self):
        self.assertEqual(
            nova_runtime_context.RUNTIME_DIR,
            nova_runtime_context.resolve_runtime_dir(nova_runtime_context.BASE_DIR),
        )
        self.assertEqual(nova_runtime_context.MEMORY_DIR, nova_runtime_context.BASE_DIR / "memory")
        self.assertEqual(nova_runtime_context.POLICY_PATH, nova_runtime_context.BASE_DIR / "policy.json")
        self.assertEqual(
            nova_runtime_context.AUTONOMY_ORCHESTRATOR_LEDGER_FILE,
            nova_runtime_context.RUNTIME_DIR / "autonomy_orchestrator_ledger.jsonl",
        )
        self.assertEqual(
            nova_runtime_context.PROMOTED_DEFINITIONS_DIR,
            nova_runtime_context.TEST_SESSIONS_DIR / "promoted",
        )

    def test_runtime_scope_resolves_live_and_validation_roots(self):
        base_dir = nova_runtime_context.BASE_DIR

        live = nova_runtime_context.resolve_runtime_dir(
            base_dir,
            environ={},
            argv=["nova_core.py"],
        )
        validation = nova_runtime_context.resolve_runtime_dir(
            base_dir,
            environ={"NOVA_TEST_RUNNER": "1"},
            argv=["nova_core.py"],
        )
        direct_unittest = nova_runtime_context.resolve_runtime_dir(
            base_dir,
            environ={},
            argv=["python", "-m", "unittest", "tests.test_smoke_placeholder"],
        )

        self.assertEqual(live, base_dir / "runtime")
        self.assertEqual(validation, base_dir / "runtime" / "validation")
        self.assertEqual(direct_unittest, base_dir / "runtime" / "validation")
        self.assertNotEqual(validation / "test_sessions", live / "test_sessions")

    def test_validation_runtime_override_is_honored(self):
        base_dir = nova_runtime_context.BASE_DIR

        runtime_dir = nova_runtime_context.resolve_runtime_dir(
            base_dir,
            environ={"NOVA_TEST_RUNNER": "1", "NOVA_VALIDATION_RUNTIME_DIR": "runtime/custom_validation"},
            argv=["nova_core.py"],
        )

        self.assertEqual(runtime_dir, base_dir / "runtime" / "custom_validation")


if __name__ == "__main__":
    unittest.main()
