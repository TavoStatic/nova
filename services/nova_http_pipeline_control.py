from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping


class NovaHttpPipelineControlService:
    """Bind Data Lane control services to the HTTP runtime dependencies."""

    @staticmethod
    def _runtime_value(runtime_scope: Mapping[str, Any], name: str) -> Any:
        return runtime_scope[name]

    @classmethod
    def payload_from_runtime(
        cls,
        runtime_scope: Mapping[str, Any],
        *,
        selected_pipeline_id: str = "",
    ) -> dict[str, Any]:
        service = cls._runtime_value(runtime_scope, "CONTROL_PIPELINES_SERVICE")
        data_sources_root = Path(cls._runtime_value(runtime_scope, "DATA_SOURCES_DIR"))
        return service.payload(
            data_sources_root=data_sources_root,
            list_pipeline_summaries_fn=cls._runtime_value(runtime_scope, "pipeline_list_summaries"),
            get_pipeline_status_fn=cls._runtime_value(runtime_scope, "pipeline_get_status"),
            get_pipeline_schema_probe_fn=cls._runtime_value(runtime_scope, "pipeline_get_schema_probe"),
            selected_pipeline_id=selected_pipeline_id,
        )

    @classmethod
    def action_hooks_from_runtime(cls, runtime_scope: Mapping[str, Any]) -> dict[str, Callable[..., Any]]:
        service = cls._runtime_value(runtime_scope, "CONTROL_PIPELINES_SERVICE")
        data_sources_root = Path(cls._runtime_value(runtime_scope, "DATA_SOURCES_DIR"))
        list_pipeline_summaries_fn = cls._runtime_value(runtime_scope, "pipeline_list_summaries")

        return {
            "pipeline_note_append_action_fn": lambda payload: service.append_note(
                payload,
                data_sources_root=data_sources_root,
                list_pipeline_summaries_fn=list_pipeline_summaries_fn,
            ),
            "pipeline_create_action_fn": lambda payload: service.create_lane(
                payload,
                data_sources_root=data_sources_root,
                list_pipeline_summaries_fn=list_pipeline_summaries_fn,
            ),
            "pipeline_start_action_fn": lambda payload: service.set_enabled(
                payload,
                data_sources_root=data_sources_root,
                list_pipeline_summaries_fn=list_pipeline_summaries_fn,
                enabled=True,
            ),
            "pipeline_pause_action_fn": lambda payload: service.set_enabled(
                payload,
                data_sources_root=data_sources_root,
                list_pipeline_summaries_fn=list_pipeline_summaries_fn,
                enabled=False,
            ),
            "pipeline_update_action_fn": lambda payload: service.update_lane_metadata(
                payload,
                data_sources_root=data_sources_root,
                list_pipeline_summaries_fn=list_pipeline_summaries_fn,
            ),
            "pipeline_population_upsert_action_fn": lambda payload: service.upsert_population_definition(
                payload,
                data_sources_root=data_sources_root,
                list_pipeline_summaries_fn=list_pipeline_summaries_fn,
            ),
            "pipeline_archive_action_fn": lambda payload: service.archive_lane(
                payload,
                data_sources_root=data_sources_root,
                list_pipeline_summaries_fn=list_pipeline_summaries_fn,
            ),
        }


HTTP_PIPELINE_CONTROL_SERVICE = NovaHttpPipelineControlService()
