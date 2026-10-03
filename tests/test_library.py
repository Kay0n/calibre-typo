from __future__ import annotations

import sqlite3

import pytest

from calibre_typo.library import CalibreLibrary, LibraryUnavailable, suggest
from sample_library import BOOK_UUID, make_library


def test_match_by_embedded_calibre_uuid(library_dir):
    library = CalibreLibrary(library_dir)
    assert library.match(title="Totally different", authors=None,
                         identifiers=f"calibre:{BOOK_UUID}\nisbn:123", filename=None) == 1


def test_match_by_title_ignoring_case_and_punctuation(library_dir):
    library = CalibreLibrary(library_dir)
    assert library.match(title="golden son!", authors=None, identifiers=None, filename=None) == 2


def test_match_by_filename(library_dir):
    library = CalibreLibrary(library_dir)
    assert library.match(title=None, authors=None, identifiers=None,
                         filename="/mnt/us/books/Golden Son - Pierce Brown.epub") == 2


def test_no_match(library_dir):
    library = CalibreLibrary(library_dir)
    assert library.match(title="Unknown", authors=None, identifiers=None, filename=None) is None


def test_record_file_change_updates_size_and_timestamp(library_dir, epub_path):
    CalibreLibrary(library_dir).record_file_change(1, "EPUB", epub_path)
    conn = sqlite3.connect(library_dir / "metadata.db")
    size = conn.execute("SELECT uncompressed_size FROM data WHERE book = 1").fetchone()[0]
    modified = conn.execute("SELECT last_modified FROM books WHERE id = 1").fetchone()[0]
    assert size == epub_path.stat().st_size
    assert modified is not None


def test_suggest_ranks_books_by_shared_title_words(library_dir):
    books = CalibreLibrary(library_dir).books()
    picks = suggest(books, title="Fugitive Telemetry (web edition)", filename=None)
    assert [b.title for b in picks] == ["Fugitive Telemetry"]
    assert suggest(books, title="The Art of War", filename=None) == []


def test_library_folder_names_with_url_characters(tmp_path):
    for name in ("Books #2", "what?", "100%"):
        root = tmp_path / name
        root.mkdir()
        make_library(root)
        assert [b.title for b in CalibreLibrary(root).books()] == ["Fugitive Telemetry", "Golden Son"]


def test_missing_library_is_reported_without_creating_one(tmp_path):
    with pytest.raises(LibraryUnavailable):
        CalibreLibrary(tmp_path).books()
    assert not (tmp_path / "metadata.db").exists()
