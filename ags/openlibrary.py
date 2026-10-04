"""Open Library som reserv-/brodatakälla.

Goodreads ligger bakom AWS WAF och kan svara med en JS-utmaning (HTTP 202,
x-amzn-waf-action: challenge) som en skriptad klient inte kan lösa.
Open Library har ett öppet JSON-API utan nyckel och indexerar även svenska
titlar — perfekt för att (a) hitta boken när Goodreads är blockerat och
(b) översätta en svensk titel till originaltiteln så att Goodreads-sökningen
faktiskt ger träffar.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

import requests

from .models import Book
from .text import norm

API = "https://openlibrary.org/search.json"
FIELDS = "title,author_name,first_publish_year,language,series,edition_count,key,cover_i,publisher"
UA = "audiobook-goodreads-sync/1.0 (personligt biblioteksverktyg)"

# Ord som bara stör i en sökning
JUNK = {
    "okänd", "okand", "unknown", "unknown author", "various", "various authors",
    "diverse", "n/a", "na", "ingen", "saknas", "artist", "author", "okänd författare",
    "ljudbok", "audiobook", "mp3", "m4b", "cd", "del", "part", "bok", "book",
}


def clean_artist(artist: str) -> str:
    """Rensa bort skräpvärden ur en artist-tagg ('okänd', 'Unknown', 'N/A' …)."""
    a = (artist or "").strip()
    if not a:
        return ""
    if norm(a) in {norm(j) for j in JUNK}:
        return ""
    if re.fullmatch(r"[0-9\s./-]+", a):
        return ""
    return a


def clean_query(title: str, artist: str) -> str:
    """Bygg en ren sökfråga: titel utan serieparentes + giltig författare."""
    from .text import split_series

    t = split_series(title or "")[0].strip()
    t = re.sub(r"^\d+\s*[-_.]\s*", "", t)
    a = clean_artist(artist)
    q = f"{t} {a}".strip()
    return re.sub(r"\s+", " ", q)[:160]


class OpenLibrary:
    """Mycket liten klient mot Open Librarys sök-API."""

    def __init__(self, min_delay: float = 1.0, cache_path: Optional[str] = None,
                 session: Optional[requests.Session] = None) -> None:
        self.min_delay = min_delay
        self.cache_path = cache_path or os.path.join(
            os.path.expanduser("~"), ".audiobook-goodreads", "openlibrary.json"
        )
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept": "application/json"})
        self._last = 0.0
        self._cache: dict = self._load_cache()
        self._dirty = False

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

    def search(self, query: str, limit: int = 8) -> list[Book]:
        """Sök och returnera böcker. Kastar inget vid nätverksfel -> tom lista."""
        data = self._search_json(query, limit)
        # Open Library är skiftlägeskänsligt på q: 'isprinsessan' -> 0 träffar
        if not data.get("docs") and query and query[0].islower():
            data = self._search_json(query[0].upper() + query[1:], limit)
        return parse_search_json(data)

    def _search_json(self, query: str, limit: int) -> dict:
        key = f"{query}|{limit}"
        ent = self._cache.get(key)
        if ent and time.time() - ent.get("ts", 0) < 30 * 86400:
            return ent["json"]
        wait = self.min_delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        try:
            resp = self.session.get(
                API, params={"q": query, "limit": limit, "fields": FIELDS}, timeout=25
            )
        except requests.RequestException:
            return {}
        if resp.status_code != 200:
            return {}
        try:
            data = resp.json()
        except ValueError:
            return {}
        self._cache[key] = {"json": data, "ts": time.time()}
        self._dirty = True
        return data

    def best_english_title(self, title: str, author: str = "", limit: int = 8) -> str:
        """Föreslå en engelsk originaltitel för en svensk titel (annars tom sträng)."""
        books = self.search(clean_query(title, author), limit=limit)
        for b in books:
            langs = getattr(b, "languages", []) or []
            if "eng" in langs and b.title and norm(b.title) != norm(title):
                return b.title
        return ""

    def close(self) -> None:
        self.save_cache()


def parse_search_json(data: dict) -> list[Book]:
    """Gör om Open Library-svar till Book-objekt."""
    out: list[Book] = []
    if not isinstance(data, dict):
        return out
    for doc in data.get("docs") or []:
        if not isinstance(doc, dict):
            continue
        title = (doc.get("title") or "").strip()
        if not title:
            continue
        authors = [a for a in (doc.get("author_name") or []) if a]
        series_raw = doc.get("series") or []
        series, number = "", ""
        if isinstance(series_raw, list) and series_raw:
            series, number = split_series_name(str(series_raw[0]))
        elif isinstance(series_raw, str) and series_raw:
            series, number = split_series_name(series_raw)
        year = doc.get("first_publish_year")
        b = Book(
            book_id=(doc.get("key") or "").split("/")[-1],
            url=f"https://openlibrary.org{doc.get('key')}" if doc.get("key") else "",
            title=title,
            authors=authors,
            series=series,
            series_number=number,
            year=str(year) if year else "",
            source="openlibrary",
        )
        b.languages = doc.get("language") or []  # type: ignore[attr-defined]
        langs = b.languages
        if isinstance(langs, list) and langs:
            b.language = str(langs[0])
        pubs = doc.get("publisher") or []
        if isinstance(pubs, list) and pubs:
            b.publisher = str(pubs[0])
        cov = doc.get("cover_i")
        if cov:
            b.cover = f"https://covers.openlibrary.org/b/id/{cov}-L.jpg"
        out.append(b)
    return out


def split_series_name(s: str) -> tuple[str, str]:
    """'Millennium #1' -> ('Millennium', '1'). Skrälldata ger ('', '')."""
    from .text import clean_series

    raw = (s or "").strip()
    if not raw or raw in {"[]", "None", "null"}:
        return "", ""
    m = re.match(r"^(.*?)\s*(?:#|,\s*#?|\bok\b|\bdel\b)\s*([0-9]+(?:\.[0-9]+)?)\s*$", raw, re.I)
    if m and m.group(1).strip():
        return clean_series(m.group(1).strip()), m.group(2)
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s+(.+)$", raw)
    if m:
        return clean_series(m.group(2).strip()), m.group(1)
    return clean_series(raw), ""
