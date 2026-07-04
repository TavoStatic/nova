from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.memory_adapter import MemoryAdapterService
from services.memory_health import build_memory_health_payload
from services.memory_retention import apply_memory_hygiene, evaluate_contamination, parse_retention_policy
from services.nova_memory_learning import mem_add


def _create_db(path: Path, rows: list[tuple[str, str, str]]) -> None:
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
        for index, (kind, source, text) in enumerate(rows):
            con.execute(
                "INSERT INTO memories(ts, kind, source, user, scope, text, vec) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (1000 + index, kind, source, "gus", "shared", text, b"vec"),
            )
        con.commit()
    finally:
        con.close()


class TestMemoryRetentionService(unittest.TestCase):
    def test_parse_retention_policy_defaults(self) -> None:
        policy = parse_retention_policy({})
        self.assertIn("chat_user", policy["ephemeral_kinds"])
        self.assertIn("chat_user", policy["store_blocked_kinds"])

    def test_evaluate_contamination_flags_chat_user_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "nova_memory.sqlite"
            _create_db(
                db_path,
                [
                    ("fact", "pinned", "developer favorite color is blue"),
                    ("chat_user", "typed", "why are you lying about the webui"),
                    ("chat_user", "voice", "where is the proof"),
                ],
            )
            payload = evaluate_contamination(db_path)
            self.assertTrue(payload["contaminated"])
            self.assertEqual(payload["ephemeral_rows"], 2)
            self.assertEqual(payload["total"], 3)

    def test_apply_memory_hygiene_dry_run_then_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "nova_memory.sqlite"
            audit_path = Path(tmp) / "runtime" / "memory_hygiene_audit.jsonl"
            _create_db(
                db_path,
                [
                    ("identity", "typed", "learned_fact: developer_name=Gus"),
                    ("chat_user", "typed", "webui is failing again"),
                ],
            )
            policy = parse_retention_policy({"retention": {"ephemeral_kinds": ["chat_user"]}})

            dry = apply_memory_hygiene(db_path, retention_policy=policy, dry_run=True, audit_log_path=audit_path)
            self.assertEqual(dry["status"], "dry_run")
            self.assertEqual(dry["deleted_rows"], 1)
            count_con = sqlite3.connect(db_path)
            try:
                remaining = int(count_con.execute("SELECT COUNT(*) FROM memories").fetchone()[0])
            finally:
                count_con.close()
            self.assertEqual(remaining, 2)

            applied = apply_memory_hygiene(db_path, retention_policy=policy, dry_run=False, audit_log_path=audit_path)
            self.assertEqual(applied["status"], "applied")
            self.assertEqual(applied["deleted_rows"], 1)
            self.assertEqual(applied["remaining_total"], 1)
            self.assertTrue(audit_path.exists())

    def test_memory_health_reports_contamination_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "nova_memory.sqlite"
            _create_db(db_path, [("chat_user", "typed", "truth fight transcript line")])

            payload = build_memory_health_payload(
                memory_db_path=db_path,
                learned_facts_file=root / "memory" / "learned_facts.json",
                identity_file=root / "memory" / "identity.json",
                memory_retention_policy=parse_retention_policy({}),
                now_fn=lambda: 1.0,
            )
            codes = {item["code"] for item in payload["issues"]}
            self.assertIn("memory_ephemeral_contamination", codes)
            self.assertTrue(payload["retention"]["contaminated"])

    def test_mem_add_blocks_chat_user_kind(self) -> None:
        events: list[dict] = []

        class _MemoryMod:
            def recall_explain(self, *_args, **_kwargs):
                return {"results": []}

            def add_memory(self, *_args, **_kwargs):
                raise AssertionError("chat_user should not be stored")

        svc = MemoryAdapterService(
            policy_memory_getter=lambda: {
                "enabled": True,
                "scope": "hybrid",
                "retention": {"store_blocked_kinds": ["chat_user"]},
            },
            active_user_getter=lambda: "gus",
        )

        mem_add(
            "chat_user",
            "typed",
            "this should never be stored in sqlite",
            mem_enabled_fn=lambda: True,
            identity_memory_text_allowed_fn=lambda _kind, _text: True,
            record_memory_event_fn=lambda action, status, **kwargs: events.append(
                {"action": action, "status": status, **kwargs}
            ),
            mem_scope_fn=lambda: "hybrid",
            memory_should_keep_text_fn=svc.memory_should_keep_text,
            memory_kind_store_allowed_fn=svc.memory_kind_store_allowed,
            memory_write_user_fn=lambda: "gus",
            memory_mod=_MemoryMod(),
            mem_min_score_fn=lambda: 0.18,
            python_path="python",
            base_dir=Path("."),
        )
        self.assertEqual(events[-1]["reason"], "policy_blocked_kind")


if __name__ == "__main__":
    unittest.main()