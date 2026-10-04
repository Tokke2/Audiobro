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
    r"^(?P<series>.+?)\s*[-\u2013\u2014-]\s*(?:book|bok|del|part|vol\.?|volume|episode|avsnitt|band|nr\.?|\#)\s*\#?\s*(?P<num>[0-9]+(?:\.[0-9]+)?)\b(?:\s*[-\u2013\u2014-]\s*(?P<title>.+))?\s*$", re.I)
SERIES_HASH_RE = re.compile(
    r"^(?P<series>.+?)\s*#\s*(?P<num>[0-9]+(?:\.[0-9]+)?)\s*[-–—]\s*(?P<title>.+)\s*$", re.I)
SERIES_NUM_DASH_RE = re.compile(
    r"^(?P<series>.+?)\s+0*(?P<num>[0-9]{1,2})\s*[-–—]\s*(?P<title>.+)\s*$")
SERIES_WORD_NUM_RE = re.compile(
    r"^(?P<series>.+?)\s+(?:book|bok|del|part|vol\.?|volume)\s*#?\s*(?P<num>[0-9]+(?:\.[0-9]+)?)\s*$", re.I)

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


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str | None) -> str:
    """Aggressiv normalisering för jämförelse: små bokstäver, utan accent/interpunktion."""
    if not s:
        return ""
    s = strip_accents(str(s)).lower()
    s = NOISE_WORDS.sub(" ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


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


def extract_part(name: str) -> str:
    """Plocka ut delnummer ur ett filnamn/titel ('03' -> '3')."""
    for rx in PART_RES:
        m = rx.search(name or "")
        if m:
            num = m.group(1)
            if re.fullmatch(r"(1[89][0-9]{2}|20[0-9]{2})", num):  # årtal, inte delnummer
                continue
            return str(int(num)) if num.isdigit() else num
    return ""


def same_number(a: str, b: str) -> bool:
    """Jämför delnummer så att '03' == '3' och '1.5' == '1.5'."""
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except ValueError:
        return False


def year_from(text: str) -> str:
    m = re.findall(r"(1[89][0-9]{2}|20[0-9]{2})", text or "")
    return m[0] if m else ""


def title_similarity(a: str, b: str) -> float:
    """Robust titelpoäng 0..1."""
    na, nb = title_key(a), title_key(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ka, kb = norm_keep_articles(a), norm_keep_articles(b)
    # hela titeln inbäddad i ett längre skräpnamn ("Titel [Imported] (Swedish) …")
    embedded = 0.0
    longer, shorter = (nb, na) if len(nb) >= len(na) else (na, nb)
    if len(shorter) >= 5 and shorter in longer:
        embedded = 0.9 if longer.startswith(shorter) else 0.85
    return max(ratio(ka, kb), 0.95 * token_set(na, nb), 0.85 * partial(na, nb), embedded)


INITIAL_RE = re.compile(r"^[a-z]\.?$")


def _name_words(s: str) -> set[str]:
    """Ord i ett personnamn, utan initialer (initialer ger falska träffar)."""
    return {w for w in s.split() if w not in ARTICLES and not INITIAL_RE.fullmatch(w)}


def author_similarity(a: str, b: str) -> float:
    """Jämför författarsträngar (kan innehålla flera namn)."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    sa, sb = _name_words(na), _name_words(nb)
    # kräv minst ett delat "riktigt" namnord, annars är det olika personer
    shared = {w for w in (sa & sb) if len(w) >= 3}
    if not shared:
        return max(0.0, ratio(na, nb) - 0.35)
    jac = len(sa & sb) / len(sa | sb)
    cover = len(sa & sb) / min(len(sa), len(sb))
    return max(ratio(na, nb), 0.9 * token_set(na, nb), 0.95 * jac, 0.85 * cover)


JUNK_TITLE_MARKERS = (
    "imported", "paperback", "hardcover", "translation", "russian", "chinese",
    "korean", "japanese", "harcover", " edition)", "häftad", "inbunden",
    "harcOVER", "av camilla", "by camilla", "harDCOVER".lower(),
    "study guide", "summary &", "summary of", "reading tracker", "tracker",
    "1st print", "first print", "first edition", "box set", "collection set",
    "books collection", "hardback",
    # 100000% — rip-skrot från taggar
    "unknown album", "unknown artist", "unknown", "untitled",
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
        title = (m.group("title") or "").strip()
        if _looks_like_series_name(ser) and num:
            # skydda mot "Chapter – Part 3" där serie-delen är för kort/generisk?
            # tillåt även kort serie som "Fjällbacka" (1 ord) – det räcker.
            return ser, num.lstrip("0") or "0", title

    # 3. Serie #n - Titel
    m = SERIES_HASH_RE.match(raw)
    if m:
        ser = (m.group("series") or "").strip()
        num = (m.group("num") or "").strip()
        title = (m.group("title") or "").strip()
        if _looks_like_series_name(ser) and num:
            return ser, num.lstrip("0") or "0", title

    # 4. Serie 01 - Titel  (kräver serie med bokstäver och titel >=2 tecken)
    m = SERIES_NUM_DASH_RE.match(raw)
    if m:
        ser = (m.group("series") or "").strip()
        num = (m.group("num") or "").strip()
        title = (m.group("title") or "").strip()
        # skydda mot "01 - Isprinsessan" där ser är "01" isåfall: _looks_like missar siffror
        if _looks_like_series_name(ser) and num and len(title) >= 2:
            return ser, num.lstrip("0") or "0", title

    # 5. Serie Bok/Del n (utan dash)
    m = SERIES_WORD_NUM_RE.match(raw)
    if m:
        ser = (m.group("series") or "").strip()
        num = (m.group("num") or "").strip()
        if _looks_like_series_name(ser) and num:
            return ser, num.lstrip("0") or "0", ""

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
