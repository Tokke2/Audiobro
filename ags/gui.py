"""Tkinter-GUI för audiobook-goodreads-sync.

Körs med:  python -m ags.gui
Selftest:  python -m ags.gui --selftest   (bygger fönstret och avslutar)
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import ocr, presenter
from .bridge import TitleBridge
from .engine import Engine, EngineOptions
from .goodreads import Goodreads
from .models import Proposal
from . import settings as settings_mod
from .nordic import BookBeatClient, NordicFallback, StorytelClient
from .openlibrary import OpenLibrary
from .tags import mutagen_available
from . import logging_setup
import webbrowser

# Hjälpmeny — donation + språk (svenska/engelska)
STRINGS = {
    "sv": {
        "help": "Hjälp",
        "about": "Om Ljudbokssynk",
        "about_text": "Ljudbokssynk — ljudböcker \u2192 Goodreads \u2192 Audiobookshelf\n\nSt\u00f6d projektet via PayPal eller Ko-fi — tack! \u2764\ufe0f",
        "donate_paypal": "St\u00f6d projektet \u2014 PayPal",
        "donate_kofi": "St\u00f6d projektet \u2014 Ko-fi \u2615",
        "language": "Spr\u00e5k",
        "lang_sv": "Svenska",
        "lang_en": "English",
        "lang_changed": "Spr\u00e5k \u00e4ndrat till {lang} — vissa etiketter uppdateras vid omstart.",
    },
    "en": {
        "help": "Help",
        "about": "About Ljudbokssynk",
        "about_text": "Ljudbokssynk — audiobooks \u2192 Goodreads \u2192 Audiobookshelf\n\nSupport the project via PayPal or Ko-fi — thank you! \u2764\ufe0f",
        "donate_paypal": "Support the project — PayPal",
        "donate_kofi": "Support the project — Ko-fi \u2615",
        "language": "Language",
        "lang_sv": "Svenska",
        "lang_en": "English",
        "lang_changed": "Language changed to {lang} — some labels update after restart.",
    },
}
PAYPAL_URL = "https://paypal.me/Rickard3dPrint"
KOFI_URL = "https://ko-fi.com/tokke2"

# Krav 28: logga precis allt — filloggningen startar direkt vid import.
logging_setup.setup_logging()
LOG = logging_setup.get("gui")

APP_TITLE = "Ljudbok → Goodreads  (titel, författare, serie)"


class App:
    """Hela fönstret. All affärslogik ligger i ags.engine — det här är bara vy."""

    def __init__(self, root: tk.Tk | None = None, delay: float = 1.5) -> None:
        self.root = root or tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1180x780")
        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self._sticky: str | None = None
        self._iid_of: dict[int, str] = {}
        self.rows: list[dict] = []
        self.proposals: list[Proposal] = []
        self.manual_results: list[Proposal] = []
        self.engine: Engine | None = None
        self.client: Goodreads | None = None
        self._busy = False
        self._delay = tk.DoubleVar(value=delay)
        self._token = tk.StringVar(value="")
        self._series = tk.BooleanVar(value=True)
        self._auto_token = tk.BooleanVar(value=True)
        self._output = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "audiobooks"))
        self._move = tk.BooleanVar(value=False)
        self._skip_done = tk.BooleanVar(value=True)
        self._log_pos = 0
        self._recent_imports: list[str] = []
        self._recent_outputs: list[str] = []
        self._album = tk.StringVar(value="serie, #del")
        self._backup = tk.BooleanVar(value=True)
        self._replaygain = tk.BooleanVar(value=True)  # 1) ReplayGain
        self._lang = tk.StringVar(value="sv")  # språk sv/en — sparas i settings.json
        self.build()
        self.root.after(120, self._poll)

    # ------------------------------------------------------------------ bygg
    def build(self) -> None:
        self._build_settings()
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=4)
        self.tab_scan = ttk.Frame(nb)
        self.tab_manual = ttk.Frame(nb)
        self.tab_ocr = ttk.Frame(nb)
        self.tab_reco = ttk.Frame(nb)
        self.tab_log = ttk.Frame(nb)
        self.tab_hist = ttk.Frame(nb)
        nb.add(self.tab_scan, text=" 1. Skanna & organisera ")
        nb.add(self.tab_manual, text=" 2. Enskild titel / länk ")
        nb.add(self.tab_ocr, text=" 3. Skärmbild / text ")
        nb.add(self.tab_reco, text=" 4. Rekommendationer ")
        nb.add(self.tab_log, text=" 5. Logg ")
        nb.add(self.tab_hist, text=" 6. Historik ")
        self._build_scan(self.tab_scan)
        self._build_manual(self.tab_manual)
        self._build_ocr(self.tab_ocr)
        self._build_reco(self.tab_reco)
        self._build_log(self.tab_log)
        self._build_history(self.tab_hist)
        self.status = ttk.Label(self.root, text="Redo.", anchor="w", relief="sunken")
        self.status.pack(fill="x", side="bottom")
        self.prog = ttk.Progressbar(self.root, mode="determinate")
        self.prog.pack(fill="x", side="bottom", padx=6)
        for w in presenter.startup_warnings():
            self.root.after(200, lambda m=w: messagebox.showwarning("Saknas", m))

    def _build_settings(self) -> None:
        f = ttk.LabelFrame(self.root, text="Inställningar")
        f.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(f, text="Fördröjning (s):").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        ttk.Spinbox(f, from_=0.5, to=10, increment=0.5, width=5, textvariable=self._delay).grid(row=0, column=1, sticky="w")
        ttk.Label(f, text="aws-waf-token:").grid(row=0, column=2, padx=(16, 4), sticky="e")
        ttk.Entry(f, textvariable=self._token, width=36).grid(row=0, column=3, sticky="w")
        ttk.Button(f, text="Använd token", command=self._use_token).grid(row=0, column=4, padx=6)
        ttk.Checkbutton(f, text="Skriv serie-taggar (TXXX:SERIES)", variable=self._series).grid(row=1, column=0, columnspan=2, padx=6, sticky="w")
        ttk.Checkbutton(f, text="🔊 ReplayGain (jämn volym)", variable=self._replaygain).grid(row=2, column=2, padx=6, sticky="w")
        ttk.Checkbutton(f, text="Lås upp via min webbläsare (Brave/Chromium) vid blockering",
                        variable=self._auto_token).grid(row=1, column=2, columnspan=3, padx=6, sticky="w")
        ttk.Label(f, text="Album blir:").grid(row=1, column=3, sticky="e")
        ttk.Combobox(f, textvariable=self._album, width=16, state="readonly",
                     values=["serie, #del", "titel", "serienamn"]).grid(row=1, column=4, padx=6, sticky="w")
        ttk.Checkbutton(f, text="Säkerhetskopiera (.agsbak)", variable=self._backup).grid(row=2, column=0, padx=6, sticky="w")
        ttk.Checkbutton(f, text="Hoppa över redan klara (historik)", variable=self._skip_done).grid(row=2, column=1, columnspan=2, padx=6, sticky="w")
        ttk.Button(f, text="Goodreads blockerad?", command=self._show_waf_help).grid(row=2, column=4, padx=6, sticky="e")
        ttk.Button(f, text="Kontrollera tillägg", command=lambda: self._check_deps(manual=True)).grid(row=4, column=0, padx=6, pady=(0, 6), sticky="w")
        ttk.Button(f, text="Rensa cache", command=self._clean_caches).grid(row=4, column=1, padx=6, pady=(0, 6), sticky="w")
        ttk.Label(f, text="Outputmapp (Audiobookshelf):").grid(row=3, column=0, padx=6, pady=(0, 6), sticky="e")
        ttk.Entry(f, textvariable=self._output, width=52).grid(row=3, column=1, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Button(f, text="Välj…", command=self._pick_output).grid(row=3, column=3, padx=4, sticky="w")
        ttk.Button(f, text="Öppna outputmapp", command=self._open_output).grid(row=4, column=3, padx=4, sticky="w")
        ttk.Checkbutton(f, text="♻️ Flytta filerna — radera källan (sparar HDD)", variable=self._move, command=self._on_move_toggle).grid(row=3, column=4, padx=6, sticky="w")

    def _build_scan(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        self.folder = tk.StringVar(value=os.path.expanduser("~/Ljudböcker"))
        ttk.Entry(top, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Välj mapp…", command=self._pick_folder).pack(side="left", padx=4)
        self.btn_scan = ttk.Button(top, text="Skanna & matcha", command=self.start_scan)
        self.btn_scan.pack(side="left", padx=4)
        self.btn_csv = ttk.Button(top, text="Exportera CSV", command=self._export_csv, state="disabled")
        self.btn_csv.pack(side="left", padx=4)

        # packa nedre panelen FÖRST så att den alltid får plats
        # 5) Serie-tidslinje (visuell) — horisontell prick-rad för serien
        self.timeline_frame = ttk.LabelFrame(parent, text="Serie-tidslinje", padding=4)
        self.timeline_frame.pack(fill="x", side="bottom", padx=6, pady=(2, 4))
        self.timeline_canvas = tk.Canvas(self.timeline_frame, height=34, bg="#fafafa", highlightthickness=0)
        self.timeline_canvas.pack(fill="x", expand=True)
        self.timeline_hint = ttk.Label(self.timeline_frame, text="Välj en bok med serie för att se tidslinjen.", foreground="#666", font=("TkDefaultFont", 8))
        self.timeline_hint.pack()
        self.detail = tk.Text(parent, height=7, wrap="word")
        self.detail.pack(fill="x", side="bottom", padx=6, pady=(0, 4))
        bottom = ttk.Frame(parent)
        bottom.pack(fill="x", side="bottom", padx=6, pady=4)
        ttk.Button(bottom, text="Öppna i filhanterare", command=self._reveal).pack(side="left")
        ttk.Button(bottom, text="Välj bra träff…", command=self._pick_candidate).pack(side="left", padx=4)
        self.btn_apply = ttk.Button(bottom, text="Skriv taggar för valda rader", command=self._apply_selected)
        self.btn_apply.pack(side="left", padx=4)
        self.btn_apply_all = ttk.Button(bottom, text="Skriv alla gröna rader", command=self._apply_green)
        self.btn_apply_all.pack(side="left", padx=4)
        ttk.Button(bottom, text="Slå ihop markerade delar",
                   command=self._merge_selected).pack(side="left", padx=4)
        self.btn_org = ttk.Button(bottom, text="Organisera valda → output", command=self._organize_selected)
        self.btn_org.pack(side="left", padx=4)
        self.btn_org_all = ttk.Button(bottom, text="Organisera gröna + OK-frågade", command=self._organize_confirm)
        self.btn_org_all.pack(side="left", padx=4)

        cols = [c[0] for c in presenter.COLUMNS]
        self.tree = ttk.Treeview(parent, columns=cols, show="headings", height=14)
        for key, head, width in presenter.COLUMNS:
            self.tree.heading(key, text=head)
            self.tree.column(key, width=width, anchor="w")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        vsb.pack(side="left", fill="y", pady=4)
        for tag, col in (("ok", "#1b7f3b"), ("warn", "#b26a00"), ("blocked", "#b00020"),
                         ("none", "#666"), ("done", "#4477aa")):
            self.tree.tag_configure(tag, foreground=col)
        self.tree.bind("<Button-3>", self._row_menu)
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)

    def _build_manual(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Label(top, text="Titel:").grid(row=0, column=0, sticky="e", padx=4)
        self.m_title = ttk.Entry(top, width=48)
        self.m_title.grid(row=0, column=1, sticky="w")
        ttk.Label(top, text="Författare:").grid(row=0, column=2, sticky="e", padx=4)
        self.m_author = ttk.Entry(top, width=26)
        self.m_author.grid(row=0, column=3, sticky="w")
        ttk.Label(top, text="…eller Goodreads-länk:").grid(row=1, column=0, sticky="e", padx=4, pady=4)
        self.m_url = ttk.Entry(top, width=48)
        self.m_url.grid(row=1, column=1, columnspan=3, sticky="w", pady=4)
        ttk.Button(top, text="Sök", command=self.start_manual).grid(row=0, column=4, rowspan=2, padx=10)

        cols = ("pick", "score", "title", "authors", "series", "num", "year", "url")
        heads = ("", "Poäng", "Titel", "Författare", "Serie", "Del", "År", "Goodreads")
        widths = (34, 55, 300, 160, 140, 40, 50, 320)
        self.mtree = ttk.Treeview(parent, columns=cols, show="headings", height=10)
        for c, h, w in zip(cols, heads, widths):
            self.mtree.heading(c, text=h)
            self.mtree.column(c, width=w, anchor="w")
        self.mtree.pack(fill="both", expand=True, padx=6, pady=4)
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=6, pady=4)
        ttk.Label(bar, text="Skriv till fil:").pack(side="left")
        self.m_target = ttk.Entry(bar)
        self.m_target.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(bar, text="Välj fil…", command=lambda: self._pick_audio(self.m_target)).pack(side="left", padx=2)
        ttk.Button(bar, text="Skriv vald träff", command=self._apply_manual).pack(side="left", padx=4)

    def _build_ocr(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Välj skärmbild…", command=self._pick_image).pack(side="left")
        self.ocr_path = ttk.Label(top, text="ingen bild vald")
        self.ocr_path.pack(side="left", padx=8)
        ttk.Button(top, text="Läs av bild (tesseract)", command=self.start_ocr_image).pack(side="left", padx=4)
        ttk.Button(top, text="Matcha texten nedan", command=self.start_ocr_text).pack(side="left", padx=4)
        tip = ("Klistra in texten från skärmbilden här — ett titelrad per bok, gärna med "
               "\"av Författare\" på raden under. Appen rensar och matchar varje rad.")
        ttk.Label(parent, text=tip, wraplength=1080, justify="left").pack(fill="x", padx=8)
        self.ocr_text = tk.Text(parent, height=12, wrap="word")
        self.ocr_text.pack(fill="both", expand=True, padx=8, pady=4)
        self.ocr_out = tk.Text(parent, height=12, wrap="word", background="#fbfbf7")
        self.ocr_out.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ------------------------------------------------------------- hjälp
    def _engine(self) -> Engine:
        token = self._token.get().strip()
        if self.client is None:
            self.client = Goodreads(
                min_delay=float(self._delay.get()),
                browser_token=token,
                on_fetch=lambda url: self.queue.put(("log", f"hämtar {url}")),
            )
        else:
            self.client.min_delay = float(self._delay.get())
            if token:
                self.client.set_browser_token(token)
        from .browser_token import fetch_waf_token

        album_map = {"serie, #del": "title", "titel": "title", "serienamn": "series"}
        opts = EngineOptions(
            write_series=self._series.get(),
            album_style=album_map.get(self._album.get(), "title"),
            backup=self._backup.get(),
            auto_token=self._auto_token.get(),
            skip_done=self._skip_done.get(),
            replaygain=self._replaygain.get(),
        )
        self.engine = Engine(
            self.client, opts,
            on_status=lambda s: self.queue.put(("log", s)),
            on_history_hit=self._ask_history,
            fallback=NordicFallback(
                [StorytelClient(), BookBeatClient(),
                 OpenLibrary(min_delay=max(1.0, float(self._delay.get())))],
                min_delay=max(1.0, float(self._delay.get()))),
            bridge=TitleBridge(),
            token_fetcher=self._fetch_token,
        )
        return self.engine

    def _fetch_token(self) -> str:
        """Hämta WAF-token via webbläsaren; spara den i fältet + inställningarna."""
        from .browser_token import fetch_waf_token

        tok = fetch_waf_token(on_status=lambda m: self.queue.put(("log", m)))
        if tok:
            self.queue.put(("token", tok))
        return tok or ""

    def _use_token(self) -> None:
        LOG.info("knapp: Använd token")
        tok = self._token.get().strip()
        if not tok:
            messagebox.showinfo("Token", "Klistra in värdet för aws-waf-token först.")
            return
        if self.client is None:
            self._engine()
        self.client.set_browser_token(tok)
        self._save_settings(silent=True)   # krav 22: token sparas mellan körningar
        self.set_status("Token sparad — Goodreads bör fungera nu.")

    def _show_waf_help(self) -> None:
        LOG.info("knapp: Goodreads blockerad? (hjälptext)")
        messagebox.showinfo("Goodreads blockerad", presenter.WAF_HELP)

    def _clean_caches(self) -> None:
        LOG.info("knapp: Rensa cache")
        from . import cleanup

        removed = cleanup.clean_caches()
        self.set_status(f"Cacherensning klar: {len(removed)} objekt bort.")
        if removed:
            messagebox.showinfo("Cache", f"Rensade {len(removed)} cachefiler/mappar.")

    def _on_close(self) -> None:
        """Krav 16+20: spara inställningar och rensa cache vid stängning."""
        LOG.info("fönster stängs — sparar inställningar och rensar cache")
        try:
            self._save_settings(silent=True)
        except Exception:  # stängning får aldrig krascha
            pass
        try:
            from . import cleanup

            cleanup.clean_caches()
        except Exception:
            pass
        self.root.destroy()

    # ------------------------------------------------------------- tillägg
    def _on_move_toggle(self) -> None:
        """500000000000% bekräftelse — Flytta raderar källan efter verifierad kopia."""
        if self._move.get():
            ok = messagebox.askyesno(
                "Flytta – spara HDD-utrymme",
                "Flytt-läget är AKTIVT.\n\n"
                "• Källfilerna FLYTTAS (raderas efteråt) i stället för att kopieras — du sparar alltså HDD-utrymme och får ingen dubbel lagring.\n"
                "• Varje fil verifieras med storlek + SHA256-hash före raderingen (500000000000% säkert).\n"
                "• Tomma källmappar rensas automatiskt.\n"
                "• Finns filen redan i output sparas den som .över-backup och rensas när flytten lyckats.\n\n"
                "Vill du behålla Flytta aktiverat?",
                parent=self.root,
            )
            if not ok:
                self._move.set(False)
                LOG.info("Flytta avaktiverat av användaren")
            else:
                LOG.info("Flytta aktiverat — filer kommer att flyttas (hash-verifierat)")
        else:
            LOG.info("Flytta avaktiverat — filer kommer att kopieras")

    def _check_deps(self, manual: bool = False) -> None:
        LOG.info("knapp: Kontrollera tillägg (manual=%s)", manual)
        """Vid start: saknas något pip-tillägg erbjuds installation direkt."""
        from . import deps

        missing = deps.check()
        if not missing:
            if manual:
                messagebox.showinfo("Tillägg", "Alla tillägg är installerade. ✔")
            return
        pip_missing = [d for d in missing if d.pip_pkg]
        bin_missing = [d for d in missing if not d.pip_pkg]
        rader = [f"• {d.name} — behövs för: {d.needed_for}" for d in missing]
        text = "Följande tillägg saknas:\n\n" + "\n".join(rader) + "\n\n"
        if bin_missing:
            text += ("\n".join(f"{d.name}: {deps.install_hint(d)}" for d in bin_missing)
                     + "\n(Skärmbildsläget fungerar ändå om du klistrar in texten.)\n\n")
        if pip_missing and messagebox.askyesno(
                "Saknade tillägg", text + "Installera dem nu via pip?"):
            def job():
                for d in pip_missing:
                    self.queue.put(("log", f"installerar {d.pip_pkg} …"))
                    ok, _tail = deps.install_pip(d.pip_pkg)
                    self.queue.put(("log", f"{'klart' if ok else 'MISSLYCKADES'}: "
                                            f"pip install {d.pip_pkg}"))
                self.queue.put(("depsdone", ""))
            self._run_bg(job, "Installerar tillägg")
        elif manual:
            messagebox.showinfo("Saknade tillägg", text)

    def _deps_done(self) -> None:
        from . import deps

        left = deps.check()
        if not left:
            messagebox.showinfo("Tillägg", "Alla tillägg är nu installerade och "
                                           "kan användas direkt — ingen omstart krävs.")
        else:
            still = ", ".join(d.name for d in left)
            messagebox.showwarning("Tillägg", f"Installeringen är klar men detta "
                                   f"saknas fortfarande: {still}.\nLoggen har detaljerna.")

    # ------------------------------------------------------------- inställningar
    def _build_menubar(self) -> None:
        """'Kom ihåg'-meny: senaste mappar + spara inställningar (krav 20) + Hjälp/donation/språk."""
        menubar = tk.Menu(self.root)
        self.mem_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Kom ihåg", menu=self.mem_menu)
        self.mem_menu.config(postcommand=self._refresh_mem_menu)
        # Hjälpmeny — donation via PayPal/Ko-fi + språkval sv/en
        self.help_menu = tk.Menu(menubar, tearoff=0)
        t = STRINGS.get(self._lang.get(), STRINGS["sv"])
        menubar.add_cascade(label=t["help"], menu=self.help_menu)
        self.help_menu.add_command(label=t["about"], command=self._show_about)
        self.help_menu.add_separator()
        self.help_menu.add_command(label=t["donate_paypal"], command=self._open_paypal)
        self.help_menu.add_command(label=t["donate_kofi"], command=self._open_kofi)
        self.help_menu.add_separator()
        self.lang_menu = tk.Menu(self.help_menu, tearoff=0)
        self.help_menu.add_cascade(label=t["language"], menu=self.lang_menu)
        self.lang_menu.add_radiobutton(label=STRINGS["sv"]["lang_sv"], variable=self._lang, value="sv", command=lambda: self._set_lang("sv"))
        self.lang_menu.add_radiobutton(label=STRINGS["en"]["lang_en"], variable=self._lang, value="en", command=lambda: self._set_lang("en"))
        self.root.config(menu=menubar)

    def _refresh_mem_menu(self) -> None:
        m = self.mem_menu
        m.delete(0, "end")
        m.add_command(label="Spara inställningar nu", command=self._save_settings)
        m.add_separator()
        m.add_command(label="Senaste importmappar:", state="disabled")
        for d in self._recent_imports:
            m.add_command(label=f"  {d}", command=lambda v=d: self.folder.set(v))
        m.add_separator()
        m.add_command(label="Senaste outputmappar:", state="disabled")
        for d in self._recent_outputs:
            m.add_command(label=f"  {d}", command=lambda v=d: self._output.set(v))

    def _load_settings(self) -> None:
        LOG.debug("laddar inställningar")
        from . import settings

        data = settings.load()
        if not data:
            return
        if data.get("import_folder"):
            self.folder.set(data["import_folder"])
        if data.get("output_folder"):
            self._output.set(data["output_folder"])
        for var, key in ((self._series, "write_series"), (self._backup, "backup"),
                         (self._replaygain, "replaygain"),
                         (self._skip_done, "skip_done"),
                         (self._auto_token, "auto_token"), (self._move, "move")):
            if isinstance(data.get(key), bool):
                var.set(data[key])
        if isinstance(data.get("lang"), str) and data.get("lang") in ("sv", "en"):
            self._lang.set(data.get("lang"))
            try:
                self._apply_lang()
            except Exception:
                pass
        if isinstance(data.get("delay"), (int, float)):
            self._delay.set(float(data["delay"]))
        if data.get("album_style"):
            self._album.set(data["album_style"])
        if data.get("waf_token"):
            self._token.set(str(data["waf_token"]))
        self._recent_imports = [str(x) for x in data.get("recent_imports", [])]
        self._recent_outputs = [str(x) for x in data.get("recent_outputs", [])]

    def _save_settings(self, silent: bool = False) -> None:
        from . import settings

        data = {
            "import_folder": self.folder.get(),
            "output_folder": self._output.get(),
            "write_series": self._series.get(),
            "backup": self._backup.get(),
            "replaygain": self._replaygain.get(),
            "lang": self._lang.get(),
            "skip_done": self._skip_done.get(),
            "auto_token": self._auto_token.get(),
            "move": self._move.get(),
            "delay": self._delay.get(),
            "album_style": self._album.get(),
            "waf_token": self._token.get().strip(),
            "recent_imports": self._recent_imports,
            "recent_outputs": self._recent_outputs,
        }
        settings.save(data)
        LOG.info("inställningar sparade (silent=%s): import=%r output=%r "
                 "flytta=%s serie=%s skip_done=%s", silent,
                 data["import_folder"], data["output_folder"], data["move"],
                 data["write_series"], data["skip_done"])
        if not silent:
            self.set_status("Inställningar sparade.")

    def _open_output(self) -> None:
        LOG.info("knapp: Öppna outputmapp (%s)", self._output.get())
        out = self._output.get().strip()
        if not out or not os.path.isdir(out):
            messagebox.showwarning("Outputmapp", f"Mappen finns inte ännu: {out or '(tom)'}")
            return
        if sys.platform == "darwin":
            os.system(f'open "{out}"')
        elif os.name == "nt":
            os.startfile(out)  # type: ignore[attr-defined]
        else:
            os.system(f'xdg-open "{out}" >/dev/null 2>&1 &')

    def _pick_output(self) -> None:
        LOG.info("dialog: välj outputmapp")
        d = filedialog.askdirectory(title="Välj outputmapp (Audiobookshelf-bibliotek)")
        if d:
            self._output.set(d)

    # ------------------------------------------------------------- organisera
    def _organize(self, proposals: list[Proposal], ask_uncertain: bool,
                  include_done: bool = False) -> None:
        LOG.info("organisering begärd: %d förslag, ask_uncertain=%s, "
                 "include_done=%s, move=%s", len(proposals), ask_uncertain,
                 include_done, self._move.get())
        out = self._output.get().strip()
        if not proposals:
            messagebox.showinfo("Inget valt", "Markera en eller flera rader först.")
            return
        if not out:
            messagebox.showwarning("Output", "Välj en outputmapp i inställningarna.")
            return
        certain = [p for p in proposals
                   if p.status == "matchad"
                   or (include_done and p.status == "klar (historik)")]
        uncertain = [p for p in proposals if p.status == "behöver koll"]
        if uncertain:
            if ask_uncertain:
                lines = "\n".join(
                    f"• {p.audio.group_label}  ->  {p.match.book.display if p.match else '?'} "
                    f"({p.match.score:.2f})" for p in uncertain[:8])
                if not messagebox.askyesno(
                        "Osäkra matchningar",
                        f"Dessa {len(uncertain)} är osäkra och behöver din kontroll:\n\n{lines}\n\n"
                        "Organisera dem också? (Nej = bara de säkra)"):
                    uncertain = []
            else:
                uncertain = []
        todo = [p for p in certain + uncertain if not p.applied]
        if not todo:
            statuser = ", ".join(sorted({p.status for p in proposals})) or "inga"
            messagebox.showinfo(
                "Kan inte organisera",
                "De markerade raderna organiseras inte automatiskt "
                f"(status: {statuser}).\n\n'klar (historik)'-rader går att "
                "tvinga med högerklick -> 'Organisera vald bok'.")
            return
        eng = self.engine or self._engine()
        move = self._move.get()

        # Dublettskydd: samma titel+författare i outputmappen -> fråga (krav 19)
        from . import organize as _org

        self._recent_outputs = settings_mod.add_recent(self._recent_outputs, out)
        self._save_settings(silent=True)
        dups = [(p, _org.find_duplicate(p, out)) for p in todo]
        dups = [(p, d) for p, d in dups if d]
        if dups:
            rader = "\n".join(f"• {p.new_title}  ->  {d}" for p, d in dups[:8])
            if messagebox.askyesno(
                    "Finns redan i outputmappen",
                    f"Dessa böcker finns redan organiserade:\n\n{rader}\n\n"
                    "Organisera dem ändå? (Nej = hoppa över dem)"):
                pass
            else:
                skip = {id(p) for p, _ in dups}
                todo = [p for p in todo if id(p) not in skip]
                if not todo:
                    messagebox.showinfo("Inget att göra", "Alla valda fanns redan "
                                        "i outputmappen — inget organiserades.")
                    return

        def job():
            moved = copied = 0
            verb0 = "Flyttar" if move else "Kopierar"
            self.queue.put(("prog", (0, len(todo), verb0)))
            for n, p in enumerate(todo, 1):
                grp = getattr(p, "group_ref", None) or [p.audio]
                LOG.info("organiserar %r (move=%s, %d filer)", p.new_title,
                         move, len(grp))
                res = eng.organize(p, grp, out, move=move)
                LOG.info("organiserar klar för %r: %d åtgärder, %d fel",
                         p.new_title, len(res.actions), len(res.errors))
                self.queue.put(("prog", (n, len(todo),
                                        f"{verb0} — {p.new_title}")))
                if res.errors:
                    LOG.error("organiseringsfel %r: %s", p.new_title,
                              "; ".join(res.errors))
                    self.queue.put(("log", f"FEL {p.audio.group_label}: {'; '.join(res.errors)}"))
                else:
                    p.applied = True
                    moved += sum(1 for a in res.actions if a.kind == "move")
                    copied += sum(1 for a in res.actions if a.kind == "copy")
                    p.status = "klar (organiserad)"
                    self.queue.put(("rowupdate", p))
                    self.queue.put(("log", f"organiserad: {res.title_dir}"))
                    self.queue.put(("ocr", f"\nOrganiserad: {p.new_title}\n  -> {res.title_dir}"
                                            + (f"\n  faktablad: {res.md_path}" if res.md_path else "")))
            verb = "flyttade" if move else "kopierade"
            self.queue.put(("log", f"organisering klar ({verb}): "
                                    f"{moved} flyttade, {copied} kopierade filer"))
            if moved + copied:
                self.queue.put(("status",
                                f"Organiserat: {moved + copied} bok/böcker "
                                f"({moved} flyttade, {copied} kopierade) — "
                                f"taggar skrivna -> {out}"))
            else:
                self.queue.put(("status", "Organiseringen misslyckades — "
                                          "se flik 5 (Logg) för detaljer"))
        self._run_bg(job, "Organiserar")

    def _organize_selected(self) -> None:
        LOG.info("kommando: Organisera vald bok (inkl. historikrader)")
        # uttryckligt val = användaren bestämmer: även 'klar (historik)'-rader
        self._organize(self._selected_proposals(), ask_uncertain=True,
                       include_done=True)

    def _organize_confirm(self) -> None:
        LOG.info("knapp: Organisera gröna + OK-frågade")
        pros = [p for p in self.proposals if p.status in ("matchad", "behöver koll") and not p.skipped]
        self._organize(pros, ask_uncertain=True)

    # ------------------------------------------------------------- rekommendationer
    def _build_reco(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Hämta rekommendationer", command=self.start_recommend).pack(side="left")
        ttk.Label(top, text="Goodreads-förslag utifrån din historik: nästa del i serier, mer av författarna och liknande böcker.").pack(side="left", padx=8)
        self.reco_text = tk.Text(parent, wrap="word", background="#fbfbf7")
        self.reco_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def start_recommend(self) -> None:
        LOG.info("flik 4: startar rekommendationer")
        from collections import Counter

        eng = self.engine or self._engine()
        author_counts: Counter = Counter()
        series_owned: dict[str, str] = {}
        owned: list[str] = []
        for e in eng.history.entries():
            if e.get("author"):
                author_counts[e["author"].split(",")[0].strip()] += 1
            if e.get("series"):
                try:
                    if float(e.get("number") or 0) > float(series_owned.get(e["series"], "0")):
                        series_owned[e["series"]] = e.get("number") or "0"
                except ValueError:
                    pass
            if e.get("title"):
                owned.append(e["title"])
        for p in self.proposals:
            owned.append(p.new_title or p.audio.album)
            if p.new_artist:
                author_counts[p.new_artist.split(",")[0].strip()] += 1
            if p.new_series:
                series_owned.setdefault(p.new_series, p.new_series_number or "0")
        if not author_counts:
            messagebox.showinfo("Rekommendationer",
                                "Ingen historik ännu — skanna eller organisera några böcker först.")
            return
        self.reco_text.delete("1.0", "end")

        def job():
            recs = eng.recommend(owned, author_counts, series_owned)
            if not recs:
                self.queue.put(("reco", "Inga förslag just nu (Goodreads nås inte eller allt är redan ditt)."))
            for r in recs:
                b = r.book
                self.queue.put(("reco", f"{r.reason}\n  -> {b.display}\n     {b.url}\n"))
        self._run_bg(job, "Hämtar rekommendationer")

    # ------------------------------------------------------------- historik
    def _build_history(self, parent) -> None:
        """Krav 21: organiserade böcker arkiveras här och matchas inte på nytt."""
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Uppdatera", command=self._refresh_history).pack(side="left")
        ttk.Button(top, text="Öppna mapp", command=self._open_history_folder).pack(side="left", padx=4)
        ttk.Button(top, text="Ta bort post", command=self._remove_history_entry).pack(side="left", padx=4)
        ttk.Button(top, text="Rensa allt", command=self._clear_history).pack(side="left", padx=4)
        ttk.Button(top, text="🔄 Sök uppdateringar i output", command=self._start_refresh).pack(side="left", padx=12)
        ttk.Button(top, text="Uppdatera valda", command=self._apply_refresh).pack(side="left", padx=4)
        ttk.Label(top, text="Organiserade böcker arkiveras här — de matchas aldrig om.").pack(side="left", padx=8)
        cols = ("when", "title", "author", "series", "number", "output")
        self.htree = ttk.Treeview(parent, columns=cols, show="headings", height=14)
        for key, head, w in (("when", "Datum", 130), ("title", "Titel", 240),
                             ("author", "Författare", 160), ("series", "Serie", 140),
                             ("number", "Del", 40), ("output", "Outputmapp", 320)):
            self.htree.heading(key, text=head)
            self.htree.column(key, width=w)
        self.htree.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._refresh_history()

    def _refresh_history(self) -> None:
        LOG.debug("historikfliken uppdateras")
        from .history import History

        for iid in self.htree.get_children():
            self.htree.delete(iid)
        for e in History().entries():
            self.htree.insert("", "end", values=(
                (e.get("ts") or "")[:16].replace("T", " "),
                e.get("title", ""), e.get("author", ""),
                e.get("series", ""), e.get("number", ""), e.get("output", "")))

    def _history_selected(self) -> list[dict]:
        from .history import History

        idx = [self.htree.index(i) for i in self.htree.selection()]
        ents = History().entries()
        return [ents[i] for i in idx if i < len(ents)]

    def _open_history_folder(self) -> None:
        LOG.info("öppnar historikmappen")
        sel = self._history_selected()
        if not sel or not sel[0].get("output"):
            return
        folder = os.path.dirname(sel[0]["output"]) if os.path.isfile(sel[0]["output"]) else sel[0]["output"]
        if sys.platform == "darwin":
            os.system(f'open "{folder}"')
        elif os.name == "nt":
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            os.system(f'xdg-open "{folder}" >/dev/null 2>&1 &')

    def _remove_history_entry(self) -> None:
        LOG.info("tar bort markerad historikpost")
        sel = self._history_selected()
        if not sel:
            messagebox.showinfo("Historik", "Markera en post först.")
            return
        if not messagebox.askyesno("Historik", f"Ta bort '{sel[0].get('title')}' ur "
                                   "historiken? Boken kan då matchas på nytt."):
            return
        from .history import History

        h = History()
        for e in sel:
            h.remove(e.get("key", ""))
        self._refresh_history()

    def _clear_history(self) -> None:
        LOG.info("rensar hela historiken")
        if not messagebox.askyesno("Historik", "Rensa HELA historiken? Alla böcker "
                                   "kan då matchas på nytt."):
            return
        from .history import History

        History().clear()
        self._refresh_history()

    # ---------------------------------------------- fråga vid historikträff (krav 21)
    def _ask_history(self, proposal, ent) -> bool:
        """'Tidigare importerad — hoppa över?' Körs i skanntråden; dialogen
        visas i huvudtråden via kön och tråden väntar på svaret."""
        import threading

        ev = threading.Event()
        answer = {"skip": True}   # ingen svarar (t.ex. fönster stängt) -> hoppa över
        title = proposal.new_title or proposal.audio.title or "?"
        author = proposal.new_artist or proposal.audio.artist or "?"
        when = (ent.get("finished_at") or "").strip()
        self.queue.put(("askhist", (title, author, when, ev, answer)))
        ev.wait(timeout=600)
        return bool(answer["skip"])

    # ------------------------------------------------------------- logg
    def _build_log(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Uppdatera", command=self._reload_log).pack(side="left")
        ttk.Button(top, text="Öppna loggfilen", command=self._open_log).pack(side="left", padx=4)
        from .logging_setup import DEFAULT_LOG as _dl
        ttk.Label(top, text=f"Allt som händer loggas till {_dl}").pack(side="left", padx=8)
        self.log_text = tk.Text(parent, wrap="none", background="#101010", foreground="#c8c8c8")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.root.after(500, self._tail_log)
        self.root.after(900, lambda: self._check_deps(False))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_menubar()
        self._load_settings()
        for var in (self.folder, self._output):
            var.trace_add("write", lambda *a: self._save_settings(silent=True))

    def _open_log(self) -> None:
        LOG.info("öppnar loggfilen")
        from .logging_setup import DEFAULT_LOG

        path = DEFAULT_LOG
        if sys.platform == "darwin":
            os.system(f'open "{path}"')
        elif os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')

    def _reload_log(self) -> None:
        LOG.info("logg: uppdatera")
        self._log_pos = 0
        self._recent_imports: list[str] = []
        self._recent_outputs: list[str] = []
        self.log_text.delete("1.0", "end")
        self._tail_log()

    def _tail_log(self) -> None:
        LOG.debug("logg: tail")
        from .logging_setup import DEFAULT_LOG

        try:
            with open(DEFAULT_LOG, encoding="utf-8", errors="replace") as fh:
                fh.seek(self._log_pos)
                chunk = fh.read()
                self._log_pos = fh.tell()
            if chunk:
                self.log_text.insert("end", chunk)
                self.log_text.see("end")
        except OSError:
            pass
        self.root.after(2500, self._tail_log)

    def set_status(self, text: str) -> None:
        self.status.config(text=text)

    def _pick_folder(self) -> None:
        LOG.info("dialog: välj importmapp")
        d = filedialog.askdirectory(title="Välj mapp med ljudböcker")
        if d:
            self.folder.set(d)

    def _pick_audio(self, var) -> None:
        LOG.info("dialog: välj ljudfil")
        f = filedialog.askopenfilename(
            title="Välj ljudfil",
            filetypes=[("Ljud", "*.mp3 *.m4b *.m4a *.flac *.ogg *.opus"), ("Alla", "*.*")],
        )
        if f:
            var.set(f)

    def _pick_image(self) -> None:
        LOG.info("dialog: välj skärmbild")
        f = filedialog.askopenfilename(title="Välj skärmbild", filetypes=[("Bild", "*.png *.jpg *.jpeg *.webp")])
        if f:
            self.ocr_path.config(text=os.path.basename(f))
            self._image_path = f

    def _busy_on(self, label: str) -> None:
        self._busy = True
        self.set_status(f"{label} …")
        for b in (self.btn_scan, self.btn_apply, self.btn_apply_all):
            b.config(state="disabled")

    def _busy_off(self) -> None:
        self._busy = False
        for b in (self.btn_scan,):
            b.config(state="normal")
        if self.rows:
            self.btn_csv.config(state="normal")
            self.btn_apply.config(state="normal")
            self.btn_apply_all.config(state="normal")

    # ------------------------------------------------------------- trådar
    def _run_bg(self, fn, done_label: str) -> None:
        if self._busy:
            LOG.warning("jobb '%s' HOPPAS ÖVER: ett annat jobb pågår redan",
                        done_label)
            self.set_status("Ett annat jobb pågår fortfarande — vänta på "
                            "'klart' i statusraden och försök igen.")
            return
        self._busy_on(done_label)
        LOG.info("jobb startar: %s", done_label)

        def worker():
            LOG.debug("jobbtråd kör: %s", done_label)
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                LOG.exception("jobb kraschade (%s)", done_label)
                self.queue.put(("error", f"{type(exc).__name__}: {exc}"))
            finally:
                self.queue.put(("done", done_label))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self) -> None:
        """Krav 28: får ALDRIG dö — en krasch i en enskild händelse får inte
        tysta hela appen (tidigare dog hela kön tyst vid ett undantag)."""
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                try:
                    self._handle_event(kind, payload)
                except Exception:
                    LOG.exception("KRASCH vid händelse %s", kind)
        except queue.Empty:
            pass
        finally:
            self.root.after(120, self._poll)

    def _handle_event(self, kind, payload) -> None:
        if kind == "log":
            LOG.info("ui-status: %s", payload)
            self.set_status(payload)
        elif kind == "row":
            self._add_row(payload)
        elif kind == "manual":
            self._show_manual(payload)
        elif kind == "ocr":
            self.ocr_out.insert("end", payload + "\n")
            self.ocr_out.see("end")
        elif kind == "reco":
            self.reco_text.insert("end", payload + "\n")
            self.reco_text.see("end")
        elif kind == "error":
            LOG.error("jobb-fel visas för användaren: %s", payload)
            self.set_status(f"FEL: {payload}")
            messagebox.showerror("Fel", payload)
        elif kind == "depsdone":
            self._busy_off()
            self._deps_done()
        elif kind == "prog":
            cur, total, label = payload
            if total:
                pct = round(100 * cur / total)
                self.prog.config(maximum=total, value=cur)
                self.set_status(f"{label} {cur}/{total} ({pct} %)")
            else:
                self.set_status(label)
        elif kind == "status":
            self._sticky = payload
            self.set_status(payload)
        elif kind == "token":
            self._token.set(payload)
            self._save_settings(silent=True)
            self.set_status("WAF-token hämtad och sparad.")
        elif kind == "rowupdate":
            self._update_row(payload)
        elif kind == "askhist":
            title, author, when, ev, answer = payload
            answer["skip"] = messagebox.askyesno(
                "Tidigare importerad",
                f"'{title}' av {author} är tidigare importerad"
                + (f" ({when})." if when else ".")
                + "\n\nJa = hoppa över (slipper importeras igen)"
                  "\nNej = matcha på nytt ändå")
            LOG.info("historikfråga '%s': %s", title,
                     "hoppa över" if answer["skip"] else "matcha igen")
            ev.set()
        elif kind == "refresh_one":
            # enstaka förslag från refresh-scanningen — lägg till rad eller uppdatera historik-rad
            prop = payload
            # lägg i proposals-listan och markera i tabellen om den redan finns
            # Spara för senare apply
            if not hasattr(self, "_refresh_proposals"):
                self._refresh_proposals = []
            self._refresh_proposals.append(prop)
            # uppdatera status i historikträdet: hitta rad med samma titel
            try:
                for iid in self.htree.get_children():
                    vals = self.htree.item(iid, "values")
                    # vals: when, title, author, series, number, output
                    if vals and vals[1] == prop.new_title and prop.new_artist.split(",")[0] in vals[2]:
                        # markera raden som behöver uppdateras (gul)
                        self.htree.set(iid, "title", f"🔄 {prop.new_title}")
                        break
            except Exception:
                pass
            LOG.info("refresh hittade %s — %s", prop.new_title, prop.status)
            self.set_status(f"Hittade: {prop.new_title} — {prop.status}")
        elif kind == "refresh_done":
            proposals = payload or []
            self._refresh_proposals = proposals
            need = sum(1 for pr in proposals if getattr(pr, "status", "") == "behöver uppdateras")
            LOG.info("refresh klart: %d skannade, %d behöver uppdateras", len(proposals), need)
            self._busy_off()
            self.prog.config(value=0)
            if need:
                self.set_status(f"Uppdateringssök klar: {need} av {len(proposals)} behöver uppdateras — markera i Historik och klicka 'Uppdatera valda'.")
                messagebox.showinfo("Uppdateringar", f"{need} av {len(proposals)} böcker i output behöver uppdateras.\n\nMarkera dem i Historik-tabellen och klicka 'Uppdatera valda'.", parent=self.root)
            else:
                self.set_status(f"Allt aktuellt — {len(proposals)} böcker kollade, ingen behöver uppdateras.")
                if proposals:
                    messagebox.showinfo("Uppdateringar", f"Alla {len(proposals)} böcker i output är redan aktuella.", parent=self.root)
                else:
                    messagebox.showwarning("Uppdateringar", "Inga böcker hittades i outputmappen.", parent=self.root)
            try:
                self._refresh_history()
            except Exception:
                pass
        elif kind == "refresh_applied":
            ok, fail = payload
            LOG.info("refresh apply klart: %d ok, %d fel", ok, fail)
            self._busy_off()
            self.prog.config(value=0)
            self.set_status(f"Uppdaterat: {ok} ok, {fail} fel.")
            messagebox.showinfo("Klart", f"Uppdaterat {ok} bok/böcker, {fail} fel.", parent=self.root)
            try:
                self._refresh_history()
            except Exception:
                pass
        elif kind == "done":
            LOG.info("jobb klart: %s", payload)
            self._busy_off()
            self.prog.config(value=0)
            self._sort_rows()
            try:
                self._refresh_history()
            except Exception:
                pass
            n_grona = sum(1 for p in self.proposals if p.status == "matchad")
            hint = (f" {n_grona} gröna rader -> knappen 'Organisera gröna + "
                    "OK-frågade' flyttar/kopierar dem till outputmappen."
                    if n_grona else "")
            self.set_status(f"{payload} — klart.{hint} "
                            f"{presenter.summary_text(self.rows) if self.rows else ''}")
            if self._sticky:
                self.set_status(self._sticky)
                self._sticky = None

    # ------------------------------------------------------------------ bygg
    def build(self) -> None:
        self._build_settings()
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=4)
        self.tab_scan = ttk.Frame(nb)
        self.tab_manual = ttk.Frame(nb)
        self.tab_ocr = ttk.Frame(nb)
        self.tab_reco = ttk.Frame(nb)
        self.tab_log = ttk.Frame(nb)
        self.tab_hist = ttk.Frame(nb)
        nb.add(self.tab_scan, text=" 1. Skanna & organisera ")
        nb.add(self.tab_manual, text=" 2. Enskild titel / länk ")
        nb.add(self.tab_ocr, text=" 3. Skärmbild / text ")
        nb.add(self.tab_reco, text=" 4. Rekommendationer ")
        nb.add(self.tab_log, text=" 5. Logg ")
        nb.add(self.tab_hist, text=" 6. Historik ")
        self._build_scan(self.tab_scan)
        self._build_manual(self.tab_manual)
        self._build_ocr(self.tab_ocr)
        self._build_reco(self.tab_reco)
        self._build_log(self.tab_log)
        self._build_history(self.tab_hist)
        self.status = ttk.Label(self.root, text="Redo.", anchor="w", relief="sunken")
        self.status.pack(fill="x", side="bottom")
        self.prog = ttk.Progressbar(self.root, mode="determinate")
        self.prog.pack(fill="x", side="bottom", padx=6)
        for w in presenter.startup_warnings():
            self.root.after(200, lambda m=w: messagebox.showwarning("Saknas", m))

    def _build_settings(self) -> None:
        f = ttk.LabelFrame(self.root, text="Inställningar")
        f.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(f, text="Fördröjning (s):").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        ttk.Spinbox(f, from_=0.5, to=10, increment=0.5, width=5, textvariable=self._delay).grid(row=0, column=1, sticky="w")
        ttk.Label(f, text="aws-waf-token:").grid(row=0, column=2, padx=(16, 4), sticky="e")
        ttk.Entry(f, textvariable=self._token, width=36).grid(row=0, column=3, sticky="w")
        ttk.Button(f, text="Använd token", command=self._use_token).grid(row=0, column=4, padx=6)
        ttk.Checkbutton(f, text="Skriv serie-taggar (TXXX:SERIES)", variable=self._series).grid(row=1, column=0, columnspan=2, padx=6, sticky="w")
        ttk.Checkbutton(f, text="🔊 ReplayGain (jämn volym)", variable=self._replaygain).grid(row=2, column=2, padx=6, sticky="w")
        ttk.Checkbutton(f, text="Lås upp via min webbläsare (Brave/Chromium) vid blockering",
                        variable=self._auto_token).grid(row=1, column=2, columnspan=3, padx=6, sticky="w")
        ttk.Label(f, text="Album blir:").grid(row=1, column=3, sticky="e")
        ttk.Combobox(f, textvariable=self._album, width=16, state="readonly",
                     values=["serie, #del", "titel", "serienamn"]).grid(row=1, column=4, padx=6, sticky="w")
        ttk.Checkbutton(f, text="Säkerhetskopiera (.agsbak)", variable=self._backup).grid(row=2, column=0, padx=6, sticky="w")
        ttk.Checkbutton(f, text="Hoppa över redan klara (historik)", variable=self._skip_done).grid(row=2, column=1, columnspan=2, padx=6, sticky="w")
        ttk.Button(f, text="Goodreads blockerad?", command=self._show_waf_help).grid(row=2, column=4, padx=6, sticky="e")
        ttk.Button(f, text="Kontrollera tillägg", command=lambda: self._check_deps(manual=True)).grid(row=4, column=0, padx=6, pady=(0, 6), sticky="w")
        ttk.Button(f, text="Rensa cache", command=self._clean_caches).grid(row=4, column=1, padx=6, pady=(0, 6), sticky="w")
        ttk.Label(f, text="Outputmapp (Audiobookshelf):").grid(row=3, column=0, padx=6, pady=(0, 6), sticky="e")
        ttk.Entry(f, textvariable=self._output, width=52).grid(row=3, column=1, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Button(f, text="Välj…", command=self._pick_output).grid(row=3, column=3, padx=4, sticky="w")
        ttk.Button(f, text="Öppna outputmapp", command=self._open_output).grid(row=4, column=3, padx=4, sticky="w")
        ttk.Checkbutton(f, text="♻️ Flytta filerna — radera källan (sparar HDD)", variable=self._move, command=self._on_move_toggle).grid(row=3, column=4, padx=6, sticky="w")

    def _build_scan(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        self.folder = tk.StringVar(value=os.path.expanduser("~/Ljudböcker"))
        ttk.Entry(top, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Välj mapp…", command=self._pick_folder).pack(side="left", padx=4)
        self.btn_scan = ttk.Button(top, text="Skanna & matcha", command=self.start_scan)
        self.btn_scan.pack(side="left", padx=4)
        self.btn_csv = ttk.Button(top, text="Exportera CSV", command=self._export_csv, state="disabled")
        self.btn_csv.pack(side="left", padx=4)

        # packa nedre panelen FÖRST så att den alltid får plats
        # 5) Serie-tidslinje (visuell) — horisontell prick-rad för serien
        self.timeline_frame = ttk.LabelFrame(parent, text="Serie-tidslinje", padding=4)
        self.timeline_frame.pack(fill="x", side="bottom", padx=6, pady=(2, 4))
        self.timeline_canvas = tk.Canvas(self.timeline_frame, height=34, bg="#fafafa", highlightthickness=0)
        self.timeline_canvas.pack(fill="x", expand=True)
        self.timeline_hint = ttk.Label(self.timeline_frame, text="Välj en bok med serie för att se tidslinjen.", foreground="#666", font=("TkDefaultFont", 8))
        self.timeline_hint.pack()
        self.detail = tk.Text(parent, height=7, wrap="word")
        self.detail.pack(fill="x", side="bottom", padx=6, pady=(0, 4))
        bottom = ttk.Frame(parent)
        bottom.pack(fill="x", side="bottom", padx=6, pady=4)
        ttk.Button(bottom, text="Öppna i filhanterare", command=self._reveal).pack(side="left")
        ttk.Button(bottom, text="Välj bra träff…", command=self._pick_candidate).pack(side="left", padx=4)
        self.btn_apply = ttk.Button(bottom, text="Skriv taggar för valda rader", command=self._apply_selected)
        self.btn_apply.pack(side="left", padx=4)
        self.btn_apply_all = ttk.Button(bottom, text="Skriv alla gröna rader", command=self._apply_green)
        self.btn_apply_all.pack(side="left", padx=4)
        ttk.Button(bottom, text="Slå ihop markerade delar",
                   command=self._merge_selected).pack(side="left", padx=4)
        self.btn_org = ttk.Button(bottom, text="Organisera valda → output", command=self._organize_selected)
        self.btn_org.pack(side="left", padx=4)
        self.btn_org_all = ttk.Button(bottom, text="Organisera gröna + OK-frågade", command=self._organize_confirm)
        self.btn_org_all.pack(side="left", padx=4)

        cols = [c[0] for c in presenter.COLUMNS]
        self.tree = ttk.Treeview(parent, columns=cols, show="headings", height=14)
        for key, head, width in presenter.COLUMNS:
            self.tree.heading(key, text=head)
            self.tree.column(key, width=width, anchor="w")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        vsb.pack(side="left", fill="y", pady=4)
        for tag, col in (("ok", "#1b7f3b"), ("warn", "#b26a00"), ("blocked", "#b00020"),
                         ("none", "#666"), ("done", "#4477aa")):
            self.tree.tag_configure(tag, foreground=col)
        self.tree.bind("<Button-3>", self._row_menu)
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)

    def _build_manual(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Label(top, text="Titel:").grid(row=0, column=0, sticky="e", padx=4)
        self.m_title = ttk.Entry(top, width=48)
        self.m_title.grid(row=0, column=1, sticky="w")
        ttk.Label(top, text="Författare:").grid(row=0, column=2, sticky="e", padx=4)
        self.m_author = ttk.Entry(top, width=26)
        self.m_author.grid(row=0, column=3, sticky="w")
        ttk.Label(top, text="…eller Goodreads-länk:").grid(row=1, column=0, sticky="e", padx=4, pady=4)
        self.m_url = ttk.Entry(top, width=48)
        self.m_url.grid(row=1, column=1, columnspan=3, sticky="w", pady=4)
        ttk.Button(top, text="Sök", command=self.start_manual).grid(row=0, column=4, rowspan=2, padx=10)

        cols = ("pick", "score", "title", "authors", "series", "num", "year", "url")
        heads = ("", "Poäng", "Titel", "Författare", "Serie", "Del", "År", "Goodreads")
        widths = (34, 55, 300, 160, 140, 40, 50, 320)
        self.mtree = ttk.Treeview(parent, columns=cols, show="headings", height=10)
        for c, h, w in zip(cols, heads, widths):
            self.mtree.heading(c, text=h)
            self.mtree.column(c, width=w, anchor="w")
        self.mtree.pack(fill="both", expand=True, padx=6, pady=4)
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=6, pady=4)
        ttk.Label(bar, text="Skriv till fil:").pack(side="left")
        self.m_target = ttk.Entry(bar)
        self.m_target.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(bar, text="Välj fil…", command=lambda: self._pick_audio(self.m_target)).pack(side="left", padx=2)
        ttk.Button(bar, text="Skriv vald träff", command=self._apply_manual).pack(side="left", padx=4)

    def _build_ocr(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Välj skärmbild…", command=self._pick_image).pack(side="left")
        self.ocr_path = ttk.Label(top, text="ingen bild vald")
        self.ocr_path.pack(side="left", padx=8)
        ttk.Button(top, text="Läs av bild (tesseract)", command=self.start_ocr_image).pack(side="left", padx=4)
        ttk.Button(top, text="Matcha texten nedan", command=self.start_ocr_text).pack(side="left", padx=4)
        tip = ("Klistra in texten från skärmbilden här — ett titelrad per bok, gärna med "
               "\"av Författare\" på raden under. Appen rensar och matchar varje rad.")
        ttk.Label(parent, text=tip, wraplength=1080, justify="left").pack(fill="x", padx=8)
        self.ocr_text = tk.Text(parent, height=12, wrap="word")
        self.ocr_text.pack(fill="both", expand=True, padx=8, pady=4)
        self.ocr_out = tk.Text(parent, height=12, wrap="word", background="#fbfbf7")
        self.ocr_out.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ------------------------------------------------------------- hjälp
    def _engine(self) -> Engine:
        token = self._token.get().strip()
        if self.client is None:
            self.client = Goodreads(
                min_delay=float(self._delay.get()),
                browser_token=token,
                on_fetch=lambda url: self.queue.put(("log", f"hämtar {url}")),
            )
        else:
            self.client.min_delay = float(self._delay.get())
            if token:
                self.client.set_browser_token(token)
        from .browser_token import fetch_waf_token

        album_map = {"serie, #del": "title", "titel": "title", "serienamn": "series"}
        opts = EngineOptions(
            write_series=self._series.get(),
            album_style=album_map.get(self._album.get(), "title"),
            backup=self._backup.get(),
            auto_token=self._auto_token.get(),
            skip_done=self._skip_done.get(),
            replaygain=self._replaygain.get(),
        )
        self.engine = Engine(
            self.client, opts,
            on_status=lambda s: self.queue.put(("log", s)),
            on_history_hit=self._ask_history,
            fallback=NordicFallback(
                [StorytelClient(), BookBeatClient(),
                 OpenLibrary(min_delay=max(1.0, float(self._delay.get())))],
                min_delay=max(1.0, float(self._delay.get()))),
            bridge=TitleBridge(),
            token_fetcher=self._fetch_token,
        )
        return self.engine

    def _fetch_token(self) -> str:
        """Hämta WAF-token via webbläsaren; spara den i fältet + inställningarna."""
        from .browser_token import fetch_waf_token

        tok = fetch_waf_token(on_status=lambda m: self.queue.put(("log", m)))
        if tok:
            self.queue.put(("token", tok))
        return tok or ""

    def _use_token(self) -> None:
        LOG.info("knapp: Använd token")
        tok = self._token.get().strip()
        if not tok:
            messagebox.showinfo("Token", "Klistra in värdet för aws-waf-token först.")
            return
        if self.client is None:
            self._engine()
        self.client.set_browser_token(tok)
        self._save_settings(silent=True)   # krav 22: token sparas mellan körningar
        self.set_status("Token sparad — Goodreads bör fungera nu.")

    def _show_waf_help(self) -> None:
        LOG.info("knapp: Goodreads blockerad? (hjälptext)")
        messagebox.showinfo("Goodreads blockerad", presenter.WAF_HELP)

    def _clean_caches(self) -> None:
        LOG.info("knapp: Rensa cache")
        from . import cleanup

        removed = cleanup.clean_caches()
        self.set_status(f"Cacherensning klar: {len(removed)} objekt bort.")
        if removed:
            messagebox.showinfo("Cache", f"Rensade {len(removed)} cachefiler/mappar.")

    def _on_close(self) -> None:
        """Krav 16+20: spara inställningar och rensa cache vid stängning."""
        LOG.info("fönster stängs — sparar inställningar och rensar cache")
        try:
            self._save_settings(silent=True)
        except Exception:  # stängning får aldrig krascha
            pass
        try:
            from . import cleanup

            cleanup.clean_caches()
        except Exception:
            pass
        self.root.destroy()

    # ------------------------------------------------------------- tillägg
    def _on_move_toggle(self) -> None:
        """500000000000% bekräftelse — Flytta raderar källan efter verifierad kopia."""
        if self._move.get():
            ok = messagebox.askyesno(
                "Flytta – spara HDD-utrymme",
                "Flytt-läget är AKTIVT.\n\n"
                "• Källfilerna FLYTTAS (raderas efteråt) i stället för att kopieras — du sparar alltså HDD-utrymme och får ingen dubbel lagring.\n"
                "• Varje fil verifieras med storlek + SHA256-hash före raderingen (500000000000% säkert).\n"
                "• Tomma källmappar rensas automatiskt.\n"
                "• Finns filen redan i output sparas den som .över-backup och rensas när flytten lyckats.\n\n"
                "Vill du behålla Flytta aktiverat?",
                parent=self.root,
            )
            if not ok:
                self._move.set(False)
                LOG.info("Flytta avaktiverat av användaren")
            else:
                LOG.info("Flytta aktiverat — filer kommer att flyttas (hash-verifierat)")
        else:
            LOG.info("Flytta avaktiverat — filer kommer att kopieras")

    def _check_deps(self, manual: bool = False) -> None:
        LOG.info("knapp: Kontrollera tillägg (manual=%s)", manual)
        """Vid start: saknas något pip-tillägg erbjuds installation direkt."""
        from . import deps

        missing = deps.check()
        if not missing:
            if manual:
                messagebox.showinfo("Tillägg", "Alla tillägg är installerade. ✔")
            return
        pip_missing = [d for d in missing if d.pip_pkg]
        bin_missing = [d for d in missing if not d.pip_pkg]
        rader = [f"• {d.name} — behövs för: {d.needed_for}" for d in missing]
        text = "Följande tillägg saknas:\n\n" + "\n".join(rader) + "\n\n"
        if bin_missing:
            text += ("\n".join(f"{d.name}: {deps.install_hint(d)}" for d in bin_missing)
                     + "\n(Skärmbildsläget fungerar ändå om du klistrar in texten.)\n\n")
        if pip_missing and messagebox.askyesno(
                "Saknade tillägg", text + "Installera dem nu via pip?"):
            def job():
                for d in pip_missing:
                    self.queue.put(("log", f"installerar {d.pip_pkg} …"))
                    ok, _tail = deps.install_pip(d.pip_pkg)
                    self.queue.put(("log", f"{'klart' if ok else 'MISSLYCKADES'}: "
                                            f"pip install {d.pip_pkg}"))
                self.queue.put(("depsdone", ""))
            self._run_bg(job, "Installerar tillägg")
        elif manual:
            messagebox.showinfo("Saknade tillägg", text)

    def _deps_done(self) -> None:
        from . import deps

        left = deps.check()
        if not left:
            messagebox.showinfo("Tillägg", "Alla tillägg är nu installerade och "
                                           "kan användas direkt — ingen omstart krävs.")
        else:
            still = ", ".join(d.name for d in left)
            messagebox.showwarning("Tillägg", f"Installeringen är klar men detta "
                                   f"saknas fortfarande: {still}.\nLoggen har detaljerna.")

    # ------------------------------------------------------------- inställningar
    def _build_menubar(self) -> None:
        """'Kom ihåg'-meny: senaste mappar + spara inställningar (krav 20) + Hjälp/donation/språk."""
        menubar = tk.Menu(self.root)
        self.mem_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Kom ihåg", menu=self.mem_menu)
        self.mem_menu.config(postcommand=self._refresh_mem_menu)
        # Hjälpmeny — donation via PayPal/Ko-fi + språkval sv/en
        self.help_menu = tk.Menu(menubar, tearoff=0)
        t = STRINGS.get(self._lang.get(), STRINGS["sv"])
        menubar.add_cascade(label=t["help"], menu=self.help_menu)
        self.help_menu.add_command(label=t["about"], command=self._show_about)
        self.help_menu.add_separator()
        self.help_menu.add_command(label=t["donate_paypal"], command=self._open_paypal)
        self.help_menu.add_command(label=t["donate_kofi"], command=self._open_kofi)
        self.help_menu.add_separator()
        self.lang_menu = tk.Menu(self.help_menu, tearoff=0)
        self.help_menu.add_cascade(label=t["language"], menu=self.lang_menu)
        self.lang_menu.add_radiobutton(label=STRINGS["sv"]["lang_sv"], variable=self._lang, value="sv", command=lambda: self._set_lang("sv"))
        self.lang_menu.add_radiobutton(label=STRINGS["en"]["lang_en"], variable=self._lang, value="en", command=lambda: self._set_lang("en"))
        self.root.config(menu=menubar)

    def _refresh_mem_menu(self) -> None:
        m = self.mem_menu
        m.delete(0, "end")
        m.add_command(label="Spara inställningar nu", command=self._save_settings)
        m.add_separator()
        m.add_command(label="Senaste importmappar:", state="disabled")
        for d in self._recent_imports:
            m.add_command(label=f"  {d}", command=lambda v=d: self.folder.set(v))
        m.add_separator()
        m.add_command(label="Senaste outputmappar:", state="disabled")
        for d in self._recent_outputs:
            m.add_command(label=f"  {d}", command=lambda v=d: self._output.set(v))

    def _load_settings(self) -> None:
        LOG.debug("laddar inställningar")
        from . import settings

        data = settings.load()
        if not data:
            return
        if data.get("import_folder"):
            self.folder.set(data["import_folder"])
        if data.get("output_folder"):
            self._output.set(data["output_folder"])
        for var, key in ((self._series, "write_series"), (self._backup, "backup"),
                         (self._replaygain, "replaygain"),
                         (self._skip_done, "skip_done"),
                         (self._auto_token, "auto_token"), (self._move, "move")):
            if isinstance(data.get(key), bool):
                var.set(data[key])
        if isinstance(data.get("lang"), str) and data.get("lang") in ("sv", "en"):
            self._lang.set(data.get("lang"))
            try:
                self._apply_lang()
            except Exception:
                pass
        if isinstance(data.get("delay"), (int, float)):
            self._delay.set(float(data["delay"]))
        if data.get("album_style"):
            self._album.set(data["album_style"])
        if data.get("waf_token"):
            self._token.set(str(data["waf_token"]))
        self._recent_imports = [str(x) for x in data.get("recent_imports", [])]
        self._recent_outputs = [str(x) for x in data.get("recent_outputs", [])]

    def _save_settings(self, silent: bool = False) -> None:
        from . import settings

        data = {
            "import_folder": self.folder.get(),
            "output_folder": self._output.get(),
            "write_series": self._series.get(),
            "backup": self._backup.get(),
            "replaygain": self._replaygain.get(),
            "lang": self._lang.get(),
            "skip_done": self._skip_done.get(),
            "auto_token": self._auto_token.get(),
            "move": self._move.get(),
            "delay": self._delay.get(),
            "album_style": self._album.get(),
            "waf_token": self._token.get().strip(),
            "recent_imports": self._recent_imports,
            "recent_outputs": self._recent_outputs,
        }
        settings.save(data)
        LOG.info("inställningar sparade (silent=%s): import=%r output=%r "
                 "flytta=%s serie=%s skip_done=%s", silent,
                 data["import_folder"], data["output_folder"], data["move"],
                 data["write_series"], data["skip_done"])
        if not silent:
            self.set_status("Inställningar sparade.")

    def _open_output(self) -> None:
        LOG.info("knapp: Öppna outputmapp (%s)", self._output.get())
        out = self._output.get().strip()
        if not out or not os.path.isdir(out):
            messagebox.showwarning("Outputmapp", f"Mappen finns inte ännu: {out or '(tom)'}")
            return
        if sys.platform == "darwin":
            os.system(f'open "{out}"')
        elif os.name == "nt":
            os.startfile(out)  # type: ignore[attr-defined]
        else:
            os.system(f'xdg-open "{out}" >/dev/null 2>&1 &')

    def _pick_output(self) -> None:
        LOG.info("dialog: välj outputmapp")
        d = filedialog.askdirectory(title="Välj outputmapp (Audiobookshelf-bibliotek)")
        if d:
            self._output.set(d)

    # ------------------------------------------------------------- organisera
    def _organize(self, proposals: list[Proposal], ask_uncertain: bool,
                  include_done: bool = False) -> None:
        LOG.info("organisering begärd: %d förslag, ask_uncertain=%s, "
                 "include_done=%s, move=%s", len(proposals), ask_uncertain,
                 include_done, self._move.get())
        out = self._output.get().strip()
        if not proposals:
            messagebox.showinfo("Inget valt", "Markera en eller flera rader först.")
            return
        if not out:
            messagebox.showwarning("Output", "Välj en outputmapp i inställningarna.")
            return
        certain = [p for p in proposals
                   if p.status == "matchad"
                   or (include_done and p.status == "klar (historik)")]
        uncertain = [p for p in proposals if p.status == "behöver koll"]
        if uncertain:
            if ask_uncertain:
                lines = "\n".join(
                    f"• {p.audio.group_label}  ->  {p.match.book.display if p.match else '?'} "
                    f"({p.match.score:.2f})" for p in uncertain[:8])
                if not messagebox.askyesno(
                        "Osäkra matchningar",
                        f"Dessa {len(uncertain)} är osäkra och behöver din kontroll:\n\n{lines}\n\n"
                        "Organisera dem också? (Nej = bara de säkra)"):
                    uncertain = []
            else:
                uncertain = []
        todo = [p for p in certain + uncertain if not p.applied]
        if not todo:
            statuser = ", ".join(sorted({p.status for p in proposals})) or "inga"
            messagebox.showinfo(
                "Kan inte organisera",
                "De markerade raderna organiseras inte automatiskt "
                f"(status: {statuser}).\n\n'klar (historik)'-rader går att "
                "tvinga med högerklick -> 'Organisera vald bok'.")
            return
        eng = self.engine or self._engine()
        move = self._move.get()

        # Dublettskydd: samma titel+författare i outputmappen -> fråga (krav 19)
        from . import organize as _org

        self._recent_outputs = settings_mod.add_recent(self._recent_outputs, out)
        self._save_settings(silent=True)
        dups = [(p, _org.find_duplicate(p, out)) for p in todo]
        dups = [(p, d) for p, d in dups if d]
        if dups:
            rader = "\n".join(f"• {p.new_title}  ->  {d}" for p, d in dups[:8])
            if messagebox.askyesno(
                    "Finns redan i outputmappen",
                    f"Dessa böcker finns redan organiserade:\n\n{rader}\n\n"
                    "Organisera dem ändå? (Nej = hoppa över dem)"):
                pass
            else:
                skip = {id(p) for p, _ in dups}
                todo = [p for p in todo if id(p) not in skip]
                if not todo:
                    messagebox.showinfo("Inget att göra", "Alla valda fanns redan "
                                        "i outputmappen — inget organiserades.")
                    return

        def job():
            moved = copied = 0
            verb0 = "Flyttar" if move else "Kopierar"
            self.queue.put(("prog", (0, len(todo), verb0)))
            for n, p in enumerate(todo, 1):
                grp = getattr(p, "group_ref", None) or [p.audio]
                LOG.info("organiserar %r (move=%s, %d filer)", p.new_title,
                         move, len(grp))
                res = eng.organize(p, grp, out, move=move)
                LOG.info("organiserar klar för %r: %d åtgärder, %d fel",
                         p.new_title, len(res.actions), len(res.errors))
                self.queue.put(("prog", (n, len(todo),
                                        f"{verb0} — {p.new_title}")))
                if res.errors:
                    LOG.error("organiseringsfel %r: %s", p.new_title,
                              "; ".join(res.errors))
                    self.queue.put(("log", f"FEL {p.audio.group_label}: {'; '.join(res.errors)}"))
                else:
                    p.applied = True
                    moved += sum(1 for a in res.actions if a.kind == "move")
                    copied += sum(1 for a in res.actions if a.kind == "copy")
                    p.status = "klar (organiserad)"
                    self.queue.put(("rowupdate", p))
                    self.queue.put(("log", f"organiserad: {res.title_dir}"))
                    self.queue.put(("ocr", f"\nOrganiserad: {p.new_title}\n  -> {res.title_dir}"
                                            + (f"\n  faktablad: {res.md_path}" if res.md_path else "")))
            verb = "flyttade" if move else "kopierade"
            self.queue.put(("log", f"organisering klar ({verb}): "
                                    f"{moved} flyttade, {copied} kopierade filer"))
            if moved + copied:
                self.queue.put(("status",
                                f"Organiserat: {moved + copied} bok/böcker "
                                f"({moved} flyttade, {copied} kopierade) — "
                                f"taggar skrivna -> {out}"))
            else:
                self.queue.put(("status", "Organiseringen misslyckades — "
                                          "se flik 5 (Logg) för detaljer"))
        self._run_bg(job, "Organiserar")

    def _organize_selected(self) -> None:
        LOG.info("kommando: Organisera vald bok (inkl. historikrader)")
        # uttryckligt val = användaren bestämmer: även 'klar (historik)'-rader
        self._organize(self._selected_proposals(), ask_uncertain=True,
                       include_done=True)

    def _organize_confirm(self) -> None:
        LOG.info("knapp: Organisera gröna + OK-frågade")
        pros = [p for p in self.proposals if p.status in ("matchad", "behöver koll") and not p.skipped]
        self._organize(pros, ask_uncertain=True)

    # ------------------------------------------------------------- rekommendationer
    def _build_reco(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Hämta rekommendationer", command=self.start_recommend).pack(side="left")
        ttk.Label(top, text="Goodreads-förslag utifrån din historik: nästa del i serier, mer av författarna och liknande böcker.").pack(side="left", padx=8)
        self.reco_text = tk.Text(parent, wrap="word", background="#fbfbf7")
        self.reco_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def start_recommend(self) -> None:
        LOG.info("flik 4: startar rekommendationer")
        from collections import Counter

        eng = self.engine or self._engine()
        author_counts: Counter = Counter()
        series_owned: dict[str, str] = {}
        owned: list[str] = []
        for e in eng.history.entries():
            if e.get("author"):
                author_counts[e["author"].split(",")[0].strip()] += 1
            if e.get("series"):
                try:
                    if float(e.get("number") or 0) > float(series_owned.get(e["series"], "0")):
                        series_owned[e["series"]] = e.get("number") or "0"
                except ValueError:
                    pass
            if e.get("title"):
                owned.append(e["title"])
        for p in self.proposals:
            owned.append(p.new_title or p.audio.album)
            if p.new_artist:
                author_counts[p.new_artist.split(",")[0].strip()] += 1
            if p.new_series:
                series_owned.setdefault(p.new_series, p.new_series_number or "0")
        if not author_counts:
            messagebox.showinfo("Rekommendationer",
                                "Ingen historik ännu — skanna eller organisera några böcker först.")
            return
        self.reco_text.delete("1.0", "end")

        def job():
            recs = eng.recommend(owned, author_counts, series_owned)
            if not recs:
                self.queue.put(("reco", "Inga förslag just nu (Goodreads nås inte eller allt är redan ditt)."))
            for r in recs:
                b = r.book
                self.queue.put(("reco", f"{r.reason}\n  -> {b.display}\n     {b.url}\n"))
        self._run_bg(job, "Hämtar rekommendationer")

    # ------------------------------------------------------------- historik
    def _build_history(self, parent) -> None:
        """Krav 21: organiserade böcker arkiveras här och matchas inte på nytt."""
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Uppdatera", command=self._refresh_history).pack(side="left")
        ttk.Button(top, text="Öppna mapp", command=self._open_history_folder).pack(side="left", padx=4)
        ttk.Button(top, text="Ta bort post", command=self._remove_history_entry).pack(side="left", padx=4)
        ttk.Button(top, text="Rensa allt", command=self._clear_history).pack(side="left", padx=4)
        ttk.Button(top, text="🔄 Sök uppdateringar i output", command=self._start_refresh).pack(side="left", padx=12)
        ttk.Button(top, text="Uppdatera valda", command=self._apply_refresh).pack(side="left", padx=4)
        ttk.Label(top, text="Organiserade böcker arkiveras här — de matchas aldrig om.").pack(side="left", padx=8)
        cols = ("when", "title", "author", "series", "number", "output")
        self.htree = ttk.Treeview(parent, columns=cols, show="headings", height=14)
        for key, head, w in (("when", "Datum", 130), ("title", "Titel", 240),
                             ("author", "Författare", 160), ("series", "Serie", 140),
                             ("number", "Del", 40), ("output", "Outputmapp", 320)):
            self.htree.heading(key, text=head)
            self.htree.column(key, width=w)
        self.htree.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._refresh_history()

    def _refresh_history(self) -> None:
        LOG.debug("historikfliken uppdateras")
        from .history import History

        for iid in self.htree.get_children():
            self.htree.delete(iid)
        for e in History().entries():
            self.htree.insert("", "end", values=(
                (e.get("ts") or "")[:16].replace("T", " "),
                e.get("title", ""), e.get("author", ""),
                e.get("series", ""), e.get("number", ""), e.get("output", "")))

    def _history_selected(self) -> list[dict]:
        from .history import History

        idx = [self.htree.index(i) for i in self.htree.selection()]
        ents = History().entries()
        return [ents[i] for i in idx if i < len(ents)]

    def _open_history_folder(self) -> None:
        LOG.info("öppnar historikmappen")
        sel = self._history_selected()
        if not sel or not sel[0].get("output"):
            return
        folder = os.path.dirname(sel[0]["output"]) if os.path.isfile(sel[0]["output"]) else sel[0]["output"]
        if sys.platform == "darwin":
            os.system(f'open "{folder}"')
        elif os.name == "nt":
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            os.system(f'xdg-open "{folder}" >/dev/null 2>&1 &')

    def _remove_history_entry(self) -> None:
        LOG.info("tar bort markerad historikpost")
        sel = self._history_selected()
        if not sel:
            messagebox.showinfo("Historik", "Markera en post först.")
            return
        if not messagebox.askyesno("Historik", f"Ta bort '{sel[0].get('title')}' ur "
                                   "historiken? Boken kan då matchas på nytt."):
            return
        from .history import History

        h = History()
        for e in sel:
            h.remove(e.get("key", ""))
        self._refresh_history()

    def _clear_history(self) -> None:
        LOG.info("rensar hela historiken")
        if not messagebox.askyesno("Historik", "Rensa HELA historiken? Alla böcker "
                                   "kan då matchas på nytt."):
            return
        from .history import History

        History().clear()
        self._refresh_history()

    # ---------------------------------------------- fråga vid historikträff (krav 21)
    def _ask_history(self, proposal, ent) -> bool:
        """'Tidigare importerad — hoppa över?' Körs i skanntråden; dialogen
        visas i huvudtråden via kön och tråden väntar på svaret."""
        import threading

        ev = threading.Event()
        answer = {"skip": True}   # ingen svarar (t.ex. fönster stängt) -> hoppa över
        title = proposal.new_title or proposal.audio.title or "?"
        author = proposal.new_artist or proposal.audio.artist or "?"
        when = (ent.get("finished_at") or "").strip()
        self.queue.put(("askhist", (title, author, when, ev, answer)))
        ev.wait(timeout=600)
        return bool(answer["skip"])

    # ------------------------------------------------------------- logg
    def _build_log(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Uppdatera", command=self._reload_log).pack(side="left")
        ttk.Button(top, text="Öppna loggfilen", command=self._open_log).pack(side="left", padx=4)
        from .logging_setup import DEFAULT_LOG as _dl
        ttk.Label(top, text=f"Allt som händer loggas till {_dl}").pack(side="left", padx=8)
        self.log_text = tk.Text(parent, wrap="none", background="#101010", foreground="#c8c8c8")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.root.after(500, self._tail_log)
        self.root.after(900, lambda: self._check_deps(False))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_menubar()
        self._load_settings()
        for var in (self.folder, self._output):
            var.trace_add("write", lambda *a: self._save_settings(silent=True))

    def _open_log(self) -> None:
        LOG.info("öppnar loggfilen")
        from .logging_setup import DEFAULT_LOG

        path = DEFAULT_LOG
        if sys.platform == "darwin":
            os.system(f'open "{path}"')
        elif os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')

    def _reload_log(self) -> None:
        LOG.info("logg: uppdatera")
        self._log_pos = 0
        self._recent_imports: list[str] = []
        self._recent_outputs: list[str] = []
        self.log_text.delete("1.0", "end")
        self._tail_log()

    def _tail_log(self) -> None:
        LOG.debug("logg: tail")
        from .logging_setup import DEFAULT_LOG

        try:
            with open(DEFAULT_LOG, encoding="utf-8", errors="replace") as fh:
                fh.seek(self._log_pos)
                chunk = fh.read()
                self._log_pos = fh.tell()
            if chunk:
                self.log_text.insert("end", chunk)
                self.log_text.see("end")
        except OSError:
            pass
        self.root.after(2500, self._tail_log)

    def set_status(self, text: str) -> None:
        self.status.config(text=text)

    def _pick_folder(self) -> None:
        LOG.info("dialog: välj importmapp")
        d = filedialog.askdirectory(title="Välj mapp med ljudböcker")
        if d:
            self.folder.set(d)

    def _pick_audio(self, var) -> None:
        LOG.info("dialog: välj ljudfil")
        f = filedialog.askopenfilename(
            title="Välj ljudfil",
            filetypes=[("Ljud", "*.mp3 *.m4b *.m4a *.flac *.ogg *.opus"), ("Alla", "*.*")],
        )
        if f:
            var.set(f)

    def _pick_image(self) -> None:
        LOG.info("dialog: välj skärmbild")
        f = filedialog.askopenfilename(title="Välj skärmbild", filetypes=[("Bild", "*.png *.jpg *.jpeg *.webp")])
        if f:
            self.ocr_path.config(text=os.path.basename(f))
            self._image_path = f

    def _busy_on(self, label: str) -> None:
        self._busy = True
        self.set_status(f"{label} …")
        for b in (self.btn_scan, self.btn_apply, self.btn_apply_all):
            b.config(state="disabled")

    def _busy_off(self) -> None:
        self._busy = False
        for b in (self.btn_scan,):
            b.config(state="normal")
        if self.rows:
            self.btn_csv.config(state="normal")
            self.btn_apply.config(state="normal")
            self.btn_apply_all.config(state="normal")

    # ------------------------------------------------------------- trådar

    # ------------------------------------------------------------- skanna
    def start_scan(self) -> None:
        root = self.folder.get().strip()
        if not root or not os.path.exists(root):
            messagebox.showwarning("Mapp", "Välj en mapp som finns.")
            return
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.rows, self.proposals = [], []
        self._iid_of = {}
        self.detail.delete("1.0", "end")
        eng = self._engine()
        LOG.info("SKANNING startad: %r", root)

        self._recent_imports = settings_mod.add_recent(self._recent_imports, root)
        self._save_settings(silent=True)

        def job():
            files = eng.scan(root, recursive=True)
            self.queue.put(("log", f"{len(files)} ljudfiler hittade"))
            props = []
            groups = eng.groups(files)
            self.queue.put(("prog", (0, len(groups), "Matchar")))
            for i, grp in enumerate(groups, 1):
                p, _ = eng.match_group(grp)
                p.group_ref = grp  # type: ignore[attr-defined]
                props.append(p)
                self.queue.put(("row", p))
                self.queue.put(("prog", (i, len(groups),
                                        f"Matchar — {p.audio.group_label}")))
            # krav 23: flera versioner av samma bok -> behåll den bästa
            from .engine import choose_best_versions

            changed = choose_best_versions(props)
            if changed:
                self.queue.put(("log", f"{len(changed)} sämre dubblettversioner "
                                        "markerade (bästa versionen behålls)"))
            for p in changed:
                self.queue.put(("rowupdate", p))
            LOG.info("SKANNING klar: %d ljudfiler, %d grupper", len(files),
                     len(groups))
        self._run_bg(job, "Skannar")

    def _add_row(self, p: Proposal) -> None:
        row = presenter.proposal_row(p)
        self.proposals.append(p)
        self.rows.append(row)
        iid = self.tree.insert("", "end", values=presenter.row_values(row), tags=(row["tag"],))
        self._iid_of[id(p)] = iid
        self.set_status(f"{presenter.summary_text(self.rows)}")

    def _merge_selected(self, proposals: list | None = None) -> None:
        LOG.info("kommando: Slå ihop markerade delar")
        """Slå ihop markerade rader till en bok (krav 24, manuell del-merge)."""
        sel = proposals if proposals is not None else self._selected_proposals()
        if len(sel) < 2:
            messagebox.showinfo("Slå ihop",
                                "Markera minst två rader som hör till samma bok.")
            return
        base = sel[0]
        for other in sel[1:]:
            base.paths = (getattr(base, "paths", None) or [base.audio.path]) + \
                         (getattr(other, "paths", None) or [other.audio.path])
            base.group_ref = (getattr(base, "group_ref", None) or [base.audio]) + \
                             (getattr(other, "group_ref", None) or [other.audio])
            base.total_size_mb = round(getattr(base, "total_size_mb", 0.0) +
                                       getattr(other, "total_size_mb", 0.0), 1)
        from . import library as _lib

        base.group_ref.sort(key=_lib._track_sort)
        base.group_size = len(base.group_ref)
        base.note = "manuellt sammanslagen" + (f" | {base.note}" if base.note else "")
        for other in sel[1:]:
            iid = self._iid_of.pop(id(other), None)
            if iid and self.tree.exists(iid):
                self.tree.delete(iid)
            for lst in (self.proposals, self.rows):
                for x in [x for x in lst if x is other]:
                    lst.remove(x)
        self._update_row(base)
        self.set_status(f"{len(sel)} delar sammanslagna till en bok.")

    def _update_row(self, p: Proposal) -> None:
        """Uppdatera en rad på plats (t.ex. efter 'bästa version'-valet)."""
        iid = self._iid_of.get(id(p))
        if not iid or not self.tree.exists(iid):
            return
        try:
            idx = self.proposals.index(p)
            self.rows[idx] = presenter.proposal_row(p)
        except ValueError:
            pass
        row = presenter.proposal_row(p)
        self.tree.item(iid, values=presenter.row_values(row), tags=(row["tag"],))

    @staticmethod
    def _sort_key(p: Proposal) -> tuple:
        """Sorteringsnyckel: författare, serie (i delordning), sedan titel.

        Serieböcker grupperas per serie med del 1 först; böcker utan serie
        hamnar efter, sorterade på titel.
        """
        ser = (p.new_series or "").strip().lower()
        try:
            num = float(p.new_series_number or "")
        except (TypeError, ValueError):
            num = float("inf")
        return ((p.new_artist or "").lower(), ser == "", ser, num,
                (p.new_title or p.audio.album or "").lower())

    def _sort_rows(self) -> None:
        """Sortera om tabellen (träd + underliggande listor hålls i synk)."""
        if len(self.rows) < 2:
            return
        items = list(zip(self.tree.get_children(), self.proposals, self.rows))
        items.sort(key=lambda t: self._sort_key(t[1]))
        for pos, (iid, _p, _r) in enumerate(items):
            self.tree.move(iid, "", pos)
        self.proposals = [t[1] for t in items]
        self.rows = [t[2] for t in items]

    # ------------------------------------------------------------- högerklick
    def _row_menu(self, event) -> None:
        LOG.debug("högerklicksmeny öppnad")
        """Högerklick på en rad: manuell Goodreads-länk m.m. (krav: blockerad
        sökning ska kunna lösas manuellt med en länk)."""
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Organisera vald bok → outputmappen",
                         command=self._organize_selected)
        menu.add_command(label="Skriv taggar för vald rad (på plats)",
                         command=self._apply_selected)
        menu.add_separator()
        menu.add_command(label="Slå ihop markerade rader (samma bok)",
                         command=self._merge_selected)
        menu.add_command(label="Klistra in Goodreads-länk för vald rad …",
                         command=self._manual_link)
        menu.add_separator()
        menu.add_command(label="Öppna i filhanterare", command=self._reveal)
        menu.add_command(label="Kopiera titel", command=self._copy_title)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _manual_link(self) -> None:
        LOG.info("högerklick: Klistra in Goodreads-länk")
        from tkinter import simpledialog

        sel = self._selected_proposals()
        if not sel:
            messagebox.showinfo("Högerklick", "Markera en rad först.")
            return
        url = simpledialog.askstring(
            "Goodreads-länk",
            "Klistra in en Goodreads-länk för boken (används i stället för "
            "sökningen — fungerar även när sökningen är blockerad):")
        if not url or not url.strip():
            return
        eng = self.engine or self._engine()

        def job():
            for old in sel:
                p2, _m = eng.from_goodreads_url(url.strip(), audio=old.audio)
                # Behåll filgruppens sökvägar — from_goodreads_url skapar tom paths, men organisering kräver filerna
                p2.paths = getattr(old, "paths", [old.audio.path])  # type: ignore[attr-defined]
                p2.group_size = getattr(old, "group_size", len(p2.paths))  # type: ignore[attr-defined]
                p2.total_size_mb = getattr(old, "total_size_mb", 0)  # type: ignore[attr-defined]
                p2.group_ref = getattr(old, "group_ref", getattr(old, "group", None))
                # Markera tydligt att Goodreads-länken ersätter reservkälla (Storytel/BookBeat/Open Library)
                prev_src = getattr(old, "source", "") or "reservkälla"
                p2.source = "goodreads:länk (ersätter " + prev_src + ")"
                if getattr(p2, "note", ""):
                    if "manuell" not in p2.note.lower():
                        p2.note = p2.note + " | manuell Goodreads-länk"
                else:
                    p2.note = f"manuell Goodreads-länk — ersätter {prev_src}"
                # Säkerställ att status blir matchad oavsett tidigare poäng från reservkälla
                p2.status = "matchad"
                # Behåll även eventuell serie/del från bok-objektet (from_goodreads_url sätter redan via _fill)
                i = self.proposals.index(old)
                self.proposals[i] = p2
                row = presenter.proposal_row(p2)
                self.rows[i] = row
                iid = self.tree.get_children()[i]
                self.tree.item(iid, values=presenter.row_values(row),
                               tags=(row["tag"],))
                self.queue.put(("log", f"manuell länk: {p2.audio.group_label} -> "
                                       f"{p2.new_title} [{p2.status}] — ersatte {prev_src}"))
                # uppdatera detaljvyn direkt om raden fortfarande är markerad
                try:
                    self._show_detail()
                except Exception:
                    pass
        self._run_bg(job, "Hämtar från länk")

    def _copy_title(self) -> None:
        LOG.info("högerklick: Kopiera titel (originalnamn)")
        sel = self._selected_proposals()
        if sel:
            p0 = sel[0]
            # originalnamn = det som boken hette på disk innan Goodreads-matchning
            # prioritera gruppetikett/mappnamn, inte den nya Goodreads-titeln
            orig = (getattr(p0.audio, "group_label", "") or p0.audio.title or p0.audio.album or "").strip()
            # "Unknown Album/Track 01" är skräp från taggar — ta mappnamnet istället
            if not orig or orig.lower() in ("unknown album", "unknown", "track 1", "track 01"):
                try:
                    import os as _os
                    orig = _os.path.basename(_os.path.dirname(p0.audio.path)) or orig
                except Exception:
                    pass
            if not orig:
                # sista fallback — källsökvägens filnamn utan ändelse
                try:
                    import os as _os
                    orig = _os.path.splitext(_os.path.basename(p0.audio.path))[0]
                except Exception:
                    orig = p0.new_title or ""
            self.root.clipboard_clear()
            self.root.clipboard_append(orig)
            LOG.info("kopierade originaltitel %r (ny titel var %r)", orig, p0.new_title)
            self.set_status(f"Kopierade: {orig}")

    def _selected_proposals(self) -> list[Proposal]:
        idx = [self.tree.index(i) for i in self.tree.selection()]
        return [self.proposals[i] for i in idx if i < len(self.proposals)]

    def _start_refresh(self) -> None:
        """Krav 34: skanna outputmappen och jämför med Goodreads/historik."""
        import os
        out = self._output.get().strip()
        if not out or not os.path.isdir(out):
            import tkinter.messagebox as messagebox
            messagebox.showwarning("Outputmapp", f"Välj en befintlig outputmapp först: {out or '(tom)'}")
            return
        LOG.info("refresh start: %s", out)
        self.set_status(f"Söker uppdateringar i {out} …")
        self._busy_on("Söker uppdateringar …")
        self.prog.config(value=0)
        self._refresh_proposals = []  # type: ignore[attr-defined]
        def job():
            try:
                eng = self._engine()
                def on_prop(pr):
                    try:
                        self.queue.put(("refresh_one", pr))
                    except Exception:
                        pass
                proposals = eng.check_output_for_updates(out, on_proposal=on_prop)
                self.queue.put(("refresh_done", proposals))
            except Exception as exc:
                LOG.exception("refresh krasch: %s", exc)
                self.queue.put(("error", str(exc)))
                try:
                    self.queue.put(("refresh_done", []))
                except Exception:
                    pass
        self._run_bg(job, "Söker uppdateringar")

    def _apply_refresh(self) -> None:
        """Krav 34: skriv uppdaterade taggar för valda Historik-rader."""
        import os
        import tkinter.messagebox as messagebox
        from .models import AudioFile
        sel_hist = self._history_selected()
        if not sel_hist:
            messagebox.showinfo("Historik", "Markera en eller flera rader i Historik-tabellen först.")
            return
        proposals = getattr(self, "_refresh_proposals", None) or []
        if not proposals:
            messagebox.showwarning("Inga förslag", "Kör först 'Sök uppdateringar i output' så att listan fylls.")
            return
        wanted = []
        for h in sel_hist:
            ht = (h.get("title") or "").strip().lower()
            ha = (h.get("author") or "").strip().lower().split(",")[0].split()[0] if h.get("author") else ""
            for pr in proposals:
                pt = (pr.new_title or "").strip().lower()
                pa = (pr.new_artist or "").strip().lower()
                if pt == ht and (not ha or ha in pa):
                    wanted.append(pr)
                    break
        if not wanted:
            wanted = [pr for pr in proposals if getattr(pr, "status", "") == "behöver uppdateras"]
            if not wanted:
                messagebox.showinfo("Inget att uppdatera", "Inga av de skannade böckerna behöver uppdateras.")
                return
        if not messagebox.askyesno("Uppdatera", f"Uppdatera {len(wanted)} bok/böcker i outputmappen?\n\n" + "\n".join(f"• {pr.new_title} — {pr.note or pr.status}" for pr in wanted[:6])):
            return
        LOG.info("refresh apply: %d förslag", len(wanted))
        self._busy_on(f"Uppdaterar {len(wanted)} …")
        self.prog.config(maximum=len(wanted), value=0)
        def job():
            ok = fail = 0
            eng = self._engine()
            for idx, pr in enumerate(wanted, 1):
                try:
                    self.queue.put(("prog", (idx, len(wanted), f"Uppdaterar {pr.new_title}")))
                except Exception:
                    pass
                paths = getattr(pr, "paths", None) or [pr.audio.path]
                group = []
                for pth in paths:
                    try:
                        group.append(AudioFile(path=pth, title=pr.new_title, artist=pr.new_artist))
                    except Exception:
                        group.append(AudioFile(path=pth))
                try:
                    res = eng.apply_update(pr, group)
                    if all(getattr(r, "ok", False) for r in res):
                        ok += 1
                    else:
                        fail += 1
                except Exception as exc:
                    LOG.warning("apply_update %s: %s", pr.new_title, exc)
                    fail += 1
            self.queue.put(("refresh_applied", (ok, fail)))
        self._run_bg(job, "Uppdaterar")

    def _open_paypal(self) -> None:
        LOG.info("hjälp: öppna PayPal donation")
        try:
            webbrowser.open(PAYPAL_URL)
            self.set_status("Öppnar PayPal — tack för stödet! \u2764\ufe0f")
        except Exception as exc:
            LOG.warning("kunde inte öppna PayPal %s: %s", PAYPAL_URL, exc)
            import tkinter.messagebox as messagebox
            messagebox.showinfo("PayPal", f"Öppna manuellt: {PAYPAL_URL}")

    def _open_kofi(self) -> None:
        LOG.info("hjälp: öppna Ko-fi donation")
        try:
            webbrowser.open(KOFI_URL)
            self.set_status("Öppnar Ko-fi — tack för stödet! \u2615")
        except Exception as exc:
            LOG.warning("kunde inte öppna Ko-fi %s: %s", KOFI_URL, exc)
            import tkinter.messagebox as messagebox
            messagebox.showinfo("Ko-fi", f"Öppna manuellt: {KOFI_URL}")

    def _show_about(self) -> None:
        t = STRINGS.get(self._lang.get(), STRINGS["sv"])
        import tkinter.messagebox as messagebox
        messagebox.showinfo(t["about"], t["about_text"])

    def _set_lang(self, lang: str) -> None:
        try:
            self._lang.set(lang)
            self._save_settings(silent=True)
            self._apply_lang()
            t = STRINGS.get(lang, STRINGS["sv"])
            self.set_status(t["lang_changed"].format(lang=lang))
            LOG.info("språk ändrat till %s", lang)
        except Exception as exc:
            LOG.warning("kunde inte byta språk %s: %s", lang, exc)

    def _apply_lang(self) -> None:
        try:
            self._build_menubar()
        except Exception as exc:
            LOG.debug("kunde inte tillämpa språk: %s", exc)

    def _show_detail(self, _event=None) -> None:
        LOG.debug("detaljvy uppdaterad")
        sel = self._selected_proposals()
        self.detail.delete("1.0", "end")
        if not sel:
            try:
                self._update_timeline(None)
            except Exception:
                pass
            return
        p = sel[0]
        head = presenter.changes_text(p)
        extra = []
        if p.match and p.match.book.url:
            extra.append(f"Källa: {p.match.book.url}")
        if p.note:
            extra.append(f"Not: {p.note}")
        self.detail.insert("end", head + ("\n" + "\n".join(extra) if extra else ""))
        try:
            self._update_timeline(p)
        except Exception as exc:
            LOG.debug("timeline: %s", exc)

    def _update_timeline(self, proposal) -> None:
        """5) Serie-tidslinje — visuell horisontell prick-rad för serien.

        Grön = ägd (finns i historiken), blå = vald, grå = saknas.
        Klick på prick visar info; hover visar tooltip via statusraden.
        """
        try:
            canvas = getattr(self, "timeline_canvas", None)
            hint = getattr(self, "timeline_hint", None)
            frame = getattr(self, "timeline_frame", None)
            if canvas is None or frame is None:
                return
            canvas.delete("all")
            if not proposal or not getattr(proposal, "new_series", "") or not proposal.new_series.strip():
                if hint is not None:
                    hint.config(text="Välj en bok med serie för att se tidslinjen.")
                    hint.pack()
                canvas.pack_forget()
                if frame is not None:
                    frame.config(text="Serie-tidslinje")
                return
            series = proposal.new_series.strip()
            cur_raw = (getattr(proposal, "new_series_number", "") or "").strip()
            cur = None
            try:
                cur = float(cur_raw) if cur_raw else None
            except Exception:
                cur = None
            # ägda delar ur historiken (History direkt — engine kan vara None före skanning)
            try:
                from .history import History
                hist = History().entries()
            except Exception:
                hist = []
            owned_hist: set[float] = set()
            for e in hist:
                try:
                    se = (e.get("series") or "").strip()
                    if se.lower() == series.lower():
                        nraw = str(e.get("number") or "").strip()
                        if nraw:
                            owned_hist.add(float(nraw))
                except Exception:
                    continue
            # bygg nummerlista att visa
            nums: list[float] = []
            if cur is not None:
                # fönster runt vald del +-3 (eller +-2.5 om .5-serie)
                has_half = any(abs(n - round(n) - 0.5) < 0.01 for n in owned_hist) or (not cur.is_integer() if cur is not None else False)
                start = int(cur) - 3 if cur.is_integer() else int(cur) - 2
                if start < 1:
                    start = 1 if not has_half else 0.5
                    if start < 0.5:
                        start = 0.5
                # täck även ägda ytterligheter
                if owned_hist:
                    mn = min(owned_hist)
                    mx = max(owned_hist)
                    if mn < start:
                        start = int(mn) if float(mn).is_integer() else float(mn)
                    end = max(int(cur + 3), int(mx) + 1)
                else:
                    end = int(cur + 3)
                if has_half:
                    n = float(start)
                    # normalisera start till .0 eller .5
                    if abs(n - round(n) - 0.5) > 0.01 and abs(n - round(n)) > 0.01:
                        n = round(n)
                    while n <= end + 0.01:
                        if n >= 0.5:
                            nums.append(round(n, 1))
                        n += 0.5
                else:
                    nums = [float(x) for x in range(int(start), int(end) + 1)]
                # max 9 prickar centrerat kring cur
                if len(nums) > 9:
                    try:
                        idx = min(range(len(nums)), key=lambda i: abs(nums[i] - cur))
                    except Exception:
                        idx = len(nums)//2
                    lo = max(0, idx - 4)
                    hi = lo + 9
                    if hi > len(nums):
                        hi = len(nums)
                        lo = hi - 9
                    nums = nums[lo:hi]
            else:
                # ingen del — visa ägda sorterat
                nums = sorted(owned_hist)[:9]
                if not nums:
                    if hint is not None:
                        hint.config(text=f"Serie: {series} — ingen delinfo. {len(owned_hist)} ägd(a).")
                        hint.pack()
                    canvas.pack_forget()
                    frame.config(text=f"Serie-tidslinje — {series}")
                    return
            # visa canvas
            if hint is not None:
                hint.pack_forget()
            canvas.pack(fill="x", expand=True)
            if frame is not None:
                frame.config(text=f"Serie-tidslinje — {series}")
            canvas.delete("all")
            # mått
            canvas.update_idletasks()
            w = canvas.winfo_width() or 500
            if w < 200:
                w = 500
            h = 34
            n = len(nums)
            # bakgrundslinje
            y = 16
            canvas.create_line(20, y, w-20, y, fill="#d0d0d0", width=2)
            for i, val in enumerate(nums):
                x = 20 + i * ((w-40) / max(1, n-1)) if n > 1 else w // 2
                is_cur = cur is not None and abs(val - cur) < 0.01
                is_owned = val in owned_hist
                # färg
                if is_cur:
                    fill = "#1a56db"  # blå — vald
                    outline = "#0f3a9a"
                    r = 11
                elif is_owned:
                    fill = "#1b7f3b"  # grön — ägd
                    outline = "#145a2b"
                    r = 9
                else:
                    fill = "#cccccc"  # grå — saknas
                    outline = "#999999"
                    r = 8
                # prick
                canvas.create_oval(x-r, y-r, x+r, y+r, fill=fill, outline=outline, width=2 if is_cur else 1)
                # nummer under
                label = f"{int(val)}" if float(val).is_integer() else f"{val:g}"
                if is_cur:
                    label = f"[{label}]"
                canvas.create_text(x, y+16, text=label, font=("TkDefaultFont", 8, "bold" if is_cur else "normal"), fill="#222222")
                # tooltip/status vid hover — bind area
                def _enter(event, v=val, owned=is_owned, curf=is_cur):
                    txt = f"Del {v:g}"
                    if curf:
                        txt += " — vald"
                    txt += " (ägd)" if owned or curf else " (saknas)"
                    self.set_status(txt)
                def _leave(event):
                    self.set_status(f"Serie {series} — {len(owned_hist)} ägd(a) av {len(nums)} visade")
                # skapa osynlig träffyta
                oid = canvas.create_oval(x-r-4, y-r-4, x+r+4, y+r+4, outline="", fill="", tags=("dot",))
                canvas.tag_bind(oid, "<Enter>", _enter)
                canvas.tag_bind(oid, "<Leave>", _leave)
                canvas.tag_bind(oid, "<Button-1>", lambda e, v=val: messagebox.showinfo("Serie-del", f"{series} — del {v:g}\n\nGrön = ägd (finns i historiken)\nBlå = vald rad\nGrå = saknas"))
            # summering i canvas högra kant
            canvas.create_text(w-6, 4, text=f"{len(owned_hist)} ägd(a)", anchor="ne", font=("TkDefaultFont", 7), fill="#666666")
        except Exception as exc:
            LOG.debug("timeline fel: %s", exc)

    def _write(self, proposals: list[Proposal]) -> None:
        if not proposals:
            messagebox.showinfo("Inget valt", "Markera en eller flera rader först.")
            return
        eng = self.engine or self._engine()
        n = sum(len(getattr(p, "paths", None) or [p.audio.path]) for p in proposals)
        if not messagebox.askyesno("Skriv taggar",
                                   f"Uppdatera {n} fil(er)?\n\n"
                                   + ("\n\n".join(presenter.changes_text(p) for p in proposals[:3]))):
            return
        LOG.info("skriver taggar för %d rader (%d filer)", len(proposals), n)

        def job():
            ok = fail = 0
            for p in proposals:
                for res in eng.apply(p, dry_run=False):
                    if res.ok:
                        ok += 1
                        self.queue.put(("log", f"skriven: {os.path.basename(res.path)}"))
                    else:
                        fail += 1
                        self.queue.put(("log", f"FEL {os.path.basename(res.path)}: {res.error}"))
            self.queue.put(("ocr", f"\n{ok} filer uppdaterade, {fail} fel."))
        self._run_bg(job, "Skriver taggar")

    def _apply_selected(self) -> None:
        LOG.info("kommando: Skriv taggar för valda rader")
        self._write(self._selected_proposals())

    def _apply_green(self) -> None:
        LOG.info("knapp: Skriv alla gröna rader")
        self._write([p for p in self.proposals if p.status == "matchad"])

    def _pick_candidate(self) -> None:
        LOG.info("knapp: Välj bra träff manuellt")
        sel = self._selected_proposals()
        if not sel:
            messagebox.showinfo("Inget valt", "Markera en rad först.")
            return
        p = sel[0]
        win = tk.Toplevel(self.root)
        win.title(f"Välj träff för {p.audio.group_label}")
        win.geometry("860x420")
        cols = ("score", "title", "authors", "series", "num", "year", "url")
        heads = ("Poäng", "Titel", "Författare", "Serie", "Del", "År", "Goodreads")
        widths = (55, 280, 150, 130, 40, 50, 300)
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for c, h, w in zip(cols, heads, widths):
            tv.heading(c, text=h)
            tv.column(c, width=w, anchor="w")
        tv.pack(fill="both", expand=True, padx=6, pady=6)
        matches = getattr(p, "candidates", None) or ([p.match] if p.match else [])
        if not matches:
            messagebox.showinfo("Inga träffar", "Den raden har inga alternativ att välja bland.")
            return
        for m in matches:
            b = m.book
            tv.insert("", "end", values=(f"{m.score:.2f}", b.title, ", ".join(b.authors),
                                         b.series, b.series_number, b.year, b.url))

        def choose():
            s = tv.selection()
            if not s:
                return
            m = matches[tv.index(s[0])]
            p.match = m
            eng = self.engine or self._engine()
            eng._fill(p, m, [p.audio], m.book.series_number)
            p.status = "matchad"
            p.note = "manuellt vald träff"
            idx = self.proposals.index(p)
            self.rows[idx] = presenter.proposal_row(p)
            self.tree.item(self.tree.get_children()[idx],
                           values=presenter.row_values(self.rows[idx]), tags=("ok",))
            win.destroy()

        ttk.Button(win, text="Använd vald träff", command=choose).pack(pady=6)

    def _reveal(self) -> None:
        LOG.info("högerklick: Öppna i filhanterare (markera fil)")
        sel = self._selected_proposals()
        # även Historik-fliken kan ha markering — fallback till historikens output
        if not sel:
            try:
                hist_sel = self._history_selected()
                if hist_sel:
                    # öppna historikens output-mapp och markera första filen om den finns
                    out = (hist_sel[0].get("output") or "").strip()
                    files = hist_sel[0].get("files") or []
                    pth = files[0] if files and files[0] else out
                    if pth and os.path.exists(pth):
                        if os.path.isfile(pth):
                            folder = os.path.dirname(os.path.abspath(pth))
                            if sys.platform == "darwin":
                                os.system(f'open -R "{pth}"')
                            elif os.name == "nt":
                                # Windows: markera filen i Utforskaren
                                os.system(f'explorer /select,"{pth}"')
                            else:
                                os.system(f'xdg-open "{folder}" >/dev/null 2>&1 &')
                            LOG.info("öppnade %r (historik)", pth)
                            return
                    if out and os.path.isdir(out):
                        if sys.platform == "darwin":
                            os.system(f'open "{out}"')
                        elif os.name == "nt":
                            os.startfile(out)  # type: ignore[attr-defined]
                        else:
                            os.system(f'xdg-open "{out}" >/dev/null 2>&1 &')
                        return
            except Exception:
                pass
            return
        # Skanna-flikens val — ta första filen i gruppen
        raw_path = getattr(sel[0], "paths", [sel[0].audio.path])[0] if getattr(sel[0], "paths", None) else sel[0].audio.path
        path = os.path.abspath(raw_path) if raw_path else ""
        # om filen inte finns längre (redan flyttad) — försök öppna mappen den låg i
        if path and os.path.isfile(path):
            folder = os.path.dirname(path)
            if sys.platform == "darwin":
                os.system(f'open -R "{path}"')
            elif os.name == "nt":
                os.system(f'explorer /select,"{path}"')
            else:
                # Linux: xdg-open kan inte markera fil, öppna mappen
                # försök även dbus för Nautilus/Dolphin
                if os.path.isdir(folder):
                    os.system(f'xdg-open "{folder}" >/dev/null 2>&1 &')
                else:
                    os.system(f'xdg-open "{os.path.dirname(folder)}" >/dev/null 2>&1 &')
            LOG.info("öppnade filhanteraren för %r", path)
            self.set_status(f"Öppnade: {path}")
            return
        # path är mapp eller saknas — öppna själva mappen
        folder = path if path and os.path.isdir(path) else (os.path.dirname(path) if path else "")
        if folder and os.path.isdir(folder):
            if sys.platform == "darwin":
                os.system(f'open "{folder}"')
            elif os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            else:
                os.system(f'xdg-open "{folder}" >/dev/null 2>&1 &')
            LOG.info("öppnade mappen %r", folder)
            self.set_status(f"Öppnade mappen: {folder}")
            return
        # sista fallback — försök öppna filens föräldermapp även om filen är borta
        try:
            fallback = os.path.dirname(path) if path else ""
            if fallback and os.path.isdir(fallback):
                if sys.platform == "darwin":
                    os.system(f'open "{fallback}"')
                elif os.name == "nt":
                    os.startfile(fallback)  # type: ignore[attr-defined]
                else:
                    os.system(f'xdg-open "{fallback}" >/dev/null 2>&1 &')
                return
        except Exception:
            pass
        LOG.warning("kan inte öppna i filhanterare — sökvägen saknas: %r", path)

    def _export_csv(self) -> None:
        LOG.info("exporterar CSV")
        import csv

        f = filedialog.asksaveasfilename(defaultextension=".csv",
                                         filetypes=[("CSV", "*.csv")], title="Spara CSV")
        if not f:
            return
        with open(f, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["fil", "status", "poäng", "titel", "författare", "serie", "del", "år", "album", "källa", "url"])
            for p, row in zip(self.proposals, self.rows):
                for path in (getattr(p, "paths", None) or [p.audio.path]):
                    w.writerow([path, p.status, row["score"], p.new_title, p.new_artist,
                                p.new_series, p.new_series_number, p.new_year, p.new_album,
                                p.source, row["url"]])
        self.set_status(f"CSV sparad: {f}")

    # ------------------------------------------------------------- manuellt
    def start_manual(self) -> None:
        LOG.info("flik 2: matcha enskild titel/länk")
        eng = self._engine()
        title = self.m_title.get().strip()
        author = self.m_author.get().strip()
        url = self.m_url.get().strip()
        if not title and not url:
            messagebox.showwarning("Saknas", "Fyll i titel eller Goodreads-länk.")
            return

        def job():
            if url:
                p, ms = eng.from_goodreads_url(url)
            else:
                p, ms = eng.match_text(title, author)
            p.candidates = ms  # type: ignore[attr-defined]
            self.queue.put(("manual", (p, ms)))
        self._run_bg(job, "Söker")

    def _show_manual(self, payload) -> None:
        p, matches = payload
        for iid in self.mtree.get_children():
            self.mtree.delete(iid)
        for m in matches[:15]:
            b = m.book
            self.mtree.insert("", "end", values=(f"{m.score:.2f}", b.title, ", ".join(b.authors),
                                                 b.series, b.series_number, b.year, b.url))
        self.manual_results = matches
        if matches:
            first = self.mtree.get_children()[0]
            self.mtree.selection_set(first)
            self.mtree.focus(first)
        self.set_status(f"{p.status} · {p.note or 'klart'} · källa: {p.source or 'goodreads'}")

    def _apply_manual(self) -> None:
        sel = self.mtree.selection()
        target = self.m_target.get().strip()
        if not sel or not self.manual_results:
            messagebox.showinfo("Inget valt", "Sök först och markera en träff.")
            return
        if not target or not os.path.exists(target):
            messagebox.showwarning("Fil", "Välj en ljudfil att skriva till.")
            return
        m = self.manual_results[self.mtree.index(sel[0])]
        eng = self.engine or self._engine()
        from .models import AudioFile

        p = Proposal(audio=AudioFile(path=target, album=os.path.splitext(os.path.basename(target))[0]))
        p.paths = [target]  # type: ignore[attr-defined]
        eng._fill(p, m, [p.audio], m.book.series_number)
        p.match = m
        self._write([p])

    # ------------------------------------------------------------- skärmbild
    def start_ocr_image(self) -> None:
        LOG.info("flik 3: OCR från skärmbild")
        path = getattr(self, "_image_path", "")
        if not path:
            messagebox.showwarning("Bild", "Välj en skärmbild först.")
            return
        if not ocr.tesseract_available():
            messagebox.showwarning(
                "tesseract saknas",
                "tesseract är inte installerat, så bilden kan inte läsas av automatiskt.\n\n"
                "Två alternativ:\n"
                "1. Installera tesseract (macOS: brew install tesseract tesseract-lang, "
                "Ubuntu/Debian: sudo apt install tesseract-ocr tesseract-ocr-swe).\n"
                "2. Klistra in texten från bilden i textrutan och klicka på "
                "\u201dMatcha texten nedan\u201d. Det ger samma resultat.",
            )
            return
        self.ocr_out.delete("1.0", "end")

        def job():
            text = ocr.ocr_image(path)
            self.queue.put(("ocr", "--- OCR-text ---\n" + text + "\n----------------"))
            self.ocr_text.delete("1.0", "end")
            self.ocr_text.insert("end", text)
            self._match_entries(ocr.parse_entries(text))
        self._run_bg(job, "Läser av bild")

    def start_ocr_text(self) -> None:
        LOG.info("flik 3: OCR från text")
        text = self.ocr_text.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Tomt", "Klistra in text först.")
            return
        self.ocr_out.delete("1.0", "end")

        def job():
            self._match_entries(ocr.parse_entries(text))
        self._run_bg(job, "Matchar text")

    def _match_entries(self, entries) -> None:
        eng = self.engine or self._engine()
        if not entries:
            self.queue.put(("ocr", "Kunde inte läsa några titlar ur texten."))
            return
        self.queue.put(("ocr", f"{len(entries)} titlar tolkade — matchar …"))
        for i, e in enumerate(entries, 1):
            p, ms = eng.match_text(e.title, e.author, e.year)
            best = p.match.book if p.match else None
            line = (f"#{i}  {e.title}"
                    + (f"  /  {e.author}" if e.author else "")
                    + f"\n     -> {p.status.upper()}"
                    + (f"  {best.display}  ({p.match.score:.2f})" if best else "  ingen träff")
                    + (f"\n        album: {p.new_album} | serie: {p.new_series} #{p.new_series_number} | år: {p.new_year}" if best else "")
                    + (f"\n        {best.url}" if best else ""))
            self.queue.put(("ocr", line))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    logging_setup.setup_logging()

    def _excepthook(t, e, tb):
        LOG.error("OKÄND KRASCH I HUVUDTRÅDEN", exc_info=(t, e, tb))

    def _thread_hook(args):
        LOG.error("OKÄND KRASCH I TRÅD",
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook
    LOG.info("GUI startad (logg: %s)", logging_setup.DEFAULT_LOG)
    selftest = "--selftest" in argv
    try:
        app = App()
    except tk.TclError as exc:
        print(f"Kunde inte öppna ett fönster ({exc}).\n"
              "Kör i ett grafiskt skrivbord, eller använd kommandoraden: python -m ags.cli scan <mapp>",
              file=sys.stderr)
        return 2
    if selftest:
        app.root.update_idletasks()
        app.root.update()
        print(f"GUI byggd: {app.root.winfo_reqwidth()}x{app.root.winfo_reqheight()}, "
              f"{len(app.tree.get_children())} rader")
        app.root.destroy()
        return 0
    app.root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
