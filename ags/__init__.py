"""audiobook-goodreads-sync (ags)

Synkar metadata för dina ljudboksfiler (mp3/m4b/flac/ogg) mot Goodreads:
titel, författare, serie och delnummer i serien.
"""
from __future__ import annotations

from .models import AudioFile, Book, Match, Proposal
from .goodreads import Goodreads, GoodreadsBlocked, GoodreadsError
from .engine import Engine, EngineOptions

__all__ = [
    "AudioFile", "Book", "Match", "Proposal",
    "Goodreads", "GoodreadsBlocked", "GoodreadsError",
    "Engine", "EngineOptions",
    "__version__",
]

__version__ = "1.0.0"
