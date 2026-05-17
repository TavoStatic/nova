"""
Root conftest for the active source test tree.

Default run: pytest -q or pytest tests -q
Authoritative: pytest tests/authoritative -q
Legacy only: pytest tests/legacy -q
Runtime live only: pytest tests/runtime -q
"""

collect_ignore_glob = ["tests/legacy/*", "tests/runtime/*"]
