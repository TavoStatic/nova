import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from services.frontdoor_cli_parity import FRONTDOOR_CLI_PARITY_SERVICE, build_frontdoor_cli_surfaces
from services.work_tree_signal_ingestion import _frontdoor_cli_signal_from_status


class TestFrontdoorCliParityService(unittest.TestCase):
    def test_build_surfaces_reports_ok_for_real_repo(self):
        root = Path(__file__).resolve().parents[1]
        surfaces = build_frontdoor_cli_surfaces(root=root, limit=40)

        self.assertEqual(surfaces.get("frontdoor_cli_status"), "ok")
        self.assertTrue((surfaces.get("cli_http_parity") or {}).get("ok"))
        self.assertGreaterEqual(int(surfaces.get("backend_command_count") or 0), 4)
        command_ids = {
            str(row.get("command_id") or "")
            for row in list(surfaces.get("backend_commands") or [])
            if isinstance(row, dict)
        }
        self.assertIn("nova_server_side", command_ids)
        self.assertIn("reverse_proxy_frontdoor", command_ids)

    def test_build_surfaces_marks_missing_frontdoor_as_missing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            surfaces = build_frontdoor_cli_surfaces(root=root, backend_commands=[])

        self.assertEqual(surfaces.get("frontdoor_cli_status"), "missing")
        self.assertFalse((surfaces.get("cli_http_parity") or {}).get("frontdoor_checks_ok"))

    def test_build_surfaces_marks_malformed_backend_commands_unreadable(self):
        root = Path(__file__).resolve().parents[1]
        surfaces = build_frontdoor_cli_surfaces(root=root, backend_commands="broken")

        self.assertEqual(surfaces.get("frontdoor_cli_status"), "unreadable")

    def test_local_frontdoor_surfaces_do_not_raise_frontdoor_cli_signal(self):
        root = Path(__file__).resolve().parents[1]
        surfaces = FRONTDOOR_CLI_PARITY_SERVICE.build_surfaces(root=root, limit=40)
        status_payload = {
            "backend_commands": surfaces.get("backend_commands"),
            "backend_command_count": surfaces.get("backend_command_count"),
            "frontdoor_cli_status": surfaces.get("frontdoor_cli_status"),
            "cli_http_parity": surfaces.get("cli_http_parity"),
        }

        signal = _frontdoor_cli_signal_from_status(status_payload)

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()