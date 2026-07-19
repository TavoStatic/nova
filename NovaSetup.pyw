# Double-click launcher (uses pythonw if available; no console window).
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "scripts" / "nova_setup_gui.py"), run_name="__main__")
