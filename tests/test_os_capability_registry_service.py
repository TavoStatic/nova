import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from services.nova_runtime_context import BASE_DIR, OS_CAPABILITY_REGISTRY_FILE
from services.os_capability_registry import OS_CAPABILITY_REGISTRY_SERVICE


def _write_script(path: Path, text: str) -> str:
    path.write_bytes(text.encode("utf-8"))
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestOsCapabilityRegistryService(unittest.TestCase):
    def _write_registry(self, root: Path, capabilities):
        path = root / "runtime" / "os_capabilities.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "registry_version": "0.1.0",
                    "default_operator_outbox_on": [
                        "missing_capability",
                        "contract_stale",
                        "invalid_args",
                        "authority_blocked",
                    ],
                    "capabilities": capabilities,
                },
                ensure_ascii=True,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return path

    def _active_verify_capability(self, script_hash: str):
        return {
            "name": "verify_ollama_model",
            "contract_version": "0.1.0",
            "status": "active",
            "authority_level": "read_only_network",
            "mutating": False,
            "locality": "local_network",
            "network_scope": "127.0.0.1",
            "script": {
                "kind": "powershell",
                "path": "tools/os_capabilities/verify_ollama_model.ps1",
                "sha256": script_hash,
                "timeout_ms": 12000,
                "working_directory": ".",
            },
            "arg_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "base_url": {
                        "type": "string",
                        "default": "http://127.0.0.1:11434",
                    },
                    "model": {
                        "type": "string",
                        "default": "llama3.2:3b",
                    },
                    "probe_chat": {
                        "type": "boolean",
                        "default": False,
                    },
                },
                "required": [],
            },
            "evidence_schema_version": "1.0.0",
        }

    def test_draft_empty_hash_loads_but_cannot_prepare(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            registry_path = self._write_registry(
                root,
                [
                    {
                        "name": "inspect_processes",
                        "contract_version": "0.1.0",
                        "status": "draft",
                        "authority_level": "read_only",
                        "mutating": False,
                        "locality": "local_os",
                        "script": {
                            "kind": "powershell",
                            "path": "tools/os_capabilities/inspect_processes.ps1",
                            "sha256": "",
                            "timeout_ms": 8000,
                            "working_directory": ".",
                        },
                        "arg_schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {},
                            "required": [],
                        },
                        "evidence_schema_version": "1.0.0",
                    }
                ],
            )

            loaded = OS_CAPABILITY_REGISTRY_SERVICE.load_registry(registry_path, base_dir=root)
            prepared = OS_CAPABILITY_REGISTRY_SERVICE.prepare_request(
                "inspect_processes",
                {},
                registry_path,
                base_dir=root,
            )

        cap = loaded["capabilities"]["inspect_processes"]
        self.assertEqual(cap["status"], "draft")
        self.assertFalse(cap["executable"])
        self.assertFalse(prepared["ok"])
        self.assertEqual(prepared["reason"], "contract_stale")
        self.assertTrue(prepared["operator_outbox"])

    def test_active_contract_hash_defaults_and_rejects_unknown_args(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_dir = root / "tools" / "os_capabilities"
            script_dir.mkdir(parents=True)
            script_text = "Write-Output 'ok'\n"
            script_hash = _write_script(script_dir / "verify_ollama_model.ps1", script_text)
            registry_path = self._write_registry(
                root,
                [self._active_verify_capability(script_hash)],
            )

            prepared = OS_CAPABILITY_REGISTRY_SERVICE.prepare_request(
                "verify_ollama_model",
                {"probe_chat": True},
                registry_path,
                base_dir=root,
            )
            invalid = OS_CAPABILITY_REGISTRY_SERVICE.prepare_request(
                "verify_ollama_model",
                {"probe_chat": True, "extra": "no"},
                registry_path,
                base_dir=root,
            )

        self.assertTrue(prepared["ok"])
        self.assertEqual(prepared["args"]["base_url"], "http://127.0.0.1:11434")
        self.assertEqual(prepared["args"]["model"], "llama3.2:3b")
        self.assertTrue(prepared["args"]["probe_chat"])
        self.assertFalse(prepared["evidence_schema_enforced"])
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["reason"], "invalid_args")
        self.assertTrue(invalid["operator_outbox"])
        self.assertIn("unknown_arg:extra", invalid["errors"])

    def test_hash_mismatch_loads_as_contract_stale(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_dir = root / "tools" / "os_capabilities"
            script_dir.mkdir(parents=True)
            _write_script(script_dir / "verify_ollama_model.ps1", "Write-Output 'changed'\n")
            registry_path = self._write_registry(
                root,
                [self._active_verify_capability("0" * 64)],
            )

            loaded = OS_CAPABILITY_REGISTRY_SERVICE.load_registry(registry_path, base_dir=root)
            prepared = OS_CAPABILITY_REGISTRY_SERVICE.prepare_request(
                "verify_ollama_model",
                {},
                registry_path,
                base_dir=root,
            )

        cap = loaded["capabilities"]["verify_ollama_model"]
        self.assertEqual(cap["status"], "contract_stale")
        self.assertIn("sha256_mismatch", cap["errors"])
        self.assertFalse(prepared["ok"])
        self.assertEqual(prepared["reason"], "contract_stale")
        self.assertTrue(prepared["operator_outbox"])

    def test_execution_time_hash_catches_script_drift_after_load(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_dir = root / "tools" / "os_capabilities"
            script_dir.mkdir(parents=True)
            script_text = "Write-Output 'first'\n"
            script_path = script_dir / "verify_ollama_model.ps1"
            script_hash = _write_script(script_path, script_text)
            registry_path = self._write_registry(
                root,
                [self._active_verify_capability(script_hash)],
            )

            loaded = OS_CAPABILITY_REGISTRY_SERVICE.load_registry(registry_path, base_dir=root)
            self.assertEqual(loaded["capabilities"]["verify_ollama_model"]["status"], "active")
            _write_script(script_path, "Write-Output 'drifted'\n")
            prepared = OS_CAPABILITY_REGISTRY_SERVICE.prepare_request(
                "verify_ollama_model",
                {},
                registry_path,
                base_dir=root,
            )

        self.assertFalse(prepared["ok"])
        self.assertEqual(prepared["reason"], "contract_stale")
        self.assertTrue(prepared["operator_outbox"])
        self.assertIn("sha256_mismatch", prepared["errors"])

    def test_allowed_roots_are_contract_bounds_not_script_logic(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_dir = root / "tools" / "os_capabilities"
            script_dir.mkdir(parents=True)
            script_text = "Write-Output 'scan'\n"
            script_hash = _write_script(script_dir / "scan_large_files.ps1", script_text)
            registry_path = self._write_registry(
                root,
                [
                    {
                        "name": "scan_large_files",
                        "contract_version": "0.1.0",
                        "status": "active",
                        "authority_level": "read_only_expensive",
                        "mutating": False,
                        "locality": "local_filesystem",
                        "allowed_roots": ["runtime", "logs", "memory", "exports"],
                        "script": {
                            "kind": "powershell",
                            "path": "tools/os_capabilities/scan_large_files.ps1",
                            "sha256": script_hash,
                            "timeout_ms": 30000,
                            "working_directory": ".",
                        },
                        "arg_schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "root": {"type": "string"},
                                "limit": {"type": "integer", "default": 25, "minimum": 1, "maximum": 200},
                            },
                            "required": ["root"],
                        },
                        "evidence_schema_version": "1.0.0",
                    }
                ],
            )

            invalid = OS_CAPABILITY_REGISTRY_SERVICE.prepare_request(
                "scan_large_files",
                {"root": "C:/"},
                registry_path,
                base_dir=root,
            )

        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["reason"], "invalid_args")
        self.assertTrue(invalid["operator_outbox"])
        self.assertIn("arg_not_allowed_root:root", invalid["errors"])

    def test_network_scope_rejects_non_localhost_base_url(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_dir = root / "tools" / "os_capabilities"
            script_dir.mkdir(parents=True)
            script_text = "Write-Output 'ok'\n"
            script_hash = _write_script(script_dir / "verify_ollama_model.ps1", script_text)
            registry_path = self._write_registry(
                root,
                [self._active_verify_capability(script_hash)],
            )

            invalid = OS_CAPABILITY_REGISTRY_SERVICE.prepare_request(
                "verify_ollama_model",
                {"base_url": "http://example.com:11434"},
                registry_path,
                base_dir=root,
            )

        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["reason"], "invalid_args")
        self.assertTrue(invalid["operator_outbox"])
        self.assertIn("arg_network_scope:base_url:127.0.0.1", invalid["errors"])

    def test_missing_capability_is_operator_worthy(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            registry_path = self._write_registry(root, [])

            missing = OS_CAPABILITY_REGISTRY_SERVICE.prepare_request(
                "restart_runtime_component",
                {},
                registry_path,
                base_dir=root,
            )

        self.assertFalse(missing["ok"])
        self.assertEqual(missing["reason"], "missing_capability")
        self.assertTrue(missing["operator_outbox"])

    def test_draft_does_not_hide_malformed_contract(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            registry_path = self._write_registry(
                root,
                [
                    {
                        "name": "bad_draft",
                        "status": "draft",
                        "script": {
                            "kind": "powershell",
                            "path": "tools/os_capabilities/bad_draft.ps1",
                            "sha256": "",
                            "timeout_ms": 8000,
                            "working_directory": ".",
                        },
                        "arg_schema": {
                            "type": "object",
                            "additionalProperties": True,
                            "properties": {},
                            "required": [],
                        },
                    }
                ],
            )

            loaded = OS_CAPABILITY_REGISTRY_SERVICE.load_registry(registry_path, base_dir=root)

        cap = loaded["capabilities"]["bad_draft"]
        self.assertFalse(loaded["ok"])
        self.assertEqual(cap["status"], "invalid_contract")
        self.assertIn("missing_contract_field:authority_level", cap["errors"])
        self.assertIn("arg_schema_additional_properties_must_be_false", cap["errors"])

    def test_default_source_registry_has_active_first_slice_capabilities(self):
        loaded = OS_CAPABILITY_REGISTRY_SERVICE.load_registry(OS_CAPABILITY_REGISTRY_FILE, base_dir=BASE_DIR)
        prepared_by_name = {
            name: OS_CAPABILITY_REGISTRY_SERVICE.prepare_request(
                name,
                {"root": "runtime"} if name == "scan_large_files" else {},
                OS_CAPABILITY_REGISTRY_FILE,
                base_dir=BASE_DIR,
            )
            for name in (
                "inspect_processes",
                "inspect_ports",
                "scan_large_files",
                "collect_diagnostics_bundle",
                "verify_ollama_model",
            )
        }

        self.assertTrue(loaded["ok"])
        for name, prepared in prepared_by_name.items():
            self.assertEqual(loaded["capabilities"][name]["status"], "active")
            self.assertTrue(prepared["ok"], name)
        self.assertEqual(prepared_by_name["verify_ollama_model"]["args"]["base_url"], "http://127.0.0.1:11434")
        self.assertEqual(prepared_by_name["scan_large_files"]["args"]["root"], "runtime")
