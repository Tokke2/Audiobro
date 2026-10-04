"""Central loggning: allt som händer (och inte händer) hamnar i fil.

Loggen ligger i <appmappen>/logs/ags.log (DEBUG-nivå) så att felsökning
är möjlig även när GUI:t inte visar något. Konsolen får bara varningar/fel —
statusraderna skrivs av appen själv.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional

def _default_log_path() -> str:
    """Krav 25: loggen sparas ALLTID i undermappen 'logs' i appmappen
    (mappen som innehåller ags-paketet). Fallback: hemkatalogen."""
    app_logs = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    try:
        os.makedirs(app_logs, exist_ok=True)
        return os.path.join(app_logs, "ags.log")
    except OSError:
        return os.path.join(os.path.expanduser("~"), ".audiobook-goodreads",
                            "ags.log")


DEFAULT_LOG = _default_log_path()
LOG_DIR = os.path.dirname(DEFAULT_LOG)

_CONFIGURED = False


class _SafeStderrHandler(logging.StreamHandler):
    """Konsolhandler som alltid skriver till *aktuell* sys.stderr (tålig mot pytest)."""

    def emit(self, record) -> None:
        try:
            self.stream = sys.stderr
            super().emit(record)
        except (ValueError, OSError):
            pass

    def flush(self) -> None:
        try:
            self.stream = sys.stderr
            super().flush()
        except (ValueError, OSError):
            pass


def setup_logging(path: Optional[str] = None, console_level: int = logging.WARNING) -> str:
    """Initiera filloggning (idempotent). Returnerar loggsökvägen."""
    global _CONFIGURED
    path = path or DEFAULT_LOG
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        pass
    root = logging.getLogger("ags")
    root.setLevel(logging.DEBUG)
    # byt filhandler till önskad sökväg (tidigare pekar kanske någon annanstans)
    for h in list(root.handlers):
        if isinstance(h, logging.FileHandler):
            root.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root.addHandler(fh)
    if not _CONFIGURED:
        ch = _SafeStderrHandler()
        ch.setLevel(console_level)
        ch.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        root.addHandler(ch)
        _CONFIGURED = True
    root.debug("loggning initierad -> %s", path)
    return path


def get(name: str) -> logging.Logger:
    return logging.getLogger(f"ags.{name}")
