"""The S3 client and object layout shared by backup.py and restore.py.

Backups go to Cloudflare R2, which speaks the S3 API. Configuration comes
from the environment only (deploy/README.md, "Backups"):

    BACKUP_S3_BUCKET             the bucket; unset means backups are off
    BACKUP_S3_ENDPOINT           e.g. https://<account>.r2.cloudflarestorage.com
    BACKUP_S3_ACCESS_KEY_ID
    BACKUP_S3_SECRET_ACCESS_KEY
    BACKUP_S3_PREFIX             optional, default "backups"

One backup is two objects under one UTC timestamp:

    <prefix>/<YYYYMMDDTHHMMSSZ>/db.dump         pg_dump -Fc
    <prefix>/<YYYYMMDDTHHMMSSZ>/media.tar       the race logs (MEDIA_ROOT; already brotli)

db.dump is uploaded last, so a timestamp that has it is complete. Old
backups are expired by an R2 lifecycle rule, not by code.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone

DB_NAME = "db.dump"
MEDIA_NAME = "media.tar"
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
STAMP_RE = re.compile(r"^\d{8}T\d{6}Z$")


@dataclass(frozen=True)
class BackupConfig:
    bucket: str
    endpoint: str | None
    access_key_id: str | None
    secret_access_key: str | None
    prefix: str

    @classmethod
    def from_env(cls, env=None) -> BackupConfig | None:
        """The configuration, or None when backups are switched off."""
        env = os.environ if env is None else env
        bucket = env.get("BACKUP_S3_BUCKET", "").strip()
        if not bucket:
            return None
        return cls(
            bucket=bucket,
            endpoint=env.get("BACKUP_S3_ENDPOINT") or None,
            access_key_id=env.get("BACKUP_S3_ACCESS_KEY_ID") or None,
            secret_access_key=env.get("BACKUP_S3_SECRET_ACCESS_KEY") or None,
            prefix=env.get("BACKUP_S3_PREFIX", "backups").strip("/") or "backups",
        )

    def key(self, stamp: str, name: str) -> str:
        return f"{self.prefix}/{stamp}/{name}"


def make_client(config: BackupConfig):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=config.endpoint,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name="auto",
    )


def stamp_now(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime(STAMP_FORMAT)


def complete_stamps(client, config: BackupConfig) -> list[str]:
    """Every timestamp that has a database dump, oldest first."""
    stamps = set()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=config.bucket, Prefix=f"{config.prefix}/"):
        for obj in page.get("Contents", []):
            parts = obj["Key"][len(config.prefix) + 1 :].split("/")
            if len(parts) == 2 and parts[1] == DB_NAME and STAMP_RE.match(parts[0]):
                stamps.add(parts[0])
    return sorted(stamps)
