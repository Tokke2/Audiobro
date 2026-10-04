"""Brygga: hitta originaltiteln (engelska) för en svensk titel.

Goodreads索引 är i praktiken engelskt — en svensk titel ger ofta noll träffar
där. Denna modul gissar originaltiteln via svenska Wikipedias språklänkar och
infobox, och används bara som ett extra försök när den svenska titeln inte gav
något. Resultaten cachas, och allt misslyckas tyst (tom sträng) så att flödet
aldrig hänger på Wikipedia.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

import requests

SV_API = "https://sv.wikipedia.org/w/api.php"
UA = "Audiobro/1.0 (personligt biblioteksverktyg)"
EN_TAIL_RE = re.compile(r"\s*\((?:novel|book|roman|bok)\)\s*$", re.I)
ORIGINAL_KEYS = ("originaltitel", "original title", "engelsk titel", "original_title", "titel (engelska)")


def clean_english_title(t: str) -> str:
    t = (t or "").strip()
    t = EN_TAIL_RE.sub("", t).strip()
    t = t.split("|")[0].strip()
    t = t.split("{{")[0].strip()
    return t.strip(" '\"")


def english_titles_from_wikitext(wikitext: str) -> list[str]:
    """Läs ut originaltitel ur en infobox-wikitext."""
    out: list[str] = []
    for key in ORIGINAL_KEYS:
        m = re.search(r"\|\s*%s\s*=\s*([^\n|]+)" % re.escape(key), wikitext or "", re.I)
        if m:
            t = clean_english_title(m.group(1))
            if t and t not in out:
                out.append(t)
    return out


def english_titles_from_langlinks(pages: dict) -> list[str]:
    """Läs ut engelska titlar ur ett svar från action=query&prop=langlinks."""
    out: list[str] = []
    for _pid, page in (pages or {}).items():
        if "missing" in page:
            continue
        for link in page.get("langlinks") or []:
            if link.get("lang") == "en":
                t = clean_english_title(link.get("*") or "")
                if t and t not in out:
                    out.append(t)
    return out


def disambiguation_pages(wikitext: str) -> list[str]:
    """På en förgreningssida: hitta artikeln som handlar om romanen/boken."""
    if "{{förgrening}}" not in (wikitext or ""):
        return []
    out = []
    for cand in re.findall(r"\[\[([^\]|]+)", wikitext):
        if re.search(r"roman|\bbok\b|novel", cand, re.I):
            name = cand.split("(")[0].strip()
            if name and name not in out:
                out.append(name)
    return out


class TitleBridge:
    """Slår upp engelsk originaltitel via sv.wikipedia (med cache)."""

    def __init__(self, cache_path: Optional[str] = None,
                 session: Optional[requests.Session] = None) -> None:
        self.cache_path = cache_path or os.path.join(
            os.path.expanduser("~"), ".audiobro", "titles.json"  # legacy handled via settings._config_dir
        )
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept": "application/json"})
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

    # ------------------------------------------------------------------ api
    def _api(self, **params) -> dict:
        params["format"] = "json"
        try:
            resp = self.session.get(SV_API, params=params, timeout=20)
        except requests.RequestException:
            return {}
        if resp.status_code != 200:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {}

    def lookup(self, title: str) -> list[str]:
        """Engelska titelförslag för en svensk titel (tom lista om inget hittas)."""
        title = (title or "").strip()
        if not title:
            return []
        if title in self._cache:
            ent = self._cache[title]
            return ent.get("en", []) if isinstance(ent, dict) else []

        found: list[str] = []
        data = self._api(action="query", prop="langlinks", lllimit="100", redirects="1", titles=title)
        pages = data.get("query", {}).get("pages", {})
        found.extend(english_titles_from_langlinks(pages))

        for _pid, page in pages.items():
            if "missing" in page:
                continue
            wt = self._api(action="parse", prop="wikitext", page=page.get("title")).get(
                "parse", {}).get("wikitext", {}).get("*", "")
            for t in english_titles_from_wikitext(wt):
                if t not in found:
                    found.append(t)
            for dis in disambiguation_pages(wt):
                d2 = self._api(action="query", prop="langlinks", lllimit="100", redirects="1", titles=dis)
                for t in english_titles_from_langlinks(d2.get("query", {}).get("pages", {})):
                    if t not in found:
                        found.append(t)

        self._cache[title] = {"en": found, "ts": time.time()}
        self._dirty = True
        return found
