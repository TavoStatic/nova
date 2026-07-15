import tempfile
import unittest
from pathlib import Path

from services.nova_cli_session import (
    CLI_SESSION_ID,
    load_cli_session_turns,
    persist_cli_session_turns,
)


class TestNovaCliSession(unittest.TestCase):
    def test_persist_and_reload_cli_session_turns(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            persist_cli_session_turns(
                [("user", "hello"), ("assistant", "world")],
                runtime_root=runtime_root,
                owner="gus",
            )
            loaded = load_cli_session_turns(runtime_root=runtime_root)

        self.assertEqual(loaded, [("user", "hello"), ("assistant", "world")])

    def test_load_returns_empty_when_store_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            loaded = load_cli_session_turns(runtime_root=Path(td))
        self.assertEqual(loaded, [])

    def test_cli_session_id_is_stable(self) -> None:
        self.assertEqual(CLI_SESSION_ID, "cli")


if __name__ == "__main__":
    unittest.main()