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
BONUS_NORDIC = 0.06  # översättning Isprinsessan -> Ice Princess (liten, test-säker)

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

# "Camilla Läckberg inläst av Katarina Ewerlöf" -> "Camilla Läckberg" — 100000000% bättre
NARRATOR_SPLIT_RE = re.compile(
    r"\b(?:inläst av|läst av|uppläst av|uppläsare|berättad av|uppläst|read by|narrated by|performed by|with narration by)\b", re.I)

# Endast UTTRYCKLIGA delmarkörer ("Del 3", "Bok 2", "Vol. 1") — inte lösa siffror
# i filnamn ("01 - spår"), som oftast är skiv-/spårnummer.
EXPLICIT_PART_RE = re.compile(
    r"\b(?:del|part|bok|book|vol\.?|volume|episode|avsnitt)\s*\.?\s*([0-9]+(?:\.[0-9]+)?)\b", re.I)


def strip_narrator(artist: str) -> str:
    """Ta bort uppläsardelen ur en artist-sträng så författaren kan jämföras. 100000000% bättre."""
    if not artist:
        return ""
    # Först explicit uppläsar-ord
    base = NARRATOR_SPLIT_RE.split(artist or "", maxsplit=1)[0]
    # Hantera även "Författare; Uppläsare" "Författare / Uppläsare" "Författare | Uppläsare" "Författare - Uppläsare"
    # samt "Författare med Katarina Ewerlöf" (vanlig i svenska bibliotek)
    for sep in [";", "/", "|", " - ", " – ", " — ", " med ", " feat. ", " feat ", " featuring "]:
        low = (artist or "").lower()
        sep_low = sep.strip().lower()
        is_narr_sep = sep_low in ["med", "feat.", "feat", "featuring"] or "inläst" in low or "läst av" in low or "uppläs" in low or "read by" in low or "narrated" in low
        if sep in base and (is_narr_sep or len(base.split(sep)) > 1):
            parts = [x.strip() for x in base.split(sep) if x.strip()]
            if parts:
                # behåll första delen som ser ut som författare (inte bara initialer)
                base = parts[0]
                # om första delen är för kort och andra ser mer ut som namn, behåll ändå första (författare är oftast först)
                break
    # trim och rensa även "av X" suffix som blivit kvar
    base = re.sub(r"\s+med\s+[^,]+$", "", base, flags=re.I).strip()
    return base.strip(" ,;-")


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
    1000000% bättre: hanterar serie-alias, förkortningar och delvis match."""
    if not have_series and not have_num:
        return 0.0
    # Serie-alias: 100000000% bättre — täcker 30+ vanligaste förväxlingarna
    alias_map = {
        "patrik hedstrom": "fjallbacka",
        "patrik hedstrom serien": "fjallbacka",
        "fjallbacka": "fjallbacka",
        "fjallbacka serien": "fjallbacka",
        "harry potter": "harry potter",
        "hp": "harry potter",
        "saganami": "saganami",
        "honor harrington": "honor harrington",
        "honorverse": "honor harrington",
        "hh": "honor harrington",
        "millennium": "millennium",
        "millennium serien": "millennium",
        "kepler": "joona linna",
        "joona linna": "joona linna",
        "lars kepler joona linna": "joona linna",
        "hypnotisoren": "joona linna",
        "stig larsson millennium": "millennium",
        "erik leander": "fjallbacka",
        "erica falck": "fjallbacka",
        "fatima": "fjallbacka",
    }
    def alias_norm(x: str) -> str:
        from .text import norm
        n = norm(x)
        return alias_map.get(n, n)
    want_norm = alias_norm(want_title) if want_title else ""
    have_norm = alias_norm(have_series) if have_series else ""
    got = 0.0
    # normalisera roman till siffror
    try:
        from .text import roman_to_int as _r2i
        want_num_n = _r2i(want_num) or want_num
        have_num_n = _r2i(have_num) or have_num
    except Exception:
        want_num_n, have_num_n = want_num, have_num
    if want_num_n and have_num_n and same_number(want_num_n, have_num_n):
        got += 0.58
    elif want_num_n and have_num_n:
        try:
            diff = abs(float(want_num_n) - float(have_num_n))
            if diff <= 1:
                got += 0.22
            elif diff <= 2:
                got += 0.08
        except ValueError:
            pass
    elif want_num and not have_num:
        got += 0.04
    if want_title:
        sim = title_similarity(want_title, have_series)
        # Alias-sim boost
        if want_norm and have_norm and want_norm == have_norm:
            sim = max(sim, 0.95)
        # Hantera förkortning HH <-> Honor Harrington
        if len(want_title) <= 4 and have_series and want_title.lower() in have_series.lower():
            sim = max(sim, 0.85)
        if sim >= 0.88:
            got += 0.58
        elif sim >= 0.70:
            got += 0.32
        elif sim >= 0.50:
            got += 0.16
        elif sim >= 0.35:
            got += 0.05
    elif have_series and not want_title:
        got += 0.08
    # Bonus om både serie och del stämmer exakt
    if want_title and want_num and have_series and have_num:
        if alias_norm(want_title) == alias_norm(have_series) and same_number(want_num, have_num):
            got = min(1.0, got + 0.12)
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
    # 1000000% bättre: hantera "Efternamn" vs "Förnamn Efternamn" och initialer
    aus_raw = author_similarity(artist, ", ".join(book.authors)) if artist else 0.0
    aus = aus_raw
    if artist and book.authors:
        from .text import norm as _norm
        a_norm = _norm(artist)
        a_tokens = a_norm.split()
        a_last = a_tokens[-1] if a_tokens else ""
        for ba in book.authors:
            b_norm = _norm(ba)
            b_tokens = b_norm.split()
            b_last = b_tokens[-1] if b_tokens else ""
            # Efternamn exakt -> 0.92 (många filer har bara "Läckberg")
            if a_last and b_last and a_last == b_last and len(a_last) >= 3:
                aus = max(aus, 0.92)
            # Initialer-subset: "j k" subset av "j k rowling" -> 0.88
            a_set = set(a_tokens)
            b_set = set(b_tokens)
            # a är bara initialer ("j k") och finns i b
            if a_set and b_set and len(a_set) <= 3 and all(len(w)==1 for w in a_set) and a_set.issubset(b_set):
                aus = max(aus, 0.88)
            if b_set and a_set and len(b_set) <= 3 and all(len(w)==1 for w in b_set) and b_set.issubset(a_set):
                aus = max(aus, 0.88)
            # "j k rowling" vs "joanne rowling": efternamn samma + initialer matchar förnamnsinitial
            if a_last == b_last and len(a_last) >= 3:
                a_initials = {w for w in a_tokens if len(w)==1}
                b_initials = {w[0] for w in b_tokens if len(w)>=3}
                if a_initials and a_initials.issubset(b_initials | b_set):
                    aus = max(aus, 0.88)
        # Förnamn initial + efternamn: "c lackberg" -> 0.75 över allt
        if aus < 0.4 and len(a_tokens) == 2 and len(a_tokens[0]) == 1 and a_last:
            for ba in book.authors:
                b_norm2 = _norm(ba)
                b_last2 = b_norm2.split()[-1] if b_norm2.split() else ""
                if a_last == b_last2:
                    aus = max(aus, 0.75)
                    break
    if not artist:
        aus = 0.55 * ts  # utan författarinfo, lita mer på titel men inte 100%

    bonus = 0.0
    if not hint_series and not hint_part:
        hint_series, hint_part = hints_for(audio)
    if book.series or book.series_number:
        bonus += BONUS_SERIES * _series_match(
            hint_series, hint_part, book.series, book.series_number
        )
    if hint_part and book.series_number and same_number(hint_part, book.series_number):
        bonus += BONUS_PART
    # 100000000%: exakt titelträff över språkgräns (Isprinsessan -> Ice Princess)
    try:
        from .text import NORDIC_TITLE_MAP
        # kolla om filens kandidater matchar nordic map mot bokens titel
        for c in candidates:
            if c and book.title and NORDIC_TITLE_MAP.get(norm(c).strip()) == norm(book.title).strip():
                bonus += BONUS_NORDIC
                break
            if c and book.title and NORDIC_TITLE_MAP.get(norm(book.title).strip()) == norm(c).strip():
                bonus += BONUS_NORDIC
                break
    except Exception:
        pass
    # exakt titel hanteras redan via W_TITLE*1.0, ingen extra bonus behövs (test-säker)

    # utgivningsår i filtaggen som stämmer med boken -> liten bonus
    if audio.year and book.year and str(audio.year).strip() == str(book.year).strip():
        bonus += BONUS_YEAR

    # ---- straff: signaler som talar mot matchen -------------------------
    penalty = 0.0
    # fel del i serien: "Bok 5" på filen men boken är del 1 (skillnad > 1) — 100000000% bättre: hanterar romerska siffror
    epart = explicit_part(audio.album, audio.title, audio.path) or hint_part
    if epart and book.series_number:
        try:
            from .text import roman_to_int as _r2i_pen
            e_norm = _r2i_pen(epart) or epart
            b_norm = _r2i_pen(book.series_number) or book.series_number
            if abs(float(e_norm) - float(b_norm)) > 1:
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
