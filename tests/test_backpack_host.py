from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.backpack_host.grant_enforcer import check_grant, operation_summary
from services.backpack_host.ops_map import (
    backpack_dir_for_pipeline_id,
    pipeline_op_to_backpack_op,
    resolve_shell_role,
)
from services.backpack_host.query import run_backpack_query
from services.backpack_host.loader import load_backpack_manifest
from services.nova_runtime_context import BASE_DIR


class TestOpsMap(unittest.TestCase):
    def test_pipeline_op_maps_to_backpack_op(self) -> None:
        root = BASE_DIR / "backpacks" / "edfi"
        self.assertEqual(pipeline_op_to_backpack_op(root, "connection_health"), "view_status")
        self.assertEqual(pipeline_op_to_backpack_op(root, "list_schools"), "view_data")
        self.assertEqual(pipeline_op_to_backpack_op(root, "changes_since"), "run_sync")
        self.assertEqual(pipeline_op_to_backpack_op(root, "warehouse_sync"), "run_warehouse_sync")
        self.assertEqual(pipeline_op_to_backpack_op(root, "warehouse_status"), "run_warehouse_sync")

    def test_backpack_dir_lookup(self) -> None:
        found = backpack_dir_for_pipeline_id("edfi", backpacks_root=BASE_DIR / "backpacks")
        self.assertIsNotNone(found)
        self.assertTrue((found / "backpack.json").is_file())

    def test_resolve_shell_role(self) -> None:
        self.assertEqual(resolve_shell_role(role="viewer"), "viewer")
        self.assertEqual(resolve_shell_role(is_admin=True), "account_admin")
        self.assertEqual(resolve_shell_role(is_admin=False), "standard_user")
        self.assertEqual(
            resolve_shell_role(context_extra={"shell_role": "limited_user"}),
            "limited_user",
        )


class TestGrants(unittest.TestCase):
    def setUp(self) -> None:
        self.root = BASE_DIR / "backpacks" / "edfi"

    def test_viewer_can_status_not_data(self) -> None:
        self.assertTrue(check_grant(self.root, "view_status", "viewer"))
        self.assertFalse(check_grant(self.root, "view_data", "viewer"))
        self.assertFalse(check_grant(self.root, "run_sync", "viewer"))
        self.assertFalse(check_grant(self.root, "run_warehouse_sync", "viewer"))
        self.assertFalse(check_grant(self.root, "install", "viewer"))

    def test_account_admin_can_install(self) -> None:
        self.assertTrue(check_grant(self.root, "install", "account_admin"))
        self.assertTrue(check_grant(self.root, "configure", "account_admin"))

    def test_operation_summary(self) -> None:
        summary = operation_summary(self.root, "viewer")
        granted = {o["id"]: o["granted"] for o in summary["operations"]}
        self.assertTrue(granted.get("view_status"))
        self.assertFalse(granted.get("view_data"))


class TestLoaderAndQueryGrants(unittest.TestCase):
    def test_load_edfi_manifest(self) -> None:
        from services.nova_runtime_context import RUNTIME_DIR

        manifest = load_backpack_manifest(
            BASE_DIR / "backpacks" / "edfi",
            nova_root=BASE_DIR,
            runtime_root=RUNTIME_DIR,
        )
        self.assertEqual(manifest.pipeline_id, "edfi")
        self.assertEqual(manifest.kind, "backpack")
        self.assertIn("backpacks.edfi.pipeline.connector", manifest.connector_module)

    def test_viewer_denied_list_schools(self) -> None:
        result = run_backpack_query("edfi", "list_schools", role="viewer")
        self.assertFalse(result.get("ok"))
        self.assertIn("backpack_grant_denied", str(result.get("error") or ""))
        self.assertEqual(result.get("backpack_operation"), "view_data")

    def test_standard_user_allowed_through_grant_gate(self) -> None:
        fake = {"ok": True, "operation": "list_schools", "rows": []}

        class _Pipe:
            def safe_query(self, *args, **kwargs):
                return dict(fake)

        with mock.patch(
            "services.backpack_host.query._registry"
        ) as reg:
            reg.return_value.instantiate.return_value = _Pipe()
            result = run_backpack_query("edfi", "list_schools", role="standard_user")
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("governed_route"), "backpack_host")


class TestScopeSettings(unittest.TestCase):
    def test_single_lea_requires_district_id(self) -> None:
        from services.backpack_host.scope_settings import validate_scope_values

        errors = validate_scope_values({"scope_mode": "single_lea"})
        self.assertTrue(any(e["code"] == "district_lea_id_required" for e in errors))

    def test_multi_lea_requires_list(self) -> None:
        from services.backpack_host.scope_settings import validate_scope_values

        errors = validate_scope_values({"scope_mode": "multi_lea"})
        self.assertTrue(any(e["code"] == "allowed_lea_ids_required" for e in errors))

    def test_resolve_query_lea_region_pick(self) -> None:
        from services.backpack_host.scope_settings import resolve_query_lea

        settings = {
            "scope_mode": "multi_lea",
            "district_lea_id": "12345",
            "allowed_lea_ids": "31901, 108904",
        }
        lea, err = resolve_query_lea(settings, "108904")
        self.assertIsNone(err)
        self.assertEqual(lea, "108904")
        lea2, err2 = resolve_query_lea(settings, "99999")
        self.assertEqual(err2, "lea_not_in_allowed_list")
        self.assertEqual(lea2, "")

    def test_lea_id_forms_match(self) -> None:
        from services.backpack_host.scope_settings import (
            lea_in_list,
            lea_identity_key,
            resolve_query_lea,
        )

        self.assertEqual(lea_identity_key("[lea-id]"), 12345)
        self.assertEqual(lea_identity_key("12345"), 12345)
        self.assertTrue(lea_in_list("[lea-id]", ["12345"]))
        settings = {
            "scope_mode": "single_lea",
            "district_lea_id": "12345",
        }
        lea, err = resolve_query_lea(settings, "[lea-id]")
        self.assertIsNone(err)
        self.assertEqual(lea, "12345")


class TestInstallerValidate(unittest.TestCase):
    def test_validate_requires_fields(self) -> None:
        from services.backpack_host.installer import BackpackInstaller

        installer = BackpackInstaller()
        errors = installer.validate(BASE_DIR / "backpacks" / "edfi", {})
        codes = {e["code"] for e in errors}
        self.assertIn("connection_id_required", codes)
        self.assertIn("base_url_required", codes)
        self.assertIn("client_secret_required", codes)
        # single_lea default still needs a LEA
        self.assertIn("district_lea_id_required", codes)

    def test_apply_writes_settings(self) -> None:
        from services.backpack_host.installer import BackpackInstaller

        installer = BackpackInstaller()
        values = {
            "connection_id": "test-conn",
            "base_url": "https://example.invalid",
            "client_id": "id",
            "client_secret": "secret",
            "district_lea_id": "12345",
        }
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            # Force apply without calling real save_connection_config network paths:
            # save_connection_config only writes files — ok offline.
            result = installer.apply(
                BASE_DIR / "backpacks" / "edfi",
                values,
                runtime_root=runtime,
            )
            settings = runtime / "edfi" / "settings.json"
            self.assertTrue(settings.is_file())
            data = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(data["district_lea_id"], "12345")
            self.assertTrue(result.get("ok") or result.get("settings_path"))

    def test_validate_normalizes_values_in_place(self) -> None:
        """Regression: validate must write canonical scope/tier back into caller dict."""
        from services.backpack_host.installer import BackpackInstaller

        installer = BackpackInstaller()
        values = {
            "connection_id": "norm-test",
            "base_url": "https://example.invalid",
            "client_id": "id",
            "client_secret": "secret",
            "scope_mode": "district",  # alias
            "credential_access_tier": "read_only",  # alias
            "district_lea_id": "[lea-id]",
        }
        errors = installer.validate(BASE_DIR / "backpacks" / "edfi", values)
        self.assertEqual(errors, [])
        self.assertEqual(values.get("scope_mode"), "single_lea")
        self.assertEqual(values.get("credential_access_tier"), "read")
        self.assertEqual(values.get("district_lea_id"), "12345")

    def test_apply_normalizes_aliases_to_settings_json(self) -> None:
        from services.backpack_host.installer import BackpackInstaller

        installer = BackpackInstaller()
        values = {
            "connection_id": "norm-apply",
            "base_url": "https://example.invalid",
            "client_id": "id",
            "client_secret": "secret",
            "scope_mode": "region",
            "credential_access_tier": "ro",
            "district_lea_id": "[lea-id]",
            "allowed_lea_ids": "[lea-id], 108904",
        }
        with tempfile.TemporaryDirectory() as tmp:
            installer.apply(
                BASE_DIR / "backpacks" / "edfi",
                values,
                runtime_root=Path(tmp),
            )
            data = json.loads((Path(tmp) / "edfi" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(data["scope_mode"], "multi_lea")
            self.assertEqual(data["credential_access_tier"], "read")
            self.assertEqual(data["district_lea_id"], "12345")
            self.assertEqual(values["scope_mode"], "multi_lea")


if __name__ == "__main__":
    unittest.main()
