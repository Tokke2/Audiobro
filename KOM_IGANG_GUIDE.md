# Kom igång — Audiobro (Bokbron / SagaSync)
*Version 2026-09-27 — ljudböcker på disk → Goodreads → Audiobookshelf, utan handpåläggning.*

> **Filer nämnda vid namn:** `KOM_IGANG_GUIDE.md` (denna guide), `README.md` (kort intro), `SPEC.md` (krav 1–34), `FUNKTIONER_CHECKLISTA.md` (vad som finns), `FUNKTIONER_25_NYA_IDÉER.md` (25 förslag), `ags/gui.py` (programmet), `Audiobro.pyw` (dubbelklick-start), `logs/ags.log` (felsök), `settings.json` / `history.json` (i `~/.audiobro/ (legacy ~/.audiobook-goodreads/)`).

---

## 1) Vad gör appen?

* Läser dina ljudboksfiler (`.mp3 .m4b .m4a .flac .ogg .opus`) i en **importmapp** → gissar titel/författare/serie offline (även `HH03 - Short Victorious War` → `Honor Harrington #3`, `Fjällbacka 01 - Isprinsessan` → `Fjällbacka #1`).
* Matchar mot **Goodreads** — poäng `0.62·titel + 0.30·författare + seriebonus`, `≥0.88 = matchad`.
* Skriver **korrekta Audiobookshelf-taggar** i filerna (titel/undertext/författare/år/serie+del/beskrivning/genre/uppläsare/förlag/språk/ISBN/ASIN) + `cover.jpg` + `.md`-faktablad med ljudkvalitet.
* Organiserar till `Outputmapp/Författare/Serie/01 - Titel/01 - Titel.mp3` så ABS sorterar serier rätt, med **kopiera eller 500000000000%-säker flytt** (ledigt-utrymme-koll + `.över`-backup + `SHA256`-verifiering).

---

## 2) Installation — 2 minuter

**Windows (dubbelklick utan konsol):** Ladda ner `Audiobro`-mappen → dubbelklicka `Audiobro.pyw` (alternativt `starta.bat`). Första gången klickar du `Kontrollera tillägg` i fönstrets överkant — appen kollar `mutagen`, `requests`, `websocket-client` och erbjuder `pip install` direkt.

**Mac/Linux:** `python3 -m ags.gui` eller `chmod +x starta.sh && ./starta.sh`.

> Saknas `tesseract` (OCR) är det **ingen varning som stoppar** — du kan alltid klistra texten i fliken `3. Skärmbild / text`.

**Kontroll:** `Hjälp → Om Audiobro` ska öppnas utan fel. Loggen skapas direkt: `<appmappen>/logs/ags.log`.

---

## 3) Första start — 3 klick

1. **Importmapp:** uppe i `1. Skanna & organisera` → `Välj mapp…` → peka på dina ljudböcker (t.ex. `C:/Users/monon/Documents/lazylibrarian` eller `~/Ljudböcker`). Sparas i `settings.json`.
2. **Outputmapp:** under `Outputmapp (Audiobookshelf):` → `Välj…` → din ABS-mapp (t.ex. `C:/Users/monon/Documents/Ljudböcker` eller `/home/user/audiobooks`). `Öppna outputmapp` öppnar den i Utforskaren. Krysset `♻️ Flytta filerna — radera källan (sparar HDD)` = av → kopiera (säkert, dubbel lagring), på → flytta (sparar HDD, raderar först efter verifierad kopia).
3. **Fördröjning:** låt stå `1.5 s` (snäll mot Goodreads).

Klicka `Kom ihåg → Spara inställningar nu` om du vill låsa valet.

---

## 4) När Goodreads är upptaget

Goodreads kan periodvis vara upptaget. Du ser då `blockerad` i Status. Lösning:

* **Automatisk (rekommenderas):** Bocka `Lås upp via min webbläsare (Brave/Chromium)` (Brave testas först) → nästa skanning hämtar en token via din egen webbläsare.
* **Manuell:** Öppna `goodreads.com` i Brave/Chrome → kopiera token från din webbläsare (F12 → Application → Cookies) → klistra i `Goodreads-token:` → `Använd token` (sparas).

Token är kortlivad (några timmar) — bockar du `Lås upp...` hämtas ny automatiskt.

**Även utan token:** appen provar `Storytel → BookBeat → Open Library` (står `Provar reservkällor…` nere) och hittar ändå många böcker.

**Knep:** Högerklicka en `blockerad`/`ej matchad` rad → `Klistra in Goodreads-länk för vald rad …` → klistra `https://www.goodreads.com/book/show/...` → raden blir `matchad 1.00 goodreads:länk` och **ersätter helt** reservkällans matchning (`goodreads:länk (ersätter storytel)` i Källa-kolumnen).

---

## 5) Skanna & organisera — ditt huvudflöde

1. `Skanna & matcha` → tabellen fylls: `grön matchad / gul behöver koll / röd blockerad / grå ej matchad / blå klar (historik|organiserad)`.
   * `Serie-tidslinje` nere visar prickar för serien (`● grön ägd / ● blå vald / ○ grå saknas`) — hovra för `Del 3 — ägd`.
2. **Kolla gula:** Dubbleklicka gula rader → `Välj bra träff…` → välj rätt bok → `Använd vald träff`.
3. **Kopiera originaltitel:** Högerklick → `Kopiera titel` kopierar **originalets mappnamn** (`SoS1 - The Shadow of Saganami`), inte Goodreads-titeln.
4. **Öppna i filhanterare:** Högerklick → `Öppna i filhanterare` → på Windows markeras filen med `explorer /select` (blå i Utforskaren), på Mac `open -R`, annars mappen öppnas.
5. **Slå ihop delar:** Markerera rader med `(1 of 2) / (2 av 2)` → `Slå ihop markerade delar`.
6. **Organisera:** Markera bara gröna (eller en rad) → `Organisera valda → output` eller högerklick `Organisera vald bok` (den senare tar även blå `klar (historik)`-rader om du vill flytta om en kopierad bok). Statusraden visar `Flyttar 2/5 (40%) — Titel` + progressbar, vid klart `Organiserat: 2 bok/böcker (2 flyttade, 0 kopierade) — taggar skrivna -> C:/...`.

> `Hoppa över redan klara (historik)` ikryssad = böcker i `6. Historik` matchas aldrig igen (krav 21). Vid träff frågar den `Tidigare importerad — hoppa över?` → `Ja` hoppar över, `Nej` matchar på nytt. `Rensa allt` nollställer.

---

## 6) De nya funktionerna du bad om

* **ReplayGain (1):** `Inställningar → 🔊 ReplayGain (jämn volym)` ikryssad = varje organiserad/refreshad fil får `REPLAYGAIN_TRACK_GAIN` (t.ex. `-7.23 dB`) via `ffmpeg loudnorm` — ingen omkodning, bara tagg. Kräver `ffmpeg` i PATH, annars hoppas taggen över tyst.
* **Serie-tidslinje (5):** Se ovan — horisontell linje `1 — [3] — 4 — 5` för vald serie.
* **Metadata-refresh (krav 34):** `6. Historik → 🔄 Sök uppdateringar i output` skannar din outputmapp och jämför befintliga `TXXX:SERIES`/`TIT3`/`TLAN` mot färsk Goodreads-data → `behöver uppdateras / aktuell` → `Uppdatera valda` skriver om taggar + ny `.md` + `cover.jpg` utan att flytta om.
* **100000% bättre matchning:** `Fjällbacka 01 - Isprinsessan`, `Honorverse HH03`, `SoS1` förstås offline, `Track 01 + Unknown Album` ignoreras, `Unknown Album` filtreras som skräp, flera sökfrågor provas (`Short Victorious War` → `Honor Harrington 3` → `HH03 - …`) tills träff.

---

## 7) Historik, logg, hjälp & språk

* **6. Historik:** datum/titel/författare/serie/del/output + `Uppdatera / Öppna mapp / Ta bort post / Rensa allt`.
* **5. Logg:** live-logg + sökväg + `Öppna loggfilen` (`logs/ags.log` loggar varje knapptryck/dialog/skanning/taggning/historiksvar + `sys.excepthook`).
* **Hjälp:** `Hjälp → Om Audiobro`, `Hjälp → Stöd projektet — PayPal` (`https://paypal.me/Rickard3dPrint`) / `Ko-fi ☕` (`https://ko-fi.com/tokke2`) — öppnar webbläsaren — tack! ❤️
* **Språk:** `Hjälp → Språk / Language → Svenska / English` — `English` översätter hela appen (knappar/inställningar/meny/flikar/historik) efter omstart (sparas i `settings.json` → `lang`). Hjälp-menyn byter direkt, övriga etiketter vid nästa start.

---

## 8) Vanliga frågor

**“Kopiera titel” kopierar fel?** Den kopierar *originalets mappnamn* nu. Vill du tillbaka till nya titeln, säg till — det är en rad i `ags/gui.py::_copy_title`.

**“Kan inte organisera (status: klar (organiserad))”?** Avsiktligt — högerklicka → `Organisera vald bok` för att tvinga.

**“Öppna i filhanterare” öppnar bara mappen?** Nu markerar den filen på Windows/Mac — uppdatera `ags/gui.py` från nya zippet.

**Uppdatera donation-länkar?** Säg ny PayPal.me / Ko-fi så patchar jag `PAYPAL_URL`/`KOFI_URL` i `ags/gui.py`.

> Tips: `Exportera CSV` i `1. Skanna & organisera` ger dig `fil,status,poäng,titel,författare,serie,del,år,album,källa,url` för Excel.

Säg **“öppna KOM_IGANG_GUIDE.md”** så ligger den framför dig — eller **“öppna ags/gui.py”** för att se koden.
