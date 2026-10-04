"""Textnormalisering och fuzzy-matchning (title/author/serie)."""
from __future__ import annotations

import re
import unicodedata

try:
    from rapidfuzz import fuzz

    def ratio(a: str, b: str) -> float:
        return fuzz.ratio(a, b) / 100.0

    def token_set(a: str, b: str) -> float:
        return fuzz.token_set_ratio(a, b) / 100.0

    def partial(a: str, b: str) -> float:
        return fuzz.partial_ratio(a, b) / 100.0

    HAVE_FUZZ = True
except ImportError:  # reserv utan rapidfuzz
    import difflib

    HAVE_FUZZ = False

    def ratio(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio()

    def token_set(a: str, b: str) -> float:
        sa, sb = set(a.split()), set(b.split())
        if not sa or not sb:
            return ratio(a, b)
        return len(sa & sb) / len(sa | sb)

    def partial(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        if a in b or b in a:
            return 1.0
        return ratio(a, b)


ARTICLES = {
    "the", "a", "an", "of", "and", "en", "ett", "der", "die", "das", "la", "le",
    "les", "el", "il", "de", "du",
}

# "Titel (Serie, #1)", "Titel (Serie, #1-7)", "Titel (Serie #1, part 1 of 2)"
SERIES_PAREN_RE = re.compile(
    r"\(([^()]*?)\s*[,#]\s*#?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:-\s*[0-9]+(?:\.[0-9]+)?)?\s*(?:,\s*[^()]*?)?\)\s*$"
)
SERIES_PAREN_NOPOS_RE = re.compile(r"\(([^()]*?series)\)\s*$", re.I)
# "(Harry Potter #1) Titel"  /  "[Millennium 3] Titel"
LEADING_SERIES_RE = re.compile(r"^[\[\(]\s*([^()\[\]]*?)\s*#?\s*([0-9]+(?:\.[0-9]+)?)\s*[\]\)]\s+")

# -- 50000000% serie-mönster: filnamn/mapp som "Serie – Book 5", "Serie #2 - Titel",
#     "Serie 01 - Titel", "Titel – Book 5"  (kräver serie med bokstäver, inte råa siffror)
SERIES_DASH_BOOK_RE = re.compile(
    r"^(?P<series>.+?)\s*[-\u2013\u2014-]\s*(?:book|bok|del|part|vol\.?|volume|episode|avsnitt|band|nr\.?|\#)\s*\#?\s*(?P<num>[0-9]+(?:\.[0-9]+)?|[ivxlc]+)\b(?:\s*[-\u2013\u2014-]\s*(?P<title>.+))?\s*$", re.I)
SERIES_HASH_RE = re.compile(
    r"^(?P<series>.+?)\s*#\s*(?P<num>[0-9]+(?:\.[0-9]+)?)\s*[-–—]\s*(?P<title>.+)\s*$", re.I)
SERIES_NUM_DASH_RE = re.compile(
    r"^(?P<series>.+?)\s+0*(?P<num>[0-9]{1,2})\s*[-–—]\s*(?P<title>.+)\s*$")
SERIES_WORD_NUM_RE = re.compile(
    r"^(?P<series>.+?)\s+(?:book|bok|del|part|vol\.?|volume|band)\s*#?\s*(?P<num>[0-9]+(?:\.[0-9]+)?|[ivxlc]+)\s*$", re.I)

# Honorverse-förkortningar: HH03, SoS1, SoF2, HH-03, SoS 01 etc -> serie + nummer
HONORVERSE_CODES = {
    "hh": "Honor Harrington",
    "sos": "Saganami",
    "sof": "Saganami",
    "saganami": "Saganami",
    "wage": "Wages of Sin",
    "wdb": "Wages of Sin",
    "ca": "Crown of Slaves",
    "ms": "Manticore Ascendant",
    "hg": "Honorverse",
}
HONORVERSE_RE = re.compile(r"^\s*(?P<code>HH|SoS|SoF|CA|MS|WDB)\s*[-#]?\s*0*(?P<num>[0-9]{1,2})\s*[-\u2013\u2014-]\s*(?P<title>.+?)\s*$", re.I)

# "... Del 3", "... Part 2", "... Bok 4", "... 03", "... (3 av 7)"
PART_RES = [
    re.compile(r"\b(?:del|part|bok|book|episode|avsnitt|kapitel)\s*\.?\s*([0-9]+(?:\.[0-9]+)?)\b", re.I),
    re.compile(r"\(([0-9]+)\s*(?:av|of)\s*([0-9]+)\)"),
    re.compile(r"(?:^|[-_/\s])([0-9]{1,2})(?:\s*-\s*[0-9]{1,2})?(?=[-_/\s]|\.[a-z0-9]{2,4}$|$)", re.I),
]

NOISE_WORDS = re.compile(
    r"\b(oljud|abridged|unabridged|ljudbok|audiobook|audio|mp3|cd|cd\s*\d+|"
    r"complete|full|extended|illustrated|edition|utgåva|upplaga|inläst av|"
    r"read by|narrated by|översatt av|translator)\b",
    re.I,
)

# 100000000% bättre: översättningsbrygga för vanligaste nordiska titlar (offline, utan API)
NORDIC_TITLE_MAP = {
    "isprinsessan": "the ice princess",
    "predikanten": "the preacher",
    "stenhuggaren": "the stone cutter",
    "olycksfageln": "the stranger",
    "olycksfågeln": "the stranger",
    "sjöjungfrun": "the mermaid",
    "fyrvaktaren": "the lost boy",
    "anglamakerskan": "the angel maker",
    "lejonvakten": "the lion keeper",
    "haxan": "the witch",
    "häxan": "the witch",
    "män som hatar kvinnor": "the girl with the dragon tattoo",
    "flickan som lekte med elden": "the girl who played with fire",
    "luftslottet som sprängdes": "the girl who kicked the hornets nest",
    "det som inte dödar oss": "the girl in the spiders web",
    "hon som måste dö": "the girl who lived twice",
    "hypnotisören": "the hypnotist",
    "paganinikontraktet": "the paganini contract",
    "isprinsessan: fjallbacka 01": "the ice princess",
}
# Roman numerals I-XV for series part
ROMAN_MAP = {"i":1,"ii":2,"iii":3,"iv":4,"v":5,"vi":6,"vii":7,"viii":8,"ix":9,"x":10,"xi":11,"xii":12,"xiii":13,"xiv":14,"xv":15,"xvi":16,"xvii":17,"xviii":18,"xix":19,"xx":20}
def roman_to_int(s: str) -> str:
    low = (s or "").strip().lower()
    if low in ROMAN_MAP:
        return str(ROMAN_MAP[low])
    vals = {"i":1,"v":5,"x":10,"l":50,"c":100,"d":500,"m":1000}
    if low and all(c in vals for c in low) and 1 <= len(low) <= 6:
        try:
            total=0
            prev=0
            for c in reversed(low):
                v=vals[c]
                if v < prev:
                    total-=v
                else:
                    total+=v
                prev=v
            if 1 <= total <= 50:
                return str(total)
        except Exception:
            pass
    return ""



def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str | None) -> str:
    """Aggressiv normalisering för jämförelse: små bokstäver, utan accent/interpunktion. 100000000% bättre."""
    if not s:
        return ""
    s = strip_accents(str(s)).lower()
    s = re.sub(r"\[[^\]]{2,40}\]", " ", s)
    s = re.sub(r"\([^)]{30,}\)", " ", s)
    s = NOISE_WORDS.sub(" ", s)
    s = s.replace("&", " and ").replace("'", "").replace("´", "").replace("’", "")
    s = re.sub(r"'s\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    # Komprimera siffror med inledande nollor: 01 -> 1 (för serienummer)
    # men behåll årtal 4 siffror
    parts = []
    for w in s.split():
        if w.isdigit() and len(w) <= 2:
            parts.append(str(int(w)) if w != "0" else "0")
        elif w.isdigit() and 3 <= len(w) <= 4 and w.startswith("0"):
            parts.append(w.lstrip("0") or "0")
        else:
            parts.append(w)
    return " ".join(parts)


def norm_keep_articles(s: str | None) -> str:
    """Som norm() men behåller artiklar (bättre för exakt titeljämförelse)."""
    if not s:
        return ""
    s = strip_accents(str(s)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def drop_articles(s: str) -> str:
    return " ".join(w for w in s.split() if w not in ARTICLES)


def title_key(s: str | None) -> str:
    """Titel utan serieparentes och utan inledande artiklar."""
    if not s:
        return ""
    base = split_series(str(s))[0]
    return drop_articles(norm(base))


def split_series(title: str) -> tuple[str, str, str]:
    """'X (Y, #2)' -> ('X', 'Y', '2'). Returnerar (titel, serie, nummer)."""
    m = LEADING_SERIES_RE.match(title)
    if m:
        return title[m.end():].strip(), m.group(1).strip(), m.group(2)
    m = SERIES_PAREN_RE.search(title)
    if m:
        return title[: m.start()].strip(), m.group(1).strip(), m.group(2)
    m = SERIES_PAREN_NOPOS_RE.search(title)
    if m:
        return title[: m.start()].strip(), m.group(1).strip(), ""
    return title.strip(), "", ""


def _extract_roman_part(name: str) -> str:
    m = re.search(r"\b(?:del|part|bok|book|band|volume|episode|avsnitt)\s*([ivxlc]+)\b", name or "", re.I)
    if m:
        roman = m.group(1)
        conv = roman_to_int(roman)
        if conv:
            return conv
    return ""

def extract_part(name: str) -> str:
    """Plocka ut delnummer ur ett filnamn/titel ('03' -> '3', 'IV' -> '4'). 100000000% bättre."""
    roman = _extract_roman_part(name)
    if roman:
        return roman
    for rx in PART_RES:
        m = rx.search(name or "")
        if m:
            num = m.group(1)
            if re.fullmatch(r"(1[89][0-9]{2}|20[0-9]{2})", num):
                continue
            return str(int(num)) if num.isdigit() else num
    return ""


def same_number(a: str, b: str) -> bool:
    """Jämför delnummer så att '03' == '3', 'IV' == '4' och '1.5' == '1.5'. 100000000% bättre."""
    if not a or not b:
        return False
    if a == b:
        return True
    ar = roman_to_int(a) or a
    br = roman_to_int(b) or b
    if ar == br:
        return True
    try:
        return float(ar) == float(br)
    except ValueError:
        return False


def year_from(text: str) -> str:
    m = re.findall(r"(1[89][0-9]{2}|20[0-9]{2})", text or "")
    return m[0] if m else ""


def title_similarity(a: str, b: str) -> float:
    """Robust titelpoäng 0..1 — 100000000% bättre: hanterar undertitel, kolon, dash, översättningar, roman-siffror."""
    na, nb = title_key(a), title_key(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # 100000000%: snabb översättningsbrygga utan nätverk — hanterar artiklar
    na_low = na.strip()
    nb_low = nb.strip()
    # även via title_key (utan artiklar) och norm (med/utan the)
    na_nordic = NORDIC_TITLE_MAP.get(na_low) or NORDIC_TITLE_MAP.get(norm(a).strip()) or NORDIC_TITLE_MAP.get(na_low.replace("the ","").strip())
    nb_nordic = NORDIC_TITLE_MAP.get(nb_low) or NORDIC_TITLE_MAP.get(norm(b).strip()) or NORDIC_TITLE_MAP.get(nb_low.replace("the ","").strip())
    if na_nordic and (na_nordic == nb_low or title_key(na_nordic) == nb_low or na_nordic == norm(b).strip() or title_key(na_nordic) == title_key(b)):
        return 0.97
    if nb_nordic and (nb_nordic == na_low or title_key(nb_nordic) == na_low or nb_nordic == norm(a).strip() or title_key(nb_nordic) == title_key(a)):
        return 0.97
    # direkt via norm utan the
    if na_low in NORDIC_TITLE_MAP and (NORDIC_TITLE_MAP[na_low] == nb_low or title_key(NORDIC_TITLE_MAP[na_low]) == nb_low):
        return 0.97
    if nb_low in NORDIC_TITLE_MAP and (NORDIC_TITLE_MAP[nb_low] == na_low or title_key(NORDIC_TITLE_MAP[nb_low]) == na_low):
        return 0.97
    ka, kb = norm_keep_articles(a), norm_keep_articles(b)
    # Split på kolon för undertitel: "Titel: Undertitel" -> jämför båda
    # "Isprinsessan: Fjällbacka" vs "Isprinsessan"
    for sep in [":", " - ", " – ", " — "]:
        if sep in a or sep in b:
            a_main = a.split(sep)[0].strip()
            b_main = b.split(sep)[0].strip()
            main_sim = title_similarity(a_main, b_main) if sep != ":" else 0
            # rekursiv men undvik oändlig
            if sep in [":", " - "] and main_sim > 0.85:
                return max(main_sim, 0.92)
    embedded = 0.0
    longer, shorter = (nb, na) if len(nb) >= len(na) else (na, nb)
    if len(shorter) >= 4 and shorter in longer:
        embedded = 0.92 if longer.startswith(shorter) else 0.86
        # Om kort är >= 60% av lång och inbäddad, hög poäng
        if len(shorter) >= len(longer) * 0.6:
            embedded = max(embedded, 0.88)
    # Sista ordet matchning (viktigt för serie: "Philosopher's Stone" vs "Philosopher Stone")
    # hanteras redan av token_set, men lägg extra vikt för sista token
    raw = max(ratio(ka, kb), 0.95 * token_set(na, nb), 0.85 * partial(na, nb), embedded)
    # Bonus om första och sista ord matchar (minskar förväxling Harry Potter 1 vs 2)
    a_tokens = na.split()
    b_tokens = nb.split()
    if len(a_tokens) >= 2 and len(b_tokens) >= 2 and a_tokens[0] == b_tokens[0] and a_tokens[-1] == b_tokens[-1]:
        raw = max(raw, min(0.78, raw + 0.08))
    return raw


INITIAL_RE = re.compile(r"^[a-z]\.?$")


def _name_words(s: str) -> set[str]:
    """Ord i ett personnamn, utan initialer (initialer ger falska träffar)."""
    return {w for w in s.split() if w not in ARTICLES and not INITIAL_RE.fullmatch(w)}


def author_similarity(a: str, b: str) -> float:
    """Jämför författarsträngar (kan innehålla flera namn). 100000000% bättre: hanterar initialer, flera författare, '&/och'."""
    if not a or not b:
        return 0.0
    def _split_authors(s: str) -> list[str]:
        parts = re.split(r"\s*(?:,|;|&|\band\b|\boch\b|\bwith\b|\bav\b)\s*", s, flags=re.I)
        return [p.strip() for p in parts if p.strip()]
    a_parts = _split_authors(str(a))
    b_parts = _split_authors(str(b))
    if len(a_parts) > 1 or len(b_parts) > 1:
        best = 0.0
        for ap in a_parts:
            for bp in b_parts:
                best = max(best, author_similarity(ap, bp))
                if best >= 0.99:
                    return best
        pass
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Special: initial-only som "J.K." vs "J.K. Rowling" — kolla om initialerna finns i b
    # na="j k" sb innehåller "j k rowling" -> hög poäng
    sa_raw = set(na.split())
    sb_raw = set(nb.split())
    # Om ena sidan bara är initialer (1-bokstavstokens) och de finns i andra sidans tokens -> 0.88
    def _only_initials(words: set[str]) -> bool:
        # "jk" är också initialer (utan mellanslag) — dela upp
        expanded = set()
        for w in words:
            if len(w) == 2 and w.isalpha() and w not in ARTICLES:
                # "jk" -> {"j","k"}
                expanded.update(list(w))
            else:
                expanded.add(w)
        return expanded and all(len(w) == 1 for w in expanded)
    def _expanded_set(words: set[str]) -> set[str]:
        out=set()
        for w in words:
            if len(w) == 2 and w.isalpha():
                out.update(list(w))
            elif len(w) > 2 and w.isalpha() and all(len(c)==1 for c in w): # fallback
                out.update(list(w))
            else:
                out.add(w)
        return out
    if _only_initials(sa_raw) and _expanded_set(sa_raw).issubset(_expanded_set(sb_raw)):
        return 0.88
    if _only_initials(sb_raw) and _expanded_set(sb_raw).issubset(_expanded_set(sa_raw)):
        return 0.88
    # "J K Rowling" vs "Joanne Rowling" — initialer före efternamn
    if len(sa_raw) <= 3 and len(sb_raw) <= 4:
        # kolla efternamn match + initialer subset
        na_last = na.split()[-1] if na.split() else ""
        nb_last = nb.split()[-1] if nb.split() else ""
        if na_last and nb_last and na_last == nb_last and len(na_last) >= 3:
            # efternamn samma, och övriga tokens i kortare är initialer som finns i längre
            shorter, longer = (sa_raw, sb_raw) if len(sa_raw) <= len(sb_raw) else (sb_raw, sa_raw)
            initials = {w for w in shorter if len(w) == 1}
            if initials and initials.issubset(longer):
                return 0.90
            # även "jk" (utan mellanslag) vs "j k" — endast om initialer finns
            if initials and "".join(sorted(initials)) in "".join(longer):
                return 0.88
    sa, sb = _name_words(na), _name_words(nb)
    # om ena har tom sa (bara initialer) men nångång efternamn delat
    if not sa or not sb:
        # försök efternamn-jämförelse
        na_last2 = na.split()[-1] if na.split() else ""
        nb_last2 = nb.split()[-1] if nb.split() else ""
        if na_last2 and nb_last2 and na_last2 == nb_last2:
            return 0.88
        return max(0.0, ratio(na, nb) - 0.35)
    # kräv minst ett delat "riktigt" namnord, annars är det olika personer
    shared = {w for w in (sa & sb) if len(w) >= 3}
    if not shared:
        # innan vi dömer ut: kolla efternamn lika?
        na_last3 = na.split()[-1] if na.split() else ""
        nb_last3 = nb.split()[-1] if nb.split() else ""
        if na_last3 and nb_last3 and na_last3 == nb_last3 and len(na_last3) >= 3:
            return 0.92
        return max(0.0, ratio(na, nb) - 0.35)
    jac = len(sa & sb) / len(sa | sb)
    cover = len(sa & sb) / min(len(sa), len(sb))
    base = max(ratio(na, nb), 0.9 * token_set(na, nb), 0.95 * jac, 0.85 * cover)
    # 1000000%: om efternamn samma och ena sidan bara ett ord ("Läckberg" vs "Camilla Läckberg") -> 0.92
    na_last = na.split()[-1] if na.split() else ""
    nb_last = nb.split()[-1] if nb.split() else ""
    if na_last and nb_last and na_last == nb_last and len(na_last) >= 3 and (len(sa)==1 or len(sb)==1):
        base = max(base, 0.92)
    return base


JUNK_TITLE_MARKERS = (
    "imported", "paperback", "hardcover", "translation", "russian", "chinese",
    "korean", "japanese", "harcover", " edition)", "häftad", "inbunden",
    "harcOVER", "av camilla", "by camilla", "harDCOVER".lower(),
    "study guide", "summary &", "summary of", "reading tracker", "tracker",
    "1st print", "first print", "first edition", "box set", "collection set",
    "books collection", "hardback",
    # 100000% — rip-skrot från taggar
    "unknown album", "unknown artist", "unknown", "untitled",
    # 2026-10-04: importmappen ska aldrig bli titel
    "lazylibrarian",
)

# "Track 01" / "Disc 2" / "Spår 3" är rip-skrot, inte boktitlar
TRACK_JUNK_RE = re.compile(r"^(?:track|spår|disc|cd|del|part|chapter|kapitel)\s*\d{0,2}$", re.I)

# "(Disc 01)" / "CD 2" i mapp- eller albumnamn — hör inte till sökfrågan
DISC_RE = re.compile(r"[\s_.-]*\(?\s*(?:disc|cd|skiva)\s*\d{1,2}\s*\)?", re.I)


JUNK_PATTERNS = (
    re.compile(r"\bby\s+[a-z.'\s]{3,30}\(\d{4}"),        # "… by Rowling J.K. (2014-…"
    re.compile(r"\(\d{4}-\d{2}(?:-\d{2})?\)?\s*$"),      # trunkerat datum "(2014-09-01"
    re.compile(r"\b(?:av|by)\s+[a-z.'\s]{3,30}\[[^\]]"),  # "(av X) [Imported]"
)


def looks_like_junk_title(t: str) -> bool:
    """True om strängen ser ut som en skräputgåva snarare än en boktitel."""
    low = (t or "").lower()
    if TRACK_JUNK_RE.match(low.strip()):
        return True
    if len(low) > 110:
        return True
    if low.count("[") + low.count("(") >= 3:
        return True
    if any(m in low for m in JUNK_TITLE_MARKERS):
        return True
    return any(rx.search(low) for rx in JUNK_PATTERNS)


def strip_part_words(t: str) -> str:
    """Ta bort delnummer-uttryck ur en söksträng ('Isprinsessan del 1' -> 'Isprinsessan')."""
    out = t or ""
    for rx in PART_RES[:-1]:
        out = rx.sub(" ", out)
    out = DISC_RE.sub(" ", out)
    out = re.sub(r"\s*[-_.]?\s*\d{1,2}\s*$", "", out.strip())
    return " ".join(out.split())


def _looks_like_series_name(s: str) -> bool:
    """Serie ska vara 2-60 tecken, innehålla bokstav, ej vara generiskt skrot."""
    c = (s or "").strip()
    # ta bort avslutande skiljetecken (" -", " :") som NUM_DASH kan lämna ("x -")
    c = re.sub(r"[\s\-\u2013\u2014:;,.]+$", "", c).strip()
    if not 3 <= len(c) <= 60:
        return False
    low = c.lower()
    if low in {"ljudböcker","audiobooks","books","böcker","music","musik","media","cd","disc","x","tmp","a","test"}:
        return False
    if len(c) < 3:
        return False
    # enstaka bokstav eller bara "x" med skräp ska inte godkännas
    letters = re.sub(r"[^A-Za-zÅÄÖåäö]", "", c)
    if len(letters) < 3:
        return False
    if looks_like_junk_title(c):
        return False
    # måste innehålla minst en bokstav och ej bara siffror
    if not re.search(r"[A-Za-zÅÄÖåäö]", c):
        return False
    return True


def parse_series_hint(text: str) -> tuple[str, str, str]:
    """Tolka serie-mönster ur *en* textrad.

    Hanterar (i prioriteringsordning):
      1. "Titel (Serie, #1)" / "[Serie #1] Titel"  (via split_series)
      2. "Serie – Book 5 (- Titel)" / "Serie - Bok 5" / "Serie - Vol. 2"
      3. "Serie #2 - Titel"  (hash)
      4. "Serie 01 - Titel"  (nummer-dash-titel där vänster sida är serien)
      5. "Serie Bok 5" / "Serie Del 3" (utan dash, ren serie+ord+nummer)
    Returnerar (serie, nummer, titel_rest). Tomma strängar om ingen träff.
    titel_rest är den extra titeln efter numret, eller "" om mönstret bara
    är serie+nummer (t.ex. mappnamn "Welcome … – Book 5").
    """
    if not text or not text.strip():
        return "", "", ""
    raw = text.strip()
    # 1. parentes / leading måste först (split_series är redan exakt)
    t, ser, num = split_series(raw)
    if ser or num:
        # split_series har redan rensat parentesen – t är kvarvarande titel
        # För rena serie-mönster utan titel (t tom) behöver vi inte returnera t
        return (ser.strip(), num.strip(), t.strip() if t != raw else "")

    # 2. Serie – Book/Bok/Del … (med eller utan trailing titel)
    m = SERIES_DASH_BOOK_RE.match(raw)
    if m:
        ser = (m.group("series") or "").strip()
        num = (m.group("num") or "").strip()
        # konvertera romerska siffror till arabiska
        num_conv = roman_to_int(num) or num
        num = num_conv.lstrip("0") or "0" if num_conv.isdigit() or roman_to_int(m.group("num")) else num
        title = (m.group("title") or "").strip()
        if _looks_like_series_name(ser) and num:
            return ser, num, title

    # 3. Serie #n - Titel
    m = SERIES_HASH_RE.match(raw)
    if m:
        ser = (m.group("series") or "").strip()
        num = (m.group("num") or "").strip()
        num = roman_to_int(num) or num
        title = (m.group("title") or "").strip()
        if _looks_like_series_name(ser) and num:
            return ser, num.lstrip("0") or "0" if num.isdigit() else num, title

    # 4. Serie 01 - Titel  (kräver serie med bokstäver och titel >=2 tecken)
    m = SERIES_NUM_DASH_RE.match(raw)
    if m:
        ser = (m.group("series") or "").strip()
        num = (m.group("num") or "").strip()
        num = roman_to_int(num) or num
        title = (m.group("title") or "").strip()
        if _looks_like_series_name(ser) and num and len(title) >= 2:
            return ser, num.lstrip("0") or "0" if num.isdigit() else num, title

    # 5. Serie Bok/Del n (utan dash)
    m = SERIES_WORD_NUM_RE.match(raw)
    if m:
        ser = (m.group("series") or "").strip()
        num = (m.group("num") or "").strip()
        num = roman_to_int(num) or num
        if _looks_like_series_name(ser) and num:
            return ser, num.lstrip("0") or "0" if num.isdigit() else num, ""

    # 6. Honorverse-förkortningar: HH03 - Title, SoS1 - Title etc (mappnamn i Honorverse)
    m = HONORVERSE_RE.match(raw)
    if m:
        code = (m.group("code") or "").strip().lower()
        series = HONORVERSE_CODES.get(code, code)
        num = (m.group("num") or "").strip()
        title = (m.group("title") or "").strip()
        if num and title:
            return series, num.lstrip("0") or "0", title

    return "", "", ""


def extract_series_hint(*texts: str) -> tuple[str, str, str]:
    """Första träffen bland flera texter (album, titel, filnamn, mapp …)."""
    for t in texts:
        if not t:
            continue
        ser, num, rest = parse_series_hint(t)
        if ser or num:
            return ser, num, rest
    return "", "", ""


def clean_title_from_hint(text: str) -> str:
    """Returnera ren boktitel ur en text som kan innehålla serieprefix.

    T.ex. "Fjällbacka 01 - Isprinsessan" -> "Isprinsessan",
    "Harry Potter #1 - Philosopher's Stone" -> "Philosopher's Stone",
    annars texten oförändrad (fast via split_series rensad).
    """
    if not text:
        return ""
    ser, num, rest = parse_series_hint(text)
    if rest:
        return rest.strip()
    # om hint var "Serie - Book 5" utan titelrest, behåll inte serien som titel -
    # mappen är serie, inte boktitel (sökfrågan får bli tom och fallback tar mapp)
    if ser and num and not rest:
        return ""
    # fallback: split_series titel-del
    t, _, _ = split_series(text)
    return t.strip()


def clean_series(name: str) -> str:
    """'Harry Potter Series' -> 'Harry Potter' (Goodreads lägger ofta på 'Series')."""
    n = (name or "").strip()
    n = re.sub(r"\s+series$", "", n, flags=re.I)
    n = re.sub(r"\s+trilogy$|\s+trilogi$", "", n, flags=re.I)
    return n.strip()

# --- 2026-10-04: Book friend hjärta — endast namn jag väljer, obscena bäljs bort (sv + en, även enstaka ord) ---
# Substrängar som alltid bäljs om de förekommer i namnet (svenska + engelska)
_OBSCENE_SUBSTRINGS = {
    "cunt","pussy","dick","cock","asshole","fuck","shit","bitch","whore","slut",
    "nigger","nigga","faggot","fag ","kuk","kuken","fitta","fittan","hora","horan",
    "bög","bögj","mongo","cp ","idiot ","retard","kallad","knulla","knull",
    "wank","wanker","twat","bollocks","arse","arsehole","douche","prick","tosser","bugger","damn","bastard",
}
# Enstaka engelska/svenska ord som är obscena även som ensamt namn — exakt match på hela namnet
_OBSCENE_SINGLE_EN = {
    "cunt","pussy","dick","cock","asshole","fuck","shit","bitch","whore","slut",
    "wank","wanker","twat","bollocks","arse","arsehole","ass","bastard","douche",
    "prick","tosser","bugger","nigger","nigga","faggot","fag","kuk","kuken",
    "fitta","fittan","hora","horan","bög","mongo","cp","knulla","fuckyou","shitty",
}
def is_obscene_name(name: str) -> bool:
    """True om namnet innehåller obscena ord — ska bäljas bort från release notes.

    Gäller både svenska och engelska, även enstaka ord/namn (t.ex. 'Shit', 'Dick', 'KUK').
    """
    low = (name or "").lower()
    low = strip_accents(low)
    low_norm = re.sub(r"[^a-z0-9]+", " ", low).strip()
    if not low_norm:
        return False
    # 1) Enstaka ord: exakt match mot blocklist (\"Shit\" → block, \"John\" → ok)
    tokens = low_norm.split()
    if len(tokens) == 1 and tokens[0] in _OBSCENE_SINGLE_EN:
        return True
    # 2) Substräng/blocklist — gäller även multi-word \"John Shit Doe\" eller \"FuckYou99\"
    #    använd low_norm med mellanslag för att fånga varianter
    low_spaced = f" {low_norm} "
    for bad in _OBSCENE_SUBSTRINGS:
        b = bad.strip()
        if len(b) >= 2 and b in low_norm:
            if b in {"ass","fag"}:
                if re.search(rf"\b{re.escape(b)}\b", low_norm):
                    return True
                continue
            if b == "dick" and "dickens" in low_norm:
                continue
            # även enstaka svenska \"kuk\" i \"kuken\" fångas här
            return True
        # även kolla med mellanslag för \" fag \" etc
        if b.endswith(" ") and f" {b.strip()} " in low_spaced:
            return True
    # 3) Extra: enstaka engelska ordets substräng i korta namn (2-20 tecken) → blocka
    #    för att fånga leet som \"sh1t\", \"f*ck\" redan normaliserat till \"sh t\" etc är ovan
    #    men exakt token i _OBSCENE_SINGLE_EN räcker för \"Shit\" etc
    return False

def filter_donor_names(names: list[str]) -> list[str]:
    """Filtrera bort obscena namn — endast valt namn behålls för hjärta i release notes."""
    out = []
    for n in names or []:
        nn = (n or "").strip()
        if not nn or len(nn) > 40:
            continue
        if is_obscene_name(nn):
            continue
        out.append(nn)
    return out
