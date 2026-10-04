"""Rekommendationer: 'böcker du kanske också gillar'.

Bygger på det appen redan vet om din samling (författare och serier i
historiken/skanningen) och frågar Goodreads (eller reservkällan) efter
andra böcker av samma författare samt nästa del i serien. Böcker du redan
behandlat eller har i mappen föreslås aldrig.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .models import Book
from .text import norm, same_number, title_key

MAX_AUTHORS = 4

# samlingsutgåvor/boxar är ingen bra rekommendation för ljudböcker
BOX_RE = re.compile(
    r"collection|box ?set|boxed|bundle|omnibus|anthology|complete (series|set)"
    r"|\d+\s*[-–]\s*\d+",
    re.I,
)


def is_boxset(b: Book) -> bool:
    return bool(BOX_RE.search(b.title or "")) or "-" in (b.series_number or "")


@dataclass
class Recommendation:
    book: Book
    reason: str = ""


def owned_keys(titles: list[str], authors: list[str] = None) -> set[str]:
    return {title_key(t) for t in titles if t}


def top_authors(author_counter: Counter, limit: int = MAX_AUTHORS) -> list[str]:
    return [a for a, _n in author_counter.most_common(limit)]


def recommend(
    search_fn,
    author_counts: Counter,
    series_owned: dict[str, str],
    owned_titles: list[str],
    limit_per_author: int = 2,
    total_limit: int = 12,
    similar_fn=None,
    history_books: list | None = None,
) -> list[Recommendation]:
    """search_fn(query, limit) -> list[Book]. Returnerar rekommendationer.

    series_owned: {serienamn: högsta ägda delnummer}
    """
    owned = owned_keys(owned_titles)
    out: list[Recommendation] = []
    seen: set[str] = set()

    def push(book: Book, reason: str) -> None:
        key = title_key(book.title)
        if not key or is_boxset(book):
            return
        if key in owned or key in seen or norm(book.title) in {norm(t) for t in owned_titles}:
            return
        seen.add(key)
        out.append(Recommendation(book=book, reason=reason))

    # 1) nästa del i serier du följer
    for series, top in list(series_owned.items())[:MAX_AUTHORS]:
        books = search_fn(series, limit=8)
        cands = []
        for b in books:
            if title_key(b.series or "") != title_key(series) and title_key(b.title) != title_key(series):
                continue
            if not b.series_number or is_boxset(b):
                continue
            try:
                if float(b.series_number) > float(top or 0):
                    cands.append(b)
            except ValueError:
                continue
        cands.sort(key=lambda b: float(b.series_number or 0))
        for b in cands[:1]:
            push(b, f"Nästa del i {series} (du har t.o.m. #{top})")

    # 2) fler böcker av författare du lyssnar på
    for author in top_authors(author_counts):
        books = search_fn(f"{author}", limit=8)
        n = 0
        for b in books:
            if n >= limit_per_author or len(out) >= total_limit:
                break
            if not any(norm(author) in norm(a) or norm(a) in norm(author) for a in b.authors):
                continue
            before = len(out)
            push(b, f"Mer av {author}")
            n += len(out) - before

    # 3) Goodreads "Readers also enjoyed" för de senaste böckerna i historiken
    if similar_fn:
        for title, url in (history_books or [])[:3]:
            if len(out) >= total_limit:
                break
            try:
                similars = similar_fn(url)
            except Exception:
                continue
            for b in similars[:2]:
                push(b, f"Läsare som gillade '{title}' gillade även denna")
    return out[:total_limit]
