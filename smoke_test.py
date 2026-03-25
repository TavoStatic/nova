#!/usr/bin/env python3
"""Compatibility launcher for the smoke test implementation in scripts/."""

from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parent / "scripts" / "smoke_test.py"), run_name="__main__")
