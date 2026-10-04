"""Autostart-hantering — multi-OS (Windows, Linux, macOS).

    Ger en enkel toggle: autostart.is_enabled() / autostart.set_enabled(True/False)

    Windows: skriver till HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
             (värde "Audiobro" -> kommando). Fallback: Startup-mappen .lnk/.bat om registret saknas.
    Linux:   ~/.config/autostart/audiobro.desktop (XDG Autostart)
    macOS:   ~/Library/LaunchAgents/com.audiobro.plist (launchd)

    Launch-kommandot pekar på aktuell installation:
      - PyInstaller onefile exe -> exe-sökvägen
      - Audiobro.pyw / .py -> pythonw/python + script
      - python -m ags.gui -> sys.executable + "-m ags.gui"

    Allt är best-effort — inga exceptions bubblar till GUI, bara True/False + log.
"""
from __future__ import annotations

import os
import sys
import pathlib
import plistlib
import shutil

from . import logging_setup

LOG = logging_setup.get("autostart")
APP_NAME = "Audiobro"
APP_ID = "com.audiobro"
LINUX_DESKTOP_NAME = "audiobro.desktop"
PLIST_NAME = "com.audiobro.plist"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LEGACY_APP_IDS = ["com.ljudbokssynk", "ljudbokssynk"]
LEGACY_DESKTOPS = ["ljudbokssynk.desktop"]
LEGACY_REG_VALUES = ["Ljudbokssynk"]


def _launch_command(add_tray: bool | None = None) -> tuple[str, str]:
    """Return (command, description) for current install.
    command is what OS should exec at login.
    Om add_tray är None kollar vi settings.json:start_to_tray och lägger till --tray.
    """
    # PyInstaller?
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        exe = pathlib.Path(sys.executable).resolve()
        _need = add_tray
        if _need is None:
            try:
                from . import settings as _st5
                _need = bool(_st5.load().get("start_to_tray", False))
            except Exception:
                _need = False
        suffix = " --tray" if _need else ""
        return str(exe) + suffix, f"{APP_NAME} (bundled)"
    # Running as script?
    # Check if Audiobro.pyw exists near __file__
    try:
        root = pathlib.Path(__file__).resolve().parent.parent
        pyw = root / "Audiobro.pyw"
        if pyw.exists():
            if sys.platform.startswith("win"):
                # pythonw undviker konsolfönster
                pyw_exe = pathlib.Path(sys.executable)
                pw = pyw_exe.parent / "pythonw.exe"
                # avgör tray
                _need_tray = add_tray
                if _need_tray is None:
                    try:
                        from . import settings as _st3
                        _need_tray = bool(_st3.load().get("start_to_tray", False))
                    except Exception:
                        _need_tray = False
                suffix = " --tray" if _need_tray else ""
                if pw.exists():
                    return f'"{pw}" "{pyw}"' + suffix, f"{APP_NAME} via pythonw"
                return f'"{pyw_exe}" "{pyw}"' + suffix, f"{APP_NAME} via python"
            else:
                _need_tray2 = add_tray
                if _need_tray2 is None:
                    try:
                        from . import settings as _st4
                        _need_tray2 = bool(_st4.load().get("start_to_tray", False))
                    except Exception:
                        _need_tray2 = False
                suffix2 = " --tray" if _need_tray2 else ""
                return f'"{sys.executable}" "{pyw}"' + suffix2, f"{APP_NAME} via python"
        # fallback: python -m ags.gui
        _need3 = add_tray
        if _need3 is None:
            try:
                from . import settings as _st6
                _need3 = bool(_st6.load().get("start_to_tray", False))
            except Exception:
                _need3 = False
        suffix3 = " --tray" if _need3 else ""
        return f'"{sys.executable}" -m ags.gui' + suffix3, f"{APP_NAME} via -m ags.gui"
    except Exception:
        try:
            from . import settings as _st7
            _need4 = bool(_st7.load().get("start_to_tray", False))
        except Exception:
            _need4 = False
        suffix4 = " --tray" if _need4 else ""
        return f'"{sys.executable}" -m ags.gui' + suffix4, f"{APP_NAME}" 


def _icon_path() -> str | None:
    try:
        root = pathlib.Path(__file__).resolve().parent.parent
        for cand in (root / "assets" / "icon-happy.png",):
            if cand.exists():
                return str(cand)
    except Exception:
        pass
    return None


# ------------------------------------------------------------------ Windows
def _win_is_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
            try:
                winreg.QueryValueEx(k, APP_NAME)
                return True
            except FileNotFoundError:
                return False
    except Exception as exc:
        LOG.debug("win is_enabled fail: %s", exc)
        # fallback: Startup-mapp
        try:
            startup = pathlib.Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
            for suffix in (".lnk", ".bat", ".url"):
                if (startup / f"{APP_NAME}{suffix}").exists():
                    return True
        except Exception:
            pass
        return False


def _win_set_enabled(enable: bool) -> bool:
    cmd, _desc = _launch_command()
    # Försök registret först
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
                LOG.info("autostart PÅ (Windows Run): %s", cmd)
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                    LOG.info("autostart AV (Windows Run borttagen)")
                except FileNotFoundError:
                    pass
        # Städa Startup-mappen om den fanns
        _win_cleanup_startup_folder()
        return True
    except Exception as exc:
        LOG.warning("kunde inte skriva till Run-nyckeln (%s), provar Startup-mappen", exc)
        # Fallback: Startup-mappen
        try:
            startup = pathlib.Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
            startup.mkdir(parents=True, exist_ok=True)
            bat = startup / f"{APP_NAME}.bat"
            if enable:
                # Skapa .bat som startar appen tyst
                bat.write_text(f'@echo off\r\nstart "" {cmd}\r\n', encoding="utf-8")
                LOG.info("autostart PÅ (Startup mapp .bat): %s", bat)
            else:
                for cand in (startup / f"{APP_NAME}.bat", startup / f"{APP_NAME}.lnk", startup / f"{APP_NAME}.url"):
                    try:
                        if cand.exists():
                            cand.unlink()
                    except Exception:
                        pass
                LOG.info("autostart AV (Startup mapp rensad)")
            return True
        except Exception as exc2:
            LOG.warning("autostart fallback misslyckades: %s", exc2)
            return False


def _win_cleanup_startup_folder() -> None:
    try:
        startup = pathlib.Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
        for cand in (startup / f"{APP_NAME}.bat", startup / f"{APP_NAME}.lnk", startup / f"{APP_NAME}.url"):
            if cand.exists():
                try:
                    cand.unlink()
                except Exception:
                    pass
    except Exception:
        pass


# ------------------------------------------------------------------ Linux
def _linux_desktop_path() -> pathlib.Path:
    return pathlib.Path.home() / ".config" / "autostart" / LINUX_DESKTOP_NAME


def _linux_is_enabled() -> bool:
    return _linux_desktop_path().exists()


def _linux_set_enabled(enable: bool) -> bool:
    p = _linux_desktop_path()
    if not enable:
        try:
            if p.exists():
                p.unlink()
                LOG.info("autostart AV (Linux): borttagen %s", p)
            return True
        except Exception as exc:
            LOG.warning("kunde inte ta bort autostart-desktop: %s", exc)
            return False
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        cmd, _desc = _launch_command()
        # .desktop kräver Exec utan citattecken-krångel — förenkla
        # Om cmd innehåller citat, behåll men XDG klarar det
        icon = _icon_path() or "audio-x-generic"
        content = (
            "[Desktop Entry]\n"
            f"Name={APP_NAME}\n"
            f"GenericName={APP_NAME}\n"
            f"Comment=Ljudbok → Goodreads → Audiobookshelf (autostart)\n"
            f"Exec={cmd}\n"
            f"Icon={icon}\n"
            "Terminal=false\n"
            "Type=Application\n"
            "Categories=AudioVideo;Audio;\n"
            "X-GNOME-Autostart-enabled=true\n"
            "StartupNotify=false\n"
        )
        p.write_text(content, encoding="utf-8")
        # Gör körbar (vissa DE kräver +x)
        try:
            p.chmod(0o755)
        except Exception:
            pass
        LOG.info("autostart PÅ (Linux): %s -> %s", p, cmd)
        return True
    except Exception as exc:
        LOG.warning("kunde inte skapa autostart-desktop: %s", exc)
        return False


# ------------------------------------------------------------------ macOS
def _macos_plist_path() -> pathlib.Path:
    return pathlib.Path.home() / "Library" / "LaunchAgents" / PLIST_NAME


def _macos_is_enabled() -> bool:
    return _macos_plist_path().exists()


def _macos_set_enabled(enable: bool) -> bool:
    p = _macos_plist_path()
    if not enable:
        try:
            if p.exists():
                p.unlink()
                # försök unload om launchctl finns
                try:
                    import subprocess
                    subprocess.call(["launchctl", "unload", str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
                LOG.info("autostart AV (macOS): borttagen %s", p)
            return True
        except Exception as exc:
            LOG.warning("kunde inte ta bort plist: %s", exc)
            return False
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        cmd, _desc = _launch_command()
        # Dela upp Exec i ProgramArguments (launchd kräver array)
        # Ta bort citat och dela enkelt
        import shlex
        try:
            args = shlex.split(cmd)
        except Exception:
            args = [sys.executable, str(pathlib.Path(__file__).resolve().parent.parent / "Audiobro.pyw")]
        plist = {
            "Label": APP_ID,
            "ProgramArguments": args,
            "RunAtLoad": True,
            "ProcessType": "Interactive",
            "StandardOutPath": str(pathlib.Path.home() / "Library" / "Logs" / "Audiobro.log"),
            "StandardErrorPath": str(pathlib.Path.home() / "Library" / "Logs" / "Audiobro.log"),
        }
        with open(p, "wb") as fh:
            plistlib.dump(plist, fh)
        # Försök load direkt
        try:
            import subprocess
            subprocess.call(["launchctl", "load", str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        LOG.info("autostart PÅ (macOS): %s -> %r", p, args)
        return True
    except Exception as exc:
        LOG.warning("kunde inte skapa plist: %s", exc)
        return False


# ------------------------------------------------------------------ publik API
def is_enabled() -> bool:
    """True om autostart är aktiv på denna OS."""
    try:
        if sys.platform.startswith("win"):
            return _win_is_enabled()
        elif sys.platform == "darwin":
            return _macos_is_enabled()
        else:
            # Linux + övrigt Unix
            return _linux_is_enabled()
    except Exception as exc:
        LOG.debug("is_enabled fel: %s", exc)
        return False


def set_enabled(enable: bool) -> bool:
    """Sätt autostart. Returnerar True om det lyckades."""
    try:
        if sys.platform.startswith("win"):
            return _win_set_enabled(bool(enable))
        elif sys.platform == "darwin":
            return _macos_set_enabled(bool(enable))
        else:
            return _linux_set_enabled(bool(enable))
    except Exception as exc:
        LOG.warning("set_enabled(%s) misslyckades: %s", enable, exc)
        return False


def sync_from_settings(want_enabled: bool) -> bool:
    """Se till att OS-autostart matchar settings.json-värdet.
    Anropas vid appstart och när användaren togglar.
    Returnerar True om OS nu matchar önskan.
    """
    try:
        have = is_enabled()
        if have == bool(want_enabled):
            LOG.debug("autostart redan %s", "PÅ" if have else "AV")
            return True
        ok = set_enabled(bool(want_enabled))
        LOG.info("autostart synkad: ville %s, har %s, set ok=%s", want_enabled, have, ok)
        return ok
    except Exception as exc:
        LOG.warning("sync_from_settings misslyckades: %s", exc)
        return False
