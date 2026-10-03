from __future__ import annotations

import logging
from datetime import timedelta

from flask import Flask

from . import web
from .config import Settings
from .db import Database
from .library import CalibreLibrary
from .services import admin, plugin_bundle
from .state import EXTENSION_KEY, AppState
from .web.issued import IssuedTokens
from .web.throttle import Throttle

__version__ = "0.1.0"

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.from_env()
    database = Database(settings.database_path)
    database.migrate()

    library = CalibreLibrary(settings.library_dir)
    if not library.metadata_path.is_file():
        log.warning("No Calibre library at %s (metadata.db not found)", settings.library_dir)

    with database.connect() as conn:
        secret = admin.session_secret(conn)
        if not admin.is_set_up(conn):
            log.warning("No admin password yet: open the web page to choose one.")
        elif admin.login_disabled(conn):
            log.warning("Login is off: anyone who can reach the web app can use it.")

    state = AppState(
        settings=settings,
        db=database,
        library=library,
        plugin_version=plugin_bundle.plugin_version(settings.plugin_dir),
        login_throttle=Throttle(),
        issued_tokens=IssuedTokens(),
    )

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=secret,
        SESSION_COOKIE_NAME="calibre_typo_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=admin.SESSION_DAYS),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    )
    app.extensions[EXTENSION_KEY] = state
    web.register(app)
    return app
