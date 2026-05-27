import unittest

import http_chat_flow


class TestHttpChatFlow(unittest.TestCase):
    def test_prepare_chat_turn_appends_user_text_without_route_rewrite(self):
        ledger = {"turn_acts": ["stale"]}
        out = http_chat_flow.prepare_chat_turn(
            session_id="s1",
            text="hi nova",
            session=object(),
            ledger=ledger,
            append_session_turn=lambda sid, role, text: [(role, text)],
        )

        self.assertEqual(out.get("turns"), [("user", "hi nova")])
        self.assertEqual(out.get("routed_text"), "hi nova")
        self.assertEqual(out.get("turn_acts"), [])
        self.assertEqual(ledger, {"turn_acts": ["stale"]})

    def test_resume_requires_session_id(self):
        out = http_chat_flow.resume_last_pending_turn(
            "",
            "",
            get_active_user=lambda: "",
            set_active_user=lambda _value: None,
            get_last_session_turn=lambda _sid: None,
            get_session_turns=lambda _sid: [],
            generate_chat_reply=lambda turns, text: ("ok", {}),
            append_session_turn=lambda sid, role, text: [],
        )

        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "session_id_required")

    def test_resume_no_turns(self):
        out = http_chat_flow.resume_last_pending_turn(
            "s1",
            "gus",
            get_active_user=lambda: "gus",
            set_active_user=lambda _value: None,
            get_last_session_turn=lambda _sid: None,
            get_session_turns=lambda _sid: [],
            generate_chat_reply=lambda turns, text: ("ok", {}),
            append_session_turn=lambda sid, role, text: [],
        )

        self.assertTrue(out.get("ok"))
        self.assertFalse(out.get("resumed"))
        self.assertEqual(out.get("reason"), "no_turns")

    def test_resume_no_pending_user_turn(self):
        out = http_chat_flow.resume_last_pending_turn(
            "s1",
            "gus",
            get_active_user=lambda: "gus",
            set_active_user=lambda _value: None,
            get_last_session_turn=lambda _sid: ("assistant", "done"),
            get_session_turns=lambda _sid: [("assistant", "done")],
            generate_chat_reply=lambda turns, text: ("ok", {}),
            append_session_turn=lambda sid, role, text: [],
        )

        self.assertTrue(out.get("ok"))
        self.assertFalse(out.get("resumed"))
        self.assertEqual(out.get("reason"), "no_pending_user_turn")

    def test_resume_success(self):
        added = []
        active = {"value": "old"}
        invalidations = []

        def _set(value):
            active["value"] = value

        out = http_chat_flow.resume_last_pending_turn(
            "s1",
            "gus",
            get_active_user=lambda: active["value"],
            set_active_user=_set,
            get_last_session_turn=lambda _sid: ("user", "hello"),
            get_session_turns=lambda _sid: [("user", "hello")],
            generate_chat_reply=lambda turns, text: ("reply", {}),
            append_session_turn=lambda sid, role, text: added.append((sid, role, text)) or [],
            invalidate_control_status_cache=lambda: invalidations.append("called"),
        )

        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("resumed"))
        self.assertEqual(out.get("reply"), "reply")
        self.assertEqual(added, [("s1", "assistant", "reply")])
        self.assertEqual(invalidations, ["called"])
        self.assertEqual(active["value"], "old")

    def test_resume_success_from_runtime_scope(self):
        added = []
        active = {"value": "old"}
        invalidations = []

        def _set(value):
            active["value"] = value

        out = http_chat_flow.resume_last_pending_turn_from_runtime(
            "s1",
            "gus",
            runtime_scope={
                "nova_core": type(
                    "CoreStub",
                    (),
                    {
                        "get_active_user": staticmethod(lambda: active["value"]),
                        "set_active_user": staticmethod(_set),
                    },
                )(),
                "_get_last_session_turn": lambda _sid: ("user", "hello"),
                "_get_session_turns": lambda _sid: [("user", "hello")],
                "_generate_chat_reply": lambda turns, text: ("reply", {}),
                "_append_session_turn": lambda sid, role, text: added.append((sid, role, text)) or [],
                "_invalidate_control_status_cache": lambda: invalidations.append("called"),
            },
        )

        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("resumed"))
        self.assertEqual(out.get("reply"), "reply")
        self.assertEqual(added, [("s1", "assistant", "reply")])
        self.assertEqual(invalidations, ["called"])
        self.assertEqual(active["value"], "old")


if __name__ == "__main__":
    unittest.main()
