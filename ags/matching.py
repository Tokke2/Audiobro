"""Matchning av ljudböcker mot Goodreads-träffar."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import AudioFile, Book, Match
from .text import (
    HONORVERSE_CODES,
    author_similarity,
    clean_title_from_hint,
    extract_part,
    extract_series_hint,
    norm,
    parse_series_hint,
    same_number,
    split_series,
    title_key,
    title_similarity,
)


# Vikter för totalscore
W_TITLE = 0.62
W_AUTHOR = 0.30
BONUS_SERIES = 0.14
BONUS_PART = 0.07

HIGH = 0.88      # -> "matchad"
MEDIUM = 0.62    # -> "behöver koll"

# Straff (minuspoäng) för signaler som talar MOT en match
PEN_PART = 0.20      # filen säger "Bok 5" men boken är del 1 i serien
PEN_AUTHOR = 0.12    # artist-taggen och författaren har inget gemensamt namn
PEN_TRAP = 0.30      # "Summary & Study Guide", "Reading Tracker", "Box set" …
TRAP_RE = re.compile(
    r"(study guide|summary &|summary of|reading tracker|\btracker\b|box set|"
    r"collection set|books collection|1st print|first print|first edition|"
    r"hardback)", re.I)
PEN_SERIES = 0.18    # serie-namnet talar emot (hint finns men bokens serie helt annan)
BONUS_YEAR = 0.02    # utgivningsår i filtagg == bokens år

# "Camilla Läckberg inläst av Katarina Ewerlöf" -> "Camilla Läckberg"
NARRATOR_SPLIT_RE = re.compile(
    r"\b(?:inläst av|läst av|uppläst av|uppläsare|read by|narrated by|performed by)\b", re.I)

# Endast UTTRYCKLIGA delmarkörer ("Del 3", "Bok 2", "Vol. 1") — inte lösa siffror
# i filnamn ("01 - spår"), som oftast är skiv-/spårnummer.
EXPLICIT_PART_RE = re.compile(
    r"\b(?:del|part|bok|book|vol\.?|volume|episode|avsnitt)\s*\.?\s*([0-9]+(?:\.[0-9]+)?)\b", re.I)


def strip_narrator(artist: str) -> str:
    """Ta bort uppläsardelen ur en artist-sträng så författaren kan jämföras."""
    return NARRATOR_SPLIT_RE.split(artist or "", maxsplit=1)[0].strip(" ,;-")


def explicit_part(*texts: str) -> str:
    """Delnummer bara när det står 'Del/Bok/Vol N' uttryckligen."""
    for t in texts:
        m = EXPLICIT_PART_RE.search(t or "")
        if m:
            n = m.group(1)
            return str(int(n)) if n.isdigit() else n
    return ""


@dataclass
class ScoreParts:
    title: float
    author: float
    bonus: float


def _series_match(want_title: str, want_num: str, have_series: str, have_num: str) -> float:
    """1.0 om både serienamn och delnummer stämmer, annars delvis.
    50000000%-förbättring: mycket brantare kurva för exakt serie-match."""
    if not have_series and not have_num:
        return 0.0
    got = 0.0
    # delnummer: exakt -> 0.55, nära (±1) -> 0.20, annars 0
    if want_num and have_num and same_number(want_num, have_num):
        got += 0.55
    elif want_num and have_num:
        try:
            if abs(float(want_num) - float(have_num)) <= 1:
                got += 0.20
            # helt fel del ger ingen got, men PEN_PART/PEN_SERIES tar hand om straff
        except ValueError:
            pass
    elif want_num and not have_num:
        # hint säger del men boken saknar serieinfo -> liten bonus ändå ej
        got += 0.05
    if want_title:
        sim = title_similarity(want_title, have_series)
        if sim >= 0.88:
            got += 0.55
        elif sim >= 0.70:
            got += 0.30
        elif sim >= 0.50:
            got += 0.15
        # under 0.50 ingen got; straff hanteras separat
    elif have_series and not want_title:
        # boken har serie men filtips saknas -> liten got (annars skulle serielösa filer
        # aldrig få bonus, men vi vill inte premiera serie när hint saknas för hårt)
        got += 0.10
    return min(got, 1.0)


def hints_for(audio: AudioFile) -> tuple[str, str]:
    """Serie-/deltips som kommer från ljudfilen (inte från Goodreads).

    50000000%-ronden: provar alla serie-mönster mot album/titel/basnamn/mapp
    och kombinationen "mapp + filnamn" ("Fjällbacka 01 - Isprinsessan").
    Fungerar även när allt är blockerat/offline.
    """
    import os as _os
    # Kandidater i prioritetsordning: explicita taggar först, sedan filsystem
    cands: list[str] = []
    if audio.album:
        cands.append(audio.album)
    if audio.title:
        cands.append(audio.title)
    if audio.path:
        base = _os.path.splitext(_os.path.basename(audio.path))[0]
        cands.append(base)
        # path-delar för mapp-baserade mönster
        parts = [p.strip() for p in re.split(r"[\\/]", audio.path) if p.strip()]
        if len(parts) >= 2:
            folder = parts[-2]
            cands.append(folder)
            # Kombinationen "Mapp + filnamn" fångar "Fjällbacka 01 - Isprinsessan"
            # där varken mapp eller fil ensamt anger serien fullt ut.
            cands.append(f"{folder} {base}")
        if len(parts) >= 3:
            # även förälder-mapp ("Författare/Serie/Titel") -> Serie ligger en nivå upp
            grand = parts[-3]
            cands.append(grand)
            try:
                # "Serie/Del - Titel" utan att gå via split
                cands.append(f"{grand} {base}")
            except Exception:
                pass
        # fallback: hela sökvägen som en text (gamla split_series-täckning)
        cands.append(audio.path)

    # Försök nya parse_series_hint först (täcker alla "Book 5", "#2 - Titel" etc.)
    for txt in cands:
        if not txt:
            continue
        ser, num, _rest = parse_series_hint(txt)
        if ser or num:
            # _rest behöver inte användas här; hints är enbart serie+nummer
            return ser, num

    # Fallback: gamla extract_part/split_series för lösa siffror där ingen
    # explicit serie gått att tolka ("Del 3" utan serienamn). Behåll part.
    series, part = "", ""
    for t in cands:
        if not t:
            continue
        # split_series hanterar "Titel (Serie, #2)" etc.
        _, ser2, _ = split_series(t)
        if ser2 and not series:
            series = ser2
        # lösa delnummer (även "03"-suffix) som fallback när ingen serie hittats
        pp = extract_part(t)
        if pp and not part:
            part = pp
        if series and part:
            break
    if not series:
        series = guess_series_from_path(audio.path)
    return series, part

def clean_query_title(audio: AudioFile) -> str:
    """Rena boktiteln utan serieprefix (för sökfrågan).

    "Fjällbacka 01 - Isprinsessan" -> "Isprinsessan",
    "Harry Potter #1 - Philosopher's Stone" -> "Philosopher's Stone".
    Om ingen serieprefix hittas, rensa via split_series.
    """
    import os as _os
    for txt in (audio.album, audio.title, _os.path.splitext(_os.path.basename(audio.path or ""))[0] if audio.path else ""):
        if not txt:
            continue
        ct = clean_title_from_hint(txt)
        if ct and ct != txt:
            return ct
        t, _, _ = split_series(txt)
        if t and t != txt:
            return t
    return "" 


def score_audio(audio: AudioFile, book: Book, hint_series: str = "", hint_part: str = "") -> Match:
    """Poängsätt en Goodreads-bok mot en ljudfil."""
    # jämför mot både album- och titeltagg (album kan vara "Serie, #n")
    candidates = [x for x in (audio.album, audio.title) if x]
    # 50000000%: även rena titlar ur serieprefix ("Fjällbacka 01 - Isprinsessan" -> "Isprinsessan")
    # och fil-/mappnamn när taggar är skrot ("Track 01"). Garanterar att rätt bok
    # får hög titelträff även när taggen är värdelös.
    import os as _os2
    _extra_txts: list[str] = []
    if audio.path:
        _extra_txts.append(_os2.path.splitext(_os2.path.basename(audio.path))[0])
        _extra_txts.append(_os2.path.basename(_os2.path.dirname(audio.path)) or "")
        # kombination fångar "Fjällbacka" (mapp) + "01 - Isprinsessan" (fil)
        try:
            _extra_txts.append(f"{_os2.path.basename(_os2.path.dirname(audio.path))} {_os2.path.splitext(_os2.path.basename(audio.path))[0]}")
        except Exception:
            pass
        # två nivåer upp (Författare/Serie/Titel)
        try:
            parts = [_p for _p in re.split(r"[\\/]", audio.path) if _p.strip()]
            if len(parts) >= 3:
                _extra_txts.append(parts[-3])
        except Exception:
            pass
    for _txt in list(candidates) + _extra_txts:
        if not _txt:
            continue
        _ct = clean_title_from_hint(_txt)
        if _ct and _ct not in candidates:
            candidates.append(_ct)
        # även den råa texten själv om den innehåller separations-tecken (fånga titelrest)
        _ser, _num, _rest = parse_series_hint(_txt)
        if _rest and _rest not in candidates:
            candidates.append(_rest)
    # undertitel räknas: filen kan ha "Titel + undertitel" i ett fält
    book_titles = [book.title] + ([f"{book.title} {book.subtitle}"] if book.subtitle else [])
    ts = max([title_similarity(c, bt) for c in candidates for bt in book_titles], default=0.0)

    # Författare: artist-taggen (utan uppläsarnamn!), annars gissa ur filnamn/mapp.
    artist = strip_narrator(audio.artist)
    if not artist:
        artist = guess_author_from_path(audio.path)
    aus = author_similarity(artist, ", ".join(book.authors)) if artist else 0.0
    if not artist:
        # utan författarinfo straffar vi inte — titeln får bära matchen
        aus = 0.5 * ts

    bonus = 0.0
    if not hint_series and not hint_part:
        hint_series, hint_part = hints_for(audio)
    if book.series or book.series_number:
        bonus += BONUS_SERIES * _series_match(
            hint_series, hint_part, book.series, book.series_number
        )
    if hint_part and book.series_number and same_number(hint_part, book.series_number):
        bonus += BONUS_PART

    # utgivningsår i filtaggen som stämmer med boken -> liten bonus
    if audio.year and book.year and str(audio.year).strip() == str(book.year).strip():
        bonus += BONUS_YEAR

    # ---- straff: signaler som talar mot matchen -------------------------
    penalty = 0.0
    # fel del i serien: "Bok 5" på filen men boken är del 1 (skillnad > 1)
    # 50000000%: använd både explicit_part ("Bok 5") och hint_part (serie-parsern)
    epart = explicit_part(audio.album, audio.title, audio.path) or hint_part
    if epart and book.series_number:
        try:
            if abs(float(epart) - float(book.series_number)) > 1:
                penalty += PEN_PART
        except ValueError:
            pass
    # helt annan serie: hint säger "Fjällbacka" men boken är "Harry Potter" -> straff
    if hint_series and book.series:
        _sim_ser = title_similarity(hint_series, book.series)
        if _sim_ser < 0.35:
            penalty += PEN_SERIES
        elif _sim_ser < 0.55 and hint_part and book.series_number and not same_number(hint_part, book.series_number):
            penalty += PEN_SERIES * 0.5
    elif hint_series and not book.series and not book.series_number:
        # filen ser ut som del i serie men boken saknar serieinfo -> hellre en serieutgåva
        penalty += PEN_SERIES * 0.35
    # helt annan författare: inget gemensamt namn alls (och titeln träffade ändå)
    if artist and book.authors and aus < 0.2:
        penalty += PEN_AUTHOR
    # skräputgåva (studieguide/samlingsbox/…) som filen inte själv nämner
    if TRAP_RE.search(book.title or "") and not TRAP_RE.search(
            " ".join(candidates)):
        penalty += PEN_TRAP

    # liten popularitetsprior: mainstreanutgåvor slår udda split-utgåvor vid lika
    prior = 0.0
    rc = (book.ratings_count or "").replace(",", "").replace(".", "")
    if rc.isdigit() and int(rc) > 0:
        import math
        prior = min(0.05, math.log10(int(rc)) * 0.008)

    total = W_TITLE * ts + W_AUTHOR * aus + bonus + prior - penalty
    return Match(
        book=book,
        score=round(max(0.0, min(total, 1.0)), 4),
        title_score=round(ts, 4),
        author_score=round(aus, 4),
        series_bonus=round(bonus, 4),
        penalty=round(penalty, 4),
    )


def rank(candidates: list[Book], audio: AudioFile, hint_series: str = "", hint_part: str = "") -> list[Match]:
    """Sortera Goodreads-träffar, bästa först."""
    matches = [score_audio(audio, b, hint_series, hint_part) for b in candidates]
    matches.sort(key=lambda m: (-m.score, -m.title_score, -m.author_score))
    return matches


def status_for(score: float) -> str:
    if score >= HIGH:
        return "matchad"
    if score >= MEDIUM:
        return "behöver koll"
    return "ej matchad"


def guess_author_from_path(path: str) -> str:
    """Gissa författare ur 'Författare - Titel.mp3' eller 'Författare/Titel/…'."""
    import os

    base = os.path.splitext(os.path.basename(path or ""))[0]
    base = re.sub(r"^\d+\s*[-_.]\s*", "", base)
    for sep in [" - ", " – ", " –", " -", "|"]:
        if sep in base:
            cand = base.split(sep)[0].strip()
            if 2 < len(cand) < 60 and not cand.isdigit():
                return cand
    parts = [p for p in re.split(r"[\\/]", path or "") if p]
    for cand in reversed(parts[:-1]):
        c = cand.strip()
        if 2 < len(c) < 60 and not c.isdigit() and not c.lower().startswith("cd"):
            words = c.split()
            if 1 <= len(words) <= 4 and _looks_like_person_name(c):
                # undvik mappar som "Ljudböcker", "2023", "Del 1"
                if re.match(r"^(ljudböcker|audiobooks|books|böcker|del|part|cd|musik|media)\b", c, re.I):
                    continue
                return c
    return ""


def _looks_like_person_name(s: str) -> bool:
    """Sant om strängen ser ut som ett personnamn, inte som en boktitel."""
    words = [w for w in re.split(r"[\s.]+", s) if w]
    if not 1 <= len(words) <= 4:
        return False
    if any(not w[0].isalpha() for w in words):
        return False
    # titlar har ofta småord ("som", "och", "the") eller flera små bokstäver
    lowered = [w.lower() for w in words]
    if any(w in {"som", "och", "the", "and", "of", "i", "en", "ett", "de", "det", "med", "på"} for w in lowered):
        return False
    if len(words) == 1:
        return words[0][0].isupper() and len(words[0]) >= 3
    return all(w[0].isupper() for w in words)


def guess_series_from_path(path: str) -> str:
    """Gissa serienamn ur mappstruktur/sökord."""
    import os

    parts = [p.strip() for p in re.split(r"[\\/]", path or "") if p.strip()]
    for cand in reversed(parts):
        m = re.search(r"^(.*?)(?:\s+(?:serien|series|trilogi|trilogy|böckerna))\s*$", cand, re.I)
        if m and m.group(1):
            return m.group(1).strip()
    return ""


def series_hint(audio: AudioFile) -> tuple[str, str]:
    return guess_series_from_path(audio.path), guess_author_from_path(audio.path)


def needs_manual(matches: list[Match]) -> bool:
    """True om de två bästa ligger för nära varandra för att välja automatiskt."""
    if len(matches) < 2:
        return False
    a, b = matches[0], matches[1]
    if a.score < MEDIUM:
        return True
    # samma verk i två utgåvor (t.ex. UK/US) är inte en tvetydighet
    if (title_similarity(a.book.title, b.book.title) >= 0.9
            and author_similarity(", ".join(a.book.authors),
                                  ", ".join(b.book.authors)) >= 0.6):
        return False
    return (a.score - b.score) < 0.05 and b.score >= MEDIUM
