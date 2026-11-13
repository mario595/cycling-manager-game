# The deploy image

**Status:** implemented
**Domain(s):** `config/`, `world/`, `frontend/` (build only)
**Issue:** #128
**One-liner:** one self-contained machine image that runs the whole game (the website, its database and the hourly tick) on Fly.io, backs itself up off the box every night, and says when the tick has stopped.

## Why this exists

The game runs only on a developer's laptop today. Everything in milestone 1
(the LLM beta managers, the report-a-problem channel, the accelerated
clock) needs it to run somewhere that stays up, with nobody watching, for
days. The tick in particular: the game is a scheduled simulation, and a
world whose tick silently stopped looks like a broken game to every manager
in it.

This is the operator's half of the game. No player sees it directly. What
they notice is that the site loads over HTTPS, races start when the
calendar says they will, and a bad deploy does not lose the season.

## Player experience

A beta manager opens the game at its `fly.dev` address and logs in. Pages
load quickly. While a race is being simulated they can be a second or two
slower, and nobody notices. Races start at their scheduled time because the
tick runs on schedule. When the operator deploys a new version, the site is
gone for about half a minute and then comes back with nothing lost.

The operator's side: if the tick stops completing, they get an email within
about two hours. When a page crashes, the error shows up in an error-tracking
inbox with its traceback. Every night the database and the race logs are
copied off the machine. If the machine's disk is lost, the operator follows a
written runbook, and the world comes back as it was the night before.

## In scope

1. **One image runs the whole game:** the web app with the compiled frontend,
   PostgreSQL, and the scheduler that runs the tick. All three run on one Fly.io
   machine (shared-cpu-1x, 512 MB) with one persistent volume that holds both
   the database and the race logs.
2. **The web part is a standard image of its own**, with no database inside
   it. The all-in-one image is a thin layer on top. Moving the database to its
   own machine later means deleting that layer and changing one setting. The
   runbook says how.
3. **The machine never sleeps.** The tick needs an always-on host
   (`world/README.md`, *Deployment requirement*).
4. **The tick runs every hour** from the scheduler inside the machine. #129
   changes how often, for the accelerated clock.
5. **Every boot brings the database up to date** (migrations) before the site
   starts serving.
6. **A health check** that Fly uses to restart a machine that has stopped
   answering.
7. **A nightly off-box backup** of the database and the race logs to
   Cloudflare R2, with the last 30 nights kept.
8. **A restore that has been done at least once** from a real backup, written
   down step by step.
9. **Tick monitoring:** every successful tick pings a healthchecks.io check,
   and the operator is emailed when two hourly pings are missed.
10. **Error reporting** to Sentry's free tier.
11. **Every external service is optional:** with no key set, backups, the tick
    ping and Sentry each switch themselves off and say so in the log. The image
    still runs.
12. **The same image runs locally** with one command, for debugging and for
    rehearsing a migration on a restored copy of the live data.
13. **A runbook:** first boot, setting secrets, seeding a world, deploying,
    restoring a backup, rehearsing a migration locally, and moving Postgres to
    its own machine.

## Out of scope

- **A second, permanent staging environment.** There is one environment. It
  runs on the accelerated clock for milestone 1 (#129). At launch (#133) it is
  wiped, switched to the real clock and re-seeded.
- **Hetzner, docker compose for production, and Caddy.** These were the
  original proposal. Fly provides TLS and routing, and the `fly.dev` hostname
  means no domain is needed.
- **Fly's Managed Postgres.** It costs $38 a month at its smallest, against
  about $4 for the whole machine.
- **Creating the Fly app, setting its secrets, and the CI deploy.** These
  belong to #136. This ticket builds and verifies the image locally.
- **The accelerated clock and its schedule** belong to #129.
- **Daily-plus-weekly backup rotation.** Cut. A single 30-day expiry is enough
  for a beta.
- **Email on 500s.** Deferred to #133, which picks the email provider.
  Sentry covers it until then.

## Rules and edge cases

- **Memory:** the measured working set (web about 95 MB, a race tick peaking
  at about 90 MB, Postgres about 40 MB) leaves room in 512 MB. A small swap
  file guards against an out-of-memory kill taking the database down.
- **A deploy restarts the database too.** About 20–30 seconds of downtime per
  deploy is accepted for the beta.
- **Two ticks never overlap.** If a tick is still running when the next one is
  due, the next one waits or is skipped. It does not start a second copy.
- **A failed backup is noisy.** It goes to Sentry and does not count as
  success. A missing R2 key is not a failure; it is "backups off" and is
  logged as such.
- **Restore never runs by itself.** It is a deliberate operator step from the
  runbook.
- **Secrets are never in the image or the repo.** They come from the
  environment (`fly secrets` in #136, a local `.env` when run locally).
- **Cost:** about $4 a month. Fly waives invoices under $5, but the waiver
  applies to the whole account, so it is free only if nothing else on the
  account bills.

## Decisions taken

- **Host:** Fly.io. Mario already has an account. Hetzner CX23 is no longer
  orderable, and the CPX02 is too small to host two environments. At one
  environment the price difference is about a euro.
- **One environment, not two:** it runs accelerated first and is promoted to
  production later. Local containers cover debugging and migration
  rehearsals.
- **All-in-one machine** rather than a separate Postgres machine (about $8 a
  month), with the move to separate machines documented.
- **No domain for now:** the `fly.dev` hostname has TLS included.
- **Scheduler inside the machine:** Fly's own scheduled machines run only
  "approximately hourly", which is too loose for the tick and cannot do #129's
  5-minute cadence.
- **Backups to R2, kept for 30 nights.**
- **Tick monitoring:** healthchecks.io, alerting after two missed hourly pings.
- **Errors:** Sentry's free tier, rather than email on 500s.

## Open questions

None.

## Deferred

- **Postgres on its own machine:** when memory gets tight or the deploy
  downtime starts to matter, most likely once human testers join.
- **Email alerts on 500s:** with #133's email provider.
- **A custom domain:** whenever one is wanted. Fly issues its certificate.
