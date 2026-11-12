"""Restore a backup taken by deploy/backup.py. Never scheduled.

    python -m deploy.restore --list
    python -m deploy.restore latest --yes
    python -m deploy.restore 20261112T033000Z --yes

It replaces the database's contents (pg_restore --clean) and unpacks the race
logs over MEDIA_ROOT. Run it at a quiet moment, not on the hour when the tick
runs. The step-by-step, including rehearsing on a laptop, is in
deploy/README.md, "Restoring a backup".
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from deploy.s3 import DB_NAME, MEDIA_NAME, BackupConfig, complete_stamps, make_client


def resolve_stamp(requested: str, stamps: list[str]) -> str:
    if not stamps:
        raise SystemExit("no complete backups found")
    if requested == "latest":
        return stamps[-1]
    if requested not in stamps:
        raise SystemExit(f"no complete backup {requested!r}; have: {', '.join(stamps[-5:])}")
    return requested


def restore_database(dump: Path, env=None) -> None:
    env = os.environ if env is None else env
    subprocess.run(
        [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--single-transaction",
            "--host", env.get("POSTGRES_HOST", "127.0.0.1"),
            "--port", env.get("POSTGRES_PORT", "5432"),
            "--username", env["POSTGRES_USER"],
            "--dbname", env["POSTGRES_DB"],
            str(dump),
        ],
        env={**env, "PGPASSWORD": env["POSTGRES_PASSWORD"]},
        check=True,
    )


def restore_media(archive: Path, media_root: Path) -> None:
    media_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tar:
        tar.extractall(media_root, filter="data")


def run_restore(requested: str, client=None, env=None) -> str:
    env = os.environ if env is None else env
    config = BackupConfig.from_env(env)
    if config is None:
        raise SystemExit("BACKUP_S3_BUCKET is not set; nothing to restore from")
    client = client or make_client(config)
    stamp = resolve_stamp(requested, complete_stamps(client, config))
    media_root = Path(env.get("DJANGO_MEDIA_ROOT", "/data/media"))

    with tempfile.TemporaryDirectory() as tmp:
        db_file = Path(tmp) / DB_NAME
        media_file = Path(tmp) / MEDIA_NAME
        client.download_file(config.bucket, config.key(stamp, DB_NAME), str(db_file))
        client.download_file(config.bucket, config.key(stamp, MEDIA_NAME), str(media_file))
        restore_database(db_file, env)
        restore_media(media_file, media_root)

    print(f"restored backup {stamp}")
    return stamp


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stamp", nargs="?", help="'latest' or a backup timestamp")
    parser.add_argument("--list", action="store_true", help="list complete backups and exit")
    parser.add_argument("--yes", action="store_true", help="confirm: this replaces the live data")
    args = parser.parse_args(argv)

    if args.list:
        config = BackupConfig.from_env()
        if config is None:
            raise SystemExit("BACKUP_S3_BUCKET is not set")
        for stamp in complete_stamps(make_client(config), config):
            print(stamp)
        return 0
    if not args.stamp:
        parser.error("give a timestamp or 'latest' (or --list)")
    if not args.yes:
        parser.error("restoring replaces the live database and race logs; pass --yes")
    run_restore(args.stamp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
