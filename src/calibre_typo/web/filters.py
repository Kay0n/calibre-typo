from __future__ import annotations

import difflib
import re

from markupsafe import Markup, escape

from ..epub import normalize

_WORD_RE = re.compile(r"\s+|\w+|[^\w\s]")


def word_diff(old: str, new: str) -> Markup:
    old_words = _WORD_RE.findall(normalize(old))
    new_words = _WORD_RE.findall(normalize(new))
    parts = []
    matcher = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        removed, added = "".join(old_words[i1:i2]), "".join(new_words[j1:j2])
        if op == "equal":
            parts.append(escape(removed))
            continue
        if removed:
            parts.append(Markup("<del>{}</del>").format(removed))
        if added:
            parts.append(Markup("<ins>{}</ins>").format(added))
    return Markup("").join(parts)


_MATCH_LABELS = {
    "context": "matched by context",
    "context before": "matched by text before",
    "context after": "matched by text after",
    "text only": "matched by text alone",
}


def match_label(method: str) -> str:
    base, sep, rest = method.partition(", ")
    return _MATCH_LABELS.get(base, base) + sep + rest


def fixes(count: int) -> str:
    return f"{count} fix" if count == 1 else f"{count} fixes"


def short_time(iso: str | None) -> str:
    return (iso or "")[:16].replace("T", " ")
