#!/usr/bin/env python3
"""Audiobro — dubbelklickbar start utan konsolfönster (dubbelklicka denna fil).

Windows: pythonw döljer konsolfönstret automatiskt för .pyw-filer.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ags.gui import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
