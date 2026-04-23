import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from services.operator_control import OPERATOR_CONTROL_SERVICE


class TestOperatorControlService(unittest.TestCase):
    def test_operator_asset_paths_resolve_from_base_dir(self):
        base_dir = Path("c:/Nova")

        self.assertEqual(
            OPERATOR_CONTROL_SERVICE.operator_macros_path(base_dir),
            base_dir / "operator_macros.json",
        )
        self.assertEqual(
            OPERATOR_CONTROL_SERVICE.backend_command_deck_path(base_dir),
            base_dir / "backend_command_deck.json",
        )

    def test_load_operator_macros_and_resolve(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "operator_macros.json"
            path.write_text(
                json.dumps(
                    {
                        "macros": [
                            {
                                "macro_id": "inspect-runtime",
                                "label": "Inspect Runtime",
                                "prompt_template": "Inspect {focus}.",
                                "placeholders": [{"name": "focus", "required": True}],
                            }
                        ]
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            macros = OPERATOR_CONTROL_SERVICE.load_operator_macros(path, limit=10)
            resolved = OPERATOR_CONTROL_SERVICE.resolve_operator_macro("inspect-runtime", macros)

        self.assertEqual(len(macros), 1)
        self.assertEqual((resolved or {}).get("macro_id"), "inspect-runtime")

    def test_render_operator_macro_prompt_applies_defaults_and_note(self):
        ok, message, values = OPERATOR_CONTROL_SERVICE.render_operator_macro_prompt(
            {
                "prompt_template": "Inspect {focus_area} with a {detail_level} report.",
                "placeholders": [
                    {"name": "focus_area", "required": True},
                    {"name": "detail_level", "default": "concise"},
                ],
            },
            {"focus_area": "restart pressure"},
            note="include restart pressure",
        )

        self.assertTrue(ok)
        self.assertEqual(values, {"focus_area": "restart pressure", "detail_level": "concise"})
        self.assertIn("Inspect restart pressure with a concise report.", message)
        self.assertIn("Operator note: include restart pressure", message)

    def test_load_backend_commands_and_parse_dynamic_args(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "backend_command_deck.json"
            path.write_text(
                json.dumps(
                    {
                        "commands": [
                            {
                                "command_id": "regression_gate",
                                "label": "Run Regression Gate",
                                "kind": "python_module",
                                "entry": "tests.runner",
                                "allow_dynamic_args": True,
                            }
                        ]
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            commands = OPERATOR_CONTROL_SERVICE.load_backend_commands(path, limit=10)
            args = OPERATOR_CONTROL_SERVICE.parse_backend_dynamic_args('--flag "two words"')

        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0].get("command_id"), "regression_gate")
        self.assertEqual(args, ["--flag", "two words"])

    def test_run_backend_command_executes_python_module(self):
        captured = {}

        def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
            captured["cmd"] = cmd
            captured["cwd"] = cwd
            captured["timeout"] = timeout
            return SimpleNamespace(returncode=0, stdout="all good", stderr="")

        ok, msg, extra = OPERATOR_CONTROL_SERVICE.run_backend_command(
            "regression_gate",
            {"args": ["--fast"]},
            commands=[
                {
                    "command_id": "regression_gate",
                    "kind": "python_module",
                    "entry": "tests.runner",
                    "args": [],
                    "allow_dynamic_args": True,
                    "enabled": True,
                    "timeout_sec": 90,
                }
            ],
            python_bin=Path("c:/Nova/.venv/Scripts/python.exe"),
            base_dir=Path("c:/Nova"),
            subprocess_run=fake_run,
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "backend_command_ok:regression_gate")
        self.assertEqual(Path(captured["cmd"][0]), Path("c:/Nova/.venv/Scripts/python.exe"))
        self.assertEqual(captured["cmd"][1:], ["-m", "tests.runner", "--fast"])
        self.assertEqual(extra.get("output"), "all good")

    def test_backend_command_run_action_requires_command(self):
        ok, msg, extra, detail = OPERATOR_CONTROL_SERVICE.backend_command_run_action(
            {},
            load_backend_commands_fn=lambda _limit: [{"command_id": "regression_gate"}],
            run_backend_command_fn=lambda _command_id, _payload: (True, "ignored", {}),
        )

        self.assertFalse(ok)
        self.assertEqual(msg, "backend_command_required")
        self.assertEqual(detail, "backend_command_required")
        self.assertEqual((extra.get("available_commands") or [])[0].get("command_id"), "regression_gate")

    def test_operator_prompt_action_renders_macro_and_returns_session(self):
        macro = {
            "macro_id": "inspect-runtime",
            "prompt_template": "Inspect {focus_area}.",
            "placeholders": [{"name": "focus_area", "required": True}],
        }
        summary = {"session_id": "operator-abc123", "turn_count": 2}

        ok, msg, extra, detail, audit_payload = OPERATOR_CONTROL_SERVICE.operator_prompt_action(
            {
                "macro": "inspect-runtime",
                "session_id": "operator-abc123",
                "message": "include restart pressure",
                "macro_values": {"focus_area": "restart pressure"},
                "source": "cli",
            },
            resolve_operator_macro_fn=lambda _macro_id: macro,
            render_operator_macro_prompt_fn=OPERATOR_CONTROL_SERVICE.render_operator_macro_prompt,
            load_operator_macros_fn=lambda _limit: [macro],
            normalize_user_id_fn=lambda value: value.strip().lower(),
            assert_session_owner_fn=lambda _session_id, _user_id, allow_bind=True: (True, "owner_bound"),
            process_chat_fn=lambda _session_id, message, user_id=None: f"reply:{message}:{user_id}",
            session_summaries_fn=lambda _limit: [summary],
            token_hex_fn=lambda _size: "abc123",
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "operator_prompt_ok")
        self.assertEqual(detail, "operator_prompt_ok:operator-abc123")
        self.assertEqual(audit_payload.get("operator_mode"), "macro")
        self.assertEqual((extra.get("session") or {}).get("turn_count"), 2)
        self.assertIn("Inspect restart pressure.", extra.get("reply"))


if __name__ == "__main__":
    unittest.main()