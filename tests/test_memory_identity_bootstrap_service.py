from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.memory_bootstrap_origin import confirm_origin_contract
from services.memory_bootstrap_origin import default_pending_origin_contract
from services.memory_bootstrap_origin import write_origin_contract
from services.memory_bootstrap_judgment import build_memory_bootstrap_judgment
from services.memory_identity_bootstrap import apply_identity_bootstrap


class TestMemoryIdentityBootstrapService(unittest.TestCase):
    def test_confirmed_origin_contract_allows_identity_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            origin = root / "memory" / "bootstrap_origin.json"
            write_origin_contract(origin, default_pending_origin_contract(now_fn=lambda: 100.0))

            contract = confirm_origin_contract(
                origin,
                {
                    "assistant_name": "Nova",
                    "developer_name": "Gustavo Uribe",
                    "developer_nickname": "Gus",
                },
                confirmed_by="operator",
                now_fn=lambda: 123.0,
            )

            self.assertEqual(contract["status"], "ready")
            self.assertEqual(contract["authority"], "operator_confirmed")
            self.assertTrue(contract["may_seed_identity_facts"])
            values = {
                row["key"]: row.get("value")
                for row in list(contract.get("required_slots") or [])
            }
            self.assertEqual(values["assistant_name"], "Nova")
            self.assertEqual(values["developer_name"], "Gustavo Uribe")
            self.assertEqual(values["developer_nickname"], "Gus")

    def test_apply_identity_bootstrap_writes_identity_and_learned_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory_dir = root / "memory"
            origin = memory_dir / "bootstrap_origin.json"
            identity = memory_dir / "identity.json"
            learned = memory_dir / "learned_facts.json"
            write_origin_contract(origin, default_pending_origin_contract(now_fn=lambda: 100.0))
            contract = confirm_origin_contract(
                origin,
                {
                    "assistant_name": "Nova",
                    "developer_name": "Gustavo Uribe",
                    "developer_nickname": "Gus",
                },
                confirmed_by="operator",
                now_fn=lambda: 123.0,
            )
            events = []
            memory_rows = []

            def load_json(path: Path) -> dict:
                return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

            def save_json(path: Path, data: dict) -> None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")

            result = apply_identity_bootstrap(
                origin_contract=contract,
                identity_file=identity,
                learned_facts_file=learned,
                load_identity_profile_fn=lambda: load_json(identity),
                save_identity_profile_fn=lambda data: save_json(identity, data),
                load_learned_facts_fn=lambda: load_json(learned),
                save_learned_facts_fn=lambda data: save_json(learned, data),
                mem_add_fn=lambda kind, source, text: memory_rows.append((kind, source, text)),
                record_memory_event_fn=lambda action, status, **kwargs: events.append((action, status, kwargs)),
                now_fn=lambda: 200.0,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "applied")
            learned_payload = load_json(learned)
            identity_payload = load_json(identity)
            self.assertEqual(learned_payload["assistant_name"], "Nova")
            self.assertEqual(learned_payload["developer_name"], "Gustavo Uribe")
            self.assertEqual(learned_payload["developer_nickname"], "Gus")
            self.assertEqual(identity_payload["developer"]["nickname"], "Gus")
            self.assertEqual(len(memory_rows), 3)
            self.assertIn(("identity_bootstrap", "ok"), [(item[0], item[1]) for item in events])

    def test_ready_memory_bootstrap_judgment_does_not_repeat_blocked_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory_dir = root / "memory"
            identity = memory_dir / "identity.json"
            learned = memory_dir / "learned_facts.json"
            events = root / "runtime" / "memory_events.jsonl"
            identity.parent.mkdir(parents=True)
            events.parent.mkdir(parents=True)
            identity.write_text("{}", encoding="utf-8")
            learned.write_text("{}", encoding="utf-8")
            events.write_text('{"action":"identity_bootstrap","status":"ok"}\n', encoding="utf-8")

            judgment = build_memory_bootstrap_judgment(
                memory_enabled=True,
                memory_health={
                    "status": "ok",
                    "issues": [],
                    "bootstrap": {"missing": [], "origin_status": "ready"},
                    "bootstrap_origin": {
                        "status": "ready",
                        "authority": "operator_confirmed",
                        "pending_slots": [],
                        "may_seed_identity_facts": True,
                    },
                },
                identity_file=identity,
                learned_facts_file=learned,
                memory_events_log=events,
                branch_payload={},
                evidence_rows=[],
            )

            self.assertEqual(judgment["classification"], "ready")
            self.assertEqual(judgment["verdict"], "ready")
            self.assertIn("No memory bootstrap action is open", judgment["next_work"][0])


if __name__ == "__main__":
    unittest.main()
