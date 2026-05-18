import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from services.nova_runtime_context import BASE_DIR, OS_CAPABILITY_REGISTRY_FILE
from services.os_script_controller import OS_SCRIPT_CONTROLLER_SERVICE


def _write_script(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_ledger(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class FakeProcess:
    def __init__(self, *, stdout="", stderr="", returncode=0, timeout=False):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.timeout = timeout
        self.killed = False
        self.calls = 0

    def communicate(self, timeout=None):
        self.calls += 1
        if self.timeout and self.calls == 1:
            raise subprocess.TimeoutExpired(
                cmd=["fake"],
                timeout=timeout,
                output="partial out",
                stderr="partial err",
            )
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True


class TestOsScriptControllerService(unittest.TestCase):
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

    def _capability(self, script_hash: str, *, status="active", timeout_ms=12000):
        return {
            "name": "verify_ollama_model",
            "contract_version": "0.1.0",
            "status": status,
            "authority_level": "read_only_network",
            "mutating": False,
            "locality": "local_network",
            "network_scope": "127.0.0.1",
            "script": {
                "kind": "powershell",
                "path": "tools/os_capabilities/verify_ollama_model.ps1",
                "sha256": script_hash,
                "timeout_ms": timeout_ms,
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

    def test_blocked_prepare_writes_ledger_without_running_script(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            registry_path = self._write_registry(
                root,
                [self._capability("", status="draft")],
            )
            ledger_path = root / "runtime" / "os_capability_ledger.jsonl"
            calls = []

            result = OS_SCRIPT_CONTROLLER_SERVICE.execute_capability(
                "verify_ollama_model",
                {},
                registry_path=registry_path,
                ledger_path=ledger_path,
                base_dir=root,
                popen_factory=lambda *a, **k: calls.append((a, k)),
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "aaa111",
            )

            rows = _read_ledger(ledger_path)

        self.assertFalse(result["ok"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["reason"], "contract_stale")
        self.assertTrue(result["operator_outbox"])
        self.assertEqual(calls, [])
        self.assertEqual(rows[0]["status"], "blocked")
        self.assertFalse(rows[0]["executed"])

    def test_successful_script_execution_records_command_and_stdout(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_hash = _write_script(root / "tools" / "os_capabilities" / "verify_ollama_model.ps1", "ok")
            registry_path = self._write_registry(root, [self._capability(script_hash)])
            ledger_path = root / "runtime" / "os_capability_ledger.jsonl"
            captured = {}

            def fake_popen(command, **kwargs):
                captured["command"] = command
                captured["kwargs"] = kwargs
                return FakeProcess(stdout='{"ok":true}', stderr="", returncode=0)

            result = OS_SCRIPT_CONTROLLER_SERVICE.execute_capability(
                "verify_ollama_model",
                {"probe_chat": True},
                registry_path=registry_path,
                ledger_path=ledger_path,
                base_dir=root,
                popen_factory=fake_popen,
                powershell_executable="pwsh-test",
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "bbb222",
            )
            rows = _read_ledger(ledger_path)

        self.assertTrue(result["ok"])
        self.assertTrue(result["executed"])
        self.assertEqual(rows[0]["status"], "success")
        self.assertEqual(rows[0]["stdout"], '{"ok":true}')
        self.assertEqual(rows[0]["args"]["base_url"], "http://127.0.0.1:11434")
        self.assertIn("-ArgsJson", captured["command"])
        self.assertEqual(captured["kwargs"]["cwd"], str(root))

    def test_invalid_args_write_operator_worthy_ledger_without_running(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_hash = _write_script(root / "tools" / "os_capabilities" / "verify_ollama_model.ps1", "ok")
            registry_path = self._write_registry(root, [self._capability(script_hash)])
            ledger_path = root / "runtime" / "os_capability_ledger.jsonl"

            result = OS_SCRIPT_CONTROLLER_SERVICE.execute_capability(
                "verify_ollama_model",
                {"base_url": "http://example.com:11434"},
                registry_path=registry_path,
                ledger_path=ledger_path,
                base_dir=root,
                popen_factory=lambda *a, **k: self.fail("script should not run"),
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "ccc333",
            )
            rows = _read_ledger(ledger_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid_args")
        self.assertTrue(result["operator_outbox"])
        self.assertEqual(rows[0]["status"], "blocked")
        self.assertIn("arg_network_scope:base_url:127.0.0.1", rows[0]["prepare"]["errors"])

    def test_timeout_kills_process_and_records_partial_output(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_hash = _write_script(root / "tools" / "os_capabilities" / "verify_ollama_model.ps1", "ok")
            registry_path = self._write_registry(root, [self._capability(script_hash, timeout_ms=5)])
            ledger_path = root / "runtime" / "os_capability_ledger.jsonl"
            process = FakeProcess(stdout="tail out", stderr="tail err", timeout=True)

            result = OS_SCRIPT_CONTROLLER_SERVICE.execute_capability(
                "verify_ollama_model",
                {},
                registry_path=registry_path,
                ledger_path=ledger_path,
                base_dir=root,
                popen_factory=lambda *a, **k: process,
                powershell_executable="pwsh-test",
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "ddd444",
            )
            rows = _read_ledger(ledger_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "timeout")
        self.assertTrue(process.killed)
        self.assertTrue(rows[0]["timed_out"])
        self.assertTrue(rows[0]["killed"])
        self.assertIn("partial out", rows[0]["stdout"])
        self.assertIn("tail out", rows[0]["stdout"])

    def test_nonzero_exit_records_failed_evidence(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_hash = _write_script(root / "tools" / "os_capabilities" / "verify_ollama_model.ps1", "ok")
            registry_path = self._write_registry(root, [self._capability(script_hash)])
            ledger_path = root / "runtime" / "os_capability_ledger.jsonl"

            result = OS_SCRIPT_CONTROLLER_SERVICE.execute_capability(
                "verify_ollama_model",
                {},
                registry_path=registry_path,
                ledger_path=ledger_path,
                base_dir=root,
                popen_factory=lambda *a, **k: FakeProcess(stdout="", stderr="bad", returncode=7),
                powershell_executable="pwsh-test",
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "eee555",
            )
            rows = _read_ledger(ledger_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "nonzero_exit")
        self.assertEqual(rows[0]["exit_code"], 7)
        self.assertEqual(rows[0]["stderr"], "bad")

    def test_json_evidence_ok_false_records_failed_evidence(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_hash = _write_script(root / "tools" / "os_capabilities" / "verify_ollama_model.ps1", "ok")
            registry_path = self._write_registry(root, [self._capability(script_hash)])
            ledger_path = root / "runtime" / "os_capability_ledger.jsonl"

            result = OS_SCRIPT_CONTROLLER_SERVICE.execute_capability(
                "verify_ollama_model",
                {},
                registry_path=registry_path,
                ledger_path=ledger_path,
                base_dir=root,
                popen_factory=lambda *a, **k: FakeProcess(
                    stdout=json.dumps({"ok": False, "errors": ["tags_probe_failed"]}),
                    stderr="",
                    returncode=0,
                ),
                powershell_executable="pwsh-test",
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "failok",
            )
            rows = _read_ledger(ledger_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "capability_evidence_not_ok")
        self.assertTrue(result["operator_outbox"])
        self.assertEqual(rows[0]["exit_code"], 0)
        self.assertTrue(rows[0]["evidence_contract"]["checked"])
        self.assertIn("evidence_ok_false", rows[0]["errors"])
        self.assertIn("tags_probe_failed", rows[0]["errors"])

    def test_execution_time_hash_drift_is_ledgered_without_running(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_path = root / "tools" / "os_capabilities" / "verify_ollama_model.ps1"
            script_hash = _write_script(script_path, "first")
            registry_path = self._write_registry(root, [self._capability(script_hash)])
            ledger_path = root / "runtime" / "os_capability_ledger.jsonl"
            script_path.write_bytes(b"drifted")

            result = OS_SCRIPT_CONTROLLER_SERVICE.execute_capability(
                "verify_ollama_model",
                {},
                registry_path=registry_path,
                ledger_path=ledger_path,
                base_dir=root,
                popen_factory=lambda *a, **k: self.fail("script should not run"),
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "fff666",
            )
            rows = _read_ledger(ledger_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "contract_stale")
        self.assertTrue(result["operator_outbox"])
        self.assertEqual(rows[0]["status"], "blocked")
        self.assertIn("sha256_mismatch", rows[0]["prepare"]["errors"])

    def test_controller_rechecks_hash_after_prepare_before_command_build(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_path = root / "tools" / "os_capabilities" / "verify_ollama_model.ps1"
            script_hash = _write_script(script_path, "first")
            registry_path = self._write_registry(root, [])
            ledger_path = root / "runtime" / "os_capability_ledger.jsonl"
            capability = self._capability(script_hash)
            capability["script"]["resolved_path"] = str(script_path)
            script_path.write_bytes(b"changed after prepare")

            class PreparedRegistry:
                def prepare_request(self, *_args, **_kwargs):
                    return {
                        "ok": True,
                        "reason": "",
                        "operator_outbox": False,
                        "capability": capability,
                        "args": {"base_url": "http://127.0.0.1:11434", "model": "llama3.2:3b", "probe_chat": False},
                        "errors": [],
                    }

                def verify_capability_hash(self, cap):
                    from services.os_capability_registry import OS_CAPABILITY_REGISTRY_SERVICE

                    return OS_CAPABILITY_REGISTRY_SERVICE.verify_capability_hash(cap)

            result = OS_SCRIPT_CONTROLLER_SERVICE.execute_capability(
                "verify_ollama_model",
                {},
                registry_path=registry_path,
                ledger_path=ledger_path,
                base_dir=root,
                registry_service=PreparedRegistry(),
                popen_factory=lambda *a, **k: self.fail("script should not run"),
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "ggg777",
            )
            rows = _read_ledger(ledger_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "contract_stale")
        self.assertEqual(rows[0]["status"], "blocked")
        self.assertIn("sha256_mismatch", rows[0]["prepare"]["execution_hash"]["errors"])

    def test_default_source_registry_executes_ollama_verifier_through_controller(self):
        with TemporaryDirectory() as td:
            ledger_path = Path(td) / "os_capability_ledger.jsonl"

            result = OS_SCRIPT_CONTROLLER_SERVICE.execute_capability(
                "verify_ollama_model",
                {"probe_chat": False},
                registry_path=OS_CAPABILITY_REGISTRY_FILE,
                ledger_path=ledger_path,
                base_dir=BASE_DIR,
                popen_factory=lambda *a, **k: FakeProcess(stdout='{"ok":true,"source":"fake"}', returncode=0),
                powershell_executable="pwsh-test",
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "hhh888",
            )
            rows = _read_ledger(ledger_path)

        self.assertTrue(result["ok"])
        self.assertEqual(rows[0]["capability"], "verify_ollama_model")
        self.assertEqual(rows[0]["status"], "success")
        self.assertEqual(rows[0]["args"]["model"], "llama3.2:3b")

    def test_authority_block_records_ledger_without_running(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_hash = _write_script(root / "tools" / "os_capabilities" / "verify_ollama_model.ps1", "ok")
            capability = self._capability(script_hash)
            capability["name"] = "restart_runtime_component"
            capability["authority_level"] = "runtime_restart"
            capability["mutating"] = True
            registry_path = self._write_registry(root, [capability])
            ledger_path = root / "runtime" / "os_capability_ledger.jsonl"

            result = OS_SCRIPT_CONTROLLER_SERVICE.execute_capability(
                "restart_runtime_component",
                {},
                registry_path=registry_path,
                ledger_path=ledger_path,
                base_dir=root,
                popen_factory=lambda *a, **k: self.fail("script should not run"),
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "iii999",
            )
            rows = _read_ledger(ledger_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "authority_blocked")
        self.assertTrue(result["operator_outbox"])
        self.assertEqual(rows[0]["status"], "blocked")
        self.assertIn("authority_level_not_allowed:runtime_restart", rows[0]["errors"])

    def test_evidence_write_verifies_reported_output_path(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_hash = _write_script(root / "tools" / "os_capabilities" / "verify_ollama_model.ps1", "ok")
            capability = self._capability(script_hash)
            capability["name"] = "collect_diagnostics_bundle"
            capability["authority_level"] = "evidence_write"
            capability["locality"] = "local_filesystem"
            capability["writes_only_to"] = "runtime/os_capability_evidence"
            capability.pop("network_scope", None)
            registry_path = self._write_registry(root, [capability])
            ledger_path = root / "runtime" / "os_capability_ledger.jsonl"
            output_path = root / "runtime" / "os_capability_evidence" / "bundle.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("{}", encoding="utf-8")

            result = OS_SCRIPT_CONTROLLER_SERVICE.execute_capability(
                "collect_diagnostics_bundle",
                {},
                registry_path=registry_path,
                ledger_path=ledger_path,
                base_dir=root,
                authority_context={
                    "allowed_authority_levels": ["evidence_write"],
                    "allow_evidence_write": True,
                },
                popen_factory=lambda *a, **k: FakeProcess(
                    stdout=json.dumps({"ok": True, "bundle_path": str(output_path), "writes": [str(output_path)]}),
                    returncode=0,
                ),
                powershell_executable="pwsh-test",
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "jjj000",
            )
            rows = _read_ledger(ledger_path)

        self.assertTrue(result["ok"])
        self.assertTrue(rows[0]["write_contract"]["checked"])
        self.assertEqual(rows[0]["write_contract"]["verified_paths"], [str(output_path)])

    def test_evidence_write_blocks_reported_path_outside_contract(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            script_hash = _write_script(root / "tools" / "os_capabilities" / "verify_ollama_model.ps1", "ok")
            capability = self._capability(script_hash)
            capability["name"] = "collect_diagnostics_bundle"
            capability["authority_level"] = "evidence_write"
            capability["locality"] = "local_filesystem"
            capability["writes_only_to"] = "runtime/os_capability_evidence"
            capability.pop("network_scope", None)
            registry_path = self._write_registry(root, [capability])
            ledger_path = root / "runtime" / "os_capability_ledger.jsonl"
            outside_path = root / "runtime" / "outside_bundle.json"
            outside_path.parent.mkdir(parents=True, exist_ok=True)
            outside_path.write_text("{}", encoding="utf-8")

            result = OS_SCRIPT_CONTROLLER_SERVICE.execute_capability(
                "collect_diagnostics_bundle",
                {},
                registry_path=registry_path,
                ledger_path=ledger_path,
                base_dir=root,
                authority_context={
                    "allowed_authority_levels": ["evidence_write"],
                    "allow_evidence_write": True,
                },
                popen_factory=lambda *a, **k: FakeProcess(
                    stdout=json.dumps({"ok": True, "bundle_path": str(outside_path), "writes": [str(outside_path)]}),
                    returncode=0,
                ),
                powershell_executable="pwsh-test",
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "kkk111",
            )
            rows = _read_ledger(ledger_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "write_contract_violation")
        self.assertTrue(result["operator_outbox"])
        self.assertIn("write_outside_allowed_root", rows[0]["write_contract"]["errors"][0])
