"""Operator command line, run inside the container.

    docker exec myastroshine-api python -m app.cli reset-admin

``reset-admin`` forgets the admin password and logs every admin browser out; the
next visit to Settings asks for a new password. It is the way back in when the
password is lost - deliberately a command on the host, not a web route or an
environment variable: whoever can run it already controls the container.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from app.config import get_settings
from app.db import database
from app.db.database import init_db
from app.logging_config import configure_logging, get_logger
from app.services.admin_auth import AdminAuthService

logger = get_logger(__name__)


def _reset_admin() -> int:
    init_db()
    with database.SessionLocal() as db:
        AdminAuthService(db).reset()
    logger.warning(
        "admin password cleared - open Settings in the web UI to set a new one",
        data_dir=str(get_settings().data_dir),
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("reset-admin", help="forget the admin password and every admin login")
    args = parser.parse_args(argv)

    configure_logging()
    if args.command == "reset-admin":
        return _reset_admin()
    return 2  # pragma: no cover - argparse rejects unknown commands first


if __name__ == "__main__":
    raise SystemExit(main())  # pragma: no cover - exercised through main()
