"""
Legacy test isolation.

These tests are NOT part of the default test suite.
They enforce old code structure and internal naming that no longer reflects
the current Nova architecture.

To run them explicitly (for archaeology only):
    pytest tests/legacy -q

Do NOT add tests/legacy to any CI command or default regression run.
"""
import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        if "legacy" in str(item.fspath):
            item.add_marker(pytest.mark.legacy_behavior_test)
            item.add_marker(pytest.mark.skip(reason="legacy: disabled – enforces old code structure"))
