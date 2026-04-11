from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import http_test_session_helpers


class TestSessionControlService:
    """Build test-session definition, report, and generated-queue summaries outside HTTP."""

    @staticmethod
    def test_sessions_root(runtime_dir: Path) -> Path:
        return Path(runtime_dir) / "test_sessions"

    def generated_test_session_definitions_dir(self, runtime_dir: Path) -> Path:
        return self.test_sessions_root(runtime_dir) / "generated_definitions"

    @staticmethod
    def test_session_definitions_dir(base_dir: Path) -> Path:
        return Path(base_dir) / "tests" / "sessions"

    @staticmethod
    def _iter_definition_files(root: Path) -> list[Path]:
        try:
            files = [path for path in root.rglob("*.json") if path.is_file()]
        except Exception:
            return []
        return sorted(files, key=lambda path: path.as_posix().lower())

    @staticmethod
    def _relative_definition_name(path: Path, root: Path) -> str:
        try:
            return path.relative_to(root).as_posix()
        except Exception:
            return path.name

    @staticmethod
    def _normalize_session_lookup(value: str) -> str:
        return str(value or "").strip().replace("\\", "/")

    @staticmethod
    def _candidate_report_keys(session_path: str) -> list[str]:
        normalized = str(session_path or "").strip().replace("\\", "/")
        if not normalized:
            return []
        candidates: list[str] = []
        for marker in ("/generated_definitions/", "/tests/sessions/"):
            if marker in normalized:
                candidates.append(normalized.split(marker, 1)[1])
        candidates.append(Path(normalized).name)
        out: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
        return out

    @staticmethod
    def _slugify_task_id(value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
        cleaned = cleaned.strip("_")
        return cleaned[:80] or "real_world_task"

    @staticmethod
    def _file_fingerprint(path: Path) -> str:
        try:
            return hashlib.sha1(path.read_bytes()).hexdigest()
        except Exception:
            return ""

    @staticmethod
    def _latest_audit_by_file(runtime_dir: Path) -> dict[str, dict]:
        audit_path = Path(runtime_dir) / "test_sessions" / "promotion_audit.jsonl"
        latest: dict[str, dict] = {}
        if not audit_path.exists():
            return latest
        try:
            lines = audit_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return latest
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            file_name = str(row.get("file") or "").strip()
            if file_name:
                latest[file_name] = row
        return latest

    def all_test_session_definition_roots(self, *, base_dir: Path, runtime_dir: Path) -> list[tuple[Path, str]]:
        return [
            (self.test_session_definitions_dir(base_dir), "saved"),
            (self.generated_test_session_definitions_dir(runtime_dir), "generated"),
        ]

    @staticmethod
    def test_session_run_action(payload: dict, *, run_test_session_definition_fn) -> tuple[bool, str, dict, str]:
        session_file = str(payload.get("session_file") or "").strip()
        ok, msg, extra = run_test_session_definition_fn(session_file)
        return ok, msg, extra, msg

    @staticmethod
    def generated_pack_run_action(payload: dict, *, run_generated_test_session_pack_fn) -> tuple[bool, str, dict, str]:
        ok, msg, extra = run_generated_test_session_pack_fn(
            limit=int(payload.get("limit") or 12),
            mode=str(payload.get("mode") or "recent"),
        )
        return ok, msg, extra, msg

    @staticmethod
    def generated_queue_run_next_action(*, run_next_generated_work_queue_item_fn) -> tuple[bool, str, dict, str]:
        ok, msg, extra = run_next_generated_work_queue_item_fn()
        return ok, msg, extra, msg

    @staticmethod
    def generated_queue_investigate_action(payload: dict, *, investigate_generated_work_queue_item_fn) -> tuple[bool, str, dict, str]:
        ok, msg, extra = investigate_generated_work_queue_item_fn(
            str(payload.get("session_file") or payload.get("file") or ""),
            session_id=str(payload.get("session_id") or ""),
            user_id=str(payload.get("user_id") or "operator"),
        )
        return ok, msg, extra, msg

    @staticmethod
    def generated_queue_operator_note(item: dict) -> str:
        return http_test_session_helpers.generated_queue_operator_note(item)

    @staticmethod
    def investigate_generated_work_queue_item(
        session_file: str = "",
        *,
        session_id: str = "",
        user_id: str = "operator",
        generated_work_queue_fn,
        resolve_operator_macro_fn,
        render_operator_macro_prompt_fn,
        normalize_user_id_fn,
        assert_session_owner_fn,
        process_chat_fn,
        session_summaries_fn,
    ) -> tuple[bool, str, dict]:
        return http_test_session_helpers.investigate_generated_work_queue_item(
            session_file=session_file,
            session_id=session_id,
            user_id=user_id,
            generated_work_queue=generated_work_queue_fn,
            resolve_operator_macro=resolve_operator_macro_fn,
            render_operator_macro_prompt=render_operator_macro_prompt_fn,
            normalize_user_id=normalize_user_id_fn,
            assert_session_owner=assert_session_owner_fn,
            process_chat=process_chat_fn,
            session_summaries=session_summaries_fn,
        )

    @staticmethod
    def available_test_session_definitions(definition_roots: list[tuple[Path, str]], limit: int = 80) -> list[dict]:
        out: list[dict] = []
        for root, origin in list(definition_roots or []):
            if not isinstance(root, Path) or not root.exists():
                continue
            for path in TestSessionControlService._iter_definition_files(root):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    payload = {}
                if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
                    continue
                messages = payload.get("messages")
                relative_name = TestSessionControlService._relative_definition_name(path, root)
                out.append(
                    {
                        "file": relative_name,
                        "basename": path.name,
                        "path": str(path),
                        "name": str(payload.get("name") or path.stem),
                        "message_count": len(messages),
                        "origin": origin,
                        "source": str(payload.get("source") or ""),
                        "category": str(payload.get("category") or ""),
                        "objective": str(payload.get("objective") or ""),
                        "task_id": str(payload.get("task_id") or ""),
                        "label": str(payload.get("label") or ""),
                        "family_id": str(payload.get("family_id") or ""),
                        "variation_id": str(payload.get("variation_id") or ""),
                        "training_priorities": list(payload.get("training_priorities") or []),
                        "fingerprint": TestSessionControlService._file_fingerprint(path),
                    }
                )
        out.sort(key=lambda item: (str(item.get("origin") or ""), str(item.get("file") or "")))
        return out[: max(1, int(limit))]

    @staticmethod
    def resolve_test_session_definition(session_name: str, definitions: list[dict]) -> Path | None:
        lookup = TestSessionControlService._normalize_session_lookup(session_name)
        if not lookup:
            return None
        candidate = Path(lookup)
        if candidate.is_absolute() and candidate.exists():
            return candidate
        basename_matches: list[Path] = []
        for item in list(definitions or []):
            path = Path(str(item.get("path") or ""))
            entry_file = TestSessionControlService._normalize_session_lookup(str(item.get("file") or ""))
            entry_path = TestSessionControlService._normalize_session_lookup(str(item.get("path") or ""))
            entry_basename = TestSessionControlService._normalize_session_lookup(str(item.get("basename") or ""))
            if lookup in {entry_file, entry_path} and path.exists():
                return path
            if lookup == entry_basename and path.exists():
                basename_matches.append(path)
        if len(basename_matches) == 1:
            return basename_matches[0]
        return None

    @staticmethod
    def generated_definition_priority_tuple(item: dict) -> tuple[int, float, int, str]:
        priorities = [priority for priority in list(item.get("training_priorities") or []) if isinstance(priority, dict)] if isinstance(item, dict) else []
        if not priorities:
            return (4, 0.0, 0, str(item.get("file") or ""))

        urgency_rank = min(
            {"high": 0, "medium": 1, "low": 2, "deferred": 3}.get(str(priority.get("urgency") or "").strip().lower(), 4)
            for priority in priorities
        )
        robustness = max(float(priority.get("robustness", 0.0) or 0.0) for priority in priorities)
        return (urgency_rank, -robustness, -len(priorities), str(item.get("file") or ""))

    @staticmethod
    def generated_work_queue_status_rank(status: str) -> int:
        normalized = str(status or "never_run").strip().lower() or "never_run"
        return {
            "drift": 0,
            "warning": 1,
            "never_run": 2,
            "green": 3,
        }.get(normalized, 4)

    @staticmethod
    def report_status_label(diff_count: int, flagged_probe_count: int) -> str:
        if diff_count > 0:
            return "drift"
        if flagged_probe_count > 0:
            return "warning"
        return "green"

    def test_session_report_summaries(self, test_sessions_root: Path, limit: int = 24) -> list[dict]:
        root = Path(test_sessions_root)
        if not root.exists():
            return []

        try:
            run_dirs = [path for path in root.iterdir() if path.is_dir()]
        except Exception:
            return []

        def _sort_key(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except Exception:
                return 0.0

        out: list[dict] = []
        for run_dir in sorted(run_dirs, key=_sort_key, reverse=True)[: max(1, int(limit))]:
            report_path = run_dir / "result.json"
            if not report_path.exists():
                continue
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(report, dict):
                continue

            session_meta = report.get("session") if isinstance(report.get("session"), dict) else {}
            comparison = report.get("comparison") if isinstance(report.get("comparison"), dict) else {}
            runs = report.get("runs") if isinstance(report.get("runs"), dict) else {}
            cli = report.get("cli") if isinstance(report.get("cli"), dict) else {}
            http = report.get("http") if isinstance(report.get("http"), dict) else {}
            left_mode = str(comparison.get("left_mode") or "cli")
            right_mode = str(comparison.get("right_mode") or "http")
            left_run = runs.get(left_mode) if isinstance(runs.get(left_mode), dict) else {}
            right_run = runs.get(right_mode) if isinstance(runs.get(right_mode), dict) else {}

            messages = session_meta.get("messages") if isinstance(session_meta.get("messages"), list) else []
            diffs = comparison.get("diffs") if isinstance(comparison.get("diffs"), list) else []
            cli_flagged = comparison.get("cli_flagged_probes") if isinstance(comparison.get("cli_flagged_probes"), list) else []
            http_flagged = comparison.get("http_flagged_probes") if isinstance(comparison.get("http_flagged_probes"), list) else []
            left_flagged = comparison.get("left_flagged_probes") if isinstance(comparison.get("left_flagged_probes"), list) else cli_flagged
            right_flagged = comparison.get("right_flagged_probes") if isinstance(comparison.get("right_flagged_probes"), list) else http_flagged
            flagged_probe_count = len(cli_flagged) + len(http_flagged)
            if not flagged_probe_count:
                flagged_probe_count = len(left_flagged) + len(right_flagged)
            diff_count = len(diffs)

            out.append(
                {
                    "run_id": run_dir.name,
                    "session_name": str(session_meta.get("name") or run_dir.name),
                    "session_path": str(session_meta.get("path") or ""),
                    "generated_at": str(report.get("generated_at") or ""),
                    "message_count": len(messages),
                    "report_path": str(report_path),
                    "status": self.report_status_label(diff_count, flagged_probe_count),
                    "comparison": {
                        "left_mode": left_mode,
                        "right_mode": right_mode,
                        "left_label": str(comparison.get("left_label") or left_mode),
                        "right_label": str(comparison.get("right_label") or right_mode),
                        "left_turns": int(comparison.get("left_turns", 0) or 0),
                        "right_turns": int(comparison.get("right_turns", 0) or 0),
                        "turn_count_match": bool(comparison.get("turn_count_match", False)),
                        "cli_turns": int(comparison.get("cli_turns", 0) or 0),
                        "http_turns": int(comparison.get("http_turns", 0) or 0),
                        "diff_count": diff_count,
                        "diffs": diffs,
                        "cli_flagged_probes": cli_flagged,
                        "http_flagged_probes": http_flagged,
                        "left_flagged_probes": left_flagged,
                        "right_flagged_probes": right_flagged,
                        "flagged_probe_count": flagged_probe_count,
                    },
                    "artifacts": {
                        "run_dir": str(run_dir),
                        "left_mode": left_mode,
                        "right_mode": right_mode,
                        "left_mode_dir": str((left_run.get("artifacts") or {}).get("mode_dir") or "") if isinstance(left_run.get("artifacts"), dict) else "",
                        "right_mode_dir": str((right_run.get("artifacts") or {}).get("mode_dir") or "") if isinstance(right_run.get("artifacts"), dict) else "",
                        "cli_mode_dir": str((cli.get("artifacts") or {}).get("mode_dir") or "") if isinstance(cli.get("artifacts"), dict) else "",
                        "http_mode_dir": str((http.get("artifacts") or {}).get("mode_dir") or "") if isinstance(http.get("artifacts"), dict) else "",
                    },
                }
            )
        return out

    def latest_generated_report_by_file(self, reports: list[dict], limit: int = 200) -> dict[str, dict]:
        latest: dict[str, dict] = {}
        for report in list(reports or [])[: max(24, int(limit or 200))]:
            session_path = str(report.get("session_path") or "").strip()
            if not session_path:
                continue
            for file_name in self._candidate_report_keys(session_path):
                if file_name in latest:
                    continue
                latest[file_name] = report
        return latest

    def create_real_world_task_definition(
        self,
        payload: dict,
        *,
        runtime_dir: Path,
        available_definitions_fn,
    ) -> tuple[bool, str, dict]:
        name = str(payload.get("name") or "").strip()
        objective = str(payload.get("objective") or "").strip()
        category = str(payload.get("category") or "operator").strip().lower() or "operator"
        prompt = str(payload.get("prompt") or "").strip()
        followup = str(payload.get("followup") or "").strip()
        requested_task_id = str(payload.get("task_id") or "").strip()
        if not name:
            return False, "real_world_task_name_required", {}
        if not objective:
            return False, "real_world_task_objective_required", {}
        if not prompt:
            return False, "real_world_task_prompt_required", {}

        task_id = self._slugify_task_id(requested_task_id or name)
        task_dir = self.generated_test_session_definitions_dir(runtime_dir) / "real_world"
        task_dir.mkdir(parents=True, exist_ok=True)
        task_path = task_dir / f"{task_id}.json"
        if task_path.exists():
            return False, f"real_world_task_exists:{task_id}", {
                "task": {"task_id": task_id, "path": str(task_path)},
                "definitions": available_definitions_fn(120),
            }

        messages = [prompt]
        if followup:
            messages.append(followup)
        definition = {
            "name": name,
            "task_id": task_id,
            "source": "real_world",
            "category": category,
            "objective": objective,
            "messages": messages,
            "success_signals": [
                "Nova understands the operator goal and keeps the task grounded.",
                "Nova returns an operator-usable outcome instead of a generic chat answer.",
            ],
            "failure_signals": [
                "Nova invents state or ignores the actual repo/runtime context.",
                "Nova drops the task thread across follow-up turns.",
            ],
            "evidence_to_review": [
                "assistant answer",
                "route summary",
                "grounding",
                "operator usefulness",
            ],
            "notes": str(payload.get("notes") or "").strip(),
        }
        task_path.write_text(json.dumps(definition, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        relative_name = self._relative_definition_name(task_path, self.generated_test_session_definitions_dir(runtime_dir))
        return True, f"real_world_task_created:{relative_name}", {
            "task": {
                "file": relative_name,
                "path": str(task_path),
                "task_id": task_id,
                "name": name,
                "category": category,
                "objective": objective,
            },
            "definitions": available_definitions_fn(120),
        }

    def real_world_task_create_action(
        self,
        payload: dict,
        *,
        runtime_dir: Path,
        available_definitions_fn,
    ) -> tuple[bool, str, dict, str]:
        ok, msg, extra = self.create_real_world_task_definition(
            payload,
            runtime_dir=runtime_dir,
            available_definitions_fn=available_definitions_fn,
        )
        return ok, msg, extra, msg

    def generated_work_queue(self, definitions: list[dict], reports: list[dict], limit: int = 24, runtime_dir: Path | None = None) -> dict:
        generated_defs = [item for item in list(definitions or []) if str(item.get("origin") or "") == "generated"]
        report_by_file = self.latest_generated_report_by_file(reports, max(200, len(generated_defs) * 2))
        audit_by_file = self._latest_audit_by_file(Path(runtime_dir)) if runtime_dir is not None else {}

        items: list[dict] = []
        for item in generated_defs:
            file_name = str(item.get("file") or "").strip()
            if not file_name:
                continue
            latest_report = dict(report_by_file.get(file_name) or {})
            latest_status = str(latest_report.get("status") or "never_run").strip().lower() or "never_run"
            fingerprint = str(item.get("fingerprint") or "")
            audit_row = dict(audit_by_file.get(file_name) or {})
            audit_fingerprint = str(audit_row.get("fingerprint") or "")
            already_reviewed_current = bool(fingerprint and audit_fingerprint and fingerprint == audit_fingerprint)
            if latest_status == "warning":
                opportunity_reason = "flagged_probe_followup"
            elif latest_status == "drift":
                opportunity_reason = "parity_drift_locked" if already_reviewed_current else "parity_drift"
            elif latest_status == "green":
                opportunity_reason = "verified"
            else:
                opportunity_reason = "unrun_generated_candidate"
            priorities = list(item.get("training_priorities") or []) if isinstance(item.get("training_priorities"), list) else []
            highest_priority = None
            if priorities:
                ordered = sorted(
                    priorities,
                    key=lambda priority: self.generated_definition_priority_tuple({"training_priorities": [priority], "file": file_name}),
                )
                highest_priority = ordered[0]
            queue_item = {
                "file": file_name,
                "name": str(item.get("name") or file_name),
                "path": str(item.get("path") or ""),
                "family_id": str(item.get("family_id") or ""),
                "variation_id": str(item.get("variation_id") or ""),
                "label": str(item.get("label") or ""),
                "message_count": int(item.get("message_count", 0) or 0),
                "training_priorities": priorities,
                "highest_priority": dict(highest_priority) if isinstance(highest_priority, dict) else {},
                "latest_status": latest_status,
                "opportunity_reason": opportunity_reason,
                "open": latest_status != "green",
                "actionable": latest_status != "green" and not (latest_status == "drift" and already_reviewed_current),
                "reviewed_current_fingerprint": already_reviewed_current,
                "latest_run_id": str(latest_report.get("run_id") or ""),
                "latest_report_path": str(latest_report.get("report_path") or ""),
                "latest_generated_at": str(latest_report.get("generated_at") or ""),
                "latest_comparison": dict(latest_report.get("comparison") or {}) if isinstance(latest_report.get("comparison"), dict) else {},
            }
            items.append(queue_item)

        items.sort(
            key=lambda queue_item: (
                0 if bool(queue_item.get("actionable")) else (1 if bool(queue_item.get("open")) else 2),
                self.generated_work_queue_status_rank(str(queue_item.get("latest_status") or "never_run")),
                *self.generated_definition_priority_tuple(queue_item),
            )
        )

        capped_items = items[: max(1, int(limit or 24))]
        next_item = next((dict(item) for item in items if bool(item.get("actionable"))), {})
        open_count = sum(1 for item in items if bool(item.get("open")))
        actionable_count = sum(1 for item in items if bool(item.get("actionable")))
        green_count = sum(1 for item in items if str(item.get("latest_status") or "") == "green")
        warning_count = sum(1 for item in items if str(item.get("latest_status") or "") == "warning")
        drift_count = sum(1 for item in items if str(item.get("latest_status") or "") == "drift")
        never_run_count = sum(1 for item in items if str(item.get("latest_status") or "never_run") == "never_run")
        return {
            "count": len(items),
            "open_count": open_count,
            "actionable_count": actionable_count,
            "green_count": green_count,
            "warning_count": warning_count,
            "drift_count": drift_count,
            "never_run_count": never_run_count,
            "next_item": next_item,
            "items": capped_items,
        }

    def run_test_session_definition(
        self,
        session_file: str,
        *,
        runner_path: Path,
        venv_python: Path,
        base_dir: Path,
        resolve_definition_fn,
        available_definitions_fn,
        report_summaries_fn,
        subprocess_run=subprocess.run,
        timeout_sec: int = 180,
    ) -> tuple[bool, str, dict]:
        session_name = str(session_file or "").strip()
        if not session_name:
            return False, "test_session_file_required", {}
        if not Path(runner_path).exists():
            return False, f"test_session_runner_missing:{runner_path}", {}
        if not Path(venv_python).exists():
            return False, f"venv_python_missing:{venv_python}", {}

        resolved_session = resolve_definition_fn(session_name)
        if resolved_session is None:
            return False, f"test_session_not_found:{session_name}", {"available": available_definitions_fn(80)}

        try:
            proc = subprocess_run(
                [str(venv_python), str(runner_path), str(resolved_session)],
                cwd=str(base_dir),
                capture_output=True,
                text=True,
                timeout=max(1, int(timeout_sec or 180)),
            )
        except Exception as exc:
            return False, f"test_session_run_failed:{exc}", {}

        output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
        reports = report_summaries_fn(24)
        latest = reports[0] if reports else {}
        ok = proc.returncode == 0
        message = f"test_session_run_completed:{session_name}" if ok else f"test_session_run_failed:{session_name}:exit:{proc.returncode}"
        return ok, message, {
            "stdout": output,
            "latest_report": latest,
            "reports": reports,
            "definitions": available_definitions_fn(80),
        }

    def run_generated_test_session_pack(
        self,
        limit: int = 12,
        *,
        mode: str = "recent",
        available_definitions_fn,
        run_test_session_definition_fn,
        report_summaries_fn,
        generated_work_queue_fn,
    ) -> tuple[bool, str, dict]:
        definitions = available_definitions_fn(500)
        generated_defs = [item for item in list(definitions or []) if str(item.get("origin") or "") == "generated"]
        if not generated_defs:
            return False, "generated_test_sessions_missing", {"definitions": available_definitions_fn(80)}

        capped_limit = max(1, min(int(limit or 12), len(generated_defs)))
        selected_defs = list(generated_defs)
        effective_mode = str(mode or "recent").strip().lower() or "recent"
        if effective_mode == "priority":
            selected_defs.sort(key=self.generated_definition_priority_tuple)
        selected_defs = selected_defs[:capped_limit]

        batch_results: list[dict] = []
        all_ok = True
        for item in selected_defs:
            session_file = str(item.get("file") or "").strip()
            ok, msg, extra = run_test_session_definition_fn(session_file)
            all_ok = all_ok and ok
            batch_results.append(
                {
                    "file": session_file,
                    "name": str(item.get("name") or session_file),
                    "ok": ok,
                    "message": msg,
                    "latest_report": dict(extra.get("latest_report") or {}),
                }
            )

        reports = report_summaries_fn(24)
        status_label = "completed" if all_ok else "partial"
        message = f"generated_test_sessions_run_{effective_mode}_{status_label}:{len(selected_defs)}"
        return all_ok, message, {
            "count": len(selected_defs),
            "mode": effective_mode,
            "results": batch_results,
            "reports": reports,
            "latest_report": reports[0] if reports else {},
            "definitions": available_definitions_fn(80),
            "work_queue": generated_work_queue_fn(24),
        }

    def run_next_generated_work_queue_item(
        self,
        *,
        generated_work_queue_fn,
        run_test_session_definition_fn,
    ) -> tuple[bool, str, dict]:
        queue_payload = generated_work_queue_fn(24)
        next_item = dict(queue_payload.get("next_item") or {})
        session_file = str(next_item.get("file") or "").strip()
        if not session_file:
            status = "generated_work_queue_blocked" if int(queue_payload.get("open_count", 0) or 0) > 0 else "generated_work_queue_clear"
            return True, status, {
                "work_queue": queue_payload,
                "selected": {},
                "latest_report": {},
            }

        ok, msg, extra = run_test_session_definition_fn(session_file)
        refreshed_queue = generated_work_queue_fn(24)
        return ok, (f"generated_work_queue_next_ok:{session_file}" if ok else f"generated_work_queue_next_failed:{session_file}"), {
            "selected": next_item,
            "runner_message": msg,
            "latest_report": dict(extra.get("latest_report") or {}),
            "reports": list(extra.get("reports") or []),
            "definitions": list(extra.get("definitions") or []),
            "work_queue": refreshed_queue,
        }


TEST_SESSION_CONTROL_SERVICE = TestSessionControlService()