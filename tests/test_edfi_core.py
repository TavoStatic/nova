from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.edfi import MILESTONE_ID, run_self_profile
from services.edfi.config import (
    CAPABILITY_SCHEMA,
    ConnectionConfig,
    connection_config_from_dict,
    profile_path,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | list | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or json.dumps(payload or {})

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")

    def json(self):
        return self._payload


class TestEdFiCore(unittest.TestCase):
    def test_golden_rule_no_domain_imports_in_edfi_package(self) -> None:
        root = Path(__file__).resolve().parents[1] / "services" / "edfi"
        banned = ("peims", "tsds", "texas", "attendance", "sped", "skyward", "ascender", "eschool")
        for path in root.glob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for token in banned:
                self.assertNotIn(
                    f"import {token}",
                    text,
                    msg=f"{path.name} must not import {token}",
                )

    def test_connection_config_requires_complete_credentials(self) -> None:
        with self.assertRaises(ValueError):
            connection_config_from_dict({"connection_id": "x", "base_url": "https://example.org"})

    def test_nova_edfi_001_self_profile_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "runtime"
            connections = runtime / "edfi" / "connections" / "district-main"
            profiles = runtime / "edfi" / "profiles"
            audit = runtime / "edfi" / "edfi_audit.jsonl"
            connections.mkdir(parents=True)
            profiles.mkdir(parents=True)

            config = ConnectionConfig(
                connection_id="district-main",
                base_url="https://district.ed-fi.org",
                client_id="client",
                client_secret="secret",
            )

            token_response = _FakeResponse(
                200,
                {"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600, "scope": "edfi"},
            )
            metadata_response = _FakeResponse(
                200,
                {
                    "apiVersion": "3.5.0",
                    "dataModelVersion": "4.0.0",
                    "resources": [
                        {"name": "schools"},
                        {"name": "students"},
                        {"name": "studentSchoolAssociations"},
                    ],
                },
            )
            sample_response = _FakeResponse(200, [])

            with mock.patch("services.edfi.config.EDFI_RUNTIME_ROOT", runtime / "edfi"), \
                mock.patch("services.edfi.config.EDFI_CONNECTIONS_ROOT", connections.parent), \
                mock.patch("services.edfi.config.EDFI_PROFILES_ROOT", profiles), \
                mock.patch("services.edfi.config.EDFI_AUDIT_LOG", audit), \
                mock.patch("services.edfi.diagnostics.EDFI_AUDIT_LOG", audit), \
                mock.patch("services.edfi.auth.requests.Session") as auth_session_cls, \
                mock.patch("services.edfi.client.requests.Session") as client_session_cls:
                auth_session_cls.return_value.post.return_value = token_response
                client_session = client_session_cls.return_value
                client_session.post.return_value = token_response
                client_session.request.side_effect = [metadata_response, sample_response]

                result = run_self_profile(
                    connection_id="district-main",
                    base_url=config.base_url,
                    client_id=config.client_id,
                    client_secret=config.client_secret,
                    now_fn=lambda: 1700000000.0,
                )

            self.assertEqual(result["milestone"], MILESTONE_ID)
            self.assertTrue(result["ok"])
            self.assertEqual(result["health"]["status"], "ok")
            self.assertEqual(result["profile"]["schema"], CAPABILITY_SCHEMA)
            self.assertEqual(result["discovery"]["resource_count"], 3)
            self.assertTrue(Path(result["profile_path"]).exists())
            saved = json.loads(Path(result["profile_path"]).read_text(encoding="utf-8"))
            self.assertEqual(saved["connection_id"], "district-main")
            self.assertIn("schools", saved["discovery"]["resources"])

    def test_self_profile_fails_closed_when_auth_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "runtime"
            connections = runtime / "edfi" / "connections" / "district-main"
            profiles = runtime / "edfi" / "profiles"
            connections.mkdir(parents=True)
            profiles.mkdir(parents=True)

            with mock.patch("services.edfi.config.EDFI_RUNTIME_ROOT", runtime / "edfi"), \
                mock.patch("services.edfi.config.EDFI_CONNECTIONS_ROOT", connections.parent), \
                mock.patch("services.edfi.config.EDFI_PROFILES_ROOT", profiles), \
                mock.patch("services.edfi.config.EDFI_AUDIT_LOG", runtime / "edfi" / "edfi_audit.jsonl"), \
                mock.patch("services.edfi.diagnostics.EDFI_AUDIT_LOG", runtime / "edfi" / "edfi_audit.jsonl"), \
                mock.patch("services.edfi.auth.requests.Session") as auth_session_cls, \
                mock.patch("services.edfi.client.requests.Session") as client_session_cls:
                auth_session_cls.return_value.post.return_value = _FakeResponse(401, text="unauthorized")
                client_session_cls.return_value.post.return_value = _FakeResponse(401, text="unauthorized")
                result = run_self_profile(
                    connection_id="district-main",
                    base_url="https://district.ed-fi.org",
                    client_id="bad",
                    client_secret="bad",
                )

            self.assertFalse(result["ok"])
            self.assertEqual(result["health"]["status"], "failure")
            self.assertIn("edfi_auth_failed", [item["code"] for item in result["health"]["issues"]])

    def test_profile_path_is_scoped_by_connection_id(self) -> None:
        with mock.patch("services.edfi.config.EDFI_PROFILES_ROOT", Path("runtime/edfi/profiles")):
            self.assertTrue(str(profile_path("district-main")).endswith("district-main.json"))


if __name__ == "__main__":
    unittest.main()