"""Offline-tester: körs mot sparad Goodreads-HTML (inga nätverksanrop)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ags import goodreads, library, matching, tags  # noqa: E402
from ags.models import AudioFile, Book, Proposal  # noqa: E402
from ags.text import (  # noqa: E402
    author_similarity, extract_part, split_series, title_key, title_similarity,
)

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name: str) -> str:
    with open(os.path.join(FIX, name), encoding="utf-8", errors="ignore") as fh:
        return fh.read()


# ------------------------------------------------------------------ parsning
def test_parse_search_returns_books_with_series():
    books = goodreads.parse_search_html(load("search_harry.html"))
    assert len(books) >= 10, f"förväntade >=10 träffar, fick {len(books)}"
    first = books[0]
    assert first.book_id.isdigit()
    assert "harry potter" in first.title.lower()
    assert any("rowling" in a.lower() for a in first.authors), first.authors
    assert first.series.lower().startswith("harry potter"), first.series
    assert first.series_number == "1", first.series_number
    assert first.url.startswith("https://www.goodreads.com/book/show/")
    assert not first.url.endswith("?")


def test_parse_search_strips_series_parenthesis_from_title():
    books = goodreads.parse_search_html(load("search_harry.html"))
    for b in books:
        assert "(" not in b.title, b.title


def test_parse_search_captures_rating_and_year():
    books = goodreads.parse_search_html(load("search_harry.html"))
    with_rating = [b for b in books if b.rating]
    assert with_rating, "ingen träff hade rating"
    b = with_rating[0]
    assert 0 < float(b.rating) <= 5
    assert b.ratings_count.replace(",", "").isdigit()


def test_parse_book_page_extracts_everything():
    b = goodreads.parse_book_html(load("book_hp1.html"), url="https://www.goodreads.com/book/show/3")
    assert "harry potter" in b.title.lower(), b.title
    assert any("rowling" in a.lower() for a in b.authors), b.authors
    assert b.series_number == "1", b.series_number
    assert b.series_id == "45175", b.series_id
    assert "harry potter" in b.series.lower(), repr(b.series)


def test_parse_series_name_from_react_props():
    name = goodreads.parse_series_name(load("series_hp.html"))
    assert name == "Harry Potter", repr(name)


def test_parse_series_name_from_book_page_aria():
    name = goodreads.parse_series_name_from_book(load("book_hp1.html"))
    assert name == "Harry Potter", repr(name)


def test_series_name_strips_trailing_word_series():
    html = (
        '<div data-react-class="ReactComponents.SeriesHeader" '
        'data-react-props="{&quot;title&quot;:&quot;Millennium Series&quot;,'
        '&quot;subtitle&quot;:&quot;3 primary works&quot;}"></div>'
    )
    assert goodreads.parse_series_name(html) == "Millennium"


def test_split_series_handles_part_suffix_and_leading_form():
    t, s, n = split_series("Harry Potter and the Order of the Phoenix (Harry Potter, #5, Part 1)")
    assert (t, s, n) == ("Harry Potter and the Order of the Phoenix", "Harry Potter", "5")
    t, s, n = split_series("(Harry Potter #2) The Chamber of Secrets")
    assert (t, s, n) == ("The Chamber of Secrets", "Harry Potter", "2")


# ------------------------------------------------------------------ text
def test_split_series():
    assert split_series("De sju systrarna (De sju systrarna, #3)") == ("De sju systrarna", "De sju systrarna", "3")
    assert split_series("Ren titel")[0] == "Ren titel"


def test_title_similarity_handles_imported_edition_noise():
    t = title_similarity("Isprinsessan",
                         "Isprinsessan (av Camilla Lackberg) [Imported] [Paperback] (Swedish) (Patrik Hedstrom) (2004-05-04)")
    assert t >= 0.85, t


def test_title_similarity_ignores_case_and_punctuation():
    assert title_similarity("Harry Potter and the Philosopher's Stone",
                            "harry potter & the philosopher's stone") > 0.95
    assert title_similarity("The Girl with the Dragon Tattoo", "Girl with the Dragon Tattoo") > 0.95
    assert title_similarity("Harry Potter", "Sagan om ringen") < 0.4


def test_author_similarity_handles_order_and_extra_people():
    assert author_similarity("J.K. Rowling", "JK Rowling") > 0.8
    assert author_similarity("J.K. Rowling", "Rowling, J.K.") > 0.7
    assert author_similarity("Camilla Läckberg", "Camilla Lackberg") > 0.9
    assert author_similarity("J.K. Rowling", "Stieg Larsson") < 0.3


def test_extract_part_from_filenames():
    assert extract_part("Millennium Del 3.mp3") == "3"
    assert extract_part("bok - Part 2.m4b") == "2"
    assert extract_part("serie/03 - titel.mp3") == "3"
    assert extract_part("ingen siffra här.mp3") == ""
    assert extract_part("Boken utgiven 2011.mp3") == ""  # årtal != delnummer


# ------------------------------------------------------------------ matchning
def test_score_prefers_right_series_number():
    audio = AudioFile(path="/bok/Harry Potter 1.mp3", album="Harry Potter", artist="J.K. Rowling")
    right = Book(title="Harry Potter and the Philosopher's Stone", authors=["J.K. Rowling"],
                 series="Harry Potter", series_number="1")
    wrong = Book(title="Harry Potter and the Chamber of Secrets", authors=["J.K. Rowling"],
                 series="Harry Potter", series_number="2")
    m_right = matching.score_audio(audio, right)
    m_wrong = matching.score_audio(audio, wrong)
    assert m_right.score > m_wrong.score
    assert m_right.score >= matching.HIGH, m_right.score


def test_status_thresholds():
    assert matching.status_for(0.95) == "matchad"
    assert matching.status_for(0.7) == "behöver koll"
    assert matching.status_for(0.2) == "ej matchad"


def test_rank_against_real_search_results():
    books = goodreads.parse_search_html(load("search_harry.html"))
    audio = AudioFile(path="/x/Harry Potter del 1.mp3", album="Harry Potter and the Philosopher's Stone",
                      artist="J.K. Rowling")
    ranked = matching.rank(books, audio)
    assert ranked, "ingen ranking"
    assert "philosopher" in ranked[0].book.title.lower() or "sorcerer" in ranked[0].book.title.lower()
    assert ranked[0].score >= matching.MEDIUM
    assert ranked[0].score >= ranked[-1].score


def test_guess_author_from_path():
    assert matching.guess_author_from_path("/musik/Camilla Läckberg - Isprinsessan.mp3") == "Camilla Läckberg"
    assert matching.guess_author_from_path("/ljudböcker/Stieg Larsson/Män som hatar kvinnor/01.mp3") == "Stieg Larsson"


def test_needs_manual_flags_close_competitors():
    from ags.models import Match
    b = Book(title="X")
    assert matching.needs_manual([Match(b, 0.80), Match(b, 0.79)]) is True
    assert matching.needs_manual([Match(b, 0.95), Match(b, 0.40)]) is False


# ------------------------------------------------------------------ taggar
def make_mp3(path: str) -> None:
    """Skapa en minimal men giltig MPEG-1 Layer III-fil (1 tyst frame-runda)."""
    # header: MPEG1 Layer3, 128 kbit/s, 44.1 kHz, ingen padding
    header = bytes([0xFF, 0xFB, 0x90, 0x00])
    frame = header + b"\x00" * (417 - 4)
    with open(path, "wb") as fh:
        fh.write(frame * 26)  # ~1 s


def test_write_and_read_back_mp3(tmp_path):
    assert tags.mutagen_available(), "mutagen måste finnas för taggtester"
    p = str(tmp_path / "test.mp3")
    make_mp3(p)
    res = tags.write_file(p, {
        "title": "Harry Potter and the Philosopher's Stone",
        "artist": "J.K. Rowling",
        "album": "Harry Potter, #1",
        "series": "Harry Potter",
        "series_number": "1",
        "year": "1997",
        "track": "1/7",
    })
    assert res.ok, res.error
    assert set(res.written) >= {"title", "artist", "album", "series", "series_number", "year", "track"}
    back = library.read_tags(p)
    assert back["title"] == "Harry Potter and the Philosopher's Stone"
    assert back["artist"] == "J.K. Rowling"
    assert back["album"] == "Harry Potter, #1"
    assert back["series"] == "Harry Potter"
    assert back["series_number"] == "1"
    assert back["track"].startswith("1/7")
    assert back["year"].startswith("1997")
    assert os.path.exists(p + ".agsbak")


def test_write_utf8_swedish_characters(tmp_path):
    p = str(tmp_path / "sv.mp3")
    make_mp3(p)
    res = tags.write_file(p, {"title": "Män som hatar kvinnor", "artist": "Stieg Larsson",
                              "album": "Millennium, #1", "series": "Millennium"}, backup=False)
    assert res.ok, res.error
    back = library.read_tags(p)
    assert back["title"] == "Män som hatar kvinnor"
    assert back["album"] == "Millennium, #1"


def make_m4b(path: str) -> None:
    """Minimal giltig MP4/M4B-container (ftyp + mdat + moov/mvhd)."""
    import struct

    def atom(name: bytes, payload: bytes = b"") -> bytes:
        return struct.pack(">I", 8 + len(payload)) + name + payload

    mvhd = struct.pack(">IIII", 0, 0, 0, 1000) + struct.pack(">I", 5000) + b"\x00" * 80
    with open(path, "wb") as fh:
        fh.write(atom(b"ftyp", b"M4B " + struct.pack(">I", 0) + b"M4B mp42isom"))
        fh.write(atom(b"mdat", b"\x00" * 512))
        fh.write(atom(b"moov", atom(b"mvhd", mvhd)))


def test_write_and_read_back_m4b(tmp_path):
    assert tags.mutagen_available()
    p = str(tmp_path / "ljud.m4b")
    make_m4b(p)
    res = tags.write_file(p, {
        "title": "Män som hatar kvinnor", "artist": "Stieg Larsson",
        "album": "Millennium, #1", "series": "Millennium", "series_number": "1",
        "year": "2005", "track": "1/3",
    }, backup=False)
    assert res.ok, res.error
    assert {"title", "artist", "album", "series", "series_number"} <= set(res.written), res.written
    back = library.read_tags(p)
    assert back["title"] == "Män som hatar kvinnor"
    assert back["series"] == "Millennium"
    assert back["series_number"] == "1"
    assert back["track"].startswith("1")


def test_write_unsupported_format_reports_error(tmp_path):
    p = tmp_path / "fil.xyz"
    p.write_bytes(b"x")
    res = tags.write_file(str(p), {"title": "t"})
    assert not res.ok
    assert "stöds inte" in res.error


def test_scan_and_group(tmp_path):
    d = tmp_path / "ljudböcker" / "Harry Potter"
    d.mkdir(parents=True)
    for i in (1, 2, 3):
        p = d / f"Harry Potter {i}.mp3"
        make_mp3(str(p))
        tags.write_file(str(p), {"title": f"Harry Potter and the Philosopher's Stone, Del {i}",
                                 "album": "Harry Potter and the Philosopher's Stone",
                                 "artist": "J.K. Rowling", "track": f"{i}/3"}, backup=False)
    files = library.scan(str(tmp_path))
    assert len(files) == 3
    groups = library.group_files(files)
    assert len(groups) == 1, [library.label_group(g) for g in groups]
    assert len(groups[0]) == 3
    assert [f.track for f in groups[0]] == ["1/3", "2/3", "3/3"]


def test_scan_reads_tags_written_earlier(tmp_path):
    p = tmp_path / "a.mp3"
    make_mp3(str(p))
    tags.write_file(str(p), {"title": "Titel", "artist": "Författare", "album": "Album"}, backup=False)
    files = library.scan(str(tmp_path))
    assert len(files) == 1
    assert files[0].title == "Titel"
    assert files[0].artist == "Författare"
    assert files[0].album == "Album"
    assert files[0].format == "mp3"


# ------------------------------------------------------------------ motor
def test_engine_builds_fields_with_track_numbers():
    from ags.engine import Engine, EngineOptions
    from ags.models import Match

    class FakeClient:
        def save_cache(self):
            pass

    eng = Engine(FakeClient(), EngineOptions())
    audio = AudioFile(path="/x/a.mp3", album="X", title="X", artist="A")
    p = Proposal(audio=audio)
    p.paths = ["/x/a.mp3", "/x/b.mp3"]
    p.new_title = "Titel"
    p.new_artist = "Författare"
    p.new_album = "Serie, #2"
    p.new_series = "Serie"
    p.new_series_number = "2"
    p.match = Match(Book(title="Titel", authors=["Författare"], series="Serie", series_number="2"), 0.99)
    f0 = eng.build_file_fields(p, 0, 2)
    f1 = eng.build_file_fields(p, 1, 2)
    assert f0["track"] == "1/2" and f1["track"] == "2/2"
    assert f0["album"] == "Serie, #2" and f0["series"] == "Serie"


def test_engine_apply_dry_run_writes_nothing(tmp_path):
    from ags.engine import Engine

    class FakeClient:
        def save_cache(self):
            pass

    p = tmp_path / "a.mp3"
    make_mp3(str(p))
    audio = AudioFile(path=str(p), album="X", title="X")
    prop = Proposal(audio=audio, new_title="Ny titel")
    prop.paths = [str(p)]
    eng = Engine(FakeClient())
    results = eng.apply(prop, dry_run=True)
    assert results and results[0].ok
    assert "title" in results[0].written
    assert library.read_tags(str(p)).get("title") in (None, "", "X")  # inget skrivet


def test_engine_apply_writes_real_file(tmp_path):
    from ags.engine import Engine, EngineOptions

    class FakeClient:
        def save_cache(self):
            pass

    p = tmp_path / "a.mp3"
    make_mp3(str(p))
    audio = AudioFile(path=str(p), album="Harry Potter", title="Harry Potter", artist="J.K. Rowling")
    prop = Proposal(audio=audio, new_title="Harry Potter and the Philosopher's Stone",
                    new_artist="J.K. Rowling", new_album="Harry Potter, #1",
                    new_series="Harry Potter", new_series_number="1")
    prop.paths = [str(p)]
    eng = Engine(FakeClient(), EngineOptions())
    results = eng.apply(prop, dry_run=False)
    assert results[0].ok, results[0].error
    back = library.read_tags(str(p))
    assert back["title"] == "Harry Potter and the Philosopher's Stone"
    assert back["series_number"] == "1"


def test_engine_match_group_uses_offline_client():
    """match_group mot en klient som serverar sparad sök-HTML."""
    from ags.engine import Engine

    class OfflineClient:
        def search_best(self, q, limit=6):
            return goodreads.parse_search_html(load("search_harry.html"))[:limit]

        def save_cache(self):
            pass

    eng = Engine(OfflineClient())
    audio = AudioFile(path="/x/Harry Potter 1.mp3", album="Harry Potter and the Philosopher's Stone",
                      artist="J.K. Rowling")
    prop, matches = eng.match_group([audio])
    assert prop.status in ("matchad", "behöver koll"), (prop.status, prop.note)
    assert prop.new_series == "Harry Potter", prop.new_series
    assert prop.new_album == "Harry Potter, #1", prop.new_album
    assert prop.new_artist == "J.K. Rowling"
    assert "philosopher" in prop.new_title.lower() or "sorcerer" in prop.new_title.lower()


# ------------------------------------------------------------------ ocr
def test_ocr_parse_two_line_layout():
    from ags import ocr
    text = """Harry Potter and the Philosopher's Stone
av J.K. Rowling
2011

De sju systrarna
av Lucinda Riley
"""
    entries = ocr.parse_entries(text)
    assert len(entries) == 2
    assert entries[0].title.startswith("Harry Potter")
    assert entries[0].author == "J.K. Rowling"
    assert entries[1].author == "Lucinda Riley"


def test_ocr_parse_dash_layout():
    from ags import ocr
    entries = ocr.parse_entries("Stieg Larsson – Män som hatar kvinnor\nCamilla Läckberg - Isprinsessan")
    assert len(entries) == 2
    assert entries[0].author == "Stieg Larsson"
    assert entries[0].title == "Män som hatar kvinnor"


def test_ocr_tesseract_missing_raises_clear_error(tmp_path):
    from ags import ocr
    if ocr.tesseract_available():
        pytest.skip("tesseract finns installerat")
    with pytest.raises(RuntimeError) as exc:
        ocr.ocr_image(str(tmp_path / "x.png"))
    assert "tesseract" in str(exc.value).lower()


def test_goodreads_blocked_detected():
    from ags.goodreads import Goodreads
    assert Goodreads._looks_blocked(403, "<title>Just a moment...</title>")
    assert Goodreads._looks_blocked(200, "cf-browser-verification challenge")
    assert not Goodreads._looks_blocked(200, "<html><title>Search results</title>")
