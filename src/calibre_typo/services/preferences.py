from __future__ import annotations

import sqlite3

from ..db import get_setting, set_setting

_AUTO_APPLY_KEY = "auto_apply"


def auto_apply_enabled(conn: sqlite3.Connection) -> bool:
    return get_setting(conn, _AUTO_APPLY_KEY) == "1"


def set_auto_apply(conn: sqlite3.Connection, enabled: bool) -> None:
    set_setting(conn, _AUTO_APPLY_KEY, "1" if enabled else "0")
