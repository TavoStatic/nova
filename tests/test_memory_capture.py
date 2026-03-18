import unittest
import uuid
import time
import os

import nova_core


class TestMemoryCapture(unittest.TestCase):
    def test_mem_add_and_recall(self):
        marker = f"unittest-memory-{uuid.uuid4().hex}"
        unique = f"remember this my integration marker is {marker}"
        user = f"testuser-{uuid.uuid4().hex}"
        orig_env_user = os.environ.get("NOVA_USER_ID")
        orig_active_user = nova_core.get_active_user()
        # store via nova_core.mem_add (wraps memory.py CLI)
        try:
            os.environ["NOVA_USER_ID"] = user
            nova_core.set_active_user(user)
            nova_core.mem_add("test", "unittest", unique)

            # small delay to allow subprocess to finish writing
            time.sleep(0.2)

            out = nova_core.mem_recall(unique)
            self.assertIsInstance(out, str)
            self.assertIn(marker, out)
        finally:
            if orig_env_user is None:
                os.environ.pop("NOVA_USER_ID", None)
            else:
                os.environ["NOVA_USER_ID"] = orig_env_user
            nova_core.set_active_user(orig_active_user)


if __name__ == "__main__":
    unittest.main()
