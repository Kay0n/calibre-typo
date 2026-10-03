"""Whitespace and block boundaries become single spaces, matching KOReader's text.
Each character keeps its source span for writing back"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

TOKEN_RE = re.compile(
    r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<![^>]*>|<[^>]+>|&#?\w+;|[^<&]+|&",
    re.S,
)
_TAG_NAME_RE = re.compile(r"</?\s*([\w:-]+)")

BLOCK_TAGS = frozenset({
    "article", "aside", "blockquote", "body", "br", "dd", "div", "dl", "dt",
    "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hr", "img", "li", "nav", "ol", "p", "pre", "section", "table",
    "td", "th", "tr", "ul",
})
HIDDEN_TAGS = frozenset({"head", "script", "style", "title"})

WHITESPACE = frozenset(
    " \t\n\r\f\v         "
    "     　"
)
INVISIBLE = frozenset("­​‌‍⁠﻿")

Span = tuple[int, int]


@dataclass(frozen=True)
class FlatText:
    """``start == end`` marks a virtual space for a block boundary"""

    text: str
    spans: list[Span]


@dataclass(frozen=True)
class TextMatch:
    start: int
    end: int
    method: str


class TextNotFound(Exception):
    pass


def is_tag(token: str) -> bool:
    return token.startswith("<")


def normalize(text: str | None) -> str:
    """Must match `flatten`, or selections won't line up"""
    visible = "".join(c for c in (text or "") if c not in INVISIBLE)
    spaced = "".join(" " if c in WHITESPACE else c for c in visible)
    return re.sub(r" +", " ", spaced).strip()


def _tag_name(tag: str) -> str | None:
    match = _TAG_NAME_RE.match(tag)
    return match.group(1).split(":")[-1].lower() if match else None


class _Builder:
    def __init__(self) -> None:
        self.chars: list[str] = []
        self.spans: list[Span] = []

    def add(self, char: str, start: int, end: int) -> None:
        if char in INVISIBLE:
            return
        if char in WHITESPACE:
            self._add_space(start, end)
        else:
            self.chars.append(char)
            self.spans.append((start, end))

    def add_boundary(self, pos: int) -> None:
        self._add_space(pos, pos)

    def _add_space(self, start: int, end: int) -> None:
        if not self.chars:
            return  # leading whitespace is never visible
        if self.chars[-1] != " ":
            self.chars.append(" ")
            self.spans.append((start, end))
            return
        # Adopt real whitespace, so deleting the space removes it too
        prev_start, prev_end = self.spans[-1]
        if prev_start == prev_end:
            self.spans[-1] = (start, end)
        elif end > start:
            self.spans[-1] = (prev_start, end)

    def build(self) -> FlatText:
        return FlatText("".join(self.chars), self.spans)


def flatten(source: str) -> FlatText:
    builder = _Builder()
    hidden_depth = 0
    for match in TOKEN_RE.finditer(source):
        token, start, end = match.group(0), match.start(), match.end()
        if is_tag(token):
            if token.startswith(("<!", "<?")):
                continue
            name = _tag_name(token)
            if name in HIDDEN_TAGS and not token.endswith("/>"):
                hidden_depth = max(hidden_depth + (-1 if token.startswith("</") else 1), 0)
            elif not hidden_depth and name in BLOCK_TAGS:
                builder.add_boundary(start)
            continue
        if hidden_depth:
            continue
        if token.startswith("&") and len(token) > 1:
            for char in html.unescape(token):
                builder.add(char, start, end)
            continue
        for offset, char in enumerate(token):
            builder.add(char, start + offset, start + offset + 1)
    return builder.build()


def find_unique(text: str, original: str, before: str = "", after: str = "") -> TextMatch:
    """Ignores whitespace: selections and context rarely agree on spacing at the joins"""
    positions = [i for i, c in enumerate(text) if c != " "]
    compact = "".join(text[i] for i in positions)

    def squash(s: str) -> str:
        return normalize(s).replace(" ", "")

    body, pre, post = squash(original), squash(before), squash(after)
    if not body:
        raise TextNotFound("empty selection")

    attempts = [("context", pre, post), ("context before", pre, ""),
                ("context after", "", post), ("text only", "", "")]
    ambiguous = False
    for method, head, tail in attempts:
        if method != "text only" and not (head or tail):
            continue
        needle = head + body + tail
        hits = [m.start() for m in re.finditer(re.escape(needle), compact)]
        if len(hits) == 1:
            first = hits[0] + len(head)
            last = first + len(body) - 1
            return TextMatch(positions[first], positions[last] + 1, method)
        ambiguous = ambiguous or len(hits) > 1
    raise TextNotFound("appears more than once" if ambiguous else "not found")
