"""Presenteringslogik för GUI:t — rena funktioner, testbara utan skärm."""
from __future__ import annotations

import os

from .models import Proposal
from .tags import mutagen_available

# Kolumner i resultattabellen: (nyckel, rubrik, bredd)
COLUMNS = [
    ("status", "Status", 90),
    ("label", "Ljudbok", 260),
    ("new_title", "Ny titel", 260),
    ("new_artist", "Författare", 150),
    ("new_album", "Album", 170),
    ("new_series", "Serie", 130),
    ("new_series_number", "Del", 40),
    ("score", "Poäng", 55),
    ("source", "Källa", 90),
]

STATUS_TAG = {
    "matchad": "ok",
    "behöver koll": "warn",
    "blockerad": "blocked",
    "fel": "blocked",
    "klar (historik)": "done",
    "klar (organiserad)": "done",
    "sämre version": "none",
    "ej matchad": "none",
    "ignorerad dublett": "ignored_dup",
    "ignorerad": "ignored_dup",
}


def proposal_row(p: Proposal) -> dict:
    """Gör om ett förslag till en tabellrad."""
    return {
        "status": p.status,
        "label": p.audio.group_label or os.path.basename(p.audio.path),
        "files": len(getattr(p, "paths", None) or [p.audio.path]),
        "new_title": p.new_title,
        "new_artist": p.new_artist,
        "new_album": p.new_album,
        "new_series": p.new_series,
        "new_series_number": p.new_series_number,
        "new_year": p.new_year,
        "score": f"{p.match.score:.2f}" if p.match else "",
        "source": p.source or "",
        "note": p.note,
        "url": p.match.book.url if p.match else "",
        "tag": STATUS_TAG.get(p.status, "none"),
    }


def row_values(row: dict) -> tuple:
    """Värden i kolumnordning (för Treeview.insert)."""
    return tuple(str(row.get(key, "")) for key, _h, _w in COLUMNS)


def changes_text(p: Proposal) -> str:
    """Text som beskriver exakt vad som skrivs i filen."""
    ch = p.changes()
    if not ch:
        return "Inga ändringar — taggarna stämmer redan."
    lines = []
    for name, old, new in ch:
        lines.append(f"{name}: {old or '(tom)'}  →  {new}")
    paths = getattr(p, "paths", None) or [p.audio.path]
    if len(paths) > 1:
        lines.append(f"Skrivs till {len(paths)} filer, spårnummer 1/{len(paths)} … {len(paths)}/{len(paths)}")
    return "\n".join(lines)


def summary_rows(rows: list[dict]) -> dict:
    """Räkna ihop statusar för statusraden."""
    out = {"total": len(rows), "files": 0}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
        out["files"] += r.get("files", 1)
    return out


def summary_text(rows: list[dict]) -> str:
    s = summary_rows(rows)
    parts = [
        f"{s['total']} grupper ({s['files']} filer)",
        f"{s.get('matchad', 0)} klara",
        f"{s.get('behöver koll', 0)} behöver koll",
        f"{s.get('ej matchad', 0)} utan träff",
    ]
    if s.get("blockerad"):
        parts.append(f"{s['blockerad']} blockerade")
    return " · ".join(parts)


def startup_warnings() -> list[str]:
    """Varningar som ska visas i GUI:t vid start."""
    w: list[str] = []
    if not mutagen_available():
        w.append(
            "mutagen saknas — appen kan läsa mappar men inte skriva taggar. "
            "Installera: pip install mutagen"
        )
    try:
        from . import ocr

        if not ocr.borttaget_available():
            w.append(
                "borttaget saknas — skärmbildsläget behöver att du klistrar in texten "
                "i textrutan i stället (eller installera borttaget)."
            )
    except Exception:
        pass
    return w


GOODREADS_HELP = """Goodreads svarar med en kontroll
Lös det på ett av tre sätt:

1. Klistra in din webbläsares token
   Öppna goodreads.com i din webbläsare (där sidan fungerar).
   Devtools (F12) → Application → Cookies → goodreads.com →
   kopiera värdet för "Goodreads-token" och klistra in det i fältet
   "Goodreads-token" nedan, klicka sedan på Använd token.

2. Kör lugnare
   Sätt fördröjningen till 3–5 sekunder och vänta några minuter.
   Blockeringen släpper oftast av sig själv.

3. Använd läget "Skärmbild / text"
   Det kräver ingen uppkoppling till Goodreads alls: du klistrar in
   titlarna (eller en skärmbild) och appen matchar dem.

Tips: Fungerar även offline — klistra in titlarna direkt.
"""

# bakåtkompatibilitet
WAF_HELP = GOODREADS_HELP
