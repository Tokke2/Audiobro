"""Text-tolkning för OCR-läget — ingen tesseract, endast inklistrad text.

Tidigare kunde tesseract användas för automatisk bild-till-text, men kravet är nu helt borttaget.
Appen matchar endast via Goodreads och via inklistrad text (manuell).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

@dataclass
class OcrCandidate:
    title: str
    author: str = ""
    year: str = ""
    raw: str = ""

def tesseract_available() -> bool:
    return False

def ocr_image(path: str, languages: str = "swe+eng") -> str:
    """Borttagen — tesseract finns ej längre. Använd parse_entries på inklistrad text."""
    raise RuntimeError(
        "Bildläsning borttagen — tesseract är helt borttaget från appen. "
        "Klistra in titlarna från bilden i textrutan och klicka 'Tolka inklistrad text'. "
        "Matchning sker endast mot Goodreads."
    )

def clean_ocr_text(text: str) -> str:
    return (text or "").strip()

YEAR_ONLY = re.compile(r"^\s*(1[89][0-9]{2}|20[0-9]{2})\s*$")
NOISE_LINE = re.compile(r"^\s*$|^[\-–—\.\s]{2,}$")
AUTHOR_PATTERNS = [
    re.compile(r"^(.+?)\s*[–—-]\s*(.+)$"),
    re.compile(r"^(.+?)\s*:\s*(.+)$"),
    re.compile(r"^(.+?)\s+[–—-]\s+(.+)$"),
]

def year_from(s: str) -> str:
    m = re.search(r"(1[89][0-9]{2}|20[0-9]{2})", s or "")
    return m.group(1) if m else ""

def _looks_like_person(s: str) -> bool:
    words = [w for w in re.split(r"[\s.]+" , s) if w]
    if not 1 <= len(words) <= 4:
        return False
    if len(words) >= 2 and all(w[:1].isupper() for w in words if w[:1].isalpha()):
        return True
    return False

def parse_entries(text: str, limit: int = 50) -> list[OcrCandidate]:
    """Tolka OCR-/inklistrad text till (titel, författare)-par."""
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
            if not year and i < len(lines) and YEAR_ONLY.match(lines[i]):
                year = YEAR_ONLY.match(lines[i]).group(1)
                i += 1
        else:
            m2 = AUTHOR_PATTERNS[0].match(line)
            if m2 and len(m2.group(1)) >= 3:
                left, right = m2.group(1).strip(), m2.group(2).strip()
                if _looks_like_person(left) and not _looks_like_person(right):
                    author, title = left, right
                elif len(left.split()) <= 3 and len(right) > len(left):
                    author, title = left, right
                else:
                    title = line
                    i += 1
                    title = re.sub(r"\s*[-–—]\s*(1[89][0-9]{2}|20[0-9]{2})\s*$", "", title).strip()
                    if title:
                        out.append(OcrCandidate(title=title, author=author, year=year, raw=line))
                    continue
                i += 1
            else:
                title = line
                i += 1
        title = re.sub(r"\s*[-–—]\s*(1[89][0-9]{2}|20[0-9]{2})\s*$", "", title).strip()
        if not title:
            continue
        out.append(OcrCandidate(title=title, author=author, year=year, raw=line))
    return out

def entries_from_image(path: str, limit: int = 50) -> list[OcrCandidate]:
    return parse_entries(ocr_image(path), limit=limit)
