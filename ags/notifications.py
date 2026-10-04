"""Native notiser — multi-OS (Windows Toast, macOS NC, Linux notify-send).

    Använder i prioritetsordning:
      1) plyer (cross-platform, pip install plyer)
      2) Windows: win10toast/powershell
      3) macOS: osascript / terminal-notifier
      4) Linux: notify-send / zenity
    Fallback: ingen notis — loggar bara.

    Anrop: notifications.notify("Titel", "Meddelande", timeout=5)
"""
from __future__ import annotations

import os
import sys
import pathlib
import shutil
import subprocess

from . import logging_setup

LOG = logging_setup.get("notifications")
APP_NAME = "Audiobro"


def _icon_path() -> str | None:
    try:
        root = pathlib.Path(__file__).resolve().parent.parent
        for cand in (root / "assets" / "icon-happy.png",):
            if cand.exists():
                return str(cand)
        if hasattr(sys, "_MEIPASS"):
            for cand in (pathlib.Path(sys._MEIPASS) / "assets" / "icon-happy.png", pathlib.Path(sys._MEIPASS) / "icon-happy.png"):
                if cand.exists():
                    return str(cand)
    except Exception:
        pass
    return None


def _try_plyer(title: str, msg: str, timeout: int = 5) -> bool:
    try:
        from plyer import notification  # type: ignore
        icon = _icon_path()
        kwargs: dict = {"title": title, "message": msg, "app_name": APP_NAME, "timeout": timeout}
        if icon and icon.endswith(".png"):
            # plyer på Windows vill ha .ico, på Linux .png — prova
            kwargs["app_icon"] = icon
        notification.notify(**kwargs)
        LOG.info("notis via plyer: %s — %s", title, msg[:80])
        return True
    except Exception as exc:
        LOG.debug("plyer misslyckades: %s", exc)
        return False


def _try_windows(title: str, msg: str) -> bool:
    # Försök PowerShell Toast (Windows 10+ utan extra deps)
    try:
        # Escape quotes
        t = title.replace('"', "'").replace("`", "'")
        m = msg.replace('"', "'").replace("`", "'").replace("\n", " ")
        # PowerShell med BurntToast fallback: använd Wscript.Shell Popup som sista utväg
        ps = (
            f'Add-Type -AssemblyName System.Windows.Forms; '
            f'$n = New-Object System.Windows.Forms.NotifyIcon; '
            f'$n.Icon = [System.Drawing.SystemIcons]::Information; '
            f'$n.BalloonTipTitle = "{t}"; $n.BalloonTipText = "{m}"; '
            f'$n.Visible = $true; $n.ShowBalloonTip(5000); Start-Sleep -Seconds 6; $n.Dispose()'
        )
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x08000000 if sys.platform == "win32" else 0)  # CREATE_NO_WINDOW
        LOG.info("notis via powershell: %s", title)
        return True
    except Exception as exc:
        LOG.debug("powershell notis misslyckades: %s", exc)
    # Försök win10toast
    try:
        from win10toast import ToastNotifier  # type: ignore
        toaster = ToastNotifier()
        toaster.show_toast(title, msg, duration=5, threaded=True, icon_path=_icon_path())
        LOG.info("notis via win10toast: %s", title)
        return True
    except Exception as exc:
        LOG.debug("win10toast misslyckades: %s", exc)
    return False


def _try_macos(title: str, msg: str) -> bool:
    # osascript
    try:
        t = title.replace('"', '\\"')
        m = msg.replace('"', '\\"')
        subprocess.Popen(["osascript", "-e", f'display notification "{m}" with title "{t}"'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        LOG.info("notis via osascript: %s", title)
        return True
    except Exception as exc:
        LOG.debug("osascript misslyckades: %s", exc)
    # terminal-notifier
    if shutil.which("terminal-notifier"):
        try:
            cmd = ["terminal-notifier", "-title", title, "-message", msg]
            icon = _icon_path()
            if icon:
                cmd += ["-contentImage", icon]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            LOG.info("notis via terminal-notifier: %s", title)
            return True
        except Exception as exc:
            LOG.debug("terminal-notifier misslyckades: %s", exc)
    return False


def _try_linux(title: str, msg: str, timeout: int = 5) -> bool:
    if shutil.which("notify-send"):
        try:
            icon = _icon_path()
            cmd = ["notify-send", title, msg, "-t", str(timeout * 1000), "-a", APP_NAME]
            if icon:
                cmd += ["-i", icon]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            LOG.info("notis via notify-send: %s", title)
            return True
        except Exception as exc:
            LOG.debug("notify-send misslyckades: %s", exc)
    if shutil.which("zenity"):
        try:
            subprocess.Popen(["zenity", "--notification", "--text", f"{title}: {msg}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            LOG.info("notis via zenity: %s", title)
            return True
        except Exception as exc:
            LOG.debug("zenity misslyckades: %s", exc)
    return False


def notify(title: str, message: str, timeout: int = 5, icon: str | None = None) -> bool:
    """Skicka native notis. Returnerar True om någon backend lyckades.
    Titel och meddelande trunkeras till rimlig längd för varje OS.
    """
    title = (title or APP_NAME)[:48]
    message = (message or "")[:220]
    if not title and not message:
        return False
    LOG.debug("notify: %r — %r", title, message)
    # Försök plyer först (bäst cross-platform)
    if _try_plyer(title, message, timeout=timeout):
        return True
    try:
        if sys.platform.startswith("win"):
            if _try_windows(title, message):
                return True
        elif sys.platform == "darwin":
            if _try_macos(title, message):
                return True
        else:
            if _try_linux(title, message, timeout=timeout):
                return True
            # även prova plyer igen utan icon?
    except Exception as exc:
        LOG.debug("notify backend fel: %s", exc)
    LOG.debug("ingen notis-backend lyckades för %r", title)
    return False


# Hjälpare för GUI — mappar interna händelser till notiser
def notify_done(count: int, moved: int = 0, copied: int = 0) -> bool:
    if count <= 0:
        return False
    title = f"✅ Klart — {count} bok{'/böcker' if count != 1 else ''}"
    msg = f"{'Flyttade' if moved else 'Kopierade' if copied else 'Organiserade'} {count} till output. "
    if moved or copied:
        msg += f"({moved} flyttade, {copied} kopierade)"
    return notify(title, msg, timeout=6)


def notify_scan_done(total: int, matched: int = 0, blocked: int = 0) -> bool:
    title = f"🔍 Skannad — {total} filer"
    if blocked:
        msg = f"{matched} matchade, {blocked} blockerade (Goodreads). Klistra token eller vänta."
    else:
        msg = f"{matched} matchade. {total - matched} behöver koll." if total else "Inga filer hittade."
    return notify(title, msg, timeout=5)


def notify_error(title: str, err: str) -> bool:
    return notify(f"⚠️ {title}", err[:180], timeout=7)


def notify_new_files(count: int) -> bool:
    return notify("📚 Nya filer hittade", f"{count} nya ljudböcker i bevakad mapp. Klicka för att visa.", timeout=6)
