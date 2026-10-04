"""Historik över färdigbehandlade böcker — hoppar över dubbelarbete.

Uppdaterad 2026-10-04: sparar även ljudkvalitet (bitrate, codec, format, storlek)
så att samma bok med bättre ljud kan erbjuda ersättning.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Optional

from .text import norm

def _default_history_path() -> str:
    # Audiobro primary, legacy fallback
    new = os.path.join(os.path.expanduser("~"), ".audiobro", "history.json")
    legacy = os.path.join(os.path.expanduser("~"), ".audiobook-goodreads", "history.json")
    if os.path.isfile(new):
        return new
    if os.path.isfile(legacy):
        # migrate
        try:
            import shutil
            os.makedirs(os.path.dirname(new), exist_ok=True)
            if not os.path.isfile(new):
                shutil.copy2(legacy, new)
        except Exception:
            pass
        return new
    return new

DEFAULT_PATH = _default_history_path()


def identity_key(title: str, author: str, series: str = "", number: str = "",
                 book_id: str = "") -> str:
    """Stabil nyckel för 'samma bok' oavsett utgåva och skiftläge."""
    if book_id:
        return f"gr:{book_id}"
    raw = "|".join(norm(x) for x in (title, author, series, number))
    return "k:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# Format-ranking för ljudkvalitet (samma som i engine)
_FORMAT_RANK = {"flac": 5, "wav": 4, "alac": 4, "m4b": 3, "m4a": 3, "aac": 3, "opus": 3, "mp3": 2, "ogg": 2, "wma": 1}

def _codec_rank(codec: str, fmt: str) -> int:
    c = (codec or "").lower()
    f = (fmt or "").lower()
    if "flac" in c or f == "flac":
        return 5
    if "wav" in c or "pcm" in c or f == "wav":
        return 4
    if "alac" in c:
        return 4
    if "opus" in c or f == "opus":
        return 3
    if "aac" in c or f in ("m4b", "m4a", "aac"):
        return 3
    if "mp3" in c or f == "mp3" or "mpeg" in c:
        return 2
    return _FORMAT_RANK.get(f, 1)

def _quality_tuple(info: dict) -> tuple:
    """Jämförbar tuple: högre = bättre ljud. Använder bitrate → sample_rate → codec → size."""
    try:
        br = int(info.get("bitrate_kbps") or 0)
    except Exception:
        br = 0
    try:
        sr = int(info.get("sample_rate") or 0)
    except Exception:
        sr = 0
    fmt = (info.get("format") or "").lower()
    codec = (info.get("codec") or "")
    cr = _codec_rank(codec, fmt)
    try:
        size = float(info.get("size_mb") or 0)
    except Exception:
        size = 0.0
    try:
        n_files = int(info.get("n_files") or 1)
    except Exception:
        n_files = 1
    # Fler filer är inte bättre — men om bitrate lika, föredra färre filer (en m4b vs 20 mp3)
    return (br, sr, cr, round(size, 1), -n_files)

def summarize_audio_qualities(qualities) -> dict:
    """Sammanfatta en lista av AudioQuality (från audioinfo.probe) till ett dict för historiken."""
    if not qualities:
        return {}
    # qualities kan vara lista av AudioQuality eller redan dicts
    # Om första element har attribut bitrate_kbps är det AudioQuality
    try:
        # Försök hantera AudioQuality-objekt
        total_br = 0
        total_sr = 0
        total_size = 0.0
        total_dur = 0.0
        count = 0
        fmts = []
        codecs = []
        channels = 0
        for q in qualities:
            if isinstance(q, dict):
                total_br += int(q.get("bitrate_kbps") or 0)
                total_sr += int(q.get("sample_rate") or 0)
                total_size += float(q.get("size_mb") or 0)
                total_dur += float(q.get("duration_s") or 0)
                fmts.append((q.get("format") or "").lower())
                codecs.append((q.get("codec") or ""))
                ch = int(q.get("channels") or 0)
                if ch > channels:
                    channels = ch
                count += 1
            else:
                # AudioQuality dataclass
                total_br += int(getattr(q, "bitrate_kbps", 0) or 0)
                total_sr += int(getattr(q, "sample_rate", 0) or 0)
                total_size += float(getattr(q, "size_mb", 0) or 0)
                total_dur += float(getattr(q, "duration_s", 0) or 0)
                fmts.append((getattr(q, "format", "") or "").lower())
                codecs.append((getattr(q, "codec", "") or ""))
                ch = int(getattr(q, "channels", 0) or 0)
                if ch > channels:
                    channels = ch
                count += 1
        if count == 0:
            return {}
        # Välj vanligaste format/codec, annars första med värde
        from collections import Counter
        fmt = Counter([f for f in fmts if f]).most_common(1)
        fmt = fmt[0][0] if fmt else (fmts[0] if fmts else "")
        codec = Counter([c for c in codecs if c]).most_common(1)
        codec = codec[0][0] if codec else (codecs[0] if codecs else "")
        # Medel-bitrate / max sample_rate
        avg_br = int(round(total_br / count)) if count else 0
        max_sr = max([int(getattr(q, "sample_rate", 0) or 0) if not isinstance(q, dict) else int(q.get("sample_rate") or 0) for q in qualities] or [0])
        # Om avg_br är 0 men storlek/duration finns, beräkna
        if avg_br == 0 and total_size and total_dur > 10:
            try:
                avg_br = int((total_size * 1024 * 1024 * 8) / (total_dur * 1000))
            except Exception:
                pass
        verdict = "okänd"
        if avg_br >= 128:
            verdict = "hög (≥128 kbit/s)"
        elif avg_br >= 64:
            verdict = "bra (64–127 kbit/s)"
        elif avg_br > 0:
            verdict = "låg (<64 kbit/s)"
        return {
            "format": fmt,
            "codec": codec,
            "bitrate_kbps": avg_br,
            "sample_rate": max_sr,
            "channels": channels,
            "size_mb": round(total_size, 1),
            "duration_s": round(total_dur, 1),
            "n_files": count,
            "verdict": verdict,
        }
    except Exception:
        return {}

def is_better_audio(new_info: dict, old_info: dict) -> bool:
    """True om nya ljudet är bättre än det sparade enligt ranking."""
    if not old_info or not isinstance(old_info, dict):
        # Gammal saknar info → kan inte jämföra, anta ej bättre (fråga ej om ersättning)
        return False
    if not new_info or not isinstance(new_info, dict):
        return False
    # Om båda har 0 bitrate (okänd) → ej bättre
    if (new_info.get("bitrate_kbps") or 0) == 0 and (old_info.get("bitrate_kbps") or 0) == 0:
        return False
    return _quality_tuple(new_info) > _quality_tuple(old_info)

def audio_description(info: dict) -> str:
    """Kort läsbar beskrivning: '128 kbps M4B (256 MB, 44.1 kHz, stereo)'"""
    if not info or not isinstance(info, dict):
        return "okänd kvalitet"
    parts = []
    br = info.get("bitrate_kbps")
    if br:
        parts.append(f"{br} kbps")
    fmt = (info.get("format") or "").upper()
    codec = info.get("codec") or ""
    if fmt:
        if codec and codec.upper() != fmt and codec.lower() not in fmt.lower():
            parts.append(f"{fmt} ({codec})")
        else:
            parts.append(fmt)
    elif codec:
        parts.append(codec)
    size = info.get("size_mb")
    if size:
        parts.append(f"{size} MB")
    sr = info.get("sample_rate")
    if sr:
        try:
            khz = int(sr) // 1000
            if khz:
                parts.append(f"{khz} kHz")
        except Exception:
            pass
    ch = info.get("channels")
    if ch:
        try:
            ch = int(ch)
            if ch == 1:
                parts.append("mono")
            elif ch == 2:
                parts.append("stereo")
            elif ch > 2:
                parts.append(f"{ch} kanaler")
        except Exception:
            pass
    verdict = info.get("verdict")
    if verdict and verdict != "okänd":
        parts.append(verdict)
    return " • ".join(parts) if parts else "okänd kvalitet"


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
            source: str = "", output: str = "", files: Optional[list[str]] = None,
            audio: Optional[dict] = None) -> None:
        # Rensa gammal post för samma nyckel
        self._entries = [e for e in self._entries if e.get("key") != key]
        entry = {
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
        }
        # Spara ljudkvalitet om tillgänglig
        if audio and isinstance(audio, dict) and audio:
            # Rensa tomma värden men behåll strukturen
            clean = {k: v for k, v in audio.items() if v not in (None, "", 0) or k in ("bitrate_kbps", "size_mb")}
            # Se till att viktiga nycklar alltid finns
            for k in ("format", "codec", "bitrate_kbps", "sample_rate", "channels", "size_mb", "duration_s", "n_files", "verdict"):
                if k not in clean:
                    clean[k] = audio.get(k, "" if k in ("format","codec","verdict") else 0)
            entry["audio"] = clean
        elif files:
            # Försök auto-proba om filer finns (best effort, misslyckas tyst)
            try:
                from . import audioinfo
                qualities = []
                for fp in files[:6]:  # max 6 filer för snabbhet
                    if fp and os.path.exists(fp):
                        try:
                            qualities.append(audioinfo.probe(fp))
                        except Exception:
                            continue
                if qualities:
                    entry["audio"] = summarize_audio_qualities(qualities)
            except Exception:
                pass
        self._entries.append(entry)
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
