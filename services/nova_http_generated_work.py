from __future__ import annotations

from typing import Any, Callable, Mapping


class NovaHttpGeneratedWorkService:
    """Bind generated test-session queue actions to the HTTP runtime."""

    @staticmethod
    def _runtime_value(runtime_scope: Mapping[str, Any], name: str) -> Any:
        return runtime_scope[name]

    @classmethod
    def run_generated_test_session_pack_from_runtime(
        cls,
        runtime_scope: Mapping[str, Any],
        limit: int = 12,
        *,
        mode: str = "recent",
    ) -> tuple[bool, str, dict]:
        service = cls._runtime_value(runtime_scope, "TEST_SESSION_CONTROL_SERVICE")
        return service.run_generated_test_session_pack(
            limit,
            mode=mode,
            available_definitions_fn=cls._runtime_value(runtime_scope, "_available_test_session_definitions"),
            run_test_session_definition_fn=cls._runtime_value(runtime_scope, "_run_test_session_definition"),
            report_summaries_fn=cls._runtime_value(runtime_scope, "_test_session_report_summaries"),
            generated_work_queue_fn=cls._runtime_value(runtime_scope, "_generated_work_queue"),
        )

    @classmethod
    def run_next_generated_work_queue_item_from_runtime(cls, runtime_scope: Mapping[str, Any]) -> tuple[bool, str, dict]:
        service = cls._runtime_value(runtime_scope, "TEST_SESSION_CONTROL_SERVICE")
        return service.run_next_generated_work_queue_item(
            generated_work_queue_fn=cls._runtime_value(runtime_scope, "_generated_work_queue"),
            run_test_session_definition_fn=cls._runtime_value(runtime_scope, "_run_test_session_definition"),
        )

    @classmethod
    def investigate_generated_work_queue_item_from_runtime(
        cls,
        runtime_scope: Mapping[str, Any],
        session_file: str = "",
        *,
        session_id: str = "",
        user_id: str = "operator",
    ) -> tuple[bool, str, dict]:
        service = cls._runtime_value(runtime_scope, "TEST_SESSION_CONTROL_SERVICE")
        assert_session_owner_fn = cls._runtime_value(runtime_scope, "_assert_session_owner")
        return service.investigate_generated_work_queue_item(
            session_file=session_file,
            session_id=session_id,
            user_id=user_id,
            generated_work_queue_fn=cls._runtime_value(runtime_scope, "_generated_work_queue"),
            resolve_operator_macro_fn=cls._runtime_value(runtime_scope, "_resolve_operator_macro"),
            render_operator_macro_prompt_fn=cls._runtime_value(runtime_scope, "_render_operator_macro_prompt"),
            normalize_user_id_fn=cls._runtime_value(runtime_scope, "_normalize_user_id"),
            assert_session_owner_fn=lambda sid, uid: assert_session_owner_fn(sid, uid, allow_bind=True),
            process_chat_fn=cls._runtime_value(runtime_scope, "process_chat"),
            session_summaries_fn=cls._runtime_value(runtime_scope, "_session_summaries"),
        )

    @classmethod
    def action_hooks_from_runtime(cls, runtime_scope: Mapping[str, Any]) -> dict[str, Callable[..., Any]]:
        service = cls._runtime_value(runtime_scope, "TEST_SESSION_CONTROL_SERVICE")
        return {
            "generated_pack_run_action_fn": lambda payload: service.generated_pack_run_action(
                payload,
                run_generated_test_session_pack_fn=lambda limit=12, mode="recent": cls.run_generated_test_session_pack_from_runtime(
                    runtime_scope,
                    limit,
                    mode=mode,
                ),
            ),
            "generated_queue_run_next_action_fn": lambda _payload: service.generated_queue_run_next_action(
                run_next_generated_work_queue_item_fn=lambda: cls.run_next_generated_work_queue_item_from_runtime(runtime_scope),
            ),
            "generated_queue_investigate_action_fn": lambda payload: service.generated_queue_investigate_action(
                payload,
                investigate_generated_work_queue_item_fn=lambda session_file, session_id="", user_id="operator": cls.investigate_generated_work_queue_item_from_runtime(
                    runtime_scope,
                    session_file,
                    session_id=session_id,
                    user_id=user_id,
                ),
            ),
        }


HTTP_GENERATED_WORK_SERVICE = NovaHttpGeneratedWorkService()
