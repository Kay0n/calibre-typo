from __future__ import annotations

import zipfile

import pytest

from calibre_typo.epub import EditNotApplicable, EpubDocument, TextEdit
from calibre_typo.epub.text import TextNotFound, find_unique, flatten, normalize


def chapter_source(path, name):
    with zipfile.ZipFile(path) as z:
        return z.read(f"OEBPS/text/{name}").decode()


def test_flatten_hides_head_and_collapses_whitespace():
    flat = flatten("<html><head><title>T</title><style>p{}</style></head>"
                   "<body><p>Fish &amp;   chips</p><p>Next</p></body></html>")
    assert flat.text == "Fish & chips Next "


def test_flatten_spans_point_at_source():
    source = "<p>a &amp; b</p>"
    flat = flatten(source)
    ampersand = flat.text.index("&")
    start, end = flat.spans[ampersand]
    assert source[start:end] == "&amp;"


def test_normalize_matches_flatten_rules():
    assert normalize("  a \n b­c ") == "a bc"


def test_find_uses_context_to_pick_between_repeats():
    text = "The the ship was quiet. Later, the the ship was loud."
    match = find_unique(text, "the the", before="Later,", after="ship was loud")
    assert text[match.start:match.end] == "the the"
    assert match.start > text.index("Later")


def test_find_reports_ambiguity_without_context():
    with pytest.raises(TextNotFound, match="more than once"):
        find_unique("x the the y the the z", "the the")


def test_find_ignores_spacing_differences_at_joins():
    match = find_unique("replied query: identify, and", "identify,", before="replied query:", after="and")
    assert match.method == "context"


def test_fix_across_italic_keeps_markup(epub_path):
    doc = EpubDocument(epub_path)
    doc.apply(TextEdit(original="I replied query: identify, and attached",
                       replacement="I replied query: identify and attached"))
    doc.save()
    source = chapter_source(epub_path, "ch1.xhtml")
    assert "I replied <i>query: identify</i> and attached" in source


def test_fix_next_to_entity(epub_path):
    doc = EpubDocument(epub_path)
    doc.apply(TextEdit(original="Fish & chips were served", replacement="Fish & chips are served"))
    doc.save()
    assert "Fish &amp; chips are" in chapter_source(epub_path, "ch1.xhtml")


def test_xpointer_hint_and_context_choose_the_right_repeat(epub_path):
    doc = EpubDocument(epub_path)
    location = doc.apply(TextEdit(original="the the", replacement="the", before="Later,",
                                  after="ship was loud", xpointer="/body/DocFragment[2]/body/p[2]/text().7"))
    assert location.item.endswith("ch2.xhtml")
    doc.save()
    source = chapter_source(epub_path, "ch2.xhtml")
    assert "The the ship was quiet" in source
    assert "Later, the ship was loud" in source


def test_unknown_text_is_refused(epub_path):
    with pytest.raises(EditNotApplicable, match="not found"):
        EpubDocument(epub_path).locate(TextEdit(original="no such words", replacement="x"))


def test_saved_epub_keeps_mimetype_first_and_uncompressed(epub_path):
    doc = EpubDocument(epub_path)
    doc.apply(TextEdit(original="She said hello.", replacement="She said goodbye."))
    doc.save()
    with zipfile.ZipFile(epub_path) as z:
        first = z.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
        assert z.testzip() is None


def test_preview_shows_surrounding_text(epub_path):
    preview = EpubDocument(epub_path).preview(TextEdit(original="walked", replacement="strolled",
                                                       before="A non-dead human", after="into the lobby"))
    assert preview.current == "walked"
    assert preview.before.endswith("A non-dead human ")
    assert preview.after.startswith(" into the lobby")
