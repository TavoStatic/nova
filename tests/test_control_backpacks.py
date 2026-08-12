from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.control_backpacks import ControlBackpacksService
from services.nova_runtime_context import BASE_DIR


class TestControlBackpacksService(unittest.TestCase):
    def test_list_includes_edfi_reference(self) -> None:
        svc = ControlBackpacksService(backpacks_root=BASE_DIR / "backpacks")
        rows = svc.list_backpacks()
        ids = {str(r.get("backpack_id")) for r in rows}
        self.assertIn("edfi", ids)

    def test_payload_model_is_honest(self) -> None:
        svc = ControlBackpacksService(backpacks_root=BASE_DIR / "backpacks")
        payload = svc.payload(selected_backpack_id="edfi", role="account_admin")
        self.assertTrue(payload.get("ok"))
        self.assertTrue(payload.get("model", {}).get("nova_install_first"))
        self.assertTrue(payload.get("model", {}).get("backpacks_optional_after_settle"))
        self.assertEqual(payload.get("model", {}).get("reference_backpack"), "edfi")
        detail = payload.get("detail") or {}
        self.assertEqual(detail.get("backpack_id"), "edfi")
        self.assertIn("settings_schema", detail)

    def test_install_validate_only_path(self) -> None:
        svc = ControlBackpacksService(backpacks_root=BASE_DIR / "backpacks")
        ok, msg, extra, _ = svc.install(
            {
                "backpack_id": "edfi",
                "settings": {
                    "connection_id": "test-only",
                    "base_url": "https://example.invalid",
                    "client_id": "id",
                    "client_secret": "secret",
                    "scope_mode": "single_lea",
                    "district_lea_id": "[lea-id]",
                },
                "skip_profile": True,
            },
            skip_profile=True,
        )
        # apply writes under real RUNTIME_DIR — use temp via service override
        self.assertIn(msg, {"backpack_settings_saved", "backpack_apply_failed", "backpack_validate_failed"})
        # At least validate should pass for well-formed values
        if msg == "backpack_validate_failed":
            self.fail(f"unexpected validate fail: {extra}")

    def test_install_to_temp_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svc = ControlBackpacksService(
                backpacks_root=BASE_DIR / "backpacks",
                runtime_root=Path(tmp),
                nova_root=BASE_DIR,
            )
            ok, msg, extra, _ = svc.install(
                {
                    "backpack_id": "edfi",
                    "settings": {
                        "connection_id": "panel-test",
                        "base_url": "https://example.invalid",
                        "client_id": "id",
                        "client_secret": "secret",
                        "scope_mode": "single_lea",
                        "district_lea_id": "[lea-id]",
                        "credential_access_tier": "read",
                    },
                    "skip_profile": True,
                },
                skip_profile=True,
            )
            self.assertTrue(ok)
            self.assertEqual(msg, "backpack_settings_saved")
            settings_path = Path(tmp) / "edfi" / "settings.json"
            self.assertTrue(settings_path.is_file())
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(data.get("district_lea_id"), "31901")  # normalized

    def test_ensure_settings_bootstraps_from_connection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            conn_dir = runtime / "edfi" / "connections" / "district-main"
            conn_dir.mkdir(parents=True)
            (conn_dir / "local_config.json").write_text(
                json.dumps(
                    {
                        "connection_id": "district-main",
                        "base_url": "https://example.invalid",
                        "client_id": "cid",
                        "client_secret": "csecret",
                        "district_lea_id": "31901",
                        "token_path": "/oauth/token",
                        "api_root": "/data/v3",
                        "metadata_path": "/metadata/resources",
                        "timeout_sec": 30,
                        "verify_ssl": True,
                    }
                ),
                encoding="utf-8",
            )
            svc = ControlBackpacksService(
                backpacks_root=BASE_DIR / "backpacks",
                runtime_root=runtime,
                nova_root=BASE_DIR,
            )
            settings = svc.ensure_settings("edfi", write=True)
            self.assertEqual(settings.get("connection_id"), "district-main")
            self.assertEqual(settings.get("client_id"), "cid")
            self.assertTrue(str(settings.get("client_secret") or ""))
            path = runtime / "edfi" / "settings.json"
            self.assertTrue(path.is_file())
            public = svc._public_settings(settings)
            self.assertNotIn("client_secret", public)
            self.assertIn("base_url", public)

    def test_teach_surface_has_pipeline_rules(self) -> None:
        svc = ControlBackpacksService(backpacks_root=BASE_DIR / "backpacks")
        teach = svc._teach_surface(BASE_DIR / "backpacks" / "edfi")
        self.assertTrue(teach.get("brief_path"))
        self.assertGreaterEqual(len(teach.get("rules") or []), 4)
        self.assertEqual(teach.get("phase"), "pipeline")

    def test_save_settings_reuses_secret_when_blank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            svc = ControlBackpacksService(
                backpacks_root=BASE_DIR / "backpacks",
                runtime_root=runtime,
                nova_root=BASE_DIR,
            )
            ok, msg, _, _ = svc.install(
                {
                    "backpack_id": "edfi",
                    "settings": {
                        "connection_id": "norm-apply",
                        "base_url": "https://example.invalid",
                        "client_id": "id1",
                        "client_secret": "keep-me",
                        "scope_mode": "single_lea",
                        "district_lea_id": "[lea-id]",
                    },
                    "skip_profile": True,
                },
                skip_profile=True,
            )
            self.assertTrue(ok, msg)
            ok2, msg2, _, _ = svc.install(
                {
                    "backpack_id": "edfi",
                    "settings": {
                        "connection_id": "norm-apply",
                        "base_url": "https://example.invalid",
                        "client_id": "id1",
                        "client_secret": "",
                        "scope_mode": "single_lea",
                        "district_lea_id": "[lea-id]",
                    },
                    "skip_profile": True,
                },
                skip_profile=True,
            )
            self.assertTrue(ok2, msg2)
            data = json.loads((runtime / "edfi" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(data.get("client_secret"), "keep-me")


if __name__ == "__main__":
    unittest.main()
