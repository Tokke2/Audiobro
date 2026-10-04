"""Nordiska ljudbokskällor: Storytel och BookBeat (reservkällor).

Båda tjänsterna har öppna, nyckelfria sök-API:er som appen frågar direkt
(samma endpoints som community-providern abs-agg använder):

* Storytel:  https://www.storytel.com/api/search.action?request_locale=sv&q=…
             -> böcker med serie + delnummer, uppläsare och utgivningsår.
* BookBeat:  https://search-api.bookbeat.com/api/appsearch/suggest?market=sweden&query=…
             -> titelförslag, sedan detaljanrop per bok (serie, år, författare).

De är särskilt bra på svenska titlar (seriedata ingår, till skillnad från
Open Library) och används därför FÖRE Open Library i reservkedjan.
Alla anrop loggas till ags.log.
"""
from __future__ import annotations

import re
from typing import Optional

import requests

from . import logging_setup
from .models import Book

log = logging_setup.get(__name__)

UA = "audiobook-goodreads-sync/1.0 (personligt biblioteksverktyg)"

STORYTEL_SEARCH = "https://www.storytel.com/api/search.action"
BOOKBEAT_SUGGEST = "https://search-api.bookbeat.com/api/appsearch/suggest"

# "Titel, Del 3" / "Titel - 2: Undertitel" … — ta bort serienummer ur titeln
_SERIES_SUFFIX = re.compile(
    r"[,:]?\s*(?:del|avsnitt|bok|episode|episode|volume|teil|band|folge)\s*\d+\s*$",
    re.I,
)


def fetch_json(url: str, timeout: int = 20):
    """Gör ett GET-anrop och returnera JSON. Loggar allt (krav: logga allt)."""
    log.debug("GET %s", url)
    resp = requests.get(
        url, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=timeout
    )
    log.debug("  <- %s, %d bytes", resp.status_code, len(resp.content or b""))
    resp.raise_for_status()
    return resp.json()


def _clean_title(name: str, series_name: str = "") -> str:
    t = _SERIES_SUFFIX.sub("", name or "").strip(" -:")
    if series_name:
        # "Fjällbacka 2: Stenhuggaren" -> "Stenhuggaren", men rör INTE
        # "Harry Potter and the Philosopher's Stone" (serienamn utan delnummer).
        pat = re.compile(rf"^{re.escape(series_name)}[:\-,\s]*\d+\s*[:\-]?\s*", re.I)
        t = pat.sub("", t)
    return t.strip() or (name or "").strip()


class StorytelClient:
    """Liten klient mot Storytels publika sök-API (ingen nyckel krävs)."""

    source = "storytel"

    def __init__(self, language: str = "sv"):
        self.language = language

    def search(self, query: str, limit: int = 8) -> list[Book]:
        if not (query or "").strip():
            return []
        url = (f"{STORYTEL_SEARCH}?request_locale={self.language}"
               f"&q={requests.utils.quote(query)}")
        try:
            data = fetch_json(url)
        except Exception as exc:  # nätverksfel får aldrig sänka skanningen
            log.warning("Storytel-fel: %s", exc)
            return []
        books: list[Book] = []
        for item in (data.get("books") or [])[:limit]:
            b = item.get("book") or {}
            name = b.get("name") or ""
            if not name:
                continue
            series = (b.get("series") or [{}])[0].get("name") or ""
            abook = item.get("abook") or {}
            ebook = item.get("ebook") or {}
            year = (abook.get("releaseDate") or b.get("releaseDate") or "")[:4]
            narrators = [n.get("name") for n in (abook.get("narrators") or [])
                         if n.get("name")] or []
            if not narrators and abook.get("narratorAsString"):
                narrators = [a.strip() for a in abook["narratorAsString"].split(",") if a.strip()]
            cover = (b.get("largeCover") or b.get("cover") or "")
            books.append(Book(
                book_id=f"storytel:{b.get('id', '')}",
                url=item.get("shareUrl") or "",
                title=_clean_title(name, series),
                authors=[a.strip() for a in (b.get("authorsAsString") or "").split(",") if a.strip()],
                series=series,
                series_number=str(b.get("seriesOrder") or ""),
                year=year,
                language=(b.get("language") or {}).get("isoValue") or "",
                description=(abook.get("description") or ebook.get("description") or ""),
                narrators=narrators,
                publisher=(abook.get("publisher") or ebook.get("publisher")
                           or b.get("publisher") or {}).get("name", "") or "",
                genres=[t.get("name") for t in (b.get("tags") or []) if t.get("name")][:3],
                cover=(f"https://www.storytel.com{cover}" if cover else ""),
                source="storytel",
            ))
        log.info("Storytel: %d träffar för %r", len(books), query)
        return books


class BookBeatClient:
    """Liten klient mot BookBeats publika sök-API (ingen nyckel krävs)."""

    source = "bookbeat"

    def __init__(self, market: str = "sweden", details: int = 3):
        self.market = market
        self.details = details

    def search(self, query: str, limit: int = 8) -> list[Book]:
        if not (query or "").strip():
            return []
        url = (f"{BOOKBEAT_SUGGEST}?includeErotic=false&market={self.market}"
               f"&query={requests.utils.quote(query)}&v=18")
        try:
            data = fetch_json(url)
        except Exception as exc:
            log.warning("BookBeat-fel: %s", exc)
            return []
        books: list[Book] = []
        for sug in (data.get("suggestions") or []):
            if len(books) >= min(limit, self.details):
                break
            if not str(sug.get("id", "")).startswith("BookTitle"):
                continue
            href = ((sug.get("_links") or {}).get("search") or {}).get("href")
            if not href:
                continue
            try:
                detail = fetch_json(href)
            except Exception as exc:
                log.warning("BookBeat-detaljfel: %s", exc)
                continue
            for bd in (detail.get("_embedded", {}).get("books") or [])[:1]:
                series = bd.get("series") or {}
                books.append(Book(
                    book_id=f"bookbeat:{bd.get('id', '')}",
                    url=href,
                    title=bd.get("title") or sug.get("value") or "",
                    authors=[a.strip() for a in (bd.get("author") or "").split(",") if a.strip()],
                    series=series.get("name") or "",
                    series_number=str(series.get("displaypartnumber") or ""),
                    year=(bd.get("published") or "")[:4],
                    language=bd.get("language") or "",
                    description=bd.get("description") or "",
                    cover=bd.get("image") or "",
                    isbn=bd.get("audiobookisbn") or bd.get("ebookisbn") or "",
                    source="bookbeat",
                ))
        log.info("BookBeat: %d träffar för %r", len(books), query)
        return books


class NordicFallback:
    """Reservkedja: prövar källorna i tur och ordning tills något hittas.

    Har samma .search(query, limit)-gränssnitt som openlibrary.OpenLibrary,
    så motorn ser ingen skillnad. Varje Book får sin `source` satt.
    """

    def __init__(self, clients: list, min_delay: float = 0.0):
        self.clients = list(clients)
        self.min_delay = min_delay

    def search(self, query: str, limit: int = 8) -> list[Book]:
        books: list[Book] = []
        for client in self.clients:
            try:
                found = client.search(query, limit=limit)
            except Exception as exc:  # en död källa får inte stoppa kedjan
                log.warning("reservkälla %s misslyckades: %s",
                            getattr(client, "source", client), exc)
                continue
            books.extend(found)
            if len(books) >= limit:
                break
        return books[:limit]
