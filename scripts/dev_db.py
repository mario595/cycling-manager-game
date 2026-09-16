#!/usr/bin/env python
"""Create this checkout's development database if it is not there yet.

`manage.py migrate` needs the database to exist already — it creates tables,
not databases. In a fresh worktree there is nothing to migrate into, and the
error Postgres gives ("database ... does not exist") looks like a
misconfiguration rather than a missing step.

Test databases need nothing from this script: Django builds and drops
`test_*` itself.

Usage, from the root of any checkout:

    .venv/bin/python scripts/dev_db.py           # create if missing
    .venv/bin/python scripts/dev_db.py --drop    # delete it (data is lost)

Connection details come from the same environment variables as
`config/settings/base.py`, with the same defaults.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2  # noqa: E402
from psycopg2 import sql  # noqa: E402
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT  # noqa: E402

from config.worktree import database_name, runserver_port, worktree_name  # noqa: E402


def connect_to_maintenance_db():
    """Connect to the always-present `postgres` database.

    CREATE DATABASE cannot run from inside the database being created, and it
    cannot run inside a transaction — hence autocommit.
    """
    connection = psycopg2.connect(
        dbname="postgres",
        user=os.environ.get("POSTGRES_USER", "cycling"),
        password=os.environ.get("POSTGRES_PASSWORD", "cycling"),
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=os.environ.get("POSTGRES_PORT", "5433"),
    )
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return connection


def exists(cursor, name: str) -> bool:
    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
    return cursor.fetchone() is not None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Delete this checkout's development database instead of creating it.",
    )
    args = parser.parse_args()

    name = os.environ.get("POSTGRES_DB") or database_name()

    try:
        connection = connect_to_maintenance_db()
    except psycopg2.OperationalError as error:
        print(f"Cannot reach Postgres: {error}", file=sys.stderr)
        print("Is it running? `docker compose up -d`", file=sys.stderr)
        return 1

    with connection, connection.cursor() as cursor:
        if args.drop:
            if not exists(cursor, name):
                print(f"{name} does not exist; nothing to drop.")
                return 0
            cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            print(f"Dropped {name}.")
            return 0

        if exists(cursor, name):
            print(f"{name} already exists.")
        else:
            cursor.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(name),
                    sql.Identifier(os.environ.get("POSTGRES_USER", "cycling")),
                )
            )
            print(f"Created {name}.")

    print(f"worktree: {worktree_name() or '(main checkout)'}   port: {runserver_port()}")
    print("Next: manage.py migrate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
