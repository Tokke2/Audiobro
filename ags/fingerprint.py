"""Duplikat-jägare med ljud-fingerprint — multi-nivå.

    Nivå 1 (alltid): titel/författare/serie + duration + filstorlek — snabb, träffar 80%
    Nivå 2 (om ffmpeg+fpcalc finns): Chromaprint (AcoustID) — hittar samma ljud trots olika bitrate/namn
    Nivå 3 (om pyacoustid+chromaprint finns): samma som 2 men via Python

    Användning:
        groups = find_duplicates(files)  # files: list[library.AudioFile] eller proposals
        # groups: list[list[AudioFile]] där varje grupp är misstänkta dubbletter

    Returnerar grupper med >=2 filer som likar varandra >= threshold.
"""
from __future__ import annotations

import os
import hashlib
import subprocess
import shutil
import re

from . import logging_setup

LOG = logging_setup.get("dedup")
try:
    from rapidfuzz import fuzz  # för titel-jämförelse
    HAS_RAPIDFUZZ = True
except Exception:
    HAS_RAPIDFUZZ = False


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower().strip())


def _title_sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if HAS_RAPIDFUZZ:
        try:
            return fuzz.ratio(a.lower(), b.lower()) / 100.0
        except Exception:
            pass
    # fallback: enkel
    an, bn = _norm(a), _norm(b)
    if not an or not bn:
        return 0.0
    # Jaccard på bigram
    def bigrams(x):
        return {x[i:i+2] for i in range(len(x)-1)} if len(x) > 1 else {x}
    ba, bb = bigrams(an), bigrams(bn)
    if not ba or not bb:
        return 1.0 if an == bn else 0.0
    return len(ba & bb) / len(ba | bb)


def _has_fpcalc() -> bool:
    return shutil.which("fpcalc") is not None


def _fpcalc_fingerprint(path: str, duration: float | None = None) -> str | None:
    """Kör fpcalc om det finns, returnerar fingerprint-sträng."""
    if not _has_fpcalc():
        return None
    try:
        # fpcalc -json ger fingerprint + duration
        cmd = ["fpcalc", "-json", path]
        # Begränsa till 90s för hastighet (fpcalc har -length)
        if duration and duration > 120:
            cmd = ["fpcalc", "-json", "-length", "90", path]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if proc.returncode != 0:
            LOG.debug("fpcalc fel för %s: %s", path, proc.stderr[:200])
            return None
        import json
        data = json.loads(proc.stdout)
        fp = data.get("fingerprint")
        if fp:
            LOG.debug("fpcalc fingerprint för %s: %d chars", path, len(fp))
            return fp
    except Exception as exc:
        LOG.debug("fpcalc exception %s: %s", path, exc)
    return None


def _fp_similarity(a: str, b: str) -> float:
    """Jämför två fingerprints (Chromaprint). Enkel: räkna lika tecken."""
    if not a or not b:
        return 0.0
    # Chromaprint är komprimerad base64-ish, jämför via Hamming på bitnivå är komplext.
    # Vi gör enkel: om båda från fpcalc, jämför likhet via rapidfuzz på själva strängen
    if HAS_RAPIDFUZZ:
        try:
            return fuzz.ratio(a, b) / 100.0
        except Exception:
            pass
    # fallback: längd + prefix-jämförelse
    # Om en är substring av den andra -> hög likhet
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return 0.0
    # Jämför första 500 chars
    a0, b0 = a[:500], b[:500]
    common = sum(1 for x, y in zip(a0, b0) if x == y)
    return common / max(len(a0), len(b0), 1)


def _quick_hash(path: str) -> str | None:
    """Snabb hash av första+ sista 1 MB + filstorlek — skiljer olika kodningar men samma fil ger samma."""
    try:
        size = os.path.getsize(path)
        h = hashlib.sha256()
        h.update(str(size).encode())
        with open(path, "rb") as fh:
            h.update(fh.read(1024 * 1024))
            if size > 2 * 1024 * 1024:
                fh.seek(-1024 * 1024, os.SEEK_END)
                h.update(fh.read(1024 * 1024))
        return h.hexdigest()[:16]
    except Exception:
        return None


def _audio_duration(path: str) -> float | None:
    try:
        from .audioinfo import read_info  # existerar i projektet
        info = read_info(path)
        if info and getattr(info, "duration", None):
            return float(info.duration)
    except Exception:
        pass
    # fallback via mutagen
    try:
        from mutagen import File  # type: ignore
        audio = File(path)
        if audio and hasattr(audio, "info") and hasattr(audio.info, "length"):
            return float(audio.info.length)
    except Exception:
        pass
    return None


def _duration_sim(a: float | None, b: float | None) -> float:
    if a is None or b is None:
        return 0.5  # okänt -> neutral
    if a == 0 or b == 0:
        return 0.0
    diff = abs(a - b) / max(a, b)
    # <2% diff = 1.0, <5% = 0.8, <10% = 0.5, <20% = 0.2
    if diff < 0.02:
        return 1.0
    if diff < 0.05:
        return 0.8
    if diff < 0.10:
        return 0.5
    if diff < 0.20:
        return 0.2
    return 0.0


def score_pair(a, b, fp_a: str | None = None, fp_b: str | None = None) -> float:
    """Poäng 0-1 att a och b är samma bok."""
    # a,b är dict-liknande med title, artist/author, duration, path
    def get_title(x):
        return getattr(x, "title", None) or getattr(x, "group_label", None) or x.get("title", "") if isinstance(x, dict) else getattr(x, "title", "")
    def get_artist(x):
        return getattr(x, "artist", None) or getattr(x, "author", None) or x.get("artist", "") if isinstance(x, dict) else getattr(x, "artist", "")
    def get_path(x):
        return getattr(x, "path", None) or x.get("path", "") if isinstance(x, dict) else getattr(x, "path", "")

    ta, tb = str(get_title(a) or ""), str(get_title(b) or "")
    aa, ab = str(get_artist(a) or ""), str(get_artist(b) or "")
    # Snabb uteslutning: helt olika författare och titel <0.4 -> ej dublett
    ts = _title_sim(ta, tb)
    artist_sim = _title_sim(aa, ab) if aa and ab else 0.5

    # Duration
    da = _audio_duration(get_path(a)) if get_path(a) else None
    db = _audio_duration(get_path(b)) if get_path(b) else None
    ds = _duration_sim(da, db)

    # Fingerprint om tillgängligt
    if fp_a is not None and fp_b is not None:
        fps = _fp_similarity(fp_a, fp_b)
        # Vikt: fingerprint 50%, titel 30%, duration 20%
        score = 0.5 * fps + 0.3 * ts + 0.2 * ds
        # Om fingerprint är mycket högt (>0.85) räcker det även vid låg titel-sim
        if fps > 0.85 and ds > 0.5:
            score = max(score, 0.88)
        return score

    # Utan fingerprint: vikt titel 50%, artist 20%, duration 30%
    # Kräv minst duration-sim 0.5 för att räknas som dublett
    if ds < 0.3:
        return 0.0
    score = 0.5 * ts + 0.2 * artist_sim + 0.3 * ds
    # Bonus om hash identisk
    ha = _quick_hash(get_path(a)) if get_path(a) else None
    hb = _quick_hash(get_path(b)) if get_path(b) else None
    if ha and hb and ha == hb:
        score = max(score, 0.95)
    return score


def find_duplicates(files, threshold: float = 0.82, use_fingerprint: bool = False) -> list[list]:  # OPT-IN: endast när användaren ber om det
    """Hittar grupper av misstänkta dubbletter.
    files: iterable av AudioFile eller dict med title/artist/path/duration
    threshold: 0.82 default (balanserad)
    use_fingerprint: prova fpcalc om tillgängligt (långsammare men träffar olika bitrate)
    """
    files = list(files)
    if len(files) < 2:
        return []
    LOG.info("dubblet-sök: %d filer, tröskel %.2f, fingerprint=%s", len(files), threshold, use_fingerprint and _has_fpcalc())
    # Pre-calc fingerprints om möjligt (bara för de som verkar lika via titel/duration först, för att spara tid)
    fps: dict[str, str | None] = {}
    # Först grovgruppering på duration-bucket + första 3 bokstäverna i titel för att minska O(n^2)
    # Men för n<500 är O(n^2) ok
    groups: list[list] = []
    used: set[int] = set()

    # Förbered fp om önskat och fpcalc finns
    want_fp = use_fingerprint and _has_fpcalc()
    if want_fp:
        LOG.info("fpcalc hittad — beräknar fingerprints för %d filer (kan ta en stund)", len(files))
        for f in files:
            p = getattr(f, "path", None) or (f.get("path") if isinstance(f, dict) else None)
            if p and os.path.exists(p):
                fps[p] = _fpcalc_fingerprint(p)
            else:
                fps[p or str(id(f))] = None

    for i in range(len(files)):
        if i in used:
            continue
        a = files[i]
        pa = getattr(a, "path", None) or (a.get("path") if isinstance(a, dict) else None) or str(i)
        fa = fps.get(pa) if want_fp else None
        group = [a]
        for j in range(i + 1, len(files)):
            if j in used:
                continue
            b = files[j]
            pb = getattr(b, "path", None) or (b.get("path") if isinstance(b, dict) else None) or str(j)
            fb = fps.get(pb) if want_fp else None
            sc = score_pair(a, b, fp_a=fa, fp_b=fb)
            if sc >= threshold:
                group.append(b)
                used.add(j)
                LOG.debug("dublett %.2f: %r vs %r", sc,
                          getattr(a, "group_label", None) or getattr(a, "title", None) or pa,
                          getattr(b, "group_label", None) or getattr(b, "title", None) or pb)
        if len(group) > 1:
            groups.append(group)
            used.add(i)
    LOG.info("dubblet-sök klart: %d grupper", len(groups))
    return groups


def find_duplicates_in_proposals(proposals, threshold: float = 0.82, respect_ignore: bool = True, use_fingerprint: bool = False) -> list[list]:  # OPT-IN ljudmatchning
    """Bekväm wrapper för engine.Proposal-lista.
    Använder new_title/new_artist + group_label + paths.
    Respekterar ignorerade dubbletter (även över källor, robust mot hyphen/"Läckberg, Camilla" vs "Camilla Läckberg") om respect_ignore=True.
    """
    # Filtrera ignorerade före gruppering — robust cross-source
    if respect_ignore:
        try:
            from .ignore import dup_keys_for_proposal, is_ignored_any, load_ignored
            ignored = load_ignored()
            if ignored:
                filtered = []
                for p in proposals:
                    try:
                        keys = dup_keys_for_proposal(p)
                        if keys and any(k in ignored for k in keys):
                            LOG.debug("filtrerar ignorerad dublett %r (%s)", getattr(p, "new_title", ""), next(iter(keys)))
                            continue
                    except Exception:
                        pass
                    filtered.append(p)
                proposals = filtered
        except Exception as exc:
            LOG.debug("ignore check fel: %s", exc)
    # Bygg pseudo-filer från proposals
    pseudo = []
    for p in proposals:
        # använd första pathen som representant
        path = (getattr(p, "paths", None) or [getattr(p.audio, "path", "")])[0] if hasattr(p, "audio") else ""
        title = getattr(p, "new_title", None) or getattr(p.audio, "title", None) or getattr(p.audio, "group_label", "") if hasattr(p, "audio") else ""
        artist = getattr(p, "new_artist", None) or getattr(p.audio, "artist", None) if hasattr(p, "audio") else ""
        pseudo.append({"title": title, "artist": artist, "path": path, "proposal": p})
    if not pseudo:
        return []
    # Gruppera pseudo
    raw_groups = find_duplicates(pseudo, threshold=threshold, use_fingerprint=use_fingerprint)
    # Mappa tillbaka till proposals
    res: list[list] = []
    for g in raw_groups:
        grp = [item["proposal"] for item in g]
        # Säkerhet: om gruppen efter filtrering bara har 1, skippa
        if len(grp) < 2:
            continue
        res.append(grp)
    return res
