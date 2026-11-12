"""Backup and restore logic (deploy/backup.py, restore.py, s3.py).

pg_dump/pg_restore and S3 are stubbed; the real round trip is verified by
hand against a local S3, as deploy/README.md describes.
"""

from __future__ import annotations

import subprocess
import tarfile
from pathlib import Path
from unittest import mock

import pytest

from deploy import backup, restore
from deploy.s3 import BackupConfig, complete_stamps

ENV = {
    "BACKUP_S3_BUCKET": "cm-backups",
    "POSTGRES_DB": "cm",
    "POSTGRES_USER": "cm",
    "POSTGRES_PASSWORD": "pw",
}


class FakeS3:
    """Just enough of boto3's S3 client: upload, download, list."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def upload_file(self, filename, bucket, key):
        self.objects[key] = Path(filename).read_bytes()

    def download_file(self, bucket, key, filename):
        Path(filename).write_bytes(self.objects[key])

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        fake = self

        class Paginator:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [{"Key": k} for k in fake.objects if k.startswith(Prefix)]}

        return Paginator()


def fake_pg_dump(args, **kwargs):
    Path(args[args.index("--file") + 1]).write_bytes(b"PGDMP fake")
    return subprocess.CompletedProcess(args, 0)


def test_backups_are_off_without_a_bucket(capsys):
    assert backup.run_backup(client=FakeS3(), env={}) is None
    assert "backups off" in capsys.readouterr().out


def test_a_backup_is_a_dump_and_a_media_archive_under_one_stamp(tmp_path):
    media = tmp_path / "media" / "race_logs"
    media.mkdir(parents=True)
    (media / "1.jsonl.br").write_bytes(b"log")
    s3 = FakeS3()

    with mock.patch("deploy.backup.subprocess.run", side_effect=fake_pg_dump) as run:
        stamp = backup.run_backup(
            client=s3, env={**ENV, "DJANGO_MEDIA_ROOT": str(tmp_path / "media")},
            stamp="20261112T033000Z",
        )

    assert stamp == "20261112T033000Z"
    assert set(s3.objects) == {
        "backups/20261112T033000Z/db.dump",
        "backups/20261112T033000Z/media.tar.gz",
    }
    assert run.call_args.kwargs["env"]["PGPASSWORD"] == "pw"
    assert "--format=custom" in run.call_args.args[0]


def test_the_dump_is_uploaded_last_so_a_stamp_with_it_is_complete(tmp_path):
    s3 = FakeS3()
    with mock.patch("deploy.backup.subprocess.run", side_effect=fake_pg_dump):
        backup.run_backup(client=s3, env={**ENV, "DJANGO_MEDIA_ROOT": str(tmp_path)}, stamp="20261112T033000Z")

    assert list(s3.objects)[-1].endswith("db.dump")


def test_a_failed_dump_fails_the_job_and_uploads_nothing(tmp_path, capsys):
    s3 = FakeS3()
    failure = subprocess.CalledProcessError(1, ["pg_dump"])
    with mock.patch.dict("os.environ", {**ENV, "DJANGO_MEDIA_ROOT": str(tmp_path)}, clear=True), \
            mock.patch("deploy.backup.subprocess.run", side_effect=failure), \
            mock.patch("deploy.backup.make_client", return_value=s3):
        assert backup.main() == 1

    assert s3.objects == {}
    assert "backup FAILED" in capsys.readouterr().err


def test_the_prefix_is_configurable():
    config = BackupConfig.from_env({**ENV, "BACKUP_S3_PREFIX": "/staging/"})
    assert config.key("20261112T033000Z", "db.dump") == "staging/20261112T033000Z/db.dump"


def test_only_stamps_with_a_dump_count_as_complete():
    s3 = FakeS3()
    s3.objects = {
        "backups/20261110T033000Z/media.tar.gz": b"",
        "backups/20261110T033000Z/db.dump": b"",
        "backups/20261111T033000Z/media.tar.gz": b"",  # dump never arrived
        "backups/not-a-stamp/db.dump": b"",
        "other/20261112T033000Z/db.dump": b"",
    }
    assert complete_stamps(s3, BackupConfig.from_env(ENV)) == ["20261110T033000Z"]


def test_latest_is_the_newest_complete_stamp():
    assert restore.resolve_stamp("latest", ["20261110T033000Z", "20261111T033000Z"]) == "20261111T033000Z"


def test_an_unknown_stamp_is_refused():
    with pytest.raises(SystemExit):
        restore.resolve_stamp("20200101T000000Z", ["20261110T033000Z"])


def test_restore_round_trips_the_race_logs(tmp_path):
    source = tmp_path / "source"
    (source / "race_logs").mkdir(parents=True)
    (source / "race_logs" / "7.jsonl.br").write_bytes(b"seven")
    s3 = FakeS3()
    with mock.patch("deploy.backup.subprocess.run", side_effect=fake_pg_dump):
        backup.run_backup(client=s3, env={**ENV, "DJANGO_MEDIA_ROOT": str(source)}, stamp="20261112T033000Z")

    target = tmp_path / "target"
    with mock.patch("deploy.restore.subprocess.run") as run:
        stamp = restore.run_restore("latest", client=s3, env={**ENV, "DJANGO_MEDIA_ROOT": str(target)})

    assert stamp == "20261112T033000Z"
    assert (target / "race_logs" / "7.jsonl.br").read_bytes() == b"seven"
    assert "--clean" in run.call_args.args[0]


def test_restore_needs_explicit_confirmation():
    with pytest.raises(SystemExit):
        restore.main(["latest"])


def test_a_media_archive_cannot_write_outside_the_media_root(tmp_path):
    evil = tmp_path / "evil.tar.gz"
    payload = tmp_path / "payload"
    payload.write_bytes(b"x")
    with tarfile.open(evil, "w:gz") as tar:
        tar.add(payload, arcname="../escaped")

    with pytest.raises(tarfile.TarError):
        restore.restore_media(evil, tmp_path / "media")
    assert not (tmp_path / "escaped").exists()
