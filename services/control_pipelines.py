from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Optional


class ControlPipelinesService:
    """Control-panel helpers for pipeline discovery and scoped operator intake."""

    @staticmethod
    def _pipeline_dir(data_sources_root: Path, pipeline_id: str) -> Path:
        safe_id = "".join(ch for ch in str(pipeline_id or "").strip() if ch.isalnum() or ch in {"_", "-"})
        return data_sources_root / safe_id

    @staticmethod
    def _safe_pipeline_id(value: str) -> str:
        raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        safe = "".join(ch for ch in raw if ch.isalnum() or ch == "_").strip("_")
        return safe

    @staticmethod
    def _safe_population_key(value: str) -> str:
        raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        return "".join(ch for ch in raw if ch.isalnum() or ch == "_").strip("_")

    @staticmethod
    def lane_control_path(*, data_sources_root: Path, pipeline_id: str) -> Path:
        return ControlPipelinesService._pipeline_dir(data_sources_root, pipeline_id) / "lane_control.json"

    @staticmethod
    def lane_state(*, data_sources_root: Path, pipeline_id: str) -> dict[str, Any]:
        path = ControlPipelinesService.lane_control_path(data_sources_root=data_sources_root, pipeline_id=pipeline_id)
        if not path.exists():
            return {"enabled": True, "state": "running", "path": str(path)}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        enabled = bool(data.get("enabled", True))
        return {
            **data,
            "enabled": enabled,
            "state": "running" if enabled else "paused",
            "path": str(path),
        }

    @staticmethod
    def _write_lane_state(
        *,
        data_sources_root: Path,
        pipeline_id: str,
        enabled: bool,
        reason: str = "",
        now_fn: Callable[[], float] = time.time,
    ) -> dict[str, Any]:
        path = ControlPipelinesService.lane_control_path(data_sources_root=data_sources_root, pipeline_id=pipeline_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "enabled": bool(enabled),
            "state": "running" if enabled else "paused",
            "reason": str(reason or "").strip(),
            "updated_at": int(now_fn()),
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        payload["path"] = str(path)
        return payload

    @staticmethod
    def payload(
        *,
        data_sources_root: Path,
        list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]],
        get_pipeline_status_fn: Callable[..., dict[str, Any]],
        get_pipeline_schema_probe_fn: Callable[..., dict[str, Any]],
        selected_pipeline_id: str = "",
    ) -> dict[str, Any]:
        summaries = []
        for item in list_pipeline_summaries_fn(data_sources_root):
            pipeline_id = str(item.get("pipeline_id") or "").strip()
            summaries.append({
                **item,
                "lane_state": item.get("lane_state") if isinstance(item.get("lane_state"), Mapping) else ControlPipelinesService.lane_state(data_sources_root=data_sources_root, pipeline_id=pipeline_id),
            })
        selected = str(selected_pipeline_id or "").strip()
        if not selected and summaries:
            selected = str(summaries[0].get("pipeline_id") or "")

        detail: dict[str, Any] = {}
        if selected:
            try:
                detail = {
                    "pipeline_id": selected,
                    "status": get_pipeline_status_fn(selected, data_sources_root=data_sources_root),
                    "schema_probe": get_pipeline_schema_probe_fn(selected, data_sources_root=data_sources_root),
                    "lane_state": ControlPipelinesService.lane_state(data_sources_root=data_sources_root, pipeline_id=selected),
                    "intake": ControlPipelinesService.intake_summary(data_sources_root=data_sources_root, pipeline_id=selected),
                }
            except Exception as exc:
                detail = {
                    "pipeline_id": selected,
                    "error": str(exc),
                    "lane_state": ControlPipelinesService.lane_state(data_sources_root=data_sources_root, pipeline_id=selected),
                    "intake": ControlPipelinesService.intake_summary(data_sources_root=data_sources_root, pipeline_id=selected),
                }

        return {
            "ok": True,
            "pipelines": summaries,
            "selected_pipeline_id": selected,
            "detail": detail,
        }

    @staticmethod
    def intake_path(*, data_sources_root: Path, pipeline_id: str) -> Path:
        return ControlPipelinesService._pipeline_dir(data_sources_root, pipeline_id) / "operator_intake.jsonl"

    @staticmethod
    def population_definitions_path(*, data_sources_root: Path, pipeline_id: str) -> Path:
        return ControlPipelinesService._pipeline_dir(data_sources_root, pipeline_id) / "population_definitions.json"

    @staticmethod
    def intake_summary(
        *,
        data_sources_root: Path,
        pipeline_id: str,
        limit: int = 12,
    ) -> dict[str, Any]:
        path = ControlPipelinesService.intake_path(data_sources_root=data_sources_root, pipeline_id=pipeline_id)
        entries: list[dict[str, Any]] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-max(1, int(limit)):]:
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    entries.append(payload)
        return {
            "path": str(path),
            "count_recent": len(entries),
            "recent": entries,
        }

    @staticmethod
    def append_note(
        payload: Mapping[str, Any],
        *,
        data_sources_root: Path,
        list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]],
        now_fn: Callable[[], float] = time.time,
    ) -> tuple[bool, str, dict[str, Any], str]:
        pipeline_id = str(payload.get("pipeline_id") or "").strip()
        note = str(payload.get("note") or "").strip()
        note_type = str(payload.get("note_type") or "operator_grounding").strip() or "operator_grounding"
        if not pipeline_id:
            return False, "pipeline_id_required", {}, "pipeline_intake_missing_pipeline"
        if not note:
            return False, "note_required", {}, "pipeline_intake_missing_note"

        known = {str(item.get("pipeline_id") or "").strip() for item in list_pipeline_summaries_fn(data_sources_root)}
        if pipeline_id not in known:
            return False, f"unknown_pipeline:{pipeline_id}", {}, "pipeline_intake_unknown_pipeline"

        path = ControlPipelinesService.intake_path(data_sources_root=data_sources_root, pipeline_id=pipeline_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": int(now_fn()),
            "pipeline_id": pipeline_id,
            "note_type": note_type,
            "note": note,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
        summary = ControlPipelinesService.intake_summary(data_sources_root=data_sources_root, pipeline_id=pipeline_id)
        return True, "pipeline_note_recorded", {"entry": entry, "intake": summary}, f"pipeline_note_recorded:{pipeline_id}"

    @staticmethod
    def upsert_population_definition(
        payload: Mapping[str, Any],
        *,
        data_sources_root: Path,
        list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]],
        now_fn: Callable[[], float] = time.time,
    ) -> tuple[bool, str, dict[str, Any], str]:
        pipeline_id = str(payload.get("pipeline_id") or "").strip()
        if not pipeline_id:
            return False, "pipeline_id_required", {}, "pipeline_population_missing_pipeline_id"
        known = {str(item.get("pipeline_id") or "").strip() for item in list_pipeline_summaries_fn(data_sources_root)}
        if pipeline_id not in known:
            return False, f"unknown_pipeline:{pipeline_id}", {}, "pipeline_population_unknown_pipeline"

        key = ControlPipelinesService._safe_population_key(str(payload.get("key") or ""))
        label = str(payload.get("label") or key).strip()
        program_id = str(payload.get("program_id") or "").strip()
        field_number = str(payload.get("field_number") or "").strip()
        if not key:
            return False, "population_key_required", {}, "pipeline_population_missing_key"
        if not program_id or not field_number:
            return False, "program_id_and_field_number_required", {}, "pipeline_population_missing_filters"

        lane_dir = ControlPipelinesService._pipeline_dir(data_sources_root, pipeline_id).resolve()
        root = data_sources_root.resolve()
        if root not in lane_dir.parents:
            return False, "pipeline_path_outside_data_sources", {}, "pipeline_population_path_blocked"

        path = ControlPipelinesService.population_definitions_path(data_sources_root=data_sources_root, pipeline_id=pipeline_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        populations = data.get("populations") if isinstance(data.get("populations"), list) else []
        existing_index = next(
            (
                index
                for index, item in enumerate(populations)
                if isinstance(item, Mapping) and str(item.get("key") or "").strip().lower() == key
            ),
            None,
        )
        entry = {
            "key": key,
            "label": label or key,
            "program_id": program_id,
            "field_number": field_number,
            "active_only": bool(payload.get("active_only", True)),
            "updated_at": int(now_fn()),
        }
        if str(payload.get("notes") or "").strip():
            entry["notes"] = str(payload.get("notes") or "").strip()
        if existing_index is None:
            populations.append(entry)
            action = "created"
        else:
            populations[existing_index] = {**populations[existing_index], **entry}
            action = "updated"
        data["populations"] = populations
        data.setdefault("source", {})
        if isinstance(data["source"], dict):
            data["source"].setdefault("notes", [])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")
        return (
            True,
            "pipeline_population_saved",
            {"pipeline_id": pipeline_id, "population": entry, "population_action": action, "path": str(path)},
            f"pipeline_population_{action}:{pipeline_id}:{key}",
        )

    @staticmethod
    def create_lane(
        payload: Mapping[str, Any],
        *,
        data_sources_root: Path,
        list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]],
        now_fn: Callable[[], float] = time.time,
    ) -> tuple[bool, str, dict[str, Any], str]:
        pipeline_id = ControlPipelinesService._safe_pipeline_id(str(payload.get("pipeline_id") or ""))
        display_name = str(payload.get("display_name") or pipeline_id).strip()
        description = str(payload.get("description") or "Operator-created data lane.").strip()
        if not pipeline_id:
            return False, "pipeline_id_required", {}, "pipeline_create_missing_pipeline_id"
        known = {str(item.get("pipeline_id") or "").strip() for item in list_pipeline_summaries_fn(data_sources_root)}
        if pipeline_id in known:
            return False, f"pipeline_exists:{pipeline_id}", {}, "pipeline_create_exists"
        lane_dir = ControlPipelinesService._pipeline_dir(data_sources_root, pipeline_id)
        if lane_dir.exists():
            return False, f"pipeline_directory_exists:{pipeline_id}", {}, "pipeline_create_directory_exists"
        lane_dir.mkdir(parents=True, exist_ok=False)
        module_name = f"data_sources.{pipeline_id}.connector"
        class_name = "OperatorDataLane"
        manifest = {
            "pipeline_id": pipeline_id,
            "display_name": display_name,
            "kind": str(payload.get("kind") or "metadata").strip() or "metadata",
            "version": "0.1.0",
            "description": description,
            "read_only": True,
            "network_scope": str(payload.get("network_scope") or "unknown").strip() or "unknown",
            "safe_operations": ["status", "schema_probe"],
            "connector_module": module_name,
            "connector_class": class_name,
            "schema_manifest": "schema_manifest.json",
            "query_templates": "query_templates.json",
            "field_dictionary": "field_dictionary.json",
            "population_definitions": "population_definitions.json",
            "vendor_dictionary": "vendor_dictionary_index.json",
            "config_example": "local_config.example.json",
            "local_config": "local_config.json",
            "audit_log": f"..\\..\\runtime\\pipelines\\{pipeline_id}_audit.jsonl",
        }
        (lane_dir / "pipeline.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
        (lane_dir / "schema_manifest.json").write_text(json.dumps({"source": {"notes": ["Operator-created data lane."]}, "entities": []}, indent=2), encoding="utf-8")
        (lane_dir / "query_templates.json").write_text("{}\n", encoding="utf-8")
        (lane_dir / "field_dictionary.json").write_text(json.dumps({"fields": [], "table_families": [], "usage_patterns": []}, indent=2), encoding="utf-8")
        (lane_dir / "population_definitions.json").write_text(json.dumps({"populations": []}, indent=2), encoding="utf-8")
        (lane_dir / "vendor_dictionary_index.json").write_text("{}\n", encoding="utf-8")
        (lane_dir / "local_config.example.json").write_text("{}\n", encoding="utf-8")
        (lane_dir / "connector.py").write_text(
            "\n".join([
                "from __future__ import annotations",
                "",
                "from typing import Any, Mapping, Optional",
                "",
                "from pipelines.base import BaseDataPipeline",
                "from pipelines.query_guard import PipelineQueryGuard, QueryGuardError",
                "",
                "",
                "class OperatorDataLane(BaseDataPipeline):",
                "    def __init__(self, manifest):",
                "        super().__init__(manifest)",
                "        self.guard = PipelineQueryGuard()",
                "",
                "    def status(self) -> dict[str, Any]:",
                "        return {",
                "            'pipeline_id': self.manifest.pipeline_id,",
                "            'display_name': self.manifest.display_name,",
                "            'kind': self.manifest.kind,",
                "            'read_only': self.manifest.read_only,",
                "            'network_scope': self.manifest.network_scope,",
                "            'configured': False,",
                "            'live_query_ready': False,",
                "            'execution_supported': False,",
                "        }",
                "",
                "    def safe_query(self, operation: str, params: Optional[Mapping[str, Any]] = None, *, row_limit: Optional[int] = None, dry_run: bool = True) -> dict[str, Any]:",
                "        try:",
                "            validated = self.guard.validate(self.load_query_templates(), operation, params, row_limit=row_limit)",
                "        except QueryGuardError as exc:",
                "            return {'ok': False, 'pipeline_id': self.manifest.pipeline_id, 'operation': operation, 'error': str(exc)}",
                "        return {'ok': False, 'pipeline_id': self.manifest.pipeline_id, 'operation': validated['operation'], 'execution_mode': 'blocked', 'error': 'No executable query templates are configured for this data lane yet.'}",
                "",
            ]),
            encoding="utf-8",
        )
        state = ControlPipelinesService._write_lane_state(data_sources_root=data_sources_root, pipeline_id=pipeline_id, enabled=True, reason="created", now_fn=now_fn)
        return True, "pipeline_created", {"pipeline_id": pipeline_id, "lane_state": state}, f"pipeline_created:{pipeline_id}"

    @staticmethod
    def set_enabled(
        payload: Mapping[str, Any],
        *,
        data_sources_root: Path,
        list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]],
        enabled: bool,
        now_fn: Callable[[], float] = time.time,
    ) -> tuple[bool, str, dict[str, Any], str]:
        pipeline_id = str(payload.get("pipeline_id") or "").strip()
        if not pipeline_id:
            return False, "pipeline_id_required", {}, "pipeline_state_missing_pipeline_id"
        known = {str(item.get("pipeline_id") or "").strip() for item in list_pipeline_summaries_fn(data_sources_root)}
        if pipeline_id not in known:
            return False, f"unknown_pipeline:{pipeline_id}", {}, "pipeline_state_unknown_pipeline"
        state = ControlPipelinesService._write_lane_state(
            data_sources_root=data_sources_root,
            pipeline_id=pipeline_id,
            enabled=enabled,
            reason=str(payload.get("reason") or ""),
            now_fn=now_fn,
        )
        msg = "pipeline_started" if enabled else "pipeline_paused"
        return True, msg, {"pipeline_id": pipeline_id, "lane_state": state}, f"{msg}:{pipeline_id}"

    @staticmethod
    def update_lane_metadata(
        payload: Mapping[str, Any],
        *,
        data_sources_root: Path,
        list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]],
        now_fn: Callable[[], float] = time.time,
    ) -> tuple[bool, str, dict[str, Any], str]:
        pipeline_id = str(payload.get("pipeline_id") or "").strip()
        if not pipeline_id:
            return False, "pipeline_id_required", {}, "pipeline_update_missing_pipeline_id"
        known = {str(item.get("pipeline_id") or "").strip() for item in list_pipeline_summaries_fn(data_sources_root)}
        if pipeline_id not in known:
            return False, f"unknown_pipeline:{pipeline_id}", {}, "pipeline_update_unknown_pipeline"

        lane_dir = ControlPipelinesService._pipeline_dir(data_sources_root, pipeline_id).resolve()
        root = data_sources_root.resolve()
        if root not in lane_dir.parents:
            return False, "pipeline_path_outside_data_sources", {}, "pipeline_update_path_blocked"
        manifest_path = lane_dir / "pipeline.json"
        if not manifest_path.exists():
            return False, "pipeline_manifest_missing", {}, "pipeline_update_manifest_missing"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return False, f"pipeline_manifest_invalid:{exc}", {}, "pipeline_update_manifest_invalid"
        if not isinstance(manifest, dict):
            return False, "pipeline_manifest_invalid", {}, "pipeline_update_manifest_invalid"

        updated_fields: dict[str, Any] = {}
        for key in ("display_name", "description", "kind", "network_scope"):
            if key not in payload:
                continue
            value = str(payload.get(key) or "").strip()
            if not value:
                continue
            manifest[key] = value
            updated_fields[key] = value

        if not updated_fields:
            return False, "no_metadata_updates_requested", {}, "pipeline_update_empty"

        manifest["updated_at"] = int(now_fn())
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
        return (
            True,
            "pipeline_metadata_updated",
            {"pipeline_id": pipeline_id, "updated_fields": updated_fields, "manifest": manifest},
            f"pipeline_metadata_updated:{pipeline_id}",
        )

    @staticmethod
    def archive_lane(
        payload: Mapping[str, Any],
        *,
        data_sources_root: Path,
        list_pipeline_summaries_fn: Callable[..., list[dict[str, Any]]],
        now_fn: Callable[[], float] = time.time,
    ) -> tuple[bool, str, dict[str, Any], str]:
        pipeline_id = str(payload.get("pipeline_id") or "").strip()
        if not pipeline_id:
            return False, "pipeline_id_required", {}, "pipeline_archive_missing_pipeline_id"
        known = {str(item.get("pipeline_id") or "").strip() for item in list_pipeline_summaries_fn(data_sources_root)}
        if pipeline_id not in known:
            return False, f"unknown_pipeline:{pipeline_id}", {}, "pipeline_archive_unknown_pipeline"
        lane_dir = ControlPipelinesService._pipeline_dir(data_sources_root, pipeline_id).resolve()
        root = data_sources_root.resolve()
        if root not in lane_dir.parents:
            return False, "pipeline_path_outside_data_sources", {}, "pipeline_archive_path_blocked"
        archive_root = data_sources_root / "_archived"
        archive_root.mkdir(parents=True, exist_ok=True)
        target = archive_root / f"{pipeline_id}_{int(now_fn())}"
        shutil.move(str(lane_dir), str(target))
        return True, "pipeline_archived", {"pipeline_id": pipeline_id, "archive_path": str(target)}, f"pipeline_archived:{pipeline_id}"


CONTROL_PIPELINES_SERVICE = ControlPipelinesService()
