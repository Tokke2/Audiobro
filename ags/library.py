"""Skanna ljudboksfiler, läs taggar och gruppera i album."""
from __future__ import annotations

import os
import re
from typing import Iterable

from .models import AudioFile
from .text import DISC_RE, extract_part, looks_like_junk_title, norm, title_key

DISC_RE = re.compile(r"\b(?:cd|disc|skiva)\s*[-.]?\s*([0-9]{1,2})\b", re.I)


def detect_disc(path: str) -> int:
    """Hitta disc-nummer i mapp- eller filnamn ('CD1', 'Disc 2', 'skiva 3')."""
    parts = re.split(r"[\\/]", path or "")
    for cand in reversed(parts):
        m = DISC_RE.search(cand)
        if m:
            return int(m.group(1))
    return 0


AUDIO_EXT = {
    ".mp3": "mp3",
    ".m4b": "m4b",
    ".m4a": "m4a",
    ".aac": "aac",
    ".flac": "flac",
    ".ogg": "ogg",
    ".opus": "opus",
    ".wav": "wav",
}

SKIP_DIRS = {"@eaDir", ".Trash", ".DS_Store", "#recycle", ".git", ".idea"}


def read_tags(path: str) -> dict:
    """Läs metadata med mutagen; returnerar {} om mutagen saknas."""
    try:
        from mutagen import File as MFile
    except ImportError:
        return {}
    try:
        f = MFile(path)
    except Exception:
        f = None
    if f is None:
        # Fallback för filer som bara har ID3 utan MPEG-ram (t.ex. test-filer med enbart taggar)
        if path.lower().endswith(".mp3"):
            try:
                from mutagen.id3 import ID3 as _ID3
                f = _ID3(path)  # direkt ID3, funkar även utan ljudram
                # gör f kompatibelt med resten (tags = f)
                class _Fake:
                    tags = f
                f = _Fake()
            except Exception:
                return {}
        else:
            return {}
    out: dict = {}
    tags = f.tags
    if tags is None:
        return out
    kind = type(tags).__name__

    def _s(v):
        """Normalisera taggvärde till str (mutagen ger bytes för MP4 freeform)."""
        if v is None:
            return ""
        if isinstance(v, bytes):
            return v.decode("utf-8", errors="replace").strip()
        return str(v).strip()
    try:
        if kind == "ID3":
            out["title"] = _first(tags.getall("TIT2"))
            out["artist"] = _first(tags.getall("TPE1"))
            out["album"] = _first(tags.getall("TALB"))
            out["track"] = _first(tags.getall("TRCK"))
            out["year"] = _first(tags.getall("TDRC")) or _first(tags.getall("TYER"))
            out["genre"] = _first(tags.getall("TCON"))
            out["series"] = _first(tags.getall("TXXX:SERIES")) or _first(tags.getall("TXXX:SERIESNAME"))
            out["series_number"] = (_first(tags.getall("TXXX:SERIES_PART"))
                                    or _first(tags.getall("TXXX:SERIES-PART"))
                                    or _first(tags.getall("TXXX:PART"))
                                    or _first(tags.getall("TXXX:EPISODE_ID"))
                                    or _first(tags.getall("TXXX:MVIN")))
            out["subtitle"] = _first(tags.getall("TIT3"))
            out["narrator"] = _first(tags.getall("TCOM"))
            out["publisher"] = _first(tags.getall("TPUB"))
            out["description"] = _first(tags.getall("COMM"))
            out["language"] = _first(tags.getall("TLAN"))
            out["asin"] = _first(tags.getall("TXXX:ASIN"))
            out["isbn"] = _first(tags.getall("TXXX:ISBN"))
            out["replaygain_track_gain"] = _first(tags.getall("TXXX:REPLAYGAIN_TRACK_GAIN"))
            out["replaygain_track_peak"] = _first(tags.getall("TXXX:REPLAYGAIN_TRACK_PEAK"))
            out["replaygain_album_gain"] = _first(tags.getall("TXXX:REPLAYGAIN_ALBUM_GAIN"))
            out["replaygain_album_peak"] = _first(tags.getall("TXXX:REPLAYGAIN_ALBUM_PEAK"))
        elif kind in ("MP4Tags", "MP4Info"):
            def g(k):
                v = tags.get(k)
                if isinstance(v, list) and v:
                    v = v[0]
                if isinstance(v, tuple):  # trkn m.fl.
                    return v
                return _s(v)
            out["title"] = g("\xa9nam")
            out["artist"] = g("\xa9ART")
            out["album"] = g("\xa9alb")
            out["year"] = g("\xa9day")
            trkn = tags.get("trkn")
            out["track"] = f"{trkn[0][0]}" if trkn else ""
            out["genre"] = g("\xa9gen")
            out["series"] = g("----:com.apple.iTunes:SERIES") or g("----:com.apple.iTunes:SERIESNAME")
            out["series_number"] = (g("----:com.apple.iTunes:SERIES_PART")
                                    or g("----:com.apple.iTunes:SERIES-PART")
                                    or g("----:com.apple.iTunes:PART")
                                    or g("----:com.apple.iTunes:EPISODE_ID")
                                    or g("----:com.apple.iTunes:MVIN"))
            out["subtitle"] = g("----:com.apple.iTunes:SUBTITLE")
            out["narrator"] = g("\xa9wrt")
            out["publisher"] = g("\xa9pub")
            out["description"] = g("\xa9des")
            out["language"] = g("----:com.apple.iTunes:LANGUAGE")
            out["asin"] = g("----:com.apple.iTunes:ASIN")
            out["isbn"] = g("----:com.apple.iTunes:ISBN")
            out["replaygain_track_gain"] = g("----:com.apple.iTunes:REPLAYGAIN_TRACK_GAIN")
            out["replaygain_track_peak"] = g("----:com.apple.iTunes:REPLAYGAIN_TRACK_PEAK")
            out["replaygain_album_gain"] = g("----:com.apple.iTunes:REPLAYGAIN_ALBUM_GAIN")
            out["replaygain_album_peak"] = g("----:com.apple.iTunes:REPLAYGAIN_ALBUM_PEAK")
        elif kind in ("VCommentDict", "VComment"):
            def gv(k):
                v = tags.get(k)
                return v[0] if v else ""
            out["title"] = gv("TITLE")
            out["artist"] = gv("ARTIST")
            out["album"] = gv("ALBUM")
            out["track"] = gv("TRACKNUMBER")
            out["year"] = gv("DATE")
            out["genre"] = gv("GENRE")
            out["series"] = gv("SERIES")
            out["series_number"] = (gv("SERIES_PART") or gv("SERIES-PART")
                                   or gv("PART") or gv("EPISODE_ID") or gv("MVIN"))
            out["subtitle"] = gv("SUBTITLE")
            out["narrator"] = gv("COMPOSER")
            out["publisher"] = gv("PUBLISHER")
            out["description"] = gv("DESCRIPTION")
            out["language"] = gv("LANGUAGE")
            out["asin"] = gv("ASIN")
            out["isbn"] = gv("ISBN")
            out["replaygain_track_gain"] = gv("REPLAYGAIN_TRACK_GAIN")
            out["replaygain_track_peak"] = gv("REPLAYGAIN_TRACK_PEAK")
            out["replaygain_album_gain"] = gv("REPLAYGAIN_ALBUM_GAIN")
            out["replaygain_album_peak"] = gv("REPLAYGAIN_ALBUM_PEAK")
    except Exception:
        return out
    return {k: (v or "").strip() for k, v in out.items() if v}


def _first(frames: list) -> str:
    for fr in frames or []:
        try:
            return str(fr.text[0]).strip()
        except Exception:
            try:
                return str(fr).strip()
            except Exception:
                continue
    return ""


def scan(root: str, extensions: Iterable[str] | None = None, recursive: bool = True) -> list[AudioFile]:
    """Hitta alla ljudfiler under root och läs deras taggar."""
    exts = {e.lower(): AUDIO_EXT[e.lower()] for e in (extensions or AUDIO_EXT) if e.lower() in AUDIO_EXT}
    found: list[AudioFile] = []
    if os.path.isfile(root):
        files = [root]
    else:
        files = []
        if recursive:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
                for fn in sorted(filenames):
                    files.append(os.path.join(dirpath, fn))
        else:
            files = [os.path.join(root, fn) for fn in sorted(os.listdir(root))]
    for path in files:
        ext = os.path.splitext(path)[1].lower()
        if ext not in exts:
            continue
        af = AudioFile(path=path, format=exts[ext])
        try:
            af.size_mb = round(os.path.getsize(path) / (1024 * 1024), 1)
        except OSError:
            af.size_mb = 0.0
        af.disc = detect_disc(path)
        tags = read_tags(path)
        af.title = tags.get("title", "")
        af.artist = tags.get("artist", "")
        af.album = tags.get("album", "")
        af.track = tags.get("track", "")
        af.year = tags.get("year", "")[:4]
        found.append(af)
    return found


def group_files(files: list[AudioFile]) -> list[list[AudioFile]]:
    """Gruppera filer som hör till samma ljudbok/album.

    Regler:
      * filer med samma ALBUM-tagg hamnar ihop (Disc/CD-rensat så CD1/CD2 hör ihop)
      * annars: samma mapp (Disc-rensad) + samma normaliserade titel-prefix
      * en ensam fil blir sin egen grupp
      * filer i Disc-mappar eller med Track-junk slås alltid ihop (inte per spår)
    """
    # TEXT_DISC_RE är bred: " (Disc 12)" / " - CD2 " etc — biblioteks DISC_RE är smal
    try:
        from .text import DISC_RE as TEXT_DISC_RE, TRACK_JUNK_RE
    except Exception:
        TEXT_DISC_RE = DISC_RE
        TRACK_JUNK_RE = re.compile(r"^(?:track|spår|disc|cd|del|part|chapter|kapitel)\s*\d{0,2}$", re.I)

    by_album: dict[str, list[AudioFile]] = {}
    rest: list[AudioFile] = []
    for f in files:
        if f.album and not looks_like_junk_title(f.album):
            # samma album (+ artist) hör ihop även över Disc1/Disc2 — rensa disc ur albumnyckel
            clean_album = TEXT_DISC_RE.sub(" ", f.album).strip()
            clean_album = DISC_RE.sub(" ", clean_album).strip()
            clean_album = re.sub(r"\(\s*\)", "", clean_album).strip()
            clean_album = re.sub(r"\s{2,}", " ", clean_album).strip() or f.album
            by_album.setdefault((norm(clean_album), norm(f.artist)), []).append(f)
        else:
            rest.append(f)

    groups: list[list[AudioFile]] = list(by_album.values())
    by_folder: dict[str, list[AudioFile]] = {}
    for f in rest:
        raw = f.path or ""
        # Robust dirname för både Windows (\\) och POSIX (/) — os.path på Linux förstår inte \\
        import ntpath as _nt
        d = _nt.dirname(raw) if "\\" in raw else os.path.dirname(raw)
        # Normalisera disc ur mappnyckel (båda regexen)
        key = TEXT_DISC_RE.sub(" ", d).strip()
        key = DISC_RE.sub(" ", key).strip()
        key = re.sub(r"\(\s*\)", "", key).strip()
        key = re.sub(r"\s{2,}", " ", key).strip()
        by_folder.setdefault(key or d, []).append(f)

    for folder, fs in by_folder.items():
        if len(fs) == 1:
            groups.append(fs)
            continue
        # Om någon fil i denna mapp är från en Disc/CD/skiva-struktur -> slå ihop allt till EN bok
        is_disc_book = False
        try:
            for _f in fs:
                if DISC_RE.search(_f.path) or TEXT_DISC_RE.search(_f.path):
                    is_disc_book = True
                    break
            # även om mappen själv innehöll disc innan rensning är det disc-bok
            if not is_disc_book and (DISC_RE.search(folder) or TEXT_DISC_RE.search(folder)):
                is_disc_book = True
        except Exception:
            pass
        if is_disc_book:
            groups.append(fs)
            continue

        # Annars: splitta på titel-prefix, men Track-junk ska INTE splittras per spår
        sub: dict[str, list[AudioFile]] = {}
        junk: list[AudioFile] = []
        for f in fs:
            import ntpath as _nt2
            raw_base = _nt2.basename(f.path) if "\\" in f.path else os.path.basename(f.path)
            base = os.path.splitext(raw_base)[0]
            base = SPLIT_PART_RE.sub(" ", base)   # "… (1 of 2)" == "… (2 of 2)"
            stripped = base.strip()
            # Track01 / Disc 2 etc är rip-skrot — hör till samma bok, inte varsin bok
            if TRACK_JUNK_RE.match(stripped) or looks_like_junk_title(stripped):
                junk.append(f)
                continue
            k = title_key(re.sub(r"\b\d{1,3}\s*$", "", base))
            if not k or k in ("track", "spar", "disc", "cd"):
                junk.append(f)
            else:
                sub.setdefault(k, []).append(f)
        if junk:
            # alla junk-spår i samma mapp är samma bok (t.ex. Track01..Track12 från flera discs som redan slagits ihop ovan)
            # om is_disc_book redan hanterats är junk här från icke-disc men ändå track-namnad mapp
            if len(junk) >= 1:
                # om sub är tom -> bara junk finns -> en grupp
                # om både junk och riktiga titlar finns -> junk hör oftast till samma bok som subtiteln, men behåll separat för säkerhet
                # här: slå ihop junk till en grupp
                groups.append(junk)
        groups.extend(sub.values())

    for g in groups:
        g.sort(key=lambda f: _track_sort(f))
    groups.sort(key=lambda g: g[0].path.lower())
    return groups


# "Salem's Lot (1 of 2)" / "(2 av 2)" / "3 of 5" -> delar av samma bok
SPLIT_PART_RE = re.compile(r"\(?\s*\d{1,2}\s+(?:av|of)\s+\d{1,2}\s*\)?", re.I)


def _track_sort(f: AudioFile) -> tuple:
    disc = getattr(f, "disc", 0) or 0
    m = re.search(r"(\d+)", f.track or "")
    if m:
        return (disc, 0, int(m.group(1)), f.path)
    part = extract_part(os.path.splitext(os.path.basename(f.path))[0])
    if part:
        try:
            return (disc, 0, float(part), f.path)
        except ValueError:
            pass
    m = re.search(r"(\d+)", os.path.splitext(os.path.basename(f.path))[0])
    if m:
        return (disc, 0, int(m.group(1)), f.path)
    return (disc, 1, 0, f.path)


def label_group(group: list[AudioFile]) -> str:
    """Visningsnamn för en grupp (för GUI:n)."""
    f = group[0]
    name = f.album or f.title or os.path.splitext(os.path.basename(f.path))[0]
    if len(group) > 1:
        return f"{name}  ({len(group)} filer)"
    return name
