import unittest

from services.supervisor_registry import DEFAULT_SUPERVISOR_RULE_SPECS
from supervisor import Supervisor


class TestSupervisorRegistry(unittest.TestCase):
    def test_default_registry_drives_supervisor_rule_order(self):
        supervisor = Supervisor()
        expected_names = [
            str(item.get("name") or "")
            for item in sorted(
                DEFAULT_SUPERVISOR_RULE_SPECS,
                key=lambda item: (int(item.get("priority", 100)), str(item.get("name") or "")),
            )
        ]
        actual_names = [str(item.get("name") or "") for item in supervisor.rules]

        self.assertEqual(actual_names, expected_names)


if __name__ == "__main__":
    unittest.main()