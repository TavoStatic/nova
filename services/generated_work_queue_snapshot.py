from __future__ import annotations

from pathlib import Path

from services.nova_runtime_context import BASE_DIR
from services.nova_runtime_context import RUNTIME_DIR
from services.test_session_control import TEST_SESSION_CONTROL_SERVICE


def generated_work_queue_payload(
    limit: int = 24,
    *,
    base_dir: Path | None = None,
    runtime_dir: Path | None = None,
) -> dict:
    effective_base = Path(base_dir or BASE_DIR)
    effective_runtime = Path(runtime_dir or RUNTIME_DIR)
    definition_roots = TEST_SESSION_CONTROL_SERVICE.all_test_session_definition_roots(
        base_dir=effective_base,
        runtime_dir=effective_runtime,
    )
    definitions = TEST_SESSION_CONTROL_SERVICE.available_test_session_definitions(
        definition_roots,
        limit=500,
    )
    reports = TEST_SESSION_CONTROL_SERVICE.test_session_report_summaries(
        TEST_SESSION_CONTROL_SERVICE.test_sessions_root(effective_runtime),
        limit=max(200, len(definitions) * 2),
    )
    return TEST_SESSION_CONTROL_SERVICE.generated_work_queue(
        definitions,
        reports,
        limit=int(limit or 24),
        runtime_dir=effective_runtime,
    )
