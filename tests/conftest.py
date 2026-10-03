from __future__ import annotations

import re
from pathlib import Path

import pytest

from calibre_typo import create_app
from calibre_typo.config import Settings
from sample_library import make_library

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "koreader" / "calibretypo.koplugin"
ADMIN_PASSWORD = "correct horse battery"


@pytest.fixture
def library_dir(tmp_path: Path) -> Path:
    root = tmp_path / "library"
    root.mkdir()
    make_library(root)
    return root


@pytest.fixture
def epub_path(library_dir: Path) -> Path:
    return library_dir / "Martha Wells/Fugitive Telemetry (1)/Fugitive Telemetry - Martha Wells.epub"


@pytest.fixture
def settings(tmp_path: Path, library_dir: Path) -> Settings:
    return Settings(library_dir=library_dir, data_dir=tmp_path / "data", plugin_dir=PLUGIN_DIR)


@pytest.fixture
def app(settings: Settings):
    app = create_app(settings)
    app.config.update(TESTING=True)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client) -> str:
    """Loading a page puts a CSRF token in the session"""
    client.get("/devices/", follow_redirects=True)  # a form in every state: setup, login or devices
    with client.session_transaction() as session:
        return session["csrf_token"]


@pytest.fixture
def admin_client(app, client):
    response = client.post("/setup", data={"csrf_token": csrf(client),
                                           "password": ADMIN_PASSWORD, "confirm": ADMIN_PASSWORD})
    assert response.status_code == 302
    return client


def add_device(client, name: str = "Kindle") -> tuple[int, str]:
    response = client.post("/devices/", data={"csrf_token": csrf(client), "name": name})
    device_id = int(response.headers["Location"].rstrip("/").split("/")[-2])
    return device_id, shown_token(client, device_id)


def shown_token(client, device_id: int) -> str:
    page = client.get(f"/devices/{device_id}/install").get_data(as_text=True)
    return re.search(r'<code class="token">([^<]+)</code>', page).group(1)
