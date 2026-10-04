"""Cacherensning — körs automatiskt efter varje avslut (krav 16 i SPEC).

Rensar genererade cachefiler i appens/workspace-katalogen:
``__pycache__/``, ``*.pyc``, ``.pytest_cache`` m.fl. Körs:

* när GUI-fönstret stängs,
* efter varje CLI-kommando,
* manuellt via knappen "Rensa cache" / ``python -m ags.cli cleanup``.

Allt loggas till ags.log.
"""
from __future__ import annotations

import os
import shutil

from . import logging_setup

log = logging_setup.get(__name__)

CACHE_DIRS = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
              ".parcel-cache", ".vite")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def clean_caches(root: str | None = None) -> list[str]:
    """Ta bort cachekataloger/filer under root (standard: projektroten).

    Returnerar vad som togs bort (för logg/status).
    """
    root = root or PROJECT_ROOT
    removed: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        for d in list(dirnames):
            if d in CACHE_DIRS:
                full = os.path.join(dirpath, d)
                shutil.rmtree(full, ignore_errors=True)
                removed.append(os.path.relpath(full, root))
                dirnames.remove(d)
        for f in filenames:
            if f.endswith((".pyc", ".pyo")):
                full = os.path.join(dirpath, f)
                try:
                    os.remove(full)
                    removed.append(os.path.relpath(full, root))
                except OSError:
                    pass
    log.info("cacherensning i %s: %d objekt bort (%s)",
             root, len(removed), ", ".join(removed[:10]) or "inget att rensa")
    return removed
