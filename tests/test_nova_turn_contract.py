import unittest
from unittest import mock

from services.nova_turn_contract import (
    bind_turn_request,
    maybe_run_attachment_vision_turn,
    normalize_input_source,
)


class TestNovaTurnContract(unittest.TestCase):
    def test_bind_turn_request_normalizes_cli_voice_sources(self):
        turn = bind_turn_request(text="hello", channel="cli", input_source="")
        self.assertEqual(turn.channel, "cli")
        self.assertEqual(turn.input_source, "typed")
        self.assertEqual(turn.work_tree_seed_source, "cli")

        self.assertEqual(normalize_input_source("", channel="voice"), "voice")

    def test_attachment_vision_runs_for_staged_image(self):
        traces = []

        class _Core:
            def execute_planned_action(self, tool, args):
                self.tool = tool
                self.args = args
                return "A laptop on a desk."

        core = _Core()
        reply, meta = maybe_run_attachment_vision_turn(
            text="what do you see?",
            attachments=[
                {
                    "name": "desk.png",
                    "path": r"C:\nova\runtime\leah_uploads\desk.png",
                    "mime": "image/png",
                    "source": "upload",
                }
            ],
            core=core,
            trace=lambda stage, outcome, detail="", **data: traces.append((stage, outcome)),
            normalize_reply=lambda value: value,
        )

        self.assertEqual(reply, "A laptop on a desk.")
        self.assertEqual(meta.get("tool"), "vision")
        self.assertTrue(meta.get("grounded"))
        self.assertEqual(core.tool, "vision")
        self.assertEqual(core.args.get("action"), "describe_file")
        self.assertEqual(traces[0], ("attachment_vision", "started"))

    def test_attachment_vision_rejects_failure_strings(self):
        class _Core:
            def execute_planned_action(self, tool, args):
                return "filesystem tool failed: permission denied"

        reply, meta = maybe_run_attachment_vision_turn(
            text="what do you see?",
            attachments=[{"path": r"C:\nova\desk.png", "mime": "image/png"}],
            core=_Core(),
            trace=lambda *_args, **_kwargs: None,
            normalize_reply=lambda value: value,
        )

        self.assertIn("Vision could not analyze", reply)
        self.assertFalse(meta.get("grounded"))

    def test_attachment_vision_skips_without_vision_intent(self):
        outcome = maybe_run_attachment_vision_turn(
            text="thanks",
            attachments=[{"path": r"C:\nova\desk.png", "mime": "image/png"}],
            core=mock.Mock(),
            trace=lambda *_args, **_kwargs: None,
            normalize_reply=lambda value: value,
        )
        self.assertIsNone(outcome)


if __name__ == "__main__":
    unittest.main()