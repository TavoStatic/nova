from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from services.nova_runtime_context import BASE_DIR, OS_CAPABILITY_LEDGER_FILE, OS_CAPABILITY_REGISTRY_FILE
from services.os_capability_registry import OS_CAPABILITY_REGISTRY_SERVICE


MAX_LEDGER_TEXT_CHARS = 20000
MUTATING_CAPABILITY_REQUIRES_ADMIN_AUTHORITY = "mutating_capability_requires_admin_authority"
EVIDENCE_WRITE_REQUIRES_WRITE_VERIFICATION = "evidence_write_requires_write_verification"


def _safe_text(value: Any, limit: int = 1000) -> str:
    return str(value or "").strip()[: max(1, int(limit or 1))]


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _compact(value: Any, *, depth: int = 0) -> Any:
    if depth >= 5:
        return _safe_text(value, 500)
    if isinstance(value, dict):
        return {str(key): _compact(item, depth=depth + 1) for key, item in list(value.items())[:80]}
    if isinstance(value, list):
        return [_compact(item, depth=depth + 1) for item in value[:80]]
    if isinstance(value, tuple):
        return [_compact(item, depth=depth + 1) for item in list(value)[:80]]
    if isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 4)
    if value is None:
        return None
    return _safe_text(value, 1000)


class OsScriptControllerService:
    """Executes verified OS capability scripts and records outcome evidence."""

    def execute_capability(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        registry_path: Path | None = None,
        ledger_path: Path | None = None,
        base_dir: Path | None = None,
        registry_service: Any = None,
        popen_factory: Any = None,
        powershell_executable: str | None = None,
        authority_context: dict[str, Any] | None = None,
        now_fn: Any = None,
        uuid_fn: Any = None,
    ) -> dict[str, Any]:
        root = Path(base_dir or BASE_DIR).resolve()
        reg_path = Path(registry_path or OS_CAPABILITY_REGISTRY_FILE)
        led_path = Path(ledger_path or OS_CAPABILITY_LEDGER_FILE)
        registry = registry_service or OS_CAPABILITY_REGISTRY_SERVICE
        started = float((now_fn or time.time)())
        request_id = self._request_id(started, uuid_fn=uuid_fn)

        prepared = registry.prepare_request(name, args or {}, reg_path, base_dir=root)
        if not bool(prepared.get("ok")):
            row = self._base_row(
                request_id=request_id,
                started=started,
                capability_name=name,
                registry_path=reg_path,
                base_dir=root,
                args=args or {},
                prepared=prepared,
            )
            row.update(
                {
                    "status": "blocked",
                    "reason": _safe_text(prepared.get("reason"), 120) or "prepare_blocked",
                    "executed": False,
                    "operator_outbox": bool(prepared.get("operator_outbox")),
                    "duration_ms": self._duration_ms(started, now_fn=now_fn),
                }
            )
            ledger = self._append_ledger(led_path, row)
            return self._result_from_row(row, ledger=ledger)

        capability = _safe_dict(prepared.get("capability"))
        execution_hash = registry.verify_capability_hash(capability)
        if not bool(execution_hash.get("ok")):
            prepared = dict(prepared)
            prepared["execution_hash"] = execution_hash
            row = self._base_row(
                request_id=request_id,
                started=started,
                capability_name=name,
                registry_path=reg_path,
                base_dir=root,
                args=prepared.get("args") or {},
                prepared=prepared,
            )
            row.update(
                {
                    "status": "blocked",
                    "reason": "contract_stale",
                    "detail": _safe_text(execution_hash.get("reason"), 500),
                    "executed": False,
                    "operator_outbox": True,
                    "duration_ms": self._duration_ms(started, now_fn=now_fn),
                    "errors": _safe_list(execution_hash.get("errors")),
                }
            )
            ledger = self._append_ledger(led_path, row)
            return self._result_from_row(row, ledger=ledger)

        authority = self._authority_result(capability, authority_context)
        if not bool(authority.get("ok")):
            row = self._base_row(
                request_id=request_id,
                started=started,
                capability_name=name,
                registry_path=reg_path,
                base_dir=root,
                args=prepared.get("args") or {},
                prepared=prepared,
            )
            row.update(
                {
                    "status": "blocked",
                    "reason": "authority_blocked",
                    "detail": _safe_text(authority.get("reason"), 500),
                    "executed": False,
                    "operator_outbox": True,
                    "duration_ms": self._duration_ms(started, now_fn=now_fn),
                    "authority": authority,
                    "errors": _safe_list(authority.get("errors")),
                }
            )
            ledger = self._append_ledger(led_path, row)
            return self._result_from_row(row, ledger=ledger)

        command_result = self._build_command(
            capability,
            _safe_dict(prepared.get("args")),
            root,
            powershell_executable=powershell_executable,
        )
        if not command_result.get("ok"):
            row = self._base_row(
                request_id=request_id,
                started=started,
                capability_name=name,
                registry_path=reg_path,
                base_dir=root,
                args=prepared.get("args") or {},
                prepared=prepared,
            )
            row.update(
                {
                    "status": "blocked",
                    "reason": "contract_stale",
                    "detail": _safe_text(command_result.get("reason"), 500),
                    "executed": False,
                    "operator_outbox": True,
                    "duration_ms": self._duration_ms(started, now_fn=now_fn),
                    "errors": _safe_list(command_result.get("errors")),
                }
            )
            ledger = self._append_ledger(led_path, row)
            return self._result_from_row(row, ledger=ledger)

        run_result = self._run_process(
            command_result["command"],
            cwd=Path(command_result["cwd"]),
            timeout_ms=int(command_result["timeout_ms"]),
            popen_factory=popen_factory,
            now_fn=now_fn,
        )
        evidence_contract = self._verify_evidence_ok(capability, run_result)
        write_contract = self._verify_writes_only_to(capability, run_result, root)
        final_status = run_result["status"]
        final_reason = run_result["reason"]
        final_errors = _safe_list(run_result.get("errors"))
        final_operator_outbox = False
        if not bool(evidence_contract.get("ok")):
            final_status = "failed"
            final_reason = _safe_text(evidence_contract.get("reason"), 120) or "capability_evidence_not_ok"
            final_errors.extend(_safe_list(evidence_contract.get("errors")))
            final_operator_outbox = True
        if not bool(write_contract.get("ok")):
            final_status = "failed"
            final_reason = _safe_text(write_contract.get("reason"), 120) or "write_contract_violation"
            final_errors.extend(_safe_list(write_contract.get("errors")))
            final_operator_outbox = True
        row = self._base_row(
            request_id=request_id,
            started=started,
            capability_name=name,
            registry_path=reg_path,
            base_dir=root,
            args=prepared.get("args") or {},
            prepared=prepared,
        )
        row.update(
            {
                "status": final_status,
                "reason": final_reason,
                "executed": True,
                "operator_outbox": final_operator_outbox,
                "duration_ms": self._duration_ms(started, now_fn=now_fn),
                "command": command_result["command_summary"],
                "exit_code": run_result.get("exit_code"),
                "timed_out": bool(run_result.get("timed_out")),
                "killed": bool(run_result.get("killed")),
                "stdout": self._limit_text(run_result.get("stdout")),
                "stderr": self._limit_text(run_result.get("stderr")),
                "errors": final_errors,
                "evidence_contract": evidence_contract,
                "write_contract": write_contract,
            }
        )
        ledger = self._append_ledger(led_path, row)
        return self._result_from_row(row, ledger=ledger)

    @staticmethod
    def recent_ledger_rows(path: Path | None = None, *, limit: int = 80) -> list[dict[str, Any]]:
        ledger_path = Path(path or OS_CAPABILITY_LEDGER_FILE)
        if not ledger_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            for line in ledger_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
        except Exception:
            return []
        return rows[-max(1, int(limit or 1)) :]

    def summary(self, path: Path | None = None, *, limit: int = 80) -> dict[str, Any]:
        ledger_path = Path(path or OS_CAPABILITY_LEDGER_FILE)
        rows = self.recent_ledger_rows(ledger_path, limit=limit)
        status_counts: dict[str, int] = {}
        reason_counts: dict[str, int] = {}
        for row in rows:
            status = _safe_text(row.get("status"), 80)
            reason = _safe_text(row.get("reason"), 120)
            if status:
                status_counts[status] = status_counts.get(status, 0) + 1
            if reason:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        return {
            "ok": True,
            "path": str(ledger_path),
            "count": len(rows),
            "status_counts": status_counts,
            "reason_counts": reason_counts,
            "last_row": rows[-1] if rows else {},
            "rows": rows,
        }

    def _verify_writes_only_to(
        self,
        capability: dict[str, Any],
        run_result: dict[str, Any],
        base_dir: Path,
    ) -> dict[str, Any]:
        raw_target = _safe_text(capability.get("writes_only_to"), 1000)
        if not raw_target:
            return {"ok": True, "reason": "", "checked": False, "errors": []}
        if _safe_text(run_result.get("status"), 80) != "success":
            return {"ok": True, "reason": "", "checked": False, "deferred": True, "errors": []}

        root = Path(base_dir).resolve()
        target_path = Path(raw_target)
        allowed_root = (target_path if target_path.is_absolute() else root / target_path).resolve()
        stdout = _safe_text(run_result.get("stdout"), MAX_LEDGER_TEXT_CHARS)
        try:
            payload = json.loads(stdout or "{}")
        except Exception as exc:
            return {
                "ok": False,
                "reason": "write_contract_stdout_not_json",
                "checked": True,
                "allowed_root": str(allowed_root),
                "errors": [f"write_contract_stdout_not_json:{exc}"],
            }
        if not isinstance(payload, dict):
            return {
                "ok": False,
                "reason": "write_contract_stdout_not_object",
                "checked": True,
                "allowed_root": str(allowed_root),
                "errors": ["write_contract_stdout_not_object"],
            }

        reported_paths = self._reported_write_paths(payload)
        if not reported_paths:
            return {
                "ok": False,
                "reason": "write_contract_path_missing",
                "checked": True,
                "allowed_root": str(allowed_root),
                "errors": ["write_contract_path_missing"],
            }

        errors: list[str] = []
        verified: list[str] = []
        for raw_path in reported_paths:
            candidate = Path(raw_path)
            resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
            try:
                resolved.relative_to(allowed_root)
            except ValueError:
                errors.append(f"write_outside_allowed_root:{resolved}")
                continue
            if not resolved.exists():
                errors.append(f"reported_write_missing:{resolved}")
                continue
            verified.append(str(resolved))

        return {
            "ok": not errors,
            "reason": "" if not errors else "write_contract_violation",
            "checked": True,
            "allowed_root": str(allowed_root),
            "verified_paths": verified,
            "errors": errors,
        }

    def _verify_evidence_ok(
        self,
        capability: dict[str, Any],
        run_result: dict[str, Any],
    ) -> dict[str, Any]:
        if _safe_text(run_result.get("status"), 80) != "success":
            return {"ok": True, "reason": "", "checked": False, "deferred": True, "errors": []}

        stdout = _safe_text(run_result.get("stdout"), MAX_LEDGER_TEXT_CHARS)
        if not stdout:
            return {"ok": True, "reason": "", "checked": False, "errors": []}
        try:
            payload = json.loads(stdout)
        except Exception:
            return {"ok": True, "reason": "", "checked": False, "errors": []}
        if not isinstance(payload, dict) or "ok" not in payload:
            return {"ok": True, "reason": "", "checked": False, "errors": []}
        if bool(payload.get("ok")):
            return {"ok": True, "reason": "", "checked": True, "errors": []}

        evidence_errors = [
            _safe_text(item, 500)
            for item in _safe_list(payload.get("errors"))
            if _safe_text(item, 500)
        ]
        if not evidence_errors:
            error_text = _safe_text(payload.get("error") or payload.get("reason"), 500)
            if error_text:
                evidence_errors.append(error_text)
        evidence_errors.insert(0, "evidence_ok_false")
        return {
            "ok": False,
            "reason": "capability_evidence_not_ok",
            "checked": True,
            "capability": _safe_text(capability.get("name"), 120),
            "errors": evidence_errors,
            "payload": _compact(payload),
        }

    @staticmethod
    def _reported_write_paths(payload: dict[str, Any]) -> list[str]:
        keys = ("output_path", "bundle_path", "report_path", "evidence_path", "path")
        paths: list[str] = []
        for key in keys:
            value = _safe_text(payload.get(key), 1000)
            if value:
                paths.append(value)
        for item in _safe_list(payload.get("writes")):
            if isinstance(item, dict):
                value = _safe_text(item.get("path") or item.get("output_path"), 1000)
            else:
                value = _safe_text(item, 1000)
            if value:
                paths.append(value)
        deduped: list[str] = []
        seen: set[str] = set()
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            deduped.append(path)
        return deduped

    @staticmethod
    def _authority_result(capability: dict[str, Any], authority_context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = _safe_dict(authority_context)
        authority_level = _safe_text(capability.get("authority_level"), 120)
        mutating = bool(capability.get("mutating", False))
        allowed_levels = {
            _safe_text(item, 120)
            for item in _safe_list(context.get("allowed_authority_levels"))
            if _safe_text(item, 120)
        } or {"read_only", "read_only_expensive", "read_only_network"}

        if authority_level not in allowed_levels:
            return {
                "ok": False,
                "reason": f"authority_level_not_allowed:{authority_level}",
                "authority_level": authority_level,
                "allowed_authority_levels": sorted(allowed_levels),
                "errors": [f"authority_level_not_allowed:{authority_level}"],
            }
        if mutating and not (bool(context.get("is_admin")) and bool(context.get("allow_mutating"))):
            return {
                "ok": False,
                "reason": MUTATING_CAPABILITY_REQUIRES_ADMIN_AUTHORITY,
                "authority_level": authority_level,
                "mutating": True,
                "errors": [MUTATING_CAPABILITY_REQUIRES_ADMIN_AUTHORITY],
            }
        if authority_level == "evidence_write" and not bool(context.get("allow_evidence_write")):
            return {
                "ok": False,
                "reason": EVIDENCE_WRITE_REQUIRES_WRITE_VERIFICATION,
                "authority_level": authority_level,
                "errors": [EVIDENCE_WRITE_REQUIRES_WRITE_VERIFICATION],
            }
        return {
            "ok": True,
            "reason": "",
            "authority_level": authority_level,
            "mutating": mutating,
            "allowed_authority_levels": sorted(allowed_levels),
            "errors": [],
        }

    def _build_command(
        self,
        capability: dict[str, Any],
        args: dict[str, Any],
        base_dir: Path,
        *,
        powershell_executable: str | None = None,
    ) -> dict[str, Any]:
        script = _safe_dict(capability.get("script"))
        kind = _safe_text(script.get("kind"), 80).lower()
        if kind != "powershell":
            return {"ok": False, "reason": f"unsupported_script_kind:{kind}", "errors": ["unsupported_script_kind"]}

        script_path = Path(_safe_text(script.get("resolved_path"), 1000))
        if not script_path.exists() or not script_path.is_file():
            return {"ok": False, "reason": "script_missing", "errors": [f"script_missing:{script_path}"]}

        cwd_raw = _safe_text(script.get("working_directory"), 1000) or "."
        cwd_path = Path(cwd_raw)
        resolved_cwd = (cwd_path if cwd_path.is_absolute() else base_dir / cwd_path).resolve()
        try:
            resolved_cwd.relative_to(base_dir)
        except ValueError:
            return {
                "ok": False,
                "reason": "working_directory_outside_base",
                "errors": [f"working_directory_outside_base:{cwd_raw}"],
            }
        if not resolved_cwd.exists() or not resolved_cwd.is_dir():
            return {"ok": False, "reason": "working_directory_missing", "errors": [f"working_directory_missing:{resolved_cwd}"]}

        executable = powershell_executable or self._powershell_executable()
        if not executable:
            return {"ok": False, "reason": "powershell_not_found", "errors": ["powershell_not_found"]}

        args_json = json.dumps(args or {}, ensure_ascii=True, sort_keys=True)
        command = [
            executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-ArgsJson",
            args_json,
        ]
        return {
            "ok": True,
            "command": command,
            "cwd": str(resolved_cwd),
            "timeout_ms": max(1, int(script.get("timeout_ms") or 1)),
            "command_summary": {
                "kind": kind,
                "executable": executable,
                "script_path": str(script_path),
                "cwd": str(resolved_cwd),
                "arg_keys": sorted(list(args.keys())),
            },
            "errors": [],
        }

    def _run_process(
        self,
        command: list[str],
        *,
        cwd: Path,
        timeout_ms: int,
        popen_factory: Any = None,
        now_fn: Any = None,
    ) -> dict[str, Any]:
        factory = popen_factory or subprocess.Popen
        timeout_sec = max(0.001, float(timeout_ms) / 1000.0)
        try:
            process = factory(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=timeout_sec)
            except subprocess.TimeoutExpired as exc:
                partial_stdout = self._decode_partial(exc.stdout)
                partial_stderr = self._decode_partial(exc.stderr)
                try:
                    process.kill()
                    killed = True
                except Exception:
                    killed = False
                try:
                    tail_stdout, tail_stderr = process.communicate()
                except Exception:
                    tail_stdout, tail_stderr = "", ""
                return {
                    "status": "timeout",
                    "reason": "timeout",
                    "exit_code": None,
                    "timed_out": True,
                    "killed": killed,
                    "stdout": self._join_output(partial_stdout, tail_stdout),
                    "stderr": self._join_output(partial_stderr, tail_stderr),
                    "errors": [f"timeout_ms:{timeout_ms}"],
                }
            exit_code = int(getattr(process, "returncode", 0) or 0)
            return {
                "status": "success" if exit_code == 0 else "failed",
                "reason": "" if exit_code == 0 else "nonzero_exit",
                "exit_code": exit_code,
                "timed_out": False,
                "killed": False,
                "stdout": stdout or "",
                "stderr": stderr or "",
                "errors": [] if exit_code == 0 else [f"exit_code:{exit_code}"],
            }
        except Exception as exc:
            return {
                "status": "error",
                "reason": "execution_error",
                "exit_code": None,
                "timed_out": False,
                "killed": False,
                "stdout": "",
                "stderr": "",
                "errors": [f"execution_error:{exc}"],
            }

    def _base_row(
        self,
        *,
        request_id: str,
        started: float,
        capability_name: str,
        registry_path: Path,
        base_dir: Path,
        args: dict[str, Any],
        prepared: dict[str, Any],
    ) -> dict[str, Any]:
        capability = _safe_dict(prepared.get("capability"))
        script = _safe_dict(capability.get("script"))
        return {
            "schema": "nova.os_capability_ledger.v1",
            "request_id": request_id,
            "ts_epoch": started,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started)),
            "capability": _safe_text(capability.get("name") or capability_name, 120),
            "contract_version": _safe_text(capability.get("contract_version"), 40),
            "authority_level": _safe_text(capability.get("authority_level"), 80),
            "mutating": bool(capability.get("mutating", False)),
            "locality": _safe_text(capability.get("locality"), 80),
            "registry_path": str(registry_path),
            "base_dir": str(base_dir),
            "script_path": _safe_text(script.get("resolved_path"), 1000),
            "script_sha256": _safe_text(script.get("sha256"), 128),
            "args": _compact(args or {}),
            "prepare": {
                "ok": bool(prepared.get("ok")),
                "reason": _safe_text(prepared.get("reason"), 120),
                "operator_outbox": bool(prepared.get("operator_outbox")),
                "errors": _safe_list(prepared.get("errors")),
                "execution_hash": _compact(prepared.get("execution_hash") or {}),
            },
        }

    @staticmethod
    def _append_ledger(path: Path, row: dict[str, Any]) -> dict[str, Any]:
        ledger_path = Path(path)
        try:
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with ledger_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
            return {"status": "recorded", "path": str(ledger_path)}
        except Exception as exc:
            return {"status": f"record_failed:{exc}", "path": str(ledger_path)}

    @staticmethod
    def _request_id(started: float, *, uuid_fn: Any = None) -> str:
        suffix = _safe_text((uuid_fn or (lambda: uuid.uuid4().hex))(), 12)
        return f"oscap_{int(started * 1000):013d}_{suffix}"

    @staticmethod
    def _duration_ms(started: float, *, now_fn: Any = None) -> int:
        return max(0, int((float((now_fn or time.time)()) - started) * 1000))

    @staticmethod
    def _powershell_executable() -> str:
        return shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe") or ""

    @staticmethod
    def _limit_text(value: Any, limit: int = MAX_LEDGER_TEXT_CHARS) -> str:
        text = str(value or "")
        if len(text) <= limit:
            return text
        return text[-limit:]

    @staticmethod
    def _decode_partial(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    @staticmethod
    def _join_output(first: Any, second: Any) -> str:
        left = str(first or "")
        right = str(second or "")
        if left and right and not left.endswith("\n"):
            return left + "\n" + right
        return left + right

    @staticmethod
    def _result_from_row(row: dict[str, Any], *, ledger: dict[str, Any]) -> dict[str, Any]:
        status = _safe_text(row.get("status"), 80)
        ledger_status = _safe_text(ledger.get("status"), 200)
        return {
            "ok": status == "success" and ledger_status == "recorded",
            "status": status,
            "reason": _safe_text(row.get("reason"), 120),
            "operator_outbox": bool(row.get("operator_outbox")),
            "executed": bool(row.get("executed")),
            "ledger": ledger,
            "row": row,
        }


OS_SCRIPT_CONTROLLER_SERVICE = OsScriptControllerService()
