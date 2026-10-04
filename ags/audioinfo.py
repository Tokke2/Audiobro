"""Ljudkvalitetsrapport för .md-faktabladet."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AudioQuality:
    path: str = ""
    format: str = ""
    codec: str = ""
    bitrate_kbps: int = 0
    sample_rate: int = 0
    channels: int = 0
    duration_s: float = 0.0
    size_mb: float = 0.0

    @property
    def duration_text(self) -> str:
        s = int(self.duration_s or 0)
        return f"{s // 3600}h {(s % 3600) // 60:02d}m {s % 60:02d}s"

    @property
    def verdict(self) -> str:
        """Enkel kvalitetsbedömning för ljudböcker."""
        if self.bitrate_kbps >= 128:
            return "hög (≥128 kbit/s)"
        if self.bitrate_kbps >= 64:
            return "bra (64–127 kbit/s)"
        if self.bitrate_kbps > 0:
            return "låg (<64 kbit/s)"
        return "okänd"


def probe(path: str) -> AudioQuality:
    """Läs format/bitrate/längd m.m. med mutagen + ffprobe-fallback (100% säkrare)."""
    q = AudioQuality(path=path)
    try:
        q.size_mb = round(os.path.getsize(path) / (1024 * 1024), 1)
    except OSError:
        q.size_mb = 0.0
    q.format = os.path.splitext(path)[1].lstrip(".").lower()
    # Försök mutagen först
    try:
        from mutagen import File as MFile
    except ImportError:
        MFile = None
    if MFile is not None:
        try:
            f = MFile(path)
            if f is not None and f.info is not None:
                info = f.info
                q.duration_s = round(getattr(info, "length", 0.0) or 0.0, 1)
                q.sample_rate = int(getattr(info, "sample_rate", 0) or 0)
                q.channels = int(getattr(info, "channels", 0) or 0)
                q.bitrate_kbps = int(round((getattr(info, "bitrate", 0) or 0) / 1000))
                kind = type(info).__name__
                codec = {
                    "MPEGInfo": f"MPEG layer {getattr(info, 'version', '')}".strip(),
                    "TrueAudioInfo": "TTA",
                    "MP4Info": "AAC",
                    "FLACInfo": "FLAC",
                    "OggVorbisInfo": "Vorbis",
                    "OggOpusInfo": "Opus",
                    "WaveInfo": "PCM/WAV",
                }.get(kind, kind)
                q.codec = codec
        except Exception:
            pass
    # ffprobe-fallback / komplettering: om bitrate saknas eller är 0, prova ffprobe (mer exakt för m4b/aac)
    # Också om mutagen missade helt
    if q.bitrate_kbps == 0 or q.sample_rate == 0 or q.duration_s == 0:
        try:
            import json, shutil, subprocess
            ffprobe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
            if ffprobe:
                cmd = [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
                if proc.returncode == 0 and proc.stdout:
                    data = json.loads(proc.stdout)
                    # streams[0] är audio
                    streams = data.get("streams", [])
                    fmt = data.get("format", {}) 
                    dur = float(fmt.get("duration", 0) or 0) or float(streams[0].get("duration", 0) if streams else 0)
                    if dur and not q.duration_s:
                        q.duration_s = round(dur,1)
                    if streams:
                        s = streams[0]
                        if not q.sample_rate:
                            q.sample_rate = int(s.get("sample_rate", 0) or 0)
                        if not q.channels:
                            q.channels = int(s.get("channels", 0) or 0)
                        if not q.codec or q.codec in ("MP4Info","MPEGInfo"):
                            q.codec = (s.get("codec_name","") or q.codec).upper()
                        # bitrate: först från stream, annars format
                        br = s.get("bit_rate") or fmt.get("bit_rate")
                        if br and not q.bitrate_kbps:
                            try:
                                q.bitrate_kbps = int(int(br)//1000)
                            except: pass
                        # Om fortfarande 0, beräkna från filstorlek/duration (CBR-approx)
                        if not q.bitrate_kbps and q.size_mb and q.duration_s:
                            try:
                                q.bitrate_kbps = int((q.size_mb*1024*1024*8)/(q.duration_s*1000))
                            except: pass
        except Exception:
            pass
    # Sista fallback: beräkna bitrate från storlek om fortfarande 0
    if q.bitrate_kbps == 0 and q.size_mb and q.duration_s > 10:
        try:
            q.bitrate_kbps = int((q.size_mb*1024*1024*8)/(q.duration_s*1000))
        except: pass
    return q


def quality_table(qualities: list[AudioQuality]) -> str:
    """Markdown-tabell med ljudkvalitet per fil."""
    lines = [
        "| Fil | Format | Codec | kbit/s | kHz | Kanaler | Längd | Storlek |",
        "|-----|--------|-------|--------|-----|---------|-------|---------|",
    ]
    for q in qualities:
        lines.append(
            f"| {os.path.basename(q.path)} | {q.format} | {q.codec or '-'} | "
            f"{q.bitrate_kbps or '-'} | {(q.sample_rate // 1000) if q.sample_rate else '-' } | "
            f"{q.channels or '-'} | {q.duration_text} | {q.size_mb} MB |"
        )
    return "\n".join(lines)


# ReplayGain — 1) volymnormalisering via ffmpeg loudnorm (om ffmpeg finns; annars None)
def replaygain(path: str) -> tuple[str | None, str | None]:
    """Beräkna ReplayGain för en fil via ffmpeg EBU R128. Returnerar (gain_dB, peak).

    gain_dB t.ex. "-7.23 dB", peak t.ex. "0.998". Ingen omkodning — endast analys.
    Kräver att ffmpeg finns i PATH. Returnerar (None, None) om ffmpeg saknas eller
    analysen misslyckas. Loggar aldrig känslig data.
    """
    import json
    import shutil
    import subprocess

    if not path or not os.path.exists(path):
        return (None, None)
    ff = shutil.which("ffmpeg")
    if not ff:
        return (None, None)
    # Kör ffmpeg loudnorm i en-pass (snabb analys, 30 s om filen är lång)
    # Vi använder hela filen för korta filer, annars första 90 s för snabbhet.
    try:
        # Använd print_format=json för att få input_i, input_tp, target_offset
        cmd = [
            ff, "-hide_banner", "-nostats",
            "-i", path,
            "-map", "a:0",
            "-af", "loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json",
            "-f", "null", "-",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=45, text=True)
        err = proc.stderr or ""
        # JSON ligger efter sista "{"  — ffmpeg skriver det till stderr
        import re
        m = re.search(r'\{[^}]*"input_i"[^}]*\}', err, re.S)
        if not m:
            # försök hitta hela JSON-blocket
            m2 = re.search(r'\{[\s\S]*?"target_offset"[\s\S]*?\}', err)
            if not m2:
                return (None, None)
            jtxt = m2.group(0)
        else:
            jtxt = m.group(0)
        data = json.loads(jtxt)
        # target_offset är gain som behövs för att nå -18 LUFS
        offset = data.get("target_offset") or data.get("input_offset")
        if offset is None:
            # fallback: beräkna från input_i
            try:
                inp = float(data.get("input_i", "-18").strip().split()[0])
                offset = -18.0 - inp
            except Exception:
                return (None, None)
        try:
            gain_val = float(str(offset).strip().split()[0])
        except Exception:
            return (None, None)
        # klipp till rimligt intervall -18 .. +6
        if gain_val < -18:
            gain_val = -18.0
        if gain_val > 12:
            gain_val = 12.0
        gain_str = f"{gain_val:.2f} dB"
        # peak: input_tp eller true-peak
        tp = data.get("input_tp") or data.get("input_true_peak") or "0"
        try:
            peak_val = float(str(tp).strip().split()[0])
            # TP är i dBTP (t.ex. "-1.5"); omvandla till linjär 0..1 för vorbis peak?
            # ReplayGain spec: peak är linjär 0..1. Vi approximerar: peak_lin = 10^(tp/20) om tp är dB
            if peak_val < 0:
                import math
                peak_lin = 10 ** (peak_val / 20.0)
            else:
                peak_lin = peak_val if peak_val <= 1.2 else 0.99
            peak_str = f"{peak_lin:.6f}"
        except Exception:
            peak_str = "0.999999"
        return (gain_str, peak_str)
    except Exception:
        return (None, None)


def book_md(
    title: str,
    author: str,
    album: str,
    series: str,
    series_number: str,
    year: str,
    url: str,
    source: str,
    score: float,
    qualities: list[AudioQuality],
    extra_note: str = "",
    subtitle: str = "",
    narrator: str = "",
    publisher: str = "",
    genre: str = "",
    language: str = "",
    description: str = "",
) -> str:
    """Markdown-faktablad som läggs bredvid ljudfilerna i outputmappen."""
    total_s = sum(q.duration_s for q in qualities)
    total_mb = sum(q.size_mb for q in qualities)
    best = max((q for q in qualities), key=lambda q: q.bitrate_kbps, default=None)
    s = int(total_s)
    parts = [
        f"# {title}",
        "",
        f"- **Författare:** {author or 'okänd'}",
        f"- **Uppläsare:** {narrator}" if narrator else "",
        f"- **Undertext:** {subtitle}" if subtitle else "",
        f"- **Förlag:** {publisher}" if publisher else "",
        f"- **Genre:** {genre}" if genre else "",
        f"- **Språk:** {language}" if language else "",
        f"- **Album:** {album}" if album else "",
        f"- **Serie:** {series}" + (f" #{series_number}" if series_number else "") if series else "",
        f"- **Först utgiven:** {year}" if year else "",
        f"- **Källa:** {source or 'goodreads'}" + (f" (matchpoäng {score:.2f})" if score else ""),
        f"- **Goodreads:** {url}" if url else "",
        f"- **Filer:** {len(qualities)} · **Total längd:** {s // 3600}h {(s % 3600) // 60:02d}m · **Storlek:** {round(total_mb, 1)} MB",
        f"- **Ljudkvalitet:** {best.verdict if best else 'okänd'}"
        + (f" ({best.bitrate_kbps} kbit/s, {best.sample_rate} Hz, {best.channels} kanaler)" if best and best.bitrate_kbps else ""),
        "",
        "## Ljudkvalitet per fil",
        "",
        quality_table(qualities),
    ]
    if description:
        parts += ["", "## Beskrivning", "", description[:1200]]
    if extra_note:
        parts += ["", "## Anteckning", "", extra_note]
    parts += ["", "---", "*Genererat av Audiobro.*"]
    return "\n".join(p for p in parts if p != "IGNORE")
