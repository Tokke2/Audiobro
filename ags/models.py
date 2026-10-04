"""Datamodeller för Audiobro."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Book:
    """En bok som hämtats från Goodreads."""

    book_id: str = ""
    url: str = ""
    title: str = ""
    authors: list[str] = field(default_factory=list)
    series: str = ""
    series_number: str = ""
    series_id: str = ""
    year: str = ""
    rating: str = ""
    ratings_count: str = ""
    cover: str = ""
    language: str = ""
    source: str = "goodreads"
    subtitle: str = ""
    description: str = ""
    narrators: list[str] = field(default_factory=list)
    publisher: str = ""
    genres: list[str] = field(default_factory=list)
    isbn: str = ""
    asin: str = ""

    @property
    def series_label(self) -> str:
        """'Harry Potter #1' eller '' när vi saknar seriedata."""
        if self.series and self.series_number:
            return f"{self.series} #{self.series_number}"
        return self.series or ""

    @property
    def display(self) -> str:
        a = ", ".join(self.authors)
        s = f" [{self.series_label}]" if self.series_label else ""
        return f"{self.title} — {a}{s}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Match:
    """Ett matchningsförslag med poäng."""

    book: Book
    score: float = 0.0
    title_score: float = 0.0
    author_score: float = 0.0
    series_bonus: float = 0.0
    penalty: float = 0.0     # minuspoäng (fel del i serien / fel författare)

    @property
    def confidence(self) -> str:
        if self.score >= 0.90:
            return "hög"
        if self.score >= 0.70:
            return "medel"
        if self.score >= 0.45:
            return "låg"
        return "osäker"


@dataclass
class AudioFile:
    """En ljudbokfil i biblioteket."""

    path: str = ""
    album: str = ""          # nuvarande albuntagg (eller mappnamn)
    title: str = ""          # nuvarande titeltagg (eller filnamn)
    artist: str = ""         # nuvarande artisttagg
    track: str = ""          # nuvarande spårnummer
    year: str = ""
    format: str = ""         # mp3 / m4b / flac ...
    size_mb: float = 0.0
    group_key: str = ""      # för gruppering i samma "album"
    part_number: str = ""    # "Del 3", "Part 2", "03" osv. ur filnamnet
    group_label: str = ""
    disc: int = 0            # 0 = ingen disc-info, 1/2/… = CD/skiva

    def query_title(self) -> str:
        t = self.album or self.title
        return t or "unknown"


@dataclass
class Proposal:
    """Resultatet av en matchning för en fil/grupp."""

    audio: AudioFile
    match: Optional[Match] = None
    new_title: str = ""
    new_artist: str = ""
    new_album: str = ""
    new_series: str = ""
    new_series_number: str = ""
    new_year: str = ""
    new_track: str = ""
    new_subtitle: str = ""
    new_description: str = ""
    new_narrator: str = ""
    new_publisher: str = ""
    new_genre: str = ""
    new_isbn: str = ""
    new_asin: str = ""
    new_language: str = ""
    status: str = "ej matchad"   # matchad / behöver koll / blockerad / ej matchad / klar (historik)
    note: str = ""
    source: str = ""             # goodreads / openlibrary / goodreads:länk
    skipped: bool = False        # redan färdigbehandlad enligt historiken
    applied: bool = False

    def identity(self) -> str:
        """Stabil nyckel för historiken (Goodreads-id i första hand)."""
        from .history import identity_key

        bid = self.match.book.book_id if self.match else ""
        return identity_key(self.new_title or self.audio.title,
                            self.new_artist or self.audio.artist,
                            self.new_series, self.new_series_number, book_id=bid)

    def changes(self) -> list[tuple[str, str, str]]:
        """(fält, gammalt, nytt) för fält som faktiskt skiljer sig."""
        out = []
        pairs = [
            ("Titel", self.audio.title, self.new_title),
            ("Artist", self.audio.artist, self.new_artist),
            ("Album", self.audio.album, self.new_album),
            ("Serie", "", self.new_series),
            ("Del i serie", "", self.new_series_number),
            ("År", self.audio.year, self.new_year),
            ("Spår", self.audio.track, self.new_track),
            ("Undertext", "", self.new_subtitle),
            ("Uppläsare", "", self.new_narrator),
            ("Förlag", "", self.new_publisher),
            ("Genre", self.audio.genre if hasattr(self.audio, "genre") else "", self.new_genre),
            ("Språk", "", self.new_language),
        ]
        for name, old, new in pairs:
            if new and new != old:
                out.append((name, old, new))
        return out
