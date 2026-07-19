#!/usr/bin/env python3
"""Double-click / executable GUI for the Nova setup wizard (no command prompt)."""

from __future__ import annotations

import queue
import sys
import threading
import traceback
from pathlib import Path

def _resolve_package_root() -> Path:
    """Prefer an explicit root, then a package folder next to the exe/script."""

    import os

    env_root = str(os.environ.get("NOVA_ROOT") or "").strip()
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
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


ROOT = _resolve_package_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"tkinter unavailable: {exc}") from exc

from services.nova_setup_wizard import render_setup_report, run_setup_wizard


class NovaSetupApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Nova Setup")
        self.geometry("780x560")
        self.minsize(640, 420)
        self.root_dir = ROOT
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False

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
                "Python 3.12, package dependencies, doctor, Ollama, models, smoke, web UI, PATH."
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
        self.close_btn = ttk.Button(buttons, text="Close", command=self.destroy)
        self.close_btn.pack(side="right")

        self.after(100, self._drain_log)

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


def main() -> int:
    app = NovaSetupApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
