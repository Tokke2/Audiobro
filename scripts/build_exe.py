"""Bygg en dubbelklickbar .exe/.app UTAN konsolfönster med PyInstaller.

    pip install pyinstaller
    python scripts/build_exe.py

Resultatet läggs i dist/Audiobro/ (onefile, --noconsole).
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    entry = os.path.join(ROOT, "Audiobro.pyw")
    # ENDAST icon-happy.png — alla andra ikoner borttagna
    icon = os.path.join(ROOT, "assets", "icon-happy.png")
    icon_png = os.path.join(ROOT, "assets", "icon-happy.png")
    datas = []
    # lägg till ikonen så PyInstaller hittar den via sys._MEIPASS
    if os.path.exists(icon):
        sep = ";" if sys.platform.startswith("win") else ":"
        datas += ["--add-data", f"{icon}{sep}assets"]
    if os.path.exists(icon_png):
        sep = ";" if sys.platform.startswith("win") else ":"
        # undvik dublett om redan tillagd
        if icon_png != icon and os.path.exists(icon_png) and False:  # endast happy gäller
            datas += ["--add-data", f"{icon_png}{sep}assets"]
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole", "--onefile", "--name", "Audiobro",
        "--collect-submodules", "ags",
    ]
    # --icon kräver .ico på Windows — generera från png om endast png finns
    icon_for_build = icon
    if icon.lower().endswith(".png") and os.path.exists(icon):
        try:
            from PIL import Image
            _ico_tmp = os.path.join(ROOT, "assets", "_build_icon.ico")
            im = Image.open(icon)
            im.save(_ico_tmp, sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])
            if os.path.exists(_ico_tmp):
                icon_for_build = _ico_tmp
        except Exception:
            pass
    if os.path.exists(icon_for_build):
        cmd += ["--icon", icon_for_build]
    cmd += datas + [entry]
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
