"""Usage: python tests/sample_library.py <directory>"""

from __future__ import annotations

import sqlite3
import sys
import zipfile
from pathlib import Path

BOOK_UUID = "6fa81348-e5ed-4237-b55d-5f94d1490e19"

CHAPTERS = {
    "text/ch1.xhtml": """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>One</title>
<style>p { margin: 0 }</style></head><body>
<h1>Chapter One</h1>
<p>It was asking me why I was here. I replied <i>query: identify,</i> and attached an image.</p>
<p>A non-dead human walked into the lobby, one of the hostel supervisors.</p>
<p>Fish &amp; chips were   served at noon.</p>
</body></html>""",
    "text/ch2.xhtml": """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Two</title></head><body>
<p>The the ship was quiet.</p>
<p>Later, the the ship was loud.</p>
<p>She said hello.</p>
</body></html>""",
}


def make_epub(path: Path, chapters: dict[str, str] = CHAPTERS) -> None:
    manifest = "".join(f'<item id="c{i}" href="{name.removeprefix("OEBPS/")}" media-type="application/xhtml+xml"/>'
                       for i, name in enumerate(chapters))
    spine = "".join(f'<itemref idref="c{i}"/>' for i in range(len(chapters)))
    opf = f"""<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier>calibre:{BOOK_UUID}</dc:identifier></metadata>
<manifest>{manifest}</manifest><spine>{spine}</spine></package>"""
    container = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        for name, body in chapters.items():
            z.writestr(f"OEBPS/{name}", body)


def make_library(root: Path) -> None:
    """Its title_sort() trigger exercises the stand-ins in library.py"""
    conn = sqlite3.connect(root / "metadata.db")
    conn.executescript("""
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, sort TEXT, path TEXT, uuid TEXT,
                            last_modified TEXT);
        CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_authors_link (id INTEGER PRIMARY KEY, book INTEGER, author INTEGER);
        CREATE TABLE data (id INTEGER PRIMARY KEY, book INTEGER, format TEXT, uncompressed_size INTEGER,
                           name TEXT);
        CREATE TRIGGER books_update_trg AFTER UPDATE ON books BEGIN
            UPDATE books SET sort = title_sort(NEW.title) WHERE id = NEW.id AND OLD.title <> NEW.title;
        END;
    """)
    books = [
        (1, "Fugitive Telemetry", "Martha Wells/Fugitive Telemetry (1)", BOOK_UUID, "Martha Wells"),
        (2, "Golden Son", "Pierce Brown/Golden Son (2)", "5917080b-8d57-4e74-ae37-ee9fdba1a0b1", "Pierce Brown"),
    ]
    for book_id, title, path, uuid, author in books:
        conn.execute("INSERT INTO books (id, title, sort, path, uuid) VALUES (?, ?, ?, ?, ?)",
                     (book_id, title, title, path, uuid))
        conn.execute("INSERT INTO authors (id, name) VALUES (?, ?)", (book_id, author))
        conn.execute("INSERT INTO books_authors_link (book, author) VALUES (?, ?)", (book_id, book_id))
        name = f"{title} - {author}"
        conn.execute("INSERT INTO data (book, format, uncompressed_size, name) VALUES (?, 'EPUB', 0, ?)",
                     (book_id, name))
        (root / path).mkdir(parents=True)
        make_epub(root / path / f"{name}.epub")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "library")
    if (target / "metadata.db").exists():
        sys.exit(f"{target} already has a library")
    target.mkdir(parents=True, exist_ok=True)
    make_library(target)
    print(f"Sample library created in {target}")
