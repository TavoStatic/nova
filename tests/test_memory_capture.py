import unittest
import uuid
import time

import nova_core


class TestMemoryCapture(unittest.TestCase):
    def test_mem_add_and_recall(self):
        unique = f"unittest-memory-{uuid.uuid4().hex}"
        # store via nova_core.mem_add (wraps memory.py CLI)
        nova_core.mem_add("test", "unittest", unique)

        # small delay to allow subprocess to finish writing
        time.sleep(0.2)

        out = nova_core.mem_recall(unique)
        self.assertIsInstance(out, str)
        self.assertIn("unittest-memory", out)


if __name__ == "__main__":
    unittest.main()
