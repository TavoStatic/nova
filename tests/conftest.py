"""
Root conftest — excludes tests/legacy from default collection.

Default run:  pytest tests/ -q       -> legacy folder skipped
Authoritative: pytest tests/authoritative -q  -> cleanest, forward-only
Legacy only:  pytest tests/legacy -q  -> explicitly opt-in

To add the collect_ignore, we also add a pytest.ini-compatible config
via pyproject or directly via this conftest.
"""
collect_ignore_glob = ["tests/legacy/*", "tests/runtime/*"]
