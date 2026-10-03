from __future__ import annotations

import difflib
import html
from dataclasses import dataclass

from .text import TOKEN_RE, FlatText, is_tag, normalize


@dataclass(frozen=True)
class Patch:
    start: int
    end: int
    text: str


def plan_patches(source: str, flat: FlatText, start: int, end: int, replacement: str) -> list[Patch]:
    """Per-character diff, keeping tags inside changed text, so italics survive a fix"""
    current = flat.text[start:end]
    wanted = normalize(replacement)
    matcher = difflib.SequenceMatcher(None, current, wanted, autojunk=False)
    patches = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        new_text = html.escape(wanted[j1:j2], quote=False)
        first, last = start + i1, start + i2
        if op == "insert":
            # Attach to the preceding character, so a comma after an italic word stays inside it
            pos = flat.spans[first - 1][1] if first > 0 else flat.spans[first][0]
            patches.append(Patch(pos, pos, new_text))
            continue
        src_start, src_end = flat.spans[first][0], flat.spans[last - 1][1]
        if src_start >= src_end:
            # Only virtual spaces: no source to remove
            if new_text:
                patches.append(Patch(src_start, src_start, new_text))
            continue
        kept_tags = "".join(t for t in TOKEN_RE.findall(source[src_start:src_end]) if is_tag(t))
        patches.append(Patch(src_start, src_end, new_text + kept_tags))
    return patches


def apply_patches(source: str, patches: list[Patch]) -> str:
    # Back to front, so earlier offsets stay valid
    for patch in sorted(patches, key=lambda p: p.start, reverse=True):
        source = source[:patch.start] + patch.text + source[patch.end:]
    return source
