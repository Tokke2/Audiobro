"""Skriv taggar till ljudfiler (mp3/m4b/flac/ogg) via mutagen."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

from .models import Proposal

# ID3-ramar
ID3_FRAMES = {
    "title": "TIT2",
    "artist": "TPE1",
    "album": "TALB",
    "year": "TDRC",
    "genre": "TCON",
}
# Audiobookshelf läser (server/scanner/AudioFileScanner.js + prober.js):
#   narrator=COMPOSER, description=DESCRIPTION/COMMENT, publisher, subtitle,
#   genres, isbn, asin, language, series + series-part.
# Vi skriver exakt de ramar/atomer som ABS ffprobe:ar fram.
ID3_EXTRA = {          # standard-ID3-ramar
    "subtitle": "TIT3",
    "narrator": "TCOM",   # ABS: composer = uppläsare
    "publisher": "TPUB",
    "description": "COMM",
    "language": "TLAN",
    "genre": "TCON",
}
ID3_TXXX = {           # egna TXXX-ramar (SERIES_PART även med bindestreck för ABS)
    "series": "SERIES",
    "series_number": "SERIES_PART",
    "asin": "ASIN",
    "isbn": "ISBN",
    # ReplayGain — 1) ReplayGain / volymnormalisering (krav 25:1) — skrivs när ffmpeg finns
    "replaygain_track_gain": "REPLAYGAIN_TRACK_GAIN",
    "replaygain_track_peak": "REPLAYGAIN_TRACK_PEAK",
    "replaygain_album_gain": "REPLAYGAIN_ALBUM_GAIN",
    "replaygain_album_peak": "REPLAYGAIN_ALBUM_PEAK",
}
MP4_ATOMS = {
    "title": "\xa9nam",
    "artist": "\xa9ART",
    "album": "\xa9alb",
    "year": "\xa9day",
    "genre": "\xa9gen",
    "narrator": "\xa9wrt",   # composer = uppläsare
    "publisher": "\xa9pub",
    "description": "\xa9des",
}
MP4_FREEFORM = {
    "series": "----:com.apple.iTunes:SERIES",
    "series_number": "----:com.apple.iTunes:SERIES_PART",
    "subtitle": "----:com.apple.iTunes:SUBTITLE",
    "language": "----:com.apple.iTunes:LANGUAGE",
    "asin": "----:com.apple.iTunes:ASIN",
    "isbn": "----:com.apple.iTunes:ISBN",
    # ReplayGain — M4B/MP4 freeform (iTunes)
    "replaygain_track_gain": "----:com.apple.iTunes:REPLAYGAIN_TRACK_GAIN",
    "replaygain_track_peak": "----:com.apple.iTunes:REPLAYGAIN_TRACK_PEAK",
    "replaygain_album_gain": "----:com.apple.iTunes:REPLAYGAIN_ALBUM_GAIN",
    "replaygain_album_peak": "----:com.apple.iTunes:REPLAYGAIN_ALBUM_PEAK",
}
VORBIS_KEYS = {
    "title": "TITLE",
    "artist": "ARTIST",
    "album": "ALBUM",
    "year": "DATE",
    "genre": "GENRE",
    "series": "SERIES",
    "series_number": "SERIES_PART",
    "subtitle": "SUBTITLE",
    "narrator": "COMPOSER",
    "publisher": "PUBLISHER",
    "description": "DESCRIPTION",
    "language": "LANGUAGE",
    "asin": "ASIN",
    "isbn": "ISBN",
    # ReplayGain — FLAC/OGG/Opus (Vorbis comment)
    "replaygain_track_gain": "REPLAYGAIN_TRACK_GAIN",
    "replaygain_track_peak": "REPLAYGAIN_TRACK_PEAK",
    "replaygain_album_gain": "REPLAYGAIN_ALBUM_GAIN",
    "replaygain_album_peak": "REPLAYGAIN_ALBUM_PEAK",
}


@dataclass
class WriteResult:
    path: str
    ok: bool
    written: list[str]
    error: str = ""


def mutagen_available() -> bool:
    try:
        import mutagen  # noqa: F401
        return True
    except ImportError:
        return False


def proposal_to_fields(p: Proposal, write_series: bool = True) -> dict:
    """Översätt ett förslag till fält som ska skrivas."""
    fields = {
        "title": p.new_title,
        "artist": p.new_artist,
        "album": p.new_album,
        "year": p.new_year,
        "track": p.new_track,
    }
    if write_series:
        fields["series"] = p.new_series
        fields["series_number"] = p.new_series_number
    for extra in ("new_subtitle", "new_description", "new_narrator",
                  "new_publisher", "new_genre", "new_isbn", "new_asin",
                  "new_language"):
        val = (getattr(p, extra, "") or "").strip()
        if val:
            fields[extra[len("new_"):]] = val
    # ReplayGain — skrivs om engine räknat ut värdet (se audioinfo.replaygain)
    for rg in ("replaygain_track_gain", "replaygain_track_peak",
               "replaygain_album_gain", "replaygain_album_peak"):
        # stöd både new_*-prefix (från Proposal) och direkt fält
        val = (getattr(p, f"new_{rg}", None) or getattr(p, rg, None) or "").strip() if isinstance(getattr(p, f"new_{rg}", None) or getattr(p, rg, None), str) else (getattr(p, f"new_{rg}", None) or getattr(p, rg, None))
        if isinstance(val, str):
            val = val.strip()
            if val:
                fields[rg] = val
        elif val is not None:
            try:
                s_val = str(val).strip()
                if s_val:
                    fields[rg] = s_val
            except Exception:
                pass
    return {k: v for k, v in fields.items() if v}


def write_file(path: str, fields: dict, backup: bool = True) -> WriteResult:
    """Skriv fälten till filen. Returnerar vilka fält som sattes."""
    if not fields:
        return WriteResult(path, True, [])
    try:
        from mutagen import File as MFile
        from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TALB, TDRC, TCON, TRCK, TXXX
        from mutagen.mp4 import MP4, MP4FreeForm
        from mutagen.flac import FLAC
        from mutagen.oggvorbis import OggVorbis
    except ImportError as exc:
        return WriteResult(path, False, [], f"mutagen saknas: {exc}. Kör: pip install mutagen")
    if not os.path.exists(path):
        return WriteResult(path, False, [], "filen finns inte")

    if backup:
        try:
            if not os.path.exists(path + ".agsbak"):
                shutil.copy2(path, path + ".agsbak")
        except OSError:
            pass

    ext = os.path.splitext(path)[1].lower()
    written: list[str] = []
    try:
        if ext == ".mp3":
            from mutagen.id3 import TIT3, TCOM, TPUB, COMM, TLAN

            try:
                tags = ID3(path)
            except ID3NoHeaderError:
                tags = ID3()
            frame_map = {"TIT2": TIT2, "TPE1": TPE1, "TALB": TALB, "TDRC": TDRC,
                         "TCON": TCON, "TRCK": TRCK, "TIT3": TIT3, "TCOM": TCOM,
                         "TPUB": TPUB, "TLAN": TLAN, "COMM": COMM}
            for key, frame_name in {**ID3_FRAMES, **ID3_EXTRA}.items():
                if key in fields:
                    cls = frame_map[frame_name]
                    if frame_name == "COMM":
                        tags.setall("COMM", [COMM(encoding=3, lang="eng",
                                                  desc="", text=[fields[key]])])
                    else:
                        tags.setall(frame_name, [cls(encoding=3, text=[fields[key]])])
                    written.append(key)
            if "track" in fields:
                tags.setall("TRCK", [TRCK(encoding=3, text=[fields["track"]])])
                written.append("track")
            for key, desc in ID3_TXXX.items():
                if key in fields:
                    tags.setall(f"TXXX:{desc}", [TXXX(encoding=3, desc=desc,
                                                      text=[fields[key]])])
                    written.append(key)
            # ABS ffprobe:ar TXXX-beskrivningen "series-part" (bindestreck)
            # 50000000% ABS: skriv även alla kända del-nycklar så att ABS alltid hittar delen
            # utan krångel (ABS kollar 'series-part','part','episode_id','mvin' m.fl. beroende på version).
            if "series_number" in fields:
                tags.setall("TXXX:SERIES-PART",
                            [TXXX(encoding=3, desc="SERIES-PART",
                                  text=[fields["series_number"]])])
                for _alt in ("PART", "EPISODE_ID", "MVIN"):
                    try:
                        tags.setall(f"TXXX:{_alt}",
                                    [TXXX(encoding=3, desc=_alt, text=[fields["series_number"]])])
                    except Exception:
                        pass
            tags.save(path, v2_version=3)
        elif ext in (".m4b", ".m4a", ".aac", ".mp4"):
            audio = MP4(path)
            tags = audio.tags
            if tags is None:
                audio.add_tags()
                tags = audio.tags
            for key, atom in MP4_ATOMS.items():
                if key in fields:
                    tags[atom] = [fields[key]]
                    written.append(key)
            if "track" in fields:
                num, _, total = fields["track"].partition("/")
                try:
                    tags["trkn"] = [(int(num or 0), int(total or 0))]
                    written.append("track")
                except ValueError:
                    pass
            for key, atom in MP4_FREEFORM.items():
                if key in fields:
                    tags[atom] = [MP4FreeForm(fields[key].encode("utf-8"))]  # UTF8 är standardformatet
                    written.append(key)
            # 50000000% ABS: samma del på alla kända M4B-nycklar
            if "series_number" in fields:  # ABS-variant med bindestreck
                tags["----:com.apple.iTunes:SERIES-PART"] = [
                    MP4FreeForm(fields["series_number"].encode("utf-8"))]
                for _alt in ("----:com.apple.iTunes:PART", "----:com.apple.iTunes:EPISODE_ID",
                             "----:com.apple.iTunes:MVIN"):
                    try:
                        tags[_alt] = [MP4FreeForm(fields["series_number"].encode("utf-8"))]
                    except Exception:
                        pass
            audio.save()
        elif ext in (".flac", ".ogg", ".opus"):
            if ext == ".flac":
                audio = FLAC(path)
            else:
                audio = OggVorbis(path)
            for key, vk in VORBIS_KEYS.items():
                if key in fields:
                    audio[vk] = [fields[key]]
                    written.append(key)
            if "track" in fields:
                audio["TRACKNUMBER"] = [fields["track"].split("/")[0]]
                tot = fields["track"].split("/")
                if len(tot) == 2 and tot[1]:
                    audio["TRACKTOTAL"] = [tot[1]]
                written.append("track")
            # 50000000% ABS: extra serie-del-nycklar för Vorbis (ABS läser olika stavningar)
            if "series_number" in fields:
                for _alt in ("PART", "EPISODE_ID", "MVIN", "SERIES-PART"):
                    try:
                        audio[_alt] = [fields["series_number"]]
                    except Exception:
                        pass
            audio.save()
        else:
            return WriteResult(path, False, [], f"formatet {ext} stöds inte ännu")
    except Exception as exc:  # noqa: BLE001
        return WriteResult(path, False, written, f"{type(exc).__name__}: {exc}")
    return WriteResult(path, True, written)


def apply_proposal(p: Proposal, backup: bool = True, write_series: bool = True) -> list[WriteResult]:
    """Skriv ett förslag till alla filer i förslaget (en fil eller grupp)."""
    fields = proposal_to_fields(p, write_series=write_series)
    results = []
    paths = getattr(p, "paths", None) or [p.audio.path]
    for path in paths:
        res = write_file(path, fields, backup=backup)
        results.append(res)
        p.applied = res.ok
    return results
