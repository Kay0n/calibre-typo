from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flask import current_app

if TYPE_CHECKING:
    from .config import Settings
    from .db import Database
    from .library import CalibreLibrary
    from .web.issued import IssuedTokens
    from .web.throttle import Throttle

EXTENSION_KEY = "calibre_typo"


@dataclass
class AppState:
    settings: Settings
    db: Database
    library: CalibreLibrary
    plugin_version: str
    login_throttle: Throttle
    issued_tokens: IssuedTokens


def get_state() -> AppState:
    return current_app.extensions[EXTENSION_KEY]
