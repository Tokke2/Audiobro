"""Historik över färdigbehandlade böcker — hoppar över dubbelarbete."""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Optional

from .text import norm

DEFAULT_PATH = os.path.join(
    os.path.expanduser("~"), ".audiobook-goodreads", "history.json"
)


def identity_key(title: str, author: str, series: str = "", number: str = "",
                 book_id: str = "") -> str:
    """Stabil nyckel för 'samma bok' oavsett utgåva och skiftläge."""
    if book_id:
        return f"gr:{book_id}"
    raw = "|".join(norm(x) for x in (title, author, series, number))
    return "k:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class History:
    """Liten JSON-butik: lista av färdigbehandlade böcker."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or DEFAULT_PATH
        self._entries: list[dict] = self._load()

    def _load(self) -> list[dict]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._entries, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass

    # -------------------------------------------------------------- läs
    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> list[dict]:
        return list(self._entries)

    def is_done(self, key: str) -> bool:
        return any(e.get("key") == key for e in self._entries)

    def find_match(self, title: str, author: str, series: str = "",
                   number: str = "") -> Optional[dict]:
        """Hitta en historikpost på titel+författare (före sökning, krav 21).

        Jämför normaliserade fält så att taggade filer från en tidigare
        organisering träffar samma post även när book-id saknas.
        """
        from .text import norm, title_key

        tk = title_key(title or "")
        if not tk:
            return None
        def _words(a: str) -> set:
            """Betydelsefulla ord i namnet: 'Läckberg, C.' -> {'lackberg'}."""
            return {w for w in norm(a).split(" och ")[0].split()
                    if len(w) > 2 and w != "och"}

        aw = _words(author or "")
        se = norm(series or "")
        for e in self._entries:
            if title_key(e.get("title") or "") != tk:
                continue
            ew = _words(e.get("author") or "")
            if aw and ew and not (aw & ew):
                continue
            es = norm(e.get("series") or "")
            if se and es and es != se:
                continue
            return e
        return None

    def find(self, key: str) -> Optional[dict]:
        for e in self._entries:
            if e.get("key") == key:
                return e
        return None

    # -------------------------------------------------------------- skriv
    def add(self, key: str, title: str, author: str, series: str = "",
            number: str = "", url: str = "", score: float = 0.0,
            source: str = "", output: str = "", files: Optional[list[str]] = None) -> None:
        self._entries = [e for e in self._entries if e.get("key") != key]
        self._entries.append({
            "key": key,
            "title": title,
            "author": author,
            "series": series,
            "number": number,
            "url": url,
            "score": round(score, 3),
            "source": source,
            "output": output,
            "files": files or [],
            "finished_at": time.strftime("%Y-%m-%d %H:%M"),
        })
        self.save()

    def remove(self, key: str) -> bool:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.get("key") != key]
        if len(self._entries) != before:
            self.save()
            return True
        return False

    def clear(self) -> None:
        self._entries = []
        self.save()
