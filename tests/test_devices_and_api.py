from __future__ import annotations

import io
import re
import sqlite3
import time
import zipfile
from dataclasses import replace

from calibre_typo.services.plugin_bundle import render_config
from conftest import add_device, csrf, shown_token
from sample_library import BOOK_UUID

FIX = {
    "uid": "fix-1",
    "title": "Fugitive Telemetry",
    "authors": "Martha Wells",
    "identifiers": f"calibre:{BOOK_UUID}",
    "xpointer": "/body/DocFragment[1]/body/p[2]/text().0",
    "original": "walked",
    "replacement": "strolled",
    "context_before": "A non-dead human",
    "context_after": "into the lobby",
}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Calibre-Typo-Plugin": "0.1.0"}


def test_plugin_download_is_preconfigured(admin_client):
    device_id, token = add_device(admin_client, "My Kindle")
    response = admin_client.get(f"/devices/{device_id}/plugin.zip")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.data)) as z:
        names = z.namelist()
        config = z.read("calibretypo.koplugin/calibretypo/config.lua").decode()
    assert "calibretypo.koplugin/main.lua" in names
    assert "calibretypo.koplugin/calibretypo/sync.lua" in names
    assert f'token = "{token}"' in config
    assert 'server = "http://localhost"' in config


def test_issued_token_stays_out_of_the_cookie(admin_client):
    _, token = add_device(admin_client)
    with admin_client.session_transaction() as session:
        assert token not in str(dict(session))


def test_download_link_expires(app, admin_client, monkeypatch):
    device_id, _ = add_device(admin_client)
    assert admin_client.get(f"/devices/{device_id}/plugin.zip").status_code == 200

    later = time.monotonic() + 30 * 60 + 1
    monkeypatch.setattr("calibre_typo.web.issued.time.monotonic", lambda: later)
    assert admin_client.get(f"/devices/{device_id}/plugin.zip").status_code == 302
    assert b"Download expired" in admin_client.get(f"/devices/{device_id}/install").data


def test_download_link_belongs_to_the_session(app, admin_client):
    device_id, _ = add_device(admin_client)
    with admin_client.session_transaction() as session:
        session.pop("issued_ticket")
    assert admin_client.get(f"/devices/{device_id}/plugin.zip").status_code == 302


def test_tokens_are_short_and_forgiving_to_type(admin_client, client):
    _, token = add_device(admin_client)
    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{4}){3}", token)
    sloppy = token.replace("-", " ").lower().replace("0", "o").replace("1", "l")
    assert client.get("/api/v1/ping", headers=bearer(sloppy)).status_code == 200


def test_api_requires_a_valid_token(client):
    assert client.get("/api/v1/ping").status_code == 401
    assert client.get("/api/v1/ping", headers=bearer("ctd_nope")).status_code == 401


def test_ping_records_the_device(admin_client, client):
    _, token = add_device(admin_client, "Phone")
    reply = client.get("/api/v1/ping", headers=bearer(token)).get_json()
    assert reply["device"] == "Phone"
    assert reply["plugin_version"]
    assert b"0.1.0" in admin_client.get("/devices/").data


def test_only_revoked_devices_get_a_new_token(admin_client, client):
    device_id, old = add_device(admin_client)
    reactivate = f"/devices/{device_id}/reactivate"

    admin_client.post(reactivate, data={"csrf_token": csrf(admin_client)})
    assert client.get("/api/v1/ping", headers=bearer(old)).status_code == 200

    admin_client.post(f"/devices/{device_id}/revoke", data={"csrf_token": csrf(admin_client)})
    assert client.get("/api/v1/ping", headers=bearer(old)).status_code == 401

    admin_client.post(reactivate, data={"csrf_token": csrf(admin_client)})
    new = shown_token(admin_client, device_id)
    assert new != old
    assert client.get("/api/v1/ping", headers=bearer(old)).status_code == 401
    assert client.get("/api/v1/ping", headers=bearer(new)).status_code == 200


def test_submitting_is_idempotent(admin_client, client, settings):
    _, token = add_device(admin_client)
    for _ in range(2):
        reply = client.post("/api/v1/edits", json={"edits": [FIX]}, headers=bearer(token)).get_json()
        assert reply["accepted"] == ["fix-1"]
    conn = sqlite3.connect(settings.database_path)
    assert conn.execute("SELECT count(*), book_id FROM edits").fetchone() == (1, 1)


def test_malformed_submission(admin_client, client):
    _, token = add_device(admin_client)
    assert client.post("/api/v1/edits", json={"nope": 1}, headers=bearer(token)).status_code == 400
    reply = client.post("/api/v1/edits", json={"edits": [{"uid": "x"}, "junk"]}, headers=bearer(token))
    assert reply.get_json()["accepted"] == []


def test_review_and_apply(admin_client, client, settings, epub_path):
    _, token = add_device(admin_client)
    client.post("/api/v1/edits", json={"edits": [FIX]}, headers=bearer(token))

    page = admin_client.get("/books/1")
    assert b"<del>walked</del><ins>strolled</ins>" in page.data
    assert b"matched by context" in page.data

    edit_id = sqlite3.connect(settings.database_path).execute("SELECT id FROM edits").fetchone()[0]
    response = admin_client.post("/books/1", data={"csrf_token": csrf(admin_client),
                                                   f"decision-{edit_id}": "approve"},
                                 follow_redirects=True)
    assert b"Applied 1 fix" in response.data

    with zipfile.ZipFile(epub_path) as z:
        assert "A non-dead human strolled into the lobby" in z.read("OEBPS/text/ch1.xhtml").decode()
    assert len(list((settings.backups_dir / "1").glob("*.epub"))) == 1


def test_edited_replacement_and_reject(admin_client, client, settings, epub_path):
    _, token = add_device(admin_client)
    second = dict(FIX, uid="fix-2", original="She said hello.", replacement="She said hi.",
                  context_before="", context_after="")
    client.post("/api/v1/edits", json={"edits": [FIX, second]}, headers=bearer(token))
    ids = [r[0] for r in sqlite3.connect(settings.database_path).execute("SELECT id FROM edits ORDER BY id")]

    admin_client.post("/books/1", data={
        "csrf_token": csrf(admin_client),
        f"decision-{ids[0]}": "reject",
        f"decision-{ids[1]}": "approve", f"replacement-{ids[1]}": "She said goodbye.",
    })
    source = zipfile.ZipFile(epub_path).read("OEBPS/text/ch2.xhtml").decode()
    assert "She said goodbye." in source
    statuses = dict(sqlite3.connect(settings.database_path).execute("SELECT uid, status FROM edits"))
    assert statuses == {"fix-1": "rejected", "fix-2": "applied"}


def test_unmatched_fix_can_be_assigned(admin_client, client, settings):
    _, token = add_device(admin_client)
    stray = dict(FIX, uid="stray", title="Some Web Novel", identifiers="", authors="Anon")
    client.post("/api/v1/edits", json={"edits": [stray]}, headers=bearer(token))
    books = admin_client.get("/").data
    assert b"1 fix not matched to a book" in books
    assert b"No fixes yet" not in books
    assert b"A non-dead human" in admin_client.get("/unmatched").data

    edit_id = sqlite3.connect(settings.database_path).execute("SELECT id FROM edits").fetchone()[0]
    admin_client.post("/unmatched", data={"csrf_token": csrf(admin_client), f"book-{edit_id}": "1"})
    assert b"strolled" in admin_client.get("/books/1").data


def test_unmatched_page_suggests_similar_titles(admin_client, client):
    _, token = add_device(admin_client)
    stray = dict(FIX, uid="stray", title="Fugitive Telemetry (web edition)", identifiers="")
    client.post("/api/v1/edits", json={"edits": [stray]}, headers=bearer(token))
    page = admin_client.get("/unmatched").get_data(as_text=True)
    suggested = page[page.index('label="Suggested"'):page.index('label="All books"')]
    assert "Fugitive Telemetry" in suggested and "Golden Son" not in suggested


def test_install_page_warns_without_a_public_url(app, admin_client):
    device_id, _ = add_device(admin_client)
    assert b"CALIBRE_TYPO_PUBLIC_URL</code> isn't set" in admin_client.get(f"/devices/{device_id}/install").data

    state = app.extensions["calibre_typo"]
    state.settings = replace(state.settings, public_url="https://typo.example.com")
    page = admin_client.get(f"/devices/{device_id}/install").data
    assert b"isn't set" not in page
    assert b"https://typo.example.com" in page


def test_a_malformed_fix_doesnt_block_the_rest_of_the_batch(admin_client, client):
    _, token = add_device(admin_client)
    bad = dict(FIX, uid="bad", title=["not", "text"], created_at={"x": 1})
    reply = client.post("/api/v1/edits", json={"edits": [bad, dict(FIX, uid="good")]}, headers=bearer(token))
    assert reply.status_code == 200
    assert reply.get_json()["accepted"] == ["bad", "good"]


def test_revoked_device_no_longer_offers_its_download(admin_client):
    device_id, token = add_device(admin_client)
    admin_client.post(f"/devices/{device_id}/revoke", data={"csrf_token": csrf(admin_client)})
    assert admin_client.get(f"/devices/{device_id}/plugin.zip").status_code == 302
    assert token.encode() not in admin_client.get(f"/devices/{device_id}/install").data


def test_device_names_with_control_characters_keep_the_config_valid():
    config = render_config("http://x", "ctd_t", 'a\rb"\\\n1')
    assert "\r" not in config and r'device_name = "a\013b\"\\\0101",' in config


def test_fixes_for_a_deleted_book_return_to_unmatched(admin_client, client, settings, library_dir):
    _, token = add_device(admin_client)
    client.post("/api/v1/edits", json={"edits": [FIX]}, headers=bearer(token))
    with sqlite3.connect(library_dir / "metadata.db") as conn:
        conn.execute("DELETE FROM books WHERE id = 1")
    assert b"1 fix not matched to a book" in admin_client.get("/").data


def test_fixes_cant_be_assigned_to_a_made_up_book(admin_client, client, settings):
    _, token = add_device(admin_client)
    client.post("/api/v1/edits", json={"edits": [dict(FIX, identifiers="", title="Nope")]}, headers=bearer(token))
    edit_id = sqlite3.connect(settings.database_path).execute("SELECT id FROM edits").fetchone()[0]
    admin_client.post("/unmatched", data={"csrf_token": csrf(admin_client), f"book-{edit_id}": "999"})
    assert sqlite3.connect(settings.database_path).execute("SELECT book_id FROM edits").fetchone()[0] is None


def test_missing_library_gives_a_clear_error(admin_client, client, library_dir):
    _, token = add_device(admin_client)
    (library_dir / "metadata.db").rename(library_dir / "elsewhere.db")
    page = admin_client.get("/")
    assert page.status_code == 503 and b"No Calibre library at" in page.data
    assert client.post("/api/v1/edits", json={"edits": [FIX]}, headers=bearer(token)).status_code == 503
