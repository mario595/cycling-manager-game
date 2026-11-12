# Deploying the staging world: plan

**Status:** implemented
**Spec:** `specs/archive/staging-deploy.md`
**Issue:** #136

No game code changes. The work is configuration, one GitHub workflow, a
config test and the runbook. Account steps (Fly, Cloudflare, healthchecks.io,
Sentry, the GitHub secret) are Mario's and are written into the runbook,
not automated.

## Decisions

- **`fly.toml` carries the staging environment in `[env]`**:
  `DJANGO_SETTINGS_MODULE=config.settings.staging`,
  `SENTRY_ENVIRONMENT=staging`, `TICK_SCHEDULE="*/5 * * * *"` and
  `DJANGO_ALLOWED_HOSTS=velodra.fly.dev`. The host is not a secret, and
  committing it leaves one less secret to set by hand. `app = "velodra"`.
  #133 changes the first three back.
- **The deploy is a separate workflow, `.github/workflows/deploy.yml`, run by
  `workflow_run` when `CI` completes** on a `push` to `master` with
  `conclusion == success`. That way the whole CI run is the gate, without
  making `ci.yml` itself depend on secrets. A pull request's CI never matches,
  because its event is `pull_request`.
- **Ordering**: `concurrency: {group: fly-deploy, cancel-in-progress: false}`
  keeps one deploy at a time, and GitHub replaces a queued run with a newer
  one. Before deploying, the job checks that the CI run's `head_sha` is still
  the tip of `master`. If it isn't, a newer merge is on its way and this run
  exits successfully without deploying. That stops an older commit whose CI
  finished late from overwriting a newer deploy.
- **`flyctl deploy --remote-only`** builds on Fly's builder, using
  `superfly/flyctl-actions/setup-flyctl@1.6`. `FLY_API_TOKEN` comes from
  `fly tokens create deploy -a velodra`, which is scoped to this app.
- **A config test** (`deploy/tests/test_fly_config.py`, which needs no
  database) parses `fly.toml` with `tomllib` and checks four things: the
  settings module it names is importable as a file, the tick schedule is a
  five-field cron expression, the allowed host is `<app>.fly.dev`, and the
  machine never auto-stops. CI's image job also renders the crontab with
  `fly.toml`'s schedule, not only the default.

## Work items

1. `fly.toml`: app name and staging `[env]`. Add `deploy/tests/test_fly_config.py`.
2. `.github/workflows/deploy.yml` as above. `ci.yml`'s image job tests the crontab rendered with `fly.toml`'s schedule.
3. `deploy/README.md`: a *First deploy* checklist in run order (Fly app, volume, secrets and token, GitHub secret, first deploy, seeding with `seed_world --set-clock`, superuser, R2, healthchecks.io at 10 min / 20 min, Sentry, a manual backup), *Deploying a new version* via CI, and a *The staging world* section (address, wipe and rebuild, freeze before long downtime, what #133 changes). Update `AGENTS.md`'s deployment line.
4. Archive the spec and plan, with `Status: implemented`.

## Test

`python -m pytest deploy` and the full suite. The workflow itself can only be
proven by the first real merge after `FLY_API_TOKEN` is set. The runbook says
to watch that run.
