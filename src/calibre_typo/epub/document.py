from __future__ import annotations

import os
import posixpath
import re
import tempfile
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .patch import apply_patches, plan_patches
from .text import FlatText, TextNotFound, flatten, find_unique, normalize

PREVIEW_CONTEXT = 120

# KOReader xpointers: /body/DocFragment[n]/..., n being the spine position
_FRAGMENT_RE = re.compile(r"DocFragment\[(\d+)\]")
_ROOTFILE_RE = re.compile(r'full-path="([^"]+)"')
_ITEM_RE = re.compile(r"<(?:\w+:)?item\b[^>]*>")
_ITEMREF_RE = re.compile(r'<(?:\w+:)?itemref\b[^>]*\bidref="([^"]+)"')
_ATTR_RE = r'\b{}="([^"]+)"'


@dataclass(frozen=True)
class TextEdit:
    original: str
    replacement: str
    before: str = ""
    after: str = ""
    xpointer: str | None = None


@dataclass(frozen=True)
class Location:
    item: str
    start: int
    end: int
    method: str


@dataclass(frozen=True)
class Preview:
    location: Location
    current: str
    before: str
    after: str


class EditNotApplicable(Exception):
    pass


@dataclass
class _Chapter:
    source: str
    flat: FlatText


class EpubDocument:
    def __init__(self, path: Path):
        self.path = Path(path)
        with zipfile.ZipFile(self.path) as archive:
            self._entries = archive.infolist()
            self._data = {e.filename: archive.read(e.filename) for e in self._entries}
        self._changed: set[str] = set()
        self._chapters: dict[str, _Chapter] = {}
        self.spine = self._read_spine()

    def _read_spine(self) -> list[str]:
        container = self._data.get("META-INF/container.xml", b"").decode("utf-8", "replace")
        match = _ROOTFILE_RE.search(container)
        opf_path = match.group(1) if match else next((n for n in self._data if n.endswith(".opf")), None)
        if opf_path not in self._data:
            return sorted(n for n in self._data if n.endswith((".html", ".xhtml", ".htm")))

        opf = self._data[opf_path].decode("utf-8", "replace")
        base = posixpath.dirname(opf_path)
        manifest = {}
        for item in _ITEM_RE.finditer(opf):
            item_id = re.search(_ATTR_RE.format("id"), item.group(0))
            href = re.search(_ATTR_RE.format("href"), item.group(0))
            if item_id and href:
                path = posixpath.normpath(posixpath.join(base, urllib.parse.unquote(href.group(1))))
                manifest[item_id.group(1)] = path
        return [manifest[ref] for ref in _ITEMREF_RE.findall(opf)
                if manifest.get(ref) in self._data]

    def _chapter(self, item: str) -> _Chapter:
        if item not in self._chapters:
            source = self._data[item].decode("utf-8", "replace")
            self._chapters[item] = _Chapter(source, flatten(source))
        return self._chapters[item]

    def _set_source(self, item: str, source: str) -> None:
        self._data[item] = source.encode("utf-8")
        self._changed.add(item)
        self._chapters.pop(item, None)

    def _hinted_chapter(self, xpointer: str | None) -> str | None:
        match = _FRAGMENT_RE.search(xpointer or "")
        if match:
            index = int(match.group(1)) - 1
            if 0 <= index < len(self.spine):
                return self.spine[index]
        return None

    def locate(self, edit: TextEdit) -> Location:
        hinted = self._hinted_chapter(edit.xpointer)
        if hinted:
            try:
                match = self._find(hinted, edit)
                return Location(hinted, match.start, match.end, match.method)
            except TextNotFound:
                pass

        found, ambiguous = [], False
        for item in self.spine:
            try:
                found.append((item, self._find(item, edit)))
            except TextNotFound as err:
                ambiguous = ambiguous or "more than once" in str(err)
        if len(found) == 1:
            item, match = found[0]
            method = match.method if item == hinted else f"{match.method}, other chapter"
            return Location(item, match.start, match.end, method)
        if found or ambiguous:
            raise EditNotApplicable("Text appears more than once")
        raise EditNotApplicable("Text not found")

    def _find(self, item: str, edit: TextEdit):
        return find_unique(self._chapter(item).flat.text, edit.original, edit.before, edit.after)

    def preview(self, edit: TextEdit) -> Preview:
        location = self.locate(edit)
        text = self._chapter(location.item).flat.text
        return Preview(
            location=location,
            current=text[location.start:location.end],
            before=text[max(0, location.start - PREVIEW_CONTEXT):location.start],
            after=text[location.end:location.end + PREVIEW_CONTEXT],
        )

    def apply(self, edit: TextEdit) -> Location:
        location = self.locate(edit)
        chapter = self._chapter(location.item)
        patches = plan_patches(chapter.source, chapter.flat, location.start, location.end, edit.replacement)
        self._set_source(location.item, apply_patches(chapter.source, patches))

        expected = normalize(edit.replacement).replace(" ", "")
        if expected not in self._chapter(location.item).flat.text.replace(" ", ""):
            raise EditNotApplicable("Patched text doesn't match the fix")
        return location

    @property
    def has_changes(self) -> bool:
        return bool(self._changed)

    def save(self) -> None:
        if not self._changed:
            return
        # Temp file then swap, so a crash never leaves a half-written book
        fd, tmp = tempfile.mkstemp(prefix=".calibre-typo-", suffix=".epub", dir=self.path.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp, "w") as archive:
                # EPUB spec: mimetype first, uncompressed
                for entry in sorted(self._entries, key=lambda e: e.filename != "mimetype"):
                    info = zipfile.ZipInfo(entry.filename, date_time=entry.date_time)
                    info.external_attr = entry.external_attr
                    info.compress_type = (zipfile.ZIP_STORED if entry.filename == "mimetype"
                                          else zipfile.ZIP_DEFLATED)
                    archive.writestr(info, self._data[entry.filename])
            os.chmod(tmp, self.path.stat().st_mode & 0o777)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        self._changed.clear()
