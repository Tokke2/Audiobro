# 🌉 Audiobro — Goodreads → Audiobookshelf ✨📚

> **Kravspecifikationen finns i [SPEC.md](SPEC.md)** — ackumulerade krav,
> avgränsningar och chatt-arbetsflöde (inkl. regeln att uppdaterade filer
> alltid länkas klickbart i varje svar).

Ett Python-verktyg som synkar metadata för dina ljudboksfiler mot **Goodreads**:
**titel, författare, serie och delnummer i serien** (plus album, år och spårnummer)
— och **organiserar dem för Audiobookshelf** med namngivna mappar och filer:

```
Outputmapp/
└── Camilla Läckberg/
    └── Patrik Hedström/
        └── 01 - Isprinsessan/          ← delnummer först = rätt sorteringsordning
            ├── 01 - Isprinsessan.mp3   (CD1+CD2 sammanfogade, spår 1–6)
            ├── …
            ├── 06 - Isprinsessan.mp3
            └── Isprinsessan.md         (faktablad: bokinfo + ljudkvalitet)
```

Svenska titlar hanteras: appen hittar originaltiteln via Wikipedia och slår upp
boken på Goodreads. Fungerar även **utan uppkoppling** via inklistrad text.

```
pip install -r requirements.txt
python -m ags.gui            # desktop-GUI (tkinter)
```

## Inställningar som minnas

Mappar och inställningar (import/output, kryssrutor, fördröjning, albumstil)
sparas i `~/.audiobro/settings.json (legacy ~/.audiobro/ (legacy ~/.audiobook-goodreads/)settings.json)` och läsas in vid start.
Menyn **"Kom ihåg"** listar dina senaste import- och outputmappar (klickbara)
samt "Spara inställningar nu". Knappen **"Öppna outputmapp"** öppnar mappen
direkt i filhanteraren.

## Starta med dubbelklick (utan konsolfönster)

| Plattform | Fil |
|-----------|-----|
| Windows | `starta.bat` (använder `pythonw` — inget svart fönster) |
| macOS | `starta.command` |
| Linux | `starta.sh` |
| Fristående .exe/.app | `pip install pyinstaller && python scripts/build_exe.py` |

## Flikarna i GUI:t

| Flik | Vad den gör |
|------|-------------|
| **1. Skanna & organisera** | Välj **importmapp** och **outputmapp**. Skannar rekursivt efter `.mp3 .m4b .m4a .flac .ogg .opus`, grupperar filer per ljudbok (**slår ihop CD1/CD2-mappar**), matchar mot Goodreads och visar förslagen i en tabell. Gröna rader skrivs med ett klick; **"Organisera"** bygger Audiobookshelf-strukturen i outputmappen (kopierar som standard, kryssrutan *Flytta* gör den destruktiv). Osäkra rader **frågar alltid innan** de organiseras. |
| **2. Enskild titel / länk** | Slår upp en enstaka bok. Du kan också klistra in en **Goodreads-länk** direkt — då används exakt den boken, ingen gissning. |
| **3. Skärmbild / text** | Reservläget: välj en skärmbild (kräver `tesseract`) eller klistra in texten från bilden; varje titel tolkas och matchas. |
| **4. Rekommendationer** | Föreslår böcker du kanske gillar: **nästa del i serier** du följer och fler böcker av författarna i din samling/historik (böcker du redan har filtreras bort; samlingsboxar hoppas över). |
| **5. Logg** | Livetail av `ags.log` — allt som händer (och inte händer) för felsökning. |

## Så flyttar du gröna rader till outputmappen

1. Skanna → gröna rader är säkra matchningar (sorterade i serieordning).
2. Klicka **"Organisera gröna + OK-frågade"** (eller markera rader och välj
   *"Organisera valda → output"*). Osäkra rader frågas alltid först.
3. Med kryssrutan **"Flytta filerna"** flyttas filerna ur importmappen, annars
   kopieras de. Allt skrivs med ny metadata: namngivna mappar/filer, taggar
   (serie, uppläsare, beskrivning …), `cover.jpg` och `.md`-faktablad.
4. Klara böcker hamnar i historiken och hoppas över nästa gång. En rad som
   redan organiserats kan inte organiseras två gånger (skydd mot dubbelkörning).
5. **Dublettskydd:** finns samma titel+författare redan i outputmappen frågas
   du innan något organiseras (CLI: varning + hoppa över, `--force` kör ändå).

> **`.över`-filer:** om målfilen redan finns sparas den gamla undan som
> `*.över` så inget skrivs sönder. Råkade en körning avbrytas/dubbelköras så
> att bara en `.över`-fil blev kvar, **återställs den automatiskt** nästa gång
> (eller döp om den manuellt: `X.m4b.över` → `X.m4b`).

## Historik — aldrig dubbelarbete

Varje organiserad bok läggs i `~/.audiobro/history.json (legacy ~/.audiobro/ (legacy ~/.audiobook-goodreads/)history.json)`. Vid nästa
skanning markeras den `[==] klar (historik)` och hoppas över (kryssrutan
*Hoppa över redan klara* / `--no-skip-done` styr detta). Med `--move` flyttas
filerna ur importmappen så de inte kan skannas igen.

## Multi-disc: CD1 + CD2 = en bok

Filer i `…/Titel/CD1/` (spår 1–12) och `…/Titel/CD2/` (spår 1–12) känns igen som
**samma bok** (`cd 1`, `cd-2`, `disc 3`, `skiva 1` … i mapp- eller filnamn).
Vid organisering hamnar allt i titelmappen med **fortsatt numrering**:
CD2:s första spår blir `13 - Titel.mp3`, och taggarna får `track 13/24`.

## Kommandorad

```bash
# torrkörning: se vad som skulle ändras
python -m ags.cli scan ~/Ljudböcker

# skriv taggarna (säkerhetskopior sparas som *.agsbak)
python -m ags.cli scan ~/Ljudböcker --apply

# organisera för Audiobookshelf (kopiera) + skriv .md-faktablad
python -m ags.cli scan ~/Ljudböcker --apply --output ~/audiobooks

# flytta i stället för att kopiera, och fråga vid osäkra matchningar
python -m ags.cli scan ~/Ljudböcker --apply --output ~/audiobooks --move --interactive

# rekommendationer utifrån historiken
python -m ags.cli recommend

# enstaka titel, visa alla träffar med poäng
python -m ags.cli match "Män som hatar kvinnor" -a "Stieg Larsson" --all

# matcha via Goodreads-länk
python -m ags.cli match --url "https://www.goodreads.com/book/show/13496"

# skärmbildsläge (tesseract) eller inklistrad text
python -m ags.cli ocr skärmbild.png
```

## Tilläggskontroll vid start

Vid start (och via knappen **"Kontrollera tillägg"** / `python -m ags.cli deps`)
kontrolleras att allt som behövs finns: `requests`, `mutagen`,
`websocket-client` och `tesseract`. Saknas ett pip-paket **erbjuder appen att
installera det direkt** (den kör `pip` själv); för tesseract visas
installationslänken för ditt operativsystem. Appen startar ändå, men talar då
tydligt om vad som fattas och vad det behövs för.

## Loggen

Allt loggas till `~/.audiobro/ags.log (eller <app>/logs/ags.log + legacy ~/.audiobro/ (legacy ~/.audiobook-goodreads/)ags.log)` (DEBUG-nivå): varje
Goodreads-anrop med statuskod, blockeringar **inklusive om en token
skickades**, vilka reservkällor som prövades och med hur många träffar, samt
per bok en rad som förklarar resultatet, t.ex.

```
WARNING ags.goodreads: Blockad: …/search?q=… (HTTP 202, challenge) | Goodreads-token: ej satt. Orsak: Goodreads skydd …
INFO ags.engine.match: reservkälla gav 1 träffar för 'Isprinsessan …' (källa=storytel)
INFO ags.engine: matchning 'Isprinsessan' -> matchad (källa=goodreads, poäng=1.00) …
WARNING ags.engine: matchning 'Okänd bok' -> blockerad. Orsak: Inga träffar …
``` Fliken *Logg* i GUI:t visar de senaste raderna live;
knappen *Öppna loggfilen* öppnar hela filen.

## Vad som skrivs i filerna

| Fält (som Audiobookshelf läser) | MP3 (ID3) | M4B/M4A (MP4) | FLAC/OGG (Vorbis) |
|------|-----------|---------------|-------------------|
| Titel | `TIT2` | `©nam` | `TITLE` |
| Författare | `TPE1` | `©ART` | `ARTIST` |
| Album | `TALB` = "Serie, #n" (eller titeln) | `©alb` | `ALBUM` |
| Serie | `TXXX:SERIES` | `----:com.apple.iTunes:SERIES` | `SERIES` |
| Del i serie | `TXXX:SERIES_PART` + `SERIES-PART` | båda varianterna | `SERIES_PART` |
| **Uppläsare** (ABS: composer) | `TCOM` | `©wrt` | `COMPOSER` |
| **Beskrivning** | `COMM` | `©des` | `DESCRIPTION` |
| **Undertext** | `TIT3` | `----:…:SUBTITLE` | `SUBTITLE` |
| **Förlag** | `TPUB` | `©pub` | `PUBLISHER` |
| **Genre** | `TCON` | `©gen` | `GENRE` |
| **Språk** | `TLAN` | `----:…:LANGUAGE` | `LANGUAGE` |
| **ASIN / ISBN** | `TXXX:ASIN` / `TXXX:ISBN` | `----:…:ASIN` / `ISBN` | `ASIN` / `ISBN` |
| År | `TDRC` | `©day` | `DATE` |
| Spår | `TRCK` = n/total för flerdelade | `trkn` | `TRACKNUMBER`+`TRACKTOTAL` |
| **Omslag** | `cover.jpg` i titelmappen (läses av ABS) | samma | samma |

Mappningen är verifierad mot Audiobookshelfs egen källkod
(`server/scanner/AudioFileScanner.js` + `server/utils/prober.js`): uppläsare
läses via composer-Taggen, beskrivning via description/comment osv. Uppläsare,
förlag och språk finns inte på Goodreads — de fylls när reservkällorna
(Storytel/BookBeat) används; beskrivning, genrer och omslag hämtas även från
Goodreads boksidor.

Innan något skrivs kopieras originalfilen till `<namn>.agsbak` (kan stängas av med
`--no-backup`). Inget skrivs alls vid torrkörning.

## Goodreads och bot-skyddet — och lösningen med din egen webbläsare

Goodreads officiella API lades ner i december 2020, så appen läser de publika
sidorna. När Goodreads är tillfälligt hårt belastat kan en vanlig skript-klient
få ett blockerings-svar. **Men en riktig webbläsare kan** — och det utnyttjar
appens upplåsningsläge:

```bash
python -m ags.cli --auto-token scan ~/Ljudböcker     # CLI
python -m ags.cli token                              # skriv ut en token manuellt
```

1. Vid blockering startar appen din **Brave** (i andra hand Chromium/Chrome/Edge)
   *headless* med en tillfällig profil och öppnar goodreads.com.
2. Webbläsaren löser JS-utmaningen på några sekunder och sparar resultatet i
   en temporär cookie från din egen webbläsare.
3. Appen läser ut cookien via DevTools-protokollet (fungerar på alla OS, även när
   profilkakan är krypterad) och återanvänder den i sina egna requests.
4. Webbläsaren stängs. Inget skickas någon annanstans; profilen slängs.

Vid hög belastning: utan token 0 träffar — med token från din webbläsare 20 träffar.

I GUI:t finns kryssrutan **"Lås upp via min webbläsare (Brave/Chromium) vid
blockering"** (på som standard). Kråver `websocket-client` (ingår i
requirements.txt).

Övriga lager när upplåsning inte används/inte behövs:

1. **Känner av blockeringen** och visar tydligt vad som händer,
2. **backar av automatiskt** (standard 1,2 s mellan anrop, justeras i GUI:t eller
   med `--delay`),
3. **cacher alla svar** i `~/.audiobro/ (legacy ~/.audiobook-goodreads/)` så samma bok aldrig hämtas två gånger,
4. **byter källa automatiskt** — reservkedjan: **Storytel** (seriedata även för
   svenska titlar) → **BookBeat** (svensk katalog) → **Open Library** (engelsk,
   bra för originaltitlar). Alla tre är nyckelfria API:er. Stäng av
   Storytel/BookBeat med `--no-nordic`, eller hela kedjan med `--no-fallback`.
5. kan **låsas upp manuellt** med en token du kopierar från din vanliga
   webbläsare (F12 → Application → Cookies → `Goodreads-token`),
6. och har förstås **skärmbildsläget** som inte behöver Goodreads alls.

## Matchningslogiken i korthet

* Sökfrågan rensas: skräptaggar som "okänd/Unknown/N/A" tas bort, serieparenteser
  "(Millennium, #1)" och delnummer plockas ur titel/filnamn och används som *hints*.
* Poäng = 0,62 · titellikhet + 0,30 · författarlikhet + bonus när serie **och**
  delnummer stämmer. ≥ 0,88 räknas som *matchad*, 0,62–0,88 som *behöver koll*.
* Flerdelade ljudböcker grupperas (samma album+artist, **över disc-mappar**) och
  får spårnummer n/total med disc 2 fortsättande efter disc 1.
* Tvekan mellan två lika bra träffar → status *behöver koll* så att du väljer
  själv (GUI: "Välj bra träff…"; CLI: `--interactive`). Osäkra rader organiseras
  aldrig utan din bekräftelse.
* Serieböcker sorteras efter delnummer: titelmappen heter `01 - Titel`,
  `02 - Titel` … (halvdelar som 2.5 fungerar) och GUI-tabellen sorteras
  automatiskt författare → serie → del → titel när skanningen är klar.
* Redan klara böcker (historiken) markeras `[==]` och kräver inga nya uppslag.

## Testa

```bash
pip install pytest
python -m pytest tests/ -q        # offline: 74 test mot sparad Goodreads-HTML
DISPLAY=:99 python -m pytest      # kör även GUI-testet (kräver X-skärm/Xvfb)
python scripts/gui_demo.py --root ~/någon-mapp --out docs/gui.png
```

Testerna behöver **ingen uppkoppling**: de körs mot sparad HTML från Goodreads
(`tests/fixtures/`). Live-test av hela kedjan: `python -m ags.cli scan <mapp>`.

## Begränsningar

* Goodreads är en engelsk index: svenska titlar matchas via originaltitel
  (Wikipedia-bryggan) eller via reservkällan Open Library.
* Serie-metadata i MP3 lagras i TXXX-ramar; spelare som bara läser standardramar
  visar i stället albumet ("Serie, #n").
* Skrivstöd: MP3, M4B/M4A, FLAC, OGG/OPUS. Andra format läses men skrivs inte.
* OCR-kvaliteten beror på skärmbildens upplösning — inklistrad text är alltid
  säkrare.
