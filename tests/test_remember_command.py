import unittest

import nova_core


class TestRememberCommand(unittest.TestCase):
    def setUp(self):
        self.orig_mem_enabled = nova_core.mem_enabled
        self.orig_mem_add = nova_core.mem_add

    def tearDown(self):
        nova_core.mem_enabled = self.orig_mem_enabled
        nova_core.mem_add = self.orig_mem_add

    def test_remember_command_pins_fact(self):
        calls = []

        nova_core.mem_enabled = lambda: True
        nova_core.mem_add = lambda kind, source, text: calls.append((kind, source, text))

        out = nova_core.handle_commands("remember: server room code is 4821")
        self.assertIn("Pinned memory saved", out)
        self.assertEqual(calls, [("fact", "pinned", "server room code is 4821")])

    def test_remember_command_requires_content(self):
        nova_core.mem_enabled = lambda: True
        out = nova_core.handle_commands("remember:")
        self.assertEqual(out, "Usage: remember: <fact>")


if __name__ == "__main__":
    unittest.main()
