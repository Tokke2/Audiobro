"""Beroendekontroll vid start: se vad som saknas och erbjud installation.

Appen ska kunna starta även när något saknas (den visar då exakt vad som
fattas och vad det behövs för), men erbjuder att installera pip-paket med
ett klick. Binära verktyg (tesseract) kan inte pip-installeras — där visas
installationslänkar för rätt operativsystem. Allt loggas.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

from . import logging_setup

log = logging_setup.get(__name__)

TESSERACT_URLS = {
    "win32": "https://ub-mannheim.github.io/tesseract/ (kör sedan om appen)",
    "darwin": "brew install tesseract",
    "linux": "sudo apt install tesseract-ocr",
}


@dataclass
class Dep:
    name: str            # visningsnamn
    module: str          # python-modul att importera ('' = binärt verktyg)
    needed_for: str      # vad den behövs för
    pip_pkg: Optional[str] = None   # pip-paketnamn om installerbart via pip


DEPS = [
    Dep("requests", "requests", "hämta webbsidor (Goodreads, Storytel …)", "requests"),
    Dep("mutagen", "mutagen", "läsa/skriva taggar i mp3/m4b/flac/ogg", "mutagen"),
    Dep("websocket-client", "websocket", "låsa upp Goodreads via din webbläsare",
        "websocket-client"),
    Dep("tesseract", "", "OCR-skärmbildsläget (fliken 'Skärmbild / text')"),
]


def is_installed(dep: Dep) -> bool:
    if dep.module:
        return importlib.util.find_spec(dep.module) is not None
    return shutil.which("tesseract") is not None


def check() -> list[Dep]:
    """Returnera listan av beroenden som SAKNAS."""
    missing = [d for d in DEPS if not is_installed(d)]
    if missing:
        log.warning("beroenden saknas: %s",
                    ", ".join(f"{d.name} ({d.needed_for})" for d in missing))
    else:
        log.info("beroendekontroll: allt installerat (%s)",
                 ", ".join(d.name for d in DEPS))
    return missing


def install_pip(pkg: str, on_line=None) -> tuple[bool, str]:
    """Installera ett pip-paket med samma python som kör appen. Loggar allt."""
    cmd = [sys.executable, "-m", "pip", "install", pkg]
    log.info("installerar: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.error("pip-installation misslyckades: %s", exc)
        return False, str(exc)
    tail = (proc.stdout or "")[-800:] + (proc.stderr or "")[-800:]
    for line in (proc.stdout or "").strip().splitlines()[-3:]:
        if on_line:
            on_line(line)
    ok = proc.returncode == 0
    log.info("pip %s -> %s", pkg, "OK" if ok else f"FEL kod {proc.returncode}")
    if not ok:
        log.error("pip-utdata: %s", tail)
    return ok, tail


def install_hint(dep: Dep) -> str:
    """Mänsklig instruktion när pip inte räcker."""
    if dep.pip_pkg:
        return f"pip install {dep.pip_pkg}"
    return TESSERACT_URLS.get(sys.platform, TESSERACT_URLS["linux"])
