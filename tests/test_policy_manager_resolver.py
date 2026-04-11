import json
import tempfile
import unittest
from pathlib import Path

import nova_core


class TestPolicyManagerResolver(unittest.TestCase):
    def setUp(self):
        self.orig_policy_path = nova_core.POLICY_PATH
        self.orig_policy_audit = nova_core.POLICY_AUDIT_LOG

    def tearDown(self):
        nova_core.POLICY_PATH = self.orig_policy_path
        nova_core.POLICY_AUDIT_LOG = self.orig_policy_audit

    def test_load_policy_uses_current_policy_path_each_call(self):
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            p1 = Path(td1) / "policy.json"
            p2 = Path(td2) / "policy.json"
            p1.write_text(json.dumps({"models": {"chat": "alpha"}}, ensure_ascii=True), encoding="utf-8")
            p2.write_text(json.dumps({"models": {"chat": "beta"}}, ensure_ascii=True), encoding="utf-8")

            nova_core.POLICY_PATH = p1
            nova_core.POLICY_AUDIT_LOG = Path(td1) / "policy_changes.jsonl"
            self.assertEqual(nova_core.load_policy().get("models", {}).get("chat"), "alpha")

            nova_core.POLICY_PATH = p2
            nova_core.POLICY_AUDIT_LOG = Path(td2) / "policy_changes.jsonl"
            self.assertEqual(nova_core.load_policy().get("models", {}).get("chat"), "beta")


if __name__ == "__main__":
    unittest.main()
