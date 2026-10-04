"""Tkinter-GUI för Audiobro.

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
from . import autostart as autostart_mod
from . import notifications as notif_mod
from . import fingerprint as fp_mod
try:
    from . import systray as systray_mod
except Exception:
    systray_mod = None  # type: ignore
from . import settings as settings_mod
from .nordic import BookBeatClient, NordicFallback, StorytelClient
from .openlibrary import OpenLibrary
from .tags import mutagen_available
from . import logging_setup
import webbrowser

# Hjälpmeny — donation + språk (svenska/engelska) — full översättning
STRINGS = {
    "sv": {
        "help": "Hjälp",
        "about": "Om Audiobro",
        "about_text": "Audiobro — ljudböcker \u2192 Goodreads \u2192 Audiobookshelf\n\nSt\u00f6d projektet via PayPal eller Ko-fi — tack! \u2764\ufe0f",
        "donate_paypal": "St\u00f6d projektet \u2014 PayPal",
        "donate_kofi": "St\u00f6d projektet \u2014 Ko-fi \u2615",
        "language": "Spr\u00e5k",
        "lang_sv": "Svenska",
        "lang_en": "English",
        "lang_changed": "Spr\u00e5k \u00e4ndrat till {lang} — starta om appen f\u00f6r full \u00f6vers\u00e4ttning.",
        "settings_title": "Inst\u00e4llningar",
        "delay": "F\u00f6rdr\u00f6jning (s):",
        "token_label": "Goodreads-token:",
        "use_token": "Anv\u00e4nd token",
        "write_series": "Skriv serie-taggar (TXXX:SERIES)",
        "auto_token": "L\u00e5s upp via min webbl\u00e4sare (Brave/Chromium) vid blockering",
        "album_becomes": "Album blir:",
        "album_opt1": "serie, #del",
        "album_opt2": "titel",
        "album_opt3": "serienamn",
        "backup": "S\u00e4kerhetskopiera (.agsbak)",
        "skip_done": "Hoppa \u00f6ver redan klara (historik)",
        "autostart": "🌅 Starta med datorn (autostart)",
        "autostart_tip": "Startar Audiobro automagiskt vid inloggning ☀️ (Windows/Linux/macOS)",
        "systray_start": "📌 Fäst i systemfältet",
        "systray_minimize": "📥 Minimera till klockan",
        "systray_tip": "Göms vid klockan istället för aktivitetsfältet ✨ (kräver pip install pystray)",
        "notifs": "💬 Notiser vid klar/fel",
        "dedup": "👯 Hitta dubbletter",
        "dedup_tip": "Jämför titel/författare + ljud-fingerprint 🎵 — hittar samma bok trots olika namn/bitrate",
        "tray_show": "Visa Audiobro",
        "tray_quit": "Avsluta",
        "waf_help": "🛡️ Goodreads hjälp",
        "check_deps": "🧩 Kolla tillägg",
        "clear_cache": "🧹 Rensa cache",
        "output_label": "📂 Outputmapp (Audiobookshelf):",
        "choose": "📁 Välj...",
        "open_output": "📂 Öppna outputmapp",
        "move": "🚚 Flytta filerna — radera källan (sparar HDD) ✨",
        "choose_folder": "📁 Välj mapp...",
        "scan_match": "✨ Skanna & matcha",
        "export_csv": "📊 Exportera CSV",
        "open_in_files": "🗂️ Visa i filhanteraren",
        "pick_good": "⭐ Välj bästa träff...",
        "write_selected": "✏️ Skriv taggar för valda",
        "write_green": "✅ Skriv alla gröna",
        "merge_parts": "🧩 Slå ihop delar",
        "organize_selected": "📚 Skicka valda → output",
        "organize_green": "🎉 Skicka alla klara → output",
        "tab_scan": " ✨ 1. Skanna & organisera ",
        "tab_manual": " 🔗 2. Enskild titel / länk ",
        "tab_ocr": " 📸 3. Skärmbild / text ",
        "tab_reco": " 💡 4. Rekommendationer ",
        "tab_log": " 📝 5. Logg ",
        "tab_hist": " 📚 6. Historik ",
        "remember": "Kom ih\u00e5g",
        "save_now": "Spara inst\u00e4llningar nu",
        "recent_import": "Senaste importmappar:",
        "recent_output": "Senaste outputmappar:",
        "history_update": "🔄 Uppdatera",
        "history_open": "📂 Öppna mapp",
        "history_remove": "🗑️ Ta bort",
        "history_clear": "🧹 Rensa allt",
        "history_refresh": "🔄 Sök uppdateringar",
        "history_apply": "✨ Uppdatera valda",
        "choose_small": "V\u00e4lj...",
        "timeline_hint": "V\u00e4lj en bok med serie f\u00f6r att se tidslinjen.",
        "pick_good_ellipsis": "V\u00e4lj bra tr\u00e4ff...",
        "choose_file": "V\u00e4lj fil...",
        "choose_image": "V\u00e4lj skr\u00e4rmbild...",
        "open_log": "\u00d6ppna loggfilen",
        "guide_menu": "Kom ig\u00e5ng - guide",
        "guide_title": "Kom ig\u00e5ng-guide",
        # — nya 2026-10-03: stepper & tydliga steg
        "stepper_title": "STEG",
        "stepper_hint": "→ följ 1→4 så blir allt rätt ✨",
        "step_choose": "Välj mappar",
        "step_scan": "Skanna",
        "step_review": "Granska",
        "step_organize": "Organisera",
        "settings_hint": "ändras direkt • sparas automatiskt • hovra för hjälp",
        "settings_card_folders": "  ①  Mappar",
        "settings_folders_hint": "Steg 1: välj var dina ljudböcker ligger och vart de ska hamna",
        "settings_output_hint": "Audiobookshelf-mappen",
        "move_hint": "sparar HDD • verifieras med hash",
        "settings_card_system": "  ②  System & utseende",
        "scan_card_choose": "①  Välj importmapp",
        "scan_card_choose_hint": "Var ligger dina ljudböcker nu? (t.ex. ~/Ljudböcker)",
        "scan_card_scan": "②  Skanna & matcha",
        "scan_card_scan_hint": "Hittar böcker → kollar Goodreads",
        "scan_hint": "💡 Tips: börja litet (1–2 böcker) för snabb test — sen kör hela biblioteket. Gröna rader = säkra, gula = kolla, röda = blockerade.",
        "review_header": "③  Granska resultatet",
        "review_hint": "grön=säker  •  gul=kolla  •  blå=klar  •  lila=dubblett  •  klicka för detaljer, högerklicka för Goodreads-länk",
        "organize_header": "④  Organisera",
        "organize_hint": "→ Audiobookshelf",
        "manual_header": "🔗 Alternativ väg — när skanning är blockerad",
        "manual_hint": "klistra Goodreads-länk = 100% träff",
        "ocr_header": "📸 Reservläge — skärmbild → text → matchning",
        "ocr_hint": "behöver ej Goodreads, funkar offline",
        "reco_header": "💡 Upptäck mer — baserat på din historik",
        "reco_hint": "nästa del i serier + fler av samma författare",
        "hist_header": "📚 Historik — redan klara",
        "hist_hint": "här hamnar organiserade böcker • de matchas aldrig igen",
        "empty_hint": "✨ Ingen skanning än — dra en mapp hit eller klicka  ✨ Skanna & matcha  🎧\nBörja litet för snabb test, sen hela biblioteket  •  1000000000% bättre tom-läge 💖",
        "dedup_none": "Inga dubbletter hittade 🎉\n\nInga böcker delade titel/författare + ljud-fingerprint över 0.82.",
        "dedup_status_none": "Inga dubbletter — allt ser unikt ut.",
        "dedup_hint": "Samma bok hittad flera gånger — även över källor (Goodreads/BookBeat/Storytel). Markerade lila. Välj att ignorera om du vill behålla båda.",
        "dedup_ignore": "🙈 Ignorera dublett (även över källor)",
        "dedup_unignore": "👁️ Sluta ignorera dublett",
        "dedup_ignore_selected": "🙈 Ignorera valda",
        "dedup_ignore_all": "🙈 Ignorera alla",
        "dedup_show_ignored": "👁️ Visa ignorerade",
        "dedup_clear_ignored": "🧹 Rensa ignorerade",
        "dedup_close": "Stäng",
        "btn_show": "Öppna i filhanterare",
        "btn_pick": "Välj bra träff…",
        "btn_write": "Skriv taggar för valda rader",
        "btn_write_all": "Skriv alla gröna rader",
        "btn_dup": "👯 Dubbletter",
        "btn_merge": "Slå ihop markerade delar",
        "btn_send_selected": "Organisera valda → output",
        "btn_send_all": "Organisera gröna + OK-frågade",
        "btn_reco": "Hämta rekommendationer",
        "reco_desc": "Goodreads-förslag utifrån din historik: nästa del i serier, mer av författarna och liknande böcker.",
        "quality_title": "🎧 Ljudkvalitet",
        "quality_best": "Bäst ljud",
        "quality_worse": "Sämre",
        "quality_info": "Jämför ljud — storlek, format och bitrate. Ska sämre version ersättas?",
        "quality_keep_best": "✅ Behåll bästa",
        "quality_replace": "🔄 Ersätt sämre",
        "quality_ask": "Vill du ersätta den sämre versionen med den bästa?",
        "quality_best_is": "Bäst ljud: {label} ({info}) — bättre än övriga. Vill du behålla bara den bästa och skippa resten?",
        "quality_no_diff": "Alla versioner har likvärdigt ljud.",
        "quality_compare_btn": "🎧 Jämför ljudkvalitet",
    },
    "en": {
        "help": "Help",
        "about": "About Audiobro",
        "about_text": "Audiobro — audiobooks \u2192 Goodreads \u2192 Audiobookshelf\n\nSupport the project via PayPal or Ko-fi — thank you! \u2764\ufe0f",
        "donate_paypal": "Support the project — PayPal",
        "donate_kofi": "Support the project — Ko-fi \u2615",
        "language": "Language",
        "lang_sv": "Svenska",
        "lang_en": "English",
        "lang_changed": "Language changed to {lang} — restart the app for full translation.",
        "settings_title": "Settings",
        "delay": "Delay (s):",
        "token_label": "Goodreads-token:",
        "use_token": "Use token",
        "write_series": "Write series tags (TXXX:SERIES)",
        "auto_token": "Unlock via my browser (Brave/Chromium) when blocked",
        "album_becomes": "Album becomes:",
        "album_opt1": "series, #part",
        "album_opt2": "title",
        "album_opt3": "series name",
        "backup": "Backup (.agsbak)",
        "skip_done": "Skip already done (history)",
        "autostart": "🌅 Launch at login (autostart)",
        "autostart_tip": "Launch Audiobro automagically at login ☀️ (Windows/Linux/macOS)",
        "systray_start": "📌 Pin to system tray",
        "systray_minimize": "📥 Minimize to clock",
        "systray_tip": "Hides by the clock instead of taskbar ✨ (needs pip install pystray)",
        "notifs": "💬 Desktop notifications",
        "dedup": "👯 Find duplicates",
        "dedup_tip": "Compare title/author + audio fingerprint 🎵 — finds same book despite different name/bitrate",
        "tray_show": "Show Audiobro",
        "tray_quit": "Quit",
        "waf_help": "🛡️ Goodreads help",
        "check_deps": "🧩 Check add-ons",
        "clear_cache": "🧹 Clear cache",
        "output_label": "📂 Output folder (Audiobookshelf):",
        "choose": "📁 Choose...",
        "open_output": "📂 Open output folder",
        "move": "🚚 Move files — delete source (save HDD) ✨",
        "choose_folder": "📁 Choose folder...",
        "scan_match": "✨ Scan & match",
        "export_csv": "📊 Export CSV",
        "open_in_files": "🗂️ Show in file manager",
        "pick_good": "⭐ Pick best hit...",
        "write_selected": "✏️ Write tags for selected",
        "write_green": "✅ Write all green",
        "merge_parts": "🧩 Merge parts",
        "organize_selected": "📚 Send selected → output",
        "organize_green": "🎉 Send all ready → output",
        "tab_scan": " ✨ 1. Scan & organize ",
        "tab_manual": " 🔗 2. Single title / link ",
        "tab_ocr": " 📸 3. Screenshot / text ",
        "tab_reco": " 💡 4. Recommendations ",
        "tab_log": " 📝 5. Log ",
        "tab_hist": " 📚 6. History ",
        "remember": "Remember",
        "save_now": "Save settings now",
        "recent_import": "Recent import folders:",
        "recent_output": "Recent output folders:",
        "history_update": "🔄 Refresh",
        "history_open": "📂 Open folder",
        "history_remove": "🗑️ Remove",
        "history_clear": "🧹 Clear all",
        "history_refresh": "🔄 Check for updates",
        "history_apply": "✨ Update selected",
        "choose_small": "Choose...",
        "timeline_hint": "Select a book with a series to see the timeline.",
        "pick_good_ellipsis": "Pick good hit...",
        "choose_file": "Choose file...",
        "choose_image": "Choose screenshot...",
        "open_log": "Open log file",
        "guide_menu": "Getting Started Guide",
        "guide_title": "Getting Started",
        "stepper_title": "STEPS",
        "stepper_hint": "→ follow 1→4 for perfect result ✨",
        "step_choose": "Choose folders",
        "step_scan": "Scan",
        "step_review": "Review",
        "step_organize": "Organize",
        "settings_hint": "changes instantly • saved automatically • hover for help",
        "settings_card_folders": "  ①  Folders",
        "settings_folders_hint": "Step 1: where are your audiobooks and where should they go",
        "settings_output_hint": "Audiobookshelf folder",
        "move_hint": "saves HDD • hash-verified",
        "settings_card_system": "  ②  System & appearance",
        "scan_card_choose": "①  Choose import folder",
        "scan_card_choose_hint": "Where are your audiobooks now? (e.g. ~/Audiobooks)",
        "scan_card_scan": "②  Scan & match",
        "scan_card_scan_hint": "Finds books → checks Goodreads",
        "scan_hint": "💡 Tip: start small (1–2 books) for quick test — then whole library. Green=safe yellow=check red=blocked.",
        "review_header": "③  Review results",
        "review_hint": "green=safe  •  yellow=check  •  blue=done  •  purple=duplicate  •  click for details, right-click for Goodreads link",
        "organize_header": "④  Organize",
        "organize_hint": "→ Audiobookshelf",
        "manual_header": "🔗 Alternative — when scan is blocked",
        "manual_hint": "paste Goodreads link = 100% hit",
        "ocr_header": "📸 Fallback — screenshot → text → match",
        "ocr_hint": "no Goodreads needed, works offline",
        "reco_header": "💡 Discover more — based on your history",
        "reco_hint": "next in series + more by same authors",
        "hist_header": "📚 History — already done",
        "hist_hint": "organized books end up here • never matched again",
        "empty_hint": "✨ No scan yet — drag a folder here or click  ✨ Scan & match  🎧\nStart small for quick test, then whole library  •  1000000000% better empty state 💖",
        "dedup_none": "No duplicates found 🎉\n\nNo books shared title/author + audio fingerprint over 0.82.",
        "dedup_status_none": "No duplicates — all unique.",
        "dedup_hint": "Same book found multiple times — even across sources (Goodreads/BookBeat/Storytel). Marked purple. Choose ignore if you want to keep both.",
        "dedup_ignore": "🙈 Ignore duplicate (even across sources)",
        "dedup_unignore": "👁️ Un-ignore duplicate",
        "dedup_ignore_selected": "🙈 Ignore selected",
        "dedup_ignore_all": "🙈 Ignore all",
        "dedup_show_ignored": "👁️ Show ignored",
        "dedup_clear_ignored": "🧹 Clear ignored",
        "dedup_close": "Close",
        "btn_show": "📂 Show",
        "btn_pick": "⭐ Pick",
        "btn_write": "✏️ Write",
        "btn_write_all": "✅ All green",
        "btn_dup": "👯 Duplicates",
        "btn_merge": "🧩 Merge",
        "btn_send_selected": "📚 Send selected",
        "btn_send_all": "🎉 Send all done",
        "btn_reco": "Fetch recommendations",
        "reco_desc": "Goodreads suggestions from your history: next in series, more by authors, and similar books.",
        "quality_title": "🎧 Audio quality",
        "quality_best": "Best quality",
        "quality_worse": "Worse",
        "quality_info": "Compare audio — size, format and bitrate. Replace the worse version?",
        "quality_keep_best": "✅ Keep best",
        "quality_replace": "🔄 Replace worse",
        "quality_ask": "Do you want to replace the worse version with the best?",
        "quality_best_is": "Best audio: {label} ({info}) — better than the others. Keep only the best and skip the rest?",
        "quality_no_diff": "All versions have similar quality.",
        "quality_compare_btn": "🎧 Compare audio quality",
    },
}
PAYPAL_URL = "https://paypal.me/Rickard3dPrint"
KOFI_URL = "https://ko-fi.com/tokke2"

# Krav 28: logga precis allt — filloggningen startar direkt vid import.
logging_setup.setup_logging()
LOG = logging_setup.get("gui")

APP_TITLE = "🌉 Audiobro — Goodreads → Audiobookshelf ✨📚"


class App:
    """Hela fönstret. All affärslogik ligger i ags.engine — det här är bara vy."""

    def __init__(self, root: tk.Tk | None = None, delay: float = 1.5) -> None:
        self.root = root or tk.Tk()
        self.root.title(APP_TITLE)
        # --- ikon överallt (aktivitetsfält, Alt-Tab, fönsterhanterare, systray) ---
        try:
            self._set_app_icon()
        except Exception:
            pass
        # --- glad design — tydligare, varmare, mer färg ---
        try:
            self._apply_happy_theme()
        except Exception:
            pass
        # --- fönsteranpassning: respektera aktivitetsfältet så allt är synligt ---
        try:
            self._fit_to_screen()
        except Exception:
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
        self._autostart = tk.BooleanVar(value=False)  # autostart vid inloggning (multi-OS)
        self._start_to_tray = tk.BooleanVar(value=False)  # starta i systemfältet
        self._minimize_to_tray = tk.BooleanVar(value=False)  # minimera till systemfältet
        self._notifs = tk.BooleanVar(value=True)  # native notiser
        self._use_fingerprint = tk.BooleanVar(value=False)  # ljudmatchning endast på begäran (opt-in)
        self._lang = tk.StringVar(value="sv")  # språk sv/en — sparas i settings.json
        self._theme = tk.StringVar(value="light")  # light/dark — 1000000000% bättre
        self._tray = None  # systray.Tray eller None
        self._tray_visible = False
        self._current_step = 1  # för stepper — 1..4
        self._stepper_circles = []  # type: ignore
        self._stepper_labels = []  # type: ignore
        self._stepper_lines = []  # type: ignore
        self.build()
        self.root.after(120, self._poll)
        # Om start i systray är ikryssad (eller --tray vid autostart), göm fönstret efter ritning
        try:
            self.root.after(600, self._maybe_start_to_tray)
        except Exception:
            pass

    # ------------------------------------------------------------------ bygg
    def build(self) -> None:
        # Header-banner — 1000000000% bättre: gradient-känsla, bättre hierarki, theme-aware
        try:
            TOK = getattr(self, "_tokens", {"bg3": "#FFF0B3", "bg": "#FFFBF5"})
            bg = TOK.get("bg3", "#FFF0B3")
            bg_main = TOK.get("bg", "#FFFBF5")
            banner = tk.Frame(self.root, bg=bg, bd=0, highlightthickness=0)
            banner.pack(fill="x", padx=0, pady=0)
            # Accent-linje överst — 3px
            top_line = tk.Frame(banner, bg="#6EC6FF", height=3)
            top_line.pack(fill="x", side="top")
            inner = tk.Frame(banner, bg=bg)
            inner.pack(fill="x", padx=12, pady=8)  # 500M: andningsutrymme
            # Ikon — endast icon-happy.png gäller (alla andra borttagna)
            try:
                import pathlib as _pl
                _icon = None
                for _cand in (_pl.Path(__file__).resolve().parent.parent / "assets" / "icon-happy.png",):
                    if _cand.exists():
                        _icon = tk.PhotoImage(file=str(_cand))
                        try:
                            factor = max(1, _icon.width() // 26)
                            if factor > 1:
                                _icon = _icon.subsample(factor, factor)
                        except Exception:
                            pass
                        break
                if _icon is not None:
                    lbl_i = tk.Label(inner, image=_icon, bg=bg, bd=0)
                    lbl_i.image = _icon
                    lbl_i.pack(side="left", padx=(6,8))
            except Exception:
                pass
            # Text-stack
            txt_col = tk.Frame(inner, bg=bg)
            txt_col.pack(side="left", fill="y")
            tk.Label(txt_col, text="Audiobro", bg=bg, fg="#1A1B26" if self._theme.get()=="light" else "#C0CAF5", font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
            tk.Label(txt_col, text="Goodreads → Audiobookshelf  •  tagga & organisera på ett klick", bg=bg, fg="#5A5A72" if self._theme.get()=="light" else "#9AA5CE", font=("TkDefaultFont", 10)).pack(anchor="w")
            # Höger sida — status + theme-toggle
            right = tk.Frame(inner, bg=bg)
            right.pack(side="right", padx=8)
            tk.Label(right, text="✨ 1000000000% bättre design", bg=bg, fg="#D35400", font=("TkDefaultFont", 8, "bold")).pack(anchor="e")
            # Theme-toggle knapp — 1000000000% bättre
            def _toggle_theme():
                try:
                    cur = self._theme.get()
                    nxt = "dark" if cur=="light" else "light"
                    self._theme.set(nxt)
                    from . import settings as _st
                    d = _st.load(); d["theme"]=nxt; _st.save(d)
                    self._apply_happy_theme()
                    # rebuild banner colors
                    self.root.update_idletasks()
                    LOG.info("theme toggled %s→%s", cur, nxt)
                except Exception as exc:
                    LOG.debug("toggle theme fel: %s", exc)
            # Spara ref så vi kan anropa från settings också
            self._toggle_theme = _toggle_theme
            # Liten knapp — använd tk.Button för att få bg att funka
            tbtn = tk.Button(right, text="🌙 Mörk" if self._theme.get()=="light" else "☀️ Ljus", command=_toggle_theme, bg=TOK.get("surface","#FFFFFF") if "TOK" in locals() else bg, fg=TOK.get("text","#1F2235") if "TOK" in locals() else "#1F2235", bd=1, relief="solid", padx=12, pady=4, font=("TkDefaultFont", 10, "bold"), highlightthickness=0, activebackground=TOK.get("bg2","#FFF4E6") if "TOK" in locals() else "#FFF4E6", highlightbackground=TOK.get("border","#FFE4C4") if "TOK" in locals() else "#FFE4C4")  # 500M fix
            tbtn.pack(anchor="e", pady=(2,0))
        except Exception as exc:
            import logging as _lg
            _lg.getLogger("gui").debug("banner 1B misslyckades: %s", exc)
        self._build_settings()
        try:
            self._build_stepper()
        except Exception as exc:
            LOG.debug("stepper misslyckades: %s", exc)
        # Footer först — alltid synlig längst ner (före notebook, annars göms bakom expand)
        TOK_F_pre = getattr(self, "_tokens", {"bg": "#FFFBF5", "bg2":"#FFF4E6", "accent":"#0EA5E9", "border":"#FFE4C4", "text":"#1F2235"})
        _footer_pre = tk.Frame(self.root, bg=TOK_F_pre.get("bg", "#FFFBF5"), bd=0, highlightthickness=0)
        _footer_pre.pack(fill="x", side="bottom", padx=0, pady=0)
        # placeholder — riktig footer skapas efter _build_* , denna håller plats så pack-ordningen blir rätt
        self._footer_placeholder = _footer_pre

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=4)
        self.tab_scan = ttk.Frame(nb)
        self.tab_review = ttk.Frame(nb)  # NY 2026-10-04: egen flik för tabellen — 100% mer yta, h=1 fix
        self.tab_manual = ttk.Frame(nb)
        self.tab_ocr = ttk.Frame(nb)
        self.tab_reco = ttk.Frame(nb)
        self.tab_missing = ttk.Frame(nb)  # dölj för lik layout som skärmbild (6 flikar)
        self.tab_log = ttk.Frame(nb)
        self.tab_hist = ttk.Frame(nb)
        nb.add(self.tab_scan, text=self._t("tab_scan"))
        nb.add(self.tab_review, text="3. Granska")
        nb.add(self.tab_manual, text=self._t("tab_manual"))
        nb.add(self.tab_ocr, text=self._t("tab_ocr"))
        nb.add(self.tab_reco, text=self._t("tab_reco"))
        nb.add(self.tab_log, text=self._t("tab_log"))
        nb.add(self.tab_hist, text=self._t("tab_hist"))
        self._build_scan(self.tab_scan)
        self._build_manual(self.tab_manual)
        self._build_ocr(self.tab_ocr)
        self._build_reco(self.tab_reco)
        # self._build_missing(self.tab_missing)  # dold för att matcha skärmbildens 6 flikar
        self._build_log(self.tab_log)
        self._build_history(self.tab_hist)
        # Status + Progress — 500000M BÅTTRE: alltid synlig progressbar med FET text, svart i ljust/vit i mörkt
        TOK_F = getattr(self, "_tokens", {"bg": "#FFFBF5", "bg2":"#FFF4E6", "accent":"#0EA5E9", "border":"#FFE4C4", "text":"#1F2235"})
        # Återanvänd placeholder-footer för korrekt pack-ordning (annars göms bakom notebook expand)
        footer = getattr(self, "_footer_placeholder", None)
        if footer is None or not footer.winfo_exists():
            footer = tk.Frame(self.root, bg=TOK_F.get("bg", "#FFFBF5"), bd=0, highlightthickness=0)
            footer.pack(fill="x", side="bottom", padx=0, pady=0)
        else:
            footer.config(bg=TOK_F.get("bg", "#FFFBF5"))
        # se till att footer ligger längst ner — pack före notebook redan gjort, lyft bara footer
        try:
            footer.lift()
            # säkerställ att footer fortfarande är side=bottom (pack kräver att den är sist i pack-ordningen för bottom)
            footer.pack_configure(fill="x", side="bottom", padx=0, pady=0)
        except: pass
        self._footer = footer
        # Progress — Canvas med fet text alltid synlig (krav: fet svart i ljust, vit i mörkt)
        is_dark = getattr(self, "_theme", None)
        try:
            is_dark = is_dark.get() == "dark" if hasattr(is_dark, "get") else str(is_dark)=="dark"
        except: is_dark = False
        prog_bg = TOK_F.get("bg2", "#FFF4E6")
        prog_fill = TOK_F.get("accent", "#0EA5E9")
        text_color = "#FFFFFF" if is_dark else "#000000"  # FET vit i mörkt, FET svart i ljust
        #  Canvas 32px hög, tydlig border, fet text alltid centrerad — syns alltid vid import
        self._prog_canvas = tk.Canvas(footer, height=32, bg=prog_bg, highlightthickness=2, highlightbackground=TOK_F.get("border","#FFE4C4"), highlightcolor=TOK_F.get("accent","#0EA5E9"), bd=0, relief="flat")
        self._prog_canvas.pack(fill="x", padx=2, pady=2)
        # Behåll kompatibel ttk.Progressbar dold för tester
        try:
            self.prog = ttk.Progressbar(footer, mode="determinate", style="Horizontal.TProgressbar")
            self.prog.pack_forget()
        except: self.prog = None
        self._prog_canvas._prog_bg_color = prog_bg
        self._prog_canvas._prog_fill_color = prog_fill
        self._prog_canvas._prog_text_color = text_color
        # fill-rektangel 0 bredd initialt (32 hög)
        self._prog_canvas.create_rectangle(0, 0, 0, 32, fill=prog_fill, outline="", tags="prog_fill")
        # Bakgrunds-rektangel för text (så fet text alltid har kontrast, oavsett fill)
        self._prog_canvas.create_rectangle(0, 0, 0, 0, fill=prog_bg, outline="", tags="prog_text_bg")
        # FET text centrerad — alltid synlig, svart i ljust / vit i mörkt, med vit/svart halo för extra läsbarhet
        # Vi skapar 4 halo-text för outline + 1 huvudtext
        for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1)]:
            self._prog_canvas.create_text(0, 16+dy, anchor="center", text="Redo. ✨", fill="white" if text_color=="#000000" else "black", font=("TkDefaultFont", 11, "bold"), tags="prog_text_halo")
        self._prog_canvas.create_text(0, 16, anchor="center", text="Redo. ✨", fill=text_color, font=("TkDefaultFont", 11, "bold"), tags="prog_text")
        # även procent separat höger? Vi använder en text som uppdateras till "Label n/total — pct%"
        self._prog_canvas._prog_last = (0, 1, "Redo")
        # Statusrad med ikon (under progress)
        status_frame = tk.Frame(footer, bg=TOK_F.get("bg", "#FFFBF5"))
        status_frame.pack(fill="x", padx=8, pady=4)
        tk.Label(status_frame, text="●", fg="#2ECC71", bg=status_frame["bg"], font=("TkDefaultFont", 10)).pack(side="left", padx=(2,6))
        self.status = tk.Label(status_frame, text="Redo. ✨", anchor="w", bg=status_frame["bg"], fg="#000000" if not is_dark else "#FFFFFF", font=("TkDefaultFont", 10, "bold"))  # FET svart/vit
        self.status.pack(side="left", fill="x", expand=True)
        tk.Label(status_frame, text="v1.0  •  Audiobro 🌉", bg=status_frame["bg"], fg="#8A8A9E", font=("TkDefaultFont", 9)).pack(side="right", padx=6)
        # Säkerställ att progressbaren alltid syns (ibland dold vid temabyte) — 100% alltid
        try:
            self._prog_canvas.lift()
            self._prog_canvas.pack(fill="x", padx=2, pady=2)
            footer.lift()
            footer.pack(fill="x", side="bottom", padx=0, pady=0)
            # tvinga geometriuppdatering så winfo_width blir korrekt direkt
            try:
                self.root.update_idletasks()
                # sätt initial prog text så den syns även före scan
                self._prog_canvas.coords("prog_text", self._prog_canvas.winfo_width()//2 if self._prog_canvas.winfo_width()>50 else 400, 16)
            except: pass
        except: pass
        LOG.debug("footer/progress packad: footer w=%s canvas w=%s visible=%s", footer.winfo_width() if footer.winfo_exists() else -1, self._prog_canvas.winfo_width() if self._prog_canvas.winfo_exists() else -1, self._prog_canvas.winfo_viewable() if hasattr(self._prog_canvas, "winfo_viewable") else "?")
        for w in presenter.startup_warnings():
            self.root.after(200, lambda m=w: messagebox.showwarning("Saknas", m))

    def _build_stepper(self) -> None:
        """Tydlig steg-indikator — 4 steg överst, alltid synlig. Hela appen byter språk direkt."""
        TOK = getattr(self, "_tokens", {"bg": "#FFFBF5", "border": "#FFE4C4", "accent": "#6EC6FF", "ok": "#2ECC71", "text": "#2B2D42", "text3": "#8A8A9E"})
        bg = TOK.get("bg", "#FFFBF5")
        bar = tk.Frame(self.root, bg=bg, bd=1, relief="solid", highlightbackground=TOK.get("border","#FFE4C4"), highlightthickness=1)
        bar.pack(fill="x", padx=10, pady=(0,6))
        self._stepper_title = tk.Label(bar, text=self._t("stepper_title"), bg=bg, fg=TOK.get("text3","#8A8A9E"), font=("TkDefaultFont", 7, "bold"))
        self._stepper_title.pack(side="left", padx=10)
        steps = [("1", self._t("step_choose")), ("2", self._t("step_scan")), ("3", self._t("step_review")), ("4", self._t("step_organize"))]
        self._stepper_circles.clear(); self._stepper_labels.clear(); self._stepper_lines.clear()
        for i, (num, label) in enumerate(steps):
            if i>0:
                line = tk.Frame(bar, bg=TOK.get("border","#FFE4C4"), width=28, height=2)
                line.pack(side="left", padx=2, pady=14)
                self._stepper_lines.append(line)
            col = tk.Frame(bar, bg=bg)
            col.pack(side="left", padx=6)
            circ = tk.Label(col, text=num, bg=TOK.get("border","#FFE4C4"), fg="#5A5A72", font=("TkDefaultFont", 8, "bold"), width=2, height=1, bd=0, relief="flat", padx=4, pady=1)
            circ.config(highlightthickness=0, borderwidth=0)
            try:
                circ.config(bg=TOK.get("border","#FFE4C4"))
            except: pass
            circ.pack(side="left")
            lbl = tk.Label(col, text=label, bg=bg, fg=TOK.get("text3","#8A8A9E"), font=("TkDefaultFont", 10))
            lbl.pack(side="left", padx=4)
            self._stepper_circles.append(circ)
            self._stepper_labels.append(lbl)
        # hjälphint höger
        self._stepper_hint = tk.Label(bar, text=self._t("stepper_hint"), bg=bg, fg=TOK.get("text3","#8A8A9E"), font=("TkDefaultFont", 9))
        self._stepper_hint.pack(side="right", padx=10)
        self._stepper_bar = bar
        self._update_stepper(1)

    def _update_stepper(self, step: int) -> None:
        """Markera aktivt steg 1..4 — grön=klar, blå=aktiv, grå=kommande."""
        try:
            TOK = getattr(self, "_tokens", {"accent":"#6EC6FF","ok":"#2ECC71","border":"#FFE4C4","text3":"#8A8A9E","text":"#2B2D42"})
            step = max(1, min(4, int(step)))
            self._current_step = step
            for i, (circ, lbl) in enumerate(zip(self._stepper_circles, self._stepper_labels), start=1):
                if i < step:
                    circ.config(bg=TOK.get("ok","#2ECC71"), fg="white")
                    lbl.config(fg=TOK.get("text","#2B2D42"), font=("TkDefaultFont", 8, "bold"))
                elif i == step:
                    circ.config(bg=TOK.get("accent","#6EC6FF"), fg="white")
                    lbl.config(fg=TOK.get("text","#2B2D42"), font=("TkDefaultFont", 8, "bold"))
                else:
                    circ.config(bg=TOK.get("border","#FFE4C4"), fg="#5A5A72")
                    lbl.config(fg=TOK.get("text3","#8A8A9E"), font=("TkDefaultFont", 10))
                # rund hörn-effekt via border
                try:
                    circ.config(bd=0, relief="flat")
                except: pass
            for i, line in enumerate(self._stepper_lines, start=1):
                if i < step:
                    line.config(bg=TOK.get("ok","#2ECC71"))
                else:
                    line.config(bg=TOK.get("border","#FFE4C4"))
        except Exception as exc:
            LOG.debug("stepper update fel: %s", exc)

    # ------------------------------------------------------------- ikon & fönster
    def _set_app_icon(self) -> None:
        import pathlib
        import sys
        # Hitta ikonfil — ENDAST assets/icon-happy.png (alla andra borttagna)
        bases = []
        try:
            if hasattr(sys, "_MEIPASS"):
                bases.append(pathlib.Path(sys._MEIPASS))
                bases.append(pathlib.Path(sys._MEIPASS) / "assets")
            bases.append(pathlib.Path(__file__).resolve().parent.parent)
            bases.append(pathlib.Path(__file__).resolve().parent)
            bases.append(pathlib.Path.cwd())
            bases.append(pathlib.Path.cwd() / "assets")
        except Exception:
            bases = [pathlib.Path(__file__).resolve().parent.parent]
        ico = None
        png = None
        for b in bases:
            for cand in (b / "assets" / "icon-happy.png", b / "icon-happy.png", b / "assets" / "icon.png", b / "icon.png"):
                # stöder både nya och fallback under övergång
                if cand.exists():
                    if cand.suffix.lower() == ".png" and png is None:
                        png = cand
            # ico genereras från png om det behövs — ingen separat fil krävs
        # fallback till icon-happy.png
        if png is None:
            png = pathlib.Path(__file__).resolve().parent.parent / "assets" / "icon-happy.png"
        # försök även hitta .ico genererad från happy om den finns (bakåtkompat)
        for b in bases:
            for cand in (b / "assets" / "icon.ico", b / "icon.ico"):
                if cand.exists():
                    ico = cand
                    break
            if ico: break
        # Försök först .ico på Windows (om ico finns), annars använd png direkt
        if sys.platform.startswith("win") and ico is not None and ico.exists():
            try:
                self.root.iconbitmap(str(ico))
            except Exception as exc:
                LOG.debug("iconbitmap .ico misslyckades: %s", exc)
        elif sys.platform.startswith("win") and png is not None and png.exists():
            # Windows utan .ico — iconphoto räcker, men prova iconbitmap via png om möjligt
            try:
                # PIL-genererad ico fallback — Tk på Windows kan ibland ta png
                pass
            except Exception:
                pass
        # iconphoto för alla plattformar (kräver PhotoImage) — ger även hanterarikon på Linux/macOS
        # Håll referens i self._icon_images så den inte garbage-collectas
        self._icon_images = getattr(self, "_icon_images", [])
        for cand in tuple(x for x in (png, ico) if x is not None):
            if not cand.exists():
                continue
            try:
                # Försök med tk.PhotoImage för PNG (inbyggt, ingen PIL krävs)
                if cand.suffix.lower() == ".png":
                    img = tk.PhotoImage(file=str(cand))
                    # Skala ner för små ikoner om bilden är 512 — PhotoImage behåller skärpa ändå
                    self.root.iconphoto(True, img)
                    self._icon_images.append(img)
                    LOG.debug("ikon satt via iconphoto %s", cand)
                    break
            except Exception as exc:
                LOG.debug("iconphoto PNG misslyckades: %s", exc)
                try:
                    # Fallback via PIL om PhotoImage inte klarar stor PNG
                    from PIL import Image, ImageTk
                    pil = Image.open(cand).resize((64, 64), Image.LANCZOS)
                    tkimg = ImageTk.PhotoImage(pil)
                    self.root.iconphoto(True, tkimg)
                    self._icon_images.append(tkimg)
                    break
                except Exception:
                    continue
        # Sätt även för Toplevel-fönster automatiskt via default root-icon (iconphoto True ger arv)

    def _fit_to_screen(self) -> None:
        # Anpassa fönsterstorlek och position till tillgänglig arbetsyta (minus aktivitetsfält/dock)
        # så allt alltid är synligt även när aktivitetsfältet är öppet (Windows/macOS/Linux).
        self.root.update_idletasks()
        try:
            import ctypes
            from ctypes import wintypes
        except Exception:
            ctypes = None
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        work_x, work_y = 0, 0
        work_w, work_h = sw, sh
        # Windows: fråga SystemParametersInfoW SPI_GETWORKAREA (exkl aktivitetsfältet)
        if ctypes is not None:
            try:
                rect = wintypes.RECT()
                SPI_GETWORKAREA = 0x0030
                if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
                    work_x = rect.left
                    work_y = rect.top
                    work_w = rect.right - rect.left
                    work_h = rect.bottom - rect.top
                    LOG.debug("arbetsyta från SPI_GETWORKAREA: %dx%d+%d+%d", work_w, work_h, work_x, work_y)
            except Exception as exc:
                LOG.debug("SPI_GETWORKAREA misslyckades: %s", exc)
        # Fallback: Tk:s wm_maxsize rapporterar ofta arbetsytan (t.ex. Linux)
        try:
            mx, my = self.root.wm_maxsize()
            # wm_maxsize är större än skärm på vissa system — använd bara om rimligt mindre
            if 800 < mx < sw and 600 < my < sh:
                # Om vi inte redan fick work via ctypes, använd detta
                if work_w == sw and work_h == sh:
                    work_w, work_h = mx, my
                    LOG.debug("arbetsyta från wm_maxsize: %dx%d", work_w, work_h)
        except Exception:
            pass
        # macOS/Linux: prova även via tkinter maxsize vs screen
        # Önskad storlek (designmått)
        desired_w, desired_h = 1180, 780
        # Marginal så fönstret inte klistrar i kanten och dekorationer får plats
        pad_x, pad_y = 16, 16
        avail_w = max(720, work_w - pad_x * 2)
        avail_h = max(480, work_h - pad_y * 2)
        # Windows dekorationer tar ~8px kant + titelrad ~30px — dra av lite extra
        avail_h = max(480, avail_h - 16)
        win_w = min(desired_w, avail_w)
        win_h = min(desired_h, avail_h)
        # Centrera i arbetsytan
        x = work_x + (work_w - win_w) // 2
        y = work_y + (work_h - win_h) // 2
        # Clampa så vi aldrig hamnar utanför arbetsytan (viktigt när aktivitetsfältet är på vänster/höger/top)
        x = max(work_x, min(x, work_x + work_w - win_w))
        y = max(work_y, min(y, work_y + work_h - win_h))
        # På små skärmar: säkerställ minst 40% synlig höjd
        self.root.minsize(960, 580)
        try:
            self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")
        except Exception:
            self.root.geometry(f"{win_w}x{win_h}")
        # Gör fönstret storleksbart och hantera framtida skärmändringar (docka/aktivitetsfält flyttas)
        try:
            self.root.resizable(True, True)
            # Lyssna på skärmupplösningsändringar — om arbetsytan ändras, anpassa om fönstret är maximerat
            self._work_area = (work_x, work_y, work_w, work_h)
            self._desired_size = (desired_w, desired_h)
        except Exception:
            pass
        LOG.info("fönster anpassat: %dx%d+%d+%d (skärm %dx%d arbetsyta %dx%d)", win_w, win_h, x, y, sw, sh, work_w, work_h)

    def _apply_icon_to_toplevel(self, win: tk.Toplevel) -> None:
        # Hjälpare för dialoger/guide — ärver huvudikonen
        try:
            if hasattr(self, "_icon_images") and self._icon_images:
                win.iconphoto(False, self._icon_images[0])
        except Exception:
            pass

    def _apply_happy_theme(self) -> None:
        """500000000% bättre — fixad light/dark-växling + bättre layout/font/läsbarhet."""
        try:
            style = ttk.Style()
            try:
                style.theme_use("clam")
            except Exception:
                pass
            # === DESIGNTOKENS — 500M bättre: ökad kontrast, WCAG AAA, större läsyta ===
            #  FET SVART i ljust / FET VIT i mörkt — ingen text otydlig (WCAG AAA, 21:1 kontrast)
            TOKENS_LIGHT = {
                "bg": "#FFFBF5", "bg2": "#FFF4E6", "bg3": "#FFF0B3",
                "surface": "#FFFFFF", "surface2": "#FFF8F0",
                "border": "#FFDAB9", "border2": "#FFBCA8",
                "text": "#000000", "text2": "#000000", "text3": "#000000",
                "accent": "#0EA5E9", "accent2": "#0284C7", "accent3": "#F97316",
                "ok": "#059669", "ok2": "#047857", "warn": "#D97706", "err": "#DC2626",
                "sol": "#F59E0B", "lav": "#FFE4E6", "mint": "#D1FAE5",
            }
            TOKENS_DARK = {
                "bg": "#0F172A", "bg2": "#1E293B", "bg3": "#334155",
                "surface": "#1E293B", "surface2": "#0F172A",
                "border": "#475569", "border2": "#64748B",
                "text": "#FFFFFF", "text2": "#FFFFFF", "text3": "#FFFFFF",
                "accent": "#38BDF8", "accent2": "#0EA5E9", "accent3": "#FB923C",
                "ok": "#34D399", "ok2": "#10B981", "warn": "#FBBF24", "err": "#F87171",
                "sol": "#FBBF24", "lav": "#DDD6FE", "mint": "#6EE7B7",
            }
            # FIX: hantera StringVar korrekt — tidigare bug gjorde att dark aldrig valdes
            raw_theme = getattr(self, "_theme", None)
            if isinstance(raw_theme, str):
                theme_name = raw_theme if raw_theme in ("light","dark") else "light"
            elif hasattr(raw_theme, "get"):
                try:
                    theme_name = raw_theme.get()
                    if theme_name not in ("light","dark"):
                        theme_name = "light"
                except Exception:
                    theme_name = "light"
            else:
                try:
                    from . import settings as _st
                    theme_name = _st.load().get("theme", "light")
                except Exception:
                    theme_name = "light"
                # behåll StringVar om den fanns, annars skapa
                if hasattr(self, "_theme") and hasattr(self._theme, "set"):
                    try: self._theme.set(theme_name)
                    except: pass
                else:
                    import tkinter as _tk
                    self._theme = _tk.StringVar(value=theme_name)
            # säkerställ att self._theme alltid är StringVar efteråt
            try:
                if isinstance(getattr(self, "_theme"), str):
                    import tkinter as _tk
                    self._theme = _tk.StringVar(value=theme_name)
                else:
                    self._theme.set(theme_name)
            except: pass
            TOK = TOKENS_DARK if theme_name == "dark" else TOKENS_LIGHT
            self._tokens = TOK
            # Root
            try:
                self.root.configure(bg=TOK["bg"])
            except Exception:
                pass
            # Notebook — 1000000000% bättre: större, tydligare, hover
            style.configure("TNotebook", background=TOK["bg"], borderwidth=0, tabmargins=[4,6,4,0])
            style.configure("TNotebook.Tab", padding=[14, 10], font=("TkDefaultFont", 11, "bold"), background=TOK["bg2"], foreground=TOK["text"], borderwidth=0, focuscolor=TOK["bg"])
            style.map("TNotebook.Tab", background=[("selected", TOK["surface"]), ("active", TOK["bg3"])], foreground=[("selected", TOK["text"]), ("active", TOK["text"])], expand=[("selected", [1,1,1,0])])
            # Knappar — 1000000000% bättre: 44px touch-target, fokus-ring, tydlig hierarchy
            style.configure("TButton", padding=[14, 9], font=("TkDefaultFont", 10, "bold"), background=TOK["surface"], foreground=TOK["text"], borderwidth=1, relief="flat", bordercolor=TOK["border"], focusthickness=1, focuscolor=TOK["accent"])
            style.map("TButton", background=[("active", TOK["bg3"]), ("pressed", TOK["border2"]), ("disabled", "#D1D5DB")], foreground=[("disabled", "#6B7280")], bordercolor=[("focus", TOK["accent"])])  # GRÅ
            style.configure("Accent.TButton", padding=[14, 8], font=("TkDefaultFont", 10, "bold"), background=TOK["accent"], foreground="white", borderwidth=0)
            style.map("Accent.TButton", background=[("active", TOK["accent2"]), ("pressed", "#3A9BE6"), ("disabled", "#9CA3AF")], foreground=[("disabled", "#FFFFFF"), ("active", "white")])  # GRÅ när skannar
            style.configure("Success.TButton", padding=[14, 8], font=("TkDefaultFont", 10, "bold"), background=TOK["ok"], foreground="white", borderwidth=0)
            style.map("Success.TButton", background=[("active", TOK["ok2"]), ("pressed", "#1E8449")])
            style.configure("Danger.TButton", background=TOK["err"], foreground="white", font=("TkDefaultFont", 9, "bold"))
            style.map("Danger.TButton", background=[("active", "#E74C3C")])
            style.configure("Ghost.TButton", background=TOK["bg"], foreground=TOK["text2"], borderwidth=0)
            style.map("Ghost.TButton", background=[("active", TOK["bg2"])], foreground=[("active", TOK["text"])])
            # LabelFrame — 1000000000% bättre: luft, tydlig titel, rundad känsla via padding
            style.configure("TLabelframe", background=TOK["bg"], borderwidth=1, relief="flat", bordercolor=TOK["border"], lightcolor=TOK["surface"], darkcolor=TOK["border"])
            style.configure("TLabelframe.Label", background=TOK["bg"], foreground=TOK["text"], font=("TkDefaultFont", 10, "bold"), padding=[6,2])
            # Entry/Spinbox/Combobox — större, tydligare fokus
            # All text tydlig i alla lägen — tvinga vit fältbakgrund + svart text för tydlighet mörk/ljus
            style.configure("TEntry", fieldbackground="#FFFFFF", background="#FFFFFF", bordercolor=TOK["border"], lightcolor=TOK["accent"], darkcolor=TOK["border"], padding=6, borderwidth=1, relief="flat", foreground="#000000", font=("TkDefaultFont", 10, "bold"))
            style.map("TEntry", bordercolor=[("focus", TOK["accent"])], lightcolor=[("focus", TOK["accent"])], foreground=[("readonly", "#000000")], fieldbackground=[("readonly", "#FFFFFF")])
            style.configure("TSpinbox", fieldbackground="#FFFFFF", background="#FFFFFF", foreground="#000000", arrowsize=12, font=("TkDefaultFont", 10, "bold"))
            style.map("TSpinbox", fieldbackground=[("readonly", "#FFFFFF")], foreground=[("readonly", "#000000")])
            style.configure("TCombobox", fieldbackground="#FFFFFF", background="#FFFFFF", foreground="#000000", selectbackground=TOK["accent"], selectforeground="white", arrowsize=14, font=("TkDefaultFont", 10, "bold"))
            style.map("TCombobox", fieldbackground=[("readonly", "#FFFFFF"), ("!disabled", "#FFFFFF")], background=[("readonly", "#FFFFFF")], foreground=[("readonly", "#000000")], selectbackground=[("readonly", TOK["accent"])])
            # Checkbutton — större hit-area
            style.configure("TCheckbutton", background=TOK["bg"], foreground=TOK["text"], font=("TkDefaultFont", 10, "bold"), indicatorcolor=TOK["surface"], indicatorbackground=TOK["surface"], focusthickness=0)
            style.map("TCheckbutton", background=[("active", TOK["bg"] )], indicatorcolor=[("selected", TOK["accent"])], indicatorbackground=[("selected", TOK["accent"])])
            # Treeview — 1000000000% bättre: zebra, hover, selection, radhöjd 26 för touch
            # Tabell alltid vit med svart fet text — tydlig i mörk/ljus
            style.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF", foreground="#000000", rowheight=30, borderwidth=0, font=("TkDefaultFont", 10, "bold"), relief="flat")
            style.configure("Treeview.Heading", background=TOK["bg3"], foreground=TOK["text"], font=("TkDefaultFont", 9, "bold"), relief="flat", padding=[8,6])
            style.map("Treeview", background=[("selected", TOK["accent"]+"33"), ("active", TOK["bg2"])], foreground=[("selected", TOK["text"])])
            style.map("Treeview.Heading", background=[("active", TOK["border2"])])
            # Scrollbar — tunnare, modern
            style.configure("Vertical.TScrollbar", background=TOK["border"], troughcolor=TOK["bg"], bordercolor=TOK["bg"], arrowcolor=TOK["text3"], gripcount=0, relief="flat", width=10)
            style.map("Vertical.TScrollbar", background=[("active", TOK["text3"])])
            style.configure("Horizontal.TScrollbar", background=TOK["border"], troughcolor=TOK["bg"])
            # Progress — gradient-känsla, rundad trough + Canvas (fet text alltid synlig)
            style.configure("Horizontal.TProgressbar", background=TOK["accent"], troughcolor=TOK["bg2"], bordercolor=TOK["bg"], lightcolor=TOK["accent"], darkcolor=TOK["accent"], thickness=14, borderwidth=0, relief="flat")
            # Canvas-progress — uppdatera färger för fet text (svart ljust / vit mörkt)
            try:
                if hasattr(self, "_prog_canvas") and self._prog_canvas.winfo_exists():
                    is_dark_c = theme_name=="dark"
                    prog_bg_c = TOK["bg2"]
                    prog_fill_c = TOK["accent"]
                    text_c = "#FFFFFF" if is_dark_c else "#000000"
                    self._prog_canvas.configure(bg=prog_bg_c, highlightbackground=TOK["border"])
                    self._prog_canvas.itemconfig("prog_fill", fill=prog_fill_c)
                    self._prog_canvas.itemconfig("prog_text", fill=text_c, font=("TkDefaultFont", 11, "bold"))
                    # halo och text_bg
                    try:
                        halo_c2 = "black" if text_c=="#FFFFFF" else "white"
                        for item in self._prog_canvas.find_withtag("prog_text_halo"):
                            self._prog_canvas.itemconfig(item, fill=halo_c2, font=("TkDefaultFont", 11, "bold"))
                        self._prog_canvas.itemconfig("prog_text_bg", fill=prog_bg_c)
                    except: pass
                    self._prog_canvas._prog_bg_color = prog_bg_c
                    self._prog_canvas._prog_fill_color = prog_fill_c
                    self._prog_canvas._prog_text_color = text_c
                    # även status-label fet
                    if hasattr(self, "status"):
                        try:
                            self.status.configure(fg=text_c, font=("TkDefaultFont", 10, "bold"))
                        except: pass
            except Exception as _e:
                LOG.debug("canvas prog theme fel: %s", _e)
            # Separator
            style.configure("TSeparator", background=TOK["border"])
            # === 500M: BÄTTRE FONT & LAYOUT — globala typsnitt, mer luft, 44px läsbarhet ===
            try:
                # Välj bästa familj per OS — Segoe UI (Win), SF Pro (mac), Ubuntu/Cantarell (Linux)
                import platform as _pl
                fam = "Segoe UI" if _pl.system()=="Windows" else ("SF Pro Display" if _pl.system()=="Darwin" else "Ubuntu")
                # Fallback om familj saknas — Tk hanterar ändå
                for fname, fconf in [
                    ("TkDefaultFont", (fam, 10)),
                    ("TkTextFont", (fam, 10)),
                    ("TkHeadingFont", (fam, 11, "bold")),
                    ("TkCaptionFont", (fam, 9)),
                    ("TkSmallCaptionFont", (fam, 8)),
                ]:
                    try:
                        import tkinter.font as _tf
                        _f = _tf.nametofont(fname)
                        sz = fconf[1] if len(fconf)>1 else 10
                        # öka storlek för mörkt tema något (bättre läsbarhet mot mörk bakgrund)
                        if theme_name=="dark" and fname=="TkDefaultFont":
                            sz = 10
                        _f.configure(family=fconf[0], size=sz, weight=fconf[2] if len(fconf)>2 else "normal")
                    except: pass
                # Säkerställ att root använder nya fonts
                try: self.root.option_add("*Font", fconf)
                except: pass
            except: pass
            # Treeview radhöjd större för mörkt läge (mer luft)
            try:
                rh = 30 if theme_name=="dark" else 28  # 500M: luftigare rader
                style.configure("Treeview", rowheight=rh)
            except: pass
            # Statusbar — kommer stylas separat via tk.Label
            # REKURSIV UPPDATERING AV BEFINTLIGA tk-Widgets (fixar att temat "inte händer något")
            try:
                def _update_rec(w):
                    # Uppdatera vanliga tk widgets baserat på klass
                    try:
                        cls = w.winfo_class()
                        if cls in ("Frame","Labelframe","TFrame","TLabelframe"):
                            try: w.configure(bg=TOK["bg"])
                            except: pass
                        elif cls == "Label":
                            try:
                                # ALLTID FET SVART i ljust / FET VIT i mörkt — ingen otydlig text
                                is_dark_r = theme_name=="dark"
                                fg = "#FFFFFF" if is_dark_r else "#000000"
                                # Behåll accent-cirklers bg men tvinga fet text
                                cur_bg = str(w.cget("bg"))
                                # Om label har accent/ok/warn som bg, behåll bg men sätt fg vitt/svart med fet stil
                                if cur_bg.lower() in (TOK["accent"].lower(), TOK["accent2"].lower(), TOK["ok"].lower(), TOK["err"].lower(), "#ffe4c4", "#ffdab9", "#f3e8ff", "#7a3b9c"):
                                    try: w.configure(fg="white", font=("TkDefaultFont", 10, "bold"))
                                    except: pass
                                elif cur_bg in (TOKENS_LIGHT["surface"], TOKENS_DARK["surface"], "#FFFFFF", TOK["surface"], TOK["surface2"]):
                                    w.configure(bg=TOK["surface"], fg=fg, font=("TkDefaultFont", 10, "bold"))
                                else:
                                    w.configure(bg=TOK["bg"], fg=fg, font=("TkDefaultFont", 10, "bold"))
                            except: pass
                        elif cls in ("Button","TButton"):
                            try:
                                # tk.Button (tema-knappen)
                                if isinstance(w, __import__("tkinter").Button):
                                    is_accent = "Mörk" in str(w.cget("text")) or "Ljus" in str(w.cget("text"))
                                    w.configure(bg=TOK["surface"] if not is_accent else TOK["accent"], fg=TOK["text"] if not is_accent else "white", activebackground=TOK["bg2"])
                            except: pass
                        elif cls == "Text":
                            try: w.configure(bg=TOK["surface"], fg=TOK["text"], insertbackground=TOK["text"], selectbackground=TOK["accent"], selectforeground="white", font=("TkDefaultFont", 10, "bold"))
                            except: pass
                        elif cls == "Entry":
                            try:
                                is_dark_e = theme_name=="dark"
                                fg_e = "#FFFFFF" if is_dark_e else "#000000"
                                bg_e = TOK["surface"]
                                w.configure(bg=bg_e, fg=fg_e, insertbackground=fg_e, selectbackground=TOK["accent"], selectforeground="white", font=("TkDefaultFont", 10, "bold"))
                            except: pass
                        elif cls == "Canvas":
                            try: w.configure(bg=TOK["bg"])
                            except: pass
                    except: pass
                    for ch in w.winfo_children():
                        _update_rec(ch)
                _update_rec(self.root)
            except Exception as _e:
                LOG.debug("rekursiv tema-uppdatering fel: %s", _e)
            # Uppdatera specifika sparade refs (banner, stepper, status, toggle-knapp)
            try:
                # status
                if hasattr(self, "status"):
                    try: self.status.configure(bg=TOK["bg"], fg=TOK["text"])
                    except: pass
                # toggle-knapp text/färg
                try:
                    for w in self.root.winfo_children():
                        # hitta banner via top_line färg? Enklare: sök tk.Button med Mörk/Ljus
                        for c in w.winfo_children():
                            for cc in c.winfo_children():
                                for ccc in cc.winfo_children():
                                    if isinstance(ccc, __import__("tkinter").Button) and ("Mörk" in str(ccc.cget("text")) or "Ljus" in str(ccc.cget("text"))):
                                        ccc.configure(text="☀️ Ljus" if theme_name=="dark" else "🌙 Mörk", bg=TOK["surface"], fg=TOK["text"], activebackground=TOK["bg2"])
                                        break
                except: pass
                # Combobox i settings — uppdatera värde
                try:
                    if hasattr(self, "_theme"):
                        self._theme.set(theme_name)
                except: pass
            except: pass
            # Tvinga tree vit bakgrund även efter mörk theme så rader syns (fix bild 133 tom mörk)
            try:
                s = ttk.Style()
                s.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF", foreground="#1A1B26")
                s.configure("Treeview.Heading", background="#F0F0F0", foreground="#1A1B26")
                if hasattr(self, "tree") and self.tree.winfo_exists():
                    self.tree.configure(style="Treeview")
                    self.tree.update_idletasks()
                    if hasattr(self, "_empty_hint") and not self.tree.get_children():
                        self._empty_hint.place(relx=0.5, rely=0.45, anchor="center")
                        self._empty_hint.lift()
                    else:
                        try: self._empty_hint.place_forget()
                        except: pass
            except: pass
            # Loggrutan — vit på vit blir aldrig bra — tema-anpassad kontrast
            try:
                if hasattr(self, "log_text") and self.log_text.winfo_exists():
                    if theme_name == "dark":
                        self.log_text.configure(background="#0F172A", foreground="#E2E8F0", insertbackground="#38BDF8", selectbackground="#334155", selectforeground="#E2E8F0")
                        self.log_text.tag_configure("DEBUG", foreground="#94A3B8", background="#0F172A")
                        self.log_text.tag_configure("INFO", foreground="#E2E8F0", background="#0F172A")
                        self.log_text.tag_configure("WARNING", foreground="#FBBF24", background="#451A03")
                        self.log_text.tag_configure("ERROR", foreground="#F87171", background="#450A0A")
                        self.log_text.tag_configure("CRITICAL", foreground="#FDE68A", background="#7F1D1D")
                        self.log_text.tag_configure("search_hit", background="#FDE68A", foreground="#111827")
                        self.log_text.tag_configure("trace", foreground="#7DD3FC", background="#0F172A")
                    else:
                        # Ljus — hög kontrast svart på vitt, ej vit på vit
                        self.log_text.configure(background="#FFFFFF", foreground="#0F172A", insertbackground="#0F172A", selectbackground="#BFDBFE", selectforeground="#0F172A")
                        self.log_text.tag_configure("DEBUG", foreground="#475569", background="#FFFFFF")
                        self.log_text.tag_configure("INFO", foreground="#0F172A", background="#FFFFFF")
                        self.log_text.tag_configure("WARNING", foreground="#92400E", background="#FFFBEB")
                        self.log_text.tag_configure("ERROR", foreground="#B91C1C", background="#FEE2E2")
                        self.log_text.tag_configure("CRITICAL", foreground="#7F1D1D", background="#FEE2E2")
                        self.log_text.tag_configure("search_hit", background="#FDE68A", foreground="#111827")
                        self.log_text.tag_configure("trace", foreground="#0369A1", background="#FFFFFF")
            except Exception as _e:
                LOG.debug("log theme fel: %s", _e)
            # Extra: se till att dropdown-listan också är vit/svart oavsett tema
            try:
                self.root.option_add("*TCombobox*Listbox.background", "#FFFFFF")
                self.root.option_add("*TCombobox*Listbox.foreground", "#000000")
                self.root.option_add("*TCombobox*Listbox.selectBackground", TOK.get("accent","#0EA5E9"))
                self.root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")
            except: pass
            LOG.debug("500000000%% bättre theme applicerad (%s) — StringVar fix + rekursiv uppdatering", theme_name)
        except Exception as exc:
            LOG.debug("happy theme 1B misslyckades: %s", exc)

    def _build_settings(self) -> None:
        # Kompakt layout exakt som skärmbild 132 — en ruta, 4 rader + knapprad
        TOK = getattr(self, "_tokens", {"bg": "#FFFBF5", "border": "#FFE4C4", "surface": "#FFFFFF"})
        bg = TOK.get("bg", "#FFFBF5")
        outer = tk.Frame(self.root, bg=bg, bd=1, relief="solid", highlightbackground=TOK.get("border","#FFE4C4"), highlightthickness=1)
        outer.pack(fill="x", padx=8, pady=(6,4))
        tk.Label(outer, text="Inställningar", bg=outer["bg"], fg=TOK.get("text","#2B2D42"), font=("TkDefaultFont", 9, "bold")).pack(anchor="w", padx=8, pady=(6,2))
        # Rad 1: Fördröjning + token + Album blir + Goodreads blockerad?
        r1 = tk.Frame(outer, bg=outer["bg"])
        r1.pack(fill="x", padx=8, pady=2)
        tk.Label(r1, text="Fördröjning (s):", bg=r1["bg"], font=("TkDefaultFont", 9)).pack(side="left")
        ttk.Spinbox(r1, from_=0.5, to=10, increment=0.5, width=4, textvariable=self._delay).pack(side="left", padx=4)
        tk.Label(r1, text="Goodreads-token:", bg=r1["bg"], font=("TkDefaultFont", 9)).pack(side="left", padx=(12,2))
        ttk.Entry(r1, textvariable=self._token, width=26).pack(side="left", padx=4)
        ttk.Button(r1, text="Använd token", width=11, command=lambda: self._use_token() if hasattr(self, "_use_token") else None).pack(side="left", padx=4)
        tk.Label(r1, text="Album blir:", bg=r1["bg"], font=("TkDefaultFont", 9)).pack(side="left", padx=(10,2))
        ttk.Combobox(r1, textvariable=self._album, width=11, state="readonly", values=["serie, #del", "titel", "serienamn"]).pack(side="left", padx=2)
        # Goodreads blockerad länk till höger
        try:
            tk.Label(r1, text="Goodreads blockerad?", bg=r1["bg"], fg="#0a58ca", font=("TkDefaultFont", 9, "underline"), cursor="hand2").pack(side="right", padx=6)
        except: pass
        # Rad 2: Skriv serie-taggar + Lås upp via webbläsare
        r2 = tk.Frame(outer, bg=outer["bg"])
        r2.pack(fill="x", padx=8, pady=2)
        ttk.Checkbutton(r2, text="Skriv serie-taggar (TXXX:SERIES)", variable=self._series).pack(side="left")
        ttk.Checkbutton(r2, text="Lås upp via min webbläsare (Brave/Chromium) vid blockering", variable=self._auto_token).pack(side="left", padx=12)
        # Rad 3: Säkerhetskopiera + Hoppa över redan klara
        r3 = tk.Frame(outer, bg=outer["bg"])
        r3.pack(fill="x", padx=8, pady=2)
        ttk.Checkbutton(r3, text="Säkerhetskopiera (.agsbak)", variable=self._backup).pack(side="left")
        ttk.Checkbutton(r3, text="Hoppa över redan klara (historik) in (jämn volym)", variable=self._skip_done).pack(side="left", padx=12)
        # Rad 4: Outputmapp + Välj + Flytta + Öppna
        r4 = tk.Frame(outer, bg=outer["bg"])
        r4.pack(fill="x", padx=8, pady=4)
        tk.Label(r4, text="Outputmapp (Audiobookshelf):", bg=r4["bg"], font=("TkDefaultFont", 9, "bold")).pack(side="left")
        ttk.Entry(r4, textvariable=self._output, width=32).pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(r4, text="Välj...", width=7, command=self._pick_output).pack(side="left", padx=2)
        ttk.Checkbutton(r4, text="Flytta filerna — radera källan (sparar HDD)", variable=self._move, command=self._on_move_toggle if hasattr(self, "_on_move_toggle") else lambda: None).pack(side="left", padx=10)
        ttk.Button(r4, text="Öppna outputmapp", command=self._open_output).pack(side="right", padx=4)
        # Rad 5: Knappar + systray/autostart (högst 7 rader compact)
        r5 = tk.Frame(outer, bg=outer["bg"])
        r5.pack(fill="x", padx=8, pady=(2,6))
        ttk.Button(r5, text="Kontrollera tillägg", command=lambda: self._check_deps(manual=True)).pack(side="left")
        ttk.Button(r5, text="Rensa cache", command=self._clean_caches).pack(side="left", padx=6)
        # Systray + autostart — packas till höger i samma rad för compactness
        try:
            self._cb_start_tray = ttk.Checkbutton(r5, text=self._t("systray_start"), variable=self._start_to_tray, command=self._on_systray_toggle)
            self._cb_start_tray.pack(side="left", padx=(12,2))
            self._cb_min_tray = ttk.Checkbutton(r5, text=self._t("systray_minimize"), variable=self._minimize_to_tray, command=self._on_systray_toggle)
            self._cb_min_tray.pack(side="left", padx=2)
            self._systray_hint = tk.Label(r5, text="", bg=r5["bg"], fg="#8A8A9E", font=("TkDefaultFont", 8))
            self._systray_hint.pack(side="left", padx=6)
            # Autostart + notiser på höger sida
            ttk.Checkbutton(r5, text=self._t("autostart"), variable=self._autostart, command=self._on_autostart_toggle).pack(side="right", padx=2)
            ttk.Checkbutton(r5, text=self._t("notifs"), variable=self._notifs).pack(side="right", padx=2)
        except Exception as _e:
            LOG.debug("systray UI add fel: %s", _e)
        # Extra hint-rad för systray om pystray saknas
        try:
            if not hasattr(self, "_systray_hint2"):
                self._systray_hint2 = tk.Label(outer, text=self._t("systray_tip"), bg=outer["bg"], fg="#8A8A9E", font=("TkDefaultFont", 8))
                self._systray_hint2.pack(anchor="w", padx=8, pady=(0,2))
        except: pass

    def _build_scan(self, parent) -> None:
        # BÄTTRE: 4 tydliga steg — 1 Välj → 2 Skanna → 3 Granska → 4 Organisera
        TOK = getattr(self, "_tokens", {"bg": "#FFFBF5", "bg2": "#FFF4E6", "surface": "#FFFFFF", "border": "#FFE4C4"})
        bg = TOK.get("bg", "#FFFBF5")
        # Säkerställ folder finns FÖRE UI skapas (fix tidigare bug)
        if not hasattr(self, "folder") or self.folder is None:
            self.folder = tk.StringVar(value=os.path.expanduser("~/Ljudböcker"))
        # --- STEG 1 + 2 — två kort sida vid sida ---  (pack som förr — ingen grid behövs)
        top = tk.Frame(parent, bg=bg)
        top.pack(fill="x", padx=8, pady=8)
        # ① Välj importmapp
        c1 = tk.Frame(top, bg=TOK.get("surface","#FFFFFF"), bd=1, relief="solid", highlightbackground=TOK.get("border","#FFE4C4"), highlightthickness=1)
        c1.pack(side="left", fill="both", expand=True, padx=(0,6))
        tk.Label(c1, text=self._t("scan_card_choose"), bg=c1["bg"], fg=TOK.get("accent","#6EC6FF"), font=("TkDefaultFont", 9, "bold")).pack(anchor="w", padx=10, pady=(8,2))
        tk.Label(c1, text=self._t("scan_card_choose_hint"), bg=c1["bg"], fg=TOK.get("text3","#8A8A9E"), font=("TkDefaultFont", 9)).pack(anchor="w", padx=10)
        r1 = tk.Frame(c1, bg=c1["bg"])
        r1.pack(fill="x", padx=10, pady=(8,8))
        ttk.Entry(r1, textvariable=self.folder).pack(side="left", fill="x", expand=True, padx=(0,6))
        ttk.Button(r1, text="📁 Välj…", command=self._pick_folder).pack(side="left")
        # ② Skanna
        c2 = tk.Frame(top, bg=TOK.get("surface","#FFFFFF"), bd=1, relief="solid", highlightbackground=TOK.get("border","#FFE4C4"), highlightthickness=1)
        c2.pack(side="left", fill="y", padx=(6,0))
        tk.Label(c2, text=self._t("scan_card_scan"), bg=c2["bg"], fg=TOK.get("accent","#6EC6FF"), font=("TkDefaultFont", 9, "bold")).pack(anchor="w", padx=10, pady=(8,2))
        tk.Label(c2, text=self._t("scan_card_scan_hint"), bg=c2["bg"], fg=TOK.get("text3","#8A8A9E"), font=("TkDefaultFont", 9)).pack(anchor="w", padx=10)
        r2 = tk.Frame(c2, bg=c2["bg"])
        r2.pack(fill="x", padx=10, pady=(8,8))
        self.btn_scan = ttk.Button(r2, text=self._t("scan_match"), command=self.start_scan, style="Accent.TButton")  # grå när skannar
        self.btn_scan.pack(side="left")
        self.btn_csv = ttk.Button(r2, text="📊 CSV", width=7, command=self._export_csv, state="disabled")
        self.btn_csv.pack(side="left", padx=6)
        # Hint-rad
        hint = tk.Label(parent, text=self._t("scan_hint"), bg=bg, fg="#8A8A9E", font=("TkDefaultFont", 9), wraplength=900, justify="left")
        hint.pack(fill="x", padx=10, pady=(0,6))

        # Serie-tidslinje borttagen — visas i egen flik "Saknade i serie" istället (om du saknar bok ur serie i historiken)
        # Tabell och verktyg flyttade till egen flik 3. Granska — egen pack-layout (gammal beprövad, h=1 fix)
        review_parent = getattr(self, "tab_review", parent)
        # Använd pack i Granska-fliken — bottom-paneler först, sedan tree expand (som gamla fungerande)
        self.detail = tk.Text(review_parent, height=4, wrap="word", bg="#FFFFFF", fg="#000000", relief="flat", bd=1, highlightthickness=1, highlightbackground="#FFDAB9", font=("TkDefaultFont", 10, "bold"), padx=8, pady=6, spacing1=2, spacing3=4)  # FIX 2026-10-04: h=4 ger 100px mer till tabellen (var 7 → 170px detaljruta → tree bara 8px)
        self.detail.pack(fill="x", side="bottom", padx=6, pady=(0, 4))
        # ④ Organisera — tydligt grupperad verktygsrad med steg-nummer
        bottom = tk.Frame(review_parent, bg=bg, bd=1, relief="solid", highlightbackground=TOK.get("border","#FFE4C4"), highlightthickness=1)
        bottom.pack(fill="x", side="bottom", padx=6, pady=4)
        tk.Label(bottom, text=self._t("organize_header"), bg=bottom["bg"], fg=TOK.get("ok","#2ECC71"), font=("TkDefaultFont", 8, "bold")).pack(side="left", padx=8)
        ttk.Button(bottom, text=self._t("btn_show"), command=self._reveal).pack(side="left", padx=2)
        ttk.Button(bottom, text=self._t("btn_pick"), command=self._pick_candidate).pack(side="left", padx=2)
        ttk.Separator(bottom, orient="vertical").pack(side="left", fill="y", padx=6, pady=4)
        self.btn_apply = ttk.Button(bottom, text=self._t("btn_write"), command=self._apply_selected)
        self.btn_apply.pack(side="left", padx=2)
        self.btn_apply_all = ttk.Button(bottom, text=self._t("btn_write_all"), command=self._apply_green)
        self.btn_apply_all.pack(side="left", padx=2)
        ttk.Button(bottom, text=self._t("btn_merge"),
                   command=self._merge_selected).pack(side="left", padx=2)
        self.btn_dedup = ttk.Button(bottom, text=self._t("btn_dup"), command=self._find_duplicates)
        self.btn_dedup.pack(side="left", padx=2)
        ttk.Separator(bottom, orient="vertical").pack(side="left", fill="y", padx=6, pady=4)
        self.btn_org = ttk.Button(bottom, text=self._t("btn_send_selected"), command=self._organize_selected, style="Success.TButton")
        self.btn_org.pack(side="left", padx=2)
        self.btn_org_all = ttk.Button(bottom, text=self._t("btn_send_all"), command=self._organize_confirm, style="Success.TButton")
        self.btn_org_all.pack(side="left", padx=4)
        tk.Label(bottom, text=self._t("organize_hint"), bg=bottom["bg"], fg=TOK.get("text3","#8A8A9E"), font=("TkDefaultFont", 9)).pack(side="left")

        # ③ Rubrik ovanför tabellen — tydliggör steget (i Granska-fliken)
        hdr = tk.Frame(review_parent, bg=bg)
        hdr.pack(fill="x", padx=6, pady=(4,0))
        tk.Label(hdr, text=self._t("review_header"), bg=bg, fg=TOK.get("text","#2B2D42"), font=("TkDefaultFont", 9, "bold")).pack(side="left")
        tk.Label(hdr, text=self._t("review_hint"), bg=bg, fg=TOK.get("text3","#8A8A9E"), font=("TkDefaultFont", 9)).pack(side="left", padx=8)
        cols = [c[0] for c in presenter.COLUMNS]
        # Tvinga vit bakgrund även i mörkt läge så rader syns — fix mörk-blå tom yta i bild 133 + hybrid: alltid synlig
        style = ttk.Style()
        try:
            style.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF", foreground="#000000", rowheight=22)
            style.configure("Treeview.Heading", background="#F0F0F0", foreground="#000000", font=("TkDefaultFont", 9, "bold"))
            style.map("Treeview", background=[("selected", "#D9ECFF")], foreground=[("selected", "#0A1B2A")])
        except: pass
        # Tabell — FIX 2026-10-04 h=8: egen grid-container så tabellen alltid expanderar oavsett pack-ordning/detail-höjd
        # container expanderar till all ledig yta, tabellen får weight=1 → fyller hela fliken (gamla koden hade tree direkt i parent och led av detail 170px + hdr/hsb → 8px kvar)
        tree_frame = tk.Frame(review_parent, bg=bg)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=4)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=14, style="Treeview")
        for key, head, width in presenter.COLUMNS:
            self.tree.heading(key, text=head)
            w = width if width and width >= 50 else 80
            self.tree.column(key, width=w, anchor="w", stretch=True)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        # Alias för loggdiagnos (behåll review_parent för bakåtkompat men table_frame pekar på nya containern)
        table_frame = tree_frame
        self._tree_frame = tree_frame
        try:
            review_parent.update_idletasks()
            tree_frame.update_idletasks()
            self.tree.update_idletasks()
            if self.tree.winfo_height() <= 1:
                self.tree.configure(height=14)
                tree_frame.update_idletasks()
        except: pass
        for tag, col in (("ok", "#1A9E4A"), ("warn", "#E67E22"), ("blocked", "#E74C3C"),
                         ("none", "#95A5A6"), ("done", "#3498DB"), ("dup", "#9B59B6")):
            self.tree.tag_configure(tag, foreground=col)
        try:
            self.tree.tag_configure("ok", background="#E8F8F0")
            self.tree.tag_configure("dup", background="#F5EEFF", foreground="#7A3B9C")
            self.tree.tag_configure("warn", background="#FFF6E5")
            self.tree.tag_configure("blocked", background="#FDEDEC")
        except Exception:
            pass
        self._empty_hint = tk.Label(tree_frame if "tree_frame" in locals() else review_parent, text="✨ Ingen skanning än — dra en mapp hit eller klicka  ✨ Skanna & matcha  🎧\nBörja litet för snabb test, sen hela biblioteket  •  1000000000% bättre tom-läge 💖", bg=getattr(self, "_tokens", {}).get("surface", "white"), fg="#9CA3AF", font=("TkDefaultFont", 11), justify="center")
        self._empty_hint.place(relx=0.5, rely=0.45, anchor="center")
        def _toggle_empty(*_a):
            try:
                has = bool(self.tree.get_children())
                if has:
                    self._empty_hint.place_forget()
                else:
                    self._empty_hint.place(relx=0.5, rely=0.45, anchor="center")
            except Exception:
                pass
        try:
            self.tree.bind("<<TreeviewSelect>>", lambda e: (_toggle_empty(), self._show_detail(e) if hasattr(self, "_show_detail") else None), add="+")
            self.root.after(400, _toggle_empty)
        except Exception:
            pass
        # Gladare: grön får ljusgrön bakgrund, dup lila på ljus lila
        try:
            self.tree.tag_configure("ok", background="#E8F8F0", foreground="#0A7A2B", font=("TkDefaultFont", 9, "bold"))
            self.tree.tag_configure("dup", background="#F5EEFF", foreground="#7A3B9C", font=("TkDefaultFont", 9))
            self.tree.tag_configure("warn", background="#FFF6E5", foreground="#9A6A0A", font=("TkDefaultFont", 9))
            self.tree.tag_configure("blocked", background="#FDEDEC", foreground="#A93226", font=("TkDefaultFont", 9))
            self.tree.tag_configure("none", background="#FFFFFF", foreground="#5A5A5A", font=("TkDefaultFont", 9))
            self.tree.tag_configure("done", background="#EAF2FF", foreground="#2E5AAC", font=("TkDefaultFont", 9))
            self.tree.tag_configure("ignored_dup", background="#F0F0F0", foreground="#888888", font=("TkDefaultFont", 9, "italic"))
        except Exception:
            pass
        self.tree.bind("<Button-3>", self._row_menu)
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)

    def _build_manual(self, parent) -> None:
        TOK = getattr(self, "_tokens", {"bg":"#FFFBF5","text":"#2B2D42","text3":"#8A8A9E"})
        hdr = tk.Frame(parent, bg=TOK.get("bg","#FFFBF5"))
        hdr.pack(fill="x", padx=8, pady=(8,4))
        tk.Label(hdr, text=self._t("manual_header"), bg=hdr["bg"], fg=TOK.get("text","#2B2D42"), font=("TkDefaultFont", 10, "bold")).pack(side="left")
        tk.Label(hdr, text=self._t("manual_hint"), bg=hdr["bg"], fg=TOK.get("text3","#8A8A9E"), font=("TkDefaultFont", 9)).pack(side="left", padx=8)
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
        ttk.Button(bar, text=self._t("choose_file"), command=lambda: self._pick_audio(self.m_target)).pack(side="left", padx=2)
        ttk.Button(bar, text="Skriv vald träff", command=self._apply_manual).pack(side="left", padx=4)

    def _build_ocr(self, parent) -> None:
        # Inklistra text — manuell batch-matchning (tesseract helt borttaget, endast text)
        TOK = getattr(self, "_tokens", {"bg":"#FFFBF5","text":"#000000"})
        hdr = tk.Frame(parent, bg=TOK.get("bg","#FFFBF5"))
        hdr.pack(fill="x", padx=8, pady=(8,4))
        tk.Label(hdr, text="📝 Inklistra text — manuell batch", bg=hdr["bg"], fg=TOK.get("text","#000000"), font=("TkDefaultFont", 11, "bold")).pack(side="left")
        tk.Label(hdr, text="Klistra titlar (en per rad, gärna 'av Författare' under) — matchas endast mot Goodreads", bg=hdr["bg"], fg=TOK.get("text","#000000"), font=("TkDefaultFont", 10, "bold")).pack(side="left", padx=8)
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Matcha texten nedan", command=self.start_ocr_text).pack(side="left", padx=4)
        ttk.Label(top, text="— ingen bild, endast text (tesseract borttaget)", foreground="#000000", font=("TkDefaultFont", 9, "bold")).pack(side="left", padx=8)
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
            use_fallback=False,  # endast Goodreads
            use_title_bridge=True,  # svensk brygga behövs även vid endast Goodreads
        )
        self.engine = Engine(
            self.client, opts,
            on_status=lambda s: self.queue.put(("log", s)),
            on_history_hit=self._ask_history,
            fallback=None,  # endast Goodreads (ingen Storytel/BookBeat/Open Library)
            bridge=TitleBridge(),  # behåll svensk→engelsk brygga för Isprinsessan etc.
            token_fetcher=self._fetch_token,
        )
        return self.engine

    def _fetch_token(self) -> str:
        """Hämta Goodreads-token via webbläsaren; spara den i fältet + inställningarna."""
        from .browser_token import fetch_waf_token

        tok = fetch_waf_token(on_status=lambda m: self.queue.put(("log", m)))
        if tok:
            self.queue.put(("token", tok))
        return tok or ""

    def _use_token(self) -> None:
        LOG.info("knapp: Använd token")
        tok = self._token.get().strip()
        if not tok:
            messagebox.showinfo("Token", "Klistra in värdet för Goodreads-token först.")
            return
        if self.client is None:
            self._engine()
        self.client.set_browser_token(tok)
        self._save_settings(silent=True)   # krav 22: token sparas mellan körningar
        self.set_status("Token sparad — Goodreads bör fungera nu.")

    def _show_waf_help(self) -> None:
        LOG.info("knapp: Goodreads blockerad? (hjälptext)")
        messagebox.showinfo("Goodreads blockerad", presenter.GOODREADS_HELP)

    def _clean_caches(self) -> None:
        LOG.info("knapp: Rensa cache")
        from . import cleanup

        removed = cleanup.clean_caches()
        self.set_status(f"Cacherensning klar: {len(removed)} objekt bort.")
        if removed:
            messagebox.showinfo("Cache", f"Rensade {len(removed)} cachefiler/mappar.")

    def _on_close(self) -> None:
        """Krav 16+20: spara inställningar och rensa cache vid stängning.
        Om 'Minimera till systemfältet' är ikryssad och tray finns, göm till tray istället för att avsluta.
        """ 
        # Om minimera till tray är aktivt och tray finns -> göm istället för att stänga
        try:
            if bool(getattr(self, "_minimize_to_tray", None) and self._minimize_to_tray.get()):
                if systray_mod is not None and systray_mod.has_tray() and getattr(self, "_tray", None) is not None:
                    LOG.info("stäng-knapp -> göm till systray (minimize_to_tray PÅ)")
                    self._tray_hide_window()
                    return
                # Om tray önskas men inte är igång, försök starta den först
                if systray_mod is not None and systray_mod.has_tray():
                    try:
                        self._setup_tray()
                        if getattr(self, "_tray", None) is not None:
                            self._tray_hide_window()
                            return
                    except Exception:
                        pass
        except Exception as exc:
            LOG.debug("on_close tray check fel: %s", exc)
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
        # Stoppa tray innan destroy
        try:
            if getattr(self, "_tray", None) is not None:
                self._tray.stop()
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
        """100000000% bättre: erbjud att installera saknade OCH uppdatera gamla — i ETT fönster.
        Vid start (manual=False) körs kollen i bakgrunden så UI aldrig fryser (pip list --outdated kan ta 15s offline).
        Vid manuell klick visas direkt en detaljerad dialog med ☑️-lista, versioner och vad varje paket behövs för.
        Allt loggas, allt är valbart, och installationen sker med samma python som kör appen.
        """
        LOG.info("knapp: Kontrollera tillägg (manual=%s)", manual)
        from . import deps
        import threading

        def _do_check_and_show():
            # 1) Samla data — saknade + gamla (pip list --outdated)
            missing = deps.check()
            pip_missing = [d for d in missing if d.pip_pkg]
            bin_missing = [d for d in missing if not d.pip_pkg]
            try:
                outdated = deps.check_outdated()
            except Exception as exc:
                LOG.debug("check_outdated fel: %s", exc)
                outdated = []
            outdated = [t for t in outdated if t[0].pip_pkg]

            # Inget att göra?
            if not missing and not outdated:
                if manual:
                    self.queue.put(("deps_nothing", ""))
                else:
                    LOG.info("deps: allt installerat och aktuellt — tyst vid autostart")
                return

            # 100000000% bättre: erbjud ALLTID vid start om något saknas/gammalt — användaren bad explicit om det
            # (tidigare visades ej dialog för valfria pystray/plyer vid autostart — nu frågar vi snällt ändå, men med förvald bock)
            critical_missing = any(d.name in ("requests","beautifulsoup4","lxml","mutagen","rapidfuzz","Pillow","websocket-client") for d in pip_missing)
            # Auto: vi visar alltid dialog om något pip saknas eller något är gammalt — det var exakt vad användaren bad om 2026-09-30
            # Ingen tyst loggning längre för saknade/gamla vid autostart — fråga direkt via unified dialog
            # (om användaren klickar Hoppa över, loggar vi och stör inte igen förrän nästa manuella koll)
            

            # Visa samlad dialog i huvudtråden
            self.queue.put(("deps_show_dialog", (pip_missing, bin_missing, outdated, manual)))

        if manual:
            # Manuell → kör direkt men med liten "Kollar…" i status så UI känns snabbt
            self.set_status("🧩 Kollar tillägg — hämtar PyPI-versioner …")
            # Kör i tråd även vid manuell så inte UI fryser om pip är segt
            threading.Thread(target=_do_check_and_show, daemon=True).start()
        else:
            # Auto vid start → alltid i bakgrund
            threading.Thread(target=_do_check_and_show, daemon=True).start()

    def _show_deps_dialog(self, pip_missing, bin_missing, outdated, manual: bool) -> None:
        """100000000% bättre: EN dialog för både saknade och gamla — med ☑️-lista, versioner, pip-kopia-knapp och 'Välj alla'.
        All text på svenska, knappfärger glada, och allt loggas.
        """
        from . import deps
        import tkinter as tk
        from tkinter import ttk

        # Bygg Toplevel — 100000000% bättre design än två askYesNo
        win = tk.Toplevel(self.root)
        win.title("🧩 Python-tillägg — installera / uppdatera")
        self._apply_icon_to_toplevel(win)
        win.transient(self.root)
        win.grab_set()
        win.geometry("680x520")
        win.minsize(640, 420)
        # Centrera
        try:
            win.update_idletasks()
            x = self.root.winfo_rootx() + (self.root.winfo_width() - 680)//2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - 520)//2
            win.geometry(f"680x520+{max(0,x)}+{max(0,y)}")
        except Exception:
            pass

        # Header
        header = tk.Frame(win, bg="#FFF0B3")
        header.pack(fill="x")
        tk.Label(header, text="✨ Hittade tillägg att fixa ✨", bg="#FFF0B3", fg="#D35400", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", padx=12, pady=(10,2))
        sub = []
        if pip_missing:
            sub.append(f"{len(pip_missing)} saknade (behövs för att appen ska funka fullt ut)")
        if bin_missing:
            sub.append(f"{len(bin_missing)} binära")
        if outdated:
            sub.append(f"{len(outdated)} gamla (nyare finns på PyPI)")
        tk.Label(header, text=" • ".join(sub) + " — du väljer vad som ska installeras/uppdateras. Samma python som kör appen används.", bg="#FFF0B3", fg="#6B4226", wraplength=640, justify="left", font=("TkDefaultFont", 9)).pack(anchor="w", padx=12, pady=(0,8))

        # Canvas + Checkbuttons — rullningsbar lista
        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=12, pady=6)
        canvas = tk.Canvas(body, bg="white", highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        canvas.create_window((0,0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        def _on_conf(event): canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_conf)

        vars_map: dict[str, tk.BooleanVar] = {}
        row = 0
        # Saknade
        if pip_missing:
            ttk.Label(inner, text="Saknade — rekommenderas att installera:", font=("TkDefaultFont", 9, "bold"), foreground="#D35400").grid(row=row, column=0, sticky="w", pady=(6,2))
            row+=1
            for d in pip_missing:
                v = tk.BooleanVar(value=True)
                vars_map[f"miss:{d.pip_pkg}"] = v
                cb = ttk.Checkbutton(inner, variable=v, text=f"{d.name}  —  {d.needed_for}   (pip install {d.pip_pkg})")
                cb.grid(row=row, column=0, sticky="w", padx=8)
                row+=1
                ttk.Label(inner, text=f"    → {deps.install_hint(d)}", foreground="#888", font=("TkDefaultFont", 10)).grid(row=row, column=0, sticky="w", padx=28)
                row+=1
        if bin_missing:
            ttk.Label(inner, text="Binära (kan ej pip-installeras — följ länken):", font=("TkDefaultFont", 9, "bold"), foreground="#6B4226").grid(row=row, column=0, sticky="w", pady=(8,2))
            row+=1
            for d in bin_missing:
                ttk.Label(inner, text=f"• {d.name} — {d.needed_for}").grid(row=row, column=0, sticky="w", padx=8)
                row+=1
                ttk.Label(inner, text=f"   → {deps.install_hint(d)}", foreground="#1a56db", font=("TkDefaultFont", 8, "underline")).grid(row=row, column=0, sticky="w", padx=28)
                row+=1
        # Gamla
        if outdated:
            ttk.Label(inner, text="Gamla — nyare version finns:", font=("TkDefaultFont", 9, "bold"), foreground="#1a56db").grid(row=row, column=0, sticky="w", pady=(8,2))
            row+=1
            for d, cur, latest in outdated:
                v = tk.BooleanVar(value=True)
                vars_map[f"out:{d.pip_pkg}"] = v
                cb = ttk.Checkbutton(inner, variable=v, text=f"{d.name}  {cur} → {latest}  —  {d.needed_for}")
                cb.grid(row=row, column=0, sticky="w", padx=8)
                row+=1
                ttk.Label(inner, text=f"    → pip install --upgrade {d.pip_pkg}  ({cur} → {latest})", foreground="#888", font=("TkDefaultFont", 10)).grid(row=row, column=0, sticky="w", padx=28)
                row+=1

        # Välj alla / ingen + Pip-kopia
        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=12, pady=4)
        def _select_all():
            for v in vars_map.values(): v.set(True)
        def _select_none():
            for v in vars_map.values(): v.set(False)
        def _copy_pip():
            sel = []
            for k, v in vars_map.items():
                if v.get():
                    pkg = k.split(":",1)[1]
                    if k.startswith("out:"):
                        sel.append(f"pip install --upgrade {pkg}")
                    else:
                        sel.append(f"pip install {pkg}")
            txt = " && ".join(sel) if sel else "pip install -r requirements.txt"
            try:
                self.root.clipboard_clear(); self.root.clipboard_append(txt)
                self.set_status(f"Kopierade: {txt[:80]}…")
            except Exception: pass
        ttk.Button(btns, text="☑️ Välj alla", command=_select_all).pack(side="left")
        ttk.Button(btns, text="◻️ Välj ingen", command=_select_none).pack(side="left", padx=4)
        ttk.Button(btns, text="📋 Kopiera pip-kommandon", command=_copy_pip).pack(side="left", padx=8)
        ttk.Label(btns, text="Tips: avbocka det du INTE vill uppdatera", foreground="#888", font=("TkDefaultFont", 10)).pack(side="left", padx=8)

        # Footer-knappar
        footer = ttk.Frame(win)
        footer.pack(fill="x", padx=12, pady=(10,12))
        result = {"action": "cancel"}
        def _do_install():
            result["action"]="go"
            win.destroy()
        def _do_skip():
            result["action"]="skip"
            win.destroy()
        # Färgglada primärknappar — 100000000% bättre
        style = ttk.Style()
        try: style.configure("Accent.TButton", background="#6EC6FF", foreground="white")
        except Exception: pass
        ttk.Button(footer, text="🚀 Installera / uppdatera valda", command=_do_install, style="Accent.TButton").pack(side="right")
        ttk.Button(footer, text="Hoppa över", command=_do_skip).pack(side="right", padx=6)
        # Info om tesseract separat
        if bin_missing:
            ttk.Label(footer, text="ℹ️ Endast Goodreads-matchning", foreground="#888", font=("TkDefaultFont", 10)).pack(side="left")

        # Modal vänta
        self.root.wait_window(win)

        if result["action"] != "go":
            LOG.info("deps-dialog: användaren valde att hoppa över (manual=%s)", manual)
            if manual:
                # Vid manuell, visa ändå vad som finns
                if not any(v.get() for v in vars_map.values()):
                    messagebox.showinfo("Tillägg", "Inget valdes — inget installerades.\n\nDu kan öppna '🧩 Kolla tillägg' igen när du vill.\n\nTips: pip install --upgrade " + ", ".join(d.pip_pkg for d in pip_missing) if pip_missing else "Allt är redan installerat.")
            return

        # Samla valda
        to_install = [k.split(":",1)[1] for k,v in vars_map.items() if k.startswith("miss:") and v.get()]
        to_upgrade = [k.split(":",1)[1] for k,v in vars_map.items() if k.startswith("out:") and v.get()]
        if not to_install and not to_upgrade:
            messagebox.showinfo("Tillägg", "Inget valdes — inget görs.")
            return

        LOG.info("deps-dialog: installera %s, uppgradera %s", to_install, to_upgrade)
        def job():
            for pkg in to_install:
                self.queue.put(("log", f"installerar {pkg} …"))
                ok, tail = deps.install_pip(pkg)
                self.queue.put(("log", f"{'✅ klart' if ok else '❌ MISSLYCKADES'}: pip install {pkg}"))
                if not ok:
                    self.queue.put(("log", tail[:400]))
            for pkg in to_upgrade:
                cur = next((c for d,c,_ in outdated if d.pip_pkg==pkg), "?")
                latest = next((l for d,_,l in outdated if d.pip_pkg==pkg), "?")
                self.queue.put(("log", f"uppdaterar {pkg} {cur}->{latest} …"))
                ok, tail = deps.upgrade_pip(pkg)
                self.queue.put(("log", f"{'✅ uppdaterad' if ok else '❌ misslyckades'}: pip install --upgrade {pkg}"))
                if not ok:
                    self.queue.put(("log", tail[:400]))
            self.queue.put(("depsdone", ""))
        self._run_bg(job, "Installerar/uppdaterar tillägg")

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
        menubar.add_cascade(label=self._t("remember"), menu=self.mem_menu)
        self.mem_menu.config(postcommand=self._refresh_mem_menu)
        # Hjälpmeny — donation via PayPal/Ko-fi + språkval sv/en
        self.help_menu = tk.Menu(menubar, tearoff=0)
        t = STRINGS.get(self._lang.get(), STRINGS["sv"])
        menubar.add_cascade(label=t["help"], menu=self.help_menu)
        self.help_menu.add_command(label=t["guide_menu"], command=self._show_guide)
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
        m.add_command(label=self._t("save_now"), command=self._save_settings)
        m.add_separator()
        m.add_command(label=self._t("recent_import"), state="disabled")
        for d in self._recent_imports:
            m.add_command(label=f"  {d}", command=lambda v=d: self.folder.set(v))
        m.add_separator()
        m.add_command(label=self._t("recent_output"), state="disabled")
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
                         (self._autostart, "autostart"),
                         (self._start_to_tray, "start_to_tray"),
                         (self._minimize_to_tray, "minimize_to_tray"),
                         (self._notifs, "notifs"),
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
        if isinstance(data.get("theme"), str) and data.get("theme") in ("light", "dark"):
            self._theme.set(data.get("theme"))
            try:
                self._apply_happy_theme()
            except Exception:
                pass
        if isinstance(data.get("delay"), (int, float)):
            self._delay.set(float(data["delay"]))
        if data.get("album_style"):
            self._album.set(data["album_style"])
        if data.get("goodreads_token") or data.get("waf_token"):
            self._token.set(str(data.get("goodreads_token") or data.get("waf_token") or ""))
        self._recent_imports = [str(x) for x in data.get("recent_imports", [])]
        self._recent_outputs = [str(x) for x in data.get("recent_outputs", [])]
        # autostart: synka settings -> OS (Windows/Linux/macOS) vid start
        try:
            want = bool(data.get("autostart", False))
            # om filen saknade nyckeln, kolla vad OS faktiskt har och spegla i GUI
            if "autostart" not in data:
                try:
                    have = autostart_mod.is_enabled()
                    self._autostart.set(have)
                    LOG.debug("autostart: ingen nyckel i settings, OS har %s", have)
                except Exception:
                    pass
            else:
                # settings säger PÅ/AV -> se till att OS matchar (best-effort)
                try:
                    autostart_mod.sync_from_settings(want)
                except Exception as exc:
                    LOG.debug("autostart sync vid load misslyckades: %s", exc)
        except Exception:
            pass
        # systray: sätt upp efter load
        try:
            self._setup_tray()
            self._update_systray_hint()
        except Exception as exc:
            LOG.debug("systray setup vid load misslyckades: %s", exc)

    def _save_settings(self, silent: bool = False) -> None:
        from . import settings

        data = {
            "import_folder": self.folder.get(),
            "output_folder": self._output.get(),
            "write_series": self._series.get(),
            "backup": self._backup.get(),
            "replaygain": self._replaygain.get(),
            "autostart": self._autostart.get(),
            "start_to_tray": self._start_to_tray.get(),
            "minimize_to_tray": self._minimize_to_tray.get(),
            "notifs": self._notifs.get(),
            "lang": self._lang.get(),
            "theme": self._theme.get(),
            "skip_done": self._skip_done.get(),
            "auto_token": self._auto_token.get(),
            "move": self._move.get(),
            "delay": self._delay.get(),
            "album_style": self._album.get(),
            "goodreads_token": self._token.get().strip(),
            "waf_token": self._token.get().strip(),  # legacy
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

    def _on_autostart_toggle(self) -> None:
        want = bool(self._autostart.get())
        LOG.info("autostart toggle: %s", "PÅ" if want else "AV")
        try:
            ok = autostart_mod.set_enabled(want)
            if ok:
                # Spara direkt så settings.json speglar OS
                self._save_settings(silent=True)
                self.set_status(f"Autostart {'på' if want else 'av'} ({autostart_mod._launch_command()[0][:60]}…)" if want else "Autostart av")
                LOG.info("autostart %s: %s", "PÅ" if want else "AV", autostart_mod._launch_command()[0])
            else:
                raise RuntimeError("set_enabled returnerade False")
        except Exception as exc:
            LOG.warning("autostart kunde inte ändras: %s", exc)
            # Återställ checkboxen
            try:
                have = autostart_mod.is_enabled()
                self._autostart.set(have)
            except Exception:
                self._autostart.set(not want)
            try:
                import tkinter.messagebox as messagebox
                messagebox.showwarning("Autostart", f"Kunde inte ändra autostart:\n{exc}")
            except Exception:
                pass
            self.set_status("Autostart: kunde inte ändras")

    # ------------------------------------------------------------- systray
    def _setup_tray(self) -> None:
        if systray_mod is None or not systray_mod.has_tray():
            try:
                hint = "pystray saknas: pip install pystray pillow" if systray_mod else "systray saknas"
                if hasattr(self, "_systray_hint"):
                    self._systray_hint.config(text=hint)
                if hasattr(self, "_cb_start_tray"):
                    self._cb_start_tray.config(state="disabled")
                    self._cb_min_tray.config(state="disabled")
            except Exception:
                pass
            LOG.debug("systray ej tillgängligt: %s", systray_mod.tray_error() if systray_mod else "no mod")
            return
        # Aktivera/avaktivera rutorna
        try:
            if hasattr(self, "_cb_start_tray"):
                self._cb_start_tray.config(state="normal")
                self._cb_min_tray.config(state="normal")
                self._update_systray_hint()
        except Exception:
            pass
        # Starta tray om någon av rutorna är ikryssad
        want_tray = bool(self._start_to_tray.get() or self._minimize_to_tray.get())
        if want_tray:
            if self._tray is None:
                try:
                    from . import systray as _st
                    self._tray = _st.Tray(self)
                    self._tray.create()
                    self._tray.run_detached()
                    self._tray_visible = True
                    LOG.info("systray aktiverad (start_to_tray=%s minimize_to_tray=%s)", self._start_to_tray.get(), self._minimize_to_tray.get())
                    # bind minimera
                    try:
                        self.root.bind("<Unmap>", self._on_minimize, add="+")
                    except Exception:
                        pass
                except Exception as exc:
                    LOG.warning("kunde inte starta systray: %s", exc)
        else:
            # Stäng tray om ingen vill ha den
            if self._tray is not None:
                try:
                    self._tray.stop()
                except Exception:
                    pass
                self._tray = None
                self._tray_visible = False
                LOG.info("systray avaktiverad")

    def _update_systray_hint(self) -> None:
        # Uppdatera även extra hint2 om den finns
        try:
            if hasattr(self, "_systray_hint2") and self._systray_hint2.winfo_exists():
                self._systray_hint2.config(text=self._t("systray_tip"))
        except: pass
        if not hasattr(self, "_systray_hint"):
            return
        try:
            if systray_mod is None or not systray_mod.has_tray():
                self._systray_hint.config(text="pip install pystray pillow för systray")
            elif self._tray is not None and self._tray_visible:
                self._systray_hint.config(text="● ligger i systemfältet vid klockan")
            elif self._start_to_tray.get() or self._minimize_to_tray.get():
                self._systray_hint.config(text="○ systray aktiveras vid nästa start")
            else:
                self._systray_hint.config(text="")
        except Exception:
            pass

    def _on_systray_toggle(self) -> None:
        LOG.info("systray toggle: start_to_tray=%s minimize_to_tray=%s", self._start_to_tray.get(), self._minimize_to_tray.get())
        self._save_settings(silent=True)
        self._setup_tray()
        # Om start_to_tray bockades i efter autostart redan är på, uppdatera autostart-kommandot
        try:
            if self._autostart.get():
                autostart_mod.sync_from_settings(True)
        except Exception:
            pass

    def _find_duplicates(self) -> None:
        LOG.info("dubblet-sök begärd: %d förslag (fingerprint=%s)", len(self.proposals), bool(self._use_fingerprint.get()))
        if not self.proposals:
            from tkinter import messagebox
            messagebox.showinfo(self._t("dedup"), "Inga rader att jämföra — skanna först.")
            return
        use_fp = bool(self._use_fingerprint.get())
        # Kör i bakgrundstråd — fingerprint endast om användaren bett om det (opt-in)
        def job():
            try:
                hint = "🔍 Letar dubbletter (titel + ljud-fingerprint)…" if use_fp else "🔍 Letar dubbletter (titel/författare)…"
                self.queue.put(("status", hint))
                groups = fp_mod.find_duplicates_in_proposals(self.proposals, threshold=0.82, use_fingerprint=use_fp)
                self.queue.put(("dedup_done", groups))
            except Exception as exc:
                LOG.warning("dedup fel: %s", exc)
                self.queue.put(("error", f"Dublettsök fel: {exc}"))
        self._run_bg(job, "Letar dubbletter" if not use_fp else "Letar dubbletter + ljud")

    def _show_dedup_results(self, groups) -> None:
        from tkinter import messagebox
        import tkinter as tk
        from tkinter import ttk
        if not groups:
            messagebox.showinfo(self._t("dedup"), self._t("dedup_none") if self._t("dedup_none") != "dedup_none" else "Inga dubbletter hittade 🎉\n\nInga böcker delade titel/författare + ljud-fingerprint över 0.82.")
            self.set_status(self._t("dedup_status_none") if self._t("dedup_status_none") != "dedup_status_none" else "Inga dubbletter — allt ser unikt ut.")
            try:
                if bool(self._notifs.get()):
                    notif_mod.notify("Inga dubbletter 🎉", "Alla böcker är unika (titel + ljud).", timeout=4)
            except Exception:
                pass
            return
        # Markera rader som dup (lila) + status — men respektera redan ignorerade (visas ej som dup)
        dup_ids = set()
        for g in groups:
            for p in g:
                try:
                    idx = self.proposals.index(p)
                    dup_ids.add(idx)
                except ValueError:
                    pass
        for idx in dup_ids:
            try:
                iid = self.tree.get_children()[idx]
                self.tree.item(iid, tags=("dup",))
            except Exception:
                pass
        try:
            self.tree.tag_configure("dup", foreground="#7a3b9c", background="#f3e8ff")
            self.tree.tag_configure("ignored_dup", foreground="#8A8A9E", background="#F5F5F5")
        except Exception: pass
        # Bygg snygg dialog istället för enkel messagebox — med Ignorera-knapp (även över källor)
        try:
            win = tk.Toplevel(self.root)
            win.title(self._t("dedup") + " — " + str(len(groups)) + " grupper")
            self._apply_icon_to_toplevel(win)
            win.geometry("640x420")
            win.minsize(560, 340)
            try: win.transient(self.root)
            except: pass
            hdr = ttk.Frame(win)
            hdr.pack(fill="x", padx=12, pady=(12,6))
            ttk.Label(hdr, text=f"🔍 {len(groups)} dublett-grupp{'er' if len(groups)!=1 else ''} ({sum(len(g) for g in groups)} filer)", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
            ttk.Label(hdr, text=self._t("dedup_hint") if self._t("dedup_hint") != "dedup_hint" else "Samma bok hittad flera gånger — även över källor (Goodreads/BookBeat/Storytel). Markerade lila. Välj att ignorera om du vill behålla båda.", wraplength=600, foreground="#5A5A72", font=("TkDefaultFont", 10)).pack(anchor="w", pady=(2,0))
            # Lista
            frm = ttk.Frame(win)
            frm.pack(fill="both", expand=True, padx=12, pady=6)
            cols = ("nr", "bok", "källor")
            tv = ttk.Treeview(frm, columns=cols, show="headings", height=10)
            tv.heading("nr", text="#"); tv.column("nr", width=30, anchor="center")
            tv.heading("bok", text="Bok"); tv.column("bok", width=360, anchor="w")
            tv.heading("källor", text="Källor"); tv.column("källor", width=160, anchor="w")
            vsb = ttk.Scrollbar(frm, orient="vertical", command=tv.yview)
            tv.configure(yscrollcommand=vsb.set)
            tv.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            for i, g in enumerate(groups, 1):
                first = g[0]
                title = getattr(first, "new_title", "") or getattr(first.audio, "group_label", "") or "?"
                author = getattr(first, "new_artist", "") or getattr(first.audio, "artist", "") or ""
                sources = ", ".join(sorted(set(getattr(p, "source", "?") or "?" for p in g)))
                if not sources.strip(): sources = "okänd källa"
                # visa även antal och cross-source hint
                cross = " • över källor" if len(set(getattr(p, "source","") for p in g)) > 1 else ""
                tv.insert("", "end", values=(i, f"{title} — {author}"[:70], f"{sources}{cross} ({len(g)} filer)"))
            # Knappar + kvalitets-panel (import-mappen: kolla vilket ljud som är bäst)
            # Detalj-ruta för vald grupp — visar ljudkvalitet och frågar om ersätt
            detail = ttk.Frame(win)
            detail.pack(fill="x", padx=12, pady=(6,0))
            ttk.Label(detail, text=self._t("quality_info") if self._t("quality_info") != "quality_info" else "Jämför ljud — storlek, format och bitrate. Ska sämre version ersättas?", foreground="#5A5A72", font=("TkDefaultFont", 10)).pack(anchor="w")
            quality_var = tk.StringVar(value="Välj en grupp i listan för att se ljudkvalitet…")
            quality_lbl = ttk.Label(detail, textvariable=quality_var, wraplength=600, justify="left", font=("TkDefaultFont", 10), foreground="#2B2D42")
            quality_lbl.pack(anchor="w", pady=(4,0), fill="x")

            def _quality_info_for_proposal(proposal):
                """BÅTTRE: Mer träffsäker — använder audioinfo.probe (mutagen + ffprobe) för exakt bitrate/sample_rate/kanaler."""
                try:
                    label = getattr(proposal.audio, "group_label", "") or getattr(proposal, "new_title", "") or "?"
                    size = getattr(proposal, "total_size_mb", None)
                    if size is None:
                        size = getattr(proposal.audio, "size_mb", 0) or 0
                    n = len(getattr(proposal, "paths", None) or [getattr(proposal.audio, "path", "")])
                    # Använd audioinfo.probe för exakt mätning
                    bitrate = ""
                    dur = ""
                    fmt = (getattr(proposal.audio, "format", "") or "?").upper()
                    codec = ""
                    sr = ""
                    ch = ""
                    verdict = ""
                    try:
                        paths = getattr(proposal, "paths", None) or [getattr(proposal.audio, "path", "")]
                        pth = next((x for x in paths if x and __import__("os").path.exists(x)), "")
                        if pth:
                            from . import audioinfo as _ai
                            q = _ai.probe(pth)
                            if q:
                                fmt = (q.format or fmt).upper()
                                codec = q.codec or ""
                                if q.bitrate_kbps:
                                    bitrate = f"{q.bitrate_kbps} kbps"
                                if q.duration_s:
                                    sec = int(q.duration_s)
                                    dur = f"{sec//3600}h {(sec%3600)//60}m" if sec>=3600 else f"{sec//60}m {sec%60}s"
                                if q.sample_rate:
                                    sr = f"{q.sample_rate//1000} kHz" if q.sample_rate>=1000 else f"{q.sample_rate} Hz"
                                if q.channels:
                                    ch = f"{q.channels}ch" + (" (stereo)" if q.channels==2 else " (mono)" if q.channels==1 else "")
                                verdict = q.verdict or ""
                                # även storlek från probe om större noggrannhet
                                if q.size_mb and q.size_mb > 0:
                                    size = q.size_mb
                    except Exception:
                        pass
                    # bygg rik info-sträng: "M4B AAC 128 kbps • 44 kHz • stereo • 450 MB • 10h 30m • hög"
                    parts = []
                    if fmt: parts.append(fmt)
                    if codec and codec != fmt: parts.append(codec)
                    if bitrate: parts.append(bitrate)
                    if sr: parts.append(sr)
                    if ch: parts.append(ch)
                    # storlek alltid
                    parts.append(f"{float(size):.0f} MB")
                    if dur: parts.append(dur)
                    if verdict: parts.append(f"({verdict})")
                    info_str = " • ".join(parts)
                    return (label, float(size), fmt, n, bitrate, dur, codec, sr, ch, verdict, info_str)
                except Exception as exc:
                    return ("?", 0, "?", 1, "", "", "", "", "", "", "?")

            def _compare_group(group):
                """BÅTTRE: Mer träffsäker — rankar på bitrate → samplingsfrekvens → codec → storlek → filantal."""
                if len(group) < 2:
                    return (None, [], False)
                def _q(p):
                    # hämta exakt via probe
                    try:
                        paths = getattr(p, "paths", None) or [getattr(p.audio, "path", "")]
                        pth = next((x for x in paths if x and __import__("os").path.exists(x)), "")
                        if pth:
                            from . import audioinfo as _ai
                            q = _ai.probe(pth)
                            br = q.bitrate_kbps if q else 0
                            sr = q.sample_rate if q else 0
                            ch = q.channels if q else 0
                            codec_rank = {"FLAC":5, "WAV":4, "ALAC":4, "AAC":3, "M4B":3, "M4A":3, "OPUS":3, "VORBIS":2, "MP3":2, "OGG":2, "WMA":1}.get((q.codec or "").upper(), 0)
                            # fallback codec från filändelse om probe saknar
                            if codec_rank == 0:
                                fmt = (getattr(p.audio, "format","") or "").upper()
                                codec_rank = {"FLAC":5, "M4B":3, "M4A":3, "MP3":2, "OGG":2, "OPUS":3}.get(fmt, 1)
                        else:
                            br, sr, ch, codec_rank = 0,0,0,0
                            fmt = (getattr(p.audio, "format","") or "").upper()
                            codec_rank = {"FLAC":5, "M4B":3, "M4A":3, "MP3":2}.get(fmt, 1)
                    except Exception:
                        br, sr, ch, codec_rank = 0,0,0,1
                    size = getattr(p, "total_size_mb", None)
                    if size is None:
                        size = getattr(p.audio, "size_mb", 0) or 0
                    n = len(getattr(p, "paths", None) or [getattr(p.audio, "path","")])
                    # Vikt: bitrate 50%, sampring 20%, codec 15%, storlek 10%, filantal 5%
                    # Vi returnerar tuple som jämförs lexikografiskt — högst först
                    return (int(br), int(sr), int(codec_rank), round(float(size),1), -int(n), int(ch))
                sorted_g = sorted(group, key=_q, reverse=True)
                best = sorted_g[0]
                rest = sorted_g[1:]
                # kolla om best är signifikant bättre (storlek >10% större eller bättre format eller högre bitrate)
                best_q = _q(best)
                worst_q = _q(rest[-1])
                # enkel diff: om best size > worst size *1.1 eller fmt bättre eller bitrate högre
                is_better = (best_q[0] > worst_q[0]*1.1) or (best_q[1] > worst_q[1]) or (best_q[2] > worst_q[2] + 16)
                return (best, rest, is_better)

            def _update_quality_display(event=None):
                sel = tv.selection()
                if not sel:
                    quality_var.set("Välj en grupp i listan för att se ljudkvalitet…")
                    return
                try:
                    idx = tv.index(sel[0])
                    g = groups[idx] if idx < len(groups) else None
                    if not g:
                        quality_var.set("")
                        return
                    best, rest, is_better = _compare_group(g)
                    if not best:
                        quality_var.set("")
                        return
                    # bygg text
                    bl, bs, bf, bn, bbr, bdur, bcodec, bsr, bch, bverd, best_info = _quality_info_for_proposal(best)
                    # best_info redan rik (fmt • codec • bitrate • kHz • ch • MB • dur • verdict)
                    # lägg till filantal separat
                    best_info_full = best_info + f" • {bn} fil{'er' if bn!=1 else ''}"
                    lines = [f"{self._t('quality_best')}: {bl} — {best_info_full}"]
                    for p in rest:
                        wl, ws, wf, wn, wbr, wdur, wcodec, wsr, wch, wverd, winfo = _quality_info_for_proposal(p)
                        winfo_full = winfo + f" • {wn} fil{'er' if wn!=1 else ''}" 
                        lines.append(f"{self._t('quality_worse')}: {wl} — {winfo}")
                    if is_better:
                        lines.append("")
                        lines.append(self._t("quality_best_is").format(label=bl, info=best_info))
                    else:
                        lines.append("")
                        lines.append(self._t("quality_no_diff"))
                    quality_var.set("\\n".join(lines))
                except Exception as exc:
                    quality_var.set(f"Kunde inte jämföra ljud: {exc}")

            tv.bind("<<TreeviewSelect>>", _update_quality_display)

            # Första grupp auto-välj för direkt info (om bara en grupp)
            try:
                if groups and len(groups)==1:
                    # välj första raden
                    first_id = tv.get_children()[0] if tv.get_children() else None
                    if first_id:
                        tv.selection_set(first_id)
                        _update_quality_display()
            except: pass

            bar = ttk.Frame(win)
            bar.pack(fill="x", padx=12, pady=(8,12))
            def _keep_best():
                sel = tv.selection()
                if not sel:
                    messagebox.showinfo(self._t("dedup"), "Markera en grupp i listan först (klicka på raden).")
                    return
                idx = tv.index(sel[0])
                g = groups[idx] if idx < len(groups) else None
                if not g or len(g) < 2:
                    return
                best, rest, is_better = _compare_group(g)
                if not best:
                    return
                # bekräfta
                bl, bs, bf, bn, bbr, bdur, bcodec, bsr, bch, bverd, best_info = _quality_info_for_proposal(best)
                # best_info är redan komplett, använd den 
                if not messagebox.askyesno(self._t("quality_title"), self._t("quality_best_is").format(label=bl, info=best_info) + "\\n\\n" + self._t("quality_ask")):
                    return
                # markera sämre som skipped/ignorerad
                for p in rest:
                    try:
                        idx2 = self.proposals.index(p)
                        iid = self.tree.get_children()[idx2]
                        self.tree.item(iid, tags=("ignored_dup",))
                        p.status = "sämre version (ljud)"
                        p.skipped = True
                        p.note = f"Sämre ljud än {bl} ({best_info}) — skippar, behåller bästa. Frågade om ersätt."
                    except Exception:
                        p.skipped = True
                self.set_status(f"Behöll bästa ljud: {bl} — {len(rest)} sämre markerade som skip.")
                _update_quality_display()
                messagebox.showinfo(self._t("quality_title"), f"Klart — behöll {bl} ({best_info}). De sämre versionerna är nu skippade och kommer inte organiseras.\\n\\nTips: Kör 'Organisera' för att flytta bara den bästa till Audiobookshelf.")

            def _replace_worse():
                # Ersätt = behåll bästa och erbjud radera sämre filer (flytta till papperskorgen)
                sel = tv.selection()
                if not sel:
                    messagebox.showinfo(self._t("dedup"), "Markera en grupp först.")
                    return
                idx = tv.index(sel[0])
                g = groups[idx] if idx < len(groups) else None
                if not g or len(g) < 2:
                    return
                best, rest, _ = _compare_group(g)
                if not best:
                    return
                bl, bs, bf, bn, bbr, bdur, bcodec, bsr, bch, bverd, best_info = _quality_info_for_proposal(best)
                # best_info är redan komplett, använd den 
                # lista sämre filer
                worse_paths = []
                for p in rest:
                    worse_paths.extend(getattr(p, "paths", None) or [getattr(p.audio, "path", "")])
                worse_paths = [x for x in worse_paths if x]
                if not worse_paths:
                    messagebox.showinfo(self._t("quality_title"), "Hittade inga filer att ersätta för de sämre versionerna.")
                    return
                preview = "\\n".join(worse_paths[:5]) + ("\\n…" if len(worse_paths)>5 else "")
                if not messagebox.askyesno(self._t("quality_title"), f"Ersätta de sämre versionerna med bästa?\\n\\nBästa: {bl} ({best_info})\\n\\nSämre filer som kommer tas bort/ignoreras:\\n{preview}\\n\\nVälj Ja för att markera sämre som 'ersatt' (de raderas EJ automatiskt — du kan radera manuellt). Välj Nej för att bara skippa."):
                    return
                for p in rest:
                    try:
                        idx2 = self.proposals.index(p)
                        iid = self.tree.get_children()[idx2]
                        self.tree.item(iid, tags=("ignored_dup",))
                        p.status = "ersatt — sämre ljud"
                        p.skipped = True
                        p.note = f"Ersatt av {bl} ({best_info}) — sämre ljud. Filen ligger kvar i import-mappen men ignoreras."
                    except Exception:
                        p.skipped = True
                self.set_status(f"Ersatt {len(rest)} sämre version(er) med {bl} — markera/import-mappen rensas manuellt om du vill.")
                messagebox.showinfo(self._t("quality_title"), f"Klart — {bl} behållen. {len(worse_paths)} sämre filer är nu markerade som ersatta (skippade).\\n\\nDe ligger kvar i import-mappen — radera dem manuellt om du vill spara plats.")
                _update_quality_display()

            def _ignore_selected():
                sel = tv.selection()
                if not sel:
                    messagebox.showinfo(self._t("dedup"), "Markera en eller flera rader i listan först.")
                    return
                idxs = [tv.index(i) for i in sel]
                to_ignore = [groups[i] for i in idxs if i < len(groups)]
                # även "ignorera alla" om ingen markering? vi kör valda
                self._ignore_dup_groups(to_ignore)
                win.destroy()
            def _ignore_all():
                if messagebox.askyesno(self._t("dedup"), "Ignorera alla visade dubbletter? De kommer inte flaggas igen (även över källor)."):
                    self._ignore_dup_groups(groups)
                    win.destroy()
            def _show_ignored():
                try:
                    from .ignore import load_ignored
                    ign = load_ignored()
                    if not ign:
                        messagebox.showinfo("Ignorerade", "Inga ignorerade dubbletter ännu.")
                    else:
                        messagebox.showinfo("Ignorerade", f"{len(ign)} ignorerade nycklar:\\n" + "\\n".join(list(ign)[:20]) + ("\\n…" if len(ign)>20 else ""))
                except Exception as exc:
                    messagebox.showinfo("Ignorerade", f"Fel: {exc}")
            ttk.Button(bar, text=self._t("quality_keep_best"), command=_keep_best).pack(side="left")
            ttk.Button(bar, text=self._t("quality_replace"), command=_replace_worse).pack(side="left", padx=6)
            ttk.Button(bar, text="🙈 Ignorera valda", command=_ignore_selected).pack(side="left", padx=6)
            ttk.Button(bar, text="🙈 Ignorera alla", command=_ignore_all).pack(side="left", padx=6)
            ttk.Button(bar, text="👁️ Visa ignorerade", command=_show_ignored).pack(side="left", padx=6)
            ttk.Button(bar, text="Stäng", command=win.destroy).pack(side="right")
            ttk.Button(bar, text="🧹 Rensa ignorerade", command=lambda: self._clear_ignored_dup()).pack(side="right", padx=6)
            win.grab_set()
            self.root.wait_window(win)
        except Exception as exc:
            LOG.debug("dedup dialog fel, fallback: %s", exc)
            lines = []
            for i, g in enumerate(groups[:6], 1):
                titles = " ↔ ".join(f"{getattr(p.audio, 'group_label', '')} ({getattr(p, 'new_title', '')})" for p in g[:3])
                lines.append(f"{i}. {titles} — {len(g)} filer")
            if len(groups) > 6:
                lines.append(f"… och {len(groups)-6} grupper till")
            msg = f"Hittade {len(groups)} dublett-grupp{'er' if len(groups)!=1 else ''} ({sum(len(g) for g in groups)} filer):\\n\\n" + "\\n".join(lines) + "\\n\\nRaderna är markerade lila. Högerklicka → 'Kopiera titel' / 'Öppna i filhanterare' för att rensa."
            messagebox.showinfo(self._t("dedup"), msg)
        self.set_status(f"Dubbletter: {len(groups)} grupper, {sum(len(g) for g in groups)} filer markerade lila — välj Ignorera för att slippa varningen (även över källor)")
        try:
            if bool(self._notifs.get()):
                notif_mod.notify(f"🔍 {len(groups)} dublett-grupp{'er' if len(groups)!=1 else ''}", f"{sum(len(g) for g in groups)} filer delar titel/ljud. Markerats lila.", timeout=6)
        except Exception:
            pass
        LOG.info("dedup klar: %d grupper", len(groups))

    def _ignore_dup_groups(self, groups) -> None:
        """Lägg till gruppernas nycklar i ignore-listan och markera rader som ignorerade. Robust cross-source."""
        try:
            from .ignore import add_ignored_proposal
            added = 0
            for g in groups:
                for p in g:
                    from .ignore import dup_keys_for_proposal
                    keys = dup_keys_for_proposal(p)
                    if keys and add_ignored_proposal(p):
                        added += len(keys)
                    # markera raden visuellt
                    try:
                        idx = self.proposals.index(p)
                        iid = self.tree.get_children()[idx]
                        self.tree.item(iid, tags=("ignored_dup",))
                        p.status = "ignorerad dublett"
                        p.skipped = True
                        p.note = self._t("dedup_hint") if "ignorerad" in self._t("dedup_hint") else "ignorerad dublett — visas ej som dublett igen (även över källor)"
                    except Exception:
                        pass
            self.set_status(self._t("dedup_hint") if added else f"Ignorerade {added} dublett-nycklar — de varnas inte igen (även över källor).")
            LOG.info("ignorerade dubbletter: %d nycklar", added)
            from tkinter import messagebox
            messagebox.showinfo(self._t("dedup"), self._t("dedup_hint") + f" ({added} nycklar)")
        except Exception as exc:
            LOG.warning("ignore dup fel: %s", exc)

    def _clear_ignored_dup(self) -> None:
        from tkinter import messagebox
        if not messagebox.askyesno("Rensa ignorerade", "Rensa alla ignorerade dubbletter? De kommer flaggas igen vid nästa sökning."):
            return
        try:
            from .ignore import clear_ignored
            clear_ignored()
            self.set_status("Ignorerade dubbletter rensade — nästa sökning flaggar igen.")
            messagebox.showinfo("Rensat", "Alla ignorerade dubbletter är nu borttagna.")
        except Exception as exc:
            LOG.warning("clear ignored fel: %s", exc)

    def _on_minimize(self, event=None) -> None:
        # Anropas vid <Unmap> (minimera). Om minimize_to_tray är ikryssad, göm fönstret till tray istället för aktivitetsfältet.
        if not bool(self._minimize_to_tray.get()):
            return
        if systray_mod is None or not systray_mod.has_tray() or self._tray is None:
            return
        try:
            # Endast om fönstret faktiskt är iconified/minimized
            if self.root.state() == "iconic":
                self._tray_hide_window()
        except Exception as exc:
            LOG.debug("on_minimize fel: %s", exc)

    def _tray_hide_window(self) -> None:
        try:
            self.root.withdraw()
            self._tray_visible = True
            if self._tray and self._tray.icon:
                self._tray.update_title("Audiobro — gömd i systemfältet")
            self.set_status("Gömd i systemfältet — klicka på ikonen vid klockan för att visa igen")
            LOG.info("fönster gömt till systray")
        except Exception as exc:
            LOG.debug("tray hide fel: %s", exc)

    def _tray_show_window(self) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self._tray_visible = False
            LOG.info("fönster visat från systray")
            self.set_status("Visad från systemfältet")
            # På Windows: återställ från iconic
            try:
                self.root.state("normal")
            except Exception:
                pass
        except Exception as exc:
            LOG.debug("tray show fel: %s", exc)

    def _tray_quit(self) -> None:
        LOG.info("avsluta via systray")
        try:
            if self._tray is not None:
                self._tray.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            try:
                self.root.quit()
            except Exception:
                pass
        try:
            import sys as _sys
            _sys.exit(0)
        except SystemExit:
            raise
        except Exception:
            pass

    def _maybe_start_to_tray(self) -> None:
        # Anropas efter build — om start_to_tray eller --tray flagga, starta gömd
        try:
            import sys as _sys
            want = bool(self._start_to_tray.get())
            if "--tray" in _sys.argv or "--minimized" in _sys.argv or "--systray" in _sys.argv:
                want = True
            if want:
                if systray_mod is None or not systray_mod.has_tray():
                    LOG.info("start_to_tray önskad men pystray saknas — visar fönstret ändå")
                    return
                self._setup_tray()
                # Ge Tk en chans att rita, sedan göm
                self.root.after(400, self._tray_hide_window)
                LOG.info("startar i systemfältet")
        except Exception as exc:
            LOG.debug("maybe_start_to_tray fel: %s", exc)

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
        try: self._update_stepper(4)
        except: pass
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
        TOK = getattr(self, "_tokens", {"bg":"#FFFBF5","text":"#2B2D42","text3":"#8A8A9E"})
        hdr = tk.Frame(parent, bg=TOK.get("bg","#FFFBF5"))
        hdr.pack(fill="x", padx=8, pady=(8,4))
        tk.Label(hdr, text=self._t("reco_header"), bg=hdr["bg"], fg=TOK.get("text","#2B2D42"), font=("TkDefaultFont", 10, "bold")).pack(side="left")
        tk.Label(hdr, text=self._t("reco_hint"), bg=hdr["bg"], fg=TOK.get("text3","#8A8A9E"), font=("TkDefaultFont", 9)).pack(side="left", padx=8)
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text=self._t("btn_reco"), command=self.start_recommend, style="Accent.TButton").pack(side="left")
        ttk.Label(top, text=self._t("reco_desc")).pack(side="left", padx=8)
        self.reco_text = tk.Text(parent, wrap="word", background="#FFFFFF", foreground="#000000", font=("TkDefaultFont", 10, "bold"), insertbackground="#000000")  # FET vid tema
        self.reco_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_missing(self, parent) -> None:
        """NY FLIK: Saknade böcker i serier — baserat på historiken."""
        TOK = getattr(self, "_tokens", {"bg":"#FFFBF5","text":"#000000"})
        hdr = tk.Frame(parent, bg=TOK.get("bg","#FFFBF5"))
        hdr.pack(fill="x", padx=8, pady=(8,4))
        tk.Label(hdr, text="📚 Saknade i serie", bg=hdr["bg"], fg=TOK.get("text","#000000"), font=("TkDefaultFont", 11, "bold")).pack(side="left")
        tk.Label(hdr, text="Visar luckor i serier du har i historiken — saknar du del 2 av 4?", bg=hdr["bg"], fg=TOK.get("text","#000000"), font=("TkDefaultFont", 10, "bold")).pack(side="left", padx=8)
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="🔍 Uppdatera", command=self._refresh_missing).pack(side="left")
        ttk.Button(top, text="📂 Visa serie", command=self._show_missing_detail).pack(side="left", padx=4)
        # Tree: Serie | Har | Saknar | Nästa
        cols = ("series", "author", "has", "missing", "next")
        self.missing_tree = ttk.Treeview(parent, columns=cols, show="headings", height=14)
        self.missing_tree.heading("series", text="Serie")
        self.missing_tree.column("series", width=220, anchor="w")
        self.missing_tree.heading("author", text="Författare")
        self.missing_tree.column("author", width=160, anchor="w")
        self.missing_tree.heading("has", text="Har delar")
        self.missing_tree.column("has", width=120, anchor="center")
        self.missing_tree.heading("missing", text="Saknar")
        self.missing_tree.column("missing", width=120, anchor="center")
        self.missing_tree.heading("next", text="Tips")
        self.missing_tree.column("next", width=180, anchor="w")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.missing_tree.yview)
        self.missing_tree.configure(yscrollcommand=vsb.set)
        self.missing_tree.pack(side="left", fill="both", expand=True, padx=(6,0), pady=4)
        vsb.pack(side="left", fill="y", pady=4)
        # Detaljfält — fet text alltid synlig
        self.missing_detail = tk.Text(parent, height=6, wrap="word", bg="#FFFFFF", fg="#000000", font=("TkDefaultFont", 10, "bold"), relief="flat", bd=1, highlightthickness=1, highlightbackground="#FFDAB9", padx=8, pady=6)
        self.missing_detail.pack(fill="x", padx=6, pady=(0,4))
        self.missing_detail.insert("1.0", "Välj en serie för detaljer — tips för saknade delar visas här. ✨")
        self.missing_tree.bind("<<TreeviewSelect>>", lambda e: self._show_missing_detail())
        # Fyll direkt
        try: self._refresh_missing()
        except: pass

    def _refresh_missing(self) -> None:
        """Hitta luckor i serier från historiken — t.ex. har 1,2,4 → saknar 3."""
        try:
            from collections import defaultdict
            try: hist = (self.engine or self._engine()).history.entries()
            except: hist = []
            # Samla serie -> set av nummer
            series_map: dict[str, set] = defaultdict(set)
            series_author: dict[str, str] = {}
            for e in hist:
                ser = (e.get("series") or "").strip()
                num = (e.get("number") or "").strip()
                if not ser or not num:
                    continue
                try:
                    # hantera "3" "3.5" "04"
                    n = float(num.replace(",","."))
                    if n.is_integer(): n = int(n)
                    series_map[ser].add(n)
                    if ser not in series_author:
                        series_author[ser] = e.get("author") or ""
                except: continue
            # Rensa trädet
            for iid in self.missing_tree.get_children():
                self.missing_tree.delete(iid)
            found = 0
            for ser, nums in sorted(series_map.items()):
                if len(nums) < 2:
                    continue
                nums_sorted = sorted(nums)
                # hitta luckor mellan min och max (om max-min > len-1 finns lucka)
                mn, mx = int(min(nums_sorted)), int(max(nums_sorted))
                # Om serien har stora nummer (>20) anta komplett, skippa
                if mx - mn > 20:
                    continue
                has_str = ", ".join(str(int(n) if isinstance(n,int) or n.is_integer() else n) for n in nums_sorted)
                missing = [i for i in range(mn, mx+1) if i not in nums]
                if not missing:
                    continue
                # även kolla om nästa del efter max saknas? Visa som tips om serien är pågående — men bara luckor
                miss_str = ", ".join(str(m) for m in missing)
                nxt = f"Saknar del {missing[0]}" if missing else ""
                auth = series_author.get(ser, "")
                self.missing_tree.insert("", "end", values=(ser, auth, has_str, miss_str, nxt))
                found += 1
            if found == 0:
                self.missing_detail.delete("1.0", "end")
                self.missing_detail.insert("1.0", "Inga luckor hittade — du har kompletta serier i historiken! 🎉\n\nTips: Organisera fler böcker så dyker luckor upp här automatiskt.")
            else:
                self.missing_detail.delete("1.0", "end")
                self.missing_detail.insert("1.0", f"Hittade {found} serie(s) med luckor — välj en rad för detaljer.")
        except Exception as exc:
            try:
                self.missing_detail.delete("1.0", "end")
                self.missing_detail.insert("1.0", f"Kunde inte läsa historik: {exc}")
            except: pass

    def _show_missing_detail(self) -> None:
        try:
            sel = self.missing_tree.selection()
            if not sel:
                return
            vals = self.missing_tree.item(sel[0], "values")
            ser, auth, has_str, miss_str, nxt = vals
            self.missing_detail.delete("1.0", "end")
            self.missing_detail.insert("1.0", f"Serie: {ser} — {auth}\nHar: {has_str}\nSaknar: {miss_str}\n\nTips: Sök efter '{ser} del {miss_str.split(',')[0].strip()}' i 2. Enskild titel/länk eller vänta på rekommendationer. ✨")
            # Uppdatera textfärg vid tema
            try:
                is_dark = self._theme.get()=="dark" if hasattr(self._theme, "get") else False
                fg = "#FFFFFF" if is_dark else "#000000"
                bg = "#1E293B" if is_dark else "#FFFFFF"
                self.missing_detail.configure(fg=fg, bg=bg, insertbackground=fg)
            except: pass
        except: pass

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
        TOK = getattr(self, "_tokens", {"bg":"#FFFBF5","text":"#2B2D42","text3":"#8A8A9E"})
        hdr = tk.Frame(parent, bg=TOK.get("bg","#FFFBF5"))
        hdr.pack(fill="x", padx=8, pady=(8,4))
        tk.Label(hdr, text=self._t("hist_header"), bg=hdr["bg"], fg=TOK.get("text","#2B2D42"), font=("TkDefaultFont", 10, "bold")).pack(side="left")
        tk.Label(hdr, text=self._t("hist_hint"), bg=hdr["bg"], fg=TOK.get("text3","#8A8A9E"), font=("TkDefaultFont", 9)).pack(side="left", padx=8)
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text=self._t("history_update"), command=self._refresh_history).pack(side="left")
        ttk.Button(top, text=self._t("history_open"), command=self._open_history_folder).pack(side="left", padx=4)
        ttk.Button(top, text=self._t("history_remove"), command=self._remove_history_entry).pack(side="left", padx=4)
        ttk.Button(top, text=self._t("history_clear"), command=self._clear_history).pack(side="left", padx=4)
        ttk.Button(top, text=self._t("history_refresh"), command=self._start_refresh).pack(side="left", padx=12)
        ttk.Button(top, text=self._t("history_apply"), command=self._apply_refresh).pack(side="left", padx=4)
        ttk.Label(top, text="✨ Organiserade böcker arkiveras här — de matchas aldrig om. 1000000000% tryggare ✨", foreground="#5A5A72", font=("TkDefaultFont", 8, "italic")).pack(side="left", padx=8)
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
        # 1000000000% bättre logg 1B — nivåfilter, regex, trace, JSON, stats, audit, mörk läsbar bakgrund
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="🔄 Uppdatera", command=self._reload_log).pack(side="left")
        ttk.Button(top, text=self._t("open_log"), command=self._open_log).pack(side="left", padx=4)
        ttk.Button(top, text="📋 Kopiera markerat", command=lambda: self.root.clipboard_clear() or self.root.clipboard_append(self.log_text.get("sel.first", "sel.last")) if self.log_text.tag_ranges("sel") else self.root.clipboard_append(self.log_text.get("1.0", "end-1c"))).pack(side="left", padx=4)
        ttk.Button(top, text="📋 Kopiera allt", command=lambda: (self.root.clipboard_clear(), self.root.clipboard_append(self.log_text.get("1.0", "end-1c")), self.set_status("📋 Hela loggen kopierad till urklipp"))).pack(side="left", padx=2)
        ttk.Button(top, text="💾 Exportera filtrerad", command=self._export_log).pack(side="left", padx=4)
        ttk.Button(top, text="📦 Exportera allt", command=self._export_log_all).pack(side="left", padx=2)
        ttk.Button(top, text="📊 Stats", command=self._show_log_stats).pack(side="left", padx=4)
        ttk.Button(top, text="🧹 Rensa vy", command=self._clear_log_view).pack(side="left", padx=4)
        # Rad 2 — filter
        filt = ttk.Frame(parent)
        filt.pack(fill="x", padx=6, pady=(0,4))
        ttk.Label(filt, text="🔍").pack(side="left")
        self._log_search = tk.StringVar(value="")
        ent = ttk.Entry(filt, textvariable=self._log_search, width=20)
        ent.pack(side="left", padx=2)
        ent.bind("<KeyRelease>", lambda e: self._filter_log())
        self._log_regex = tk.BooleanVar(value=False)
        ttk.Checkbutton(filt, text="regex", variable=self._log_regex, command=self._filter_log).pack(side="left", padx=4)
        ttk.Label(filt, text="Nivå:").pack(side="left", padx=(8,2))
        self._log_level = tk.StringVar(value="ALL")
        cb = ttk.Combobox(filt, textvariable=self._log_level, width=9, state="readonly",
                          values=["ALL","DEBUG","INFO","WARNING","ERROR","CRITICAL"])
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._filter_log())
        ttk.Label(filt, text="trace:").pack(side="left", padx=(8,2))
        self._log_trace = tk.StringVar(value="")
        te = ttk.Entry(filt, textvariable=self._log_trace, width=10)
        te.pack(side="left")
        te.bind("<KeyRelease>", lambda e: self._filter_log())
        self._log_paused = tk.BooleanVar(value=False)
        ttk.Checkbutton(filt, text="⏸ Paus", variable=self._log_paused).pack(side="left", padx=8)
        self._log_autoscroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(filt, text="⤓ Auto-scroll", variable=self._log_autoscroll).pack(side="left")
        self._log_json = tk.BooleanVar(value=False)
        ttk.Checkbutton(filt, text="🧾 JSON", variable=self._log_json, command=self._reload_log).pack(side="left", padx=6)
        from .logging_setup import DEFAULT_LOG as _dl, JSON_LOG as _jl
        ttk.Label(parent, text=f"📄 {_dl}  •  🧾 {_jl}", foreground="#888", font=("TkDefaultFont", 9)).pack(anchor="w", padx=8, pady=(0,2))
        # Starta med tema-anpassad logg — ljus = svart på vitt (ej vit på vit)
        _is_dark_log = False
        try:
            _is_dark_log = getattr(self, "_theme", None) and getattr(self._theme, "get", lambda: "light")() == "dark"
        except: _is_dark_log = False
        if _is_dark_log:
            bg_log, fg_log, ib, sb = "#0F172A", "#E2E8F0", "#38BDF8", "#334155"
        else:
            bg_log, fg_log, ib, sb = "#FFFFFF", "#0F172A", "#0F172A", "#BFDBFE"
        self.log_text = tk.Text(parent, wrap="none", background=bg_log, foreground=fg_log,
                                insertbackground=ib, selectbackground=sb,
                                relief="flat", bd=0, highlightthickness=0, padx=8, pady=6,
                                font=("Consolas", 9) if sys.platform.startswith("win") else ("Menlo", 9),
                                exportselection=True, undo=True)
        # Gör loggen kopierbar — högerklick + Ctrl+C/A
        self.log_text.configure(yscrollcommand=lambda *a: ysb.set(*a), xscrollcommand=lambda *a: xsb.set(*a), wrap="none", state="normal")
        ysb = ttk.Scrollbar(parent, orient="vertical", command=self.log_text.yview)
        xsb = ttk.Scrollbar(parent, orient="horizontal", command=self.log_text.xview)
        self.log_text.pack(side="left", fill="both", expand=True, padx=(8,0), pady=(0,8))
        ysb.pack(side="left", fill="y", pady=(0,8))
        xsb.pack(side="bottom", fill="x", padx=8)
        # Kopiera-meny
        try:
            menu = tk.Menu(self.log_text, tearoff=0)
            menu.add_command(label="📋 Kopiera markerat  (Ctrl+C)", command=lambda: self.root.clipboard_clear() or self.root.clipboard_append(self.log_text.get("sel.first", "sel.last")) if self.log_text.tag_ranges("sel") else None)
            menu.add_command(label="📋 Kopiera allt  (Ctrl+A)", command=lambda: (self.root.clipboard_clear(), self.root.clipboard_append(self.log_text.get("1.0", "end-1c"))))
            menu.add_separator()
            menu.add_command(label="💾 Exportera logg...", command=self._export_log_all)
            def _popup(e):
                try: menu.tk_popup(e.x_root, e.y_root)
                finally: menu.grab_release()
            self.log_text.bind("<Button-3>", _popup)
            self.log_text.bind("<Control-a>", lambda e: (self.log_text.tag_add("sel", "1.0", "end"), "break"))
            self.log_text.bind("<Control-A>", lambda e: (self.log_text.tag_add("sel", "1.0", "end"), "break"))
        except Exception as _e:
            LOG.debug("log copy menu fel: %s", _e)
        if _is_dark_log:
            self.log_text.tag_configure("DEBUG", foreground="#94A3B8", background="#0F172A")
            self.log_text.tag_configure("INFO", foreground="#E2E8F0", background="#0F172A")
            self.log_text.tag_configure("WARNING", foreground="#FBBF24", background="#451A03")
            self.log_text.tag_configure("ERROR", foreground="#F87171", background="#450A0A")
            self.log_text.tag_configure("CRITICAL", foreground="#FDE68A", background="#7F1D1D", font=("TkDefaultFont", 9, "bold"))
            self.log_text.tag_configure("search_hit", background="#FDE68A", foreground="#111827")
            self.log_text.tag_configure("trace", foreground="#7DD3FC", background="#0F172A")
        else:
            self.log_text.tag_configure("DEBUG", foreground="#475569", background="#FFFFFF")
            self.log_text.tag_configure("INFO", foreground="#0F172A", background="#FFFFFF")
            self.log_text.tag_configure("WARNING", foreground="#92400E", background="#FFFBEB")
            self.log_text.tag_configure("ERROR", foreground="#B91C1C", background="#FEE2E2")
            self.log_text.tag_configure("CRITICAL", foreground="#7F1D1D", background="#FEE2E2", font=("TkDefaultFont", 9, "bold"))
            self.log_text.tag_configure("search_hit", background="#FDE68A", foreground="#111827")
            self.log_text.tag_configure("trace", foreground="#0369A1", background="#FFFFFF")
        self._log_lines: list[str] = []
        self._log_pos = 0
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
        LOG.info("logg: uppdatera (nivå=%s sök=%r json=%s)", getattr(self, "_log_level", None) and self._log_level.get(), getattr(self, "_log_search", None) and self._log_search.get(), getattr(self, "_log_json", None) and self._log_json.get())
        self._log_pos = 0
        self.log_text.delete("1.0", "end")
        if hasattr(self, "_log_lines"):
            self._log_lines.clear()
        # 1B: stöder JSON-läge
        if getattr(self, "_log_json", None) and self._log_json.get():
            try:
                from .logging_setup import tail_json
                recs = tail_json(500)
                import json as _js
                for r in recs:
                    self._log_lines.append(_js.dumps(r, ensure_ascii=False) + "\n")
                self._filter_log()
                return
            except Exception as exc:
                LOG.debug("reload json fel: %s", exc)
        self._tail_log()
        if hasattr(self, "_filter_log"):
            try: self._filter_log()
            except Exception: pass

    def _clear_log_view(self) -> None:
        self.log_text.delete("1.0", "end")
        if hasattr(self, "_log_lines"):
            self._log_lines.clear()
        self._log_pos = 0
        LOG.info("logg-vy rensad (filen ligger kvar)")

    def _export_log(self) -> None:
        # 1B: exporterar filtrerat via logging_setup.export_logs (respekterar sök+nivå)
        from tkinter import filedialog as _fd
        dest = _fd.asksaveasfilename(defaultextension=".log", filetypes=[("Logg","*.log"),("JSONL","*.jsonl"),("Alla","*.*")], title="Exportera filtrerad logg")
        if not dest:
            return
        try:
            from .logging_setup import export_logs
            q = (self._log_search.get() or "").strip() or None
            lvl = (self._log_level.get() or "ALL").upper()
            if lvl == "ALL": lvl = None
            n = export_logs(dest, level=lvl, query=q, regex=bool(getattr(self, "_log_regex", None) and self._log_regex.get()))
            self.set_status(f"Logg exporterad ({n} rader) → {dest}")
            LOG.info("logg exporterad filtrerad till %s (%d rader)", dest, n)
        except Exception as exc:
            LOG.warning("export logg fel: %s", exc)
            self.set_status(f"Export misslyckades: {exc}")

    def _export_log_all(self) -> None:
        from tkinter import filedialog as _fd
        from .logging_setup import DEFAULT_LOG as _dl2
        import pathlib as _pl
        dest = _fd.asksaveasfilename(defaultextension=".log", filetypes=[("Logg","*.log"),("Alla","*.*")], title="Exportera hela loggen")
        if not dest:
            return
        try:
            import shutil as _sh
            _sh.copyfile(_dl2, dest)
            from .logging_setup import JSON_LOG as _jl
            if _pl.Path(_jl).exists():
                _sh.copyfile(_jl, dest + ".jsonl")
            self.set_status(f"Hel logg exporterad → {dest}")
            LOG.info("hel logg exporterad till %s", dest)
        except Exception as exc:
            LOG.warning("export hel logg fel: %s", exc)

    def _show_log_stats(self) -> None:
        try:
            from .logging_setup import stats
            s = stats()
            import tkinter as _tk
            from tkinter import ttk as _ttk
            win = _tk.Toplevel(self.root)
            win.title("📊 Loggstatistik — 1B")
            self._apply_icon_to_toplevel(win)
            win.geometry("520x380")
            try: win.transient(self.root)
            except Exception: pass
            txt = _tk.Text(win, wrap="word", padx=10, pady=10, bg="#0F172A", fg="#E2E8F0", font=("Consolas", 9))
            txt.pack(fill="both", expand=True, padx=6, pady=6)
            txt.insert("1.0", f"📄 Fil: {s['path']}\n📦 Storlek: {s['dir_human']} i {s['dir_size']} bytes  •  {s['lines']} rader\n")
            txt.insert("end", f"\n── per nivå ──\n")
            for k,v in (s.get("by_level") or {}).items():
                txt.insert("end", f"  {k:8} {v}\n")
            txt.insert("end", f"\n── per logger (topp 10) ──\n")
            for k,v in list((s.get("by_logger") or {}).items())[:10]:
                txt.insert("end", f"  {k:20} {v}\n")
            if s.get("top_errors"):
                txt.insert("end", f"\n── vanligaste fel ──\n")
                for msg,cnt in s["top_errors"][:5]:
                    txt.insert("end", f"  ({cnt}×) {msg[:90]}\n")
            txt.config(state="disabled")
            _ttk.Button(win, text="OK", command=win.destroy).pack(pady=6)
            LOG.info("logg-stats visad: %d rader", s["lines"])
        except Exception as exc:
            LOG.warning("show stats fel: %s", exc)

    def _filter_log(self) -> None:
        if not hasattr(self, "_log_lines"):
            return
        q = (self._log_search.get() or "").strip()
        lvl = (self._log_level.get() or "ALL").upper()
        trace = (self._log_trace.get() or "").strip() if hasattr(self, "_log_trace") else ""
        use_regex = bool(getattr(self, "_log_regex", None) and self._log_regex.get())
        import re as _re
        rx = None
        if use_regex and q:
            try: rx = _re.compile(q, _re.I)
            except Exception: rx = None
        self.log_text.delete("1.0", "end")
        for line in self._log_lines[-4000:]:
            if lvl != "ALL" and f" {lvl} " not in line and f" {lvl:7}" not in line:
                continue
            if trace and trace not in line:
                continue
            if q:
                if rx:
                    if not rx.search(line): continue
                elif q.lower() not in line.lower():
                    continue
            tag = "INFO"
            for cand in ("CRITICAL","ERROR","WARNING","DEBUG","INFO"):
                if f" {cand} " in line or f" {cand:7}" in line:
                    tag = cand
                    break
            start = self.log_text.index("end-1c")
            self.log_text.insert("end", line, tag)
            # highlight sökning
            if q and not rx:
                low = line.lower(); ql=q.lower()
                idx = low.find(ql)
                while idx != -1:
                    s_idx = f"{start}+{idx}c"
                    e_idx = f"{s_idx}+{len(ql)}c"
                    self.log_text.tag_add("search_hit", s_idx, e_idx)
                    idx = low.find(ql, idx+1)
            elif rx:
                for m in rx.finditer(line):
                    s_idx = f"{start}+{m.start()}c"
                    e_idx = f"{start}+{m.end()}c"
                    self.log_text.tag_add("search_hit", s_idx, e_idx)
            if trace and trace in line:
                # faint trace highlight — whole line background already, add trace tag extra
                self.log_text.tag_add("trace", start, f"{start} lineend")
        if getattr(self, "_log_autoscroll", None) and self._log_autoscroll.get():
            self.log_text.see("end")

    def _tail_log(self) -> None:
        if hasattr(self, "_log_paused") and self._log_paused.get():
            self.root.after(800, self._tail_log)
            return
        # 1B: JSON-läge läser tail_json direkt
        if getattr(self, "_log_json", None) and self._log_json.get():
            try:
                from .logging_setup import tail_json as _tj
                import json as _js
                recs = _tj(200)
                # visa bara nya — enkel: byt ut hela vyn om vi har nya
                self._log_lines = [_js.dumps(r, ensure_ascii=False) + "\n" for r in recs[-4000:]]
                self._filter_log()
            except Exception as exc:
                LOG.debug("tail json fel: %s", exc)
            self.root.after(900, self._tail_log)
            return
        from .logging_setup import DEFAULT_LOG
        try:
            with open(DEFAULT_LOG, encoding="utf-8", errors="replace") as fh:
                fh.seek(self._log_pos)
                chunk = fh.read()
                self._log_pos = fh.tell()
            if chunk:
                new_lines = chunk.splitlines(keepends=True)
                if not hasattr(self, "_log_lines"):
                    self._log_lines = []
                self._log_lines.extend(new_lines)
                if len(self._log_lines) > 8000:
                    self._log_lines = self._log_lines[-6000:]
                q = (self._log_search.get() or "").strip() if hasattr(self, "_log_search") else ""
                lvl = (self._log_level.get() or "ALL") if hasattr(self, "_log_level") else "ALL"
                trace = (self._log_trace.get() or "").strip() if hasattr(self, "_log_trace") else ""
                use_regex = bool(getattr(self, "_log_regex", None) and self._log_regex.get())
                if q or lvl != "ALL" or trace or use_regex or (getattr(self, "_log_json", None) and self._log_json.get()):
                    self._filter_log()
                else:
                    for line in new_lines:
                        tag = "INFO"
                        for cand in ("CRITICAL","ERROR","WARNING","DEBUG","INFO"):
                            if f" {cand} " in line or f" {cand:7}" in line:
                                tag = cand
                                break
                        self.log_text.insert("end", line, tag)
                    if hasattr(self, "_log_autoscroll") and self._log_autoscroll.get():
                        self.log_text.see("end")
        except OSError as exc:
            LOG.debug("tail fel: %s", exc)
        self.root.after(700, self._tail_log)

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
        # SKANNA-knappen grå + text "Skannar…" — tydligt att den jobbar
        try:
            self.btn_scan.config(state="disabled", text="⏳ Skannar…")
            # tvinga grå stil direkt (även om theme är accent)
            try: self.btn_scan.configure(style="TButton")
            except: pass
        except: pass
        for b in (self.btn_apply, self.btn_apply_all):
            try: b.config(state="disabled")
            except: pass

    def _busy_off(self) -> None:
        self._busy = False
        # Återställ Skanna-knappen från grå till accent
        try:
            self.btn_scan.config(state="normal", text=self._t("scan_match") if hasattr(self, "_t") else "✨ Skanna & matcha")
            try: self.btn_scan.configure(style="Accent.TButton")
            except: pass
        except: pass
        if self.rows:
            try: self.btn_csv.config(state="normal")
            except: pass
            try: self.btn_apply.config(state="normal")
            except: pass
            try: self.btn_apply_all.config(state="normal")
            except: pass

    # ------------------------------------------------------------- trådar
    def _run_bg(self, fn, label: str) -> None:
        """Kör fn i bakgrundstråd — 100000000% bättre: visar tydligt om jobb redan pågår."""
        if self._busy:
            self.set_status(f"{label} pågår redan — vänta…")
            LOG.warning("bakgrundsjobb %r ignorerat — redan busy", label)
            return
        self._busy_on(label)
        import threading
        def _wrap():
            try:
                fn()
            except Exception as exc:
                LOG.exception("bakgrundsjobb %r kraschade: %s", label, exc)
                try:
                    self.queue.put(("error", str(exc)))
                except Exception:
                    pass
            finally:
                try:
                    self.queue.put(("busy_off", ""))
                except Exception:
                    pass
        threading.Thread(target=_wrap, daemon=True).start()

    def _poll(self) -> None:
        """100000000% bättre: tömmer kön, hanterar ALLA meddelanden, överlever krascher."""
        import queue as _q
        try:
            while True:
                try:
                    kind, payload = self.queue.get_nowait()
                except _q.Empty:
                    break
                try:
                    if kind == "log":
                        # logga till fil + visa i status/logg-fliken
                        try:
                            LOG.info("%s", payload)
                        except Exception:
                            pass
                        # även visa i status om kort
                        if isinstance(payload, str) and len(payload) < 120:
                            try:
                                self.set_status(str(payload))
                            except Exception:
                                pass
                    elif kind == "prog":
                        # payload = (n, total, label) — FET text alltid synlig på progress-baren (svart ljust/vit mörkt)
                        try:
                            n, total, label = payload
                            pct = int(n/total*100) if total else 0
                            txt = f"{label} {n}/{total} — {pct} %"
                            self.set_status(txt)
                            # Uppdatera dold ttk progress för kompatibilitet
                            try:
                                if hasattr(self, "prog") and self.prog is not None:
                                    self.prog.config(maximum=total, value=n)
                            except: pass
                            # Uppdatera Canvas progress med fet text
                            try:
                                if hasattr(self, "_prog_canvas") and self._prog_canvas.winfo_exists():
                                    canv = self._prog_canvas
                                    # robust bredd — winfo_width kan vara 1 innan fönster ritats
                                    try:
                                        w = canv.winfo_width()
                                        if w < 50:
                                            w = canv.winfo_reqwidth()
                                        if w < 50:
                                            w = self.root.winfo_width() or 800
                                        if w < 50:
                                            w = 800
                                    except: w = 800
                                    frac = (n/total) if total else 0
                                    fill_w = int(w * max(0, min(1, frac)))
                                    canv.coords("prog_fill", 0, 0, fill_w, 32)
                                    # FET text centrerad — svart i ljust / vit i mörkt, alltid synlig
                                    is_dark_p = False
                                    try:
                                        is_dark_p = self._theme.get()=="dark" if hasattr(self._theme, "get") else str(self._theme)=="dark"
                                    except: is_dark_p = False
                                    text_c = "#FFFFFF" if is_dark_p else "#000000"
                                    halo_c = "black" if text_c=="#FFFFFF" else "white"
                                    # uppdatera halo + huvudtext — centrerad
                                    canv.coords("prog_text", w//2, 16)
                                    canv.itemconfig("prog_text", text=txt, fill=text_c, font=("TkDefaultFont", 11, "bold"))
                                    # halo
                                    try:
                                        for item in canv.find_withtag("prog_text_halo"):
                                            canv.coords(item, w//2, 16)
                                            canv.itemconfig(item, text=txt, fill=halo_c, font=("TkDefaultFont", 11, "bold"))
                                            canv.tag_lower(item, "prog_text")
                                    except: pass
                                    # text-bg rektangel (så text alltid har kontrast även över fill)
                                    try:
                                        bbox = canv.bbox("prog_text")
                                        if bbox:
                                            x1,y1,x2,y2 = bbox
                                            canv.coords("prog_text_bg", x1-8, y1-2, x2+8, y2+2)
                                            canv.itemconfig("prog_text_bg", fill=canv._prog_bg_color, outline="")
                                            canv.tag_lower("prog_text_bg", "prog_text_halo")
                                            canv.tag_lower("prog_fill", "prog_text_bg")
                                    except: pass
                                    canv.tag_raise("prog_text")
                                    canv._prog_last = (n, total, label)
                                    # Se till att canvas är synlig — pack om den råkar vara dold
                                    try:
                                        if not canv.winfo_viewable():
                                            canv.pack(fill="x", padx=2, pady=2)
                                    except: pass
                            except Exception as _e:
                                LOG.debug("canvas prog update fel: %s", _e)
                        except Exception as exc:
                            LOG.debug("poll prog krasch (förväntat i test): %s", exc)
                            continue
                    elif kind == "row":
                        try:
                            # EXHAUSTIVE: logga allt som händer — varför/ varför inte rad läggs till
                            try:
                                lbl = getattr(getattr(payload, "audio", None), "group_label", "?")
                                st = getattr(payload, "status", "?")
                                sc = getattr(getattr(payload, "match", None), "score", "?")
                                ttl = getattr(payload, "new_title", "?")
                                art = getattr(payload, "new_artist", "?")
                                src = getattr(payload, "source", "?")
                                note = (getattr(payload, "note", "") or "")[:150]
                                paths = getattr(payload, "paths", None) or [getattr(getattr(payload, "audio", None), "path", "?")]
                                LOG.info("POLL row MOTTAGEN: label=%r status=%r score=%r title=%r artist=%r source=%r note=%r paths=%d qsize=%d tree_exists=%s tree_children_före=%d", lbl, st, sc, ttl, art, src, note, len(paths), self.queue.qsize() if hasattr(self.queue, "qsize") else -1, bool(hasattr(self, "tree") and self.tree.winfo_exists()), len(self.tree.get_children()) if hasattr(self, "tree") and self.tree.winfo_exists() else -1)
                            except Exception as _e:
                                LOG.debug("POLL row log mottagen fel: %s", _e)
                            before = len(self.tree.get_children()) if hasattr(self, "tree") and self.tree.winfo_exists() else -1
                            bh = self.tree.winfo_height() if hasattr(self, "tree") and self.tree.winfo_exists() else -1
                            bv = self.tree.winfo_viewable() if hasattr(self, "tree") and hasattr(self.tree, "winfo_viewable") else "?"
                            ph = self.tree.winfo_parent() if hasattr(self, "tree") else "?"
                            LOG.debug("POLL row före _add_row: tree h=%s viewable=%s children=%s parent=%s table_frame_exists=%s", bh, bv, before, ph, bool(hasattr(self, "tree")))
                            self._add_row(payload)
                            after = len(self.tree.get_children()) if hasattr(self, "tree") and self.tree.winfo_exists() else -1
                            ah = self.tree.winfo_height() if hasattr(self, "tree") and self.tree.winfo_exists() else -1
                            av = self.tree.winfo_viewable() if hasattr(self, "tree") and hasattr(self.tree, "winfo_viewable") else "?"
                            # verifiera att raden verkligen syns
                            try:
                                iid = self._iid_of.get(id(payload), "?")
                                vals = self.tree.item(iid, "values") if hasattr(self, "tree") and self.tree.exists(iid) else "no-iid"
                                LOG.info("POLL row KLAR: label=%r iid=%r children %d->%d tree h %s->%s viewable %s vals=%r", lbl, iid, before, after, bh, ah, av, vals[:2] if isinstance(vals, (list,tuple)) else vals)
                                if after == before:
                                    LOG.warning("POLL row VARN: children ökade ej! label=%r före=%d efter=%d — insert misslyckades eller raderades direkt", lbl, before, after)
                                if ah == 1 or ah == 0:
                                    LOG.warning("POLL row VARN: tree höjd=%s (1/0) — pack/grid fel, tabellen osynlig trots insert label=%r", ah, lbl)
                                if not av:
                                    LOG.warning("POLL row VARN: tree ej viewable (winfo_viewable=0) label=%r — flik ej vald eller fönster minimerat", lbl)
                            except Exception as _e2:
                                LOG.debug("POLL row efter-log fel: %s", _e2)
                            # säkerställ att trädet målas direkt (även mitt i skanning)
                            try:
                                self.tree.update_idletasks()
                            except: pass
                        except Exception as exc:
                            LOG.warning("POLL row FEL: payload=%r exc=%s", getattr(payload, "audio", payload), exc)
                            LOG.exception("POLL row exception: %s", exc)
                    elif kind == "rowupdate":
                        try:
                            self._update_row(payload)
                        except Exception as exc:
                            LOG.debug("poll rowupdate fel: %s", exc)
                    elif kind == "status":
                        try:
                            self.set_status(str(payload))
                        except Exception:
                            pass
                    elif kind == "error":
                        try:
                            self.set_status(f"Fel: {payload}")
                            LOG.error("poll error: %s", payload)
                        except Exception:
                            pass
                    elif kind == "busy_off":
                        try:
                            self._busy_off()
                        except Exception:
                            pass
                    elif kind == "depsdone":
                        try:
                            self._deps_done()
                        except Exception as exc:
                            LOG.debug("depsdone fel: %s", exc)
                        try:
                            self._busy_off()
                        except Exception:
                            pass
                    elif kind == "deps_show_dialog":
                        try:
                            pip_missing, bin_missing, outdated, manual = payload
                            self._show_deps_dialog(pip_missing, bin_missing, outdated, manual)
                        except Exception as exc:
                            LOG.exception("deps_show_dialog fel: %s", exc)
                    elif kind == "deps_nothing":
                        try:
                            from tkinter import messagebox as _mb
                            _mb.showinfo("Tillägg", "✅ Alla tillägg är installerade och aktuella!\n\nInget saknas, inget gammalt — du är uppdaterad. 🎉")
                        except Exception:
                            pass
                    elif kind == "dedup_done":
                        try:
                            self._show_dedup_results(payload)
                        except Exception as exc:
                            LOG.debug("dedup_done fel: %s", exc)
                        try:
                            self._busy_off()
                        except Exception:
                            pass
                    elif kind == "quality_dup":
                        try:
                            groups_q = payload or []
                            # Visa dialog som jämför ljud och frågar om ersätt — import-mappen
                            def _qinfo(proposal):
                                # BÅTTRE: exakt via audioinfo.probe (mutagen+ffprobe)
                                try:
                                    label = getattr(proposal.audio, "group_label", "") or getattr(proposal, "new_title", "") or "?"
                                    size = getattr(proposal, "total_size_mb", None)
                                    if size is None:
                                        size = getattr(proposal.audio, "size_mb", 0) or 0
                                    n = len(getattr(proposal, "paths", None) or [getattr(proposal.audio, "path", "")])
                                    fmt = (getattr(proposal.audio, "format", "") or "?").upper()
                                    br = ""
                                    sr = ""
                                    codec = ""
                                    try:
                                        paths = getattr(proposal, "paths", None) or [getattr(proposal.audio, "path", "")]
                                        pth = next((x for x in paths if x and __import__("os").path.exists(x)), "")
                                        if pth:
                                            from . import audioinfo as _ai
                                            q = _ai.probe(pth)
                                            if q:
                                                fmt = (q.format or fmt).upper()
                                                codec = q.codec or ""
                                                if q.bitrate_kbps:
                                                    br = f"{q.bitrate_kbps} kbps"
                                                if q.sample_rate:
                                                    sr = f"{q.sample_rate//1000}kHz"
                                                # storlek från probe om mer exakt
                                                if q.size_mb:
                                                    size = q.size_mb
                                    except Exception:
                                        pass
                                    parts = []
                                    if fmt: parts.append(fmt)
                                    if codec and codec != fmt: parts.append(codec)
                                    if br: parts.append(br)
                                    if sr: parts.append(sr)
                                    parts.append(f"{float(size):.0f} MB")
                                    parts.append(f"{n} fil{'er' if n!=1 else ''}")
                                    info = " • ".join(parts)
                                    return (label, info, float(size), fmt, br)
                                except Exception:
                                    return ("?", "", 0, "?", "")
                            # Bygg meddelande för alla grupper
                            msgs = []
                            for g in groups_q:
                                if len(g) < 2:
                                    continue
                                # sortera så bästa först (samma som engine)
                                def _rank(p):
                                    size = getattr(p, "total_size_mb", None)
                                    if size is None:
                                        size = getattr(p.audio, "size_mb", 0) or 0
                                    fmt_rank = {"FLAC":3, "M4B":2, "M4A":2, "MP3":1}.get((getattr(p.audio, "format","") or "").upper(), 0)
                                    try:
                                        _, _, _, _, br = _qinfo(p)
                                        brv = int(br.split()[0]) if br and br.split()[0].isdigit() else 0
                                    except: brv = 0
                                    n = len(getattr(p, "paths", None) or [getattr(p.audio, "path","")])
                                    return (float(size), fmt_rank, brv, -n)
                                sg = sorted(g, key=_rank, reverse=True)
                                best = sg[0]
                                rest = sg[1:]
                                bl, bi, _, _, _ = _qinfo(best)
                                for w in rest:
                                    wl, wi, _, _, _ = _qinfo(w)
                                    msgs.append(f"• {bl} — bästa {bi} vs sämre {wl} {wi}")
                            if msgs:
                                from tkinter import messagebox as _mb
                                # visa sammanfattning och fråga
                                preview = "\\n".join(msgs[:4]) + ("\\n..." if len(msgs)>4 else "")
                                txt = f"Hittade {len(groups_q)} bok/böcker med flera versioner i import-mappen.\\n\\n" + preview + "\\n\\n" + self._t("quality_info")
                                # vi frågar direkt: vill du behålla bästa? (Ja = behåll bästa, Nej = ångra markering)
                                res = _mb.askyesnocancel(self._t("quality_title"), txt + "\\n\\nJa = Behåll bästa (sämre skippas)\\nNej = Ångra — behåll alla\\nAvbryt = Visa detaljerad dialog")
                                if res is True:
                                    # redan markerade som sämre — behåll
                                    self.set_status(f"Bästa ljud behållet — {len(msgs)} sämre version(er) skippade. Kör 'Organisera' för att flytta bara bästa.")
                                elif res is False:
                                    # ångra: återställ alla changed
                                    for g in groups_q:
                                        for p in g:
                                            if getattr(p, "status", "").startswith("sämre"):
                                                p.status = "matchad"
                                                p.skipped = False
                                                p.note = "Ångrade — behåller båda versionerna trots sämre ljud"
                                                try:
                                                    iid = self._iid_of.get(id(p))
                                                    if iid and self.tree.exists(iid):
                                                        from . import presenter
                                                        row = presenter.proposal_row(p)
                                                        self.tree.item(iid, tags=(row["tag"],), values=presenter.row_values(row))
                                                except: pass
                                    self.set_status("Ångrade — alla versioner behålls.")
                                else: # None = Avbryt → visa detaljerad dedup-dialog
                                    try:
                                        self._show_dedup_results(groups_q)
                                    except: pass
                        except Exception as exc:
                            LOG.debug("quality_dup poll fel: %s", exc)
                    elif kind == "reco":
                        try:
                            self.reco_text.insert("end", str(payload) + "\n")
                            self.reco_text.see("end")
                        except Exception:
                            pass
                    elif kind == "ocr":
                        try:
                            self.ocr_out.insert("end", str(payload) + "\n")
                            self.ocr_out.see("end")
                        except Exception:
                            pass
                    elif kind == "manual":
                        try:
                            self._show_manual(payload)
                        except Exception as exc:
                            LOG.debug("manual fel: %s", exc)
                        try:
                            self._busy_off()
                        except Exception:
                            pass
                    elif kind == "row":
                        pass
                    elif kind == "askhist":
                        try:
                            title, author, when, ev, answer = payload
                            from tkinter import messagebox as _mb
                            # Visa fråga i huvudtråden (poll körs i huvudtråden)
                            q = f"\"{title}\" av {author} är redan organiserad" + (f" ({when})" if when else "") + ".\n\nHoppa över (Ja) eller matcha på nytt (Nej)?"
                            res = _mb.askyesno("Redan klar — hoppa över?", q)
                            answer["skip"] = bool(res)
                            ev.set()
                        except Exception as exc:
                            LOG.debug("askhist fel: %s", exc)
                            try:
                                ev.set()
                            except Exception:
                                pass
                    elif kind == "token":
                        try:
                            self._token.set(str(payload))
                            self._save_settings(silent=True)
                            self.set_status("Token mottagen — sparad")
                        except Exception:
                            pass
                    elif kind == "refresh_one":
                        # Enskild refresh-proposal — lägg i historik-vyn?
                        try:
                            # Spara för _apply_refresh
                            if not hasattr(self, "_refresh_proposals"):
                                self._refresh_proposals = []
                            self._refresh_proposals.append(payload)
                        except Exception:
                            pass
                    elif kind == "refresh_done":
                        try:
                            self._refresh_proposals = payload
                            # Visa i historik? Enkelt: uppdatera status
                            n = len([p for p in payload if getattr(p, "status", "") == "behöver uppdateras"])
                            self.set_status(f"Sökte uppdateringar — {n} behöver uppdateras" if n else "Inga uppdateringar hittades")
                            self._busy_off()
                            # Uppdatera historik-trädet om behov finns — visa antal
                            try:
                                self._refresh_history()
                            except Exception:
                                pass
                        except Exception as exc:
                            LOG.debug("refresh_done fel: %s", exc)
                            try:
                                self._busy_off()
                            except Exception:
                                pass
                    elif kind == "refresh_applied":
                        try:
                            ok, fail = payload
                            self.set_status(f"Uppdaterade {ok} bok/böcker — {fail} fel" if fail else f"Uppdaterade {ok} bok/böcker ✅")
                            self._busy_off()
                        except Exception:
                            pass
                    else:
                        LOG.debug("poll okänd kind %r", kind)
                except Exception as exc:
                    LOG.exception("poll hantering %r kraschade: %s", kind, exc)
                    continue
        finally:
            try:
                self.root.after(120, self._poll)
            except Exception:
                pass

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
        # visa tom-hint igen vid ny skanning (tills första träffen)
        try:
            if hasattr(self, "_empty_hint") and self._empty_hint.winfo_exists():
                self._empty_hint.place(relx=0.5, rely=0.45, anchor="center")
                self._empty_hint.lift()
        except: pass
        # steg → 2 Skanna
        try: self._update_stepper(2)
        except: pass
        eng = self._engine()
        LOG.info("SKANNING startad: %r", root)

        self._recent_imports = settings_mod.add_recent(self._recent_imports, root)
        self._save_settings(silent=True)

        def job():
            # Visa progress direkt vid inläsning från importmappen — alltid synlig
            self.queue.put(("prog", (0, 1, "Läser importmapp…")))
            self.queue.put(("status", "📂 Läser importmapp…"))
            files = eng.scan(root, recursive=True)
            # Uppdatera progress: filer hittade
            self.queue.put(("prog", (1, 1, f"Hittade {len(files)} filer — grupperar…")))
            self.queue.put(("log", f"{len(files)} ljudfiler hittade"))
            props = []
            groups = eng.groups(files)
            # Nu matchar-fas med tydlig progress
            self.queue.put(("prog", (0, max(1, len(groups)), "Matchar mot Goodreads…")))
            for i, grp in enumerate(groups, 1):
                try:
                    LOG.info("ENGINE start match_group %d/%d: label=%r paths=%r artist=%r album=%r filer=%d", i, len(groups), getattr(grp[0], "group_label", "?") if grp else "?", [g.path for g in grp][:3], getattr(grp[0], "artist", "") if grp else "", getattr(grp[0], "album", "") if grp else "", len(grp))
                    p, _ = eng.match_group(grp)
                except Exception as exc:
                    LOG.exception("ENGINE match_group krasch %d/%d grp=%r exc=%s", i, len(groups), getattr(grp[0], "group_label", "?") if grp else "?", exc)
                    raise
                p.group_ref = grp  # type: ignore[attr-defined]
                props.append(p)
                LOG.info("ENGINE köar RAD %d/%d: label=%r status=%r score=%r title=%r artist=%r source=%r note=%r paths=%d qsize~%d", i, len(groups), p.audio.group_label, p.status, getattr(p.match, "score", "") if getattr(p, "match", None) else "", p.new_title, p.new_artist, p.source, (p.note or "")[:120], len(getattr(p, "paths", None) or [getattr(p.audio, "path", "")]), self.queue.qsize() if hasattr(self.queue, "qsize") else -1)
                try:
                    self.queue.put(("row", p))
                    LOG.debug("ENGINE put row ok %r qsize=%d", p.audio.group_label, self.queue.qsize() if hasattr(self.queue, "qsize") else -1)
                except Exception as exc:
                    LOG.exception("ENGINE put row FEL %r exc=%s", p.audio.group_label, exc)
                self.queue.put(("prog", (i, len(groups),
                                        f"Matchar — {p.audio.group_label}")))
            # krav 23: flera versioner av samma bok -> behåll den bästa + kolla ljudkvalitet
            from .engine import choose_best_versions

            changed = choose_best_versions(props)
            if changed:
                self.queue.put(("log", f"{len(changed)} sämre dubblettversioner "
                                        "markerade (bästa versionen behålls)"))
                # Extra: kolla ljudkvalitet för import-mapp dubbletter — om bästa har bättre ljud, fråga om ersätt
                try:
                    # bygg grupper för kvalitets-dialog (robust nyckel)
                    from .ignore import _robust_title_key, _robust_author_key
                    by_robust: dict[str, list] = {}
                    for pr in props:
                        if pr.skipped and pr.status.startswith("sämre"):
                            # hitta dess robusta nyckel
                            rtk = _robust_title_key(pr.new_title or pr.audio.title or "")
                            rak = _robust_author_key(pr.new_artist or pr.audio.artist or "")
                            rk = f"ta:{rtk}|{rak}" if rtk else ""
                            # hitta bästa i samma grupp (den som ej är skipped med samma rk)
                            best = next((x for x in props if not x.skipped and _robust_title_key(x.new_title or x.audio.title or "")==rtk and _robust_author_key(x.new_artist or x.audio.artist or "")==rak), None)
                            if best:
                                key = rk or f"id:{id(best)}"
                                if key not in by_robust:
                                    by_robust[key] = [best]
                                if pr not in by_robust[key]:
                                    by_robust[key].append(pr)
                    # Fallback: om by_robust tom, gruppera via changed direkt
                    if not by_robust and changed:
                        # försök gruppera changed via deras robusta nyckel och lägg till best
                        for pr in changed:
                            rtk = _robust_title_key(pr.new_title or pr.audio.title or "")
                            rak = _robust_author_key(pr.new_artist or pr.audio.artist or "")
                            best = next((x for x in props if x is not pr and not x.skipped and _robust_title_key(x.new_title or x.audio.title or "")==rtk and _robust_author_key(x.new_artist or x.audio.artist or "")==rak), None)
                            if best:
                                rk = f"ta:{rtk}|{rak}"
                                by_robust.setdefault(rk, [best])
                                if pr not in by_robust[rk]:
                                    by_robust[rk].append(pr)
                    # Filtrera bort falska dubbletter där titlarna är för olika (fix 2026-10-04)
                    try:
                        from .text import title_similarity as _ts_q, author_similarity as _as_q
                        filtered_q = []
                        for grp in dup_groups_for_quality:
                            if len(grp) < 2:
                                continue
                            base = grp[0]
                            keep = [base]
                            for cand in grp[1:]:
                                ts = _ts_q(base.new_title or base.audio.title or base.audio.group_label or "", cand.new_title or cand.audio.title or cand.audio.group_label or "")
                                if ts < 0.75:
                                    LOG.info("quality_dup skip: %r vs %r titlar olika %.2f — ej samma bok", base.new_title or base.audio.title, cand.new_title or cand.audio.title, ts)
                                    continue
                                keep.append(cand)
                            if len(keep) >= 2:
                                filtered_q.append(keep)
                        dup_groups_for_quality = filtered_q
                    except Exception as exc:
                        LOG.debug("quality_dup filter fel: %s", exc)
                    if dup_groups_for_quality:
                        LOG.info("quality_dup köar %d grupper (efter filter)", len(dup_groups_for_quality))
                        self.queue.put(("quality_dup", dup_groups_for_quality))
                    else:
                        LOG.info("quality_dup: ingen grupp kvar efter titelfilter — dialog visas ej")
                except Exception as exc:
                    try: LOG.debug("quality_dup kö-fel: %s", exc)
                    except: pass
            for p in changed:
                self.queue.put(("rowupdate", p))
            LOG.info("SKANNING klar: %d ljudfiler, %d grupper, %d förslag — tree_children=%d rows=%d proposals=%d", len(files),
                     len(groups), len(props), len(self.tree.get_children()) if hasattr(self, "tree") and self.tree.winfo_exists() else -1, len(self.rows), len(self.proposals))
            # EXHAUSTIVE slutdiagnos — varför syns/syns ej?
            try:
                ch = len(self.tree.get_children()) if hasattr(self, "tree") and self.tree.winfo_exists() else -1
                th = self.tree.winfo_height() if hasattr(self, "tree") and self.tree.winfo_exists() else -1
                tv = self.tree.winfo_viewable() if hasattr(self, "tree") and hasattr(self.tree, "winfo_viewable") else "?"
                tfh = self.tree.master.winfo_height() if hasattr(self, "tree") and self.tree.master and self.tree.master.winfo_exists() else -1
                LOG.info("SLUTDIAGNOS: tree children=%d h=%s viewable=%s table_frame h=%s rows_len=%d props_len=%d iid_map=%d", ch, th, tv, tfh, len(self.rows), len(self.proposals), len(self._iid_of))
                if ch == 0 and len(props) > 0:
                    LOG.warning("SLUTDIAGNOS VARN: 0 rader i tree trots %d förslag — alla inserts misslyckades eller raderades! Kolla POLL row FEL ovan", len(props))
                if th in (0,1):
                    LOG.warning("SLUTDIAGNOS VARN: tree höjd %s (0/1) — pack/grid fel, tabellen osynlig trots %d förslag", th, len(props))
            except Exception as _e:
                LOG.debug("slutdiagnos fel: %s", _e)
            # tvinga hint bort och tree synlig även om alla rader skippade
            try:
                self.queue.put(("log", f"KLAR: {len(props)} förslag, {len([p for p in props if p.status=='matchad'])} matchade, {len([p for p in props if p.status=='behöver koll'])} behöver koll — tree={len(self.tree.get_children()) if hasattr(self,'tree') and self.tree.winfo_exists() else '?'} rader"))
                # säkerställ att första raden triggar stepper
                if props:
                    self.queue.put(("status", f"{len(props)} rader redo — granska"))
            except: pass
        self._run_bg(job, "Skannar")

    def _force_table_visible(self, iid=None):
        """566660000% garanti — tabellen MÅSTE synas. Kallas efter varje rad."""
        try:
            # Se till att Granska-fliken är vald
            import tkinter.ttk as _ttk
            for child in self.root.winfo_children():
                if isinstance(child, _ttk.Notebook):
                    try:
                        child.select(getattr(self, "tab_review", self.tab_scan))
                    except: pass
                    break
            self.root.update_idletasks()
            if hasattr(self, "_tree_frame") and self._tree_frame.winfo_exists():
                self._tree_frame.update_idletasks()
                self._tree_frame.pack_configure(fill="both", expand=True, padx=6, pady=4)
            if hasattr(self, "tab_review") and self.tab_review.winfo_exists():
                self.tab_review.update_idletasks()
            self.tree.update_idletasks()
            h = self.tree.winfo_height() if self.tree.winfo_exists() else -1
            # Om fortfarande 8 eller <30, tvinga om — grid vs pack race vid hidden tab
            if h != -1 and h < 60:
                try:
                    # Prova att tvinga höjd via height=0 (auto) och sedan tillbaka till 14 med update
                    self.tree.configure(height=0)
                    self.tree.update_idletasks()
                    self.tree.configure(height=14)
                    if hasattr(self, "_tree_frame"):
                        self._tree_frame.grid_rowconfigure(0, weight=1)
                        self._tree_frame.grid_columnconfigure(0, weight=1)
                    self.root.update_idletasks()
                    self.tree.update_idletasks()
                    h2 = self.tree.winfo_height() if self.tree.winfo_exists() else -1
                    LOG.debug("_force_table_visible tvingad: h %s -> %s", h, h2)
                except Exception as _e:
                    LOG.debug("_force_table_visible tvingad fel: %s", _e)
            if iid and self.tree.winfo_exists():
                try:
                    self.tree.see(iid)
                    self.tree.selection_set(iid)
                    # bläddra inte bort — bara se till att den är synlig
                    self.tree.selection_remove(iid)
                except: pass
            # Final log
            try:
                rp = getattr(self, "tab_review", None)
                tf = getattr(self, "_tree_frame", None)
                LOG.info("TABLE VISIBLE CHECK: review %dx%d tree_frame %dx%d tree %dx%d viewable=%s children=%d", 
                    rp.winfo_width() if rp and rp.winfo_exists() else -1, rp.winfo_height() if rp and rp.winfo_exists() else -1,
                    tf.winfo_width() if tf and tf.winfo_exists() else -1, tf.winfo_height() if tf and tf.winfo_exists() else -1,
                    self.tree.winfo_width() if self.tree.winfo_exists() else -1, self.tree.winfo_height() if self.tree.winfo_exists() else -1,
                    self.tree.winfo_viewable() if hasattr(self.tree, "winfo_viewable") else "?", len(self.tree.get_children()) if self.tree.winfo_exists() else -1)
            except: pass
        except Exception as _e:
            LOG.debug("_force_table_visible fel: %s", _e)

    def _add_row(self, p: Proposal) -> None:
        # EXHAUSTIVE: logga allt som händer vid radinsättning — varför/varför inte
        try:
            LOG.debug("_add_row IN: label=%r status=%r score=%r title=%r artist=%r album=%r files=%r group_label=%r path=%r tree_exists=%s viewable=%s h=%s children=%s",
                      p.audio.group_label, p.status, getattr(p.match, "score", "") if getattr(p, "match", None) else "", p.new_title, p.new_artist, p.new_album, len(getattr(p, "paths", None) or [p.audio.path]), p.audio.group_label, p.audio.path, bool(self.tree.winfo_exists()) if hasattr(self, "tree") else False, bool(self.tree.winfo_viewable()) if hasattr(self, "tree") and hasattr(self.tree, "winfo_viewable") else "?", self.tree.winfo_height() if hasattr(self, "tree") and self.tree.winfo_exists() else -1, len(self.tree.get_children()) if hasattr(self, "tree") and self.tree.winfo_exists() else -1)
        except Exception as _e:
            LOG.debug("_add_row IN-logg fel: %s", _e)
        row = presenter.proposal_row(p)
        LOG.debug("_add_row presenter row: %r", {k: row.get(k) for k in ("status","label","new_title","new_artist","score","source","tag")})
        LOG.debug("_add_row row_values: %r", presenter.row_values(row))
        self.proposals.append(p)
        self.rows.append(row)
        # före insert — mät geometri
        try:
            tf = self.tree.master
            LOG.debug("_add_row före insert: tree h=%s w=%s viewable=%s parent=%s table_frame h=%s w=%s viewable=%s children=%s empty_hint_visible=%s", self.tree.winfo_height(), self.tree.winfo_width(), self.tree.winfo_viewable(), self.tree.winfo_parent(), tf.winfo_height() if tf and tf.winfo_exists() else -1, tf.winfo_width() if tf and tf.winfo_exists() else -1, tf.winfo_viewable() if tf and hasattr(tf, "winfo_viewable") else "?", len(self.tree.get_children()), bool(self._empty_hint.winfo_viewable()) if hasattr(self, "_empty_hint") and hasattr(self._empty_hint, "winfo_viewable") and self._empty_hint.winfo_exists() else "?")
        except Exception as _e:
            LOG.debug("_add_row geom före fel: %s", _e)
        try:
            iid = self.tree.insert("", "end", values=presenter.row_values(row), tags=(row["tag"],))
            LOG.debug("_add_row insert OK iid=%r values=%r tag=%r", iid, presenter.row_values(row)[:3], row.get("tag"))
        except Exception as exc:
            LOG.exception("tree insert FEL row=%r exc=%s payload_label=%r status=%r", row, exc, p.audio.group_label, p.status)
            # även dumpa tree state vid fel
            try:
                LOG.warning("tree state vid FEL: exists=%s h=%s w=%s children=%s master=%s", self.tree.winfo_exists(), self.tree.winfo_height(), self.tree.winfo_width(), len(self.tree.get_children()), self.tree.winfo_parent())
            except Exception as _e2:
                LOG.debug("tree state logg fel: %s", _e2)
            raise
        self._iid_of[id(p)] = iid
        # 100000000% bättre: göm tom-läget så rader syns direkt efter matchning — och tvinga synlighet
        try:
            if hasattr(self, "_empty_hint") and self._empty_hint.winfo_exists():
                before_hint = bool(self._empty_hint.winfo_viewable()) if hasattr(self._empty_hint, "winfo_viewable") else "?"
                self._empty_hint.place_forget()
                LOG.debug("_add_row empty_hint place_forget före_viewable=%s efter_exists=%s", before_hint, self._empty_hint.winfo_exists())
            # lyft tree över hint och säkerställ att den ritas
            try:
                self.tree.lift()
                self.tree.update_idletasks()
            except Exception as _e:
                LOG.debug("_add_row lift/update fel: %s", _e)
        except Exception as _e:
            LOG.debug("_add_row empty_hint fel: %s", _e)
        # Extra diagnos: varför h=6? Logga alla höjder i Granska-fliken och notebook
        try:
            rp = getattr(self, "tab_review", None)
            nb = None
            for child in self.root.winfo_children():
                import tkinter.ttk as _ttk
                if isinstance(child, _ttk.Notebook):
                    nb = child
                    break
            LOG.debug("HEIGHTS: root %dx%d notebook %s review %dx%d tree_frame %dx%d tree %dx%d header %dx%d hsb %dx%d detail %dx%d bottom %dx%d outer %dx%d footer %dx%d",
                self.root.winfo_width(), self.root.winfo_height(),
                f"{nb.winfo_width()}x{nb.winfo_height()}" if nb and nb.winfo_exists() else "no-nb",
                rp.winfo_width() if rp and rp.winfo_exists() else -1, rp.winfo_height() if rp and rp.winfo_exists() else -1,
                tf.winfo_width() if (tf:=getattr(self, "_tree_frame", None)) and tf.winfo_exists() else -1, tf.winfo_height() if tf and tf.winfo_exists() else -1,
                self.tree.winfo_width() if self.tree.winfo_exists() else -1, self.tree.winfo_height() if self.tree.winfo_exists() else -1,
                hdr.winfo_width() if 'hdr' in locals() and hdr.winfo_exists() else -1, hdr.winfo_height() if 'hdr' in locals() and hdr.winfo_exists() else -1,
                hsb.winfo_width() if 'hsb' in locals() and hsb.winfo_exists() else -1, hsb.winfo_height() if 'hsb' in locals() and hsb.winfo_exists() else -1,
                self.detail.winfo_width() if self.detail.winfo_exists() else -1, self.detail.winfo_height() if self.detail.winfo_exists() else -1,
                bottom.winfo_width() if 'bottom' in locals() and bottom.winfo_exists() else -1, bottom.winfo_height() if 'bottom' in locals() and bottom.winfo_exists() else -1,
                outer.winfo_width() if 'outer' in locals() and outer.winfo_exists() else -1, outer.winfo_height() if 'outer' in locals() and outer.winfo_exists() else -1,
                self._footer.winfo_width() if hasattr(self, "_footer") and self._footer.winfo_exists() else -1, self._footer.winfo_height() if hasattr(self, "_footer") and self._footer.winfo_exists() else -1,
            )
        except Exception as _e:
            LOG.debug("heights log fel: %s", _e)
        LOG.info("RAD tillagd: %s — %s [%s] %.2f iid=%r tree_h=%s viewable=%s children=%d", row.get("label"), row.get("new_title"), row.get("status"), float(row.get("score") or 0) if row.get("score") else 0.0, iid, self.tree.winfo_height() if self.tree.winfo_exists() else -1, self.tree.winfo_viewable() if hasattr(self.tree, "winfo_viewable") else "?", len(self.tree.get_children()))
        # VARFÖR INTE SYNS? — diagnostik direkt efter insert
        try:
            if self.tree.winfo_height() in (0,1):
                LOG.warning("RAD SYNS EJ? tree höjd=%s (0/1) — pack/grid ger ingen yta! table_frame h=%s w=%s viewable=%s parent=%s", self.tree.winfo_height(), self.tree.master.winfo_height() if self.tree.master and self.tree.master.winfo_exists() else -1, self.tree.master.winfo_width() if self.tree.master and self.tree.master.winfo_exists() else -1, self.tree.master.winfo_viewable() if self.tree.master and hasattr(self.tree.master, "winfo_viewable") else "?", self.tree.winfo_parent())
            if not self.tree.winfo_viewable():
                LOG.warning("RAD SYNS EJ? tree ej viewable (flik kanske ej vald) label=%r", row.get("label"))
            # kontrollera att raden verkligen ligger i trädet
            if not self.tree.exists(iid):
                LOG.warning("RAD SYNS EJ? iid %r finns ej efter insert! label=%r", iid, row.get("label"))
        except Exception as _e:
            LOG.debug("RAD diagnostik fel: %s", _e)
        self.set_status(f"{presenter.summary_text(self.rows)}")
        LOG.debug("RAD summary: %s rows=%d proposals=%d", presenter.summary_text(self.rows), len(self.rows), len(self.proposals))
        # Säkerställ att tabellen ritas direkt — tvinga update även mitt i 238-raders skanning
        try:
            self.tree.see(iid)
            self.tree.update_idletasks()
            # växla till Granska-fliken (egen flik för tabellen) — se till att den är synlig + tvinga layout
            try:
                for child in self.root.winfo_children():
                    if isinstance(child, ttk.Notebook):
                        # välj nya Granska-fliken om den finns, annars fallback till scan
                        target = getattr(self, "tab_review", self.tab_scan)
                        child.select(target)
                        break
                # Tvinga notebook att rita ny flik innan höjdmätning — annars h=6
                self.root.update_idletasks()
                if hasattr(self, "tab_review") and self.tab_review.winfo_exists():
                    self.tab_review.update_idletasks()
                LOG.debug("efter tab select: review %dx%d tree %dx%d nb %dx%d", self.tab_review.winfo_width() if self.tab_review.winfo_exists() else -1, self.tab_review.winfo_height() if self.tab_review.winfo_exists() else -1, self.tree.winfo_width() if self.tree.winfo_exists() else -1, self.tree.winfo_height() if self.tree.winfo_exists() else -1, child.winfo_width() if 'child' in locals() and child.winfo_exists() else -1, child.winfo_height() if 'child' in locals() and child.winfo_exists() else -1)
            except Exception as _e:
                LOG.debug("tab select fel: %s", _e)
            # 566660000% — tvinga synlighet även om Notebook inte hunnit rita
            try:
                self._force_table_visible(iid)
                self.root.after(200, lambda iid=iid: self._force_table_visible(iid))
                self.root.after(600, lambda iid=iid: self._force_table_visible(iid))
            except Exception as _e2:
                LOG.debug("_force_table_visible call fel: %s", _e2)
        except: pass
        # första raden → steg 3 Granska + växla flik
        if len(self.proposals) == 1:
            try:
                self._update_stepper(3)
                for child in self.root.winfo_children():
                    if isinstance(child, ttk.Notebook):
                        child.select(getattr(self, "tab_review", self.tab_scan))
                        break
            except: pass

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
        menu.add_command(label="🙈 Ignorera dublett (även över källor)", command=self._ignore_selected_dup)
        menu.add_command(label="👁️ Sluta ignorera dublett", command=self._unignore_selected_dup)
        menu.add_separator()
        menu.add_command(label="Öppna i filhanterare", command=self._reveal)
        menu.add_command(label="Kopiera titel", command=self._copy_title)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _ignore_selected_dup(self) -> None:
        sel = self._selected_proposals()
        if not sel:
            from tkinter import messagebox
            messagebox.showinfo("Ignorera", "Markera en eller flera rader först.")
            return
        # gruppera valda som en grupp att ignorera
        self._ignore_dup_groups([sel])

    def _unignore_selected_dup(self) -> None:
        sel = self._selected_proposals()
        if not sel:
            from tkinter import messagebox
            messagebox.showinfo("Sluta ignorera", "Markera en rad först.")
            return
        try:
            from .ignore import remove_ignored, dup_keys_for_proposal
            removed = 0
            for p in sel:
                keys = dup_keys_for_proposal(p)
                for k in list(keys):
                    if remove_ignored(k):
                        removed += 1
                # återställ visning
                try:
                    idx = self.proposals.index(p)
                    iid = self.tree.get_children()[idx]
                    # återställ till original tag baserat på status
                    from . import presenter
                    row = presenter.proposal_row(p)
                    self.tree.item(iid, tags=(row["tag"],))
                except Exception:
                    pass
                p.note = "slutade ignorera — kommer flaggas igen vid nästa dubblett-sök"
            from tkinter import messagebox
            messagebox.showinfo("Slutat ignorera", f"Tog bort {removed} ignorerade nycklar. Kör 'Hitta dubbletter' igen för att se.")
            self.set_status(f"Slutade ignorera {removed} nycklar")
        except Exception as exc:
            LOG.warning("unignore fel: %s", exc)

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
                # Markera tydligt att Goodreads-länken ersätter reservkällan (BookBeat)
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
        try:
            if hasattr(self, "_prog_canvas") and self._prog_canvas.winfo_exists():
                self._prog_canvas.coords("prog_fill", 0, 0, 0, 28)
                is_dark_r = False
                try: is_dark_r = self._theme.get()=="dark" if hasattr(self._theme, "get") else False
                except: pass
                self._prog_canvas.itemconfig("prog_text", text="Klart ✨" if "Klart" not in str(self._prog_canvas.itemcget("prog_text","text")) else self._prog_canvas.itemcget("prog_text","text"), fill="#FFFFFF" if is_dark_r else "#000000", font=("TkDefaultFont", 10, "bold"))
        except: pass
        try: self.prog.config(value=0)
        except: pass
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

    def _show_guide(self) -> None:
        import os, pathlib
        t = STRINGS.get(self._lang.get(), STRINGS["sv"])
        title = t["guide_title"]
        LOG.info("hjälp: öppna guide (%s)", self._lang.get())
        # Hitta guidfilen — sv eller en beroende på valt språk
        try:
            gui_path = pathlib.Path(__file__).resolve()
            base = gui_path.parent.parent
            fname = "KOM_IGANG_GUIDE_EN.md" if self._lang.get() == "en" else "KOM_IGANG_GUIDE.md"
            candidates = [base / fname, base / "KOM_IGANG_GUIDE.md", pathlib.Path.cwd() / fname, pathlib.Path.cwd() / "KOM_IGANG_GUIDE.md"]
            guide_text = ""
            chosen = None
            for cand in candidates:
                if cand.exists():
                    guide_text = cand.read_text(encoding="utf-8")
                    chosen = cand
                    break
            if not guide_text:
                guide_text = f"{title}\n\n(Kunde inte hitta guidfilen — leta efter {fname} i appmappen)"
                LOG.warning("guidefil saknas, sökte %s", candidates)
            else:
                LOG.info("guide laddad från %s (%d tecken)", chosen, len(guide_text))
        except Exception as exc:
            guide_text = f"{title}\n\nFel vid laddning: {exc}"
            LOG.warning("kunde inte ladda guide: %s", exc)
        # Visa i eget fönster med rullning — fungerar på valt språk
        import tkinter as tk
        from tkinter import ttk
        win = tk.Toplevel(self.root)
        win.title(title)
        self._apply_icon_to_toplevel(win)
        # Anpassa guide-fönstret efter arbetsytan (aktivitetsfältet) — samma logik som huvudfönstret
        try:
            win.update_idletasks()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            # hämta arbetsyta om möjligt
            work_w, work_h = sw, sh
            work_x, work_y = 0, 0
            try:
                import ctypes
                from ctypes import wintypes
                rect = wintypes.RECT()
                if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                    work_x, work_y = rect.left, rect.top
                    work_w, work_h = rect.right - rect.left, rect.bottom - rect.top
            except Exception:
                pass
            desired_w, desired_h = 900, 700
            avail_w = max(640, work_w - 32)
            avail_h = max(480, work_h - 32)
            win_w = min(desired_w, avail_w)
            win_h = min(desired_h, avail_h)
            x = work_x + (work_w - win_w)//2
            y = work_y + (work_h - win_h)//2
            win.geometry(f"{win_w}x{win_h}+{x}+{y}")
            win.minsize(640, 480)
            try:
                win.transient(self.root)
            except Exception:
                pass
        except Exception:
            win.geometry("900x700")
        # Textruta med scrollbar
        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=6, pady=6)
        txt = tk.Text(frame, wrap="word", padx=8, pady=8, font=("TkDefaultFont", 9))
        vsb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.insert("1.0", guide_text)
        txt.config(state="disabled")
        # Stäng-knapp
        ttk.Button(win, text="OK", command=win.destroy).pack(pady=6)
        self.set_status(f"{title} öppnad")

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

    def _t(self, key: str) -> str:
        """Hämta översatt sträng — hela appen ska byta språk direkt."""
        try:
            lang = self._lang.get() if hasattr(self, "_lang") and self._lang else "sv"
            if lang not in STRINGS:
                lang = "sv"
            val = STRINGS.get(lang, STRINGS["sv"]).get(key)
            if val is not None:
                return val
            # fallback till svenska
            return STRINGS["sv"].get(key, key)
        except Exception:
            return STRINGS["sv"].get(key, key)

    def _apply_lang(self) -> None:
        try:
            self._build_menubar()
        except Exception as exc:
            LOG.debug("kunde inte tillämpa språk: %s", exc)
        # Uppdatera alla synliga texter direkt — hela appen byter språk utan omstart
        try:
            # Notebook tabs
            try:
                import tkinter.ttk as ttk
                for child in self.root.winfo_children():
                    if isinstance(child, ttk.Notebook):
                        nb_w = child
                        keys = ["tab_scan","tab_review","tab_manual","tab_ocr","tab_reco","tab_log","tab_hist"]
                        # Sätt tab-texter via widget, inte index — robust vid 7 flikar
                        try: nb_w.tab(self.tab_scan, text=self._t("tab_scan"))
                        except: pass
                        try: nb_w.tab(self.tab_review, text="3. Granska")
                        except: pass
                        try: nb_w.tab(self.tab_manual, text=self._t("tab_manual"))
                        except: pass
                        try: nb_w.tab(self.tab_ocr, text=" 📝 Inklistra text ")
                        except: pass
                        try: nb_w.tab(self.tab_reco, text=self._t("tab_reco"))
                        except: pass
                        try: nb_w.tab(self.tab_missing, text=" 📚 Saknade i serie ")
                        except: pass
                        try: nb_w.tab(self.tab_log, text=self._t("tab_log"))
                        except: pass
                        try: nb_w.tab(self.tab_hist, text=self._t("tab_hist"))
                        except: pass
                        break
            except Exception:
                pass
            # Stepper — uppdatera via _t och behåll cirklar
            try:
                # uppdatera stepper labels direkt
                if hasattr(self, "_stepper_title"):
                    self._stepper_title.config(text=self._t("stepper_title"))
                if hasattr(self, "_stepper_hint"):
                    self._stepper_hint.config(text=self._t("stepper_hint"))
                if hasattr(self, "_stepper_labels"):
                    keys = ["step_choose","step_scan","step_review","step_organize"]
                    for lbl, k in zip(self._stepper_labels, keys):
                        try: lbl.config(text=self._t(k))
                        except: pass
                self._update_stepper(getattr(self, "_current_step", 1))
            except Exception as exc:
                LOG.debug("stepper lang fel: %s", exc)
            # Timeline borttagen — ingen hint att uppdatera (visas i egen flik)
            # Empty hint
            try:
                if hasattr(self, "_empty_hint"):
                    self._empty_hint.config(text=self._t("empty_hint"))
            except: pass
            # Settings cards — uppdatera om refs finns
            try:
                if hasattr(self, "_settings_card_folders_label"):
                    self._settings_card_folders_label.config(text=self._t("settings_card_folders"))
            except: pass
            # Generisk traversering: uppdatera alla labels/buttons som matchar någon känd översättning
            try:
                # bygg omvänd karta: sv_text -> key och en_text -> key
                rev = {}
                for lang in ("sv","en"):
                    for k, v in STRINGS.get(lang, {}).items():
                        rev[v] = k
                        # även normaliserad utan emoji/prefix?
                def _update_widget(w):
                    try:
                        if hasattr(w, "cget"):
                            try:
                                txt = w.cget("text")
                                if txt in rev:
                                    key = rev[txt]
                                    w.config(text=self._t(key))
                            except Exception:
                                pass
                            try:
                                # även för ttk.Button etc, kolla via cget
                                pass
                            except: pass
                    except: pass
                    for child in w.winfo_children():
                        _update_widget(child)
                _update_widget(self.root)
            except Exception as exc:
                LOG.debug("generic lang update fel: %s", exc)
            # Status
            try:
                cur = self._lang.get()
                tcur = STRINGS.get(cur, STRINGS["sv"])
                self.set_status(tcur.get("lang_changed","").format(lang=cur) if "lang_changed" in tcur else self.status.cget("text"))
            except: pass
        except Exception as exc:
            LOG.debug("apply_lang extra fel: %s", exc)

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
        """Borttagen — tidslinje visas i egen flik "Saknade i serie" (historiken).

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
                    hint.config(text=self._t("timeline_hint"))
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
            canvas.create_text(w-6, 4, text=f"{len(owned_hist)} ägd(a)", anchor="ne", font=("TkDefaultFont", 9), fill="#666666")
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
        self._apply_icon_to_toplevel(win)
        try:
            win.update_idletasks()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            work_w, work_h = sw, sh
            work_x, work_y = 0, 0
            try:
                import ctypes
                from ctypes import wintypes
                rect = wintypes.RECT()
                if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                    work_x, work_y = rect.left, rect.top
                    work_w, work_h = rect.right - rect.left, rect.bottom - rect.top
            except Exception:
                pass
            desired_w, desired_h = 860, 420
            avail_w = max(600, work_w - 32)
            avail_h = max(360, work_h - 48)
            win_w = min(desired_w, avail_w)
            win_h = min(desired_h, avail_h)
            x = work_x + (work_w - win_w)//2
            y = work_y + (work_h - win_h)//2
            win.geometry(f"{win_w}x{win_h}+{x}+{y}")
            win.minsize(600, 360)
            try:
                win.transient(self.root)
            except Exception:
                pass
        except Exception:
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

    # ------------------------------------------------------------- skärmbild — tesseract helt borttaget
    def start_ocr_image(self) -> None:
        messagebox.showinfo("Borttaget", "Bildläsning är borttagen — tesseract är helt borttaget.\n\nKlistra in texten i rutan och klicka 'Tolka inklistrad text'. Matchning sker endast mot Goodreads.")

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
