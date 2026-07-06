from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from services.edfi import MILESTONE_ID, run_self_profile
from services.edfi.auth import EdFiAuthService
from services.edfi.client import EdFiClient
from services.edfi.config import (
    CAPABILITY_SCHEMA,
    ConnectionConfig,
    TokenCacheEntry,
    connection_config_from_dict,
    profile_path,
    validate_connection_payload,
)
from services.edfi.diagnostics import append_audit_event
from services.edfi.errors import classify_request_exception


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | list | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or json.dumps(payload or {})

    @property
    def ok(self) -> bool:
        return int(self.status_code) < 400

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")

    def json(self):
        return self._payload


def _runtime_patches(tmp: str):
    runtime = Path(tmp) / "runtime"
    connections = runtime / "edfi" / "connections" / "district-main"
    profiles = runtime / "edfi" / "profiles"
    audit = runtime / "edfi" / "edfi_audit.jsonl"
    connections.mkdir(parents=True)
    profiles.mkdir(parents=True)
    return (
        mock.patch("services.edfi.config.EDFI_RUNTIME_ROOT", runtime / "edfi"),
        mock.patch("services.edfi.config.EDFI_CONNECTIONS_ROOT", connections.parent),
        mock.patch("services.edfi.config.EDFI_PROFILES_ROOT", profiles),
        mock.patch("services.edfi.config.EDFI_AUDIT_LOG", audit),
        mock.patch("services.edfi.diagnostics.EDFI_AUDIT_LOG", audit),
        audit,
    )


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

    def test_connection_config_validation_matrix(self) -> None:
        cases = [
            ({"connection_id": "x"}, "connection_base_url_missing"),
            ({"connection_id": "x", "base_url": "https://example.org"}, "connection_client_id_missing"),
            (
                {"connection_id": "x", "base_url": "https://example.org", "client_id": "id"},
                "connection_client_secret_missing",
            ),
            (
                {"connection_id": "x", "base_url": "not-a-url", "client_id": "id", "client_secret": "secret"},
                "connection_base_url_invalid",
            ),
            (
                {
                    "connection_id": "x",
                    "base_url": "https://example.org",
                    "client_id": "id",
                    "client_secret": "secret",
                    "verify_ssl": "yes",
                },
                "connection_ssl_verify_invalid",
            ),
            (
                {
                    "connection_id": "x",
                    "base_url": "https://example.org",
                    "client_id": "id",
                    "client_secret": "secret",
                    "ca_bundle_path": "missing-bundle.pem",
                },
                "connection_ca_bundle_missing",
            ),
        ]
        for payload, expected_code in cases:
            errors = validate_connection_payload(payload, connection_id="x")
            codes = [item["code"] for item in errors]
            self.assertIn(expected_code, codes, msg=str(payload))

    def test_connection_config_requires_complete_credentials(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            connection_config_from_dict({"connection_id": "x", "base_url": "https://example.org"})
        self.assertEqual(str(ctx.exception), "connection_client_id_missing")

    def test_nova_edfi_001_self_profile_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2, p3, p4, p5, audit = _runtime_patches(tmp)
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

            with p1, p2, p3, p4, p5, \
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
            self.assertTrue(saved["discovery"]["stages"]["metadata"]["ok"])
            self.assertTrue(saved["discovery"]["stages"]["sample_get"]["ok"])
            self.assertTrue(audit.exists())
            lines = audit.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            audit_event = json.loads(lines[0])
            self.assertEqual(audit_event["action"], "self_profile")
            self.assertTrue(audit_event["auth_ok"])

    def test_self_profile_fails_closed_when_auth_fails_401(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2, p3, p4, p5, _audit = _runtime_patches(tmp)
            with p1, p2, p3, p4, p5, \
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
            codes = [item["code"] for item in result["health"]["issues"]]
            self.assertIn("edfi_auth_unauthorized", codes)

    def test_self_profile_auth_forbidden_403(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2, p3, p4, p5, _audit = _runtime_patches(tmp)
            with p1, p2, p3, p4, p5, \
                mock.patch("services.edfi.auth.requests.Session") as auth_session_cls, \
                mock.patch("services.edfi.client.requests.Session") as client_session_cls:
                auth_session_cls.return_value.post.return_value = _FakeResponse(403, text="forbidden")
                client_session_cls.return_value.post.return_value = _FakeResponse(403, text="forbidden")
                result = run_self_profile(
                    connection_id="district-main",
                    base_url="https://district.ed-fi.org",
                    client_id="bad",
                    client_secret="bad",
                )
            codes = [item["code"] for item in result["health"]["issues"]]
            self.assertIn("edfi_auth_forbidden", codes)

    def test_self_profile_config_missing_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2, p3, p4, p5, audit = _runtime_patches(tmp)
            with p1, p2, p3, p4, p5:
                result = run_self_profile(
                    connection_id="district-main",
                    base_url="",
                    client_id="id",
                    client_secret="secret",
                )
            self.assertFalse(result["ok"])
            self.assertEqual(result["error_code"], "connection_base_url_missing")
            self.assertIn("connection_base_url_missing", [i["code"] for i in result["health"]["issues"]])
            self.assertTrue(audit.exists())

    def test_self_profile_invalid_connection_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2, p3, p4, p5, _audit = _runtime_patches(tmp)
            config_dir = Path(tmp) / "runtime" / "edfi" / "connections" / "district-main"
            (config_dir / "local_config.json").write_text("{not-json", encoding="utf-8")
            with p1, p2, p3, p4, p5:
                result = run_self_profile(connection_id="district-main")
            self.assertFalse(result["ok"])
            self.assertEqual(result["error_code"], "connection_config_json_invalid")

    def test_partial_discovery_metadata_ok_sample_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2, p3, p4, p5, _audit = _runtime_patches(tmp)
            token_response = _FakeResponse(200, {"access_token": "token", "expires_in": 3600})
            metadata_response = _FakeResponse(200, {"resources": [{"name": "schools"}]})
            sample_response = _FakeResponse(403, text="forbidden")

            with p1, p2, p3, p4, p5, \
                mock.patch("services.edfi.auth.requests.Session") as auth_session_cls, \
                mock.patch("services.edfi.client.requests.Session") as client_session_cls:
                auth_session_cls.return_value.post.return_value = token_response
                client_session = client_session_cls.return_value
                client_session.post.return_value = token_response
                client_session.request.side_effect = [metadata_response, sample_response, sample_response]
                result = run_self_profile(
                    connection_id="district-main",
                    base_url="https://district.ed-fi.org",
                    client_id="client",
                    client_secret="secret",
                )

            self.assertFalse(result["ok"])
            self.assertEqual(result["health"]["status"], "watch")
            profile = json.loads(Path(result["profile_path"]).read_text(encoding="utf-8"))
            stages = profile["discovery"]["stages"]
            self.assertTrue(stages["metadata"]["ok"])
            self.assertFalse(stages["sample_get"]["ok"])
            self.assertEqual(stages["sample_get"]["error_code"], "edfi_auth_forbidden")

    def test_discover_metadata_falls_back_to_root_dependencies(self) -> None:
        config = ConnectionConfig(
            connection_id="district-main",
            base_url="https://district.ed-fi.org",
            client_id="client",
            client_secret="secret",
        )
        client = EdFiClient(config, auth_service=mock.Mock(), session=mock.Mock())
        client.auth.get_authorization_header.return_value = ("Bearer token", mock.Mock(ok=True))

        metadata_404 = mock.Mock(
            ok=False,
            status_code=404,
            latency_ms=10,
            error="not found",
            error_code="edfi_not_found",
            body=None,
        )
        root_200 = mock.Mock(
            ok=True,
            status_code=200,
            latency_ms=12,
            body={
                "version": "7.1",
                "dataModels": [{"name": "Ed-Fi", "version": "4.0.0"}],
                "urls": {
                    "dependencies": "https://district.ed-fi.org/metadata/data/v3/dependencies",
                    "dataManagementApi": "https://district.ed-fi.org/data/v3/",
                },
            },
        )
        deps_200 = mock.Mock(
            ok=True,
            status_code=200,
            latency_ms=15,
            body=[{"resource": "/ed-fi/schools"}, {"resource": "/ed-fi/students"}],
        )
        sample_200 = mock.Mock(ok=True, status_code=200, latency_ms=20, body=[])

        with mock.patch.object(client, "get", side_effect=[metadata_404, root_200, deps_200, sample_200]) as get_mock:
            from services.edfi.discovery import discover_metadata

            result = discover_metadata(client)

        self.assertTrue(result.ok)
        self.assertEqual(result.resource_count, 2)
        self.assertEqual(result.api_version, "7.1")
        self.assertEqual(result.data_model_version, "4.0.0")
        self.assertIn("ed-fi/schools", result.resources)
        self.assertTrue(result.sample_ok)
        self.assertEqual(get_mock.call_args_list[-1].args[0], "https://district.ed-fi.org/data/v3/ed-fi/schools")

    def test_fetch_token_retries_with_basic_auth_on_invalid_request(self) -> None:
        config = ConnectionConfig(
            connection_id="district-main",
            base_url="https://odsprod.tea.texas.gov/odsedfiapi2026",
            client_id="client",
            client_secret="secret",
        )
        service = EdFiAuthService(session=mock.Mock())
        bad = _FakeResponse(400, text='{"error":"invalid_request"}')
        good = _FakeResponse(200, {"access_token": "token-abc", "expires_in": 1800})
        service._session.post.side_effect = [bad, good]
        result = service.fetch_token(config)
        self.assertTrue(result.ok)
        self.assertEqual(result.access_token, "token-abc")
        self.assertEqual(service._session.post.call_count, 2)
        second_call = service._session.post.call_args_list[1]
        self.assertEqual(second_call.kwargs.get("auth"), ("client", "secret"))
        self.assertEqual(second_call.kwargs["data"], {"grant_type": "client_credentials"})

    def test_auth_transport_error_classification(self) -> None:
        service = EdFiAuthService(session=mock.Mock())
        config = ConnectionConfig(
            connection_id="district-main",
            base_url="https://district.ed-fi.org",
            client_id="client",
            client_secret="secret",
        )
        service._session.post.side_effect = requests.exceptions.ConnectTimeout("timed out")
        result = service.fetch_token(config)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "edfi_timeout")

        service._session.post.side_effect = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='missing.example', port=443): Max retries exceeded "
            "with url: /oauth/token (Caused by NameResolutionError: getaddrinfo failed)"
        )
        result = service.fetch_token(config)
        self.assertEqual(result.error_code, "edfi_dns_failure")

        service._session.post.side_effect = requests.exceptions.SSLError("certificate verify failed")
        result = service.fetch_token(config)
        self.assertEqual(result.error_code, "edfi_ssl_error")

    def test_expired_token_is_refreshed(self) -> None:
        config = ConnectionConfig(
            connection_id="district-main",
            base_url="https://district.ed-fi.org",
            client_id="client",
            client_secret="secret",
        )
        service = EdFiAuthService(session=mock.Mock())
        service._cache[config.connection_id] = TokenCacheEntry(
            access_token="old-token",
            expires_at=100.0,
        )
        token_response = _FakeResponse(200, {"access_token": "new-token", "expires_in": 3600})
        service._session.post.return_value = token_response
        header, result = service.get_authorization_header(config, now_fn=lambda: 200.0)
        self.assertTrue(result.ok)
        self.assertEqual(header, "Bearer new-token")

    def test_client_get_resource_name_resolves_under_api_root(self) -> None:
        config = ConnectionConfig(
            connection_id="district-main",
            base_url="https://district.ed-fi.org",
            client_id="client",
            client_secret="secret",
        )
        client = EdFiClient(config, auth_service=mock.Mock(), session=mock.Mock())
        client.auth.get_authorization_header.return_value = ("Bearer token", mock.Mock(ok=True))
        client._session.request.return_value = mock.Mock(status_code=200, content=b"[]", text="[]")
        with mock.patch("services.edfi.client._parse_json", return_value=[]):
            response = client.get("students")
        self.assertTrue(response.ok)
        called_url = client._session.request.call_args.args[1]
        self.assertEqual(called_url, "https://district.ed-fi.org/data/v3/students")

    def test_profile_path_is_scoped_by_connection_id(self) -> None:
        with mock.patch("services.edfi.config.EDFI_PROFILES_ROOT", Path("runtime/edfi/profiles")):
            self.assertTrue(str(profile_path("district-main")).endswith("district-main.json"))

    def test_audit_log_lines_are_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            audit = Path(tmp) / "edfi_audit.jsonl"
            append_audit_event({"action": "probe", "ok": False, "error_code": "edfi_timeout"}, audit_log_path=audit)
            append_audit_event({"action": "probe", "ok": True}, audit_log_path=audit)
            lines = audit.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            for line in lines:
                payload = json.loads(line)
                self.assertEqual(payload["component"], "edfi_core")
                self.assertIn("ts", payload)

    def test_classify_request_exception_helper(self) -> None:
        self.assertEqual(
            classify_request_exception(requests.exceptions.ReadTimeout("read timed out")),
            "edfi_timeout",
        )


if __name__ == "__main__":
    unittest.main()