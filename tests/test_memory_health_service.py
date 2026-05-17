from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.memory_health import build_memory_health_payload
from services.memory_bootstrap_origin import default_pending_origin_contract, write_origin_contract
from services.nova_memory_learning import load_learned_facts, save_learned_facts


def _create_memory_db(path: Path, count: int) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute(
            """
            CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                user TEXT DEFAULT '',
                scope TEXT DEFAULT 'shared',
                text TEXT NOT NULL,
                vec BLOB NOT NULL
            )
            """
        )
        for index in range(count):
            con.execute(
                "INSERT INTO memories(ts, kind, source, user, scope, text, vec) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (1000 + index, "fact", "typed", "gus", "shared", f"memory {index}", b"vec"),
            )
        con.commit()
    finally:
        con.close()


class TestMemoryHealthService(unittest.TestCase):
    def test_memory_health_flags_orphan_learned_facts_tmp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "nova_memory.sqlite"
            _create_memory_db(db_path, 3)
            learned = root / "memory" / "learned_facts.json"
            identity = root / "memory" / "identity.json"
            learned.parent.mkdir(parents=True)
            learned.with_suffix(".json.tmp").write_text('{"assistant_name":"Novaprime"}', encoding="utf-8")

            payload = build_memory_health_payload(
                memory_db_path=db_path,
                learned_facts_file=learned,
                identity_file=identity,
                now_fn=lambda: 123.0,
            )

            self.assertEqual(payload["status"], "watch")
            self.assertFalse(payload["ok"])
            codes = {item["code"] for item in payload["issues"]}
            self.assertIn("learned_facts_orphan_tmp", codes)
            self.assertEqual(payload["memory_db"]["total"], 3)

    def test_memory_health_preserves_last_good_count_on_drop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "nova_memory.sqlite"
            _create_memory_db(db_path, 2)
            snapshot = root / "runtime" / "memory_health_snapshot.json"
            snapshot.parent.mkdir(parents=True)
            snapshot.write_text(json.dumps({"last_good_total": 10}), encoding="utf-8")

            payload = build_memory_health_payload(
                memory_db_path=db_path,
                learned_facts_file=root / "memory" / "learned_facts.json",
                identity_file=root / "memory" / "identity.json",
                snapshot_file=snapshot,
                update_snapshot=True,
                now_fn=lambda: 456.0,
            )

            self.assertEqual(payload["status"], "failure")
            self.assertEqual(payload["snapshot"]["count_drop"], 8)
            self.assertEqual(json.loads(snapshot.read_text(encoding="utf-8"))["last_good_total"], 10)

    def test_learned_facts_loader_recovers_from_valid_tmp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory_dir = root / "memory"
            learned = memory_dir / "learned_facts.json"
            memory_dir.mkdir()
            learned.with_suffix(".json.tmp").write_text(
                json.dumps({"assistant_name": "Novaprime", "updated_at": "2026-04-21 20:09:42"}),
                encoding="utf-8",
            )

            facts = load_learned_facts(
                learned_facts_file=learned,
                save_learned_facts_fn=lambda data: save_learned_facts(data, memory_dir=memory_dir, learned_facts_file=learned),
            )

            self.assertEqual(facts["assistant_name"], "Novaprime")
            self.assertTrue(learned.exists())

    def test_memory_health_flags_invalid_recent_memory_event_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "nova_memory.sqlite"
            _create_memory_db(db_path, 3)
            events_log = root / "runtime" / "memory_events.jsonl"
            events_log.parent.mkdir(parents=True)
            events_log.write_text(
                '{"action":"add","status":"ok","ts":1000}\nnot-json\n',
                encoding="utf-8",
            )

            payload = build_memory_health_payload(
                memory_db_path=db_path,
                learned_facts_file=root / "memory" / "learned_facts.json",
                identity_file=root / "memory" / "identity.json",
                memory_events_log=events_log,
                now_fn=lambda: 789.0,
            )

            self.assertEqual(payload["status"], "watch")
            self.assertEqual(payload["memory_events_log"]["invalid_tail_count"], 1)
            codes = {item["code"] for item in payload["issues"]}
            sources = {item["source"] for item in payload["issues"]}
            self.assertIn("memory_events_jsonl_tail_invalid", codes)
            self.assertIn("memory_events_log", sources)

    def test_memory_health_names_missing_bootstrap_when_memory_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "nova_memory.sqlite"
            _create_memory_db(db_path, 0)

            payload = build_memory_health_payload(
                memory_db_path=db_path,
                learned_facts_file=root / "memory" / "learned_facts.json",
                identity_file=root / "memory" / "identity.json",
                memory_enabled=True,
                now_fn=lambda: 987.0,
            )

            self.assertEqual(payload["status"], "watch")
            self.assertEqual(payload["bootstrap"]["status"], "incomplete")
            self.assertEqual(set(payload["bootstrap"]["missing"]), {"learned_facts", "identity"})
            codes = {item["code"] for item in payload["issues"]}
            self.assertIn("learned_facts_missing", codes)
            self.assertIn("identity_missing", codes)

    def test_memory_health_distinguishes_pending_bootstrap_origin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "nova_memory.sqlite"
            _create_memory_db(db_path, 0)
            origin = root / "memory" / "bootstrap_origin.json"
            write_origin_contract(origin, default_pending_origin_contract(now_fn=lambda: 123.0))

            payload = build_memory_health_payload(
                memory_db_path=db_path,
                learned_facts_file=root / "memory" / "learned_facts.json",
                identity_file=root / "memory" / "identity.json",
                bootstrap_origin_file=origin,
                memory_enabled=True,
                now_fn=lambda: 987.0,
            )

            self.assertEqual(payload["bootstrap"]["status"], "waiting_for_origin_confirmation")
            self.assertEqual(payload["bootstrap"]["origin_status"], "pending_operator_confirmation")
            codes = {item["code"] for item in payload["issues"]}
            self.assertIn("memory_bootstrap_origin_pending", codes)
            self.assertIn("identity_missing", codes)


if __name__ == "__main__":
    unittest.main()
