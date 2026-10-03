from calibre_typo.web.filters import fixes, match_label


def test_match_label():
    assert match_label("context") == "matched by context"
    assert match_label("text only, other chapter") == "matched by text alone, other chapter"


def test_fixes_is_plural_aware():
    assert [fixes(n) for n in (0, 1, 2)] == ["0 fixes", "1 fix", "2 fixes"]
