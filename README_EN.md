# 🌉 Audiobro — Goodreads → Audiobookshelf ✨📚

> **Swedish name: *Audiobro*** — the file you double-click is still `Audiobro.pyw`. International / GitHub name is **Audiobro**.
> *Repo folder is `Audiobro` • App window title is `Audiobro — Goodreads → Audiobookshelf`*

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()
[![GUI](https://img.shields.io/badge/GUI-Tkinter-green)]()
[![Audiobookshelf](https://img.shields.io/badge/for-Audiobookshelf-8A2BE2)]()
[![Goodreads](https://img.shields.io/badge/data-Goodreads-blue)]()
[![Tests](https://img.shields.io/badge/tests-131%20passed-brightgreen)]()
[![Donate PayPal](https://img.shields.io/badge/donate-PayPal-0070BA?logo=paypal)](https://paypal.me/Rickard3dPrint)
[![Ko-fi](https://img.shields.io/badge/donate-Ko--fi-FF5E5B?logo=kofi)](https://ko-fi.com/tokke2)

**One-click audiobook organizer.** Point Audiobro at your messy import folder — it finds the right book on **Goodreads**, writes **correct Audiobookshelf tags** (title, author, series + part, narrator, description, …), and builds a pristine `Author/Series/01 - Title/` library with `cover.jpg` + `.md` fact sheet. Copy or *verified move* — your choice, your HDD saved.

<p align="center">
  <img src="assets/icon-happy.png" width="96" alt="Audiobro — happy book">
  <br>
  <em>The happy book is everywhere — tray, exe and docs</em>
</p>

<p align="center">
  <a href="https://paypal.me/Rickard3dPrint"><img src="https://img.shields.io/badge/💙_Support_via_PayPal-donate-0070BA?style=for-the-badge" alt="PayPal"></a>
  <a href="https://ko-fi.com/tokke2"><img src="https://img.shields.io/badge/☕_Buy_me_a_coffee-Ko--fi-FF5E5B?style=for-the-badge" alt="Ko-fi"></a>
</p>

---

## Why Audiobro?

- **Dumb folders → smart library in one click.** No manual tagging, no renaming.
- **Goodreads, directly.** Matches against Goodreads. If Goodreads is busy, just paste a Goodreads link (right-click → paste link) — 100% hit.
- **Audiobookshelf-native.** Mapping verified against ABS source (`AudioFileScanner.js` + `prober.js`). Series sorting just works — no extra settings in ABS.
- **Safe by default.** Dry-run first, `.agsbak` backups, `.över` collision rescue, SHA-256 verified move, history that never re-imports a done book.
- **Swedish hearts, world-ready.** Swedish titles resolved via Wikipedia → original title → Goodreads; UI in Swedish *and* English (`Help → Language`).

---

## What you get

```
Output/  ← your Audiobookshelf library
└── Camilla Läckberg/
    └── Fjällbacka/
        ├── 01 - Isprinsessan/          ← padded 01,02…10 = correct sort
        │   ├── 01 - Isprinsessan.mp3   (CD1 1–12 + CD2 1–12 → 1–24, continuous)
        │   ├── 02 - Isprinsessan.mp3
        │   ├── …
        │   ├── 06 - Isprinsessan.mp3
        │   ├── cover.jpg               (picked up by ABS automatically)
        │   └── Isprinsessan.md         (book info + audio quality per file)
        └── 02 - Predikanten/
            └── …
```

Each file keeps the **original audio** — only tags/filenames change (unless you encoded).

---

## ✨ Features

| | Feature |
|---|---|
| **6-tab GUI** | `1 Scan & organize` · `2 Single title / link` · `3 Screenshot / text` · `4 Recommendations` · `5 Log` · `6 History` |
| **Double-click, no console** | `Audiobro.pyw` + `starta.bat/.command/.sh` + `scripts/build_exe.py` (PyInstaller `--noconsole`) |
| **Exhaustive logging** | `~/.audiobro/ags.log` (DEBUG) + `logs/ags.log` — every click, HTTP status, token sent/not sent, match reason |
| **History & skip** | `~/.audiobro/history.json (legacy ~/.audiobro/ (legacy ~/.audiobro/)history.json)` — `[==] done (history)` never scanned again; right-click to force |
| **Multi-disc** | `CD1/CD 1/disc 2/skiva 1` folders merged → `13 - Title.mp3`, tags `track 13/24` |
| **Metadata + fact sheet** | `.md` per book with description, series, narrator, publisher, language, ISBN/ASIN + bitrate/kHz/channels/length/size |
| **Confirm before write** | Yellow *needs check* rows never auto-organize — double-click to pick; green rows organize in one click |
| **Recommendations** | Next in series + more by your authors + Goodreads “Readers also enjoyed” (owned + box sets filtered) |
| **Notifications & tray** | System tray (`pystray`), minimize-to-tray, autostart (Windows registry / macOS LaunchAgent / Linux .desktop), desktop notifications (`plyer`) |
| **Import + Output pickers** | Both folders remembered in `settings.json` + “Remember” menu with last 10 |
| **Status bar & progress** | `%` + “Moving 2/5 — Title” + 28 px Canvas progress bar (`#000`/`#FFF`) in `1 Scan & organize` |

---

## 🚀 Quick start

### 1. Install

```bash
git clone https://github.com/Tokke2/Audiobro.git
cd Audiobro
pip install -r requirements.txt
python -m ags.gui            # or double-click Audiobro.pyw
```

**Requirements** (`requirements.txt`):

```
requests>=2.28
beautifulsoup4>=4.12
lxml>=4.9
mutagen>=1.47
rapidfuzz>=3.0
Pillow>=9.0
websocket-client
pystray>=0.19
plyer>=2.1
```

> On first launch the app checks that all add-ons are installed and up-to-date. Missing → offers `pip install -r requirements.txt`; out-dated → offers `pip install --upgrade`. You can re-check anytime via **Check add-ons** button or `python -m ags.cli deps`.

No `tesseract` needed unless you use the screenshot tab.

### 2. First launch — 3 clicks

1. **Import folder** — `1 Scan & organize` → `Choose…` → your messy folder (e.g. `~/Audiobooks` or `C:\Users\you\Documents\lazylibrarian`)
2. **Output folder** — `Output folder (Audiobookshelf):` → `Choose…` → your ABS library folder
3. Leave **Delay `1.5 s`** (polite to Goodreads) → `Remember → Save settings now`

### 3. Scan & organize — main flow

1. `Scan & match` → table fills: `🟢 matched` / `🟡 needs check` / `🔴 blocked` / `⚪ not matched` / `🔵 done (history)`
2. **Yellow rows:** double-click → `Pick good hit…` → choose the right book → `Use selected`
3. **Merge parts:** select rows with `(1 of 2)` / `(2 of 2)` → `Merge selected parts`
4. **Organize:** `Organize green + confirmed` or select rows → right-click `Organize selected → output`
5. Watch the status bar: `Moving 3/12 (25%) — Isprinsessan` → `Organized: 3 book(s) (2 moved, 1 copied) — tags written → C:/…`

Copy is default. Check `♻️ Move files — delete source` to move (only after verified copy + free-space check).

> **Tiers that save you:** green rows are sorted `author → series → part → title` and already padded `01 - Title` so Audiobookshelf shows series in order with zero config.

---

## 🖥️ The 6 tabs

| Tab | What it does |
|-----|--------------|
| **1 Scan & organize** | Pick import & output, recursive scan (`.mp3 .m4b .m4a .flac .ogg .opus`), group per book (CD1+CD2 merged), match Goodreads, table with colors. Buttons: `Organize`, `Open output folder`, `Export CSV`. Right-click: `Copy title` (copies *original* folder name, not Goodreads title), `Open in file manager` (highlights file via `explorer /select` on Windows, `open -R` on macOS), `Paste Goodreads link for selected…`, `Merge parts`, `Organize selected book` |
| **2 Single title / link** | Look up one book. Paste a **Goodreads URL** (`https://www.goodreads.com/book/show/...`) — that exact book is used (`goodreads:link`, no guessing) |
| **3 Screenshot / text** | Offline fallback: pick a screenshot or paste text; each title is parsed and matched — needs no Goodreads |
| **4 Recommendations** | Next in series + more by your authors from history/library; box sets skipped, owned filtered |
| **5 Log** | Live tail of `ags.log` + `Open log file` |
| **6 History** | Every organized book: date/title/author/series/part/output + `🔄 Check for updates in output` (compares `TXXX:SERIES`/`TIT3`/`TLAN` vs fresh Goodreads → rewrites tags + `.md` + `cover.jpg` without moving) |

---

## 🔓 Goodreads — how it works

Goodreads has no public API since Dec 2020. The app reads the public pages. If Goodreads is temporarily busy, Audiobro can use your own browser to get the data:

```bash
python -m ags.cli --auto-token scan ~/Audiobooks     # CLI auto-unlock
python -m ags.cli token                              # print a token manually
```

---

## 🧠 Matching logic (19999% edition)

- Query cleanup: removes junk tags (`Unknown`, `N/A`), extracts series hints (`(Millennium, #1)`, `Fjällbacka 01 - Isprinsessan` → `Fjällbacka #1`, `HH03`, `SoS1`)
- Multi-query: tries `Short Victorious War` → `Honor Harrington 3` → `HH03 - …` until hit
- Score `0.62·title + 0.30·author + series bonus`; `≥0.88 matched`, `0.62–0.88 needs check`, tie → `needs check` so *you* choose
- Series books get `01 - Title` folder + `SERIES_PART` tags + CSV + GUI sort by part (handles `2.5`)
- Already done (`history.json`) → `[==]` and skipped (`Skip already done` checkbox / `--no-skip-done`)

---

## 🏷️ What gets written (Audiobookshelf-verified)

Mapping checked against ABS `server/scanner/AudioFileScanner.js` + `server/utils/prober.js` — narrator via `composer`, description via `description`/`comment`, etc.

| Field (ABS) | MP3 (ID3) | M4B/M4A (MP4) | FLAC/OGG (Vorbis) |
|---|---|---|---|
| Title | `TIT2` | `©nam` | `TITLE` |
| Author | `TPE1` | `©ART` | `ARTIST` |
| Album | `TALB` = `Series, #n` or title | `©alb` | `ALBUM` |
| Series | `TXXX:SERIES` | `----:com.apple.iTunes:SERIES` | `SERIES` |
| Part | `TXXX:SERIES_PART` + `SERIES-PART` + `PART`/`EPISODE_ID`/`MVIN` | `----:…:SERIES_PART`+`SERIES-PART`+… | `SERIES_PART`+… |
| **Narrator** (ABS composer) | `TCOM` | `©wrt` | `COMPOSER` |
| **Description** | `COMM` | `©des` | `DESCRIPTION` |
| **Subtitle** | `TIT3` | `----:…:SUBTITLE` | `SUBTITLE` |
| **Publisher** | `TPUB` | `©pub` | `PUBLISHER` |
| **Genre** | `TCON` | `©gen` | `GENRE` |
| **Language** | `TLAN` | `----:…:LANGUAGE` | `LANGUAGE` |
| **ASIN / ISBN** | `TXXX:ASIN` / `TXXX:ISBN` | `----:…:ASIN`/`ISBN` | `ASIN`/`ISBN` |
| Year | `TDRC` | `©day` | `DATE` |
| Track | `TRCK` = `n/total` | `trkn` | `TRACKNUMBER`+`TRACKTOTAL` |
| **Cover** | `cover.jpg` in title folder | same | same |

Original file backed up as `<name>.agsbak` (disable with `--no-backup`). Nothing written on dry-run. If target exists, old file saved as `*.över` and auto-restored if orphaned.

---

## ⌨️ CLI

```bash
# dry-run: see what would change
python -m ags.cli scan ~/Audiobooks

# write tags (backups as .agsbak)
python -m ags.cli scan ~/Audiobooks --apply

# organize for Audiobookshelf + .md
python -m ags.cli scan ~/Audiobooks --apply --output ~/audiobooks

# move instead of copy, ask on yellow rows
python -m ags.cli scan ~/Audiobooks --apply --output ~/audiobooks --move --interactive

# recommendations from history
python -m ags.cli recommend

# single title, all hits with scores
python -m ags.cli match "The Shadow of Saganami" -a "David Weber" --all

# via Goodreads URL — exact
python -m ags.cli match --url "https://www.goodreads.com/book/show/13496"

# screenshot fallback
python -m ags.cli ocr screenshot.png

# deps check
python -m ags.cli deps

# build exe
pip install pyinstaller && python scripts/build_exe.py   # → dist/Audiobro/
```

---

## ⚙️ Settings, history & logs

- Settings → `~/.audiobro/settings.json (legacy ~/.audiobook-goodreads/settings.json)` (folders, checkboxes, delay, album style, `lang: sv/en`, `Goodreads-token`, systray/autostart)
- History → `~/.audiobro/history.json (legacy ~/.audiobro/ (legacy ~/.audiobro/)history.json)`
- Cache → `~/.audiobro/ (legacy ~/.audiobro/)cache/`
- Logs → `~/.audiobro/ags.log (eller <app>/logs/ags.log + legacy ~/.audiobro/ (legacy ~/.audiobro/)ags.log)` + `<app>/logs/ags.log` + `logs/audit.log` + `logs/perf.jsonl`

Menu **`Remember`** lists last import/output folders + `Save settings now`. `Help → Language → Svenska / English` switches the whole app (restart to apply all tabs; Help menu switches instantly).

---

## ❤️ Support the project — keep it free & magical

**Audiobro is free, no ads, no paywall, open source.** Your donation is what keeps series matching, tagging and Goodreads support alive. You support a solo indie dev — not a company.

| Way | Link |
|-----|------|
| **PayPal** (any amount) | **[paypal.me/Rickard3dPrint](https://paypal.me/Rickard3dPrint)** |
| **Ko-fi** (coffee / monthly) | **[ko-fi.com/tokke2](https://ko-fi.com/tokke2)** |

### Why donate?

- **55% Development** — better matching, series logic, Goodreads fixes, ABS finesse
- **25% Ops & test** — domain, build, test audiobooks to ship without bugs
- **20% Coffee & time** — your coffee keeps the keyboard warm

> No tracking. No account in the app. Receipt comes directly from PayPal/Ko-fi. Want your name in the README? Add it to the message. Want to stay anonymous? Leave it empty. Want Swish? Tell me the number/QR and I’ll add a `swish://` button.

### 🎁 Choose your support tier — or any amount you like

All tiers use the links above — pick any sum you want (one-time or monthly on Ko-fi).

| Tier | Amount | What you get | Quick link |
|------|--------|--------------|------------|
| ☕ **Coffee** | `39 kr` | Thank-you in next release notes + good vibes | **[PayPal 39 kr](https://paypal.me/Rickard3dPrint/39SEK)** · [Ko-fi](https://ko-fi.com/tokke2) |
| 📚 **Book friend** ⭐ *Most popular* | `99 kr` | Little ♥ in the app + your ideas prioritized | **[PayPal 99 kr](https://paypal.me/Rickard3dPrint/99SEK)** · [Ko-fi](https://ko-fi.com/tokke2) |
| 🌟 **Hero** | `299 kr` | Name in README (if you want) + wishlist priority + eternal gratitude | **[PayPal 299 kr](https://paypal.me/Rickard3dPrint/299SEK)** · [Ko-fi](https://ko-fi.com/tokke2) |

> **Any amount counts** — 20 kr or 500 kr, one-time or monthly. Every krona keeps the 19999% matching alive.
> **Swish?** Tell me the number/QR and I’ll add a beautiful `swish://` button here.
> Or open the full thank-you page in the app: `Help → Support the project` → `DONATION.html`

*Thank you — tack!* ❤️ *You make free audiobooks possible.*

---

## 🧪 Tests

```bash
pip install pytest
python -m pytest tests/ -q        # offline — 131 tests vs saved Goodreads HTML (fixtures/)
DISPLAY=:99 python -m pytest      # + GUI test (needs X / Xvfb)
python scripts/gui_demo.py --root ~/some-folder --out docs/gui.png
```

No network needed for the suite — it replays `tests/fixtures/*.html` (search + book + series).

---

## ⚠️ Limitations

- Goodreads is English-centric: Swedish titles are resolved via Wikipedia bridge → original title → Goodreads
- Series in MP3 uses `TXXX` frames — players that only read standard frames will show Album (`Series, #n`) instead
- Write support: MP3, M4B/M4A, FLAC, OGG/OPUS — other formats are read but not written
- OCR quality depends on screenshot resolution — pasted text is always more reliable

---

## 📄 Docs

- `KOM_IGANG_GUIDE.md` — Swedish getting-started (full)
- `KOM_IGANG_GUIDE_EN.md` — English getting-started
- `SPEC.md` — requirement spec 1–34 (Swedish, accumulated — nothing removed until you say so)
- `DESIGN_BATTRE.md` — design notes
- `STÖD_PROJEKTET.html` / `DONATION.html` — local donation page (open from `Help → Support…`)

---

## Credits

Built with ♥ for audiobook lovers. Icon `assets/icon-happy.png`. Mapping verified against Audiobookshelf source. Goodreads scraping for personal metadata only — be polite (delay).

**Questions?** Open `Help → About` in the app, or ping via PayPal/Ko-fi message — I read every one.

*Tip: `Export CSV` in `1 Scan & organize` gives you `file,status,score,title,author,series,part,year,album,source,url` for Excel.*

---

## Name FAQ

- **What name did we pick?** Code title is **`Audiobro`** (`APP_TITLE = "🌉 Audiobro — Goodreads → Audiobookshelf ✨📚"`). The double-click file stays **`Audiobro.pyw`** for Swedish users. GitHub repo is **`Audiobro`**. Working titles `Bokbron` / `SagaSync` were floated in `KOM_IGANG_GUIDE.md` but **Audiobro won**.
- **Which to use where?** Use **Audiobro** internationally (GitHub, English docs, window title) and **Audiobro** in Swedish contexts (guide, Start menu, `.pyw`). Both point to the same thing.
- **Change it?** Tell me the final name and I’ll patch `APP_TITLE` in `ags/gui.py`, the `autostart.py` shortcut name, `scripts/build_exe.py` output folder, and all docs in one commit.
