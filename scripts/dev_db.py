#!/usr/bin/env python
"""Create or drop this checkout's development database.

`manage.py migrate` needs the database to exist already — it creates tables,
not databases. In a fresh worktree there is nothing to migrate into, and the
error Postgres gives ("database ... does not exist") looks like a
misconfiguration rather than a missing step.

Usage, from the root of any checkout:

    .venv/bin/python scripts/dev_db.py            # create if missing
    .venv/bin/python scripts/dev_db.py --drop     # delete it, and its test database

`--drop` is for tidying up a worktree once its branch is in review: it removes
this worktree's database so finished work does not leave databases behind. It
refuses to run in the main checkout, where the database is the one you actually
use, unless you pass `--force`.

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

from config.worktree import (  # noqa: E402
    database_name,
    runserver_port,
    test_database_name,
    worktree_name,
)


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


def drop(cursor, name: str) -> bool:
    """Drop `name` if it is there. Returns whether anything was dropped.

    WITH (FORCE) disconnects anything still attached — a dev server that was
    not stopped cleanly, or a psql left open — rather than failing with
    "database is being accessed by other users". Postgres 13+.
    """
    if not exists(cursor, name):
        return False
    cursor.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Delete this checkout's development and test databases.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow --drop in the main checkout. You almost never want this.",
    )
    args = parser.parse_args()

    name = os.environ.get("POSTGRES_DB") or database_name()

    if args.drop and worktree_name() is None and not args.force:
        print(
            f"Refusing to drop {name}: this is the main checkout, not a worktree.\n"
            "That is the database you work in day to day. Pass --force if you "
            "really mean it.",
            file=sys.stderr,
        )
        return 2

    try:
        connection = connect_to_maintenance_db()
    except psycopg2.OperationalError as error:
        print(f"Cannot reach Postgres: {error}", file=sys.stderr)
        print("Is it running? `docker compose up -d`", file=sys.stderr)
        return 1

    # Not `with connection, ...`: psycopg2's connection context manager wraps
    # the block in a transaction on __enter__ (committing or rolling back on
    # exit), which overrides the autocommit mode CREATE DATABASE needs —
    # Postgres refuses to run it inside a transaction block. Autocommit alone
    # is both necessary and sufficient here; the connection is closed
    # implicitly when the process exits.
    with connection.cursor() as cursor:
        if args.drop:
            for target in (name, test_database_name()):
                print(f"Dropped {target}." if drop(cursor, target) else f"{target} was not there.")
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
