"""Spawn a process that does not die with the caller.

Popen DETACHED/BREAKAWAY still leaves the child in this host's agent/shell
job. Win32_Process.Create (WMI) does not. On Windows that is the only
accepted start. If WMI cannot create the process, fail out loud.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def quote_windows_command(argv: list[str]) -> str:
    parts: list[str] = []
    for raw in argv:
        text = str(raw or "")
        if not text:
            parts.append('""')
            continue
        if any(ch in text for ch in (" ", "\t", '"')):
            parts.append('"' + text.replace('"', '\\"') + '"')
        else:
            parts.append(text)
    return " ".join(parts)


def spawn_unattached(
    argv: list[str],
    *,
    cwd: str | Path,
    stdout_path: str | Path | None = None,
    stderr_path: str | Path | None = None,
    exit_code_path: str | Path | None = None,
    wmi_create_fn=None,
    popen_fn=None,
) -> tuple[bool, int | None, str]:
    """Start argv so it outlives this process. Returns (ok, pid, detail)."""
    command = [str(item) for item in list(argv or []) if str(item)]
    if len(command) < 2:
        return False, None, "command_required"
    workdir = os.fspath(cwd)
    if os.name == "nt":
        creator = wmi_create_fn or _wmi_create_process
        command_text = quote_windows_command(command)
        if stdout_path or stderr_path or exit_code_path:
            command_text = _quote_windows_redirected_command(
                command_text,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                exit_code_path=exit_code_path,
            )
        ok, pid, detail = creator(command_text, workdir)
        if ok:
            return True, pid, detail
        return False, None, detail or "wmi_failed"
    starter = popen_fn or subprocess.Popen
    stdout_handle = None
    stderr_handle = None
    try:
        if stdout_path:
            stdout_handle = open(stdout_path, "ab")
        if stderr_path:
            stderr_handle = open(stderr_path, "ab")
        proc = starter(
            command,
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle or subprocess.DEVNULL,
            stderr=stderr_handle or subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        return False, None, f"popen_failed:{exc}"
    finally:
        if stdout_handle:
            stdout_handle.close()
        if stderr_handle:
            stderr_handle.close()
    pid = int(getattr(proc, "pid", 0) or 0)
    return True, (pid or None), "posix_detached"


def _quote_windows_redirected_command(
    command_text: str,
    *,
    stdout_path: str | Path | None,
    stderr_path: str | Path | None,
    exit_code_path: str | Path | None,
) -> str:
    stdout_text = str(stdout_path) if stdout_path else "NUL"
    stderr_text = str(stderr_path) if stderr_path else "NUL"
    exit_text = str(exit_code_path) if exit_code_path else ""
    command = f'cmd.exe /d /v:on /s /c "{command_text} 1>"{stdout_text}" 2>"{stderr_text}"'
    if exit_text:
        command += f' & echo !ERRORLEVEL! >"{exit_text}"'
    return command + '"'


def _wmi_create_process(command: str, cwd: str) -> tuple[bool, int | None, str]:
    env = os.environ.copy()
    env["NOVA_DETACH_CMD"] = str(command)
    env["NOVA_DETACH_CWD"] = str(cwd)
    script = (
        "$cmd = [Environment]::GetEnvironmentVariable('NOVA_DETACH_CMD','Process');"
        "$dir = [Environment]::GetEnvironmentVariable('NOVA_DETACH_CWD','Process');"
        "$r = ([wmiclass]'Win32_Process').Create($cmd, $dir);"
        "if ($null -eq $r) { Write-Output 'err:no_result'; exit 1 };"
        "Write-Output ('ok:' + [string]$r.ReturnValue + ':' + [string]$r.ProcessId)"
    )
    try:
        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )
    except Exception as exc:
        return False, None, f"wmi_launch_failed:{exc}"
    line = str(proc.stdout or "").strip().splitlines()
    text = line[-1] if line else ""
    if not text.startswith("ok:"):
        err = str(proc.stderr or text or "wmi_no_output").strip()[:240]
        return False, None, f"wmi_failed:{err}"
    parts = text.split(":", 2)
    try:
        return_value = int(parts[1])
        pid = int(parts[2]) if len(parts) > 2 and str(parts[2]).isdigit() else 0
    except (TypeError, ValueError, IndexError):
        return False, None, f"wmi_parse_failed:{text}"
    if return_value != 0 or pid <= 0:
        return False, None, f"wmi_create_failed:{return_value}:{pid}"
    return True, pid, f"wmi_created:{pid}"
