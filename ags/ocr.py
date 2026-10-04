"""OCR-reserv: läs titel/författare ur en skärmbild när webbskrapning blockas.

Två lägen:
  1) tesseract installerat  -> automatisk avläsning (pip/apt krävs utanför appen)
  2) inklistrad text        -> appen parsar texten direkt, ingen OCR behövs

Appen fungerar alltså även utan tesseract: klistra in texten från bilden.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

from .models import AudioFile
from .text import year_from


@dataclass
class OcrCandidate:
    title: str = ""
    author: str = ""
    year: str = ""
    raw: str = ""

    def as_audio(self, index: int = 0) -> AudioFile:
        return AudioFile(
            path=f"<skärmbild #{index + 1}>",
            album=self.title,
            title=self.title,
            artist=self.author,
            year=self.year,
        )


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_image(path: str, languages: str = "swe+eng") -> str:
    """Kör tesseract på en bild. Kastar RuntimeError om tesseract saknas."""
    if not tesseract_available():
        raise RuntimeError(
            "tesseract är inte installerat. Installera det eller klistra in "
            "texten från skärmbilden i textrutan i stället."
        )
    try:
        out = subprocess.run(
            ["tesseract", path, "stdout", "-l", languages, "--psm", "6"],
            capture_output=True, text=True, timeout=120, check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("tesseract tog för lång tid (>120 s).")
    if out.returncode != 0:
        raise RuntimeError(f"tesseract misslyckades: {out.stderr.strip()[:300]}")
    return out.stdout


def clean_ocr_text(text: str) -> str:
    """Rensa typiska OCR-artefakter."""
    t = text.replace("\u00a0", " ")
    t = re.sub(r"[ \t]*\n[ \t]*", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    # vanliga förväxlingar
    t = re.sub(r"(?<=\w)\|(?=\w)", "l", t)
    t = re.sub(r"(?<=\d)O(?=\d)", "0", t)
    return t.strip()


# "av Namn Namnson", "Namn - Titel", "Title by Author"
AUTHOR_PATTERNS = [
    re.compile(r"^\s*(?:av|by)\s+(.{2,60}?)\s*$", re.I),
    re.compile(r"^\s*(.{2,60}?)\s+av\s+(.{2,60}?)\s*$", re.I),
    re.compile(r"^\s*(.{2,60}?)\s*[-–—|]\s*(.{2,60}?)\s*$"),
]
YEAR_ONLY = re.compile(r"^\s*(1[89][0-9]{2}|20[0-9]{2})\s*$")
NOISE_LINE = re.compile(
    r"^\s*(ljudbok|audiobook|inläst av|read by|narrated by|del \d+|part \d+|"
    r"kapitel|chapter|cd \d+|\d+\s*/\s*\d+|goodreads|storytel|bookbeat)\b",
    re.I,
)


def parse_entries(text: str, limit: int = 50) -> list[OcrCandidate]:
    """Tolka OCR-/inklistrad text till (titel, författare)-par.

    Hanterar de vanligaste layouterna:
        Titelrad
        av Författare
        2011
    eller
        Författare – Titel
    """
    text = clean_ocr_text(text or "")
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    out: list[OcrCandidate] = []
    i = 0
    while i < len(lines) and len(out) < limit:
        line = lines[i]
        if NOISE_LINE.match(line) or YEAR_ONLY.match(line):
            i += 1
            continue
        title, author, year = "", "", year_from(line)
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        m = re.match(r"^\s*(?:av|by)\s+(.{2,60})$", nxt, re.I)
        if m:
            title, author = line, m.group(1).strip()
            i += 2
            # årtal på egen rad efter författaren ("2003")
            if not year and i < len(lines) and YEAR_ONLY.match(lines[i]):
                year = YEAR_ONLY.match(lines[i]).group(1)
                i += 1
        else:
            m2 = AUTHOR_PATTERNS[2].match(line)
            if m2 and len(m2.group(1)) >= 3:
                # "Författare – Titel" om vänstern ser ut som ett personnamn
                left, right = m2.group(1).strip(), m2.group(2).strip()
                if _looks_like_person(left) and not _looks_like_person(right):
                    author, title = left, right
                else:
                    title, author = left, right
                i += 1
            else:
                title = line
                i += 1
        title = re.sub(r"\s*[-–—]\s*(1[89][0-9]{2}|20[0-9]{2})\s*$", "", title).strip()
        if not title:
            continue
        out.append(OcrCandidate(title=title, author=author, year=year, raw=line))
    return out


def _looks_like_person(s: str) -> bool:
    words = [w for w in re.split(r"[\s.]+", s) if w]
    if not 1 <= len(words) <= 4:
        return False
    if len(words) >= 2 and all(w[:1].isupper() for w in words if w[:1].isalpha()):
        return True
    return False


def entries_from_image(path: str, limit: int = 50) -> list[OcrCandidate]:
    return parse_entries(ocr_image(path), limit=limit)
