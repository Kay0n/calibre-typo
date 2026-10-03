"""Needs LuaJIT, LuaSocket and dkjson, which the devenv shell provides"""

from __future__ import annotations

import io
import shutil
import sqlite3
import subprocess
import threading
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from waitress.server import create_server

from calibre_typo import create_app
from calibre_typo.config import Settings
from conftest import PLUGIN_DIR, add_device, csrf

HARNESS = Path(__file__).parent / "lua" / "harness.lua"


def lua_ready() -> bool:
    if not shutil.which("luajit"):
        return False
    probe = subprocess.run(["luajit", "-e", "require('socket.http'); require('dkjson')"],
                           capture_output=True)
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(not lua_ready(), reason="needs luajit with luasocket and dkjson")


@pytest.fixture
def redirector():
    """Like a proxy sending http:// to https://"""
    target = {}

    def app(environ, start_response):
        start_response("301 Moved Permanently", [("Location", target["url"] + environ["PATH_INFO"])])
        return [b""]

    server = create_server(app, host="127.0.0.1", port=0)
    threading.Thread(target=server.run, daemon=True).start()
    yield f"http://127.0.0.1:{server.effective_port}", target
    server.close()


@pytest.fixture
def live_server(tmp_path, library_dir):
    settings = Settings(library_dir=library_dir, data_dir=tmp_path / "data", plugin_dir=PLUGIN_DIR)
    app = create_app(settings)
    server = create_server(app, host="127.0.0.1", port=0)
    base_url = f"http://127.0.0.1:{server.effective_port}"
    # So the download points at this server
    state = app.extensions["calibre_typo"]
    state.settings = replace(settings, public_url=base_url)
    threading.Thread(target=server.run, daemon=True).start()
    yield app, settings
    server.close()


def test_plugin_end_to_end(tmp_path, live_server, redirector):
    app, settings = live_server
    redirect_url, redirect_target = redirector
    redirect_target["url"] = app.extensions["calibre_typo"].settings.public_url
    browser = app.test_client()
    browser.post("/setup", data={"csrf_token": csrf(browser),
                                 "password": "long enough password", "confirm": "long enough password"})
    device_id, _ = add_device(browser, "Harness")

    download = browser.get(f"/devices/{device_id}/plugin.zip")
    with zipfile.ZipFile(io.BytesIO(download.data)) as archive:
        archive.extractall(tmp_path / "plugins")
    settings_dir = tmp_path / "koreader-settings"
    settings_dir.mkdir()

    result = subprocess.run(
        ["luajit", str(HARNESS), str(tmp_path / "plugins" / "calibretypo.koplugin"), str(settings_dir),
         redirect_url],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stdout.strip().endswith("OK")

    rows = sqlite3.connect(settings.database_path).execute(
        "SELECT book_id, original, replacement, ctx_before, ctx_after FROM edits").fetchall()
    assert rows == [(1, "walked", "strolled", "A non-dead human ", " into the lobby")]
    assert b"<del>walked</del><ins>strolled</ins>" in browser.get("/books/1").data
