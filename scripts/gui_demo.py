"""Bygger GUI:t, fyller det med ett riktigt matchningsresultat och sparar en skärmdump.

Används för att visa/verifiera gränssnittet utan att klicka manuellt:
    DISPLAY=:99 python scripts/gui_demo.py --root /tmp/demo --out docs/gui.png
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ags.bridge import TitleBridge            # noqa: E402
from ags.engine import Engine, EngineOptions  # noqa: E402
from ags.goodreads import Goodreads           # noqa: E402
from ags.gui import App                       # noqa: E402
from ags.openlibrary import OpenLibrary       # noqa: E402
from ags.presenter import proposal_row, row_values  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.expanduser("~/Ljudböcker"))
    ap.add_argument("--out", default="docs/gui.png")
    ap.add_argument("--delay", type=float, default=1.2)
    args = ap.parse_args()

    app = App(delay=args.delay)
    app.root.update_idletasks()

    client = Goodreads(min_delay=args.delay,
                       on_fetch=lambda u: app.set_status(f"hämtar {u}"))
    eng = Engine(client, EngineOptions(),
                 on_status=app.set_status,
                 fallback=OpenLibrary(min_delay=args.delay),
                 bridge=TitleBridge())
    app.engine = eng
    app.client = client
    app.folder.set(args.root)

    proposals = eng.run(args.root, dry_run=True,
                        on_proposal=lambda p: app.queue.put(("row", p)))
    # töm kön synkront så att raderna hamnar i tabellen
    deadline = time.time() + 15
    while time.time() < deadline:
        app.root.update()
        if len(app.rows) >= len(proposals):
            break
        time.sleep(0.05)
    app.root.update_idletasks()
    if app.tree.get_children():
        first = app.tree.get_children()[0]
        app.tree.selection_set(first)
        app.tree.focus(first)
        app._show_detail()
    app.set_status(f"{len(app.rows)} grupper matchade · {presenter_summary(app)}")
    app.root.update()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    app.root.after(60)
    app.root.update()
    geom = f"{app.root.winfo_width()}x{app.root.winfo_height()}+{app.root.winfo_x()}+{app.root.winfo_y()}"
    os.system(f"import -window root -crop {geom}+0+0 +repage '{args.out}' 2>/dev/null"
              f" || import -window root '{args.out}'")
    print(f"skärmdump: {args.out} ({app.root.winfo_width()}x{app.root.winfo_height()})")
    for row in app.rows:
        print(" ", row["status"], "|", row["label"], "->", row["new_title"],
              "|", row["new_series"], row["new_series_number"], "|", row["source"])
    client.close()
    app.root.destroy()
    return 0


def presenter_summary(app) -> str:
    from ags import presenter

    return presenter.summary_text(app.rows)


if __name__ == "__main__":
    raise SystemExit(main())
