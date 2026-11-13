# The deploy image: implementation plan

**Spec:** `specs/archive/deploy-image.md` · **Issue:** #128 · **Status:** implemented
**Touches:** `Dockerfile` (new), `.dockerignore` (new), `deploy/` (new, ops files and runbook, not a Django app), `fly.toml` (new), `config/settings/prod.py`, `config/health.py` (new), `requirements.txt`, `.github/workflows/ci.yml`, `AGENTS.md`

## Context you need

- The SPA is built with Vite into `frontend/dist/`, which Django serves
  through WhiteNoise from `STATICFILES_DIRS` and `TEMPLATES["DIRS"]`
  (`frontend/README.md`). `frontend/` imports source from `race_player/src/`,
  so `race_player`'s `node_modules` must be installed before
  `npm run build`. CI already does this.
- `config/settings/prod.py` reads its secrets and the `POSTGRES_*` settings
  from the environment and fails loudly when one is missing. It inherits
  `GAME_CLOCK_CLASS = RealClock` from `base.py`. The clock is never read from
  the environment (`world/README.md`, *Which clock runs where*), and nothing
  here changes that.
- `manage.py tick` exits non-zero when a run records an error. Two ticks
  cannot claim the same race (`select_for_update` in
  `world/services.py`), but they should not overlap anyway.
- `seed_world` (#139) builds a world, and `ALLOW_WORLD_RESET` stays off in
  `prod.py`. #129 adds `staging.py` with it turned on.
- Race logs go through Django's default storage under `MEDIA_ROOT`. They are
  authoritative records, so they are backed up along with the database.
- Measured on a prototype: gunicorn with 2 workers uses about 95 MB, a tick
  that runs a race peaks at about 90 MB and 30–60 s of CPU, and Postgres with
  a seeded world about 40 MB.

## Decisions

1. **One Dockerfile, three stages.** `frontend` (node:20-slim, the build),
   `web` (python:3.12.11-slim, the standard image with no database) and
   `allinone` (`FROM web`, adding Postgres and the scheduler). `fly.toml`
   builds `allinone`. Moving to a separate database later means switching the
   target to `web`.
2. **Postgres is Debian's own package, version 17**, from trixie, which is
   what the base image ships. Dev and CI stay on 16. Dumps are taken and
   restored with the image's own tools, including in a local rehearsal, so the
   version gap never crosses a dump. A PGDG repository would add build
   complexity for no gain.
3. **The scheduler is supercronic**, a single static binary pinned by
   version and checksum. It never starts a job while the previous run of the
   same job is still going, which gives the no-overlap rule for free. With
   `-sentry-dsn` it reports every failed job (tick or backup) to Sentry. Its
   schedule is `deploy/crontab`.
4. **The supervisor is a shell entrypoint, not supervisord.** It runs as
   root:
   - chowns the volume and runs `initdb` on first boot, with the
     `POSTGRES_PASSWORD` superuser;
   - starts Postgres as `postgres`, listening on localhost only and tuned
     small (`shared_buffers=64MB`, `max_connections=20`);
   - waits for it, then runs `migrate` (static files were collected at
     build time, so `collectstatic` is not repeated);
   - starts supercronic and gunicorn as the unprivileged `app` user.

   It then waits for the first of the three to exit and stops the others. The
   container exits and Fly restarts the machine. No extra dependency, and a
   crash is never half-hidden.
5. **Migrations run in the entrypoint, not in Fly's `release_command`.** The
   release command runs on a temporary machine without the volume, so it
   cannot reach a database that lives on that volume.
6. **The health check is middleware, `config/health.py`, first in
   `MIDDLEWARE`.** It answers `GET /healthz` with `ok` after a `SELECT 1`,
   or 503 when that fails, before `SecurityMiddleware` (the HTTPS redirect)
   and before anything calls `get_host()` (`ALLOWED_HOSTS`). Fly's internal
   checks come over plain HTTP with an internal Host header, and a view would
   be rejected by one of those two first.
7. **The backup is `deploy/backup.py`**, plain Python with boto3. boto3 is a
   new runtime dependency: R2 speaks S3, and it is smaller than awscli and
   testable.
   - It writes `pg_dump -Fc` and a `tar.gz` of `MEDIA_ROOT` to
     `<prefix>/<UTC timestamp>/db.dump` and `.../media.tar.gz`.
   - With `BACKUP_S3_BUCKET` unset it logs "backups off" and exits 0.
   - On any other failure it exits non-zero, so supercronic reports it.
   - Retention is an R2 lifecycle rule (expire after 30 days), set once in
     the dashboard (runbook). No rotation code.
8. **The restore is `deploy/restore.py`.** Given a timestamp, or `latest`,
   it downloads both files and then runs `pg_restore --clean --if-exists`
   and untars the media. It shares the S3 client code with `backup.py`
   (`deploy/s3.py`). It is never scheduled.
9. **The tick ping is `deploy/tick.sh`.** It runs `manage.py tick`, and only
   on exit 0 does it `curl` `HEALTHCHECKS_TICK_URL` when that is set. The
   check in healthchecks.io has a 1-hour period with a 1-hour grace (runbook),
   so the email comes after two missed runs.
10. **Sentry is initialised in `prod.py`** when `SENTRY_DSN` is set, with the
    Django integration and `send_default_pii=False`. `sentry-sdk` is a new
    runtime dependency.
11. **Two prod settings become environment-tunable**, both defaulting to
    today's behaviour:
    - `DJANGO_MEDIA_ROOT`, so race logs live on the volume at `/data/media`;
    - `DJANGO_SECURE_SSL_REDIRECT`, which defaults to on and is set to `0`
      only by the local compose file, since there is no TLS in front of it
      locally.

    Neither touches the clock.
12. **`fly.toml`:**
    - region `ams`, the cheapest European multiplier;
    - `[build] target = "allinone"`;
    - a mount `data` → `/data`;
    - `http_service` on 8000 with `force_https`, `auto_stop_machines = "off"`
      and `min_machines_running = 1`;
    - an HTTP check on `/healthz`;
    - `[[vm]]` shared-cpu-1x / 512 MB, and `swap_size_mb = 512`.

    The app name is a placeholder that #136 fills in.
13. **Local run is `deploy/compose.local.yml`**, which builds `allinone`,
    reads `deploy/.env` (gitignored, with a committed `deploy/env.example`),
    keeps a named volume and serves on `127.0.0.1:8080`.
14. **CI builds the image** (`docker build --target allinone`) in a new job,
    so a broken Dockerfile fails the PR. It does not push anything. The push
    and deploy belong to #136.

## Work items

1. **Health check middleware.**
   - Add `config/health.py`, first in `MIDDLEWARE` in `base.py`.
   - Tests in `core/tests.py`, which is the app that holds shared things and
     is in `testpaths`:
     - 200 `ok` with a working database;
     - 503 when the database cursor raises;
     - served with a disallowed Host;
     - not redirected under `SECURE_SSL_REDIRECT=True`.
2. **Prod settings.**
   - Add `DJANGO_MEDIA_ROOT`, `DJANGO_SECURE_SSL_REDIRECT` and Sentry to
     `prod.py`.
   - Add `gunicorn`, `sentry-sdk` and `boto3` to `requirements.txt`.
   - Tests: import `prod.py` under a patched environment and check:
     - the defaults;
     - the overrides;
     - Sentry initialised only with a DSN;
     - `GAME_CLOCK_CLASS` still `RealClock`.
3. **The Dockerfile**, with its `web` and `allinone` stages and
   `.dockerignore`, plus the entrypoint, `deploy/crontab` and
   `deploy/tick.sh`. Verify by hand:
   - the image builds;
   - first boot initialises the database and migrates;
   - a second boot does neither initialisation step again;
   - `/healthz` returns 200;
   - killing gunicorn stops the container.
4. **Backup and restore.**
   - Add `deploy/s3.py`, `deploy/backup.py` and `deploy/restore.py`.
   - Unit tests in `deploy/tests/test_backup.py`, added to `testpaths`, with a
     fake S3 client and a stubbed `subprocess`. They check:
     - object key layout;
     - "off" with no bucket;
     - a non-zero exit when `pg_dump` fails;
     - `latest` picks the newest timestamp.
   - Verify by hand once against a local MinIO: seed, back up, wipe the
     volume, restore, and see the same teams and race logs.
5. **`fly.toml` and `deploy/compose.local.yml`** with `deploy/env.example`.
6. **CI image build job.**
7. **Docs.**
   - `deploy/README.md` is the runbook: what runs where, first deploy,
     secrets, seeding, deploying, R2 and healthchecks setup, restore,
     rehearsing a migration locally, moving Postgres to its own machine, and
     cost.
   - Update `AGENTS.md`: tech stack *Deployment*, project structure, and
     the generated-files note on `/data/media`.
   - Move the spec and plan to `specs/archive/`.

## Not in here

Creating the Fly app, its secrets, pushing to GHCR and the CI deploy (#136),
`staging.py` and the 5-minute schedule (#129), email on 500s (#133).
