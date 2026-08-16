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
    wmi_create_fn=None,
    popen_fn=None,
) -> tuple[bool, int | None, str]:
    """Start argv so it outlives this process. Returns (ok, pid, detail)."""
    command = [str(item) for item in list(argv or []) if str(item)]
    if len(command) < 2:
        return False, None, "command_required"
    workdir = str(Path(cwd))
    if os.name == "nt":
        creator = wmi_create_fn or _wmi_create_process
        ok, pid, detail = creator(quote_windows_command(command), workdir)
        if ok:
            return True, pid, detail
        return False, None, detail or "wmi_failed"
    starter = popen_fn or subprocess.Popen
    try:
        proc = starter(
            command,
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        return False, None, f"popen_failed:{exc}"
    pid = int(getattr(proc, "pid", 0) or 0)
    return True, (pid or None), "posix_detached"


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
