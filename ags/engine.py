"""Orkestrering: skanna -> matcha mot Goodreads -> föreslå taggar -> skriv."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, Optional

from . import library, matching, organize, tags
from .goodreads import Goodreads, GoodreadsBlocked, GoodreadsError
from .history import History, identity_key
from .logging_setup import get

log = get("engine")
from .models import AudioFile, Proposal
from .text import (
    DISC_RE,
    clean_series,
    clean_title_from_hint,
    extract_part,
    extract_series_hint,
    looks_like_junk_title,
    norm,
    parse_series_hint,
    split_series,
    strip_part_words,
    title_key,
    title_similarity,
)


@dataclass
class EngineOptions:
    write_series: bool = True      # skriv TXXX:SERIES / ----:iTunes:SERIES
    album_style: str = "title"     # "title" | "series"  ("Harry Potter" som album)
    backup: bool = True
    min_score: float = matching.MEDIUM
    include_year: bool = True
    max_candidates: int = 6
    use_fallback: bool = True      # Open Library när Goodreads är blockerat/tomt
    use_title_bridge: bool = True  # gissa engelsk originaltitel för svenska titlar
    auto_token: bool = False       # lås upp Goodreads via Brave/Chromium vid blockering
    skip_done: bool = True         # hoppa över böcker som historiken säger är klara
    replaygain: bool = True        # 1) ReplayGain / volymnormalisering — skriv REPLAYGAIN_* om ffmpeg finns


def _clean_ranked(matches: list, prefer_title: str = "") -> list:
    """Poäng>0.15; föredra (1) exakt titelutgåva, (2) ren utgåva, (3) nordic översättning, annars som det är. 100000000% bättre."""
    from .text import title_key

    matches = [m for m in matches if m.score > 0.15]
    if not matches:
        return matches
    want = title_key(prefer_title)
    # även nordic översättning som exakt
    try:
        from .text import NORDIC_TITLE_MAP, norm
        want_norm = norm(prefer_title).strip() if prefer_title else ""
        want_trans = NORDIC_TITLE_MAP.get(want_norm, "")
        want_trans_key = title_key(want_trans) if want_trans else ""
    except Exception:
        want_trans_key = ""
    if want:
        exact = [m for m in matches if title_key(m.book.title) == want]
        # även översättningsexakt
        if not exact and want_trans_key:
            exact = [m for m in matches if title_key(m.book.title) == want_trans_key]
        if exact:
            exact.sort(key=lambda m: (0 if (m.book.series or m.book.series_number) else 1,
                                      -_ratings(m.book), -m.score))
            rest = [m for m in matches if m not in exact]
            return exact + rest
    clean = [m for m in matches if not looks_like_junk_title(m.book.title)]
    return clean or matches


def _ratings(book) -> int:
    rc = (book.ratings_count or "").replace(",", "").replace(".", "")
    return int(rc) if rc.isdigit() else 0


# Krav 23: flera versioner av samma bok -> behåll den bästa.
# BÅTTRE: Mer träffsäker — bitrate (via mutagen/ffprobe) → sample_rate → codec → storlek → färre filer
_FORMAT_RANK = {"flac": 5, "wav": 4, "alac": 4, "m4b": 3, "m4a": 3, "aac": 3, "opus": 3, "mp3": 2, "ogg": 2, "wma": 1}

def _version_quality(p: "Proposal") -> tuple:
    """BÅTTRE ljudkvalitet: probe första filen för exakt bitrate/sample_rate, annars fallback storlek/format."""
    size = getattr(p, "total_size_mb", None)
    if size is None:
        size = p.audio.size_mb or 0.0
    fmt = (p.audio.format or "").lower()
    base_rank = _FORMAT_RANK.get(fmt, 1)
    n_files = len(getattr(p, "paths", None) or [p.audio.path])
    # Försök exakt bitrate/sample_rate/codec via audioinfo.probe (finns filen?)
    bitrate = 0
    sample_rate = 0
    codec_rank = base_rank
    try:
        paths = getattr(p, "paths", None) or [p.audio.path]
        pth = next((x for x in paths if x and __import__("os").path.exists(x)), "")
        if pth:
            from . import audioinfo as _ai
            q = _ai.probe(pth)
            if q:
                if q.bitrate_kbps:
                    bitrate = int(q.bitrate_kbps)
                if q.sample_rate:
                    sample_rate = int(q.sample_rate)
                if q.codec:
                    codec_rank = _FORMAT_RANK.get(q.codec.lower(), base_rank)
                    # FLAC via codec rank högre
                    if "flac" in q.codec.lower():
                        codec_rank = 5
                    elif "aac" in q.codec.lower():
                        codec_rank = 3
                if q.size_mb and q.size_mb > 0:
                    size = q.size_mb
    except Exception:
        pass
    # Fallback bitrate från storlek om probe missade och duration finns (approx)
    if bitrate == 0 and size and getattr(p.audio, "path", ""):
        try:
            dur = 0
            paths = getattr(p, "paths", None) or [p.audio.path]
            pth = next((x for x in paths if x and __import__("os").path.exists(x)), "")
            if pth:
                from . import audioinfo as _ai
                q2 = _ai.probe(pth)
                if q2 and q2.duration_s:
                    dur = q2.duration_s
            if dur and dur > 60:
                bitrate = int((float(size)*1024*1024*8)/(dur*1000))
        except: pass
    return (int(bitrate), int(sample_rate), int(codec_rank), round(float(size),1), -int(n_files))


def choose_best_versions(proposals: list["Proposal"]) -> list["Proposal"]:
    """Fler versioner av samma bok i samma skanning -> välj den bästa.

    Jämför matchade förslag med samma identitet (Goodreads-id, annars
    titel+författare). Vinnaren behåller sin status; förlorarna markeras
    'sämre version' + skipped så att de inte organiseras. Returnerar
    listan över ändrade förslag.

    Respekterar ignorerade dubbletter (även över källor) — robust mot
    olika stavning/hyphen och "Läckberg, Camilla" vs "Camilla Läckberg".
    """
    from .text import norm, title_key
    try:
        from .ignore import load_ignored, dup_keys_for_proposal, is_ignored_any
        ignored = load_ignored()
    except Exception:
        ignored = set()

    by_key: dict[str, list] = {}
    for p in proposals:
        if p.skipped or p.status not in ("matchad", "behöver koll") or not p.match:
            continue
        # Ignorerad dublett — hoppa över helt (robust cross-source)
        try:
            from .ignore import dup_keys_for_proposal as _dkp
            keys = _dkp(p)
            if keys and is_ignored_any(keys, path=None):
                # använd loadad ignored via helper för att undvika extra I/O
                if any(k in ignored for k in keys):
                    log.info("ignorerad dublett hoppas över i best-version: %r (%s)", p.new_title or p.audio.title, next(iter(keys)))
                    continue
        except Exception:
            pass
        # Gruppera robust cross-source: använd både id och robust titel+författare så att "Läckberg, Camilla" == "Camilla Läckberg" och "IS-prinsessan" == "Isprinsessan"
        try:
            from .ignore import _robust_title_key, _robust_author_key
            rtk = _robust_title_key(p.new_title or p.audio.title or "")
            rak = _robust_author_key(p.new_artist or p.audio.artist or "")
            robust_key = f"ta:{rtk}|{rak}" if rtk else ""
        except Exception:
            robust_key = ""
        bid = p.match.book.book_id if p.match.book else ""
        # Prioritera robust titel+författare för cross-source, men behåll id som egen grupp om robust saknas
        if robust_key and robust_key != "ta:|":
            key = robust_key
        elif bid:
            key = f"id:{bid}"
        else:
            key = "ta:" + title_key(p.new_title or p.audio.title) + "|" + norm(p.new_artist or p.audio.artist)
        # Även robust cross-source check (ignorera)
        try:
            from .ignore import dup_keys_for_proposal as _dkp2
            if any(k in ignored for k in _dkp2(p)):
                log.info("ignorerad cross-source dublett hoppas över: %r", p.new_title or p.audio.title)
                continue
        except Exception:
            pass
        by_key.setdefault(key, []).append(p)

    changed: list = []
    for group in by_key.values():
        if len(group) < 2:
            continue
        # Extra check: om gruppens första proposal är ignorerad (robust), skippa hela gruppen
        try:
            from .ignore import dup_keys_for_proposal as _dkp3
            if any(k in ignored for k in _dkp3(group[0])):
                continue
        except Exception:
            pass
        # Säkerhet: två olika böcker i samma serie ska aldrig bli "sämre version" — kräver hög titellikhet
        # (fix 2026-10-04: Worlds of Honor vs Changer of Worlds felaktigt grupperade)
        try:
            from .text import title_similarity, author_similarity
            # Filtrera gruppen — behåll bara de som faktiskt är samma bok (titelnära + samma författare)
            filtered = [group[0]]
            for cand in group[1:]:
                ts = title_similarity(group[0].new_title or group[0].audio.title or "", cand.new_title or cand.audio.title or "")
                # Även fallback till group_label om titel tom
                if ts < 0.10:
                    ts2 = title_similarity(group[0].audio.group_label or "", cand.audio.group_label or "")
                    ts = max(ts, ts2)
                auth_a = group[0].new_artist or group[0].audio.artist or ""
                auth_b = cand.new_artist or cand.audio.artist or ""
                aus = author_similarity(auth_a, auth_b) if auth_a and auth_b else 1.0
                if ts < 0.75:
                    log.info("hoppar över sämre-version för %r vs %r — titlar för olika (%.2f) trots samma robust nyckel %r", cand.new_title or cand.audio.title, group[0].new_title or group[0].audio.title, ts, next(iter(by_key), "")[:30])
                    continue
                if aus < 0.30 and auth_a and auth_b:
                    log.info("hoppar över sämre-version för %r vs %r — författare för olika (%.2f)", cand.new_title or cand.audio.title, group[0].new_title or group[0].audio.title, aus)
                    continue
                filtered.append(cand)
            group = filtered
            if len(group) < 2:
                continue
        except Exception as exc:
            log.debug("titel-filter för best-version fel: %s", exc)
        group.sort(key=_version_quality, reverse=True)
        best = group[0]
        for worse in group[1:]:
            # Dubbelkolla titlar en extra gång före markering — olika böcker i serie ska ej flaggas
            try:
                from .text import title_similarity as _ts2
                _ts = _ts2(best.new_title or best.audio.title or best.audio.group_label or "", worse.new_title or worse.audio.title or worse.audio.group_label or "")
                if _ts < 0.75:
                    log.info("skippar sämre-markering: %r vs %r titlar olika %.2f", best.new_title or best.audio.title, worse.new_title or worse.audio.title, _ts)
                    continue
            except Exception:
                pass
            worse.status = "sämre version"
            worse.skipped = True
            b_size = getattr(best, "total_size_mb", best.audio.size_mb or 0.0)
            w_size = getattr(worse, "total_size_mb", worse.audio.size_mb or 0.0)
            worse.note = (f"bättre version vald: {best.audio.group_label or best.audio.path} "
                          f"({b_size:.0f} MB mot {w_size:.0f} MB)")
            log.info("flera versioner av %r — behåller %r, hoppar över %r",
                     worse.new_title or worse.audio.title,
                     best.audio.group_label, worse.audio.group_label)
            changed.append(worse)
    return changed


class Engine:
    """Kopplar ihop biblioteksskanning, Goodreads och taggskrivning."""

    def __init__(self, client: Goodreads, options: Optional[EngineOptions] = None,
                 on_status: Optional[Callable[[str], None]] = None,
                 fallback=None, bridge=None,
                 token_fetcher: Optional[Callable[[], str]] = None,
                 history: Optional[History] = None,
                 on_history_hit: Optional[Callable[["Proposal", dict], bool]] = None) -> None:
        self.client = client
        self.options = options or EngineOptions()
        self.on_status = on_status or (lambda s: None)
        self.fallback = fallback    # openlibrary.OpenLibrary
        self.bridge = bridge        # bridge.TitleBridge
        self.token_fetcher = token_fetcher  # t.ex. browser_token.fetch_waf_token
        self.history = history or History()
        # Krav 21: fråga användaren vid historikträff. True = hoppa över,
        # False = matcha på nytt. None = hoppa över utan att fråga.
        self.on_history_hit = on_history_hit
        self._unlocked = False
        self._unlock_tries = 0

    # ---------------------------------------------------------------- källor
    def resolve(self, title: str, author: str, part: str = "") -> tuple[list, str, str]:
        """Hämta kandidater. Returnerar (böcker, källa, notering).

        Kedja:
          1. Goodreads med renad sökfråga (titel utan serieparentes + giltig författare)
          2. Goodreads med engelsk originaltitel (via Wikipedia) om steg 1 gav tomt
          3. Open Library (fungerar utan nyckel, även för svenska titlar)
        """
        from .openlibrary import clean_query

        q = clean_query(title, author)
        note = ""
        if q != title.strip():
            note = f"sökfråga rensad till '{q}'"

        books: list = []
        source = "goodreads"
        from . import logging_setup as _ls
        _log = _ls.get("engine.match")
        # 100000000% bättre: logga query-förfining med roman-normalisering
        try:
            from .text import roman_to_int as _r2i2
            if title and _r2i2(title.split()[-1]):
                _log.debug("roman-detekt: titel slutar med roman %s", title.split()[-1])
        except Exception:
            pass
        if not getattr(self.client, "blocked", False):
            try:
                books = self.client.search_best(q, limit=self.options.max_candidates)
                # Goodreads eget sök träffar ofta fel utgåva på långa titlar:
                # komplettera med en kort fråga (första orden + författare).
                seen = {b.book_id for b in books}

                def merge(extra_books) -> None:
                    for b in extra_books:
                        if b.book_id and b.book_id not in seen:
                            books.append(b)
                            seen.add(b.book_id)

                short = self._short_query(title, author)
                if short and short != q:
                    merge(self.client.search_best(short, limit=4))
                if part:
                    base = " ".join(split_series(title)[0].split()[:2])
                    part_q = f"{base} {part}"
                    if part_q not in (q, short):
                        merge(self.client.search_best(part_q, limit=4))
                # Fallback: titel utan författare — Goodreads sök med författare kan dränkas i studieguider/summaries
                # (t.ex. "Project Hail Mary Andy Weir" ger 18 summaries medan "Project Hail Mary" ger romanen).
                # Denna extra fråga säkerställer att riktiga romanen alltid finns bland kandidaterna.
                title_only = clean_query(title, "")
                if title_only and title_only not in (q, short):
                    # Undvik att skicka "lazylibrarian" etc
                    from .text import looks_like_junk_title as _is_junk
                    if title_only and not _is_junk(title_only):
                        try:
                            merge(self.client.search_best(title_only, limit=4))
                        except Exception:
                            pass
            except GoodreadsBlocked as exc:
                _log.warning("goodreads blockerad för %r: %s", q, exc)
                # Tillåt upp till 3 automatiska upplåsningar per scan (inte bara 1) — vid stora bibliotek kan token hinna gå ut mitt i
                if self.options.auto_token and self.token_fetcher and getattr(self, "_unlock_tries", 0) < 3:
                    self._unlock_tries = getattr(self, "_unlock_tries", 0) + 1
                    self._unlocked = True
                    self.on_status(f"Goodreads blockerad — låser upp via din webbläsare … (försök {self._unlock_tries}/3)")
                    try:
                        token = self.token_fetcher()
                        if token:
                            self.client.set_browser_token(token)
                            # nollställ blockerad-flaggan redan i set_browser_token, prova igen
                            books = self.client.search_best(q, limit=self.options.max_candidates)
                            if books:
                                note = (note + " | " if note else "") + "upplåst via webbläsar-token"
                                _log.info("upplåsning lyckades — fick %d träffar efter token (försök %d)", len(books), self._unlock_tries)
                            else:
                                _log.info("upplåsning gav token men 0 träffar för %r — provar nästa fråga/fallback", q)
                        else:
                            _log.warning("token_fetcher returnerade tom token (försök %d)", self._unlock_tries)
                    except (GoodreadsBlocked, GoodreadsError) as excb:
                        _log.warning("upplåsning misslyckades fortfarande blockerad: %s", excb)
                        books = []
                    except Exception as exc2:  # noqa: BLE001
                        _log.warning("Upplåsning misslyckades: %s", exc2)
                        self.on_status(f"Upplåsning misslyckades: {exc2}")
                if not books:
                    note = (note + " | " if note else "") + "Goodreads blockerad"
                    self.on_status(note)
            except GoodreadsError as exc:
                _log.warning("goodreads-fel för %r: %s", q, exc)
                note = (note + " | " if note else "") + f"Goodreads-fel: {exc}"

        # Goodreads index är i praktiken engelskt: svenska titlar (även sådana
        # utan å/ä/ö, t.ex. "Isprinsessan") ger ofta noll träffar.
        base_title = split_series(title)[0]
        needs_bridge = (
            not books
            and self.options.use_title_bridge
            and self.bridge is not None
            and not getattr(self.client, "blocked", False)
            and len(base_title) >= 3
        )
        if needs_bridge:
            _log.info("goodreads gav 0 träffar för %r — provar originaltitlar via Wikipedia", q)
            _log.debug("QUERY DETAIL 9555%%: title=%r author=%r clean_q=%r series=%r part=%r folder=%r fname=%r", title, author, clean_query(title, author) if "clean_query" in dir() else q, split_series(title)[0] if "split_series" in dir() else title, "", folder_title if "folder_title" in locals() else "", fname if "fname" in locals() else "")
            for cand in (self.bridge.lookup(split_series(title)[0]) or [])[:2]:
                _log.info("originaltitel-kandidat: %r", cand)
                self.on_status(f"Provar originaltitel: {cand}")
                try:
                    books = self.client.search_best(clean_query(cand, author), limit=self.options.max_candidates)
                except (GoodreadsBlocked, GoodreadsError):
                    books = []
                if books:
                    note = (note + " | " if note else "") + f"matchad via originaltiteln '{cand}'"
                    break

        if not books and self.options.use_fallback and self.fallback is not None:
            _log.info("inga träffar för %r från goodreads/bridge — provar reservkällor", q)
            self.on_status("Provar reservkällor (Storytel/BookBeat/Open Library) …")
            books = self.fallback.search(q, limit=self.options.max_candidates)
            if books:
                src = getattr(books[0], "source", "") or ""
                source = src if src and src != "goodreads" else "openlibrary"
                _log.info("reservkälla gav %d träffar för %r (källa=%s)", len(books), q, source)
                pretty = {"openlibrary": "Open Library", "storytel": "Storytel",
                          "bookbeat": "BookBeat"}.get(source, source)
                note = (note + " | " if note else "") + f"träffar från {pretty} (Goodreads ej tillgänglig)"
        return books, source, note

    @staticmethod
    def _short_query(title: str, author: str) -> str:
        """'Harry Potter and the Philosopher's Stone' -> 'Harry Potter' (+ författare)."""
        small = {"om", "och", "i", "av", "the", "of", "and", "en", "ett", "den", "det"}
        # 1000000%: ta bort undertitel efter kolon
        base = split_series(title or "")[0].split(":")[0].strip()
        words = base.split()
        if len(words) <= 3:
            return ""
        keep = words[:3]
        while keep and keep[-1].lower() in small:
            keep.pop()
        if len(keep) < 2:
            return ""
        short = " ".join(keep)
        if author:
            short = f"{short} {author}"
        return short

    # ---------------------------------------------------------------- skanna
    def scan(self, root: str, recursive: bool = True) -> list[AudioFile]:
        self.on_status(f"Skannar {root} …")
        return library.scan(root, recursive=recursive)

    def groups(self, files: list[AudioFile]) -> list[list[AudioFile]]:
        return library.group_files(files)

    # ---------------------------------------------------------------- matcha
    def match_group(self, group: list[AudioFile]) -> tuple[Proposal, list]:
        """Matcha en grupp (en eller flera filer för samma bok) mot Goodreads."""
        rep = group[0]
        audio = AudioFile(
            path=rep.path,
            album=rep.album or rep.title or os.path.splitext(os.path.basename(rep.path))[0],
            title=rep.title or rep.album,
            artist=rep.artist or matching.guess_author_from_path(rep.path),
            year=rep.year,
            format=rep.format,
            group_label=library.label_group(group),
        )
        proposal = Proposal(audio=audio)
        proposal.paths = [f.path for f in group]  # type: ignore[attr-defined]
        proposal.group_size = len(group)          # type: ignore[attr-defined]
        proposal.total_size_mb = round(sum(f.size_mb or 0.0 for f in group), 1)  # type: ignore[attr-defined]
        # 50000000%: serie/del från filnamn/mapp ("Welcome … – Book 5", "Fjällbacka 01 - Isprinsessan"
        # "Harry Potter #1 - Philosopher's Stone") - fungerar helt offline.
        hint_series, hint_part = matching.hints_for(audio)
        # part för sökning: primärt hint_part, annars lösa "Del 3" i taggar/path
        part = hint_part or extract_part(audio.album) or extract_part(rep.path)

        # Sökfråga: välj den mest boklika källan (titel -> filnamn -> album -> serie).
        # Serie-prefix rensat: "Fjällbacka 01 - Isprinsessan" -> "Isprinsessan"
        # Normalisera separators så Windows-paths med "\" funkar även på Linux-test och vice versa
        _norm_path = (rep.path or "").replace("\\", "/")
        fname = os.path.splitext(os.path.basename(_norm_path))[0]
        fname = re.sub(r"\s*[-_.]?\s*\d{1,3}\s*$", "", fname)
        # Rensa underrubriker som \" - A novel...\" redan här så de inte blir sökfråga
        fname = re.sub(r"\s*[-–—]\s*A novel.*$", "", fname, flags=re.I).strip()
        # Rensa (Unabridged)/(Abridged) etc från fil- och mappnamn — annars \"Contention (Unabridged)\" ger 0 träffar
        fname = re.sub(r"\s*\((?:Unabridged|Abridged|Complete|Uncut)\)\s*$", "", fname, flags=re.I).strip()
        # mappnamnet är ofta bokliast ("The Green Mile (Disc 01)") när taggar
        # är rip-skrot ("Track 01")
        folder_raw = os.path.basename(os.path.dirname(_norm_path)) or ""
        folder_title = DISC_RE.sub(" ", folder_raw).strip()
        folder_title = re.sub(r"\s*\((?:Unabridged|Abridged|Complete|Uncut)\)\s*$", "", folder_title, flags=re.I).strip()
        folder_title = re.sub(r"\s*[-–—]\s*A novel.*$", "", folder_title, flags=re.I).strip()
        # Om mappen är import-roten \"lazylibrarian\" ska den inte användas som titel
        if folder_title.lower() == "lazylibrarian":
            folder_title = ""
        # rena titlar utan serieprefix har högsta prio — men serie-tolkad
        # titelrest och serie+nummer går före "Chapter 01"-skrot.
        clean_title = clean_title_from_hint(audio.title) or clean_title_from_hint(audio.album)
        clean_fname = clean_title_from_hint(fname)
        clean_folder = clean_title_from_hint(folder_title)
        # hint_rest direkt från parsern (om serie-mönstret bar på titelrest)
        _hs, _hp, _hr = extract_series_hint(audio.title, audio.album, fname, folder_title)
        # interna hjälpen: undvik att skicka "Chapter 01" som boktitel
        def _is_chapter_junk(t: str) -> bool:
            low = (t or "").lower()
            return "chapter" in low or "kapitel" in low
        q_candidates = [
            _hr if _hr and not _is_chapter_junk(_hr) else "",
            hint_series and f"{hint_series} {hint_part}" if hint_series and hint_part else "",
            clean_folder if clean_folder and not _is_chapter_junk(clean_folder) else "",
            clean_title if clean_title and not _is_chapter_junk(clean_title) else "",
            clean_fname if clean_fname and not _is_chapter_junk(clean_fname) else "",
            strip_part_words(audio.title) if not _is_chapter_junk(audio.title) else "",
            strip_part_words(audio.album) if not _is_chapter_junk(audio.album) else "",
            folder_title if not _is_chapter_junk(folder_title) else "",
            fname if not _is_chapter_junk(fname) else "",
            split_series(audio.album)[0] if not _is_chapter_junk(split_series(audio.album)[0]) else "",
            library.read_tags(rep.path).get("series", ""),
        ]
        # platta ut och filtrera — 100000000% bättre: behåll ordning, rensa bracket-skräp, hantera roman/band
        flat: list[str] = []
        seen = set()
        for c in q_candidates:
            if c and isinstance(c, str) and c.strip():
                cc = c.strip()
                # rensa " (Disc 01)" etc, men behåll "(Fjällbacka, #1)" som kan vara serieinfo
                cc = re.sub(r"\s*\(Disc[^)]*\)", " ", cc, flags=re.I).strip()
                cc = cc.split(" [")[0].strip()  # "[Imported]" direkt bort
                cc = cc.split(" (")[0].strip() if "disc" in cc.lower() or "imported" in cc.lower() or len(cc.split(" (")[-1]) > 25 else cc
                if not looks_like_junk_title(cc) and cc.lower() not in ("unknown album", "unknown"):
                    low = cc.lower()
                    if low not in seen:
                        flat.append(cc)
                        seen.add(low)
                        # även prova utan "Band N" "Del N" för ren titel
                        no_part = strip_part_words(cc)
                        if no_part and no_part != cc and no_part.lower() not in seen and not looks_like_junk_title(no_part):
                            flat.append(no_part)
                            seen.add(no_part.lower())
        # 100000000% bättre: lägg till författar-efternamn + multi-författare + titel-ensam
        try:
            # Behåll original-efternamn med stor bokstav (\"Hobb\" inte \"hobb\") — fix 2026-10-04
            artist_variants = []  # list[(norm_last, original_last)]
            if audio.artist:
                for part in re.split(r"\s*(?:,|;|&|\boch\b|\band\b)\s*", audio.artist, flags=re.I):
                    part = part.strip()
                    if not part:
                        continue
                    # original efternamn (sista ordet, behåll casing)
                    orig_last = part.split()[-1].strip(" .,-") if part.split() else ""
                    if orig_last and len(orig_last) >= 3 and orig_last.lower() not in {"unknown","okänd","various"}:
                        from .text import norm as _norm2
                        norm_last = _norm2(orig_last)
                        if norm_last:
                            artist_variants.append((norm_last, orig_last))
                # unik på norm_last, behåll original
                seen_lv = set()
                uniq = []
                for nl, ol in artist_variants:
                    if nl not in seen_lv:
                        seen_lv.add(nl)
                        uniq.append((nl, ol))
                artist_variants = uniq[:2]
            for base in list(flat)[:3]:
                if base and audio.artist and base.lower() not in (audio.artist.lower()):
                    for nl, ol in artist_variants:
                        if nl not in base.lower() and ol.lower() not in base.lower():
                            cand2 = f"{base} {ol}"
                            if cand2.lower() not in seen and not looks_like_junk_title(cand2):
                                flat.append(cand2)
                                seen.add(cand2.lower())
                    if base.lower() not in seen:
                        flat.append(base)
                        seen.add(base.lower())
            # även prova titel utan årtal/siffror ("Isprinsessan 2007" -> "Isprinsessan")
            for base in list(flat)[:2]:
                no_year = re.sub(r"\b(19|20)\d{2}\b", "", base).strip()
                no_year = " ".join(no_year.split())
                if no_year and no_year != base and no_year.lower() not in seen and not looks_like_junk_title(no_year):
                    flat.append(no_year)
                    seen.add(no_year.lower())
        except Exception:
            pass
        query = next((c for c in flat if not looks_like_junk_title(c)),
                     strip_part_words(audio.album) or strip_part_words(audio.title) or fname)
        query_candidates = flat if flat else [query]

        # Krav 21: redan organiserad bok -> arkiverad i historiken, ingen sökning.
        # 2026-10-04: även ljudkvalitet sparas — om samma bok laddas med bättre ljud, fråga om ersättning
        rematch = False   # True om användaren svarat "matcha på nytt" på frågan
        if self.options.skip_done:
            cur = library.read_tags(rep.path)
            ent = self.history.find_match(audio.title or audio.album,
                                          audio.artist,
                                          cur.get("series", ""),
                                          cur.get("series_number", ""))
            if ent:
                # Beräkna ljudkvalitet för inkommande filer vs sparad historik
                try:
                    from .history import audio_description as _ad, is_better_audio as _is_better, summarize_audio_qualities as _summ
                    from . import audioinfo as _ai
                    new_quals = []
                    for af in group[:4]:
                        if af.path and os.path.exists(af.path):
                            try:
                                new_quals.append(_ai.probe(af.path))
                            except Exception:
                                continue
                    new_audio = _summ(new_quals) if new_quals else {}
                    old_audio = ent.get("audio") or {}
                    is_better = _is_better(new_audio, old_audio) if old_audio else False
                    # Spara för dialogen i GUI (så den kan visa jämförelse)
                    proposal._new_audio = new_audio  # type: ignore[attr-defined]
                    proposal._old_audio = old_audio  # type: ignore[attr-defined]
                    proposal._is_better_audio = is_better  # type: ignore[attr-defined]
                    if is_better:
                        old_desc = _ad(old_audio)
                        new_desc = _ad(new_audio)
                        proposal.note = f"tidigare importerad med sämre ljud ({old_desc}) — ny version har bättre ljud ({new_desc}) — fråga om ersättning"
                        log.info("historikträff med bättre ljud: %r gammal=%s ny=%s", audio.group_label, old_desc, new_desc)
                    else:
                        proposal.note = "tidigare importerad — hoppas över (matchas inte på nytt)"
                except Exception as _e:
                    log.debug("ljudjämförelse för historik misslyckades: %s", _e)
                    proposal.note = "tidigare importerad — hoppas över (matchas inte på nytt)"
                proposal.status = "klar (historik)"
                proposal.skipped = True
                proposal.source = "historik"
                proposal.new_title = ent.get("title") or audio.title
                proposal.new_artist = ent.get("author") or audio.artist
                proposal.new_series = ent.get("series") or ""
                proposal.new_series_number = ent.get("number") or ""
                if self.on_history_hit is None or self.on_history_hit(proposal, ent):
                    log.info("matchning %r -> klar (historik) via %s, ingen sökning görs",
                             audio.group_label, ent.get("key", "?")[:12])
                    return proposal, []
                # användaren vill matcha på nytt -> nollställ och sök som vanligt
                rematch = True
                proposal.status, proposal.skipped, proposal.source = "ej matchad", False, ""
                proposal.note = ""
                # Markera för ersättning om nya har bättre ljud (för organize-rensning)
                try:
                    if getattr(proposal, "_is_better_audio", False):
                        proposal._replace_old = True  # type: ignore[attr-defined]
                        proposal._old_output = ent.get("output")  # type: ignore[attr-defined]
                        log.info("bättre ljud valt för ersättning: %r gammal=%s", audio.group_label, ent.get("output"))
                except Exception:
                    pass
                log.info("matchning %r -> användaren vill matcha på nytt trots historikträff",
                         audio.group_label)

        # 100000%: prova query_candidates i turordning (max 5) tills träff
        books: list = []
        source = ""
        note = ""
        tried = []
        for q in query_candidates[:5]:
            if q in tried:
                continue
            tried.append(q)
            self.on_status(f"Söker: {q}")
            books, source, note = self.resolve(q, audio.artist, part=part)
            if books:
                query = q
                break
            # även vid blockerad, prova nästa kandidat om fallback kan hitta
            if getattr(self.client, "blocked", False) and source.startswith("fallback"):
                # fallback gav tomt — prova nästa
                continue
        if not books:
            # ingen kandidat gav träff — behåll sista försökets note/source
            pass
        proposal.source = source
        if note:
            proposal.note = note
        if not books:
            proposal.status = "blockerad" if getattr(self.client, "blocked", False) else "ej matchad"
            if not note:
                proposal.note = "Inga träffar (varken Goodreads eller reservkälla)"
            log.warning("matchning %r -> %s. Orsak: %s",
                        audio.group_label, proposal.status, proposal.note)
            return proposal, []

        # 100000%: föredra titeln som faktiskt gav träff (query) vid rankning, inte alltid audio.title
        prefer = query if 'query' in locals() and query else (audio.title or audio.album)
        matches = _clean_ranked(matching.rank(books, audio), prefer)
        if not matches:
            proposal.status = "ej matchad"
            proposal.note = "Inga Goodreads-träffar"
            return proposal, []

        best = matches[0]
        proposal.match = best
        proposal.candidates = matches  # type: ignore[attr-defined]
        self._fill(proposal, best, group, part)
        proposal.status = matching.status_for(best.score)
        # fel författare får aldrig bli "matchad" (t.ex. "Insomnia" av King
        # vs J.R. Johansson) — titeln lik men artist-taggen säger emot
        if (proposal.status == "matchad" and best.author_score < 0.25
                and audio.artist):
            proposal.status = "behöver koll"
            proposal.note = (proposal.note + " | " if proposal.note else "") + \
                "författaren stämmer inte med filens artist-tagg — kontrollera"
        log.info("match %r -> %r (%.2f, %s%s)", audio.group_label,
                 best.book.display, best.score, proposal.status,
                 f", minus {best.penalty:.2f}" if getattr(best, "penalty", 0) > 0 else "")
        if self.options.skip_done and not rematch and self.history.is_done(proposal.identity()):
            # Kvalitetsmedveten historik-koll även efter matchning (andra spärren).
            # Om samma nyckel redan finns men nya filerna har bättre ljud, ska vi inte
            # automatiskt hoppa över — fråga istället.
            _skip_history = True
            _is_better_after = False
            try:
                ent_after = self.history.find(proposal.identity())
                if ent_after and ent_after.get("audio"):
                    from .history import is_better_audio as _is_b2, summarize_audio_qualities as _summ2b, audio_description as _ad2
                    from . import audioinfo as _ai2b
                    new_quals2: list = []
                    for af in group[:4]:
                        _pp = getattr(af, "path", None)
                        if _pp and os.path.exists(_pp):
                            try:
                                new_quals2.append(_ai2b.probe(_pp))
                            except Exception:
                                continue
                    new_audio2 = _summ2b(new_quals2) if new_quals2 else {}
                    old_audio2 = ent_after.get("audio") or {}
                    if new_audio2 and old_audio2 and _is_b2(new_audio2, old_audio2):
                        _is_better_after = True
                        # Sätt attribut för dialog
                        proposal._new_audio = new_audio2  # type: ignore[attr-defined]
                        proposal._old_audio = old_audio2  # type: ignore[attr-defined]
                        proposal._is_better_audio = True  # type: ignore[attr-defined]
                        proposal.note = f"tidigare importerad med sämre ljud ({_ad2(old_audio2)}) — ny version har bättre ljud ({_ad2(new_audio2)}) — fråga om ersättning"
                        log.info("historikträff med bättre ljud efter matchning %r gammal=%s ny=%s",
                                 proposal.identity(), _ad2(old_audio2), _ad2(new_audio2))
                        # Fråga användaren om vi har en callback
                        if self.on_history_hit is not None:
                            try:
                                _skip_history = bool(self.on_history_hit(proposal, ent_after))
                            except Exception as exc:
                                log.warning("on_history_hit efter match fel: %s", exc)
                                _skip_history = True
                        else:
                            _skip_history = False  # utan GUI: tillåt ersättning
                        if not _skip_history:
                            try:
                                proposal._replace_old = True  # type: ignore[attr-defined]
                                proposal._old_output = ent_after.get("output")  # type: ignore[attr-defined]
                            except Exception:
                                pass
            except Exception as exc:
                log.debug("kvalitetsjämförelse efter match fel: %s", exc)
            if _skip_history and not _is_better_after:
                proposal.status = "klar (historik)"
                proposal.skipped = True
                log.info("hoppar över %r — redan färdigbehandlad", audio.group_label)
            elif _skip_history and _is_better_after:
                proposal.status = "klar (historik)"
                proposal.skipped = True
                log.info("hoppar över %r trots bättre ljud — användaren valde att behålla gammal", audio.group_label)
            else:
                # Bättre ljud och användaren vill ersätta — hoppa inte över
                log.info("hoppar INTE över %r — bättre ljud och användaren vill ersätta", audio.group_label)
                # Behåll proposal.status som matchad, säkerställ att skipped är False
                proposal.skipped = False
        if matching.needs_manual(matches):
            proposal.status = "behöver koll"
            extra = f"Två nära träffar ({best.score:.2f} vs {matches[1].score:.2f})"
            proposal.note = f"{proposal.note} | {extra}" if proposal.note else extra
        log.info("matchning %r -> %s (källa=%s, poäng=%s) %s",
                 audio.group_label, proposal.status, proposal.source,
                 f"{best.score:.2f}", proposal.note or "")
        return proposal, matches

    def _fill(self, proposal: Proposal, match, group: list[AudioFile], part: str) -> None:
        book = match.book
        # skräputgåvor ("… [Imported] [Paperback] …") får låna titeltext av en ren utgåva
        title = book.title
        if looks_like_junk_title(title):
            for m in getattr(proposal, "candidates", None) or []:
                alt = m.book.title
                if not looks_like_junk_title(alt) and title_similarity(alt, title) >= 0.7:
                    title = alt
                    break
        proposal.new_title = title
        proposal.new_artist = ", ".join(book.authors) or proposal.audio.artist
        series = clean_series(book.series)
        number = book.series_number or part
        # 50000000% ABS: om Goodreads saknar serie men filen tydligt säger serie
        # ("Fjällbacka 01 - Isprinsessan"), använd hint — annars hamnar boken
        # fel i ABS (utan serie-mapp och utan serie-tagg).
        if not series:
            try:
                hs, hp = matching.hints_for(proposal.audio)
                if hs and hs.strip():
                    series = clean_series(hs)
                    if not number and hp:
                        number = hp
            except Exception:
                pass
        proposal.new_series = series
        proposal.new_series_number = number
        proposal.new_year = book.year if self.options.include_year else ""
        if proposal.source.startswith("goodreads"):
            try:
                self.client.enrich(book)
            except Exception:  # noqa: BLE001 - metadata är aldrig kritiskt
                pass
        proposal.new_subtitle = book.subtitle or ""
        proposal.new_description = (book.description or "").strip()
        proposal.new_narrator = ", ".join(book.narrators) if book.narrators else ""
        proposal.new_publisher = book.publisher or ""
        proposal.new_genre = ", ".join(book.genres[:3]) if book.genres else ""
        proposal.new_isbn = book.isbn or ""
        proposal.new_asin = book.asin or ""
        proposal.new_language = book.language or ""

        if self.options.album_style == "series" and series:
            album = f"{series}, #{number}" if number else series
        else:
            album = book.title
            if series and number:
                album = f"{series}, #{number}"
            elif series:
                album = series
        proposal.new_album = album

        if len(group) > 1:
            total = len(group)
            proposal.new_track = ""
        else:
            proposal.new_track = ""
        # spårnummer per fil skrivs i apply()

    # ---------------------------------------------------------------- skriv
    def build_file_fields(self, proposal: Proposal, index: int, total: int, path: str | None = None) -> dict:
        """Fält för en enskild fil i gruppen (spårnummer n/total)."""
        fields = tags.proposal_to_fields(proposal, write_series=self.options.write_series)
        if total > 1:
            fields["track"] = f"{index + 1}/{total}"
        elif proposal.audio.track:
            fields["track"] = proposal.audio.track
        else:
            fields.pop("track", None)
        # 1) ReplayGain — beräkna per fil om aktiverat och ffmpeg finns
        if getattr(self.options, "replaygain", False) and path:
            try:
                from . import audioinfo as _ai
                gain, peak = _ai.replaygain(path)
                if gain:
                    fields["replaygain_track_gain"] = gain
                if peak:
                    fields["replaygain_track_peak"] = peak
            except Exception:
                pass
        return fields

    def apply(self, proposal: Proposal, dry_run: bool = False) -> list[tags.WriteResult]:
        paths = getattr(proposal, "paths", None) or [proposal.audio.path]
        total = len(paths)
        results: list[tags.WriteResult] = []
        for i, path in enumerate(paths):
            fields = self.build_file_fields(proposal, i, total, path=path)
            if dry_run:
                results.append(tags.WriteResult(path, True, sorted(fields)))
                continue
            res = tags.write_file(path, fields, backup=self.options.backup)
            results.append(res)
        proposal.applied = all(r.ok for r in results) and bool(results)
        return results

    # ---------------------------------------------------------------- organisera
    def organize(self, proposal: Proposal, group: list[AudioFile], out_root: str,
                 move: bool = False) -> organize.OrganizeResult:
        """Kopiera/flytta + tagga + .md + historik, Audiobookshelf-struktur."""
        # 2026-10-04: Om samma bok redan finns med sämre ljud och användaren valt
        # "Ersätt", rensa gamla output-mappen innan ny kopiering (så gamla filer
        # inte ligger kvar bredvid nya med bättre kvalitet).
        if getattr(proposal, "_replace_old", False):
            old_output = getattr(proposal, "_old_output", None)
            # Fallback: hämta från historiken om attribut saknas
            if not old_output:
                try:
                    old_output = (self.history.find(proposal.identity()) or {}).get("output")
                except Exception:
                    old_output = None
            if old_output and os.path.isdir(old_output):
                try:
                    import shutil
                    # Säkerhet: rensa endast om mappen ligger under out_root eller är den exakta gamla mappen
                    abs_old = os.path.abspath(old_output)
                    abs_root = os.path.abspath(out_root) if out_root else ""
                    if not abs_root or abs_old.startswith(abs_root) or os.path.commonpath([abs_old, abs_root]) == abs_root:
                        shutil.rmtree(old_output)
                        log.info("ersätter med bättre ljud — tog bort gammal output %s", old_output)
                        # Återskapa inte här, organize.execute skapar vid behov
                    else:
                        # Om gamla mappen ligger utanför out_root (ovanligt), rensa endast filer inuti
                        for _f in os.listdir(old_output):
                            _fp = os.path.join(old_output, _f)
                            try:
                                if os.path.isfile(_fp):
                                    os.remove(_fp)
                                elif os.path.isdir(_fp):
                                    shutil.rmtree(_fp)
                            except Exception:
                                pass
                        log.info("ersätter med bättre ljud — rensade filer i %s", old_output)
                except Exception as exc:
                    log.warning("kunde inte rensa gammal output %s vid ersättning: %s", old_output, exc)
        # Om ReplayGain är aktiverat, beräkna per källfil och lägg på förslaget
        # så att organize.execute kan återanvända samma fält per målfil
        # (vi lagrar temporärt på proposal för att undvika API-bryt).
        if getattr(self.options, "replaygain", False):
            try:
                from . import audioinfo as _ai
                # beräkna per fil i gruppen och spara som dict path->(gain,peak)
                rg_map: dict[str, tuple[str | None, str | None]] = {}
                for af in group:
                    rg_map[af.path] = _ai.replaygain(af.path)
                # spara på proposal för senare användning i execute-loopen
                proposal._rg_map = rg_map  # type: ignore[attr-defined]
            except Exception:
                pass
        res = organize.execute(proposal, group, out_root, move=move,
                               write_series=self.options.write_series)
        # Efter-skriv ReplayGain på målfilerna (om beräknat) — utan att störa befintligt flöde
        if getattr(proposal, "_rg_map", None) and not res.errors:
            try:
                from . import tags as _tags
                for act in res.actions:
                    if act.kind in ("copy", "move") and act.dst:
                        src = act.src
                        gain_peak = getattr(proposal, "_rg_map", {}).get(src)
                        if gain_peak and (gain_peak[0] or gain_peak[1]):
                            rg_fields: dict = {}
                            if gain_peak[0]:
                                rg_fields["replaygain_track_gain"] = gain_peak[0]
                            if gain_peak[1]:
                                rg_fields["replaygain_track_peak"] = gain_peak[1]
                            wr = _tags.write_file(act.dst, rg_fields, backup=False)
                            if wr.ok:
                                log.info("replaygain skrivet %s -> %s", act.dst, rg_fields)
            except Exception as exc:
                log.warning("replaygain efter-skriv misslyckades: %s", exc)
        if res.errors:
            for e in res.errors:
                log.error("organize: %s", e)
        else:
            key = proposal.identity()
            paths = [a.dst for a in res.actions if a.kind in ("copy", "move", "tags")]
            # Spara även ljudkvalitet i historiken (för framtida "bättre ljud?"-fråga)
            audio_info = None
            try:
                from .history import summarize_audio_qualities as _summ2
                from . import audioinfo as _ai2
                quals = []
                for dst in paths[:6]:
                    if dst and os.path.exists(dst):
                        try:
                            quals.append(_ai2.probe(dst))
                        except Exception:
                            continue
                # Fallback: prova källfiler om output ännu ej finns (dry-run)
                if not quals:
                    for af in group[:4]:
                        if af.path and os.path.exists(af.path):
                            try:
                                quals.append(_ai2.probe(af.path))
                            except Exception:
                                continue
                if quals:
                    audio_info = _summ2(quals)
            except Exception as _e:
                log.debug("kunde inte sammanfatta ljud för historik: %s", _e)
            self.history.add(
                key,
                title=proposal.new_title,
                author=proposal.new_artist,
                series=proposal.new_series,
                number=proposal.new_series_number,
                url=proposal.match.book.url if proposal.match else "",
                score=proposal.match.score if proposal.match else 0.0,
                source=proposal.source or "",
                output=res.title_dir,
                files=paths,
                audio=audio_info,
            )
            log.info("historik: %r klar -> %s%s", proposal.new_title, res.title_dir, f" ({audio_info.get('bitrate_kbps')} kbps {audio_info.get('format')})" if audio_info and audio_info.get("bitrate_kbps") else "")
        return res

    # -------------------------------------------------------- metadata-uppdatering (krav 34)
    def check_output_for_updates(self, out_root: str, on_proposal=None) -> list[Proposal]:
        """Skanna redan organiserad outputmapp och jämför taggar med färsk Goodreads-data.

        Returnerar förslag där minst ett fält skiljer sig (titel/författare/serie/del/år/undertext/...)
        eller där omslag/.md saknas. Fungerar helt offline om historiken har URL, annars ny sökning.
        """
        import os as _os
        files = self.scan(out_root, recursive=True)
        if not files:
            return []
        groups = self.groups(files)
        out: list[Proposal] = []
        for group in groups:
            rep = group[0]
            cur = library.read_tags(rep.path)
            # gissa titel/författare från taggar eller mapp
            cur_title = cur.get("title") or rep.title or _os.path.splitext(_os.path.basename(rep.path))[0]
            cur_artist = cur.get("artist") or rep.artist
            cur_series = cur.get("series", "")
            cur_number = cur.get("series_number", "")
            # försök hitta historikpost via output-sökväg eller nyckel
            hist_entry = None
            # sök via output i historiken (exakt mapp)
            title_dir = _os.path.dirname(group[0].path)
            # gå uppåt tills vi hittar en historikpost som matchar output
            for e in self.history.entries():
                out_path = e.get("output", "")
                if out_path and (title_dir == out_path or title_dir.startswith(out_path + _os.sep)):
                    hist_entry = e
                    break
            if not hist_entry:
                # fallback: match via titel/författare/serie
                hist_entry = self.history.find_match(cur_title, cur_artist, cur_series, cur_number)
            book = None
            source = "goodreads"
            # 1) försök via sparad Goodreads-länk (mest exakt)
            if hist_entry and hist_entry.get("url"):
                try:
                    book = self.client.book(hist_entry["url"])
                except Exception:
                    book = None
            # 2) annars ny sökning mot Goodreads/fallback
            if book is None:
                # använd hint för bättre sökning (serie-mönster)
                hint_series, hint_part = matching.hints_for(rep)
                # bygg audio för sökning (likt match_group men från cur-taggar)
                audio_tmp = rep
                # försök matcha med nuvarande titel/författare
                q_title = cur_title
                # om titel är skräp, använd mappnamn
                if looks_like_junk_title(q_title):
                    q_title = _os.path.basename(_os.path.dirname(rep.path)) or q_title
                books, source, _note = self.resolve(q_title, cur_artist, part=hint_part or cur_number)
                if not books:
                    continue
                # ranka och ta bästa
                # skapa en tillfällig AudioFile för rankning
                tmp_af = AudioFile(path=rep.path, title=cur_title, artist=cur_artist, album=cur.get("album",""), year=cur.get("year",""))
                ranked = _clean_ranked(matching.rank(books, tmp_af), q_title)
                if not ranked:
                    continue
                book = ranked[0].book
            if not book:
                continue
            # bygg förslag med färsk data
            audio_for_fill = AudioFile(path=rep.path, title=cur_title, artist=cur_artist, album=cur.get("album",""))
            proposal = Proposal(audio=audio_for_fill)
            proposal.paths = [f.path for f in group]
            proposal.group_size = len(group)
            proposal.total_size_mb = round(sum(f.size_mb or 0 for f in group),1)
            # använd samma _fill-logik för att få nya fält (inkl hint-fallback)
            # skapa en Match med book
            from .models import Match
            m = Match(book=book, score=1.0)
            # låtsas att vi har kandidater för junk-hantering
            proposal.candidates = [m]
            # part från hint eller befintlig
            hint_series2, hint_part2 = matching.hints_for(rep)
            part_for_fill = hint_part2 or cur_number
            self._fill(proposal, m, group, part_for_fill)
            proposal.source = source
            # beräkna diff mot nuvarande taggar
            new_fields = tags.proposal_to_fields(proposal, write_series=self.options.write_series)
            # även år etc: proposal_to_fields inkluderar redan
            cur_fields = {k: v for k,v in cur.items() if k in new_fields}
            # jämför varje fält som skulle skrivas
            diffs = []
            for k, new_val in new_fields.items():
                cur_val = cur.get(k, "")
                # normalisera för jämförelse (strip)
                if (new_val or "").strip() != (cur_val or "").strip():
                    diffs.append((k, cur_val, new_val))
            # även kolla omslag
            title_dir = _os.path.dirname(group[0].path)
            cover_path = _os.path.join(title_dir, "cover.jpg")
            md_path = _os.path.join(title_dir, f"{proposal.new_title or cur_title}.md")
            # md jämförs inte hårt — om titel/serie ändrats bör md uppdateras
            needs_cover = bool(book.cover and not _os.path.exists(cover_path))
            needs_md = bool(diffs)  # om något fält ändras bör md också skrivas om
            if diffs or needs_cover or needs_md:
                proposal.status = "behöver uppdateras"
                # bygg läsbar note
                if diffs:
                    proposal.note = "Ändringar: " + ", ".join(f"{k}: '{old}' → '{new}'" for k,old,new in diffs[:4])
                    if len(diffs) > 4:
                        proposal.note += f" (+{len(diffs)-4} till)"
                elif needs_cover:
                    proposal.note = "Omslag saknas — kommer att hämtas"
                else:
                    proposal.note = "Metadata skiljer sig"
                proposal._diffs = diffs  # type: ignore
                proposal._needs_cover = needs_cover  # type: ignore
                proposal._needs_md = needs_md  # type: ignore
            else:
                proposal.status = "aktuell"
                proposal.note = "Inga ändringar"
            proposal.match = m
            # spara diff för apply
            if on_proposal:
                on_proposal(proposal)
            out.append(proposal)
        return out

    def apply_update(self, proposal: Proposal, group: list[AudioFile]) -> list:
        """Skriv uppdaterad metadata direkt i outputmappen (ingen flytt, bara taggar+md+cover)."""
        import os as _os
        from . import audioinfo
        results = []
        fields = tags.proposal_to_fields(proposal, write_series=self.options.write_series)
        total = len(group)
        # sortera filer som vid organisering
        ordered = organize.order_files(group)
        for i, af in enumerate(ordered, 1):
            f = {**fields}
            if total > 1:
                f["track"] = f"{i}/{total}"
            elif af.track:
                f["track"] = af.track
            # 1) ReplayGain per fil vid uppdatering
            if getattr(self.options, "replaygain", False):
                try:
                    from . import audioinfo as _ai
                    gain, peak = _ai.replaygain(af.path)
                    if gain:
                        f["replaygain_track_gain"] = gain
                    if peak:
                        f["replaygain_track_peak"] = peak
                except Exception:
                    pass
            res = tags.write_file(af.path, f, backup=False)
            results.append(res)
            if res.ok:
                log.info("uppdaterade taggar %s -> %s", af.path, sorted(res.written))
            else:
                log.warning("misslyckades uppdatera %s: %s", af.path, res.error)
        # uppdatera .md (alltid om diff fanns)
        title_dir = _os.path.dirname(group[0].path)
        # hitta befintlig md (kan heta gammal titel)
        md_files = [f for f in _os.listdir(title_dir) if f.lower().endswith(".md")] if _os.path.isdir(title_dir) else []
        # skriv ny md med nytt titel-namn
        new_md_name = f"{proposal.new_title or proposal.audio.title}.md"
        md_path = _os.path.join(title_dir, new_md_name)
        try:
            quals = [audioinfo.probe(f.path) for f in ordered]
            md = audioinfo.book_md(
                title=proposal.new_title or proposal.audio.title,
                author=proposal.new_artist,
                album=proposal.new_album,
                series=proposal.new_series,
                series_number=proposal.new_series_number,
                year=proposal.new_year,
                url=proposal.match.book.url if proposal.match else "",
                source=proposal.source or "",
                score=proposal.match.score if proposal.match else 0.0,
                qualities=quals,
                extra_note=proposal.note,
                subtitle=proposal.new_subtitle,
                narrator=proposal.new_narrator,
                publisher=proposal.new_publisher,
                genre=proposal.new_genre,
                language=proposal.new_language,
                description=proposal.new_description,
            )
            with open(md_path, "w", encoding="utf-8") as fh:
                fh.write(md)
            # rensa gammal md om namnet ändrats
            for old_md in md_files:
                old_path = _os.path.join(title_dir, old_md)
                if old_path != md_path and _os.path.exists(old_path):
                    try:
                        _os.remove(old_path)
                        log.info("tog bort gammal md %s", old_path)
                    except OSError:
                        pass
            results.append(tags.WriteResult(md_path, True, ["md"]))
        except OSError as exc:
            results.append(tags.WriteResult(md_path, False, [], str(exc)))
        # omslag: hämta om saknas eller om URL ändrats
        cover_url = (proposal.match.book.cover if proposal.match else "") or getattr(proposal, "cover_url", "")
        cover_path = _os.path.join(title_dir, "cover.jpg")
        if cover_url:
            needs = not _os.path.exists(cover_path) or getattr(proposal, "_needs_cover", False)
            # om historiken hade annan url kan vi alltid uppdatera — för 50000000% enkelhet: hämta om cover saknas
            if needs:
                try:
                    import requests
                    resp = requests.get(cover_url, headers={"User-Agent": "Audiobro/1.0"}, timeout=30)
                    head = resp.content[:4]
                    if resp.status_code == 200 and (head.startswith(b"\xff\xd8\xff") or head.startswith(b"\x89PNG") or head.startswith(b"GIF8")):
                        with open(cover_path, "wb") as fh:
                            fh.write(resp.content)
                        log.info("uppdaterade omslag %s", cover_path)
                        results.append(tags.WriteResult(cover_path, True, ["cover"]))
                except Exception as exc:
                    log.warning("kunde inte hämta omslag %s: %s", cover_url, exc)
        # uppdatera historikpost om den finns — även ljudkvalitet (om output-filerna finns)
        try:
            key = proposal.identity()
            # hitta befintlig post via output eller nyckel
            for e in self.history.entries():
                if e.get("output") and title_dir.startswith(e["output"]) or e.get("key") == key:
                    audio_info2 = None
                    try:
                        from .history import summarize_audio_qualities as _summ3
                        from . import audioinfo as _ai3
                        quals2 = []
                        for _fp in [f.path for f in group][:4]:
                            if _fp and _os.path.exists(_fp):
                                try:
                                    quals2.append(_ai3.probe(_fp))
                                except Exception:
                                    continue
                        if quals2:
                            audio_info2 = _summ3(quals2)
                    except Exception:
                        audio_info2 = None
                    self.history.add(key, title=proposal.new_title, author=proposal.new_artist, series=proposal.new_series, number=proposal.new_series_number, url=proposal.match.book.url if proposal.match else e.get("url",""), score=proposal.match.score if proposal.match else 0, source=proposal.source or "", output=title_dir, files=[f.path for f in group], audio=audio_info2)
                    break
        except Exception:
            pass
        return results

    # ---------------------------------------------------------------- hela flödet
    def run(self, root: str, dry_run: bool = True, recursive: bool = True,
            on_proposal: Optional[Callable[[Proposal], None]] = None) -> list[Proposal]:
        files = self.scan(root, recursive=recursive)
        self.on_status(f"{len(files)} ljudfiler hittade")
        out: list[Proposal] = []
        for group in self.groups(files):
            proposal, _ = self.match_group(group)
            out.append(proposal)
            if on_proposal:
                on_proposal(proposal)
        self.client.save_cache()
        done = sum(1 for p in out if p.skipped)
        if done:
            self.on_status(f"{done} bok/böcker hoppades över (redan klara enligt historiken)")
        return out

    # ---------------------------------------------------------------- rekommendationer
    def recommend(self, owned_titles: list[str], author_counts=None,
                  series_owned=None) -> list:
        from collections import Counter

        from .recommendations import recommend

        def search_fn(q, limit=8):
            try:
                return self.client.search_best(q, limit=limit)
            except (GoodreadsBlocked, GoodreadsError):
                if self.fallback is not None:
                    return self.fallback.search(q, limit=limit)
                return []

        # senaste böckerna i historiken med Goodreads-länk -> "liknande böcker"
        hist_books = [(e.get("title", ""), e.get("url", ""))
                      for e in reversed(self.history.entries()) if e.get("url")]

        def similar_fn(url):
            return self.client.similar(url) if hasattr(self.client, "similar") else []

        return recommend(search_fn, author_counts or Counter(),
                         series_owned or {}, owned_titles,
                         similar_fn=similar_fn, history_books=hist_books)

    # ---------------------------------------------------------------- manuellt
    def match_text(self, title: str, author: str = "", year: str = "") -> tuple[Proposal, list]:
        """Matcha en manuellt angiven/OCR-läst titel (skärmbildsläget)."""
        audio = AudioFile(path=f"<manuellt> {title}", album=title, title=title, artist=author, year=year)
        audio.group_label = title
        proposal = Proposal(audio=audio)
        proposal.paths = []  # type: ignore[attr-defined]
        proposal.group_size = 1  # type: ignore[attr-defined]
        self.on_status(f"Söker: {title}")
        books, source, note = self.resolve(title, author)
        proposal.source = source
        if note:
            proposal.note = note
        if not books:
            proposal.status = "blockerad" if getattr(self.client, "blocked", False) else "ej matchad"
            return proposal, []
        matches = _clean_ranked(matching.rank(books, audio), title)
        if matches:
            best = matches[0]
            proposal.match = best
            proposal.candidates = matches  # type: ignore[attr-defined]
            self._fill(proposal, best, [audio], extract_part(title))
            proposal.status = matching.status_for(best.score)
        else:
            proposal.status = "ej matchad"
        return proposal, matches

    def from_goodreads_url(self, url: str, audio: Optional[AudioFile] = None) -> tuple[Proposal, list]:
        """Använd en Goodreads-länk direkt (100 % rätt bok, ingen gissning).

        Fungerar även när sökindex är blockerat — boksidan hämtas direkt.
        Om WAF blockerar provas automatisk upplåsning via Brave (upp till 3 försök)
        precis som vid sökning.
        """
        from .openlibrary import clean_query

        audio = audio or AudioFile(path=url, album=url, title=url)
        proposal = Proposal(audio=audio)
        proposal.paths = []  # type: ignore[attr-defined]
        proposal.group_size = 1  # type: ignore[attr-defined]
        # Normalisera länk: Goodreads accepterar ?ac=1 etc men vi vill cacha utan query-brus
        # (client.book hanterar query ändå, men vi loggar ren url)
        try:
            book = self.client.book(url)
        except GoodreadsBlocked as exc:
            # Försök låsa upp via webbläsare om aktiverat — samma logik som resolve()
            if self.options.auto_token and self.token_fetcher and getattr(self, "_unlock_tries", 0) < 3:
                self._unlock_tries = getattr(self, "_unlock_tries", 0) + 1
                self._unlocked = True
                self.on_status(f"Goodreads blockerad — låser upp via din webbläsare … (försök {self._unlock_tries}/3)")
                try:
                    token = self.token_fetcher()
                    if token:
                        self.client.set_browser_token(token)
                        book = self.client.book(url)
                    else:
                        proposal.status = "blockerad"
                        proposal.note = str(exc)
                        return proposal, []
                except GoodreadsBlocked as exc2:
                    proposal.status = "blockerad"
                    proposal.note = str(exc2)
                    return proposal, []
                except GoodreadsError as exc2:
                    proposal.status = "fel"
                    proposal.note = str(exc2)
                    return proposal, []
                except Exception as exc2:
                    self.on_status(f"Upplåsning misslyckades: {exc2}")
                    proposal.status = "blockerad"
                    proposal.note = str(exc)
                    return proposal, []
            else:
                proposal.status = "blockerad"
                proposal.note = str(exc)
                return proposal, []
        except GoodreadsError as exc:
            proposal.status = "fel"
            proposal.note = str(exc)
            return proposal, []
        m = matching.score_audio(audio, book)
        m.score = 1.0  # länken är ett uttryckligt val — ersätter alla reservkällor
        proposal.match = m
        # _fill sätter alla fält från Goodreads-boken (titel/serie/författare/omslag etc)
        self._fill(proposal, m, [audio], book.series_number)
        proposal.status = "matchad"
        proposal.source = "goodreads:länk"
        proposal.note = "100% träff via klistrad Goodreads-länk — ersätter reservkälla"
        # spara även paths om de följde med via audio (för grupp-manual)
        if not getattr(proposal, "paths", None):
            proposal.paths = [audio.path]  # type: ignore[attr-defined]
        return proposal, [m]
