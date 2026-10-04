# Getting Started — Audiobro (Bokbron / SagaSync)
*Version 2026-09-27 — audiobooks on disk → Goodreads → Audiobookshelf, hands-free.*

> **Files by name:** `KOM_IGANG_GUIDE_EN.md` (this guide, English), `KOM_IGANG_GUIDE.md` (Swedish), `README.md`, `SPEC.md` (req 1–34), `FUNKTIONER_CHECKLISTA.md`, `ags/gui.py` (app), `Audiobro.pyw` (double-click), `logs/ags.log`, `settings.json` / `history.json` (in `~/.audiobro/ (legacy ~/.audiobook-goodreads/)`).

---

## 1) What does the app do?

* Reads your audiobooks (`.mp3 .m4b .m4a .flac .ogg .opus`) in an **import folder** → guesses title/author/series offline (e.g. `HH03 - Short Victorious War` → `Honor Harrington #3`, `Fjällbacka 01 - Isprinsessan` → `Fjällbacka #1`).
* Matches against **Goodreads** — score `0.62·title + 0.30·author + series bonus`, `≥0.88 = matched`.
* Writes **correct Audiobookshelf tags** (title/subtitle/author/year/series+part/description/genre/narrator/publisher/language/ISBN/ASIN) + `cover.jpg` + `.md` fact sheet with audio quality.
* Organizes to `Output/Author/Series/01 - Title/01 - Title.mp3` so ABS sorts correctly, with **copy or 500000000000%-safe move** (free-space check + `.över` backup + `SHA256` verify).

---

## 2) Install — 2 minutes

**Windows (double-click, no console):** Download `Audiobro` → double-click `Audiobro.pyw` (or `starta.bat`). First run click `Check add-ons` at the top — it checks `mutagen`, `requests`, `websocket-client` and offers `pip install`.

**Mac/Linux:** `python3 -m ags.gui` or `chmod +x starta.sh && ./starta.sh`.

> Missing `tesseract` (OCR) is not blocking — you can always paste text in tab `3. Screenshot / text`.

**Check:** `Help → About` should open without error. Log is created immediately: `<app folder>/logs/ags.log`.

---

## 3) First launch — 3 clicks

1. **Import folder:** In `1. Scan & organize` → `Choose folder…` → point to your audiobooks (e.g. `C:/Users/you/Documents/lazylibrarian` or `~/Audiobooks`). Saved in `settings.json`.
2. **Output folder:** Under `Output folder (Audiobookshelf):` → `Choose…` → your ABS folder. `Open output folder` opens it in Explorer. Checkbox `♻️ Move files — delete source (save HDD)` = off → copy (safe, double storage), on → move (save HDD, deletes only after verified copy).
3. **Delay:** leave `1.5 s` (nice to Goodreads).

Click `Remember → Save settings now` to lock in.

---

## 4) When Goodreads is busy

Goodreads can occasionally be busy. You’ll see `blocked` in Status.

* **Automatic (recommended):** Check `Unlock via my browser (Brave/Chromium)` (Brave tried first) → next scan fetches a token via your own browser.
* **Manual:** Open `goodreads.com` in your browser → copy the token (F12 → Application → Cookies) → paste into `Goodreads-token:` → `Use token`.

Token is short-lived (hours) — with `Unlock…` checked it’s refreshed automatically.

**Even without token:** the app tries `Storytel → BookBeat → Open Library` (`Trying fallback…` at bottom) and still finds many books.

**Trick:** Right-click a `blocked`/`not matched` row → `Paste Goodreads link for selected…` → paste `https://www.goodreads.com/book/show/...` → row becomes `matched 1.00 goodreads:link` and **fully replaces** the fallback match (`goodreads:link (replaces storytel)` in Source).

---

## 5) Scan & organize — main flow

1. `Scan & match` → table fills: `green matched / yellow needs check / red blocked / grey not matched / blue done (history|organized)`.
   * `Series timeline` below shows dots for the series (`● green owned / ● blue selected / ○ grey missing`) — hover for `Part 3 — owned`.
2. **Check yellow:** Double-click → `Pick good hit…` → choose correct book → `Use selected`.
3. **Copy original title:** Right-click → `Copy title` copies **original folder name** (`SoS1 - The Shadow of Saganami`), not the Goodreads title.
4. **Open in file manager:** Right-click → `Open in file manager` → on Windows the file is highlighted with `explorer /select` (blue in Explorer), macOS `open -R`, otherwise folder opens.
5. **Merge parts:** Select rows with `(1 of 2) / (2 of 2)` → `Merge selected parts`.
6. **Organize:** Select only green (or one row) → `Organize selected → output` or right-click `Organize selected book` (the latter also forces blue `done (history)` rows if you want to re-move a copied book). Status shows `Moving 2/5 (40%) — Title` + progress bar, done `Organized: 2 book(s) (2 moved, 0 copied) — tags written -> C:/...`.

> `Skip already done (history)` checked = books in `6. History` are never matched again (req 21). On hit it asks `Previously imported — skip?` → `Yes` skips, `No` rematches. `Clear all` resets.

---

## 6) New features you asked for

* **ReplayGain (1):** `Settings → 🔊 ReplayGain (even volume)` checked = each organized/refreshed file gets `REPLAYGAIN_TRACK_GAIN` (e.g. `-7.23 dB`) via `ffmpeg loudnorm` — no re-encode, just tag. Needs `ffmpeg` in PATH, otherwise silently skipped.
* **Series timeline (5):** See above.
* **Metadata refresh (req 34):** `6. History → 🔄 Check for updates in output` scans your output and compares existing `TXXX:SERIES`/`TIT3`/`TLAN` against fresh Goodreads → `needs update / up to date` → `Update selected` rewrites tags + new `.md` + `cover.jpg` without moving.
* **100000% better matching:** `Fjällbacka 01 - Isprinsessan`, `Honorverse HH03`, `SoS1` understood offline, `Track 01 + Unknown Album` ignored, multi-query tries `Short Victorious War` → `Honor Harrington 3` → `HH03 - …` until hit.

---

## 7) History, log, help & language

* **6. History:** date/title/author/series/part/output + `Refresh / Open folder / Remove entry / Clear all`.
* **5. Log:** live log + path + `Open log file` (`logs/ags.log` logs every click/dialog/scan/tag/history answer + `sys.excepthook`).
* **Help:** `Help → About`, `Help → Support the project — PayPal` (`https://paypal.me/Rickard3dPrint`) / `Ko-fi ☕` (`https://ko-fi.com/tokke2`) — opens browser — thank you! ❤️
* **Language:** `Help → Language → Svenska / English` — `English` translates the whole app (buttons/settings/menu/tabs/history) after restart (saved in `settings.json` → `lang`). Help menu switches instantly, other labels on next launch.

---

## 8) FAQ

**“Copy title” copies wrong?** It now copies the *original folder name*. Want the new title? Tell me — it’s one line in `ags/gui.py::_copy_title`.

**“Cannot organize (status: done (organized))”?** Intentional — right-click → `Organize selected book` to force.

**“Open in file manager” only opens folder?** Now it highlights the file on Windows/Mac — update `ags/gui.py` from the new zip.

**Update donation links?** Tell me new PayPal.me / Ko-fi and I’ll patch `PAYPAL_URL`/`KOFI_URL` in `ags/gui.py`.

> Tip: `Export CSV` in `1. Scan & organize` gives you `file,status,score,title,author,series,part,year,album,source,url` for Excel.

Say **“open KOM_IGANG_GUIDE_EN.md”** to see it again — or **“open ags/gui.py”** to see the code.
