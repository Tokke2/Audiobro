#!/usr/bin/env python3
"""Dubbelklickbar start utan konsolfönster.

Windows: högerklicka -> Öppna med -> Python, eller använd starta.bat
(pythonw visar inget konsolfönster för .pyw-filer).
macOS/Linux: använd starta.command / starta.sh.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ags.gui import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
