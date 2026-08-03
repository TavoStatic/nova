from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


# Proven clean-install target. 3.14 fails (e.g. winsdk has no wheel).
SUPPORTED_PYTHON = (3, 12)
SUPPORTED_PYTHON_LABEL = "3.12"
WINGET_PYTHON_ID = "Python.Python.3.12"
WINGET_OLLAMA_ID = "Ollama.Ollama"
DEFAULT_OLLAMA_BASE = "http://127.0.0.1:11434"
DEFAULT_WEBUI_PORT = 18088

# Approximate on-disk download size (GB) for Ollama pulls — used for preflight
# disk checks before multi-GB model downloads begin.
_MODEL_DISK_GB: dict[str, float] = {
    "llama3.2:3b": 2.0,
    "qwen2.5:7b": 4.7,
    "qwen2.5vl:7b": 5.5,
    "llama3.1:8b": 4.7,
    "qwen2.5:14b": 9.0,
    "qwen2.5vl:14b": 9.0,
}
_MODEL_DISK_BUFFER = 1.25  # spare for layers, unpack, OS headroom
# Full base install budget (Python runtime + venv libraries + headroom).
# Measured against heavy requirements (opencv, scipy, faster-whisper, onnx, etc.).
_DISK_PYTHON_INSTALL_GB = 0.75  # winget/python.org install footprint
_DISK_VENV_LIBRARIES_GB = 7.0  # pip deps into .venv (wheels + unpack)
_DISK_OLLAMA_APP_GB = 1.5  # Ollama application install
_DISK_RUNTIME_HEADROOM_GB = 2.0  # logs, runtime state, unpack temp
_MIN_FREE_DISK_GB_BASE = (
    _DISK_PYTHON_INSTALL_GB + _DISK_VENV_LIBRARIES_GB + _DISK_RUNTIME_HEADROOM_GB
)  # ~9.75 GB without models/Ollama

_SETUP_MUTEX_NAME = "Local\\NovaSetupWizardSingleton"
_setup_lock_handle: Any = None
_setup_lock_depth = 0


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def acquire_setup_singleton() -> tuple[bool, str]:
    """Ensure only one setup wizard process runs at a time (Windows mutex + lock file)."""

    global _setup_lock_handle, _setup_lock_depth
    if _setup_lock_handle is not None:
        _setup_lock_depth += 1
        return True, f"nested_hold depth={_setup_lock_depth}"

    # Windows named mutex — covers multiple double-clicks of NovaSetup.exe.
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateMutexW(None, False, _SETUP_MUTEX_NAME)
            last_error = int(kernel32.GetLastError() or 0)
            ERROR_ALREADY_EXISTS = 183
            if not handle:
                return False, "mutex_create_failed"
            if last_error == ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(handle)
                return False, "another_nova_setup_is_already_running"
            _setup_lock_handle = ("mutex", handle)
            _setup_lock_depth = 1
            return True, "mutex_acquired"
        except Exception as exc:
            # Fall through to lock file.
            last_mutex_error = str(exc)
    else:
        last_mutex_error = "non_windows"

    lock_dir = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".nova") / "Nova"
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        lock_dir = Path.cwd()
    lock_path = lock_dir / "setup_wizard.lock"
    try:
        fh = open(lock_path, "a+b")
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            if fh.read(1) == b"":
                fh.write(b"0")
                fh.flush()
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()).encode("ascii", errors="ignore"))
        fh.flush()
        _setup_lock_handle = ("file", fh, lock_path)
        _setup_lock_depth = 1
        return True, f"lock_file:{lock_path}"
    except Exception as exc:
        return False, f"lock_failed:{exc};mutex={last_mutex_error}"


def release_setup_singleton() -> None:
    global _setup_lock_handle, _setup_lock_depth
    if _setup_lock_handle is None:
        _setup_lock_depth = 0
        return
    _setup_lock_depth = max(0, int(_setup_lock_depth) - 1)
    if _setup_lock_depth > 0:
        return
    handle = _setup_lock_handle
    _setup_lock_handle = None
    if not handle:
        return
    kind = handle[0]
    try:
        if kind == "mutex" and os.name == "nt":
            import ctypes

            ctypes.windll.kernel32.CloseHandle(handle[1])
        elif kind == "file":
            fh = handle[1]
            lock_path = handle[2] if len(handle) > 2 else None
            if os.name == "nt":
                import msvcrt

                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
            else:
                import fcntl

                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
            try:
                fh.close()
            except Exception:
                pass
            if lock_path:
                try:
                    Path(lock_path).unlink(missing_ok=True)
                except Exception:
                    pass
    except Exception:
        pass


def _step(
    name: str,
    *,
    ok: bool,
    required: bool = True,
    action: str = "check",
    detail: str = "",
    messages: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "required": bool(required),
        "action": str(action or "check"),
        "detail": str(detail or ""),
        "messages": list(messages or []),
    }


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else (
            (exc.stdout or b"").decode("utf-8", errors="replace") if exc.stdout else ""
        )
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else (
            (exc.stderr or b"").decode("utf-8", errors="replace") if exc.stderr else ""
        )
        return subprocess.CompletedProcess(
            command,
            124,
            stdout + "\n[setup] timed out\n",
            stderr,
        )


def _run_streaming(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 3600,
    env: dict[str, str] | None = None,
    label: str = "",
) -> subprocess.CompletedProcess[str]:
    """Run a long command while streaming stdout/stderr live for the operator.

    Wait on the *process* first, not the reader. On Windows, pip/winget child
    processes can keep the stdout pipe open after the parent exits; waiting on
    the reader forever was the real NovaSetup.exe hang after pip succeeded.
    """

    import threading

    title = str(label or " ".join(str(part) for part in command[:4])).strip()
    print(f"[setup] {title}", flush=True)
    print(f"[setup] $ {' '.join(str(part) for part in command)}", flush=True)
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    # CREATE_NO_WINDOW keeps headless/windowed exe runs quiet on Windows.
    creationflags = 0
    if os.name == "nt":
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
    process = subprocess.Popen(
        [str(part) for part in command],
        cwd=str(cwd) if cwd is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=merged_env,
        bufsize=1,
        creationflags=creationflags,
    )
    chunks: list[str] = []
    wait_timeout = max(30, int(timeout or 30))

    def _reader() -> None:
        try:
            assert process.stdout is not None
            for line in process.stdout:
                chunks.append(line)
                try:
                    print(line, end="", flush=True)
                except Exception:
                    pass
        except Exception as exc:
            chunks.append(f"\n[setup] reader_error:{exc}\n")

    reader = threading.Thread(target=_reader, name="nova-setup-stream", daemon=True)
    reader.start()
    returncode = 1
    timed_out = False
    try:
        try:
            returncode = int(process.wait(timeout=wait_timeout) or 0)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                process.kill()
            except Exception:
                pass
            try:
                returncode = int(process.wait(timeout=15) or 1)
            except Exception:
                returncode = 1
            chunks.append("\n[setup] timed out; process killed\n")
            print("[setup] timed out; process killed", flush=True)
    except Exception as exc:
        try:
            process.kill()
        except Exception:
            pass
        chunks.append(f"\n[setup] stream_failed:{exc}\n")
        print(f"[setup] stream_failed:{exc}", flush=True)
        returncode = 1
    finally:
        # Unblock the reader if a grandchild still holds the write end of the pipe.
        try:
            if process.stdout is not None:
                process.stdout.close()
        except Exception:
            pass
        reader.join(timeout=5)
        if reader.is_alive():
            chunks.append("\n[setup] reader still running after close; continuing\n")
            print("[setup] reader still running after close; continuing", flush=True)

    if timed_out and returncode == 0:
        returncode = 1
    print(f"[setup] done: {title} exit={returncode}", flush=True)
    return subprocess.CompletedProcess(command, int(returncode or 0), "".join(chunks), "")


def _which(name: str) -> str:
    return str(shutil.which(name) or "").strip()


def refresh_windows_path() -> str:
    """Rebuild this process PATH from Machine + User registry (Windows).

    winget installs update the registry PATH, but the current process keeps the
    old PATH until we merge it back in.
    """

    if os.name != "nt":
        return str(os.environ.get("PATH") or "")

    parts: list[str] = []
    try:
        import winreg  # type: ignore

        for hive, subkey in (
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, "Environment"),
        ):
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, "Path")
            except OSError:
                continue
            text = str(value or "").strip()
            if text:
                parts.extend([item for item in text.split(";") if str(item or "").strip()])
    except Exception:
        parts = [item for item in str(os.environ.get("PATH") or "").split(os.pathsep) if item]

    # Common install locations even before PATH registration settles.
    local = Path(os.environ.get("LOCALAPPDATA") or "")
    program_files = Path(os.environ.get("ProgramFiles") or r"C:\Program Files")
    for candidate in (
        local / "Programs" / "Python" / "Python312",
        local / "Programs" / "Python" / "Python312" / "Scripts",
        local / "Programs" / "Ollama",
        program_files / "Python312",
        program_files / "Python312" / "Scripts",
        program_files / "Ollama",
        local / "Nova" / "bin",
    ):
        if candidate.is_dir():
            parts.append(str(candidate))

    # Preserve process-local entries that may not be in the registry yet.
    for item in str(os.environ.get("PATH") or "").split(os.pathsep):
        clean = str(item or "").strip()
        if clean:
            parts.append(clean)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in parts:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    merged = os.pathsep.join(deduped)
    os.environ["PATH"] = merged
    return merged


def known_python312_commands() -> list[list[str]]:
    """Absolute Python 3.12 binaries that may exist after winget install."""

    commands: list[list[str]] = []
    local = Path(os.environ.get("LOCALAPPDATA") or "")
    program_files = Path(os.environ.get("ProgramFiles") or r"C:\Program Files")
    for base in (
        local / "Programs" / "Python" / "Python312" / "python.exe",
        program_files / "Python312" / "python.exe",
        Path(r"C:\Python312\python.exe"),
    ):
        if base.is_file():
            commands.append([str(base)])
    return commands


def ensure_user_path_entry(entry: str) -> tuple[bool, str]:
    """Append entry to the current-user PATH if missing. Returns (changed, detail)."""

    clean = str(entry or "").strip().rstrip("\\/")
    if not clean:
        return False, "empty_entry"
    if os.name != "nt":
        current = str(os.environ.get("PATH") or "")
        if clean.lower() in current.lower():
            return False, "already_on_path"
        os.environ["PATH"] = clean + os.pathsep + current
        return True, "updated_process_path_only"

    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            try:
                current, value_type = winreg.QueryValueEx(key, "Path")
            except OSError:
                current, value_type = "", winreg.REG_EXPAND_SZ
            text = str(current or "")
            parts = [item for item in text.split(";") if str(item or "").strip()]
            if any(str(item).rstrip("\\/").lower() == clean.lower() for item in parts):
                refresh_windows_path()
                return False, "already_on_user_path"
            parts.append(clean)
            winreg.SetValueEx(key, "Path", 0, value_type or winreg.REG_EXPAND_SZ, ";".join(parts))
        # Broadcast environment change so new shells pick it up.
        try:
            import ctypes

            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002
            result = ctypes.c_long()
            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST,
                WM_SETTINGCHANGE,
                0,
                "Environment",
                SMTO_ABORTIFHUNG,
                5000,
                ctypes.byref(result),
            )
        except Exception:
            pass
        refresh_windows_path()
        return True, f"added_user_path:{clean}"
    except Exception as exc:
        return False, f"user_path_update_failed:{exc}"


def load_policy_models(root: Path) -> dict[str, str]:
    policy_path = Path(root) / "policy.json"
    models: dict[str, str] = {}
    if not policy_path.is_file():
        return models
    try:
        data = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception:
        return models
    raw = data.get("models") if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        return models
    for key in ("chat", "routing", "vision", "coder", "embed", "embedding"):
        value = str(raw.get(key) or "").strip()
        if value and key not in {"stt_size"}:
            models[key] = value
    return models


def required_ollama_models(root: Path) -> list[str]:
    models = load_policy_models(root)
    ordered: list[str] = []
    for key in ("chat", "routing", "vision", "coder", "embed", "embedding"):
        name = str(models.get(key) or "").strip()
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def parse_python_version(text: str) -> tuple[int, int] | None:
    clean = str(text or "").strip()
    # Accept "Python 3.12.6" or "3.12.6"
    for token in clean.replace(",", " ").split():
        if token[0:1].isdigit() and "." in token:
            parts = token.split(".")
            try:
                return int(parts[0]), int(parts[1])
            except Exception:
                continue
    return None


def detect_python_candidates() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(command: list[str], label: str) -> None:
        try:
            proc = _run(command + ["--version"], timeout=30)
        except Exception as exc:
            found.append({"label": label, "command": command, "ok": False, "detail": str(exc)})
            return
        version_text = ((proc.stdout or "") + (proc.stderr or "")).strip()
        parsed = parse_python_version(version_text)
        key = " ".join(command) + "|" + version_text
        if key in seen:
            return
        seen.add(key)
        found.append(
            {
                "label": label,
                "command": command,
                "ok": proc.returncode == 0 and parsed is not None,
                "version_text": version_text,
                "version": parsed,
                "supported": parsed == SUPPORTED_PYTHON,
            }
        )

    add([sys.executable], "sys.executable")
    if _which("py"):
        add(["py", f"-{SUPPORTED_PYTHON_LABEL}"], f"py -{SUPPORTED_PYTHON_LABEL}")
        add(["py", "-3"], "py -3")
    if _which("python"):
        add(["python"], "python")
    if _which("python3"):
        add(["python3"], "python3")
    for index, command in enumerate(known_python312_commands()):
        add(command, f"known_python312_{index}")
    return found


def select_supported_python(candidates: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    rows = list(candidates if candidates is not None else detect_python_candidates())
    for row in rows:
        if bool(row.get("supported")) and bool(row.get("ok")):
            return row
    return None


def check_host(root: Path) -> dict[str, Any]:
    messages: list[str] = []
    system = platform.system().lower()
    ok = system.startswith("win")
    if not ok:
        messages.append(f"unsupported_os:{system}")
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".nova_setup_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        writable = True
    except Exception as exc:
        writable = False
        messages.append(f"not_writable:{exc}")
        ok = False
    detail = f"os={platform.system()} arch={platform.machine()} root={root}"
    return _step("host", ok=ok and writable, action="check", detail=detail, messages=messages)


def ensure_python(*, install: bool = True) -> dict[str, Any]:
    candidates = detect_python_candidates()
    selected = select_supported_python(candidates)
    if selected is not None:
        return _step(
            "python",
            ok=True,
            action="check",
            detail=f"using {selected.get('label')} ({selected.get('version_text')})",
            messages=[f"candidate={c.get('label')}:{c.get('version_text')}" for c in candidates],
        )

    messages = [f"candidate={c.get('label')}:{c.get('version_text') or c.get('detail')}" for c in candidates]
    if not install:
        return _step(
            "python",
            ok=False,
            action="check",
            detail=f"supported Python {SUPPORTED_PYTHON_LABEL}.x not found",
            messages=messages,
        )

    winget = _which("winget")
    if not winget:
        return _step(
            "python",
            ok=False,
            action="install",
            detail="winget not available; install Python 3.12 manually",
            messages=messages,
        )

    proc = _run_streaming(
        [
            winget,
            "install",
            "--id",
            WINGET_PYTHON_ID,
            "-e",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ],
        timeout=900,
        label="install Python 3.12 via winget",
    )
    messages.append(f"winget_exit={proc.returncode}")
    if (proc.stdout or "").strip():
        messages.append((proc.stdout or "")[-500:])

    # winget updates registry PATH; refresh this process and probe known install dirs.
    refresh_windows_path()
    time.sleep(1)
    selected = select_supported_python()
    if selected is None:
        # One more pass after a short settle; some installs finish PATH registration late.
        time.sleep(2)
        refresh_windows_path()
        selected = select_supported_python()
    if selected is None:
        return _step(
            "python",
            ok=False,
            action="install",
            detail=(
                f"winget finished but Python {SUPPORTED_PYTHON_LABEL} still not selectable in this process. "
                "Open a new terminal, or install Python 3.12 from python.org with Add to PATH."
            ),
            messages=messages,
        )
    return _step(
        "python",
        ok=True,
        action="install",
        detail=f"installed/using {selected.get('label')} ({selected.get('version_text')})",
        messages=messages,
    )


def ensure_venv(root: Path, python_command: list[str]) -> dict[str, Any]:
    venv_python = Path(root) / ".venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return _step("venv", ok=True, action="check", detail=str(venv_python))

    venv_dir = Path(root) / ".venv"
    proc = _run(list(python_command) + ["-m", "venv", str(venv_dir)], cwd=root, timeout=180)
    if proc.returncode != 0 or not venv_python.is_file():
        return _step(
            "venv",
            ok=False,
            action="install",
            detail="venv create failed",
            messages=[(proc.stdout or "")[-400:], (proc.stderr or "")[-400:]],
        )
    return _step("venv", ok=True, action="install", detail=str(venv_python))


def ensure_python_deps(root: Path, venv_python: Path) -> dict[str, Any]:
    requirements = Path(root) / "requirements.txt"
    if not requirements.is_file():
        return _step("python_deps", ok=False, detail="requirements.txt missing")

    upgrade = _run_streaming(
        [str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        cwd=root,
        timeout=600,
        label="pip upgrade tooling",
    )
    if upgrade.returncode != 0:
        return _step(
            "python_deps",
            ok=False,
            action="install",
            detail="pip upgrade failed",
            messages=[(upgrade.stdout or "")[-800:]],
        )

    install = _run_streaming(
        [str(venv_python), "-m", "pip", "install", "-r", str(requirements)],
        cwd=root,
        timeout=1800,
        label="pip install requirements",
    )
    if install.returncode != 0:
        return _step(
            "python_deps",
            ok=False,
            action="install",
            detail="pip install -r requirements.txt failed",
            messages=[(install.stdout or "")[-1200:]],
        )
    return _step("python_deps", ok=True, action="install", detail="requirements installed")


def ensure_doctor(root: Path, venv_python: Path) -> dict[str, Any]:
    doctor = Path(root) / "doctor.py"
    if not doctor.is_file():
        return _step("doctor", ok=False, detail="doctor.py missing")
    fix = _run([str(venv_python), str(doctor), "--fix"], cwd=root, timeout=120)
    check = _run([str(venv_python), str(doctor)], cwd=root, timeout=120)
    ok = check.returncode == 0
    return _step(
        "doctor",
        ok=ok,
        action="fix" if fix.returncode == 0 else "check",
        detail=f"fix_exit={fix.returncode} check_exit={check.returncode}",
        messages=[(check.stdout or "")[-800:]],
    )


def ollama_tags(base: str = DEFAULT_OLLAMA_BASE, timeout: float = 5.0) -> list[str]:
    try:
        with urllib.request.urlopen(f"{base.rstrip('/')}/api/tags", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
    except Exception:
        return []
    names: list[str] = []
    for item in list(payload.get("models") or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def ollama_api_up(base: str = DEFAULT_OLLAMA_BASE, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{base.rstrip('/')}/api/tags", timeout=timeout) as response:
            return 200 <= int(getattr(response, "status", 0) or 0) < 500
    except Exception:
        return False


def ensure_ollama(*, install: bool = True, base: str = DEFAULT_OLLAMA_BASE) -> dict[str, Any]:
    messages: list[str] = []
    ollama = _which("ollama")
    if not ollama and install:
        winget = _which("winget")
        if winget:
            proc = _run_streaming(
                [
                    winget,
                    "install",
                    "--id",
                    WINGET_OLLAMA_ID,
                    "-e",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ],
                timeout=900,
                label="install Ollama via winget",
            )
            messages.append(f"winget_ollama_exit={proc.returncode}")
            messages.append((proc.stdout or "")[-500:])
            refresh_windows_path()
            ollama = _which("ollama")
            if not ollama:
                # Common winget location before PATH settles.
                for candidate in (
                    Path(os.environ.get("LOCALAPPDATA") or "") / "Programs" / "Ollama" / "ollama.exe",
                    Path(os.environ.get("ProgramFiles") or r"C:\Program Files") / "Ollama" / "ollama.exe",
                ):
                    if candidate.is_file():
                        ollama = str(candidate)
                        break
        else:
            messages.append("winget not available for ollama install")

    if not ollama:
        return _step(
            "ollama",
            ok=False,
            required=True,
            action="install" if install else "check",
            detail="ollama not on PATH",
            messages=messages,
        )

    if not ollama_api_up(base=base):
        # Best-effort start
        try:
            subprocess.Popen(
                [ollama, "serve"],
                cwd=str(Path.home()),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            messages.append("started ollama serve")
        except Exception as exc:
            messages.append(f"serve_start_failed:{exc}")
        for _ in range(20):
            if ollama_api_up(base=base):
                break
            time.sleep(0.5)

    api_ok = ollama_api_up(base=base)
    return _step(
        "ollama",
        ok=api_ok,
        action="install" if install else "check",
        detail=f"binary={ollama} api={'up' if api_ok else 'down'} base={base}",
        messages=messages,
    )


def estimate_model_disk_gb(model: str) -> float:
    name = str(model or "").strip()
    if name in _MODEL_DISK_GB:
        return float(_MODEL_DISK_GB[name])
    low = name.lower()
    if "14b" in low:
        return 9.0
    if "8b" in low or "7b" in low:
        return 5.0
    if "3b" in low or "1.5b" in low:
        return 2.0
    return 5.0


def free_disk_gb(path: Path | str | None = None) -> float | None:
    try:
        target = Path(path or Path.cwd()).resolve()
        if not target.exists():
            target = target.parent if target.parent.exists() else Path.cwd()
        usage = shutil.disk_usage(str(target))
        return round(float(usage.free) / (1024 ** 3), 2)
    except Exception:
        return None


def ollama_models_dir() -> Path:
    # Default Ollama model store on Windows; fall back to user home.
    local = Path(os.environ.get("LOCALAPPDATA") or str(Path.home()))
    candidate = local / "Ollama" / "models"
    if candidate.is_dir():
        return candidate
    home = Path.home() / ".ollama" / "models"
    if home.is_dir():
        return home
    return local / "Ollama"


def model_present(name: str, installed: list[str]) -> bool:
    target = str(name or "").strip()
    if not target:
        return False
    if target in installed:
        return True
    # Accept tags like qwen2.5:7b matching qwen2.5:7b-...
    base = target.split(":", 1)[0]
    for item in installed:
        if item == target or item.startswith(target + "-") or item.startswith(target + ":"):
            return True
        if item.split(":", 1)[0] == base and ":" in target and target in item:
            return True
    # Exact family:tag match looser
    if ":" in target:
        for item in installed:
            if item.startswith(target):
                return True
    return target in installed


def ensure_sock_policy(root: Path, *, install: bool = True) -> dict[str, Any]:
    """Run SOCK hardware profile and apply model recommendations to policy.json."""

    messages: list[str] = []
    policy_path = Path(root) / "policy.json"
    try:
        from services.sock_service import apply_policy, build_diff, recommend_models, scan_hardware
    except Exception as exc:
        return _step(
            "sock_hardware",
            ok=False,
            required=False,
            detail=f"sock_service unavailable: {exc}",
        )

    try:
        hw = scan_hardware()
        rec = recommend_models(hw)
        diff = build_diff(rec, policy_path)
    except Exception as exc:
        return _step(
            "sock_hardware",
            ok=False,
            required=False,
            detail=f"hardware scan failed: {exc}",
        )

    messages.append(
        f"hardware ram_gb={hw.ram_gb} vram_gb={hw.vram_gb} gpu={hw.gpu_name!r} "
        f"cpu_cores={hw.cpu_cores} free_disk_gb={hw.storage_free_gb}"
    )
    messages.append(
        f"recommended chat={rec.chat} routing={rec.routing} vision={rec.vision} stt={rec.stt_size}"
    )
    for key, why in dict(rec.rationale or {}).items():
        messages.append(f"why_{key}={why}")
    if hw.detection_notes:
        messages.extend([f"note:{n}" for n in list(hw.detection_notes)[:8]])

    applied = False
    if install and diff.changed_keys:
        try:
            if not policy_path.is_file():
                return _step(
                    "sock_hardware",
                    ok=False,
                    detail="policy.json missing; cannot apply SOCK recommendations",
                    messages=messages,
                )
            apply_policy(rec, policy_path)
            applied = True
            messages.append(f"policy_applied changed={diff.changed_keys}")
            print(
                f"[setup] SOCK adjusted policy models for this machine: "
                f"chat={rec.chat} routing={rec.routing} vision={rec.vision}",
                flush=True,
            )
        except Exception as exc:
            messages.append(f"apply_failed:{exc}")
            return _step(
                "sock_hardware",
                ok=False,
                detail=f"SOCK recommendation ready but policy apply failed: {exc}",
                messages=messages,
            )
    elif not diff.changed_keys:
        messages.append("policy already matches SOCK recommendation")
    else:
        messages.append(f"check_only recommended_changes={diff.changed_keys}")

    detail = (
        f"ram={hw.ram_gb}GB vram={hw.vram_gb}GB gpu={hw.gpu_name or 'unknown'} "
        f"-> chat={rec.chat} routing={rec.routing} vision={rec.vision}"
        + (" (applied)" if applied else "")
    )
    return _step(
        "sock_hardware",
        ok=True,
        required=False,
        action="install" if applied else "check",
        detail=detail,
        messages=messages,
    )


def ensure_model_disk_space(root: Path, models: list[str]) -> dict[str, Any]:
    """Fail before multi-GB Ollama pulls when free disk is insufficient."""

    needed_models = [str(m).strip() for m in models if str(m).strip()]
    if not needed_models:
        return _step(
            "model_disk",
            ok=True,
            required=False,
            detail="no models to size",
        )

    estimates = {name: estimate_model_disk_gb(name) for name in needed_models}
    raw_need = sum(estimates.values())
    need_gb = round(raw_need * _MODEL_DISK_BUFFER, 2)
    # Check the volume that will hold Ollama models, and the package root volume.
    targets = [ollama_models_dir(), Path(root).resolve()]
    free_readings: list[tuple[str, float | None]] = []
    min_free: float | None = None
    for target in targets:
        free = free_disk_gb(target)
        free_readings.append((str(target), free))
        if free is None:
            continue
        if min_free is None or free < min_free:
            min_free = free

    messages = [
        f"models={needed_models}",
        f"estimates_gb={estimates}",
        f"required_gb={need_gb} (includes buffer {_MODEL_DISK_BUFFER})",
        f"free_readings={free_readings}",
    ]
    if min_free is None:
        return _step(
            "model_disk",
            ok=False,
            detail="could not determine free disk space",
            messages=messages,
        )
    if min_free < need_gb:
        print(
            f"[setup] FAIL disk space: need ~{need_gb} GB free for models, have {min_free} GB",
            flush=True,
        )
        return _step(
            "model_disk",
            ok=False,
            detail=f"insufficient disk: need>={need_gb}GB free, have={min_free}GB",
            messages=messages
            + [
                "Free disk space or choose a smaller SOCK model tier before pulling models.",
                "Ollama stores models under %LOCALAPPDATA%\\Ollama on Windows.",
            ],
        )
    print(f"[setup] Disk check OK: need ~{need_gb} GB, free {min_free} GB", flush=True)
    return _step(
        "model_disk",
        ok=True,
        detail=f"need={need_gb}GB free={min_free}GB",
        messages=messages,
    )


def install_disk_budget(
    *,
    need_python_install: bool = True,
    need_venv_libraries: bool = True,
    need_ollama_app: bool = False,
    models: list[str] | None = None,
) -> dict[str, float]:
    """Return GB budget breakdown for the selected install phases."""

    parts = {
        "python_install": _DISK_PYTHON_INSTALL_GB if need_python_install else 0.0,
        "venv_and_libraries": _DISK_VENV_LIBRARIES_GB if need_venv_libraries else 0.0,
        "ollama_app": _DISK_OLLAMA_APP_GB if need_ollama_app else 0.0,
        "runtime_headroom": _DISK_RUNTIME_HEADROOM_GB,
        "models": 0.0,
    }
    for name in list(models or []):
        parts["models"] = float(parts["models"]) + estimate_model_disk_gb(name)
    if parts["models"] > 0:
        parts["models"] = round(float(parts["models"]) * _MODEL_DISK_BUFFER, 2)
    parts["total"] = round(sum(float(v) for k, v in parts.items() if k != "total"), 2)
    return parts


def ensure_base_disk_space(
    root: Path,
    *,
    need_python_install: bool = True,
    need_venv_libraries: bool = True,
    need_ollama_app: bool = False,
    models: list[str] | None = None,
) -> dict[str, Any]:
    """Check free space for Python, venv libraries, Ollama app, and optional models."""

    budget = install_disk_budget(
        need_python_install=need_python_install,
        need_venv_libraries=need_venv_libraries,
        need_ollama_app=need_ollama_app,
        models=models,
    )
    need_gb = float(budget["total"])
    free = free_disk_gb(root)
    messages = [
        f"budget_gb={budget}",
        (
            "Includes: Python installer footprint, pip libraries "
            f"(~{_DISK_VENV_LIBRARIES_GB}GB for opencv/scipy/whisper/etc), "
            f"runtime headroom, and model downloads when selected."
        ),
    ]
    if free is None:
        return _step("base_disk", ok=False, detail="could not read free disk", messages=messages)
    messages.append(f"free_gb={free}")
    if free < need_gb:
        print(f"[setup] FAIL disk: need ~{need_gb} GB free (Python+libs+…), have {free} GB", flush=True)
        return _step(
            "base_disk",
            ok=False,
            detail=f"need>={need_gb}GB free for install budget, have={free}GB",
            messages=messages,
        )
    print(f"[setup] Disk budget OK: need ~{need_gb} GB, free {free} GB", flush=True)
    return _step("base_disk", ok=True, detail=f"need={need_gb}GB free={free}GB", messages=messages)


def ensure_ollama_models(
    root: Path,
    *,
    install: bool = True,
    base: str = DEFAULT_OLLAMA_BASE,
) -> dict[str, Any]:
    required = required_ollama_models(root)
    if not required:
        return _step("ollama_models", ok=True, required=False, detail="no models declared in policy.json")

    ollama = _which("ollama")
    if not ollama:
        return _step("ollama_models", ok=False, detail="ollama binary missing")

    installed = ollama_tags(base=base)
    missing = [name for name in required if not model_present(name, installed)]
    messages = [f"required={required}", f"installed={installed}", f"missing_before={missing}"]

    if missing and install:
        disk_step = ensure_model_disk_space(root, missing)
        messages.extend(list(disk_step.get("messages") or []))
        if not disk_step.get("ok"):
            return _step(
                "ollama_models",
                ok=False,
                action="install",
                detail=f"blocked by disk check: {disk_step.get('detail')}",
                messages=messages,
            )
        for name in missing:
            print(f"[setup] Pulling Ollama model {name} (this can take a long time)...", flush=True)
            proc = _run_streaming(
                [ollama, "pull", name],
                timeout=3600,
                label=f"ollama pull {name}",
            )
            messages.append(f"pull:{name}:exit={proc.returncode}")
            if proc.returncode != 0:
                messages.append((proc.stdout or "")[-400:])
            else:
                print(f"[setup] Finished pull: {name}", flush=True)
        installed = ollama_tags(base=base)
        missing = [name for name in required if not model_present(name, installed)]
    elif missing and not install:
        disk_step = ensure_model_disk_space(root, missing)
        messages.append(f"disk_check={disk_step.get('detail')}")

    return _step(
        "ollama_models",
        ok=not missing,
        action="install" if install else "check",
        detail=f"missing={missing}" if missing else f"present={required}",
        messages=messages,
    )


def ensure_nova_path(root: Path, *, install: bool = True) -> dict[str, Any]:
    """Register a user-level `nova` launcher so the CLI works outside the package folder."""

    package_root = Path(root).resolve()
    nova_cmd = package_root / "nova.cmd"
    messages: list[str] = []
    if not nova_cmd.is_file():
        return _step("nova_path", ok=False, detail="nova.cmd missing in package root")

    local_app = Path(os.environ.get("LOCALAPPDATA") or str(package_root))
    bin_dir = local_app / "Nova" / "bin"
    shim_cmd = bin_dir / "nova.cmd"
    how_to = (
        f"From any new terminal after PATH update: nova doctor\n"
        f"Or always: \"{nova_cmd}\" setup\n"
        f"Package root: {package_root}"
    )
    messages.append(how_to)

    if not install:
        on_path = bool(_which("nova") or _which("nova.cmd"))
        return _step(
            "nova_path",
            ok=True,
            required=False,
            action="check",
            detail="nova on PATH" if on_path else f"shim target {shim_cmd} (not registered this run)",
            messages=messages,
        )

    try:
        bin_dir.mkdir(parents=True, exist_ok=True)
        shim_body = (
            "@echo off\r\n"
            f"set \"NOVA_ROOT={package_root}\"\r\n"
            f"call \"{nova_cmd}\" %*\r\n"
        )
        shim_cmd.write_text(shim_body, encoding="utf-8")
        messages.append(f"wrote_shim:{shim_cmd}")
    except Exception as exc:
        return _step(
            "nova_path",
            ok=False,
            required=False,
            action="install",
            detail=f"failed to write nova shim: {exc}",
            messages=messages,
        )

    changed, path_detail = ensure_user_path_entry(str(bin_dir))
    messages.append(path_detail)
    refresh_windows_path()
    # Ensure current process can resolve the shim immediately.
    os.environ["PATH"] = str(bin_dir) + os.pathsep + str(os.environ.get("PATH") or "")
    on_path = bool(_which("nova") or _which("nova.cmd") or shim_cmd.is_file())
    detail = (
        f"registered {shim_cmd}; PATH {'updated' if changed else 'already contained bin'}; "
        f"open a new terminal then run: nova doctor"
    )
    return _step(
        "nova_path",
        ok=on_path,
        required=False,
        action="install",
        detail=detail,
        messages=messages,
    )


def ensure_smoke_base(root: Path, venv_python: Path) -> dict[str, Any]:
    smoke = Path(root) / "scripts" / "smoke_test.py"
    if not smoke.is_file():
        smoke = Path(root) / "smoke_test.py"
    if not smoke.is_file():
        return _step("smoke_base", ok=False, detail="smoke_test.py missing")
    proc = _run([str(venv_python), str(smoke), "--tier", "base"], cwd=root, timeout=600)
    return _step(
        "smoke_base",
        ok=proc.returncode == 0,
        action="check",
        detail=f"exit={proc.returncode}",
        messages=[((proc.stdout or "") + (proc.stderr or ""))[-800:]],
    )


def _kill_listeners_on_port(port: int) -> list[str]:
    """Best-effort kill of listeners on a TCP port (setup smoke only)."""

    notes: list[str] = []
    if os.name != "nt" or port <= 0:
        return notes
    try:
        # Prefer PowerShell NetTCPConnection when it returns quickly; fall back to taskkill by pid.
        probe = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    f"$conns = Get-NetTCPConnection -LocalPort {int(port)} -State Listen "
                    "-ErrorAction SilentlyContinue; "
                    "$conns | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        pids = []
        for line in (probe.stdout or "").splitlines():
            text = line.strip()
            if text.isdigit():
                pids.append(int(text))
        for pid in pids:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                notes.append(f"killed_pid={pid}")
            except Exception as exc:
                notes.append(f"kill_failed:{pid}:{exc}")
    except Exception as exc:
        notes.append(f"port_kill_probe_failed:{exc}")
    return notes


def ensure_webui(root: Path, *, port: int = DEFAULT_WEBUI_PORT) -> dict[str, Any]:
    """Start nova_http directly, hit /api/health, then kill it.

    Avoids `nova webui-start/stop` during setup: those paths can hang forever on
    Windows CIM / Get-NetTCPConnection under load (seen in real NovaSetup.exe sandbox).
    """

    base = Path(root)
    venv_python = base / ".venv" / "Scripts" / "python.exe"
    http_py = base / "nova_http.py"
    messages: list[str] = []
    if not venv_python.is_file():
        return _step("webui", ok=False, detail="venv python missing")
    if not http_py.is_file():
        return _step("webui", ok=False, detail="nova_http.py missing")

    messages.extend(_kill_listeners_on_port(int(port)))
    url = f"http://127.0.0.1:{int(port)}/api/health"
    creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0) if os.name == "nt" else 0
    process: subprocess.Popen[str] | None = None
    health_ok = False
    try:
        process = subprocess.Popen(
            [str(venv_python), str(http_py), "--host", "127.0.0.1", "--port", str(int(port))],
            cwd=str(base),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        messages.append(f"started_pid={process.pid}")
        deadline = time.time() + 45
        while time.time() < deadline:
            if process.poll() is not None:
                messages.append(f"webui_exited_early={process.returncode}")
                break
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if 200 <= int(getattr(response, "status", 0) or 0) < 300:
                        health_ok = True
                        break
            except Exception:
                time.sleep(0.5)
        messages.append(f"health={'ok' if health_ok else 'fail'} url={url}")
    except Exception as exc:
        messages.append(f"start_failed:{exc}")
    finally:
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=8)
                messages.append("terminated")
            except Exception:
                try:
                    process.kill()
                    messages.append("killed")
                except Exception as exc:
                    messages.append(f"stop_failed:{exc}")
        messages.extend(_kill_listeners_on_port(int(port)))

    return _step(
        "webui",
        ok=health_ok,
        action="check",
        detail=f"port={port}",
        messages=messages,
    )


def ensure_shell_first_admin(root: Path, *, install: bool = True) -> dict[str, Any]:
    """
    Ensure Nova Shell identity store exists and first account_admin is created when possible.

    Non-interactive create uses:
      NOVA_SHELL_ADMIN_USER
      NOVA_SHELL_ADMIN_PASSWORD
      NOVA_SHELL_ADMIN_DISPLAY (optional)

    If credentials are not provided and no admin exists, returns a required=False
    warning step with instructions to run scripts/setup_nova_shell.py (headless
    field installs must set the env vars or run shell setup after).
    """
    messages: list[str] = []
    base = Path(root)
    shell_runtime = base / "runtime" / "nova_shell"
    db_path = shell_runtime / "nova_shell.db"

    try:
        import argon2  # noqa: F401

        messages.append("argon2:available")
    except ImportError:
        messages.append("argon2:missing — pip install argon2-cffi (or reinstall requirements.txt)")

    try:
        from services.nova_shell.admin import ShellAdmin
        from services.nova_shell.auth import ShellAuth
        from services.nova_shell.identity import load_or_create_identity
        from services.nova_shell.store import ShellStore
    except Exception as exc:
        return _step(
            "shell_admin",
            ok=False,
            required=False,
            action="check",
            detail=f"shell_import_failed:{exc}",
            messages=messages,
        )

    try:
        identity = load_or_create_identity(shell_runtime)
        messages.append(f"installation_id={identity.installation_id}")
        store = ShellStore(db_path=db_path)
        auth = ShellAuth(store)
        admin = ShellAdmin(store, auth)
    except Exception as exc:
        return _step(
            "shell_admin",
            ok=False,
            required=False,
            action="install" if install else "check",
            detail=f"shell_store_failed:{exc}",
            messages=messages,
        )

    if admin.first_admin_exists():
        return _step(
            "shell_admin",
            ok=True,
            required=False,
            action="check",
            detail="account_admin already exists",
            messages=messages,
        )

    if not install:
        return _step(
            "shell_admin",
            ok=False,
            required=False,
            action="check",
            detail="no account_admin; check-only mode",
            messages=messages,
        )

    username = str(os.environ.get("NOVA_SHELL_ADMIN_USER") or "").strip()
    password = str(os.environ.get("NOVA_SHELL_ADMIN_PASSWORD") or "")
    display = str(os.environ.get("NOVA_SHELL_ADMIN_DISPLAY") or username).strip() or username

    if not username or not password:
        return _step(
            "shell_admin",
            ok=False,
            required=False,
            action="install",
            detail=(
                "no account_admin created — set NOVA_SHELL_ADMIN_USER and "
                "NOVA_SHELL_ADMIN_PASSWORD, or run: python scripts/setup_nova_shell.py"
            ),
            messages=messages
            + [
                "Shell accounts are separate from control-panel API login.",
                "First admin role: account_admin",
            ],
        )

    try:
        user = admin.create_first_admin(username, password, display)
        messages.append(f"created_user={user.get('username')}")
        return _step(
            "shell_admin",
            ok=True,
            required=False,
            action="install",
            detail=f"created account_admin user={user.get('username')}",
            messages=messages,
        )
    except Exception as exc:
        return _step(
            "shell_admin",
            ok=False,
            required=False,
            action="install",
            detail=f"create_first_admin_failed:{exc}",
            messages=messages,
        )


def run_setup_wizard(
    root: Path | str | None = None,
    *,
    install: bool = True,
    include_ollama: bool = True,
    include_models: bool = True,
    include_webui: bool = True,
    include_smoke: bool = True,
    register_path: bool = True,
    webui_port: int = DEFAULT_WEBUI_PORT,
    report_path: Path | str | None = None,
) -> dict[str, Any]:
    """Run the full setup wizard: check, install where possible, verify, report."""

    base = Path(root or Path(__file__).resolve().parents[1]).resolve()
    steps: list[dict[str, Any]] = []
    started = _now()

    locked, lock_detail = acquire_setup_singleton()
    if not locked:
        report = {
            "generated_at": _now(),
            "started_at": started,
            "finished_at": _now(),
            "root": str(base),
            "ok": False,
            "required_failed": ["singleton"],
            "steps": [
                _step(
                    "singleton",
                    ok=False,
                    detail="Another Nova Setup is already running. Close it and try again.",
                    messages=[lock_detail],
                )
            ],
            "required_models": required_ollama_models(base),
            "operator_next_steps": ["Only one Nova Setup window/process may run at a time."],
        }
        print("[setup] Another setup instance is already running — exiting.", flush=True)
        return report

    try:
        steps.append(check_host(base))

        # Early budget: Python + libraries (+ Ollama app if selected). Models sized after SOCK.
        need_python = select_supported_python() is None
        steps.append(
            ensure_base_disk_space(
                base,
                need_python_install=need_python and install,
                need_venv_libraries=install,
                need_ollama_app=include_ollama and install and not _which("ollama"),
                models=None,
            )
        )

        # Always start from a refreshed PATH so winget/prior installs are visible.
        if os.name == "nt":
            refresh_windows_path()

        python_step = ensure_python(install=install)
        steps.append(python_step)
        selected = select_supported_python() if python_step.get("ok") else None
        python_command = list(selected.get("command") or [sys.executable]) if selected else [sys.executable]

        venv_step = (
            ensure_venv(base, python_command)
            if python_step.get("ok")
            else _step("venv", ok=False, detail="skipped; python not ready")
        )
        steps.append(venv_step)
        venv_python = base / ".venv" / "Scripts" / "python.exe"

        if venv_step.get("ok") and venv_python.is_file():
            if install:
                # Re-check library space right before the heavy pip install.
                lib_disk = ensure_base_disk_space(
                    base,
                    need_python_install=False,
                    need_venv_libraries=True,
                    need_ollama_app=False,
                    models=None,
                )
                steps.append({**lib_disk, "name": "library_disk"})
                if not lib_disk.get("ok"):
                    steps.append(_step("python_deps", ok=False, detail="skipped; insufficient disk for libraries"))
                else:
                    print("[setup] Installing Python dependencies (can take several minutes)...", flush=True)
                    steps.append(ensure_python_deps(base, venv_python))
            else:
                steps.append(_step("python_deps", ok=venv_python.is_file(), detail="check-only"))
            if any(s.get("name") == "python_deps" and s.get("ok") for s in steps):
                print("[setup] Running doctor --fix / doctor...", flush=True)
                steps.append(ensure_doctor(base, venv_python))
            else:
                steps.append(_step("doctor", ok=False, detail="skipped; deps not ready"))
        else:
            steps.append(_step("python_deps", ok=False, detail="skipped; venv not ready"))
            steps.append(_step("doctor", ok=False, detail="skipped; venv not ready"))

        # SOCK first so policy models match this machine before any multi-GB pulls.
        print("[setup] SOCK hardware scan / policy adjust...", flush=True)
        sock_step = ensure_sock_policy(base, install=install)
        steps.append(sock_step)

        if include_ollama:
            print("[setup] Ensuring Ollama...", flush=True)
            ollama_step = ensure_ollama(install=install)
            steps.append(ollama_step)
            if include_models:
                if ollama_step.get("ok"):
                    # Disk gate runs inside ensure_ollama_models for missing pulls.
                    print("[setup] Ensuring Ollama models...", flush=True)
                    steps.append(ensure_ollama_models(base, install=install))
                else:
                    steps.append(_step("ollama_models", ok=False, detail="skipped; ollama not ready"))
        else:
            steps.append(_step("ollama", ok=True, required=False, detail="skipped by flag"))
            steps.append(_step("ollama_models", ok=True, required=False, detail="skipped by flag"))

        if include_smoke and venv_python.is_file() and any(s.get("name") == "doctor" and s.get("ok") for s in steps):
            print("[setup] Running smoke-base...", flush=True)
            steps.append(ensure_smoke_base(base, venv_python))
        else:
            steps.append(
                _step(
                    "smoke_base",
                    ok=False if include_smoke else True,
                    required=include_smoke,
                    detail="skipped",
                )
            )

        if include_webui:
            print(f"[setup] WebUI smoke on port {webui_port}...", flush=True)
            steps.append(ensure_webui(base, port=int(webui_port)))
        else:
            steps.append(_step("webui", ok=True, required=False, detail="skipped by flag"))

        if register_path:
            print("[setup] Registering user PATH launcher...", flush=True)
            steps.append(ensure_nova_path(base, install=install))
        else:
            steps.append(_step("nova_path", ok=True, required=False, detail="skipped by flag"))

        # Nova Shell first account (optional unless env credentials provided).
        print("[setup] Nova Shell first admin...", flush=True)
        steps.append(ensure_shell_first_admin(base, install=install))

        print("[setup] Writing report...", flush=True)

        required_failed = [s["name"] for s in steps if s.get("required") and not s.get("ok")]
        path_step = next((s for s in steps if s.get("name") == "nova_path"), {})
        shell_step = next((s for s in steps if s.get("name") == "shell_admin"), {})
        next_steps = [
            f"Package root: {base}",
            "Open a NEW terminal after PATH registration.",
            "Then run: nova doctor",
            f"Or: \"{base / 'nova.cmd'}\" doctor",
            str((path_step or {}).get("detail") or ""),
        ]
        if shell_step and not shell_step.get("ok"):
            next_steps.append(
                "Create Nova Shell admin: set NOVA_SHELL_ADMIN_USER + NOVA_SHELL_ADMIN_PASSWORD "
                "and re-run setup, or: python scripts/setup_nova_shell.py"
            )
        report = {
            "generated_at": _now(),
            "started_at": started,
            "finished_at": _now(),
            "root": str(base),
            "supported_python": SUPPORTED_PYTHON_LABEL,
            "install": bool(install),
            "include_ollama": bool(include_ollama),
            "include_models": bool(include_models),
            "ok": len(required_failed) == 0,
            "required_failed": required_failed,
            "steps": steps,
            "required_models": required_ollama_models(base),
            "singleton": lock_detail,
            "operator_next_steps": [s for s in next_steps if str(s).strip()],
        }

        out = Path(report_path) if report_path else (base / "runtime" / "setup_wizard_report.json")
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=2), encoding="utf-8")
            report["report_path"] = str(out)
        except Exception as exc:
            report["report_path_error"] = str(exc)

        return report
    finally:
        release_setup_singleton()


def render_setup_report(report: dict[str, Any]) -> str:
    lines = [
        "Nova Setup Wizard",
        "-----------------",
        f"root: {report.get('root')}",
        f"supported_python: {report.get('supported_python')}",
        f"ok: {report.get('ok')}",
        f"required_failed: {report.get('required_failed')}",
        f"required_models: {report.get('required_models')}",
        "",
        "steps:",
    ]
    for step in list(report.get("steps") or []):
        if not isinstance(step, dict):
            continue
        mark = "OK" if step.get("ok") else ("FAIL" if step.get("required") else "WARN")
        lines.append(
            f"  [{mark}] {step.get('name')} ({step.get('action')}) :: {step.get('detail')}"
        )
    next_steps = [str(item).strip() for item in list(report.get("operator_next_steps") or []) if str(item).strip()]
    if next_steps:
        lines.append("")
        lines.append("next:")
        for item in next_steps:
            lines.append(f"  - {item}")
    if report.get("report_path"):
        lines.append("")
        lines.append(f"report: {report.get('report_path')}")
    return "\n".join(lines)
