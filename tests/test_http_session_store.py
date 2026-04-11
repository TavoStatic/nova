import tempfile
import unittest
from pathlib import Path

import http_session_store


class _FakeSession:
    def __init__(self):
        self.pending_action = {"kind": "demo"}
        self.pending_correction_target = "target"
        self.continuation_used_last_turn = True
        self.last_reflection = {"reply_contract": "demo.reply"}

    def active_subject(self):
        return "subject"

    def state_kind(self):
        return "kind"

    def reflection_summary(self):
        return {"active_subject": "subject", "continuation_used": True, "overrides_active": []}


class _FakeStateManager:
    def __init__(self):
        self.sessions = {}
        self.dropped = []

    def peek(self, sid):
        return self.sessions.get(sid)

    def drop(self, sid):
        self.dropped.append(sid)
        self.sessions.pop(sid, None)


class TestHttpSessionStore(unittest.TestCase):
    def test_trim_turns_caps_history(self):
        turns = [("user", str(i)) for i in range(10)]
        http_session_store.trim_turns(turns, max_turns=2)
        self.assertEqual(len(turns), 4)
        self.assertEqual(turns[0][1], "6")

    def test_append_and_get_turns(self):
        session_turns = {}
        persisted = []
        turns = http_session_store.append_session_turn(
            "s1",
            "user",
            "hello",
            session_turns=session_turns,
            max_turns=10,
            persist_callback=lambda: persisted.append(True),
        )
        self.assertEqual(turns, [("user", "hello")])
        self.assertEqual(http_session_store.get_session_turns("s1", session_turns=session_turns), [("user", "hello")])
        self.assertEqual(http_session_store.get_last_session_turn("s1", session_turns=session_turns), ("user", "hello"))
        self.assertEqual(len(persisted), 1)

    def test_session_summaries(self):
        state_manager = _FakeStateManager()
        state_manager.sessions["s1"] = _FakeSession()
        summaries = http_session_store.session_summaries(
            session_turns={"s1": [("user", "hello there"), ("assistant", "hi back")]},
            session_owners={"s1": "gus"},
            state_manager=state_manager,
            limit=10,
        )
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["session_id"], "s1")
        self.assertEqual(summaries[0]["owner"], "gus")
        self.assertEqual(summaries[0]["state"]["active_subject"], "subject")

    def test_delete_session(self):
        session_turns = {"s1": [("user", "hello")]}
        session_owners = {"s1": "gus"}
        state_manager = _FakeStateManager()
        state_manager.sessions["s1"] = _FakeSession()
        persisted = []
        ended = []
        ok, msg = http_session_store.delete_session(
            "s1",
            session_turns=session_turns,
            session_owners=session_owners,
            state_manager=state_manager,
            persist_callback=lambda: persisted.append(True),
            on_session_end=lambda sid, session: ended.append((sid, session.last_reflection)),
        )
        self.assertTrue(ok)
        self.assertEqual(msg, "session_deleted")
        self.assertEqual(session_turns, {})
        self.assertEqual(session_owners, {})
        self.assertEqual(state_manager.dropped, ["s1"])
        self.assertEqual(len(persisted), 1)
        self.assertEqual(ended[0][0], "s1")

    def test_assert_session_owner(self):
        session_owners = {}
        persisted = []
        ok, msg = http_session_store.assert_session_owner(
            "s1",
            "gus",
            session_owners=session_owners,
            normalize_user_id=lambda value: str(value).strip().lower(),
            persist_callback=lambda: persisted.append(True),
            allow_bind=True,
        )
        self.assertTrue(ok)
        self.assertEqual(msg, "owner_bound")
        self.assertEqual(session_owners["s1"], "gus")

        ok, msg = http_session_store.assert_session_owner(
            "s1",
            "other",
            session_owners=session_owners,
            normalize_user_id=lambda value: str(value).strip().lower(),
            persist_callback=lambda: persisted.append(True),
            allow_bind=True,
        )
        self.assertFalse(ok)
        self.assertEqual(msg, "session_owner_mismatch")

    def test_persist_and_load_sessions(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            store_path = runtime_dir / "http_chat_sessions.json"
            session_turns = {"s1": [("user", "hello"), ("assistant", "hi")]}
            session_owners = {"s1": "gus"}
            http_session_store.persist_sessions(
                runtime_dir=runtime_dir,
                store_path=store_path,
                session_turns=session_turns,
                session_owners=session_owners,
                max_stored_sessions=120,
                max_stored_turns_per_session=10,
            )
            loaded_turns = {}
            loaded_owners = {}
            http_session_store.load_persisted_sessions(
                store_path=store_path,
                session_turns=loaded_turns,
                session_owners=loaded_owners,
                max_stored_turns_per_session=10,
            )
            self.assertEqual(loaded_turns["s1"], [("user", "hello"), ("assistant", "hi")])
            self.assertEqual(loaded_owners["s1"], "gus")


if __name__ == "__main__":
    unittest.main()
