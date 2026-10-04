"""Goodreads-klient: sök och läs ut titel, författare, serie och delnummer.

Goodreads officiella API lades ner i december 2020, så allt här bygger på att
läsa de publika sidorna. Sidorna serveras fortfarande som vanlig HTML
(verified 2026-09-18: /search -> HTTP 200, /book/show/<id> -> HTTP 200),
men Goodreads kan blockera vid hög takt -> alltid låg förfrågningsfrekvens
och cachning.
"""
from __future__ import annotations

import html as html_lib
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .logging_setup import get
from .models import Book
from .text import clean_series

log = get("goodreads")

BASE = "https://www.goodreads.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,sv;q=0.8",
    "Referer": BASE + "/",
}


class GoodreadsBlocked(RuntimeError):
    """Goodreads svarade med en tillfällig blockering (403/429)."""

    def __init__(self, msg: str = "", hint: str = "") -> None:
        super().__init__(msg)
        self.hint = hint or (
            "Goodreads svarar med en tillfällig blockering "
            "som en skriptad klient inte kan lösa. Lösningar: (1) kör långsammare "
            "(--delay 3) och vänta några minuter, (2) klistra in din "
            "Goodreads-token från webbläsaren, eller (3) använd läget "
            "'Klistra in / skärmbild' som inte behöver någon uppkoppling."
        )


@dataclass
class GoodreadsError(Exception):
    msg: str = "Goodreads-fel"


class Goodreads:
    """Liten skrapande klient med cache och artig takt."""

    def __init__(
        self,
        min_delay: float = 1.2,
        cache_path: Optional[str] = None,
        language: str = "en-US",
        session: Optional[requests.Session] = None,
        on_fetch: Optional[Callable[[str], None]] = None,
        max_cache_age_days: int = 60,
        browser_token: str = "",
        retries: int = 2,
    ) -> None:
        self.min_delay = min_delay
        self.language = language
        self.on_fetch = on_fetch
        self.max_cache_age_days = max_cache_age_days
        self.retries = max(1, retries)
        self.blocked = False          # True så fort blockeringen träffas
        self.last_status = 0
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        if browser_token:
            self.set_browser_token(browser_token)
        self.cache_path = cache_path or os.path.join(
            os.path.expanduser("~"), ".audiobro", "cache.json"
        )
        self._last = 0.0
        self._lock = threading.Lock()
        self._cache: dict = self._load_cache()
        self._dirty = False

    # ---------------------------------------------------------------- cache
    def _load_cache(self) -> dict:
        try:
            with open(self.cache_path, encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_cache(self) -> None:
        if not self._dirty:
            return
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            tmp = self.cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._cache, fh, ensure_ascii=False)
            os.replace(tmp, self.cache_path)
            self._dirty = False
        except Exception:
            pass

    def cache_size(self) -> int:
        return len(self._cache)

    # ---------------------------------------------------------------- fetch
    def set_browser_token(self, token: str) -> None:
        """Återanvänd en Goodreads-token från din egen webbläsare.

        Hämtas i webbläsarens devtools (Application -> Cookies -> goodreads.com
        -> Goodreads-token (aws-waf-token)). Då slipper appen blockeringen.
        Sätter cookien för både .goodreads.com och www.goodreads.com för robusthet.
        """
        token = (token or "").strip()
        if token:
            # Sätt för båda domänerna — Goodreads kan svara från www eller apex
            for dom in (".goodreads.com", "www.goodreads.com", "goodreads.com"):
                try:
                    self.session.cookies.set("aws-waf-token", token, domain=dom, path="/")
                except Exception:
                    pass
            # Spara rå token för loggning/diagnos (visas aldrig i klartext i logg)
            self._browser_token = token  # type: ignore[attr-defined]
            self.blocked = False
            log.info("Goodreads-token satt (%d tecken) för %s", len(token), ", ".join([".goodreads.com","www.goodreads.com"]))

    def get(self, url: str, use_cache: bool = True) -> str:
        if use_cache:
            ent = self._cache.get(url)
            if ent and time.time() - ent.get("ts", 0) < self.max_cache_age_days * 86400:
                return ent["html"]
        last_exc: Optional[Exception] = None
        attempts = 1  # blockeringar ger inget vid retry; nätverksfel får ett försök till
        for attempt in range(self.retries):
            with self._lock:
                wait = self.min_delay - (time.monotonic() - self._last)
                if wait > 0:
                    time.sleep(wait)
                self._last = time.monotonic()
            if attempt:  # backoff innan nytt försök
                time.sleep(self.min_delay * (2 ** attempt))
            if self.on_fetch:
                self.on_fetch(url)
            try:
                resp = self.session.get(url, timeout=30)
            except requests.RequestException as exc:
                last_exc = GoodreadsError(f"Nätverksfel mot Goodreads: {exc}")
                continue
            body = resp.text or ""
            self.last_status = resp.status_code
            if self._is_block_challenge(resp) or resp.status_code in (403, 429) or self._looks_blocked(resp.status_code, body):
                self.blocked = True
                log.warning(
                    "Goodreads blockerad: %s (HTTP %s, %s) | Goodreads-token: %s. "
                    "Orsak: Goodreads kräver giltig token "
                    "eller webbläsarupplåsning — se fliken Logg / 'Goodreads "
                    "blockerad?'.", url, resp.status_code,
                    resp.headers.get("x-amzn-waf-action", "-"),
                    "skickades" if getattr(self, "_browser_token", "") else "ej satt")
                raise GoodreadsBlocked(
                    f"Goodreads blockerade förfrågan (HTTP {resp.status_code}, "
                    f"{resp.headers.get('x-amzn-waf-action', 'bot-skydd')})."
                )
            if resp.status_code >= 400:
                raise GoodreadsError(f"HTTP {resp.status_code} för {url}")
            self.blocked = False
            log.info("GET %s -> %s (%d byte)", url, resp.status_code, len(body))
            self._cache[url] = {"html": body, "ts": time.time()}
            self._dirty = True
            return body
        if last_exc:
            raise last_exc
        raise GoodreadsError(f"Kunde inte hämta {url}")

    @staticmethod
    def _is_waf_challenge(resp) -> bool:
        return Goodreads._is_block_challenge(resp)

    @staticmethod
    def _is_block_challenge(resp) -> bool:
        """Goodreads blockering: HTTP 202 + x-amzn-waf-action: challenge, tom body."""
        if resp.headers.get("x-amzn-waf-action", "").lower() == "challenge":
            return True
        if resp.status_code == 202 and len(resp.content or b"") < 5000:
            return True
        return False

    @staticmethod
    def _looks_blocked(status: int, body: str) -> bool:
        low = body[:4000].lower()
        if "just a moment" in low or "cf-browser-verification" in low:
            return True
        if "enable javascript and cookies to continue" in low:
            return True
        return False

    # ---------------------------------------------------------------- sök
    def search_url(self, query: str, page: int = 1) -> str:
        q = quote_plus(query.strip())
        return f"{BASE}/search?page={page}&q={q}"

    def search(self, query: str, page: int = 1, limit: int = 10) -> list[Book]:
        """Sök på Goodreads och returnera träffar (utan extra boksidan)."""
        html = self.get(self.search_url(query, page))
        books = parse_search_html(html)
        return books[:limit]

    # ---------------------------------------------------------------- boksida
    def book(self, url_or_id: str, with_series: bool = True) -> Book:
        url = url_or_id
        if not url.startswith("http"):
            url = f"{BASE}/book/show/{url_or_id}"
        html = self.get(url)
        book = parse_book_html(html, url=url)
        if with_series and book.series_number and not book.series:
            book.series = self.series_name_from_book_html(html) or ""
        if with_series and book.series_id and not book.series:
            book.series = self.series_name(book.series_id) or book.series
        return book

    def similar(self, url_or_id: str, limit: int = 6) -> list[Book]:
        """'Readers also enjoyed' från en boksida — böcker som liknar den."""
        url = url_or_id if str(url_or_id).startswith("http") else f"{BASE}/book/show/{url_or_id}"
        try:
            html = self.get(url)
        except (GoodreadsBlocked, GoodreadsError):
            return []
        return parse_similar_books(html)[:limit]

    def series_name(self, series_id: str) -> str:
        """Hämta det officiella serienamnet från /series/<id> (cachas per serie)."""
        key = f"__series__{series_id}"
        if key in self._cache and isinstance(self._cache[key], dict) and "name" in self._cache[key]:
            ent = self._cache[key]
            if time.time() - ent.get("ts", 0) < self.max_cache_age_days * 86400:
                return ent["name"]
        try:
            html = self.get(f"{BASE}/series/{series_id}", use_cache=True)
        except (GoodreadsBlocked, GoodreadsError):
            return ""
        name = parse_series_name(html)
        self._cache[key] = {"name": name, "ts": time.time()}
        self._dirty = True
        return name

    @staticmethod
    def series_name_from_book_html(html: str) -> str:
        return parse_series_name_from_book(html)

    # ---------------------------------------------------------------- praktiskt
    def enrich(self, b: Book) -> Book:
        """Komplettera en träff med beskrivning/genrer/omslag från boksidan.

        Boksidan cachas, så kostnaden är ett anrop per unik bok. Vid
        blockering hoppar vi över tyst (metadata är nice-to-have).
        """
        if not (b.url or "").startswith("http") or b.description:
            return b
        try:
            full = self.book(b.url, with_series=False)
        except (GoodreadsBlocked, GoodreadsError) as exc:
            log.debug("enrich hoppades över (%s): %s", b.url, exc)
            return b
        b.description = b.description or full.description
        b.genres = b.genres or full.genres
        b.cover = b.cover or full.cover
        b.language = b.language or full.language
        return b

    def search_best(self, query: str, limit: int = 8) -> list[Book]:
        """Sök och komplettera med boksidor bara där seriedata saknas.

        Serieinformationen syns oftast redan i sökträffens titel som
        "(Harry Potter, #1)", så boksidan hämtas endast när den saknas —
        det håller nere antalet anrop (Goodreads gillar inte hög takt).
        """
        books = self.search(query, limit=limit)
        out: list[Book] = []
        extra_fetches = 0
        for b in books:
            if not b.series_number and not b.series and extra_fetches < 2:
                extra_fetches += 1
                try:
                    full = self.book(b.url)
                except GoodreadsBlocked:
                    self.save_cache()
                    raise
                except GoodreadsError:
                    full = None
                if full is not None and full.title:
                    if not full.series:
                        full.series = b.series
                    if not full.series_number:
                        full.series_number = b.series_number
                    if not full.url:
                        full.url = b.url
                    out.append(full)
                    continue
            out.append(b)
        return out

    def close(self) -> None:
        self.save_cache()
        try:
            self.session.close()
        except Exception:
            pass


# --------------------------------------------------------------------------
#  Parsning (rena funktioner -> testbara mot sparad HTML)
# --------------------------------------------------------------------------
TAG_RE = re.compile(r"<[^>]+>")


def _txt(fragment: str) -> str:
    t = TAG_RE.sub(" ", fragment or "")
    t = html_lib.unescape(t)
    t = t.replace("<!-- -->", " ")
    return " ".join(t.split())


# Roller som inte ska hamna i artist-fältet (illustratörer, översättare, inläsare …)
NON_PRIMARY_ROLES = (
    "illustrator", "illustratör", "translator", "översättare", "narrator",
    "inläsare", "editor", "redaktör", "foreword", "förord", "designer",
    "photographer", "fotograf", "cover", "contributor",
)


def _role_of(container) -> str:
    node = container.select_one("span.role, span.authorName.role, .greyText.smallText.role")
    if node is None:
        for sp in container.select("span"):
            cls = " ".join(sp.get("class") or [])
            if "role" in cls:
                node = sp
                break
    return _txt(node.get_text()).strip("() ").lower() if node is not None else ""


def _authors_from_search_row(title_anchor) -> list[str]:
    """Plocka ut huvudförfattare ur en sökträff (hoppar över illustratörer m.fl.)."""
    asp = title_anchor.find_next("span", itemprop="author")
    if asp is None:
        return []
    containers = asp.select("div.authorName__container") or [asp]
    primary: list[str] = []
    everyone: list[str] = []
    for c in containers:
        nm = _txt(c.select_one("a.authorName").get_text()) if c.select_one("a.authorName") else ""
        if not nm:
            continue
        everyone.append(nm)
        if _role_of(c) in NON_PRIMARY_ROLES:
            continue
        primary.append(nm)
    seen: list[str] = []
    for nm in (primary or everyone):
        if nm not in seen:
            seen.append(nm)
    return seen


def _js_unescape(s: str) -> str:
    """Avkoda en JSON-strängs innehåll (hanterar citat och unicode utan att förstöra UTF-8)."""
    if not s:
        return s
    try:
        return json.loads(f'"{s}"')
    except Exception:
        try:
            return bytes(s, "utf-8").decode("unicode_escape")
        except Exception:
            return s


def _parse_search_nextjs(html: str) -> list[Book]:
    """Parsa nya Goodreads Next.js-sökresultatet (2024+).

    HTML:et innehåller RSC-payload i self.__next_f.push([...]) med
    serialiserade Book-objekt. Vi avkodar pusharna och regexar ut
    book-objekten direkt — soup.select('a.bookTitle') är död (0 träffar
    sedan 2026-09).
    """
    from .text import split_series
    import datetime as _dt

    pushes = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)\"\]\)', html, re.DOTALL)
    if pushes:
        decoded_all = ""
        for p in pushes:
            try:
                decoded_all += json.loads(f'"{p}"')
            except Exception:
                try:
                    decoded_all += bytes(p, "utf-8").decode("unicode_escape")
                except Exception:
                    decoded_all += p
    else:
        decoded_all = html

    # Varje bok har triple legacyId + title + imageUrl direkt efter
    triple_pat = re.compile(
        r'"legacyId"\s*:\s*(\d+)\s*,\s*"title"\s*:\s*"((?:\\.|[^"\\])*)"\s*,\s*"imageUrl"\s*:\s*"([^"]*)"',
        re.DOTALL,
    )
    triples = list(triple_pat.finditer(decoded_all))
    if not triples:
        return []

    positions = [m.start() for m in triples]
    out: list[Book] = []
    for idx, m in enumerate(triples):
        bid = m.group(1)
        raw_title = m.group(2)
        image_url = m.group(3)
        title = html_lib.unescape(_js_unescape(raw_title)).strip()
        if not title:
            continue
        # Titel kan redan innehålla serie-parantes — behåll som fallback
        _t, _s_fallback, _n_fallback = split_series(title)

        start = m.start()
        end = positions[idx + 1] if idx + 1 < len(positions) else start + 20000
        chunk = decoded_all[start:end]
        if len(chunk) > 15000:
            chunk = chunk[:15000]

        # URL & omslag
        wm = re.search(r'"webUrl"\s*:\s*"([^"]*book/show/[^"]*)"', chunk)
        web_url = wm.group(1) if wm else f"{BASE}/book/show/{bid}"
        web_url = web_url.replace("\\u0026", "&").split("?")[0]
        cover = image_url.replace("\\u0026", "&")

        # Författare — primary + secondary där role==Author
        authors: list[str] = []
        pm = re.search(
            r'"primaryContributorEdge".*?"name"\s*:\s*"((?:\\.|[^"\\])*)".*?"role"\s*:\s*"([^"]*)"',
            chunk,
            re.DOTALL,
        )
        if pm:
            raw_name, role = pm.group(1), pm.group(2)
            name = html_lib.unescape(_js_unescape(raw_name)).strip()
            name = " ".join(name.split())
            if name and role.lower() == "author":
                authors.append(name)

        sec_block_m = re.search(
            r'"secondaryContributorEdges"\s*:\s*\[(.*?)\]\s*,\s*"reviewEditUrl"',
            chunk,
            re.DOTALL,
        )
        sec_block = sec_block_m.group(1) if sec_block_m else ""
        if sec_block:
            for raw_name, role in re.findall(
                r'"name"\s*:\s*"((?:\\.|[^"\\])*)".*?"role"\s*:\s*"([^"]*)"',
                sec_block,
                re.DOTALL,
            ):
                name = html_lib.unescape(_js_unescape(raw_name)).strip()
                name = " ".join(name.split())
                if name and role.lower() == "author" and name not in authors:
                    authors.append(name)

        if not authors:
            # Fallback: plocka första rimliga contributor-namn i chunken
            for raw_name in re.findall(r'"name"\s*:\s*"((?:\\.|[^"\\])*)"', chunk[:6000]):
                name = html_lib.unescape(_js_unescape(raw_name)).strip()
                name = " ".join(name.split())
                if name and 1 < len(name) < 40 and name not in authors:
                    if " " in name or not authors:
                        authors.append(name)
                    if len(authors) >= 2:
                        break

        # Serie & delnummer
        series = ""
        series_number = ""
        sm = re.search(
            r'"bookSeries":\[{"__typename":"BookSeries","seriesPlacement":"([^"]*)","series":\{"__typename":"Series","id":"[^"]*","title":"((?:\\.|[^"\\])*)"',
            chunk,
            re.DOTALL,
        )
        if sm:
            series_number = sm.group(1)
            raw_series = sm.group(2)
            series = html_lib.unescape(_js_unescape(raw_series)).strip()
        else:
            sm2 = re.search(
                r'"bookSeries":\[[^\]]*?"title"\s*:\s*"((?:\\.|[^"\\])*)"',
                chunk,
                re.DOTALL,
            )
            if sm2:
                raw_series = sm2.group(1)
                series = html_lib.unescape(_js_unescape(raw_series)).strip()
                plc = re.search(r'"seriesPlacement"\s*:\s*"([^"]*)"', chunk)
                if plc:
                    series_number = plc.group(1)
            # Ingen bookSeries — försök serie från titel-parantes som fallback
            if not series and _s_fallback:
                series = _s_fallback
                series_number = _n_fallback

        if series_number and "-" in series_number:
            series_number = series_number.split("-")[0]
        series_number = series_number.strip()
        series = clean_series(series)

        # År från publicationTime (ms)
        year = ""
        ptm = re.search(r'"publicationTime"\s*:\s*(\d+)', chunk)
        if ptm:
            try:
                ts = int(ptm.group(1))
                import datetime as _dt2

                year = str(_dt2.datetime.fromtimestamp(ts / 1000, tz=_dt2.timezone.utc).year)
            except Exception:
                year = ""

        # Betyg
        rating = ""
        rm = re.search(r'"averageRating"\s*:\s*([0-9.]+)', chunk)
        if rm:
            rating = rm.group(1)
        ratings_count = ""
        rcm = re.search(r'"ratingsCount"\s*:\s*(\d+)', chunk)
        if rcm:
            ratings_count = rcm.group(1)

        out.append(
            Book(
                book_id=bid,
                url=urljoin(BASE, web_url.split("?")[0]),
                title=_t,
                authors=authors,
                series=series,
                series_number=series_number,
                year=year,
                rating=rating,
                ratings_count=ratings_count,
                cover=cover,
                source="goodreads:sök",
            )
        )
    return out


def parse_search_html(html: str) -> list[Book]:
    """Parsa /search-sidan. Hanterar både legacy-HTML (a.bookTitle) och nya Next.js-RSC."""
    from .text import split_series

    soup = BeautifulSoup(html, "lxml")
    out: list[Book] = []
    # 1. Legacy-path (före 2024): a.bookTitle — behåll för bakåtkompatibilitet + tester
    legacy_anchors = soup.select("a.bookTitle")
    if legacy_anchors:
        for a in legacy_anchors:
            href = a.get("href") or ""
            m = re.search(r"/book/show/([0-9]+)", href)
            if not m:
                continue
            bid = m.group(1)
            raw_title = _txt(a.get_text())
            title, series, num = split_series(raw_title)
            authors = _authors_from_search_row(a)
            rating = ""
            rc = ""
            rate = a.find_next("span", class_="minirating")
            if rate:
                txt = _txt(rate.get_text())
                mr = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*avg", txt)
                cr = re.search(r"([0-9,\\.]+)\s*ratings", txt)
                rating = mr.group(1) if mr else ""
                rc = cr.group(1) if cr else ""
            year = ""
            y = a.find_next("span", class_="uitext")
            if y:
                ym = re.search(r"\b(1[89][0-9]{2}|20[0-9]{2})\b", _txt(y.get_text()))
                year = ym.group(1) if ym else ""
            img = a.find_previous("img", class_="bookCover")
            cover = ""
            if img is not None:
                cover = img.get("src") or ""
            out.append(
                Book(
                    book_id=bid,
                    url=urljoin(BASE, href.split("?")[0]),
                    title=title,
                    authors=authors,
                    series=clean_series(series),
                    series_number=num,
                    year=year,
                    rating=rating,
                    ratings_count=rc,
                    cover=cover,
                    source="goodreads:sök",
                )
            )
        if out:
            return out

    # 2. Nya Next.js (2024+): RSC-payload i self.__next_f — primär sedan Goodreads migrerade
    try:
        nxt = _parse_search_nextjs(html)
        if nxt:
            log.info("Goodreads sök: Next.js-parser gav %d träffar", len(nxt))
            return nxt
    except Exception as exc:  # pragma: no cover
        log.debug("Next.js parse_search misslyckades: %s", exc)

    # 3. Sist fallback: generisk grav — a[href*=book/show] med text (för att aldrig ge 0 träffar)
    try:
        seen: set[str] = set()
        for a in soup.select("a[href*='/book/show/']"):
            href = a.get("href") or ""
            m = re.search(r"/book/show/([0-9]+)", href)
            if not m:
                continue
            bid = m.group(1)
            if bid in seen:
                continue
            txt = _txt(a.get_text())
            if not txt or len(txt) < 2:
                continue
            seen.add(bid)
            title, series, num = split_series(txt)
            out.append(
                Book(
                    book_id=bid,
                    url=urljoin(BASE, href.split("?")[0]),
                    title=title,
                    authors=[],
                    series=clean_series(series),
                    series_number=num,
                    cover="",
                    source="goodreads:sök",
                )
            )
            if len(out) >= 20:
                break
        if out:
            log.info("Goodreads sök: fallback grav gav %d träffar", len(out))
            return out
    except Exception:
        pass

    return out



def parse_book_html(html: str, url: str = "") -> Book:
    """Parsa en /book/show/-sida."""
    soup = BeautifulSoup(html, "lxml")
    book_id = ""
    m = re.search(r"/book/show/([0-9]+)", url)
    if m:
        book_id = m.group(1)

    # Titel: JSON-LD är mest pålitligt, därefter data-testid="bookTitle"
    title = ""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict) and it.get("@type") == "Book" and it.get("name"):
                title = html_lib.unescape(str(it["name"])).strip()
                break
        if title:
            break
    if not title:
        h1 = soup.find(attrs={"data-testid": "bookTitle"})
        if h1:
            title = _txt(h1.get("aria-label") or h1.get_text())
            title = re.sub(r"^book title:\s*", "", title, flags=re.I)

    # Författare (primära; narratörer/översättare ligger i egna block längre ner)
    authors: list[str] = []
    for block in soup.select("div[class*='BookPageMetadataSection__contributor']"):
        for sp in block.select("span[data-testid='name']"):
            nm = _txt(sp.get_text())
            if nm and nm not in authors:
                authors.append(nm)
    if not authors:
        for sp in soup.select("span[data-testid='name']"):
            nm = _txt(sp.get_text())
            if nm and nm not in authors:
                authors.append(nm)
    if not authors:
        for sp in soup.select("a.contributorName"):
            nm = _txt(sp.get_text())
            if nm and nm not in authors:
                authors.append(nm)

    # Serie + delnummer, från titelsektionens aria-label ("Book 1 in the Harry Potter series")
    series, number, series_id = "", "", ""
    sec = soup.find(class_="BookPageTitleSection__title")
    node = sec.find("h3") if sec else None
    if node is None:
        node = soup.find("a", href=re.compile(r"^https?://www\.goodreads\.com/series/"))
    if node is not None:
        label = node.get("aria-label") or ""
        mm = re.search(r"(?:book|bok|del)\s*([0-9]+(?:\.[0-9]+)?)\b", label, re.I)
        number = mm.group(1) if mm else ""
        link = node.find("a") or (node if node.name == "a" else None)
        if link is not None:
            href = link.get("href") or ""
            sm = re.search(r"/series/([0-9]+)", href)
            if sm:
                series_id = sm.group(1)
            nm = re.sub(r"<!--.*?-->", " ", link.get_text() or "")
            nm = _txt(nm)
            nm = re.sub(r"\s*#?\s*[0-9]+(?:\.[0-9]+)?\s*$", "", nm).strip()
            series = clean_series(nm)
    if not series_id:
        sm = re.search(r'href="https://www\.goodreads\.com/series/([0-9]+)', html)
        series_id = sm.group(1) if sm else ""

    # År
    year = ""
    det = soup.find("div", attrs={"data-testid": "bookDetails"})
    if det:
        ym = re.search(r"\b(1[89][0-9]{2}|20[0-9]{2})\b", _txt(det.get_text()))
        year = ym.group(1) if ym else ""

    rating = rc = ""
    r = soup.find(attrs={"data-testid": "averageRating"})
    if r is not None:
        tm = _txt(r.get_text())
        rating = tm.split()[0] if tm else ""
    c = soup.find(attrs={"data-testid": "ratingsCount"})
    if c is not None:
        cm = re.search(r"([0-9\.,]+)", _txt(c.get_text()))
        rc = cm.group(1) if cm else ""

    cover = ""
    im = soup.find("img", class_="ResponsiveImage")
    if im is not None:
        cover = im.get("src") or ""

    lang = ""
    lm = re.search(r'"language"\s*:\s*"([a-zA-Z\-_]+)"', html[:200000])
    if lm:
        lang = lm.group(1)

    # beskrivning + genrer (Används av Audiobookshelf-fälten)
    description = ""
    dnode = soup.find("div", id="description") or soup.find(
        attrs={"data-testid": "description"})
    if dnode is not None:
        description = _txt(dnode.get_text())
    genres: list[str] = []
    for g in soup.select('a[href^="/genres/"]'):
        nm = _txt(g.get_text())
        if nm and nm.lower() not in {x.lower() for x in genres}:
            genres.append(nm)
    genres = genres[:3]

    return Book(
        book_id=book_id,
        url=url,
        title=title,
        authors=authors,
        series=series,
        series_number=number,
        series_id=series_id,
        year=year,
        rating=rating,
        ratings_count=rc,
        cover=cover,
        language=lang,
        description=description,
        genres=genres,
        source="goodreads:boksida",
    )


SERIES_PROPS_RE = re.compile(
    r'data-react-class="ReactComponents\.SeriesHeader"[^>]*?data-react-props="(.*?)"(?=[\s>])',
    re.S,
)


def parse_series_name(html: str) -> str:
    """Serienamn från /series/<id>: ligger i React-props som HTML-entiteter."""
    m = SERIES_PROPS_RE.search(html)
    if not m:
        return ""
    raw = html_lib.unescape(m.group(1))
    try:
        props = json.loads(raw)
        title = props.get("title") or ""
    except Exception:
        tm = re.search(r'"title"\s*:\s*"([^"]+)"', raw)
        title = tm.group(1) if tm else ""
    title = html_lib.unescape(title).strip()
    return clean_series(title)


def parse_series_name_from_book(html: str) -> str:
    """Serienamn direkt ur boksidan (när det står i titelraden)."""
    m = re.search(r'aria-label="(?:Book|Bok)\s*[0-9.]+\s+in the (.+?) series"', html)
    if m:
        return clean_series(html_lib.unescape(m.group(1)))
    return ""


def parse_similar_books(html: str) -> list[Book]:
    """Parsa 'Readers also enjoyed'-karusellen på en /book/show/-sida."""
    soup = BeautifulSoup(html, "lxml")
    section = soup.find(attrs={"data-testid": re.compile(r"readersalsoenjoyed", re.I)})
    if section is None:
        for h in soup.find_all(["h2", "h3"]):
            if "readers also enjoyed" in h.get_text().lower():
                section = h.find_parent(["section", "div"])
                break
    if section is None:
        return []
    out: list[Book] = []
    seen: set[str] = set()
    for a in section.find_all("a", href=re.compile(r"/book/show/[0-9]+")):
        m = re.search(r"/book/show/([0-9]+)", a["href"])
        bid = m.group(1)
        if bid in seen:
            continue
        seen.add(bid)
        img = a.find("img")
        title = (img.get("alt") if img else "") or _txt(a.get_text())
        if not title:
            continue
        out.append(Book(book_id=bid, url=urljoin(BASE + "/", a["href"]),
                        title=title.strip(), source="goodreads"))
    return out
