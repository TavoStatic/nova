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


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


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
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _which(name: str) -> str:
    return str(shutil.which(name) or "").strip()


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

    proc = _run(
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
    )
    messages.append(f"winget_exit={proc.returncode}")
    if (proc.stdout or "").strip():
        messages.append((proc.stdout or "")[-500:])
    if (proc.stderr or "").strip():
        messages.append((proc.stderr or "")[-500:])

    # Refresh detection after install.
    time.sleep(2)
    selected = select_supported_python()
    if selected is None:
        return _step(
            "python",
            ok=False,
            action="install",
            detail=f"installed via winget but Python {SUPPORTED_PYTHON_LABEL} still not selectable; open a new shell or reinstall",
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

    upgrade = _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], cwd=root, timeout=600)
    if upgrade.returncode != 0:
        return _step(
            "python_deps",
            ok=False,
            action="install",
            detail="pip upgrade failed",
            messages=[(upgrade.stdout or "")[-500:], (upgrade.stderr or "")[-500:]],
        )

    install = _run(
        [str(venv_python), "-m", "pip", "install", "-r", str(requirements)],
        cwd=root,
        timeout=1800,
    )
    if install.returncode != 0:
        tail = ((install.stdout or "") + "\n" + (install.stderr or ""))[-1200:]
        return _step(
            "python_deps",
            ok=False,
            action="install",
            detail="pip install -r requirements.txt failed",
            messages=[tail],
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
            proc = _run(
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
            )
            messages.append(f"winget_ollama_exit={proc.returncode}")
            messages.append(((proc.stdout or "") + (proc.stderr or ""))[-500:])
            ollama = _which("ollama")
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
        for name in missing:
            proc = _run([ollama, "pull", name], timeout=3600)
            messages.append(f"pull:{name}:exit={proc.returncode}")
            if proc.returncode != 0:
                messages.append(((proc.stdout or "") + (proc.stderr or ""))[-400:])
        installed = ollama_tags(base=base)
        missing = [name for name in required if not model_present(name, installed)]

    return _step(
        "ollama_models",
        ok=not missing,
        action="install" if install else "check",
        detail=f"missing={missing}" if missing else f"present={required}",
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


def ensure_webui(root: Path, *, port: int = DEFAULT_WEBUI_PORT) -> dict[str, Any]:
    nova_cmd = Path(root) / "nova.cmd"
    if not nova_cmd.is_file():
        return _step("webui", ok=False, detail="nova.cmd missing")

    start = _run(
        ["cmd", "/c", str(nova_cmd), "webui-start", "--host", "127.0.0.1", "--port", str(port)],
        cwd=root,
        timeout=180,
    )
    messages = [f"start_exit={start.returncode}", ((start.stdout or "") + (start.stderr or ""))[-500:]]
    health_ok = False
    if start.returncode == 0:
        url = f"http://127.0.0.1:{port}/api/health"
        for _ in range(20):
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    health_ok = 200 <= int(getattr(response, "status", 0) or 0) < 300
                    if health_ok:
                        break
            except Exception:
                time.sleep(0.5)
        messages.append(f"health={'ok' if health_ok else 'fail'} url={url}")

    stop = _run(
        ["cmd", "/c", str(nova_cmd), "webui-stop", "--port", str(port)],
        cwd=root,
        timeout=90,
    )
    messages.append(f"stop_exit={stop.returncode}")
    return _step(
        "webui",
        ok=start.returncode == 0 and health_ok,
        action="check",
        detail=f"port={port}",
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
    webui_port: int = DEFAULT_WEBUI_PORT,
    report_path: Path | str | None = None,
) -> dict[str, Any]:
    """Run the full setup wizard: check, install where possible, verify, report."""

    base = Path(root or Path(__file__).resolve().parents[1]).resolve()
    steps: list[dict[str, Any]] = []
    started = _now()

    steps.append(check_host(base))

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
        steps.append(ensure_python_deps(base, venv_python) if install else _step("python_deps", ok=venv_python.is_file(), detail="check-only"))
        steps.append(ensure_doctor(base, venv_python))
    else:
        steps.append(_step("python_deps", ok=False, detail="skipped; venv not ready"))
        steps.append(_step("doctor", ok=False, detail="skipped; venv not ready"))

    if include_ollama:
        ollama_step = ensure_ollama(install=install)
        steps.append(ollama_step)
        if include_models:
            if ollama_step.get("ok"):
                steps.append(ensure_ollama_models(base, install=install))
            else:
                steps.append(_step("ollama_models", ok=False, detail="skipped; ollama not ready"))
    else:
        steps.append(_step("ollama", ok=True, required=False, detail="skipped by flag"))
        steps.append(_step("ollama_models", ok=True, required=False, detail="skipped by flag"))

    if include_smoke and venv_python.is_file():
        steps.append(ensure_smoke_base(base, venv_python))
    else:
        steps.append(_step("smoke_base", ok=False if include_smoke else True, required=include_smoke, detail="skipped"))

    if include_webui:
        steps.append(ensure_webui(base, port=int(webui_port)))
    else:
        steps.append(_step("webui", ok=True, required=False, detail="skipped by flag"))

    required_failed = [s["name"] for s in steps if s.get("required") and not s.get("ok")]
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
    }

    out = Path(report_path) if report_path else (base / "runtime" / "setup_wizard_report.json")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["report_path"] = str(out)
    except Exception as exc:
        report["report_path_error"] = str(exc)

    return report


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
    if report.get("report_path"):
        lines.append("")
        lines.append(f"report: {report.get('report_path')}")
    return "\n".join(lines)
