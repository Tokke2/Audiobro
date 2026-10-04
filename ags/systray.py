"""Systray — multi-OS (Windows, Linux, macOS) via pystray.

    Starta i systemfältet / minimera dit, så appen ligger som ikon vid klockan
    istället för i aktivitetsfältet.

    Använder pystray (pip install pystray) + Pillow. Om pystray saknas
    returnerar has_tray()==False och GUI disablar kryssen med tipset
    "pip install pystray".
"""
from __future__ import annotations

import os
import sys
import pathlib
import threading

from . import logging_setup

LOG = logging_setup.get("systray")
APP_NAME = "Audiobro"

# Försök ladda pystray + PIL
_HAS_TRAY = False
_TRAY_ERROR = ""
try:
    import pystray  # type: ignore
    from PIL import Image  # type: ignore
    _HAS_TRAY = True
except Exception as exc:
    _HAS_TRAY = False
    _TRAY_ERROR = str(exc)
    LOG.debug("pystray saknas: %s", exc)


def has_tray() -> bool:
    return _HAS_TRAY


def tray_error() -> str:
    return _TRAY_ERROR


def _icon_image() -> "Image.Image | None":
    try:
        from PIL import Image  # type: ignore
        # Leta upp assets/icon.png / icon-256.png
        bases = []
        try:
            bases.append(pathlib.Path(__file__).resolve().parent.parent)
            bases.append(pathlib.Path.cwd())
            if hasattr(sys, "_MEIPASS"):
                bases.append(pathlib.Path(sys._MEIPASS))
        except Exception:
            pass
        for b in bases:
            for cand in (b / "assets" / "icon-happy.png",
                         b / "icon-happy.png"):
                if cand.exists():
                    try:
                        im = Image.open(cand).convert("RGBA")
                        # pystray vill ha kvadrat ~64-256
                        if im.size[0] > 256:
                            im = im.resize((256, 256), Image.LANCZOS)
                        return im
                    except Exception:
                        continue
        # fallback: skapa enkel ikon (blå kvadrat + hörlur)
        im = Image.new("RGBA", (64, 64), (30, 58, 95, 255))
        return im
    except Exception as exc:
        LOG.debug("kunde inte ladda ikonbild: %s", exc)
        return None


class Tray:
    """Wrapper runt pystray.Icon som kan starta/stoppa och toggla huvudfönstret."""

    def __init__(self, app) -> None:
        self.app = app  # ags.gui.App
        self.icon = None
        self._thread: threading.Thread | None = None
        self._running = False

    def create(self) -> bool:
        if not _HAS_TRAY:
            LOG.debug("create tray: pystray saknas")
            return False
        try:
            import pystray  # type: ignore
            from pystray import MenuItem, Menu  # type: ignore
            img = _icon_image()
            if img is None:
                LOG.warning("ingen ikonbild för systray")
                return False

            def _show(icon, item):
                self.app.root.after(0, self.app._tray_show_window)

            def _scan(icon, item):
                self.app.root.after(0, self.app.start_scan)

            def _open_out(icon, item):
                self.app.root.after(0, self.app._open_output)

            def _quit(icon, item):
                self.app.root.after(0, self.app._tray_quit)

            menu = Menu(
                MenuItem("Visa Audiobro", _show, default=True),
                MenuItem("Skanna & matcha", _scan),
                MenuItem("Öppna outputmapp", _open_out),
                Menu.SEPARATOR,
                MenuItem("Avsluta", _quit),
            )
            self.icon = pystray.Icon(APP_NAME, img, APP_NAME, menu)
            LOG.info("systray ikon skapad")
            return True
        except Exception as exc:
            LOG.warning("kunde inte skapa systray: %s", exc)
            return False

    def run_detached(self) -> bool:
        if self.icon is None:
            if not self.create():
                return False
        if self._running:
            return True
        try:
            # pystray.Icon.run() är blockerande — kör i daemon-tråd
            def _run():
                try:
                    LOG.info("systray tråd startad")
                    self.icon.run()
                except Exception as exc:
                    LOG.debug("systray run slut: %s", exc)
                finally:
                    self._running = False

            self._thread = threading.Thread(target=_run, name="systray", daemon=True)
            self._thread.start()
            self._running = True
            LOG.info("systray visad i systemfältet")
            return True
        except Exception as exc:
            LOG.warning("kunde inte starta systray: %s", exc)
            return False

    def stop(self) -> None:
        try:
            if self.icon is not None:
                try:
                    self.icon.stop()
                except Exception:
                    pass
                LOG.info("systray stoppad")
            self.icon = None
            self._running = False
        except Exception as exc:
            LOG.debug("stop systray fel: %s", exc)

    def update_title(self, text: str) -> None:
        try:
            if self.icon is not None:
                self.icon.title = text
        except Exception:
            pass
