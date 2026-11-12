# Deploying the staging world

**Status:** implemented
**Domain(s):** `deploy/`, `.github/`, `config/` (no game code)
**Issue:** #136
**One-liner:** the game runs on the internet at `velodra.fly.dev`, on the accelerated clock, and every change merged to master reaches it on its own.

## Why this exists

Everything milestone 1 has built so far runs on a laptop. The image (#128),
the accelerated clock (#129), API tokens (#130), report-a-problem (#131) and
the beta world (#139) all assume a host that stays up for days with nobody
watching it, at an address the LLM beta managers (#132) can reach. Nobody
can play the game until that host exists.

This is the operator's half of the game. A player sees it only as an address
that answers and a world that keeps moving. The operator needs a merge to
master to reach the world without anyone running a deploy by hand, and needs
to hear about it when the tick stops, a page crashes or a night's backup
fails.

## Player experience

A beta manager goes to `velodra.fly.dev`, registers or signs in with an API
token, and finds a world that is already playing on the accelerated clock:
season 1 is open, sixteen teams are waiting to be claimed, and a game day
passes every real hour. When a fix is merged, the site drops for about half a
minute and comes back running the new version. A deploy lasts a few game
minutes, so nothing in the game notices.

The operator's side: a merge to master that passes CI deploys itself. A merge
that fails CI deploys nothing. When the tick has stopped for about half an
hour they get an email. A crashing page or a failed scheduled job shows up in
Sentry, labelled *staging*. Every night the world is copied to Cloudflare R2,
and the runbook says how to bring it back. Seeding, wiping and rebuilding the
world between beta runs are single commands that the runbook gives.

## In scope

1. **One Fly app, `velodra`**, served at `velodra.fly.dev`, with its one
   `data` volume, built from the existing all-in-one image.
2. **The committed configuration describes staging.** It names the staging
   settings, a 5-minute tick, Sentry's *staging* label and the app's own
   address. Secrets are never committed.
3. **Every merge to master that passes the whole of CI deploys.** A merge
   that fails CI deploys nothing. There is no manual deploy button.
4. **One deploy at a time, and never an older one.** If two merges land close
   together, the newer one is deployed, and an older commit whose CI finishes
   late does not overwrite it.
5. **A deploy token that works only for this app**, stored as a GitHub repo
   secret.
6. **Backups, tick alerts and Sentry are switched on**, and one manual backup
   is taken to check them.
7. **Tick alerts are tuned to the staging cadence.** The operator is emailed
   after about 30 minutes without a successful tick.
8. **The beta world is seeded** with the staging form of the one-command
   seed, so season 1 is open from the start.
9. **A runbook for the account steps**, in the order the operator runs them,
   with every command written out. It covers the Fly app, volume, secrets and
   token, the R2 bucket and its lifecycle rule, the healthchecks.io check, the
   Sentry project, the GitHub secret, the first deploy and seeding.
10. **A runbook section for the staging world:** its address, its alerts,
    wiping and rebuilding it between beta runs, and freezing the clock before
    a long planned outage.

## Out of scope

- **Deploys without downtime.** These need Postgres on its own machine, no
  volume on the web machine (race logs go to R2), a blue-green deploy and
  migrations the old code can survive. That costs about $3–5 a month more and
  a day or two of work. *Later*, as its own ticket, when downtime matters,
  probably before the human beta.
- **Pushing the image to a registry (GHCR).** Fly builds the image itself.
  *No*: it adds a second place for images to live and does nothing for us.
- **A manual deploy button.** *No*, by Mario's choice: every merge deploys.
- **Pausing the clock around deploys.** *No*: a deploy is a few game
  minutes, and the tick catches up.
- **Renaming the game to Velodra in the UI.** This is part of the Spanish
  translation, #137.
- **Closing registration.** Belongs to #134. Until then the URL is simply not
  shared.
- **Production.** #133 promotes this same app by wiping it and switching its
  settings.

## Rules and edge cases

- **CI is the gate.** A deploy starts only after the whole CI run on master
  has passed. A CI run on a pull request never deploys.
- **A migration lands on the live world** the moment its merge deploys. The
  runbook already describes rehearsing a risky one on a copy of last night's
  backup first.
- **A failed deploy leaves the old version running**, because Fly keeps the
  old machine if the new one never passes its health check. The failure shows
  up as a red run in GitHub Actions.
- **A deploy in the middle of a tick** is already handled by the image: the
  tick gets time to finish and is safe to cut short.
- **Every external service stays optional.** The app deploys and runs before
  any of their keys are set, and each one switches on when its key arrives.
- **Long planned downtime** (more than about three real days) needs the clock
  frozen first. Otherwise the inactivity rule releases every team. The
  runbook says so.

## Decisions taken

- App name: **velodra**. The game will be called Velodra, and the name keeps its address when this app becomes production.
- Account steps: **Mario runs them**, from a written list of commands.
- Deploy trigger: **every merge to master that passes CI**, with no manual button.
- Registration: **left open, URL not shared**, until #134.
- Tick alert: **period 10 min, grace 20 min** on staging, back to 1 h / 1 h at #133.
- Services: **R2 backups, healthchecks.io and Sentry all on now.**
- The committed configuration describes staging, and #133 switches it back in its own PR.
- Renaming the UI to Velodra **moved to #137.**

## Open questions

None.

## Deferred

- Deploys without downtime: when deploy downtime matters, likely before the human beta.
