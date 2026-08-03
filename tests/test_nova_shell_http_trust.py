from __future__ import annotations

import unittest

from services.nova_shell.http_trust import resolve_control_panel_role, shell_http_status


class TestShellHttpTrust(unittest.TestCase):
    def test_privileged_actions_force_account_admin(self) -> None:
        self.assertEqual(
            resolve_control_panel_role(
                "viewer",
                control_authenticated=True,
                for_privileged_action=True,
            ),
            "account_admin",
        )
        self.assertEqual(
            resolve_control_panel_role(
                "llc_master",
                control_authenticated=True,
                for_privileged_action=True,
            ),
            "account_admin",
        )

    def test_preview_allows_viewer(self) -> None:
        self.assertEqual(
            resolve_control_panel_role(
                "viewer",
                control_authenticated=True,
                for_privileged_action=False,
            ),
            "viewer",
        )

    def test_unauthenticated_is_viewer(self) -> None:
        self.assertEqual(
            resolve_control_panel_role(
                "account_admin",
                control_authenticated=False,
                for_privileged_action=True,
            ),
            "viewer",
        )

    def test_status_is_honest(self) -> None:
        status = shell_http_status()
        self.assertFalse(status["shell_bearer_middleware"])
        self.assertTrue(status["control_auth_gates_control_api"])


if __name__ == "__main__":
    unittest.main()
