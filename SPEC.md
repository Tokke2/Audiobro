# SPEC — Audiobro — Goodreads → Audiobookshelf

Detta dokument är projektets kravspecifikation. Varje punkt kommer från
användarens beställningar och är ackumulerad (inget stryks förrän användaren
tar bort det). `README.md` beskriver *hur* appen används; detta dokument
beskriver *vad* som ska gälla.

## Mål och avgränsningar

* Källor: ljudboksfiler på disk (`.mp3 .m4b .m4a .flac .ogg .opus`).
* Riktning: Goodreads (m.fl.) → metadata **skrivs in i filerna** och organiserar
  dem för Audiobookshelf. Ingen synk tillbaka till Goodreads.
* GUI: Tkinter, svenska etiketter och kommentarer.
* OCR/skärmbild är endast reservläge (inklistrad text fungerar alltid).

## Krav (ackumulerade)

1. **Audiobookshelf-anpassning** — serie + titel läses in; både mappar *och*
   filer namnges; boken placeras i `Författare/Serie/NN - Titel/` så att serier
   sorteras efter **delnummer** (även i GUI-tabellen).
2. **Dubbelklick utan konsol** — `Audiobro.pyw`, `starta.bat` (pythonw),
   `starta.command`, `starta.sh`, samt `scripts/build_exe.py` (PyInstaller
   `--noconsole`).
3. **Logga allt** — `~/.audiobro/ags.log (eller <app>/logs/ags.log + legacy ~/.audiobro/ (legacy ~/.audiobro/)ags.log)` (DEBUG): varje anrop med
   statuskod, blockeringar *inkl. om token skickades*, vilka källor
   som prövades och med hur många träffar, samt per bok en rad som förklarar
   resultatet/orsaken när matchning misslyckas (”10000 % felsökningssäkert”).
4. **Välj importmapp OCH outputmapp** (GUI + CLI `--output`).
5. **Historik** — färdiga böcker hoppas över (`[==] klar (historik)`),
   `--no-skip-done`/kryssruta styr.
6. **Multi-disc** — CD1 (spår 1–12) + CD2 (spår 1–12) slås ihop till en bok;
   disc 2 fortsätter numreringen (13–24) i filnamn och taggar.
7. **`.md`-faktablad** — bokinfo + ljudkvalitet per fil (bitrate, kHz, kanaler,
   längd, storlek) + beskrivning/uppläsare/förlag/genre/språk.
8. **Användaren bekräftar** osäkra matchningar (GUI-dialog / `--interactive`);
   osäkra rader organiseras aldrig automatiskt.
9. **Rekommendationer ur historiken** — flik "4. Rekommendationer" föreslår
   utifrån det du tidigare organiserat: nästa del i serier, fler böcker av
   dina författare samt Goodreads "Readers also enjoyed" för de senaste
   böckerna i historiken; ägda böcker och samlingsboxar filtreras bort.
10. **Städning** — var 5:e chattmeddelande töms arbetsytan till spec + aktiva
    filer.
11. **Reservkällor** — när Goodreads är blockerat/tomt: **Storytel → BookBeat →
    Open Library** (nyckelfria API:er; `--no-nordic` / `--no-fallback` styr).
12. **Audiobookshelf-metadata i filerna** — exakt de fält ABS-editorn visar:
    title, subtitle, authors, publish year, series + del, description,
    genres/tags, narrators (via composer), publisher, language, ISBN, ASIN —
    samt **`cover.jpg`** i titelmappen. Mappningen verifierad mot ABS källkod
    (`AudioFileScanner.js`/`prober.js`); serie-delen skrivs i både
    `SERIES_PART` och `SERIES-PART`.
13. **Tilläggskontroll vid start** — appen kontrollerar `requests`, `mutagen`,
    `websocket-client`, `tesseract`; saknas ett pip-paket **erbjuds
    installation direkt** (appens egen pip-körning), för tesseract visas
    installationslänk per OS. CLI: `python -m ags.cli deps [--install]`.
14. **Upplåsning** — Goodreads låses upp via användarens egen
    webbläsare (Brave först), token återanvänds; manuell token via GUI/CLI.

## Arbetsflöde i chatten (krav från 2026-09-20)

15. **Filer nämns vid namn + öppnas i ws-visaren.** I *varje*
    chattmeddelande som nämner, skapar eller ändrar filer ska **alla dessa
    filer** räknas upp vid namn, och huvudfilen öppnas i arbetsytans visare
    (`present_file`) så den hamnar framför användaren i samma fönster.
    Vanliga markdown-länkar används inte för att öppna filer — chatklienten
    gör om dem till externa URL:er som inte pekar på ws. Sägg "öppna X"
    för att se vilken som helst fil.
16. **Cacherensning efter varje avslut — i appen och i ws.** Efter *varje*
    avslutat meddelande/uppdrag rensas genererade cachefiler ur arbetsytan:
    `__pycache__/`, `*.pyc`, `.pytest_cache` m.fl. Rensningen är **inbyggd i
    appen**: den körs när GUI-fönstret stängs, efter varje CLI-kommando, samt
    manuellt via knappen *"Rensa cache"* / `python -m ags.cli cleanup`.
    (Den större städningen var 5:e meddelande, krav 10, gäller utöver detta.)

17. **Högerklicksmeny vid blockad.** När en sökning är blockerad (eller av
    annan anledning missar) ska man via **högerklick på raden** i tabellen kunna
    *klistra in en Goodreads-länk manuellt* — raden uppdateras då med exakt den
    boken. Menyn har även "Öppna i filhanterare" och "Kopiera titel".

18. **Dubbelkörningsskydd + självreparation.** En organiserad rad kan inte
    organiseras igen (`applied`); saknas källfilen rapporteras det som fel i
    stället för att krascha; och en kvarlämnad `.över`-fil återställs
    automatiskt när källan saknas.

19. **Dublettskydd i output.** Finns samma *titel + författare* redan i
    outputmappen frågas användaren innan något organiseras (GUI-dialog;
    CLI: varning + hoppa över, `--interactive` frågar, `--force` kör ändå).

20. **Inställningar sparas i JSON.** Mappar och inställningar (importmapp,
    outputmapp, kryssrutor, fördröjning, albumstil) sparas i
    `~/.audiobro/settings.json (legacy ~/.audiobro/ (legacy ~/.audiobro/)settings.json)` och läses vid start. Menyn
    **"Kom ihåg"** listar senaste import-/outputmappar (klickbara) och
    "Spara inställningar nu". Knappen **"Öppna outputmapp"** öppnar mappen i
    filhanteraren.
21. **Arkiveras efter organisering — historikflik, ingen ommatchning.** När en
    bok organiserats arkiveras den i historiken (`history.json`), visas i
    GUI-fliken **"6. Historik"** (datum/titel/författare/serie/del/output +
    knapparna Uppdatera, Öppna mapp, Ta bort post, Rensa allt) och **matchas
    aldrig på nytt**: historiken kontrolleras *före* några sökanrop görs.
    Vid träff frågar GUI:t **"Tidigare importerad — hoppa över?"**
    (Ja = hoppa över, Nej = matcha på nytt); CLI frågar med
    `--interactive`, annars hoppas tyst över. Tas en post bort kan
    boken matchas igen.
22. **Token sparas.** Token som hämtas via webbläsaren (eller klistras
    in manuellt) sparas i `settings.json` (`goodreads_token`) och återanvänds
    automatiskt vid nästa start — i både GUI och CLI (`ags token` sparar
    också). Filen är klartext och token kortlivad; maskning i loggen är
    planerad (se checklistan).
23. **Flera versioner — bästa väljs.** Finns flera versioner av samma bok i
    en skanning (samma Goodreads-id, annars samma titel+författare) behålls
    den bästa: störst total filstorlek (bitrate-proxy), därefter m4b/m4a
    före mp3, därefter färst antal filer. Övriga markeras
    **`sämre version`** (`[~~]` i CLI) och hoppas över vid organisering.
24. **Split-delar upptäcks + manuell sammanslagning.** Filnamn med
    "(1 of 2)", "(2 av 2)" e.dyl. räknas som samma bok: de grupperas ihop
    och sorteras i delordning. Fungerar inte det automatiskt kan delarna
    slås ihop manuellt: markera raderna -> "Slå ihop markerade delar"
    (knapp eller högerklicksmeny).
25. **Logg i appmappen.** Loggen sparas alltid i `<appmappen>/logs/ags.log`
    (fallback: hemkatalogen om appmappen är skrivskyddad). Logg-fliken visar
    sökvägen och "Öppna loggfilen" öppnar den.
26. **Organisera vald bok via högerklick.** Högerklicksmenyn har
    "Organisera vald bok → outputmappen" (samma som knappen
    "Organisera valda"). Ett uttryckligt val får även ta med
    `klar (historik)`-rader — t.ex. för att flytta en bok som tidigare
    kopierats — medan de automatiska knapparna förblir skyddade.
27. **Förlopp synligt.** Under skanning och organisering visar statusraden
    vad som görs och hur långt det gått — "Matchar 3/12 (25 %) — <grupp>" /
    "Flyttar 2/5 (40 %) — <titel>" — och en progressbar i fönstrets nederkant
    fylls på. Nollställs vid klart.
33. **Flytta sparar HDD — 500000000000 % säkert.** Valet ”♻️ Flytta filerna — radera källan (sparar HDD)” finns i GUI (kryssruta, sparas i `settings.json` → `move`) och CLI (`--move`). Avkriat kopierar (behåller källan som backup); flytt *flyttar*: källan raderas först efter verifierad kopia. Säkerheten är 500000000000 %: ledigt-utrymme koll före start (50 MB marginal), befintlig fil i output backupas till `.över`, atomär `os.replace` på samma filsystem annars `copy2` + storlek- + SHA256-hash-verifiering över enheter, hash för <500 MB, mål verifieras efteråt, `.över`-backup rensas vid lyckad flytt, tomma källmappar rensas (max 4 nivåer). GUI frågar med ja/nej-dialog när Flytta bockas i, loggar `move=True/False` och visar ”Flyttar/Kopierar n/m (x %) — titel” + slutrad ”(X flyttade, Y kopierade)”. Vid fel återställs backup och källan behålls — ingen dataförlust, inget extra HDD-slöseri.
32. **ABS-seriemetadata 50000000 % (Audiobookshelf utan krångel).** Varje organiserad fil får serie + del skrivet **redundant i alla format** så ABS alltid hittar delen utan handpåläggning: MP3 `TXXX:SERIES`+`TXXX:SERIES_PART` *och* `TXXX:SERIES-PART`+`TXXX:PART`/`EPISODE_ID`/`MVIN`, M4B `----:com.apple.iTunes:SERIES`+`SERIES_PART`+`SERIES-PART`+`PART`/`EPISODE_ID`, FLAC/OGG `SERIES`+`SERIES_PART`+`PART`/`SERIES-PART` m.fl. Saknar Goodreads serie används hint från mapp/filnamn (`Fjällbacka 01 - Isprinsessan` → `Fjällbacka #1`) så mappen alltid blir `Författare/Serie/01 - Titel/` med nollpaddat `01,02…10` för korrekt sort. Varje fil i en bok får löpande `TRCK`/`trkn`/`TRACKNUMBER` (`01/12, 02/12…` över disc-gränser, `03/04` → `04/04`), `cover.jpg` i titelmappen och `.md` med `Serie: Fjällbacka #1` — ABS läser serien direkt via taggar *eller* mapp utan extra inställning.
31. **Serie-mönster 50000000 % (serie-perfektion).** Alla vanliga serie-mönster i filnamn/mapp tolkas *före* sökning och helt offline: "Serie – Book 5", "Serie #2 - Titel", "Serie 01 - Titel", "Titel (Serie, #1)", "[Serie #1] Titel", "Vol. 2/Part 3/#11" — även när mappen heter "Fjällbacka 01 - Isprinsessan" och filen bara "Track 01.mp3". Den rena boktiteln ("Isprinsessan") används som sökfråga och serie/del ger bonus/straff i matchningen: rätt del i rätt serie slår fel del/serie med 0.12–0.18 poäng; "Track 01"/"Chapter 01"-skrot hindrar aldrig serie-tolkning; fel del >1 straffas hårt ("Bok 5" vs del 1 kan aldrig bli "matchad"). Fungerar även när Goodreads är upptaget.
30. **Matchningskvalitet (19999 %-ronden).** (a) Disc-mappar ("X (Disc 01)",
    "X (Disc 02)") slås ihop till EN bok vid gruppering. (b) Rip-skrot som
    "Track 01" i titeltaggen används aldrig som sökfråga — mappnamnet tar
    över. (c) Skräputgåvor ("Summary & Study Guide", "Reading Tracker",
    "Box set", "1st print hardback" …) straffas hårt i poängen. (d) En träff
    vars författare inte stämmer med filens artist-tagg kan aldrig bli
    "matchad" (-> "behöver koll"). (e) Två nära träffar som är samma verk i
    olika utgåvor triggar inte "behöver koll".
29. **Organiseringen syns tydligt.** När en bok organiseras (knapp eller
    högerklick) visar statusraden löpande "Flyttar/Kopierar n/m (x %) — titel"
    och vid klart ett explicit slutbesked: "Organiserat: N bok/böcker
    (X flyttade, Y kopierade) — taggar skrivna -> <output>". Radens status
    byts till `klar (organiserad)` (blå) så det syns i tabellen.
28. **Logga precis allt.** Filloggningen startar redan när GUI-modulen
    importeras (`setup_logging()` anropas vid import och i `main()`), så
    `logs/ags.log` skapas direkt appen startar. Varje knapptryck, menyval,
    högerklick, dialog, skanning, organisering, taggskrivning,
    inställningsändring och historiksvar loggas; okända krascher fångas av
    `sys.excepthook`/`threading.excepthook` och loggas med stacktrace.
    Eventpumpen (`_poll`) är kraschsäker: ett undantag i en enskild händelse
    loggas men dödar inte kön. Ett jobb som hoppas över p.g.a. pågående jobb
    visas i statusraden ("Ett annat jobb pågår fortfarande …") och loggas.

34. **Metadata-uppdatering av organiserade filer — refresh utan att flytta om.** Outputmappen kan genomsökas när som helst: `python -m ags.cli refresh [output] [--apply]` eller GUI-fliken **6. Historik → 🔄 Sök uppdateringar i output / Uppdatera valda**. Flödet: `scan(output) → groups → för varje grupp: läs befintliga taggar (library.read_tags), slå upp historik (`history.find_match`/`history.output`) eller matcha på nytt (`client.book` eller `resolve+matching.rank`), bygg förslag via `engine._fill`, diff mot befintliga taggar via `tags.write_file`-fältet och `_diffs`, flagga `cover.jpg`/`.md`-behov; status `behöver uppdateras` vs `aktuell`. `engine.apply_update` skriver omtaggning per fil med löpande `TRCK n/total`, regenererar `.md` via `audioinfo.book_md`+`probe`, hämtar `cover.jpg` om saknad, uppdaterar `history.add`. Stöd för `--all` (visa aktuella), `--force` (utan fråga), `-v` (torrkörning med diff). GUI kör `refresh` i bakgrundstråd med `queue` (`refresh_one`/`refresh_done`/`refresh_applied`/`progress`) och visar % i statusraden.

## Kommande checklista (planerat, ännu ej byggt)

Prioriterade av användaren 2026-09-20:

- [x] **Serie-mönster ur filnamn/mapp** — "…Welcome to the Multiverse – Book 5",
      "Vol. 2", "Part 3", "#11" tolkas till serie + delnummer *före* sökning
      (fungerar även när allt är blockerat) — **byggd som krav 31 (50000000 %).**
- [x] **Historik-kontroll FÖRE sökning** — byggd som krav 21.
- [ ] **Mörkt tema-växlare** (ttk-theme).
- [x] **Progressbar + % + pågående steg i statusraden** — byggd som krav 27.
- [ ] **Avbrytt-knapp** under skanning/organisering.
- [ ] **Omslagstumnail i detaljpanelen**.
- [ ] **Loggrotation (kapa vid 5 MB) + maskera token-värden** i loggen.
- [ ] **Omslag inbäddat i filerna** (ID3 APIC / MP4 covr) som alternativ till
      `cover.jpg`.
- [x] **Metadata-uppdatering av organiserade filer** — skanna outputmappen,
      jämför med Goodreads och bättra på taggar som ändrats/saknas — **byggd 2026-09-27 som krav 34 (se nedan).**
- [ ] **Bevaka nya utgåvor** — notis när en författare du har böcker av
      släpper nytt (polla Goodreads författarsida, max 1/dag).

Övriga förslag som ska bevakas:

- [x] Historik-fönster i GUI — byggd som krav 21 (flik "6. Historik").
- [ ] Kapitellista från m4b i .md-faktabladet.
- [ ] Parallell matchning (3 trådar med egen delay).
- [ ] Förhandsvisning före organisering (torrkörnings-dialog med Avbryt/Kör).
- [ ] Ångra senaste organiseringen (backa från loggens actions).
- [ ] Sökruta i Logg-fliken.
- [ ] Kortkommandon (Ctrl+S/Ctrl+O/Ctrl+L).
- [ ] Sorterbara kolumner (klick på rubrik) + zebrarandning/färgförklaring.
- [ ] CSV-export med statusfilter.
- [ ] Uppläsarsök + "samma uppläsare"-rekommendationer (Storytel).
- [ ] Varna vid avvikande ljudlängd (abridged vs unabridged).
- [ ] Importera redan organiserad ABS-struktur till historiken.
- [ ] Språkfilter/-bonus (föredra svenska utgåvor).
- [ ] Flera biblioteksprofiler (olika outputmappar/inställningar).
- [ ] Dra-och-släpp mapp i GUI.
- [ ] Omslagscache på disk (`~/.audiobro/ (legacy ~/.audiobro/)covers/`).
- [ ] Inkrementell skanning (bara nya/ändrade filer, mtime-cache).
- [ ] ETag/conditional requests i webbcachen.
- [ ] Lata importer för snabbare start.
- [ ] Atomära skrivningar av taggar (tempfil + rename).
- [ ] Skriv-och-verifiera (läs tillbaka taggar, återställ `.agsbak` vid avvikelse).
- [ ] Låsfil mot två samtidiga instanser.
- [ ] Windows-installer (Inno Setup kring PyInstaller-exen).
- [ ] Backup-knapp för `settings.json` + `history.json`.
- [ ] Automatisk uppdateringskoll (GitHub-releases).
- [ ] Audiobookshelf-API: pusha metadata direkt till ABS-servern (token).

Fler förslag (tillagda 2026-09-20, omgång 2 — ej byggda):

- [ ] **Anslutningstest & källstatus** — "Testa anslutning"-knapp som visar
      grön/röd status per källa (Goodreads, Storytel, BookBeat, Open Library)
      med svarstid; token-indikator i statusraden.
- [ ] **Token-timer** — hämta om token automatiskt var N:e timme så
      långa skanningar inte dör mitt i.
- [ ] **Automatiskt omförsök med backoff** — transienta nätverksfel och 429
      väntas ut (1s/4s/16s) i stället för att raden markeras som blockerad.
- [ ] **Egna korrigeringar (`overrides.json`)** — titel/serie/delnummer du
      själv skriver in tillämpas före all matchning (slår källorna).
- [ ] **Kö av flera importmappar** — lägg till mappar i en kö, kör en efter
      en med samma inställningar.
- [ ] **Önskelista** — spara rekommendationer, bocka av när boken är köpt;
      synkas in i "ägda" så den inte föreslås igen.
- [ ] **Tillgänglighet för rekommendationer** — markera om föreslagen bok
      finns på Storytel/BookBeat (API:erna är redan integrerade).
- [ ] **Sökruta + datumsortering i Historik-fliken.**
- [ ] **Historik-dedup** — slå ihop poster med samma titel+författare
      (t.ex. efter dubbelorganisering i olika mappar).
- [ ] **Loggexport** — "Spara logg som fil"-knapp + bifoga vid felsökning;
      "Öppna loggfilen" i filhanteraren.
- [ ] **Molnsynk** — valfri sökväg för `settings.json`/`history.json`
      (OneDrive/Dropbox) så flera datorer delar historik.
- [ ] **Kopieringsverifiering vid flytt** — jämför storlek/hash mellan källa
      och destination innan källfilen tas bort (move-läget).
- [ ] **Auto-organiseringsläge** — valfritt: organisera gröna rader direkt
      efter skanning utan extra klick (avstängt som standard).
- [ ] **Språkval i GUI** (svenska/engelska, alla strängar i en katalog).
- [ ] **Ignorera-lista** — markera filer/böcker som aldrig ska föreslås
      eller matchas igen (per filnyckel).

## Tekniska bindningar (beslut som ligger fast)

* Goodreads officiella API är nedlagt (dec 2020) → skrapning av publika sidor.
* Poängmodell: 0,62·titel + 0,30·författare + serie/del-bonus − straff;
  ≥0,88 = matchad, 0,62–0,88 = behöver koll. Straff: fel del i serien
  (−0,20, endast vid uttrycklig "Del/Bok/Vol N"-markör) och helt fel
  författare (−0,12). Bonus: undertitel räknas in i titeln, rätt
  utgivningsår (+0,02), popularitet (max +0,05). Uppläsarnamn i
  artist-taggen ("… inläst av X") ignoreras vid författarjämförelsen.
* Svenska titlar → originaltitel via Wikipedia-brygga innan Goodreads-sökning.
* Taggmappningar per format finns i `ags/tags.py` (kommenterade mot ABS).
