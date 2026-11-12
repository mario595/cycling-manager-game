"""Nightly off-box backup: the database and the race logs, to R2.

Run by the scheduler (deploy/crontab) as `python -m deploy.backup`.

- With no BACKUP_S3_BUCKET it says backups are off and exits 0: an image
  without an R2 account still runs.
- Any failure exits non-zero, which supercronic reports to Sentry.

See deploy/s3.py for the layout and deploy/README.md for setup and restore.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from deploy.s3 import DB_NAME, MEDIA_NAME, BackupConfig, make_client, stamp_now


def dump_database(target: Path, env=None) -> None:
    env = os.environ if env is None else env
    subprocess.run(
        [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--host", env.get("POSTGRES_HOST", "127.0.0.1"),
            "--port", env.get("POSTGRES_PORT", "5432"),
            "--username", env["POSTGRES_USER"],
            "--dbname", env["POSTGRES_DB"],
            "--file", str(target),
        ],
        env={**env, "PGPASSWORD": env["POSTGRES_PASSWORD"]},
        check=True,
    )


def archive_media(media_root: Path, target: Path) -> None:
    # Uncompressed: the race logs are already brotli-compressed.
    with tarfile.open(target, "w") as tar:
        if media_root.exists():
            tar.add(media_root, arcname=".")


def run_backup(client=None, env=None, stamp: str | None = None) -> str | None:
    """Take one backup. Returns its timestamp, or None when backups are off."""
    env = os.environ if env is None else env
    config = BackupConfig.from_env(env)
    if config is None:
        print("backups off: BACKUP_S3_BUCKET is not set")
        return None
    client = client or make_client(config)
    stamp = stamp or stamp_now()
    media_root = Path(env.get("DJANGO_MEDIA_ROOT", "/data/media"))

    with tempfile.TemporaryDirectory() as tmp:
        db_file = Path(tmp) / DB_NAME
        media_file = Path(tmp) / MEDIA_NAME
        dump_database(db_file, env)
        archive_media(media_root, media_file)
        # Media first, the dump last: a timestamp with a dump is complete.
        client.upload_file(str(media_file), config.bucket, config.key(stamp, MEDIA_NAME))
        client.upload_file(str(db_file), config.bucket, config.key(stamp, DB_NAME))

    print(f"backup {stamp} uploaded to {config.bucket}/{config.prefix}/{stamp}/")
    return stamp


def main() -> int:
    try:
        run_backup()
    except Exception as exc:  # noqa: BLE001 - report anything, then fail loudly
        print(f"backup FAILED: {exc!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
