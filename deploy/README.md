# Deploy: the image, the machine and the runbook

How the game runs outside a laptop. It is one environment on **Fly.io**: one
always-on machine that runs the whole game from one image. The spec and the
reasoning (why Fly, why one environment, why all-in-one) are in
`specs/archive/deploy-image.md`.

This folder is ops code, not a Django app: it holds the image's entrypoint,
schedule, backup and restore, plus this runbook. Its Python (`backup.py`,
`restore.py`, `s3.py`) imports nothing from the game, and its tests live in
`deploy/tests/`.

## What runs where

```
Fly machine (shared-cpu-1x, 512 MB, region ams, never stopped)
├── entrypoint-allinone.sh   supervisor, PID 1's child
│   ├── postgres             127.0.0.1:5432, data in /data/postgres
│   ├── gunicorn             :8000, 2 workers  ← Fly proxy (TLS) ← <app>.fly.dev
│   └── supercronic          deploy/crontab
│       ├── tick.sh          hourly: manage.py tick, then ping healthchecks.io
│       └── backup.py        03:30 UTC: pg_dump + race logs → Cloudflare R2
└── volume "data" → /data    database + race logs (/data/media)
```

- **The Dockerfile has three stages.** `frontend` builds the SPA. `web` is
  the standard Django image (gunicorn plus WhiteNoise, no database).
  `allinone` is `web` plus Debian's PostgreSQL and supercronic.
  `fly.toml` deploys `allinone`.
- **Boot order** (`entrypoint-allinone.sh`):
  1. Own the volume.
  2. Run `initdb` on first boot only.
  3. Start Postgres and wait for it.
  4. Run `migrate`.
  5. Render the crontab.
  6. Start supercronic and gunicorn as the `app` user.

  If any of the three processes exits, the others are stopped and the
  machine exits, and Fly restarts it. Migrations run here rather than in a
  Fly `release_command`, because the release machine has no volume.
- **`/healthz`** (`config/health.py`) answers before the HTTPS redirect
  and host validation. It returns 200 when the database answers and 503 when
  it doesn't. Fly checks it every 30 s.
- **Memory**, measured: gunicorn about 95 MB, a race-simulating tick peaks at
  about 90 MB, Postgres about 40 MB, and Postgres is tuned small. A 512 MB
  swap file (`fly.toml`) is the cushion.
- **Deploying restarts the database with the app.** Expect about 20–30 s of
  downtime per deploy. On a stop, gunicorn and the scheduler get up to 90 s
  to finish, enough for a tick that is still running, and then Postgres is
  stopped cleanly. `fly.toml`'s `kill_timeout` is 120 s, so Fly never
  SIGKILLs the database. The tick itself is interruption-safe
  (`world/README.md`), so a run that is cut short just runs again.

### The tick's cadence

Set by the environment and read by the entrypoint:

| Variable | Default | Effect |
|---|---|---|
| `TICK_SCHEDULE` | `0 * * * *` | Cron expression for the tick. The accelerated staging world (#129) uses `*/5 * * * *`. |

supercronic never starts a tick while the previous one is still running.
**Which clock runs is never an environment variable**: it is decided by
`DJANGO_SETTINGS_MODULE` (`world/README.md`, *Which clock runs where*).

## Configuration

Everything comes from the environment. On Fly, secrets go in with
`fly secrets set NAME=value ...`; locally they go in `deploy/.env`. The
template is `deploy/env.example`.

| Variable | Required | What |
|---|---|---|
| `DJANGO_SECRET_KEY` | yes | `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_ALLOWED_HOSTS` | yes | `<app>.fly.dev` (comma-separated) |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | yes | The database and superuser `initdb` creates on first boot. Never change them afterwards without changing the database too. |
| `DJANGO_SETTINGS_MODULE` | set in `fly.toml` | `config.settings.prod`, or #129's staging module |
| `SENTRY_DSN` | no | Errors from Django and failed scheduled jobs go to Sentry |
| `SENTRY_ENVIRONMENT` | no | Label in Sentry. `fly.toml` sets `production`. |
| `HEALTHCHECKS_TICK_URL` | no | Pinged after every successful tick |
| `BACKUP_S3_BUCKET`, `BACKUP_S3_ENDPOINT`, `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY` | no | R2 for backups. With no bucket, backups are off and the log says so. |
| `BACKUP_S3_PREFIX` | no | Key prefix, default `backups` |
| `WEB_CONCURRENCY` | no | gunicorn workers, default 2 |

The image sets `POSTGRES_HOST=127.0.0.1`, `PGDATA=/data/postgres` and
`DJANGO_MEDIA_ROOT=/data/media`.

## First deploy

Creating the app belongs to #136. The steps:

```bash
fly apps create <app>                # then set `app` in fly.toml
fly volumes create data --region ams --size 1
fly secrets set DJANGO_SECRET_KEY=... DJANGO_ALLOWED_HOSTS=<app>.fly.dev \
    POSTGRES_DB=cycling_manager POSTGRES_USER=cycling POSTGRES_PASSWORD=...
fly deploy                           # builds the allinone target remotely
fly logs                             # watch: initdb, migrate, scheduler, gunicorn
curl https://<app>.fly.dev/healthz   # ok
```

Then seed the world (`world/README.md`, *Building a world*):

```bash
fly ssh console -C "su app -s /bin/sh -c 'cd /app && python manage.py seed_world'"
```

And make an admin:

```bash
fly ssh console -C "su app -s /bin/sh -c 'cd /app && python manage.py createsuperuser'"
```

## Deploying a new version

Run `fly deploy`. The machine restarts, migrations run at boot, and the site
is back once `/healthz` passes. **A migration goes straight onto the live
world**, so rehearse risky ones first (below).

## Monitoring

- **The tick: healthchecks.io.**
  1. Create a check with **period 1 hour** and **grace 1 hour**. That means
     an email after about two missed hourly ticks.
  2. Set its ping URL as `HEALTHCHECKS_TICK_URL`.

  A tick that errors exits non-zero and sends no ping.
- **Errors: Sentry.** Create a free Django project and set `SENTRY_DSN`.
  Unhandled exceptions in requests are reported, and so is every scheduled
  job that fails (tick or backup), through supercronic's own Sentry hook.
  Personal data is not sent.

## Backups

Every night at 03:30 UTC, `python -m deploy.backup` uploads two objects:

- `backups/<YYYYMMDDTHHMMSSZ>/media.tar`, the race logs (not compressed again, since they are brotli already);
- `backups/<YYYYMMDDTHHMMSSZ>/db.dump`, a `pg_dump -Fc` of the database.

The dump is uploaded last, so a timestamp that has a dump is complete. The
race logs are included because they are authoritative records that cannot be
regenerated (`racing/README.md`).

Setting up R2, once:

1. In Cloudflare, create bucket `cycling-manager-backups`.
2. Under *Settings* → *Object lifecycle rules*, add **delete objects 30
   days after upload**. That is the retention; there is no rotation code.
3. Create an R2 API token with *Object Read & Write* on that bucket only.
4. `fly secrets set BACKUP_S3_BUCKET=cycling-manager-backups BACKUP_S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com BACKUP_S3_ACCESS_KEY_ID=... BACKUP_S3_SECRET_ACCESS_KEY=...`
5. Take one backup by hand to check it works:
   `fly ssh console -C "su app -s /bin/sh -c 'cd /app && python -m deploy.backup'"`

Fly's daily volume snapshots are a second, on-Fly safety net. The first
10 GB is free.

## Restoring a backup

`restore` replaces the database's contents and unpacks the race logs over
`/data/media`. Don't run it on the hour, when the tick runs.

```bash
fly ssh console
su app -s /bin/sh
cd /app
python -m deploy.restore --list           # complete backups, oldest first
python -m deploy.restore latest --yes     # or a timestamp from the list
exit; exit
fly machine restart                       # fresh connections, re-run migrate
```

**If the volume itself is lost:**

1. Create a new `data` volume and deploy. First boot runs `initdb` with the
   same `POSTGRES_*` secrets.
2. Run the restore above.

**Tested:** the backup → wipe → restore cycle was run against a local
S3 server on 2026-11-12. The steps were:

1. Seed a world (16 teams) and add a race log.
2. Back up.
3. Boot a brand-new, empty volume (0 teams).
4. Restore `latest`: 16 teams again, the race log back, `/healthz` 200.

## Running the image locally

The same all-in-one image, on your machine:

```bash
cp deploy/env.example deploy/.env
alias dc='docker compose -f deploy/compose.local.yml'
dc up --build -d                                       # http://127.0.0.1:8080
dc exec -u app game python manage.py seed_world         # one-offs: exec into it
dc logs -f game
```

**Use `exec` for one-off commands while it is up, never `run`.** `run`
starts a second container through the entrypoint, and so a second Postgres
on the same volume. The two can't see each other's lock and will corrupt
the data. `run` is only for when nothing is up.

It differs from Fly only in having no TLS (`DJANGO_SECURE_SSL_REDIRECT=0`).
`dc down -v` throws the data away.

### Rehearsing a migration on live data

1. Put the R2 read credentials in `deploy/.env`.
2. On the **current** master, `dc up --build -d` (an empty world).
3. Load last night's live data: `dc exec -u app game python -m deploy.restore latest --yes`
4. `dc down` (keeping the volume), check out the branch with the migration,
   and run `dc up --build -d` again. The migration runs at boot, against a
   copy of the live world.

## Upgrading Postgres

The image pins PostgreSQL's major version (`PG_MAJOR` in the `Dockerfile`,
currently 17), and the Debian release with it. The data directory on the
volume can only be read by the major that wrote it. If the image's major
doesn't match the data, the entrypoint refuses to start and says so.

To move to a new major:
1. Take a backup with the running image.
2. Deploy the new image onto a **new, empty** volume.
3. Restore that backup into it.

## Moving Postgres to its own machine

Do this when memory gets tight or the deploy downtime starts to matter. It
takes an hour or two, with about 5 minutes of downtime:

1. Create a Postgres machine: a Fly app running `postgres:17` with its own
   volume. Set its password.
2. Take a fresh backup, or `pg_dump` directly.
3. `pg_restore` it into the new database.
4. In `fly.toml`, set `build-target = "web"`, add a `release_command =
   "python manage.py migrate --noinput"`, and remove the `[mounts]` block. Race
   logs then need a home: a volume on the web machine, or django-storages on
   R2 (`config/settings/prod.py`).
5. `fly secrets set POSTGRES_HOST=<db-app>.internal` and the new credentials,
   then deploy.
6. Move the cron to the web machine. supercronic as a second Fly process
   group, running the same `deploy/crontab`, does it.

## Cost

USD per month before VAT, Fly's Amsterdam prices (November 2026):

| Item | Cost |
|---|---|
| shared-cpu-1x machine, 512 MB | $3.78 |
| 1 GB volume | $0.15 |
| Egress at $0.02/GB | cents |
| **Total** | **≈ $4** |

R2, healthchecks.io and Sentry are on free tiers. R2's free tier is 10 GB.
Thirty full nightly backups add up as race logs accumulate (about 15 MB per
season, and seasons go by quickly on the accelerated clock). It's a long way
off, but if it gets close, shorten the lifecycle rule. Fly waives invoices under
$5, but across the **whole account**, so this is free only while nothing else
on the account bills.
