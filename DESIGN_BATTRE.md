# Battre design & tydligare steg — 1000000000% battre (2026-10-03)

## Oversikt
Hela appen har fatt battre layout och guidning — fran forsta klick till klar bok.
Fokus: 4 steg som syns overallt, mer luft, storre klickytor, battre hierarki.

## Nytt — vad du ser direkt

### 1) Steg-indikator overst (alltid synlig)
Ny STEG 1->2->3->4 precis under installningar:
[1 Valj mappar] -- [2 Skanna] -- [3 Granska] -- [4 Organisera]   -> folj 1->4 sa blir allt ratt
- Farger: gron = klar, bla = aktiv, gra = kommer (via _update_stepper(step))
- Uppdateras automatiskt: start_scan() -> 2, forsta rad -> 3, Organisera -> 4
- Kod: _build_stepper() + _update_stepper() i ags/gui.py:364,396

### 2) Installningar — grupperade i 2 kort
Outer med titelrad "Installningar — andras direkt • sparas automatiskt"
- Vanster kort 1 Mappar — Output-mapp (Valj/Oppna) + Flytta-rutan med hint sparar HDD
- Hoger kort 2 System & utseende — Tema, Delay, Backup/Skip/ReplayGain, Autostart/Tray/Notiser, Token+Serie
- Mer luft, vit bakgrund mot varm FFFBF5, 1px border FFE4C4

### 3) Flik 1 — Skanna & organisera — 4 tydliga steg-kort
1 Valj importmapp | 2 Skanna & matcha [Skanna & matcha] [CSV]
Hint: borja litet (1-2 bocker) — gron=saker gul=kolla rod=blockerad
3 Granska resultatet — header ovanfor tabellen: "gron=saker • gul=kolla • bla=klar • lila=dubblett"
[Tabell med zebra, 26px radhojd]
4 Organisera — gron bard:
   [Visa] [Valj] | [Skriv] [Alla grona] [Sla ihop] [Dubbletter] | [Skicka valda] [Skicka alla klara] -> Audiobookshelf
Tidslinje + detaljer langst ner

### 4) Ovriga flikar — tydliga headers
- 2. Enskild titel / lank -> Alternativ vag — nar skanning ar blockerad
- 3. Skarmbild / text -> Reservlage — skarmbild -> text -> matchning
- 4. Rekommendationer -> Upptack mer — baserat pa din historik + Accent-knapp
- 6. Historik -> Historik — redan klara • de matchas aldrig igen
- 5. Logg — niva/regex/trace/JSON/Stats/Export

## Filer andrade
- ags/gui.py (175K) — stepper + settings + scan + headers
- STOD_PROJEKTET.html + DONATION.html — donationssida
- assets/icon-happy.png — enda ikonen

## Verifierat
- py_compile OK, pytest 131 passed, 14 skipped
- gui --selftest bygg OK
