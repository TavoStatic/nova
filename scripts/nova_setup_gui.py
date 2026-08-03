#!/usr/bin/env python3
"""Double-click / executable GUI for the Nova setup wizard (no command prompt)."""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import traceback
from pathlib import Path

def _resolve_package_root(explicit: str = "") -> Path:
    """Prefer an explicit root, then a package folder next to the exe/script."""

    import os

    for candidate_text in (
        str(explicit or "").strip(),
        str(os.environ.get("NOVA_ROOT") or "").strip(),
    ):
        if not candidate_text:
            continue
        candidate = Path(candidate_text).expanduser().resolve()
        if (candidate / "nova.cmd").is_file():
            return candidate

    frozen = bool(getattr(sys, "frozen", False))
    here = Path(sys.executable).resolve().parent if frozen else Path(__file__).resolve().parent
    search = [
        Path.cwd(),
        here,
        here.parent,
        Path(__file__).resolve().parents[1] if not frozen else here,
    ]
    for candidate in search:
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        if (resolved / "nova.cmd").is_file() and (resolved / "requirements.txt").is_file():
            return resolved
    # Dev fallback: repo root next to scripts/
    return Path(__file__).resolve().parents[1]


def _bootstrap_sys_path(root: Path) -> None:
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)


_bootstrap_sys_path(_resolve_package_root())

try:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"tkinter unavailable: {exc}") from exc

from services.nova_setup_wizard import (
    acquire_setup_singleton,
    release_setup_singleton,
    render_setup_report,
    run_setup_wizard,
)


class NovaSetupApp(tk.Tk):
    def __init__(self, root_dir: Path | None = None, *, auto_start: bool = False) -> None:
        super().__init__()
        self.title("Nova Setup")
        self.geometry("780x560")
        self.minsize(640, 420)
        self.root_dir = Path(root_dir or _resolve_package_root()).resolve()
        self._auto_start = bool(auto_start)
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        header = ttk.Label(
            self,
            text="Nova Setup Wizard",
            font=("Segoe UI", 16, "bold"),
        )
        header.pack(anchor="w", padx=16, pady=(16, 4))

        sub = ttk.Label(
            self,
            text=(
                "Installs and verifies everything Nova needs on this machine:\n"
                "Python 3.12, library disk budget, deps, doctor, SOCK model sizing,\n"
                "Ollama, model pulls, smoke, web UI, PATH. Only one setup may run."
            ),
            font=("Segoe UI", 10),
            justify="left",
        )
        sub.pack(anchor="w", padx=16, pady=(0, 8))

        opts = ttk.Frame(self)
        opts.pack(fill="x", padx=16, pady=4)
        self.var_ollama = tk.BooleanVar(value=True)
        self.var_models = tk.BooleanVar(value=True)
        self.var_webui = tk.BooleanVar(value=True)
        self.var_path = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Install / verify Ollama", variable=self.var_ollama).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(opts, text="Pull models", variable=self.var_models).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(opts, text="Prove web UI", variable=self.var_webui).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(opts, text="Register nova on PATH", variable=self.var_path).pack(side="left")

        self.status = ttk.Label(self, text="Ready.", font=("Segoe UI", 10))
        self.status.pack(anchor="w", padx=16, pady=(8, 4))

        self.log = scrolledtext.ScrolledText(self, height=22, font=("Consolas", 9), wrap="word")
        self.log.pack(fill="both", expand=True, padx=16, pady=8)
        self.log.configure(state="disabled")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=16, pady=(0, 16))
        self.start_btn = ttk.Button(buttons, text="Start Setup", command=self.start_setup)
        self.start_btn.pack(side="left")
        self.close_btn = ttk.Button(buttons, text="Close", command=self._on_close)
        self.close_btn.pack(side="right")

        self.after(100, self._drain_log)
        if self._auto_start:
            self.after(300, self.start_setup)

    def _on_close(self) -> None:
        if self._running:
            if not messagebox.askyesno(
                "Nova Setup",
                "Setup is still running. Closing will not stop background work safely.\n\nClose anyway?",
            ):
                return
        try:
            release_setup_singleton()
        except Exception:
            pass
        self.destroy()

    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_log(self) -> None:
        try:
            while True:
                item = self._log_queue.get_nowait()
                self._append(item)
        except queue.Empty:
            pass
        self.after(100, self._drain_log)

    def start_setup(self) -> None:
        if self._running:
            messagebox.showinfo("Nova Setup", "Setup is already running in this window.")
            return
        self._running = True
        self.start_btn.configure(state="disabled")
        self.status.configure(text="Running setup… this can take a long time (models/downloads).")
        self._append("=== Nova Setup started ===\n")

        def worker() -> None:
            import builtins

            real_print = builtins.print

            def queued_print(*args, **kwargs):  # type: ignore[no-untyped-def]
                sep = kwargs.get("sep", " ")
                end = kwargs.get("end", "\n")
                line = sep.join(str(a) for a in args) + end
                self._log_queue.put(line)
                try:
                    real_print(*args, **kwargs)
                except Exception:
                    pass

            builtins.print = queued_print  # type: ignore[assignment]
            try:
                report = run_setup_wizard(
                    self.root_dir,
                    install=True,
                    include_ollama=bool(self.var_ollama.get()),
                    include_models=bool(self.var_models.get()),
                    include_webui=bool(self.var_webui.get()),
                    include_smoke=True,
                    register_path=bool(self.var_path.get()),
                    webui_port=18088,
                )
                summary = render_setup_report(report) + "\n"
                self._log_queue.put("\n" + summary)
                ok = bool(report.get("ok"))
                failed = list(report.get("required_failed") or [])
                if failed == ["singleton"]:
                    msg = "Another Nova Setup is already running. Close the other window and try again."
                    self.after(0, lambda: self._finish(False, msg))
                else:
                    self.after(
                        0,
                        lambda: self._finish(
                            ok,
                            "Setup completed successfully." if ok else "Setup finished with failures. See log.",
                        ),
                    )
            except Exception:
                self._log_queue.put(traceback.format_exc())
                self.after(0, lambda: self._finish(False, "Setup crashed. See log."))
            finally:
                builtins.print = real_print  # type: ignore[assignment]

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _finish(self, ok: bool, message: str) -> None:
        self._running = False
        self.start_btn.configure(state="normal")
        self.status.configure(text=message)
        if ok:
            messagebox.showinfo("Nova Setup", message + "\n\nOpen a new terminal and run: nova doctor")
        else:
            messagebox.showerror("Nova Setup", message)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nova Setup GUI / executable")
    parser.add_argument("--root", default="", help="Nova package root containing nova.cmd")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Start setup immediately (for sandbox/automated exe tests)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run setup without GUI (exe/sandbox automation); prints report to stdout",
    )
    parser.add_argument("--skip-ollama", action="store_true")
    parser.add_argument("--skip-models", action="store_true")
    parser.add_argument("--skip-webui", action="store_true")
    parser.add_argument("--no-register-path", action="store_true")
    parser.add_argument("--webui-port", type=int, default=18088)
    parser.add_argument("--report", default="")
    return parser.parse_args(argv)


def run_headless(args: argparse.Namespace) -> int:
    root = _resolve_package_root(str(args.root or ""))
    _bootstrap_sys_path(root)
    report_path = Path(args.report) if str(args.report or "").strip() else (root / "runtime" / "setup_wizard_report.json")
    log_path = report_path.with_suffix(".log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "w", encoding="utf-8", errors="replace")
    # Windowed NovaSetup.exe has no console; bind stdio to a log file.
    sys.stdout = log_fh  # type: ignore[assignment]
    sys.stderr = log_fh  # type: ignore[assignment]

    locked, detail = acquire_setup_singleton()
    if not locked:
        print(f"[setup] Another Nova Setup is already running ({detail})", flush=True)
        log_fh.close()
        return 2
    try:
        print(f"[setup] headless NovaSetup root={root}", flush=True)
        print(f"[setup] report={report_path}", flush=True)
        print(f"[setup] log={log_path}", flush=True)
        report = run_setup_wizard(
            root,
            install=True,
            include_ollama=not bool(args.skip_ollama),
            include_models=not bool(args.skip_models),
            include_webui=not bool(args.skip_webui),
            include_smoke=True,
            register_path=not bool(args.no_register_path),
            webui_port=int(args.webui_port),
            report_path=str(report_path),
        )
        print(render_setup_report(report), flush=True)
        return 0 if report.get("ok") else 1
    finally:
        release_setup_singleton()
        try:
            log_fh.flush()
            log_fh.close()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = _resolve_package_root(str(args.root or ""))
    _bootstrap_sys_path(root)

    if args.headless:
        return run_headless(args)

    locked, detail = acquire_setup_singleton()
    if not locked:
        try:
            probe = tk.Tk()
            probe.withdraw()
            messagebox.showerror(
                "Nova Setup",
                "Another Nova Setup is already running.\n\n"
                "Close the other setup window and try again.\n\n"
                f"({detail})",
            )
            probe.destroy()
        except Exception:
            print(f"Another Nova Setup is already running ({detail})", flush=True)
        return 2

    try:
        app = NovaSetupApp(root_dir=root, auto_start=bool(args.auto))
        app.mainloop()
        return 0
    finally:
        release_setup_singleton()


if __name__ == "__main__":
    raise SystemExit(main())
