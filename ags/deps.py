"""Beroendekontroll vid start: se vad som saknas och erbjud installation.

Appen ska kunna starta även när något saknas (den visar då exakt vad som
fattas och vad det behövs för), men erbjuder att installera pip-paket med
ett klick. Allt loggas.
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


@dataclass
class Dep:
    name: str            # visningsnamn
    module: str          # python-modul att importera ('' = binärt verktyg)
    needed_for: str      # vad den behövs för
    pip_pkg: Optional[str] = None   # pip-paketnamn om installerbart via pip


DEPS = [
    # Kritiska — utan dessa kan appen inte matcha/skriva taggar
    Dep("requests", "requests", "hämta webbsidor (Goodreads)", "requests"),
    Dep("beautifulsoup4", "bs4", "tolka Goodreads-HTML (sök + boksidor)", "beautifulsoup4"),
    Dep("lxml", "lxml", "snabb HTML-parser åt BeautifulSoup", "lxml"),
    Dep("mutagen", "mutagen", "läsa/skriva taggar i mp3/m4b/flac/ogg", "mutagen"),
    Dep("rapidfuzz", "rapidfuzz", "fuzzy-matcha titel/författare (19999% bättre träff)", "rapidfuzz"),
    Dep("Pillow", "PIL", "ikoner/bilder i GUI och notiser", "Pillow"),
    # Valfria men rekommenderade — dialogen frågar ändå vid start om de saknas
    Dep("websocket-client", "websocket", "låsa upp Goodreads via din webbläsare",
        "websocket-client"),
    Dep("pystray", "pystray", "systemfältet/systray — minimera till klockan (valfritt)",
        "pystray"),
    Dep("plyer", "plyer", "skrivbords-notiser när klar/fel (valfritt, fallback till notify-send/osascript)",
        "plyer"),
    # tesseract borttaget — OCR bort, manuell Goodreads-länk gäller
]


def is_installed(dep: Dep) -> bool:
    if dep.module:
        return importlib.util.find_spec(dep.module) is not None
    return False


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


def get_version(dep: Dep) -> str | None:
    if not dep.module:
        return None
    try:
        from importlib.metadata import version as _ver
        return _ver(dep.pip_pkg or dep.name)
    except Exception:
        try:
            import importlib.metadata as _md
            return _md.version(dep.pip_pkg or dep.name)
        except Exception:
            return None

def check_outdated() -> list[tuple[Dep, str, str]]:
    """Kolla vilka pip-paket som har nyare version på PyPI.
    Returnerar [(Dep, installed, latest), ...]. Tom lista = alla aktuella eller pip saknas/offline.
    """ 
    res: list[tuple[Dep, str, str]] = []
    # pip list --outdated är snabb och kräver inget extra paket
    try:
        proc = subprocess.run([sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
                              capture_output=True, text=True, timeout=20)
        if proc.returncode != 0:
            log.debug("pip list --outdated fel %s: %s", proc.returncode, proc.stderr[:300])
            return []
        import json as _js
        data = _js.loads(proc.stdout or "[]")
        # data: [{"name":"requests","version":"2.31","latest_version":"2.32", ...}, ...]
        latest_map = {d["name"].lower(): d.get("latest_version","") for d in data}
        ver_map = {d["name"].lower(): d.get("version","") for d in data}
        for dep in DEPS:
            if not dep.pip_pkg:
                continue
            if not is_installed(dep):
                continue
            key = (dep.pip_pkg or dep.name).lower().replace("_","-")
            # pip normaliserar _ och -
            if key in latest_map:
                res.append((dep, ver_map.get(key, get_version(dep) or "?"), latest_map[key]))
            elif dep.name.lower() in latest_map:
                res.append((dep, ver_map.get(dep.name.lower(), ""), latest_map[dep.name.lower()]))
        if res:
            log.info("gamla paket: %s", ", ".join(f"{d.name} {cur}->{lat}" for d,cur,lat in res))
    except Exception as exc:
        log.debug("check_outdated misslyckades: %s", exc)
    return res

def upgrade_pip(pkg: str, on_line=None) -> tuple[bool, str]:
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", pkg]
    log.info("uppgraderar: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.error("pip-upgrade misslyckades: %s", exc)
        return False, str(exc)
    tail = (proc.stdout or "")[-800:] + (proc.stderr or "")[-800:]
    for line in (proc.stdout or "").strip().splitlines()[-3:]:
        if on_line:
            on_line(line)
    ok = proc.returncode == 0
    log.info("pip upgrade %s -> %s", pkg, "OK" if ok else f"FEL {proc.returncode}")
    if not ok:
        log.error("pip-utdata: %s", tail)
    return ok, tail

def install_hint(dep: Dep) -> str:
    """Mänsklig instruktion när pip inte räcker."""
    if dep.pip_pkg:
        return f"pip install {dep.pip_pkg}"
    return ""
