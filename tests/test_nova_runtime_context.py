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
        self.assertEqual(nova_runtime_context.RUNTIME_DIR, nova_runtime_context.BASE_DIR / "runtime")
        self.assertEqual(nova_runtime_context.MEMORY_DIR, nova_runtime_context.BASE_DIR / "memory")
        self.assertEqual(nova_runtime_context.POLICY_PATH, nova_runtime_context.BASE_DIR / "policy.json")
        self.assertEqual(
            nova_runtime_context.PROMOTED_DEFINITIONS_DIR,
            nova_runtime_context.TEST_SESSIONS_DIR / "promoted",
        )


if __name__ == "__main__":
    unittest.main()