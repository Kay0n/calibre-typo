"""Run the server, or reset the admin password"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys

from .config import Settings
from .db import Database
from .services import admin


def serve(settings: Settings) -> None:
    from waitress import serve as waitress_serve

    from . import create_app

    app = create_app(settings)
    logging.getLogger(__name__).info(
        "Serving on http://%s:%d (library: %s)", settings.host, settings.port, settings.library_dir)
    waitress_serve(app, host=settings.host, port=settings.port, threads=8, ident="calibre-typo")


def reset_password(settings: Settings) -> int:
    password = getpass.getpass("New admin password (empty turns off login): ")
    if password != getpass.getpass("Repeat it: "):
        print("Passwords don't match", file=sys.stderr)
        return 1
    database = Database(settings.database_path)
    database.migrate()
    with database.connect() as conn:
        admin.set_password(conn, password)
    print("Password changed. All browsers are logged out." if password else "Login turned off.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="calibre-typo", description=__doc__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="run the web server (default)")
    commands.add_parser("reset-password", help="set a new admin password")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    if args.command == "reset-password":
        return reset_password(settings)
    serve(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
