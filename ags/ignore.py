"""Ignorera dubbletter — även över källor.

Sparar en mängd nycklar (source-agnostiska) i ~/.audiobro/ignore.json (legacy ~/.audiobook-goodreads/ignore.json).
En nyckel är t.ex. 'ta:harrypotter1|rowling' eller 'gr:12345'.
Om en nyckel är ignorerad kommer den inte att flaggas som dublett igen,
och 'sämre version'-logiken hoppar över den.

UI kan anropa add_ignored / is_ignored / clear_ignored.
"""
from __future__ import annotations

import json
import os
import hashlib

from . import logging_setup
from .text import norm, title_key

LOG = logging_setup.get("ignore")

def _default_ignore_path() -> str:
    new = os.path.join(os.path.expanduser("~"), ".audiobro", "ignore.json")
    legacy = os.path.join(os.path.expanduser("~"), ".audiobook-goodreads", "ignore.json")
    if os.path.isfile(new):
        return new
    if os.path.isfile(legacy):
        try:
            import shutil
            os.makedirs(os.path.dirname(new), exist_ok=True)
            if not os.path.isfile(new):
                shutil.copy2(legacy, new)
        except Exception:
            pass
        return new
    return new

DEFAULT_PATH = _default_ignore_path()


def _path(path: str | None = None) -> str:
    return path or DEFAULT_PATH


def load_ignored(path: str | None = None) -> set[str]:
    p = _path(path)
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return set(str(x) for x in data)
        if isinstance(data, dict) and "ignored" in data:
            return set(str(x) for x in data["ignored"])
    except FileNotFoundError:
        pass
    except Exception as exc:
        LOG.debug("kunde inte läsa ignore %s: %s", p, exc)
    return set()


def save_ignored(ignored: set[str], path: str | None = None) -> None:
    p = _path(path)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(sorted(ignored), fh, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        LOG.info("ignore sparad %d nycklar -> %s", len(ignored), p)
    except OSError as exc:
        LOG.warning("kunde inte spara ignore: %s", exc)


def is_ignored(key: str, path: str | None = None) -> bool:
    return key in load_ignored(path)

def is_ignored_any(keys: set[str] | list[str] | str, path: str | None = None) -> bool:
    """True om någon av nycklarna är ignorerad — cross-source robust."""
    if isinstance(keys, str):
        keys = {keys}
    ignored = load_ignored(path)
    return any(k in ignored for k in keys)

def is_proposal_ignored(p, path: str | None = None) -> bool:
    """True om proposalens alla varianter matchar ignore-listan."""
    return is_ignored_any(dup_keys_for_proposal(p), path)


def add_ignored(key: str | set[str] | list[str], path: str | None = None) -> bool:
    if not key:
        return False
    keys = {key} if isinstance(key, str) else set(key)
    keys = {k for k in keys if k}
    if not keys:
        return False
    ignored = load_ignored(path)
    if keys.issubset(ignored):
        return False
    ignored.update(keys)
    save_ignored(ignored, path)
    LOG.info("ignorerad dublett tillagd: %s", ", ".join(sorted(keys)))
    return True

def add_ignored_proposal(p, path: str | None = None) -> bool:
    """Lägg till alla varianter för en proposal — så cross-source ignoreras."""
    keys = dup_keys_for_proposal(p)
    return add_ignored(keys, path)


def remove_ignored(key: str, path: str | None = None) -> bool:
    ignored = load_ignored(path)
    if key not in ignored:
        return False
    ignored.remove(key)
    save_ignored(ignored, path)
    LOG.info("ignorerad dublett borttagen: %s", key)
    return True


def clear_ignored(path: str | None = None) -> None:
    save_ignored(set(), path)
    LOG.info("ignore rensad")


def _robust_title_key(title: str) -> str:
    """Robust titelnyckel för cross-source: utan mellanslag/bindestreck, utan artiklar, normaliserad.
    Junk-titlar som "Unknown", "Untitled", "Track 01" ger tom nyckel så att de inte grupperas som samma bok (fix 2026-10-04 Worlds of Honor vs Changer of Worlds)."""
    if not title:
        return ""
    # Junk-titlar ska inte ge samma nyckel för olika böcker — t.ex. alla "Unknown" av samma författare ska inte bli dublett
    try:
        from .text import looks_like_junk_title
        if looks_like_junk_title(title):
            return ""
    except Exception:
        pass
    tk = title_key(title or "")
    if not tk:
        return ""
    # Ta bort alla mellanslag så att "is prinsessan" == "isprinsessan" (hyphen vs no hyphen)
    return tk.replace(" ", "")

def _robust_author_key(author: str) -> str:
    """Robust författarnyckel: använd efternamn sista token, hantera 'Läckberg, Camilla' -> 'lackberg'."""
    a = norm(author or "").strip()
    if not a:
        return ""
    # norm gör redan "lackberg camilla" från "Läckberg, Camilla" (komma -> mellanslag)
    # Vi tar sista token som efternamn, men för stabilitet: sortera? Nej, sista ordet är mest troligt efternamn.
    # Om författare har flera ("Camilla Läckberg & Henrik Fexeus"), ta sista ordet i varje? Enklare: ta alla efternamn sorterade.
    # För nu: använd sista token + även första token om olika, för att undvika kollision vid samma efternamn olika författare.
    # Men för att cross-source med omvänd ordning ska matcha, räcker sista token.
    parts = a.split()
    if len(parts) >= 2:
        # Om format "lackberg camilla" (efternamn först), sista är "camilla" -> inte idealiskt. Vi tar den mest signifikanta: längsta ordet?
        # Välj längsta ordet som troligt efternamn om det skiljer sig.
        # Ex: "lackberg camilla" -> "lackberg" (8 vs 7) -> "lackberg"
        # Ex: "camilla lackberg" -> "lackberg" (8 vs 7) -> "lackberg"
        longest = max(parts, key=len)
        # säkerställ att vi väljer efternamn, inte förnamn. Längsta är ofta efternamn.
        return longest
    # enstaka ord
    return a.replace(" ", "")

def dup_keys_for_proposal(p) -> set[str]:
    """Returnera alla robusta nycklar för en proposal — för att ignorera oavsett källformat."""
    keys: set[str] = set()
    try:
        # Prioritera new_title (Goodreads) — men ignorera junk så att olika "Unknown"-böcker inte blir samma nyckel
        title = getattr(p, "new_title", None) or getattr(getattr(p, "audio", None), "title", None) or getattr(getattr(p, "audio", None), "album", "") or ""
        # Om titel är junk (Unknown etc), prova group_label direkt — den är ofta mappnamnet och mer distinkt
        try:
            from .text import looks_like_junk_title
            if looks_like_junk_title(title or ""):
                gl2 = getattr(getattr(p, "audio", None), "group_label", "") or ""
                if gl2 and not looks_like_junk_title(gl2):
                    title = gl2
        except Exception:
            pass
        artist = getattr(p, "new_artist", None) or getattr(getattr(p, "audio", None), "artist", "") or ""
        tk = _robust_title_key(title or "")
        if not tk:
            gl = getattr(getattr(p, "audio", None), "group_label", "") or ""
            tk = _robust_title_key(gl)
        ak = _robust_author_key(artist or "")
        if tk:
            keys.add(f"ta:{tk}|{ak}")
            # även utan författare (fallback om author saknas i ena källan)
            keys.add(f"ta:{tk}|")
            # även med full norm author för bakåtkompatibilitet
            full_ak = norm(artist or "").strip().replace(" ", "")
            if full_ak and full_ak != ak:
                keys.add(f"ta:{tk}|{full_ak}")
        else:
            paths = getattr(p, "paths", None) or [getattr(getattr(p, "audio", None), "path", "")]
            raw = "|".join(str(x) for x in paths if x)
            if raw:
                h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
                keys.add(f"path:{h}")
        # Lägg även till Goodreads-ID om det finns — då ignoreras samma GR-bok oavsett titelvariant
        gid = getattr(p, "goodreads_id", None) or getattr(p, "book_id", None) or getattr(getattr(p, "candidate", None), "work_id", None) or ""
        if gid:
            try:
                keys.add(f"gr:{str(gid).strip()}")
            except: pass
    except Exception:
        pass
    return {k for k in keys if k}

def dup_key_for_proposal(p) -> str:
    """Source-agnostisk nyckel — primär (robust). För bakåtkompabilitet returnera första."""
    keys = dup_keys_for_proposal(p)
    # prioritera ta:... framför path
    for k in sorted(keys):
        if k.startswith("ta:"):
            return k
    return next(iter(keys), "")
    


def dup_key_for_title_author(title: str, author: str) -> str:
    tk = _robust_title_key(title or "")
    ak = _robust_author_key(author or "")
    return f"ta:{tk}|{ak}"


def dup_key_for_ids(book_id: str = "", title: str = "", author: str = "") -> str:
    """Hjälpare om man har book_id — men för cross-source bör titel användas."""
    if book_id:
        # returnera både — men vi väljer att spara båda nycklarna när man ignorerar
        return f"gr:{book_id}"
    return dup_key_for_title_author(title, author)
