# Deploy: the image, the machine and the runbook

How the game runs outside a laptop. It is one environment on **Fly.io**, the
app **`velodra`** at **https://velodra.fly.dev**: one always-on machine that
runs the whole game from one image. During milestone 1 it is the accelerated
staging world (*The staging world*, below), and #133 promotes it to
production. The spec and the reasoning (why Fly, why one environment, why
all-in-one) are in `specs/archive/deploy-image.md`. Deploying it, and every
account behind it, is `specs/archive/staging-deploy.md` (#136).

This folder is ops code, not a Django app: it holds the image's entrypoint,
schedule, backup and restore, plus this runbook. Its Python (`backup.py`,
`restore.py`, `s3.py`) imports nothing from the game, and its tests live in
`deploy/tests/`.

## What runs where

```
Fly machine (shared-cpu-1x, 512 MB, region ams, never stopped)
├── entrypoint-allinone.sh   supervisor, PID 1's child
│   ├── postgres             127.0.0.1:5432, data in /data/postgres
│   ├── gunicorn             :8000, 2 workers  ← Fly proxy (TLS) ← velodra.fly.dev
│   └── supercronic          deploy/crontab
│       ├── tick.sh          TICK_SCHEDULE (staging: every 5 min): manage.py tick, then ping healthchecks.io
│       ├── beta_agents      minute 5 of every hour: start the LLM testers' workflow if one is due (staging only, beta_agents/README.md)
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
  to finish (the tick ignores the SIGTERM a stop sends it, `deploy/tick.sh`), enough for a tick that is still running, and then Postgres is
  stopped cleanly. `fly.toml`'s `kill_timeout` is 120 s, so Fly never
  SIGKILLs the database. The tick itself is interruption-safe
  (`world/README.md`), so a run that is cut short just runs again.

### The tick's cadence

Set by the environment and read by the entrypoint:

| Variable | Default | Effect |
|---|---|---|
| `TICK_SCHEDULE` | `0 * * * *` | Cron expression for the tick. The accelerated staging world (#129) uses `*/5 * * * *`, set in `fly.toml`. |

supercronic never starts a tick while the previous one is still running.
**Which clock runs is never an environment variable**: it is decided by
`DJANGO_SETTINGS_MODULE` (`world/README.md`, *Which clock runs where*).

## Configuration

Everything comes from the environment. On Fly, what is not secret is
committed in `fly.toml`'s `[env]`, and secrets go in with
`fly secrets set NAME=value ...`. Locally both go in `deploy/.env`, from the
template `deploy/env.example`. `deploy/tests/test_fly_config.py` checks
`fly.toml`'s values in CI.

| Variable | Required | What |
|---|---|---|
| `DJANGO_SECRET_KEY` | yes | `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_ALLOWED_HOSTS` | set in `fly.toml` | `velodra.fly.dev` (comma-separated) |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | yes | The database and superuser `initdb` creates on first boot. Never change them afterwards without changing the database too. |
| `DJANGO_SETTINGS_MODULE` | set in `fly.toml` | `config.settings.staging` for milestone 1, `config.settings.prod` from #133 |
| `SENTRY_DSN` | no | Errors from Django and failed scheduled jobs go to Sentry |
| `SENTRY_ENVIRONMENT` | no | Label in Sentry. `fly.toml` sets `staging`, and `production` from #133. |
| `HEALTHCHECKS_TICK_URL` | no | Pinged after every successful tick |
| `BACKUP_S3_BUCKET`, `BACKUP_S3_ENDPOINT`, `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY` | no | R2 for backups. With no bucket, backups are off and the log says so. |
| `BACKUP_S3_PREFIX` | no | Key prefix, default `backups` |
| `WEB_CONCURRENCY` | no | gunicorn workers, default 2 |
| `BETA_DISPATCH_TOKEN` | staging only | A fine-grained GitHub token that lets the hourly `python -m beta_agents dispatch` start the LLM testers' workflow (#160). Without it that job does nothing. Setup is in `beta_agents/README.md`, *The workflow*. Never set it in production. |

The image sets `POSTGRES_HOST=127.0.0.1`, `PGDATA=/data/postgres` and
`DJANGO_MEDIA_ROOT=/data/media`.

## First deploy

Done once, by the operator, on a laptop with
[`flyctl`](https://fly.io/docs/flyctl/install/) signed in (`fly auth login`).

**Add a payment method to the Fly organization first.** A trial
organization stops every machine 5 minutes after it starts (`flyd`,
`requested_stop=true` in `fly machine status`), and the proxy only starts it
again on the next request, so the tick barely runs. That cost the first
deploy a day (#136). The bill is under Fly's $5 waiver either way.
In this order. Each external service is optional: the app runs before its
key is set, and the service switches on when the key arrives.

**1. The app, its volume and its secrets.**

```bash
fly apps create velodra                       # fly.toml already says app = "velodra"
fly volumes create data --app velodra --region ams --size 1 --yes
fly secrets set --app velodra --stage \
    DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" \
    POSTGRES_DB=cycling_manager POSTGRES_USER=cycling \
    POSTGRES_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
```

`--stage` stores the secrets without trying to restart a machine that does
not exist yet. The Postgres password never needs to be known: nothing
outside the machine connects to the database.

**2. The deploy token, as a GitHub secret.** It can deploy this one app and
nothing else on the account.

```bash
fly tokens create deploy --app velodra --name github-actions --expiry 8760h \
    | gh secret set FLY_API_TOKEN --repo mario595/cycling-manager-game
```

(Or paste the token into GitHub, *Settings* → *Secrets and variables* →
*Actions* → *New repository secret*, named `FLY_API_TOKEN`.) It expires
after a year; the deploy run fails with an auth error when it does, and the
fix is to run this again.

**3. The first deploy.** From a checkout of master:

```bash
fly deploy --app velodra                      # builds the allinone target remotely
fly logs --app velodra                        # watch: initdb, migrate, scheduler, gunicorn
curl https://velodra.fly.dev/healthz          # ok
```

From then on every merge deploys itself (*Deploying a new version*).

**4. The world, and an admin.** `--set-clock` is the staging form: it moves
the accelerated clock to season 1's start and ticks once, so the world opens
already playing (`world/README.md`, *Building a world*).

```bash
fly ssh console --app velodra -C "su app -s /bin/sh -c 'cd /app && python manage.py seed_world --set-clock'"
fly ssh console --app velodra --pty -C "su app -s /bin/sh -c 'cd /app && python manage.py createsuperuser'"
```

`--yes` on `volumes create` accepts Fly's warning that one volume means no
redundancy: that is the design, and the nightly backup is the safety net.
`createsuperuser` asks questions, hence `--pty`.

**5. Backups.** Follow *Backups* → *Setting up R2* below, including the one
backup by hand.

**6. Tick alerts.** On healthchecks.io, create a check named *velodra tick*
with **period 10 minutes** and **grace 50 minutes**. That emails after about
an hour without a successful tick: one game day on the accelerated clock.
Not tighter: the ping goes out only when a tick ends, and a race tick held
at the CPU baseline takes 15–20 minutes, two races back to back on a stage
day twice that (*What the machine can do: CPU*). (Production goes back to 1 hour and 1 hour, #133.) Then:

```bash
fly secrets set --app velodra HEALTHCHECKS_TICK_URL=https://hc-ping.com/<uuid>
```

**7. Errors.** In Sentry, create a project for the **Django** platform, take
its DSN, and:

```bash
fly secrets set --app velodra SENTRY_DSN=https://<key>@<org>.ingest.sentry.io/<id>
```

Events arrive labelled `staging` (`fly.toml`). To check it works, open
`fly ssh console --app velodra`, then `su app -s /bin/sh`, `cd /app`,
`python manage.py shell`, and run
`import sentry_sdk; sentry_sdk.capture_message("velodra hello"); sentry_sdk.flush()`.
The message shows up in the project within a minute.

Each `fly secrets set` without `--stage` restarts the machine, about 30 s of
downtime, so the last three can be set in one command once all three keys
are to hand.

## Deploying a new version

**Every merge to master deploys itself.** `.github/workflows/deploy.yml`
runs when the `CI` workflow finishes on a push to master. If CI passed, it
runs `flyctl deploy --remote-only` with the `FLY_API_TOKEN` secret.

- **CI is the gate.** A red CI run deploys nothing, and a pull request's CI
  never deploys.
- **One deploy at a time, and the newest wins.** Deploys queue behind each
  other, and a run still waiting is replaced by a newer one. A run whose
  commit is no longer the tip of master skips itself, because the newer
  merge's own run will deploy that one. So an older commit whose CI happens
  to finish last never overwrites a newer deploy.
- **A failed deploy leaves the old version up.** Fly keeps the old machine
  if the new one never passes `/healthz`. The run goes red in *Actions*;
  `fly logs --app velodra` says why.
- Until `FLY_API_TOKEN` is set, the run succeeds without deploying and says
  so.

The machine restarts, migrations run at boot, and the site is back once
`/healthz` passes, about 30 s. **A migration goes straight onto the live
world**, so rehearse risky ones first (below). A hand deploy, `fly deploy
--app velodra` from a checkout, still works, but the next merge replaces it.

**Deploys without downtime are deliberately not built.** They need Postgres
on its own machine (*Moving Postgres to its own machine*), no volume on the
web machine (race logs to R2), Fly's `bluegreen` strategy, and migrations that
the old code can survive, since they would run while it still serves. That's
about $3–5 a month more. It is worth doing when deploy downtime starts to
matter, probably before the human beta.

## What the machine can do: CPU

A `shared-cpu-1x` is guaranteed **6.25% of a core**. It bursts to a full core
on credit it saves while below that, and once the credit is spent the host
holds it at the baseline (inside the VM this shows as ~90% steal in `top`;
in Fly's Grafana, *CPU utilization* sits on the 6.25% line). At full speed a
race simulates in under a minute; held at the baseline it takes **15–20
minutes**. Measured on 2026-11-13, when restarts and seeding had spent the
credit.

- **Normal play fits the baseline.** The world calendar has ~20 races a
  season, about one every 4 game days. On the accelerated clock that is
  every ~4 real hours, so even a throttled race leaves the machine idle,
  earning credit, most of the time. A tick with nothing due takes seconds.
- **A catch-up is slow.** After an outage, the first tick simulates every
  race that fell due, one after another, at the baseline. supercronic skips
  the ticks that come due meanwhile (`not starting: job is still running`),
  and healthchecks.io gets no ping until it ends. That's expected, not a
  hang: check the log for the tick's `starting` line and the CPU graph.
- **If it stops fitting** (agents notice slow pages while a race runs, or the
  graph sits on the baseline between races), move to `shared-cpu-2x`: twice
  the baseline and the burst, about $2 a month more. Change `[[vm]]` in
  `fly.toml`, not `fly scale`, or the next deploy undoes it.

## The staging world

For milestone 1 the app runs `config.settings.staging` (`fly.toml`): the
production game on the **accelerated clock**, 24× real time, so a game day
passes every real hour and a season every ~3.5 days (`world/README.md`,
*The accelerated clock*). The tick runs every 5 minutes. Nothing advances the
clock; it moves by itself. The tick declares the next season by itself too,
so there is no `add_season` cron. The LLM managers' briefing on what the
speed means is `world/STAGING_BRIEFING.md`.

- **The beta testers** (#132) play from GitHub Actions, not from this
  machine: five LLM managers on their own accounts and API keys, run by
  `.github/workflows/beta-agents.yml`. Setting them up, pausing them and
  choosing their model are in `beta_agents/README.md`. Their reports land in
  Django admin like anyone else's. **Before promoting to production (#133),
  pause them** (`BETA_AGENTS_ENABLED`), or they will play on the real clock
  at staging's cadence.
- **The address is not advertised.** Registration is open until #134
  (invite-only) lands. Only the beta managers are meant to be there.
- **Wiping and rebuilding between beta runs** keeps the accounts and
  rebuilds the world from scratch (`world/README.md`, *The wipe*):
  ```bash
  fly ssh console --app velodra -C "su app -s /bin/sh -c 'cd /app && python manage.py seed_world --set-clock --reset'"
  ```
- **Freeze the clock before planned downtime longer than about three real
  days**, or the inactivity rule releases every team when it comes back.
  Freezing pauses game time; resuming carries on from where it stopped:
  ```bash
  fly ssh console --app velodra -C "su app -s /bin/sh -c 'cd /app && python manage.py mock_clock freeze'"
  fly ssh console --app velodra -C "su app -s /bin/sh -c 'cd /app && python manage.py mock_clock resume'"
  fly ssh console --app velodra -C "su app -s /bin/sh -c 'cd /app && python manage.py mock_clock status'"
  ```
  A deploy, a restart or a short outage needs nothing: the tick catches up.
- **Promoting it to production (#133)** means wiping the world, setting
  `fly.toml`'s `DJANGO_SETTINGS_MODULE`, `SENTRY_ENVIRONMENT` and
  `TICK_SCHEDULE` back to `config.settings.prod`, `production` and
  `0 * * * *`, setting the healthchecks.io check back to 1 h / 1 h, and
  running `seed_world --reset` on the real clock. Staging's game time runs
  ahead of real time, so its world cannot be carried over as it is.

## Monitoring

- **The tick: healthchecks.io.**
  1. Create a check. On the staging world, use **period 10 minutes** and
     **grace 50 minutes**, which emails after about an hour without a
     successful tick, longer than a throttled race tick takes. On the hourly production tick (#133), use **period 1 hour** and
     **grace 1 hour**, which emails after about two missed ticks.
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
4. `fly secrets set --app velodra BACKUP_S3_BUCKET=cycling-manager-backups BACKUP_S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com BACKUP_S3_ACCESS_KEY_ID=... BACKUP_S3_SECRET_ACCESS_KEY=...`
5. Take one backup by hand to check it works:
   `fly ssh console --app velodra -C "su app -s /bin/sh -c 'cd /app && python -m deploy.backup'"`

Fly's daily volume snapshots are a second, on-Fly safety net. The first
10 GB is free.

## Restoring a backup

`restore` replaces the database's contents and unpacks the race logs over
`/data/media`. Don't run it while a tick runs. In production that is on the
hour. On staging a tick starts every 5 minutes and takes seconds, so start
the restore just after one has finished (`fly logs` shows each one).

```bash
fly ssh console --app velodra
su app -s /bin/sh
cd /app
python -m deploy.restore --list           # complete backups, oldest first
python -m deploy.restore latest --yes     # or a timestamp from the list
exit; exit
fly apps restart velodra                  # fresh connections, re-run migrate
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
