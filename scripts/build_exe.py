"""Bygg en dubbelklickbar .exe/.app UTAN konsolfönster med PyInstaller.

    pip install pyinstaller
    python scripts/build_exe.py

Resultatet läggs i dist/Ljudbokssynk/ (onefile, --noconsole).
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    entry = os.path.join(ROOT, "Ljudbokssynk.pyw")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole", "--onefile", "--name", "Ljudbokssynk",
        "--collect-submodules", "ags",
        entry,
    ]
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
